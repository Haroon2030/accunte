"""
منطق صندوق واتساب: استقبال أحداث Evolution، مطابقة الموردين، الإسناد، الحالات، والإرسال.
"""
import datetime
import logging
import re
import threading

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models import F
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.core.access import has_role
from apps.core.models import Notification, Role

from . import client
from .client import WhatsAppError
from .models import ConversationAssignment, ConversationMessage, SupplierConversation

log = logging.getLogger(__name__)
S = SupplierConversation.Status
M = ConversationMessage
RT = Role.RoleType

SUPERVISOR_ROLES = (RT.ADMIN, RT.CS_SUPERVISOR, RT.MANAGER)
AGENT_ROLES = (RT.CS_AGENT,)
VIEW_ROLES = (RT.ADMIN, RT.CS_SUPERVISOR, RT.CS_AGENT, RT.MANAGER, RT.CFO, RT.AUDITOR)
TYPING_TTL = 60
MAX_TEXT = 4000


class ConversationError(Exception):
    """رسالة عربية جاهزة للعرض."""


# ── استخراج المحتوى من حمولة Evolution ─────────────────────────────────────────
WRAPPERS = ('ephemeralMessage', 'viewOnceMessage', 'viewOnceMessageV2', 'documentWithCaptionMessage',
            'editedMessage')
IGNORED = ('reactionMessage', 'protocolMessage', 'senderKeyDistributionMessage', 'messageContextInfo')


def extract_content(message):
    """يُرجع (kind, body, media_name) أو None إن كانت الرسالة غير معروضة (تفاعل/بروتوكول)."""
    if not isinstance(message, dict):
        return None
    for _ in range(3):   # فك الأغلفة المتداخلة
        for w in WRAPPERS:
            inner = message.get(w)
            if isinstance(inner, dict) and isinstance(inner.get('message'), dict):
                message = inner['message']
                break
        else:
            break
    if isinstance(message.get('conversation'), str):
        return M.Kind.TEXT, message['conversation'], ''
    ext = message.get('extendedTextMessage')
    if isinstance(ext, dict):
        return M.Kind.TEXT, str(ext.get('text') or ''), ''
    for key, kind in (('imageMessage', M.Kind.IMAGE), ('videoMessage', M.Kind.VIDEO),
                      ('audioMessage', M.Kind.AUDIO), ('documentMessage', M.Kind.DOCUMENT),
                      ('stickerMessage', M.Kind.STICKER)):
        m = message.get(key)
        if isinstance(m, dict):
            return kind, str(m.get('caption') or ''), str(m.get('fileName') or '')[:255]
    if any(k in message for k in IGNORED) and len(message) <= 2:
        return None
    return M.Kind.OTHER, '', ''


def jid_to_number(key):
    """رقم دولي من معرّف واتساب. المجموعات والبث والمعرفات المخفية بلا رقم تُتجاهل."""
    jid = str(key.get('remoteJid') or '')
    if jid.endswith('@lid'):
        jid = str(key.get('remoteJidAlt') or key.get('senderPn') or '')
    if not jid.endswith('@s.whatsapp.net'):
        return None
    digits = re.sub(r'\D', '', jid.split('@')[0])
    return digits if 8 <= len(digits) <= 15 else None


def _timestamp(value):
    try:
        if isinstance(value, dict):
            value = value.get('low')
        ts = int(value)
        if ts > 10 ** 12:
            ts //= 1000
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return timezone.now()


# ── مطابقة المورد ─────────────────────────────────────────────────────────────
def match_supplier(number):
    """يربط الرقم بمورد عبر جهات الاتصال المعتمدة. يُرجع (supplier, contact) أو (None, None) عند الغموض."""
    from apps.suppliers.models import SupplierContact
    contacts = list(SupplierContact.objects.filter(phone=number, is_approved=True).select_related('supplier')[:5])
    if not contacts or len({c.supplier_id for c in contacts}) != 1:
        return None, None
    return contacts[0].supplier, contacts[0]


# ── الاستقبال ─────────────────────────────────────────────────────────────────
def _notify(users, title, message, conv):
    rows = [Notification(recipient=u, category=Notification.Category.SYSTEM, title=title, message=message,
                         link=f'/inbox/{conv.pk}/') for u in users if u.is_active]
    if rows:
        Notification.objects.bulk_create(rows)


def _desk_users(*role_types):
    return list(get_user_model().objects.filter(is_active=True, profile__role__role_type__in=role_types))


def _get_conversation(number, push_name):
    try:
        with transaction.atomic():
            conv, created = SupplierConversation.objects.get_or_create(
                contact_number=number, defaults={'display_name': push_name[:150], 'status': S.NEW})
    except IntegrityError:   # حدث متزامن أنشأها قبلنا
        conv, created = SupplierConversation.objects.get(contact_number=number), False
    return conv, created


def ingest_message(data):
    """يعالج حدث messages.upsert واحدًا. يُرجع 'created' | 'duplicate' | 'ignored'."""
    key = data.get('key') or {}
    wa_id = str(key.get('id') or '')[:128]
    number = jid_to_number(key)
    content = extract_content(data.get('message'))
    if not number or not wa_id or content is None:
        return 'ignored'
    kind, body, media_name = content
    from_me = bool(key.get('fromMe'))
    ts = _timestamp(data.get('messageTimestamp'))
    push_name = '' if from_me else str(data.get('pushName') or '')

    with transaction.atomic():
        if M.objects.filter(wa_message_id=wa_id).exists():
            return 'duplicate'
        conv, created = _get_conversation(number, push_name)
        conv = SupplierConversation.objects.select_for_update().get(pk=conv.pk)
        try:
            with transaction.atomic():
                msg = M.objects.create(
                    conversation=conv, direction=M.Direction.OUT if from_me else M.Direction.IN, wa_message_id=wa_id,
                    kind=kind, body=body, media_name=media_name, timestamp=ts,
                    status=M.DeliveryStatus.SENT if from_me else M.DeliveryStatus.RECEIVED)
        except IntegrityError:
            return 'duplicate'

        reopened = False
        if conv.supplier_id is None:
            conv.supplier, conv.contact = match_supplier(number)
        if push_name and not conv.display_name:
            conv.display_name = push_name[:150]
        if conv.last_message_at is None or ts >= conv.last_message_at:
            conv.last_message_at = ts

        if from_me:
            # رد من الهاتف نفسه: يُغلق انتظار الرد
            if conv.awaiting_reply_since:
                msg.response_seconds = max(0, int((ts - conv.awaiting_reply_since).total_seconds()))
                msg.save(update_fields=['response_seconds'])
                conv.last_response_seconds = msg.response_seconds
                conv.awaiting_reply_since = None
        else:
            conv.unread_count = F('unread_count') + 1
            if conv.awaiting_reply_since is None:
                conv.awaiting_reply_since = ts
            if conv.status in (S.CLOSED, S.PENDING):
                reopened = conv.status == S.CLOSED
                conv.status = S.OPEN if conv.assigned_agent_id else S.NEW
                conv.closed_at = None
        conv.save()
        conv.refresh_from_db()

        if not from_me:
            if created or reopened:
                _notify(_desk_users(RT.CS_SUPERVISOR, RT.CS_AGENT), 'محادثة واتساب جديدة',
                        f'{conv.display_name or conv.contact_number}: {body[:60] or "[" + msg.get_kind_display() + "]"}', conv)
            elif conv.assigned_agent_id and conv.unread_count == 1:
                _notify([conv.assigned_agent], 'رسالة جديدة من مورد',
                        f'{conv.display_name or conv.contact_number}: {body[:60] or "[" + msg.get_kind_display() + "]"}', conv)
    return 'created'


STATUS_RANK = {M.DeliveryStatus.PENDING: 0, M.DeliveryStatus.SENT: 1, M.DeliveryStatus.DELIVERED: 2,
               M.DeliveryStatus.READ: 3}
ACK_MAP = {'SERVER_ACK': M.DeliveryStatus.SENT, 'DELIVERY_ACK': M.DeliveryStatus.DELIVERED,
           'READ': M.DeliveryStatus.READ, 'PLAYED': M.DeliveryStatus.READ}


def ingest_status(data):
    """تحديث حالة التسليم لرسالة صادرة. لا يُنزل الحالة أبدًا (قُرئت لا تعود وصلت)."""
    wa_id = str(data.get('keyId') or data.get('messageId') or (data.get('key') or {}).get('id') or '')
    new = ACK_MAP.get(str(data.get('status') or '').upper())
    if not wa_id or new is None:
        return 'ignored'
    msg = M.objects.filter(wa_message_id=wa_id, direction=M.Direction.OUT).first()
    if msg is None:
        return 'ignored'
    if STATUS_RANK.get(msg.status, 0) >= STATUS_RANK[new]:
        return 'duplicate'
    M.objects.filter(pk=msg.pk).update(status=new)
    return 'updated'


def handle_event(payload):
    """نقطة الدخول من الـ webhook. يُرجع عدد الأحداث المعالجة."""
    event = str(payload.get('event') or '').lower().replace('_', '.')
    data = payload.get('data')
    items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    done = 0
    for item in items:
        if event == 'messages.upsert':
            result = ingest_message(item)
        elif event == 'messages.update':
            result = ingest_status(item)
        else:
            result = 'ignored'
        done += result in ('created', 'updated')
    return done


# ── الإسناد والحالات (قفل تفاؤلي + تشاؤمي) ────────────────────────────────────
def is_supervisor(user):
    return has_role(user, *SUPERVISOR_ROLES)


def can_act(user, conv):
    """هل يحق للمستخدم الرد/تغيير الحالة؟ الموظف على محادثته فقط، والمشرف على الكل."""
    if is_supervisor(user):
        return True
    return has_role(user, *AGENT_ROLES) and conv.assigned_agent_id == user.pk


def _record_assignment(conv, agent, by):
    conv.assignments.filter(is_active=True).update(is_active=False, active_conversation=None, ended_at=timezone.now())
    if agent is not None:
        ConversationAssignment.objects.create(conversation=conv, agent=agent, assigned_by=by)


@transaction.atomic
def claim(conv_id, user):
    """استلام محادثة غير مسندة. يفشل بأمان إن سبقك موظف آخر (UPDATE شرطي ذري)."""
    if not (has_role(user, *AGENT_ROLES) or is_supervisor(user)):
        raise ConversationError('ليس لديك صلاحية استلام المحادثات')
    rows = (SupplierConversation.objects.filter(pk=conv_id, assigned_agent__isnull=True)
            .exclude(status=S.CLOSED)
            .update(assigned_agent=user, status=S.OPEN, version=F('version') + 1))
    if rows == 0:
        raise ConversationError('تم استلام هذه المحادثة من موظف آخر أو أُغلقت')
    conv = SupplierConversation.objects.get(pk=conv_id)
    _record_assignment(conv, user, user)
    log_action(AuditLog.Action.UPDATE, conv, entity_type='whatsapp.Conversation',
               previous={'assigned_agent': None}, new={'assigned_agent': user.pk}, reason='استلام محادثة', actor=user)
    return conv


@transaction.atomic
def assign(conv_id, agent, by, expected_version=None):
    if not is_supervisor(by):
        raise ConversationError('الإسناد للمشرفين فقط')
    if not has_role(agent, *AGENT_ROLES, *SUPERVISOR_ROLES) or not agent.is_active:
        raise ConversationError('المستخدم المختار ليس موظف خدمة عملاء')
    conv = SupplierConversation.objects.select_for_update().get(pk=conv_id)
    if expected_version is not None and conv.version != expected_version:
        raise ConversationError('تغيّرت المحادثة أثناء عملك، حدّث الصفحة وأعد المحاولة')
    if conv.status == S.CLOSED:
        raise ConversationError('المحادثة مغلقة')
    old = conv.assigned_agent_id
    conv.assigned_agent = agent
    if conv.status == S.NEW:
        conv.status = S.OPEN
    conv.version += 1
    conv.save()
    _record_assignment(conv, agent, by)
    log_action(AuditLog.Action.UPDATE, conv, entity_type='whatsapp.Conversation', previous={'assigned_agent': old},
               new={'assigned_agent': agent.pk}, reason='إسناد محادثة', actor=by)
    _notify([agent], 'أُسندت إليك محادثة واتساب', f'{conv.display_name or conv.contact_number}', conv)
    return conv


@transaction.atomic
def release(conv_id, user):
    conv = SupplierConversation.objects.select_for_update().get(pk=conv_id)
    if not can_act(user, conv):
        raise ConversationError('ليس لديك صلاحية على هذه المحادثة')
    old = conv.assigned_agent_id
    conv.assigned_agent = None
    if conv.status != S.CLOSED:
        conv.status = S.NEW
    conv.version += 1
    conv.save()
    _record_assignment(conv, None, user)
    log_action(AuditLog.Action.UPDATE, conv, entity_type='whatsapp.Conversation', previous={'assigned_agent': old},
               new={'assigned_agent': None}, reason='إعادة المحادثة للصندوق', actor=user)
    return conv


@transaction.atomic
def set_status(conv_id, user, to, reason=''):
    conv = SupplierConversation.objects.select_for_update().get(pk=conv_id)
    if not can_act(user, conv):
        raise ConversationError('ليس لديك صلاحية على هذه المحادثة')
    if to not in (S.OPEN, S.PENDING, S.ESCALATED, S.CLOSED):
        raise ConversationError('حالة غير صالحة')
    reason = (reason or '').strip()
    if to == S.ESCALATED and not reason:
        raise ConversationError('سبب التصعيد مطلوب')
    old = conv.status
    if old == to:
        return conv
    conv.status = to
    conv.version += 1
    if to == S.ESCALATED:
        conv.escalation_reason = reason
    if to == S.CLOSED:
        conv.closed_at = timezone.now()
        conv.awaiting_reply_since = None
        conv.unread_count = 0
    elif old == S.CLOSED:
        conv.closed_at = None
    conv.save()
    log_action(AuditLog.Action.STATUS_CHANGE, conv, entity_type='whatsapp.Conversation', previous={'status': old},
               new={'status': to}, reason=reason, actor=user)
    if to == S.ESCALATED:
        _notify(_desk_users(RT.CS_SUPERVISOR, RT.MANAGER), 'محادثة واتساب مصعَّدة',
                f'{conv.display_name or conv.contact_number}: {reason[:80]}', conv)
    return conv


def mark_read(conv_id):
    SupplierConversation.objects.filter(pk=conv_id).exclude(unread_count=0).update(unread_count=0)


def ping_typing(conv_id, user):
    SupplierConversation.objects.filter(pk=conv_id).update(
        typing_agent=user, typing_until=timezone.now() + datetime.timedelta(seconds=TYPING_TTL))


def other_typing(conv, user):
    """اسم موظف آخر يكتب الآن، أو None."""
    if conv.typing_agent_id and conv.typing_agent_id != user.pk and conv.typing_until \
            and conv.typing_until > timezone.now():
        return conv.typing_agent.get_full_name() or conv.typing_agent.get_username()
    return None


@transaction.atomic
def link_supplier(conv_id, user, supplier):
    conv = SupplierConversation.objects.select_for_update().get(pk=conv_id)
    if not can_act(user, conv):
        raise ConversationError('ليس لديك صلاحية على هذه المحادثة')
    old = conv.supplier_id
    conv.supplier = supplier
    conv.save(update_fields=['supplier'])
    log_action(AuditLog.Action.UPDATE, conv, entity_type='whatsapp.Conversation', previous={'supplier': old},
               new={'supplier': supplier.pk if supplier else None}, reason='ربط المحادثة بمورد', actor=user)
    return conv


@transaction.atomic
def link_case(conv_id, user, case):
    conv = SupplierConversation.objects.select_for_update().get(pk=conv_id)
    if not can_act(user, conv):
        raise ConversationError('ليس لديك صلاحية على هذه المحادثة')
    old = conv.reconciliation_case_id
    conv.reconciliation_case = case
    conv.save(update_fields=['reconciliation_case'])
    log_action(AuditLog.Action.UPDATE, conv, entity_type='whatsapp.Conversation',
               previous={'reconciliation_case': old}, new={'reconciliation_case': case.pk if case else None},
               reason='ربط المحادثة بحالة مطابقة', actor=user)
    return conv


# ── الإرسال ───────────────────────────────────────────────────────────────────
def send_reply(conv_id, user, text):
    text = (text or '').strip()
    if not text:
        raise ConversationError('اكتب نص الرسالة')
    if len(text) > MAX_TEXT:
        raise ConversationError(f'الرسالة أطول من {MAX_TEXT} حرف')
    with transaction.atomic():
        conv = SupplierConversation.objects.select_for_update().get(pk=conv_id)
        if conv.status == S.CLOSED:
            raise ConversationError('المحادثة مغلقة. أعد فتحها أولًا')
        if conv.assigned_agent_id is None and is_supervisor(user):
            conv.assigned_agent = user      # المشرف الذي يرد على محادثة غير مسندة يستلمها
            conv.version += 1
            _record_assignment(conv, user, user)
        if not can_act(user, conv):
            raise ConversationError('استلم المحادثة أولًا للرد عليها')
        busy = other_typing(conv, user)
        if busy and not is_supervisor(user):
            raise ConversationError(f'{busy} يكتب ردًا على هذه المحادثة الآن')
        now = timezone.now()
        response = None
        if conv.awaiting_reply_since:
            response = max(0, int((now - conv.awaiting_reply_since).total_seconds()))
            conv.last_response_seconds = response
            conv.awaiting_reply_since = None
        msg = M.objects.create(conversation=conv, direction=M.Direction.OUT, kind=M.Kind.TEXT, body=text,
                               sent_by=user, status=M.DeliveryStatus.PENDING, response_seconds=response,
                               timestamp=now)
        if conv.status in (S.NEW, S.PENDING):
            conv.status = S.OPEN
        conv.last_message_at = now
        conv.unread_count = 0
        conv.typing_agent = None
        conv.typing_until = None
        conv.save()
        if settings.WHATSAPP_ASYNC_DISPATCH:
            transaction.on_commit(lambda: _dispatch_async(msg.pk))
        else:
            transaction.on_commit(lambda: deliver(msg.pk))
    return msg


def _dispatch_async(message_id):
    def run():
        try:
            deliver(message_id)
        finally:
            close_old_connections()
    threading.Thread(target=run, daemon=True, name=f'wa-send-{message_id}').start()


def deliver(message_id):
    """يرسل الرسالة عبر Evolution ويحدّث حالتها. آمن لإعادة الاستدعاء (لا يرسل مرتين)."""
    msg = M.objects.select_related('conversation').get(pk=message_id)
    if msg.status not in (M.DeliveryStatus.PENDING, M.DeliveryStatus.FAILED):
        return msg
    try:
        resp = client.send_text(msg.conversation.contact_number, msg.body)
    except WhatsAppError as exc:
        M.objects.filter(pk=msg.pk).update(status=M.DeliveryStatus.FAILED, error=str(exc)[:300])
        return M.objects.get(pk=msg.pk)
    wa_id = str(((resp or {}).get('key') or {}).get('id') or '')[:128] or None
    try:
        with transaction.atomic():
            M.objects.filter(pk=msg.pk).update(status=M.DeliveryStatus.SENT, wa_message_id=wa_id, error='')
    except IntegrityError:
        # وصل صدى الـ webhook قبل حفظ المعرّف فأنشأ سجلًا لنفس الرسالة: ندمج بدل التكرار
        echo = M.objects.filter(wa_message_id=wa_id).first()
        if echo:
            M.objects.filter(pk=echo.pk).update(sent_by=msg.sent_by, response_seconds=msg.response_seconds,
                                                body=msg.body or echo.body)
            msg.delete()
            return echo
    return M.objects.get(pk=msg.pk)


def resend(message_id, user):
    msg = M.objects.select_related('conversation').get(pk=message_id)
    if not can_act(user, msg.conversation):
        raise ConversationError('ليس لديك صلاحية على هذه المحادثة')
    if msg.status != M.DeliveryStatus.FAILED:
        raise ConversationError('الرسالة لم تفشل')
    return deliver(msg.pk)
