"""
منطق طلبات الخدمة: التحقق من الحقول الديناميكية، الإنشاء، الاستلام، آلة الحالات، التصعيد التلقائي، الرؤية.
"""
import datetime
import re
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.core.dates import safe_parse_date as parse_date

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.core.access import get_role_type, has_role
from apps.core.models import Notification, Role
from apps.reconciliation.services import file_sha256, validate_upload
from apps.reconciliation.workflow import TransitionError

from .models import RequestStatusHistory, ServiceRequest, ServiceType

S = ServiceRequest.Status
RT = Role.RoleType
SUPERVISOR_ROLES = (RT.ADMIN, RT.CS_SUPERVISOR, RT.CFO)
OVERSIGHT_ROLES = SUPERVISOR_ROLES
VIEW_ROLES = OVERSIGHT_ROLES + (RT.ACCOUNTANT,)
MANAGE_TYPES_ROLES = (RT.ADMIN, RT.CFO)

# يوزّع الطلبات المشرفون (SUPERVISOR_ROLES) ويستقبلها المطابقون (المحاسبون) فقط، بغض النظر عن نوع الطلب.
# (لا ربط دائم بين المورد والمحاسب: المشرف يوزّع كل طلب وقت وصوله.)
ASSIGNABLE_ROLES = (RT.ACCOUNTANT,)

FIELD_TYPES = ('text', 'textarea', 'number', 'date', 'select')
KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')


class RequestError(Exception):
    """رسالة عربية جاهزة للعرض."""


# ── الحقول الديناميكية ─────────────────────────────────────────────────────────
def validate_schema(schema):
    """يتحقق من تعريف الحقول الذي يضعه المدير. يُرجع قائمة منقّاة أو يرفع RequestError."""
    if not isinstance(schema, list):
        raise RequestError('تعريف الحقول غير صالح')
    out, seen = [], set()
    for f in schema:
        if not isinstance(f, dict):
            raise RequestError('تعريف الحقول غير صالح')
        key, label, ftype = str(f.get('key', '')).strip(), str(f.get('label', '')).strip(), f.get('type', 'text')
        if not KEY_RE.match(key):
            raise RequestError(f'مفتاح الحقل "{key}" غير صالح (حروف إنجليزية صغيرة وأرقام و _ ويبدأ بحرف)')
        if key in seen:
            raise RequestError(f'مفتاح الحقل "{key}" مكرر')
        if not label:
            raise RequestError(f'عنوان الحقل "{key}" مطلوب')
        if ftype not in FIELD_TYPES:
            raise RequestError(f'نوع الحقل "{key}" غير مدعوم')
        options = [str(o).strip() for o in (f.get('options') or []) if str(o).strip()]
        if ftype == 'select' and not options:
            raise RequestError(f'الحقل "{label}" من نوع قائمة ويحتاج خيارات')
        seen.add(key)
        out.append({'key': key, 'label': label[:100], 'type': ftype, 'required': bool(f.get('required')),
                    'options': options if ftype == 'select' else []})
    return out


def validate_fields(schema, getter):
    """getter(key) يُرجع القيمة الخام. يُرجع (cleaned, errors)."""
    cleaned, errors = {}, []
    for f in schema or []:
        raw = (getter(f'f_{f["key"]}') or '').strip()
        if not raw:
            if f.get('required'):
                errors.append(f'الحقل "{f["label"]}" مطلوب')
            continue
        t = f.get('type')
        if t == 'number':
            try:
                d = Decimal(raw.replace(',', ''))
                if not d.is_finite():
                    raise InvalidOperation
                cleaned[f['key']] = str(d)
            except InvalidOperation:
                errors.append(f'الحقل "{f["label"]}" يجب أن يكون رقمًا')
        elif t == 'date':
            d = parse_date(raw)
            if d is None:
                errors.append(f'الحقل "{f["label"]}" تاريخ غير صالح')
            else:
                cleaned[f['key']] = d.isoformat()
        elif t == 'select':
            if raw not in f.get('options', []):
                errors.append(f'قيمة الحقل "{f["label"]}" غير مسموحة')
            else:
                cleaned[f['key']] = raw
        else:
            cleaned[f['key']] = raw[:2000]
    if cleaned.get('period_start') and cleaned.get('period_end') and cleaned['period_start'] > cleaned['period_end']:
        errors.append('تاريخ البداية بعد تاريخ النهاية')
    return cleaned, errors


def labelled_data(req):
    """بيانات الطلب كأزواج (عنوان، قيمة) حسب تعريف النوع الحالي."""
    schema = {f['key']: f for f in (req.service_type.field_schema or [])}
    return [(schema.get(k, {}).get('label', k), v) for k, v in (req.data or {}).items()]


# ── الصلاحيات والرؤية ─────────────────────────────────────────────────────────
def can_create(user, stype):
    return stype.is_active and has_role(user, *stype.effective_create_roles())


def can_handle(user, stype):
    return has_role(user, *stype.effective_handle_roles())


def is_supervisor(user):
    return has_role(user, *SUPERVISOR_ROLES)


def can_see_confidential(user):
    """الشكاوى وما شابهها: المدير المالي ومدير النظام فقط."""
    return has_role(user, RT.CFO)


def can_receive_assignment(user):
    """هل يصلح هذا المستخدم لإسناد طلب إليه؟ (فعّال وبدور مطابق/محاسب)."""
    return user.is_active and not user.is_superuser and get_role_type(user) in ASSIGNABLE_ROLES


def assignable_users():
    """كل من يصلح لاستقبال الإسناد، مرتبًا بالاسم. يطابق can_receive_assignment."""
    return list(get_user_model().objects.filter(
        profile__role__role_type__in=ASSIGNABLE_ROLES, profile__role__is_active=True, is_active=True,
        is_superuser=False).order_by('username'))


def visible_requests(user):
    qs = ServiceRequest.objects.select_related('service_type', 'supplier', 'assigned_to', 'created_by')
    if not can_see_confidential(user):
        qs = qs.exclude(service_type__confidential=True)
    if has_role(user, *OVERSIGHT_ROLES):
        return qs
    role = get_role_type(user)
    if role in ASSIGNABLE_ROLES:                       # المطابق يرى مهامه فقط، لا طابورًا عامًا
        return qs.filter(Q(created_by=user) | Q(assigned_to=user))
    handled = [t.pk for t in ServiceType.objects.all() if role in t.effective_handle_roles()]
    return qs.filter(Q(created_by=user) | Q(assigned_to=user)
                     | Q(assigned_to__isnull=True, service_type_id__in=handled, status__in=ServiceRequest.OPEN))


def can_edit_documents(user, req):
    return not req.is_terminal and (req.created_by_id == user.pk or req.assigned_to_id == user.pk
                                    or is_supervisor(user))


# ── الإنشاء ───────────────────────────────────────────────────────────────────
def _users_with_role(*roles):
    return list(get_user_model().objects.filter(is_active=True, profile__role__role_type__in=roles))


def _intake_users(stype):
    """من يُشعَر بطلب جديد غير مسند: الجهة المستلمة، إلا إن كانت دور مطابقين فيصل المشرفين ليوزّعوه."""
    if stype.confidential:                              # المدير المالي ومدير النظام (بما فيهم الحساب الأعلى)
        return list(get_user_model().objects.filter(
            Q(profile__role__role_type__in=(RT.CFO, RT.ADMIN)) | Q(is_superuser=True), is_active=True).distinct())
    if stype.destination_role in ASSIGNABLE_ROLES:
        return _users_with_role(RT.CS_SUPERVISOR)
    return _users_with_role(stype.destination_role)


def _notify(users, title, message, req):
    seen, rows = set(), []
    for u in users:
        if u is None or u.pk in seen or not u.is_active:
            continue
        seen.add(u.pk)
        rows.append(Notification(recipient=u, category=Notification.Category.SYSTEM, title=title, message=message,
                                 link=f'/service-requests/{req.pk}/'))
    if rows:
        Notification.objects.bulk_create(rows)


@transaction.atomic
def create_request(user, stype, supplier, subject, details='', priority='normal', getter=None, conversation=None,
                   assign_to=None):
    """assign_to: إسناد مباشر عند الإنشاء (للمشرفين فقط)، فلا يُنتظر توزيع لاحق."""
    if not can_create(user, stype):
        raise RequestError('ليس لديك صلاحية إنشاء هذا النوع من الطلبات')
    if assign_to is not None:
        if not is_supervisor(user):
            raise RequestError('الإسناد المباشر للمشرفين فقط')
        if not can_receive_assignment(assign_to):
            raise RequestError('هذا المستخدم لا يستقبل الطلبات')
    subject = (subject or '').strip()
    if not subject:
        raise RequestError('الموضوع مطلوب')
    if priority not in ServiceRequest.Priority.values:
        raise RequestError('أولوية غير صالحة')
    data, errors = validate_fields(stype.field_schema, getter or (lambda k: ''))
    if errors:
        raise RequestError(' · '.join(errors))
    now = timezone.now()
    req = ServiceRequest.objects.create(
        service_type=stype, supplier=supplier, conversation=conversation, subject=subject[:200],
        details=(details or '').strip(), data=data, priority=priority, created_by=user,
        due_at=now + datetime.timedelta(hours=stype.sla_hours))
    RequestStatusHistory.objects.create(request=req, to_status=S.NEW, changed_by=user, reason='إنشاء الطلب')
    log_action(AuditLog.Action.CREATE, req, entity_type='servicedesk.ServiceRequest',
               new={'type': stype.code, 'supplier': supplier.pk, 'priority': priority, 'due_at': req.due_at}, actor=user)
    if assign_to is not None:
        _set_assignee(req, assign_to, user, 'إسناد عند الإنشاء')      # يُشعَر المسنَد إليه وحده بدل كل الجهة
    else:
        _notify(_intake_users(stype), 'طلب خدمة جديد', f'{req.reference} · {stype.name} · {supplier.name}', req)
    return req


@transaction.atomic
def create_from_whatsapp(conversation, stype, details, subject=''):
    """طلب ينشئه المساعد الآلي بعد أن يختار المورد الخدمة من قائمة واتساب أو دردشة البوابة.

    لا يتحقق من الحقول الإلزامية للنوع (لا يمكن جمعها في دردشة): نص المورد يُحفظ في «التفاصيل»
    والموظف المستلم يكمل الباقي. المورد مطلوب، فالمحادثة غير المربوطة بمورد لا تصل إلى هنا.
    """
    supplier = conversation.supplier
    if supplier is None:
        raise RequestError('المحادثة غير مرتبطة بمورد')
    now = timezone.now()
    in_portal = conversation.channel == 'portal'
    source = ServiceRequest.Source.PORTAL if in_portal else ServiceRequest.Source.WHATSAPP
    where = 'دردشة البوابة' if in_portal else 'واتساب'
    req = ServiceRequest.objects.create(
        service_type=stype, supplier=supplier, conversation=conversation, subject=(subject or f'{stype.name} (عبر {where})')[:200],
        details=(details or '').strip()[:4000], priority=ServiceRequest.Priority.NORMAL, source=source,
        due_at=now + datetime.timedelta(hours=stype.sla_hours))
    RequestStatusHistory.objects.create(request=req, to_status=S.NEW, reason=f'إنشاء آلي من {where}')
    log_action(AuditLog.Action.CREATE, req, entity_type='servicedesk.ServiceRequest',
               new={'type': stype.code, 'supplier': supplier.pk, 'source': source.value, 'conversation': conversation.pk},
               reason=f'طلب آلي من قائمة {where}')
    _notify(_intake_users(stype), f'طلب خدمة جديد من {where}',
            f'{req.reference} · {stype.name} · {supplier.name}', req)
    return req


MAX_PORTAL_FILES = 5


def _validated_files(files):
    files = [f for f in (files or []) if f]
    if len(files) > MAX_PORTAL_FILES:
        raise RequestError(f'الحد الأقصى {MAX_PORTAL_FILES} ملفات للطلب الواحد')
    try:
        for f in files:
            validate_upload(f)
    except TransitionError as exc:
        raise RequestError(str(exc))
    return files


def attach_files(req, files, user, label='', shared=False):
    """يحفظ الملفات (بعد التحقق منها) كمستندات للطلب مع بصمة SHA-256 وسجل تدقيق لكل ملف."""
    from .models import ServiceRequestDocument
    for f in files:
        doc = ServiceRequestDocument(request=req, label=label[:120], original_name=f.name[:255], size=f.size,
                                     uploaded_by=user, sha256=file_sha256(f), shared_with_supplier=shared)
        doc.file.save(f.name, f, save=True)
        log_action(AuditLog.Action.CREATE, doc, entity_type='servicedesk.Document',
                   entity_repr=f'{req.reference}: {doc.original_name}',
                   new={'label': label, 'name': doc.original_name, 'sha256': doc.sha256, 'shared': shared}, actor=user)


@transaction.atomic
def create_from_portal(user, stype, subject, details='', getter=None, files=None):
    """طلب يقدّمه المورد بنفسه من بوابة الموردين: المورد هو صاحب الحساب، والحقول تُتحقَّق كما في الطلب العادي.
    المرفقات (حتى 5) تُتحقَّق كلها قبل إنشاء الطلب، فلا يُنشأ طلب بملف مرفوض."""
    supplier = getattr(getattr(user, 'profile', None), 'supplier', None)
    if supplier is None:
        raise RequestError('حسابك غير مرتبط بمورد. تواصل مع الإدارة')
    if not (stype.is_active and stype.portal_menu):
        raise RequestError('هذه الخدمة غير متاحة في البوابة')
    subject = (subject or '').strip() or stype.name
    data, errors = validate_fields(stype.field_schema, getter or (lambda k: ''))
    if errors:
        raise RequestError(' · '.join(errors))
    files = _validated_files(files)
    now = timezone.now()
    req = ServiceRequest.objects.create(
        service_type=stype, supplier=supplier, subject=subject[:200], details=(details or '').strip()[:4000], data=data,
        priority=ServiceRequest.Priority.NORMAL, created_by=user, source=ServiceRequest.Source.PORTAL,
        due_at=now + datetime.timedelta(hours=stype.sla_hours))
    RequestStatusHistory.objects.create(request=req, to_status=S.NEW, changed_by=user, reason='طلب من بوابة الموردين')
    log_action(AuditLog.Action.CREATE, req, entity_type='servicedesk.ServiceRequest',
               new={'type': stype.code, 'supplier': supplier.pk, 'source': 'portal'}, actor=user)
    attach_files(req, files, user, label='مرفق المورد', shared=True)
    _notify(_intake_users(stype), 'طلب خدمة جديد من بوابة الموردين', f'{req.reference} · {stype.name} · {supplier.name}', req)
    return req


# ── الاستلام والإسناد ─────────────────────────────────────────────────────────
@transaction.atomic
def claim(req_id, user):
    req = ServiceRequest.objects.select_related('service_type').get(pk=req_id)
    if get_role_type(user) in ASSIGNABLE_ROLES:
        raise RequestError('تُسند الطلبات إليك من المشرف ولا تُستلم ذاتيًا')
    if not can_handle(user, req.service_type):
        raise RequestError('هذا الطلب ليس من اختصاصك')
    rows = (ServiceRequest.objects.filter(pk=req_id, assigned_to__isnull=True, status__in=ServiceRequest.OPEN)
            .update(assigned_to=user))
    if rows == 0:
        raise RequestError('استلمه موظف آخر أو لم يعد متاحًا')
    log_action(AuditLog.Action.UPDATE, req, entity_type='servicedesk.ServiceRequest',
               previous={'assigned_to': None}, new={'assigned_to': user.pk}, reason='استلام الطلب', actor=user)
    return ServiceRequest.objects.get(pk=req_id)


@transaction.atomic
def assign(req_id, agent, by):
    if not is_supervisor(by):
        raise RequestError('الإسناد للمشرفين فقط')
    req = ServiceRequest.objects.select_for_update().select_related('service_type').get(pk=req_id)
    if req.service_type.confidential and not can_see_confidential(by):
        raise RequestError('هذا الطلب سرّي ولا يُسند')
    if req.is_terminal:
        raise RequestError('الطلب منتهٍ')
    if not can_receive_assignment(agent):
        raise RequestError('هذا المستخدم لا يستقبل الطلبات (اختر محاسبًا أو موظف خدمة عملاء)')
    _set_assignee(req, agent, by, 'إسناد الطلب')
    return req


def _set_assignee(req, agent, by, reason):
    """يكتب الإسناد ويسجّله ويُشعر المسنَد إليه. نقطة واحدة يشترك فيها الإنشاء والإسناد اللاحق."""
    old = req.assigned_to_id
    req.assigned_to = agent
    req.save(update_fields=['assigned_to', 'updated_at'])
    log_action(AuditLog.Action.UPDATE, req, entity_type='servicedesk.ServiceRequest', previous={'assigned_to': old},
               new={'assigned_to': agent.pk}, reason=reason, actor=by)
    _notify([agent], 'مهمة جديدة: يرجى المطابقة',
            f'يرجى مطابقة «{req.service_type.name}» مع الكشف للمورد {req.supplier.name} ({req.reference})', req)


# ── آلة الحالات ───────────────────────────────────────────────────────────────
TRANSITIONS = {
    S.NEW: {S.IN_PROGRESS: 'handler', S.CANCELLED: 'owner'},
    S.IN_PROGRESS: {S.WAITING_VENDOR: 'assignee', S.RESOLVED: 'assignee', S.ESCALATED: 'assignee', S.CANCELLED: 'owner'},
    S.WAITING_VENDOR: {S.IN_PROGRESS: 'assignee', S.RESOLVED: 'assignee', S.CANCELLED: 'owner'},
    S.ESCALATED: {S.IN_PROGRESS: 'assignee', S.RESOLVED: 'assignee', S.CANCELLED: 'owner'},
    S.RESOLVED: {S.CLOSED: 'owner', S.IN_PROGRESS: 'owner'},
    S.CLOSED: {}, S.CANCELLED: {},
}
REASON_REQUIRED = {S.CANCELLED, S.ESCALATED}


def _can_work_unassigned(user, req):
    """الطلب غير المسند يعالجه المختصون والمشرفون؛ أما المطابق فلا يعمل إلا على ما أُسند إليه."""
    if get_role_type(user) in ASSIGNABLE_ROLES:
        return False
    return can_handle(user, req.service_type) or is_supervisor(user)


def _allowed(kind, user, req):
    if req.service_type.confidential and not can_see_confidential(user):
        return False                                   # السرّي لا يتعامل معه غير المدير المالي ومدير النظام
    if kind == 'handler':
        return req.assigned_to_id == user.pk or _can_work_unassigned(user, req)
    if kind == 'assignee':
        if req.assigned_to_id is None:          # طلب غير مسند (مثلًا صُعِّد تلقائيًا): يعالجه المختصون
            return _can_work_unassigned(user, req)
        return req.assigned_to_id == user.pk or is_supervisor(user)
    if kind == 'owner':
        return req.created_by_id == user.pk or is_supervisor(user)
    return False


def allowed_transitions(user, req):
    return [to for to, kind in TRANSITIONS.get(req.status, {}).items() if _allowed(kind, user, req)]


def missing_documents(req):
    have = {d.label for d in req.documents.all()}
    return [lbl for lbl in (req.service_type.required_documents or []) if lbl not in have]


@transaction.atomic
def transition(req_id, to_status, user, reason='', resolution_note=''):
    req = ServiceRequest.objects.select_for_update().select_related('service_type', 'supplier').get(pk=req_id)
    if to_status not in S.values:
        raise RequestError('حالة غير معروفة')
    to = S(to_status)
    kind = TRANSITIONS.get(req.status, {}).get(to)
    if kind is None:
        raise RequestError(f'لا يمكن الانتقال من "{req.get_status_display()}" إلى "{to.label}"')
    if not _allowed(kind, user, req):
        raise RequestError('ليس لديك صلاحية تنفيذ هذا الإجراء')
    reason = (reason or '').strip()
    reopening = req.status == S.RESOLVED and to == S.IN_PROGRESS
    if (to in REASON_REQUIRED or reopening) and not reason:
        raise RequestError('السبب مطلوب لهذا الإجراء')
    if to == S.RESOLVED:
        if not (resolution_note or '').strip():
            raise RequestError('اكتب ملاحظة الحل')
        miss = missing_documents(req)
        if miss:
            raise RequestError('مستندات إلزامية ناقصة: ' + '، '.join(miss))
        if (req.source == ServiceRequest.Source.PORTAL and req.service_type.required_documents
                and not req.documents.filter(shared_with_supplier=True).exclude(uploaded_by_id=req.created_by_id).exists()):
            raise RequestError('شارك المستند المطلوب مع المورد قبل إغلاق الطلب (خانة «مشاركة مع المورد»)')

    old = req.status
    now = timezone.now()
    if kind in ('handler', 'assignee') and req.assigned_to_id is None and can_handle(user, req.service_type):
        req.assigned_to = user                  # من يعالج طلبًا غير مسند يستلمه
    if to == S.IN_PROGRESS and old in (S.ESCALATED, S.RESOLVED):
        req.due_at = now + datetime.timedelta(hours=req.service_type.sla_hours)   # مهلة جديدة بعد التصعيد/إعادة الفتح
    if to == S.ESCALATED:
        req.escalated_at = now
        req.escalation_count += 1
    if to == S.RESOLVED:
        req.resolved_at = now
        req.resolution_note = resolution_note.strip()
    if reopening:
        req.resolved_at = None
    req.status = to
    req.save()
    RequestStatusHistory.objects.create(request=req, from_status=old, to_status=to, changed_by=user, reason=reason)
    log_action(AuditLog.Action.STATUS_CHANGE, req, entity_type='servicedesk.ServiceRequest', previous={'status': old},
               new={'status': to.value}, reason=reason, actor=user)
    if to == S.ESCALATED:
        _notify(_users_with_role(req.service_type.escalation_role), 'طلب خدمة مصعَّد',
                f'{req.reference} · {reason[:80]}', req)
    elif to == S.RESOLVED:
        _notify([req.created_by], 'تم حل طلب الخدمة', f'{req.reference} · {req.supplier.name}', req)
    return req


# ── التصعيد التلقائي ──────────────────────────────────────────────────────────
def escalate_overdue(now=None):
    """يُصعِّد الطلبات المتأخرة عن مهلتها. آمن للتكرار: الطلب المصعَّد لا يُصعَّد ثانية حتى يُعاد للمعالجة."""
    now = now or timezone.now()
    ids = list(ServiceRequest.objects.filter(
        status__in=(S.NEW, S.IN_PROGRESS, S.WAITING_VENDOR), due_at__lt=now).values_list('pk', flat=True))
    done = 0
    for pk in ids:
        with transaction.atomic():
            req = ServiceRequest.objects.select_for_update().select_related('service_type', 'supplier').get(pk=pk)
            if req.status not in (S.NEW, S.IN_PROGRESS, S.WAITING_VENDOR) or not req.due_at or req.due_at >= now:
                continue
            old = req.status
            req.status = S.ESCALATED
            req.escalated_at = now
            req.escalation_count += 1
            req.save()
            reason = 'تجاوز مهلة الإنجاز'
            RequestStatusHistory.objects.create(request=req, from_status=old, to_status=S.ESCALATED, reason=reason)
            log_action(AuditLog.Action.STATUS_CHANGE, req, entity_type='servicedesk.ServiceRequest',
                       previous={'status': old}, new={'status': S.ESCALATED.value}, reason=reason,
                       actor=None, request=None)
            _notify(_users_with_role(req.service_type.escalation_role) + [req.assigned_to],
                    'تصعيد تلقائي لطلب خدمة', f'{req.reference} · {req.supplier.name} · تجاوز المهلة', req)
            done += 1
    return done
