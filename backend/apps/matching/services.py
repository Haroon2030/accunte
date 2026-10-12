"""منطق المطابقة والشكاوى: الرؤية والصلاحيات وانتقال المراحل وبناء JSON كما تتوقعه الواجهة."""
import datetime
import os

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.api import ApiError
from apps.accounts.models import UserProfile

from .models import SLA_DAYS, Attachment, Complaint, MatchRequest, Message

Role = UserProfile.Role
Sender = Message.Sender

ADVANCE_NOTE = {1: 'بدأت المطابقة على كشف الحساب', 2: 'فُتحت قناة المراسلة مع المورد', 3: 'أُغلقت المراسلة وأُنجز الطلب'}
C_ADVANCE_NOTE = {1: 'بدأ المدير المالي مراجعة الشكوى', 2: 'أُغلقت الشكوى بعد رد المدير المالي'}
CATEGORIES = ['دفعة غير مستلمة', 'فرق في الرصيد لم يُحسم', 'تأخر في السداد', 'تأخر الرد على الطلبات', 'تعامل موظف', 'أخرى']
STATEMENT_EXT = {'pdf', 'xlsx', 'xls', 'csv'}
ATTACH_EXT = STATEMENT_EXT | {'png', 'jpg', 'jpeg', 'doc', 'docx', 'txt'}

# من يستطيع الكتابة بأي صفة (المدير يرى المطابقة بصفة مراقب أو مطابق)
SENDER_ROLES = {
    Role.SUPPLIER: {Sender.SUPPLIER}, Role.MATCHER: {Sender.MATCHER},
    Role.MANAGER: {Sender.MANAGER, Sender.MATCHER}, Role.ADMIN: {Sender.MANAGER, Sender.MATCHER},
}


# ───────── الرؤية ─────────
def visible_requests(user):
    qs = MatchRequest.objects.all()
    p = user.profile
    if p.role == Role.SUPPLIER:
        return qs.filter(supplier_org=p.org)
    if p.role == Role.MATCHER:
        return qs.filter(Q(matcher__isnull=True) | Q(matcher=user))
    return qs


def visible_complaints(user):
    qs = Complaint.objects.all()
    p = user.profile
    if p.role == Role.SUPPLIER:
        return qs.filter(supplier_org=p.org)
    if p.role in (Role.MANAGER, Role.ADMIN):
        return qs
    return qs.none()


def get_request(user, code):
    obj = visible_requests(user).filter(code=code).first()
    if obj is None:
        raise ApiError('الطلب غير موجود.', 404)
    return obj


def get_complaint(user, code):
    obj = visible_complaints(user).filter(code=code).first()
    if obj is None:
        raise ApiError('الشكوى غير موجودة.', 404)
    return obj


# ───────── الملفات ─────────
def _ext(name):
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


def validate_files(files, allowed, *, required=False):
    files = list(files)
    if required and not files:
        raise ApiError('أرفق الملف المطلوب.')
    if len(files) > settings.MAX_FILES_PER_MESSAGE:
        raise ApiError(f'الحد الأقصى {settings.MAX_FILES_PER_MESSAGE} ملفات في المرة الواحدة.')
    for f in files:
        if _ext(f.name) not in allowed:
            raise ApiError(f'نوع الملف «{os.path.basename(f.name)[:60]}» غير مسموح.')
        if f.size > settings.MAX_UPLOAD_BYTES:
            raise ApiError(f'حجم الملف «{os.path.basename(f.name)[:60]}» يتجاوز {settings.MAX_UPLOAD_BYTES // 1048576} MB.')
    return files


def store_attachment(f, user, **owner):
    return Attachment.objects.create(file=f, name=os.path.basename(f.name)[:255], size=f.size, uploaded_by=user, **owner)


# ───────── الإنشاء ─────────
@transaction.atomic
def create_request(user, period, notes, statement):
    period = (period or '').strip()
    if not period or len(period) > 100:
        raise ApiError('اختر الفترة المطلوب مطابقتها.')
    notes = (notes or '').strip()
    if len(notes) > 2000:
        raise ApiError('الملاحظات طويلة (الحد 2000 حرف).')
    [statement] = validate_files([statement] if statement else [], STATEMENT_EXT, required=True)
    now = timezone.now()
    req = MatchRequest.objects.create(
        supplier_org=user.profile.org, created_by=user, period=period, notes=notes, stage=1,
        reached=[now.isoformat(), now.isoformat(), None, None, None], due_at=now + datetime.timedelta(days=SLA_DAYS))
    store_attachment(statement, user, statement_of=req)
    return req


@transaction.atomic
def create_complaint(user, category, subject, body, related_code, files):
    category = (category or '').strip()
    subject, body = (subject or '').strip(), (body or '').strip()
    if category not in CATEGORIES:
        raise ApiError('اختر نوع الشكوى.')
    if not subject or not body:
        raise ApiError('اكتب عنوان الشكوى وتفاصيلها قبل الإرسال.')
    if len(subject) > 200 or len(body) > 4000:
        raise ApiError('العنوان أو التفاصيل أطول من المسموح.')
    related = None
    if related_code:
        related = MatchRequest.objects.filter(code=related_code, supplier_org=user.profile.org).first()
        if related is None:
            raise ApiError('طلب المطابقة المرتبط غير صحيح.')
    files = validate_files(files, ATTACH_EXT)
    now = timezone.now()
    c = Complaint.objects.create(supplier_org=user.profile.org, created_by=user, category=category, subject=subject,
                                 related=related, stage=1, reached=[now.isoformat(), now.isoformat(), None, None, None])
    msg = Message.objects.create(complaint=c, sender_role=Sender.SUPPLIER, sender=user, text=body)
    for f in files:
        store_attachment(f, user, message=msg)
    return c


# ───────── انتقال المراحل ─────────
@transaction.atomic
def advance_request(user, code):
    req = MatchRequest.objects.select_for_update().filter(pk=get_request(user, code).pk).first()
    role = user.profile.role
    if role not in (Role.MATCHER, Role.MANAGER, Role.ADMIN):
        raise ApiError('المطابق أو المدير فقط يحرّك الطلب.', 403)
    if req.matcher_id and req.matcher_id != user.pk and role == Role.MATCHER:
        raise ApiError('هذا الطلب عند مطابق آخر.', 403)
    if req.stage >= 4:
        raise ApiError('الطلب منجز.')
    nxt = req.stage + 1
    reached = list(req.reached)
    reached[nxt] = timezone.now().isoformat()
    req.stage, req.reached = nxt, reached
    if req.matcher_id is None:
        req.matcher = user
    req.save()
    Message.objects.create(request=req, sender_role=Sender.SYSTEM, text=ADVANCE_NOTE[nxt - 1])
    return req


@transaction.atomic
def advance_complaint(user, code):
    if user.profile.role not in (Role.MANAGER, Role.ADMIN):
        raise ApiError('المدير المالي فقط يحرّك الشكوى.', 403)
    c = Complaint.objects.select_for_update().filter(pk=get_complaint(user, code).pk).first()
    if c.stage >= 3:
        raise ApiError('الشكوى مغلقة.')
    nxt = c.stage + 1
    reached = list(c.reached)
    reached[nxt] = timezone.now().isoformat()
    c.stage, c.reached = nxt, reached
    c.save()
    Message.objects.create(complaint=c, sender_role=Sender.SYSTEM, text=C_ADVANCE_NOTE[nxt - 1])
    return c


# ───────── المراسلات ─────────
def _sender_for(user, requested, allowed_default):
    allowed = SENDER_ROLES[user.profile.role]
    chosen = requested if requested in {s.value for s in allowed} else allowed_default
    if chosen not in {s.value for s in allowed}:
        raise ApiError('لا يمكنك الكتابة بهذه الصفة.', 403)
    return chosen


@transaction.atomic
def post_request_message(user, code, text, requested_from, files):
    req = get_request(user, code)
    if req.stage != 3:
        raise ApiError('المراسلة مفتوحة فقط أثناء مرحلة الاستيضاح.')
    role = user.profile.role
    sender = _sender_for(user, requested_from, {Role.SUPPLIER: 'supplier', Role.MATCHER: 'matcher'}.get(role, 'manager'))
    if sender == Sender.MATCHER and role == Role.MATCHER and req.matcher_id not in (None, user.pk):
        raise ApiError('هذا الطلب عند مطابق آخر.', 403)
    return _save_message(user, files, text, sender, request=req)


@transaction.atomic
def post_complaint_message(user, code, text, requested_from, files):
    c = get_complaint(user, code)
    if c.stage >= 3:
        raise ApiError('أُغلقت الشكوى.')
    role = user.profile.role
    sender = _sender_for(user, requested_from, 'supplier' if role == Role.SUPPLIER else 'manager')
    if sender == Sender.MATCHER:
        raise ApiError('المطابقون لا يطّلعون على الشكاوى.', 403)
    return _save_message(user, files, text, sender, complaint=c)


def _save_message(user, files, text, sender, **owner):
    text = (text or '').strip()
    files = validate_files(files, ATTACH_EXT)
    if not text and not files:
        raise ApiError('اكتب رسالة أو أرفق مستنداً.')
    if len(text) > 4000:
        raise ApiError('الرسالة أطول من المسموح (4000 حرف).')
    msg = Message.objects.create(sender_role=sender, sender=user, text=text, **owner)
    for f in files:
        store_attachment(f, user, message=msg)
    return msg


# ───────── التسلسل إلى JSON (شكل الواجهة) ─────────
def _iso(dt):
    return dt.isoformat() if dt else None


def _file(a):
    return {'id': a.pk, 'name': a.name, 'size': a.size}


def _message(m):
    return {'id': m.pk, 'from': m.sender_role, 'text': m.text, 'at': _iso(m.created_at),
            'files': [_file(a) for a in m.attachments.all()]}


def _person(user):
    return (user.first_name or user.get_username()) if user else None


def serialize_request(r):
    st = getattr(r, 'statement', None)
    return {
        'id': r.code, 'supplier': r.supplier_org, 'period': r.period, 'stage': r.stage, 'created': _iso(r.created_at),
        'due': _iso(r.due_at), 'reached': r.reached, 'matcher': _person(r.matcher),
        'diff': float(r.diff) if r.diff is not None else None, 'notes': r.notes,
        'statement': _file(st) if st else {'id': None, 'name': '—', 'size': 0},
        'messages': [_message(m) for m in r.messages.all()],
    }


def serialize_complaint(c):
    return {
        'id': c.code, 'supplier': c.supplier_org, 'category': c.category, 'subject': c.subject,
        'related': c.related.code if c.related_id else None, 'stage': c.stage, 'created': _iso(c.created_at),
        'reached': c.reached, 'messages': [_message(m) for m in c.messages.all()],
    }


def requests_payload(user):
    qs = (visible_requests(user).select_related('matcher', 'statement')
          .prefetch_related('messages__attachments'))
    return [serialize_request(r) for r in qs]


def complaints_payload(user):
    qs = visible_complaints(user).select_related('related').prefetch_related('messages__attachments')
    return [serialize_complaint(c) for c in qs]


def attachment_visible_to(user, att):
    """هل يحق للمستخدم تنزيل هذا المرفق؟ بحسب رؤية الطلب أو الشكوى التابع لهما."""
    if att.statement_of_id:
        return visible_requests(user).filter(pk=att.statement_of_id).exists()
    msg = att.message
    if msg.request_id:
        return visible_requests(user).filter(pk=msg.request_id).exists()
    return visible_complaints(user).filter(pk=msg.complaint_id).exists()
