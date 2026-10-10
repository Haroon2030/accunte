"""
المساعد الآلي لواتساب: يعرض على المورد قائمة الخدمات ويُنشئ طلب الخدمة من اختياره، أو يحوّله لفريق الدعم.

الدورة (لكل محادثة، ما دامت غير مسندة لموظف ومرتبطة بمورد):
    ''  ──(أي رسالة)──▶ menu     يُعرض الترحيب وقائمة مرقّمة
    menu ──(رقم خدمة)──▶ collect  يُطلب وصف الطلب في رسالة واحدة
    menu ──(0)─────────▶ human   تحويل لفريق الدعم (تظهر في الصندوق للموظفين)
    collect ──(نص)────▶ ''      يُنشأ طلب الخدمة وتُغلق المحادثة (تُفتح من جديد برسالة لاحقة)
    collect ──(0)─────▶ human،  collect ──(#)──▶ menu
بعد human يصمت المساعد حتى تُغلق المحادثة. وأي رد من موظف يحوّل الحالة إلى human فورًا.
أثناء menu/collect تُعرض المحادثة «بانتظار العميل» ولا تزعج الموظفين بعدّادات.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import services
from .models import BOT_COLLECT as COLLECT
from .models import BOT_HUMAN as HUMAN
from .models import BOT_IDLE as IDLE
from .models import BOT_MENU as MENU
from .models import ConversationMessage as M
from .models import SupplierConversation

log = logging.getLogger(__name__)
S = SupplierConversation.Status

MAX_MENU = 9
MAX_ATTEMPTS = 3
_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def enabled():
    return bool(settings.WHATSAPP_ENABLED and settings.WHATSAPP_BOT_ENABLED)


def eligible(conv):
    """هل يتولى المساعد هذه المحادثة؟ مورد معروف، لا موظف مسؤول، ولم تُسلَّم للدعم."""
    return (enabled() and conv.supplier_id is not None and conv.assigned_agent_id is None
            and conv.bot_state != HUMAN)


def menu_types():
    from apps.servicedesk.models import ServiceType
    return list(ServiceType.objects.filter(is_active=True, whatsapp_menu=True).order_by('sort_order', 'name')[:MAX_MENU])


def menu_text(conv, types, prefix=''):
    name = conv.supplier.name if conv.supplier_id else ''
    lines = [prefix or f'أهلًا بك {name} 👋'.strip(), 'اختر الخدمة بإرسال رقمها:']
    lines += [f'{i}- {t.name}' for i, t in enumerate(types, 1)]
    lines.append('0- التحدث مع فريق الدعم')
    return '\n'.join(lines)


def _normalize(text):
    return (text or '').translate(_DIGITS).strip()


def _reply(conv, text):
    services.send_automated(conv, text)


def _park(conv, state, **extra):
    """المحادثة في عهدة المساعد: بانتظار العميل، بلا عدّادات ولا انتظار رد من الموظفين."""
    conv.bot_state = state
    conv.status = S.PENDING
    conv.unread_count = 0
    conv.awaiting_reply_since = None
    for k, v in extra.items():
        setattr(conv, k, v)


def _handoff(conv, first_message_at, text):
    conv.bot_state = HUMAN
    conv.bot_service_code = ''
    conv.bot_attempts = 0
    conv.status = S.NEW
    conv.unread_count = 1
    conv.awaiting_reply_since = first_message_at
    conv.save()
    _reply(conv, text)
    services.notify_desk_new_conversation(conv, 'طلب التحدث مع الدعم')


def handle(conv_id, msg_id):
    """يعالج رسالة واردة واحدة. يُستدعى بعد حفظها (خارج معاملة الاستقبال) ولا يرمي أخطاء للمستدعي."""
    try:
        _handle(conv_id, msg_id)
    except Exception:       # المساعد لا يجوز أن يُسقط الـ webhook
        log.exception('whatsapp bot failed for conversation %s', conv_id)


def _handle(conv_id, msg_id):
    with transaction.atomic():
        conv = SupplierConversation.objects.select_for_update().select_related('supplier').get(pk=conv_id)
        msg = M.objects.get(pk=msg_id)
        if not eligible(conv):
            return
        text = _normalize(msg.body) if msg.kind == M.Kind.TEXT else ''
        now = msg.timestamp or timezone.now()

        if conv.bot_state == IDLE:
            types = menu_types()
            if not types:
                return _handoff(conv, now, 'تم استلام رسالتك، وسيرد عليك أحد موظفي الدعم قريبًا.')
            _park(conv, MENU, bot_attempts=0, bot_service_code='')
            conv.save()
            return _reply(conv, menu_text(conv, types))

        if text == '0':
            return _handoff(conv, now, 'تم تحويلك إلى فريق الدعم، وسيرد عليك أحد الموظفين قريبًا.')

        if conv.bot_state == MENU:
            types = menu_types()
            if text.isdigit() and 1 <= int(text) <= len(types):
                chosen = types[int(text) - 1]
                _park(conv, COLLECT, bot_service_code=chosen.code, bot_attempts=0)
                conv.save()
                return _reply(conv, f'اخترت: {chosen.name}\nاكتب تفاصيل طلبك في رسالة واحدة.\n'
                                    '(أرسل # للرجوع إلى القائمة، أو 0 للتحدث مع الدعم)')
            conv.bot_attempts += 1
            if conv.bot_attempts >= MAX_ATTEMPTS:
                return _handoff(conv, now, 'تعذّر فهم اختيارك، فحوّلناك إلى فريق الدعم وسيرد عليك أحد الموظفين.')
            _park(conv, MENU)
            conv.save()
            return _reply(conv, menu_text(conv, types, 'لم أفهم اختيارك. أرسل رقم الخدمة فقط.'))

        if conv.bot_state == COLLECT:
            if text == '#':
                _park(conv, MENU, bot_service_code='', bot_attempts=0)
                conv.save()
                return _reply(conv, menu_text(conv, menu_types()))
            if msg.kind != M.Kind.TEXT or not text:
                return _handoff(conv, now, 'استلمنا مرفقك، وحوّلناك إلى فريق الدعم ليكمل معك.')
            return _create_request(conv, msg, now)


def _create_request(conv, msg, now):
    from apps.servicedesk.models import ServiceType
    from apps.servicedesk.services import RequestError, create_from_whatsapp
    stype = ServiceType.objects.filter(code=conv.bot_service_code, is_active=True).first()
    if stype is None:
        return _handoff(conv, now, 'تعذّر إنشاء الطلب، وحوّلناك إلى فريق الدعم.')
    try:
        req = create_from_whatsapp(conv, stype, msg.body)
    except RequestError:
        return _handoff(conv, now, 'تعذّر إنشاء الطلب، وحوّلناك إلى فريق الدعم.')
    conv.bot_state, conv.bot_service_code, conv.bot_attempts = IDLE, '', 0
    conv.status, conv.closed_at = S.CLOSED, timezone.now()
    conv.unread_count, conv.awaiting_reply_since = 0, None
    conv.save()
    _reply(conv, f'تم استلام طلبك ✅\nالرقم المرجعي: {req.reference}\n'
                 f'الخدمة: {stype.name}\nسنتواصل معك خلال {stype.sla_hours} ساعة.\n'
                 'للتواصل في أي وقت أرسل رسالة جديدة.')
