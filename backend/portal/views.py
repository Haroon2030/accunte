import re
import secrets
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import FileResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SLA_DAYS, Attachment, Complaint, Message, MatchRequest, Notice, Supplier, User
from .permissions import (supplier_or_page, IsAdmin, IsManagerPage, IsMatcherPage, IsStaff, IsSupplier, IsSuppliersPage, CanReadSuppliers, STAFF_PAGES, SupplierOrManagerPage, IsNoticesPage, SupplierOrNotices, allowed_pages,
                          can_view_complaint, can_view_request, roles)
from .serializers import complaint_out, message_out, notice_out, request_out, supplier_out, user_out
from .validators import INLINE_TYPES, TAX_RE, MOBILE_RE, check_password_rule, extension_of, normalize_digits, normalize_mobile, validate_upload

USERNAME_RE = re.compile(r'^[a-z0-9._-]{1,30}$')
REQ_NOTE = {1: 'بدأت المطابقة على كشف الحساب', 2: 'فُتحت قناة المراسلة مع المورد', 3: 'أُغلقت المراسلة وأُنجز الطلب'}
COMPLAINT_NOTE = {1: 'بدأ المدير المالي مراجعة الشكوى', 2: 'أُغلقت الشكوى بعد رد المدير المالي'}


def norm_username(v):
    return normalize_digits(v).strip().lower()


def temp_password():
    sets = ['abcdefghjkmnpqrstuvwxyz', 'ABCDEFGHJKMNPQRSTUVWXYZ', '23456789', '@#$%']
    out = [secrets.choice(s) for s in sets]
    out += [secrets.choice(''.join(sets)) for _ in range(7)]
    secrets.SystemRandom().shuffle(out)
    return ''.join(out)


def revoke_sessions(user):
    for s in Session.objects.filter(expire_date__gte=timezone.now()):
        if s.get_decoded().get('_auth_user_id') == str(user.pk):
            s.delete()


def save_files(files, uploader, **parent):
    saved = []
    for f in files:
        validate_upload(f)
        saved.append(Attachment.objects.create(
            file=f, original_name=f.name[:255], size=f.size, uploaded_by=uploader, **parent))
    return saved


# ------------------------------------------------------------------ auth
@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(APIView):
    """Who is signed in. It must read the session: without it every page reload looked signed out."""
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        u = request.user if request.user.is_authenticated else None
        return Response({'user': user_out(u) if u else None})


@method_decorator(ratelimit(key='ip', rate='30/m', block=True), name='post')
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        name = norm_username(request.data.get('username'))
        pw = request.data.get('password') or ''
        if not name or not pw:
            raise ValidationError({'detail': 'أدخل رقم المستخدم وكلمة المرور.'})
        bad = ValidationError({'detail': 'رقم المستخدم أو كلمة المرور غير صحيحة.'})
        user = User.objects.filter(username=name).first()
        if not user or not user.check_password(pw):
            raise bad
        if not user.is_active:
            raise ValidationError({'detail': 'هذا الحساب موقوف. تواصل مع مدير النظام لتفعيله.'})
        login(request, authenticate(request, username=name, password=pw))
        return Response({'user': user_out(user)})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({'ok': True})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        pw = request.data.get('password') or ''
        check_password_rule(pw)
        if request.user.check_password(pw):
            raise ValidationError({'detail': 'اختر كلمة مرور مختلفة عن الحالية.'})
        request.user.set_password(pw)
        request.user.must_change_password = False
        request.user.save()
        login(request, request.user)  # keep this session alive after the hash changes
        return Response({'user': user_out(request.user)})


# ------------------------------------------------------------------ users (admin only)
def clean_user_payload(data, instance=None):
    errors = {}
    name = (data.get('name') or '').strip()
    username = norm_username(data.get('username'))
    role = data.get('role') or User.SUPPLIER
    org = (data.get('org') or '').strip()
    code = (data.get('code') or '').strip()
    tax = normalize_digits(data.get('taxNo'))
    if not name:
        errors['name'] = 'أدخل الاسم الكامل.'
    if not USERNAME_RE.match(username):
        errors['username'] = 'أرقام أو حروف إنجليزية صغيرة، حتى 30 خانة.'
    elif User.objects.filter(username=username).exclude(pk=getattr(instance, 'pk', None)).exists():
        errors['username'] = 'رقم المستخدم مستخدم لحساب آخر.'
    if role not in dict(User.ROLES):
        errors['role'] = 'دور غير صحيح.'
    supplier = None
    if role == User.SUPPLIER:
        sid = str(data.get('supplierId') or '')
        if sid:
            # the normal path: the account is linked to a supplier from the supplier data screen
            supplier = Supplier.objects.filter(pk=sid, is_active=True).first() if sid.isdigit() else None
            if not supplier and instance and sid.isdigit() and instance.supplier_id == int(sid):
                supplier = instance.supplier
            if not supplier:
                errors['supplierId'] = 'اختر مورداً من بيانات الموردين.'
        else:
            # direct entry of the company details (commands and older clients): find or create the supplier record
            if not org:
                errors['org'] = 'أدخل اسم المورد.'
            if not code:
                errors['code'] = 'أدخل رمز المورد.'
            elif Supplier.objects.filter(code__iexact=code).exclude(pk=getattr(instance, 'supplier_id', None)).exists():
                errors['code'] = 'رمز المورد مستخدم لمورد آخر.'
            if tax and not TAX_RE.match(tax):
                errors['taxNo'] = 'الرقم الضريبي 15 رقماً.'
            if not errors:
                if instance and instance.supplier_id:
                    supplier = instance.supplier
                    supplier.name, supplier.code, supplier.tax_no = org, code, tax
                else:
                    supplier = Supplier(name=org, code=code, tax_no=tax)
                supplier.save()
    else:
        org, code, tax = org or 'أسواق الرشيد', '', ''
    if errors:
        raise ValidationError(errors)
    out = {'name': name, 'username': username, 'role': role, 'org': org, 'code': code or None, 'tax_no': tax, 'supplier': supplier}
    if supplier:
        out.update(org=supplier.name, code=supplier.code, tax_no=supplier.tax_no)
    return out


def clean_pages(data, role, current, editing_self):
    """None = the role's default pages. Staff get a subset of the four staff pages; suppliers never get staff pages."""
    raw = data.get('pages')
    if raw is None or raw == '':
        return None
    if not isinstance(raw, list):
        raise ValidationError({'pages': 'صيغة الصلاحيات غير صحيحة.'})
    if role == User.SUPPLIER:
        raise ValidationError({'pages': 'حساب المورد لا تُعدَّل صلاحياته.'})
    pages = [p for p in STAFF_PAGES if p in raw]
    if len(pages) != len(set(raw)):
        raise ValidationError({'pages': 'صفحة غير معروفة في الصلاحيات.'})
    if not pages:
        raise ValidationError({'pages': 'اختر صفحة واحدة على الأقل.'})
    if editing_self and 'users' not in pages:
        raise ValidationError({'pages': 'لا يمكنك سحب صلاحية إدارة المستخدمين من حسابك الحالي.'})
    return pages


class UsersView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response([user_out(u) for u in User.objects.select_related('supplier').order_by('name')])

    def post(self, request):
        fields = clean_user_payload(request.data)
        pw = request.data.get('password') or ''
        check_password_rule(pw)
        user = User(**fields, must_change_password=True, pages=clean_pages(request.data, fields['role'], None, False))
        user.set_password(pw)
        user.save()
        return Response(user_out(user), status=201)


class UserDetailView(APIView):
    permission_classes = [IsAdmin]

    def delete(self, request, pk):
        user = User.objects.filter(pk=pk).first() or self._404()
        if user.pk == request.user.pk:
            raise ValidationError({'detail': 'لا يمكنك حذف حسابك الحالي.'})
        if user.role == User.ADMIN and User.objects.filter(role=User.ADMIN, is_active=True).exclude(pk=user.pk).count() == 0:
            raise ValidationError({'detail': 'لا يمكن حذف آخر مدير نظام.'})
        if user.requests.exists() or user.complaints.exists():
            raise ValidationError({'detail': 'لهذا المورد طلبات أو شكاوى مسجّلة، فلا يمكن حذفه. أوقف الحساب بدلاً من ذلك، أو احذف طلباته أولاً.'})
        revoke_sessions(user)
        user.delete()
        return Response(status=204)

    def patch(self, request, pk):
        user = User.objects.filter(pk=pk).first() or self._404()
        fields = clean_user_payload(request.data, user)
        if user.pk == request.user.pk and fields['role'] != user.role:
            raise ValidationError({'role': 'لا يمكنك تغيير دور حسابك الحالي.'})
        active = bool(request.data.get('active', user.is_active))
        if user.pk == request.user.pk:
            active = True
        for k, v in fields.items():
            setattr(user, k, v)
        if 'pages' in request.data:
            user.pages = clean_pages(request.data, fields['role'], user.pages, user.pk == request.user.pk)
        elif fields['role'] != User.objects.get(pk=user.pk).role:
            user.pages = None                                  # a new role starts from its own default pages
        user.is_active = active
        new_pw = request.data.get('password') or ''
        if new_pw:
            check_password_rule(new_pw)
            user.set_password(new_pw)
            user.must_change_password = bool(request.data.get('mustChange', False))
        user.save()
        if new_pw:
            if user.pk == request.user.pk:
                update_session_auth_hash(request, user)      # keep the admin signed in after changing their own password
            else:
                revoke_sessions(user)
        elif not active:
            revoke_sessions(user)
        if new_pw and not active:
            revoke_sessions(user)
        return Response(user_out(user))

    @staticmethod
    def _404():
        raise NotFound('المستخدم غير موجود.')


class UserToggleView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if not user:
            raise NotFound('المستخدم غير موجود.')
        if user.pk == request.user.pk:
            raise ValidationError({'detail': 'لا يمكنك إيقاف حسابك الحالي.'})
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        if not user.is_active:
            revoke_sessions(user)
        return Response(user_out(user))


class UserResetView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if not user:
            raise NotFound('المستخدم غير موجود.')
        pw = temp_password()
        user.set_password(pw)
        user.must_change_password = True
        user.save()
        revoke_sessions(user)
        return Response({'user': user_out(user), 'password': pw})


# ------------------------------------------------------------------ matching requests
supplier_or_requests = supplier_or_page('matcher', 'manager')

def request_qs():
    return (MatchRequest.objects.select_related('supplier', 'matcher')
            .prefetch_related('attachments', 'messages__files', 'messages__sender'))


def get_request(user, pk):
    req = request_qs().filter(pk=pk).first()
    if not req or not can_view_request(user, req):
        raise NotFound('الطلب غير موجود.')
    return req


def stamp(obj, stage):
    obj.reached = {**obj.reached, str(stage): timezone.now().isoformat()}


def system_message(parent_field, parent, text):
    return Message.objects.create(**{parent_field: parent}, kind=Message.SYSTEM, text=text)


def statement_period(data):
    """The statement period as a from / to date range ("dateFrom", "dateTo"); a plain "period" text is still accepted."""
    start, end = (data.get('dateFrom') or '').strip(), (data.get('dateTo') or '').strip()
    if not start and not end:
        period = (data.get('period') or '').strip()
        if not period:
            raise ValidationError({'dateFrom': 'حدّد تاريخ بداية الكشف ونهايته.'})
        return period[:60]
    try:
        d1, d2 = date.fromisoformat(normalize_digits(start)), date.fromisoformat(normalize_digits(end))
    except ValueError:
        raise ValidationError({'dateFrom': 'حدّد تاريخ البداية والنهاية بشكل صحيح.'})
    if d1 > d2:
        raise ValidationError({'dateTo': 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية.'})
    if d2 > timezone.localdate() or d1.year < 2000 or (d2 - d1).days > 3660:
        raise ValidationError({'dateTo': 'الفترة غير صحيحة. اختر تواريخ سابقة لا تتجاوز 10 سنوات.'})
    return f'من {d1:%d/%m/%Y} إلى {d2:%d/%m/%Y}'


class RequestsView(APIView):
    permission_classes = [supplier_or_requests]

    def get(self, request):
        qs = request_qs()
        if request.user.role == User.SUPPLIER:
            qs = qs.filter(supplier=request.user)
        return Response([request_out(r) for r in qs])

    @transaction.atomic
    def post(self, request):
        if request.user.role != User.SUPPLIER:
            raise PermissionDenied('رفع الطلبات للمورد فقط.')
        period = statement_period(request.data)
        statement = request.FILES.get('statement')
        if not statement:
            raise ValidationError({'statement': 'أرفق كشف الحساب.'})
        now = timezone.now()
        # a double click sends the same request twice: answer with the one just created instead of making a copy
        twin = request_qs().filter(supplier=request.user, period=period, created_at__gte=now - timedelta(seconds=60),
                                   attachments__kind=Attachment.STATEMENT, attachments__original_name=statement.name[:255], attachments__size=statement.size).first()
        if twin:
            return Response(request_out(twin), status=200)
        req = MatchRequest.objects.create(
            supplier=request.user, period=period, notes=(request.data.get('notes') or '').strip(),
            due_at=now + timedelta(days=SLA_DAYS), reached={'1': now.isoformat()}, created_at=now)
        req.number = f'MT-{now:%y%m}-{req.pk:04d}'
        req.save(update_fields=['number'])
        save_files([statement], request.user, request=req, kind=Attachment.STATEMENT)
        return Response(request_out(request_qs().get(pk=req.pk)), status=201)


class RequestDetailView(APIView):
    permission_classes = [supplier_or_requests]

    def get(self, request, pk):
        return Response(request_out(get_request(request.user, pk)))

    def patch(self, request, pk):
        if request.user.role == User.SUPPLIER:
            raise PermissionDenied()
        req = get_request(request.user, pk)
        if request.user.role == User.MATCHER and req.matcher_id != request.user.pk:
            raise PermissionDenied('هذا الطلب ليس مسنداً إليك.')
        if 'diff' in request.data:
            raw = request.data.get('diff')
            try:
                req.diff = None if raw in (None, '') else Decimal(str(raw))
            except InvalidOperation:
                raise ValidationError({'diff': 'قيمة الفرق غير صحيحة.'})
        req.save()
        return Response(request_out(get_request(request.user, pk)))

    @transaction.atomic
    def delete(self, request, pk):
        req = get_request(request.user, pk)
        # the system admin may delete any request; a supplier only their own request that nobody has received yet
        if not (request.user.role == User.ADMIN or (request.user.role == User.SUPPLIER and req.stage == 1)):
            raise PermissionDenied('لا يمكن حذف هذا الطلب. الحذف لمدير النظام، أو للمورد قبل استلام طلبه.')
        req.delete()                                    # messages and files go with it
        return Response(status=204)


class ChangesView(APIView):
    """A tiny fingerprint of what the signed-in user can see. The page polls it and reloads the lists only when it changes."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mine = request.user.role == User.SUPPLIER
        reqs, comps = MatchRequest.objects.all(), Complaint.objects.all()
        msgs, files = Message.objects.all(), Attachment.objects.all()
        if mine:
            reqs, comps = reqs.filter(supplier=request.user), comps.filter(supplier=request.user)
            msgs = msgs.filter(Q(request__supplier=request.user) | Q(complaint__supplier=request.user))
            files = files.filter(Q(request__supplier=request.user) | Q(message__request__supplier=request.user) | Q(message__complaint__supplier=request.user))
        notices = Notice.objects.filter(supplier=request.user) if mine else Notice.objects.all()
        parts = [
            notices.aggregate(n=Count('id'), m=Max('id')),
            reqs.aggregate(n=Count('id'), m=Max('id'), s=Sum('stage'), a=Sum('matcher_id'), d=Sum('diff')),
            comps.aggregate(n=Count('id'), m=Max('id'), s=Sum('stage')),
            msgs.aggregate(n=Count('id'), m=Max('id')),
            files.aggregate(n=Count('id'), m=Max('id')),
        ]
        if not mine:
            parts.append(User.objects.aggregate(n=Count('id'), m=Max('id'), a=Count('id', filter=Q(is_active=True)), p=Max('last_login')))
        return Response({'v': str(parts)})


class MatchersView(APIView):
    """Active matchers: the list the supervisor picks from when receiving a request."""
    permission_classes = [IsMatcherPage]

    def get(self, request):
        return Response([{'id': u.pk, 'name': u.name} for u in User.objects.filter(role=User.MATCHER, is_active=True).order_by('name')])


class RequestAdvanceView(APIView):
    permission_classes = [IsMatcherPage]

    @transaction.atomic
    def post(self, request, pk):
        # lock the row first: two clicks (or two people) at the same moment must not advance the request twice
        list(MatchRequest.objects.select_for_update().filter(pk=pk).values_list('pk', flat=True))
        req = get_request(request.user, pk)
        seen = request.data.get('fromStage')
        if seen not in (None, '') and str(seen) != str(req.stage):
            # the page was showing an older step: someone (or a second click) already moved the request
            return Response({'detail': 'تغيّرت حالة الطلب للتو. حُدّثت الصفحة فتأكد قبل المتابعة.'}, status=409)
        if req.stage >= 5:
            raise ValidationError({'detail': 'الطلب منجز.'})
        role = request.user.role
        if req.stage in (1, 4) and role not in (User.SUPERVISOR, User.MANAGER, User.ADMIN):
            raise PermissionDenied('استلام الطلبات وإرسال ملف المطابقة لموظف الدعم أو المدير المالي أو مدير النظام فقط.')
        if req.stage == 1:
            # receiving a request is for the support supervisor, the finance manager and the system admin: they hand it to a matcher
            matcher_id = request.data.get('matcherId')
            matcher = User.objects.filter(pk=matcher_id, role=User.MATCHER, is_active=True).first() if str(matcher_id or '').isdigit() else None
            if not matcher:
                raise ValidationError({'matcherId': 'اختر المطابق الذي ستُسند إليه الطلب.'})
            req.matcher = matcher
            note = f'استلم {dict(User.ROLES)[role]} {request.user.name} الطلب وأسنده إلى المطابق {matcher.name}'
        elif req.stage == 4:
            # the last step: the support employee sends the reconciliation file to the supplier
            f = request.FILES.get('file')
            if not f:
                raise ValidationError({'file': 'أرفق ملف المطابقة لإرساله إلى المورد.'})
            save_files([f], request.user, request=req, kind=Attachment.RESULT)
            note = f'أرسل {dict(User.ROLES)[role]} {request.user.name} ملف المطابقة إلى المورد'
        else:
            if role == User.SUPERVISOR:
                raise PermissionDenied('بعد الاستلام يتابع المطابق الطلب.')
            if role == User.MATCHER and req.matcher_id != request.user.pk:
                raise PermissionDenied('هذا الطلب ليس مسنداً إليك.')
            note = REQ_NOTE[req.stage]
        system_message('request', req, note)
        req.stage += 1
        stamp(req, req.stage)
        req.save()
        return Response(request_out(get_request(request.user, pk)))


def post_message(request, parent, field, kind, allowed):
    if not allowed:
        raise PermissionDenied('لا يمكنك المراسلة في هذا الطلب الآن.')
    text = (request.data.get('text') or '').strip()
    files = request.FILES.getlist('files')
    if not text and not files:
        raise ValidationError({'detail': 'اكتب رسالة أو أرفق ملفاً.'})
    for f in files:
        validate_upload(f)
    with transaction.atomic():
        msg = Message.objects.create(**{field: parent}, kind=kind, sender=request.user, text=text)
        save_files(files, request.user, message=msg)
    return message_out(Message.objects.prefetch_related('files').select_related('sender').get(pk=msg.pk))


class RequestMessagesView(APIView):
    permission_classes = [supplier_or_requests]

    def post(self, request, pk):
        req = get_request(request.user, pk)
        role = request.user.role
        kind = Message.SUPPLIER if role == User.SUPPLIER else Message.MATCHER
        ok = req.stage == 3 and role != User.SUPERVISOR and (role != User.MATCHER or req.matcher_id == request.user.pk)
        return Response(post_message(request, req, 'request', kind, ok), status=201)


# ------------------------------------------------------------------ complaints
def complaint_qs():
    return Complaint.objects.select_related('supplier', 'related').prefetch_related('messages__files', 'messages__sender')


def get_complaint(user, pk):
    c = complaint_qs().filter(pk=pk).first()
    if not c or not can_view_complaint(user, c):
        raise NotFound('الشكوى غير موجودة.')
    return c


class ComplaintsView(APIView):
    permission_classes = [SupplierOrManagerPage]

    def get(self, request):
        qs = complaint_qs()
        if request.user.role == User.SUPPLIER:
            qs = qs.filter(supplier=request.user)
        return Response([complaint_out(c) for c in qs])

    @transaction.atomic
    def post(self, request):
        if request.user.role != User.SUPPLIER:
            raise PermissionDenied('رفع الشكاوى للمورد فقط.')
        category = (request.data.get('category') or '').strip()
        subject = (request.data.get('subject') or '').strip()
        body = (request.data.get('body') or '').strip()
        errors = {}
        if not category:
            errors['category'] = 'اختر نوع الشكوى.'
        if not subject:
            errors['subject'] = 'اكتب عنوان الشكوى.'
        if not body:
            errors['body'] = 'اكتب تفاصيل الشكوى.'
        related = None
        if request.data.get('related'):
            related = MatchRequest.objects.filter(number=request.data.get('related'), supplier=request.user).first()
            if not related:
                errors['related'] = 'الطلب المرتبط غير موجود.'
        files = request.FILES.getlist('files')
        for f in files:
            validate_upload(f)
        twin = complaint_qs().filter(supplier=request.user, category=category, subject=subject, created_at__gte=timezone.now() - timedelta(seconds=60)).first()
        if twin and not errors:
            return Response(complaint_out(twin), status=200)
        if errors:
            raise ValidationError(errors)
        now = timezone.now()
        c = Complaint.objects.create(supplier=request.user, category=category, subject=subject, related=related,
                                     reached={'1': now.isoformat()}, created_at=now)
        c.number = f'SH-{now:%y%m}-{c.pk:04d}'
        c.save(update_fields=['number'])
        msg = Message.objects.create(complaint=c, kind=Message.SUPPLIER, sender=request.user, text=body, created_at=now)
        save_files(files, request.user, message=msg)
        return Response(complaint_out(complaint_qs().get(pk=c.pk)), status=201)


class ComplaintDetailView(APIView):
    permission_classes = [SupplierOrManagerPage]

    def get(self, request, pk):
        return Response(complaint_out(get_complaint(request.user, pk)))

    @transaction.atomic
    def delete(self, request, pk):
        c = get_complaint(request.user, pk)
        if not (request.user.role == User.ADMIN or (request.user.role == User.SUPPLIER and c.stage == 1)):
            raise PermissionDenied('لا يمكن حذف هذه الشكوى. الحذف لمدير النظام، أو للمورد قبل أن يبدأ المدير المالي مراجعتها.')
        c.delete()
        return Response(status=204)


class ComplaintAdvanceView(APIView):
    permission_classes = [IsManagerPage]

    @transaction.atomic
    def post(self, request, pk):
        list(Complaint.objects.select_for_update().filter(pk=pk).values_list('pk', flat=True))
        c = get_complaint(request.user, pk)
        if c.stage >= 3:
            raise ValidationError({'detail': 'الشكوى مغلقة.'})
        system_message('complaint', c, COMPLAINT_NOTE[c.stage])
        c.stage += 1
        stamp(c, c.stage)
        c.save()
        return Response(complaint_out(get_complaint(request.user, pk)))


class ComplaintMessagesView(APIView):
    permission_classes = [SupplierOrManagerPage]

    def post(self, request, pk):
        c = get_complaint(request.user, pk)
        kind = Message.SUPPLIER if request.user.role == User.SUPPLIER else Message.MANAGER
        return Response(post_message(request, c, 'complaint', kind, c.stage < 3), status=201)


# ------------------------------------------------------------------ files
class AttachmentDownloadView(APIView):
    """Files stream through Django so every download passes the same permission check."""

    def get(self, request, pk):
        a = Attachment.objects.select_related('request__supplier', 'message__request__supplier', 'message__complaint__supplier').filter(pk=pk).first()
        if not a:
            raise NotFound('الملف غير موجود.')
        req = a.request or (a.message.request if a.message else None)
        comp = a.message.complaint if a.message else None
        allowed = (req and can_view_request(request.user, req)) or (comp and can_view_complaint(request.user, comp))
        if not allowed:
            raise NotFound('الملف غير موجود.')
        inline = extension_of(a.original_name) in INLINE_TYPES
        resp = FileResponse(a.file.open('rb'), as_attachment=not inline, filename=a.original_name)
        resp['X-Content-Type-Options'] = 'nosniff'
        resp['Cache-Control'] = 'private, max-age=0'
        return resp


# ------------------------------------------------------------------ supplier notices (simple tax invoices)
def notice_qs():
    return Notice.objects.select_related('supplier__supplier', 'issued_by')


def get_notice(user, pk):
    n = notice_qs().filter(pk=pk).first()
    if not n or (user.role == User.SUPPLIER and n.supplier_id != user.pk):
        raise NotFound('الإشعار غير موجود.')
    return n


def money(v, field, allow_zero=True):
    try:
        d = Decimal(str(v if v not in (None, '') else 0))
    except InvalidOperation:
        raise ValidationError({'items': f'قيمة غير صحيحة في {field}.'})
    if not d.is_finite() or d < 0 or d > Decimal('99999999') or (not allow_zero and d == 0):
        raise ValidationError({'items': f'قيمة غير صحيحة في {field}.'})
    return d.quantize(Decimal('0.01'))


def clean_notice_items(raw):
    if not isinstance(raw, list) or not raw:
        raise ValidationError({'items': 'أضف بنداً واحداً على الأقل.'})
    if len(raw) > 60:
        raise ValidationError({'items': 'الحد الأقصى 60 بنداً.'})
    out = []
    for it in raw:
        name = str((it or {}).get('name') or '').strip()
        if not name:
            raise ValidationError({'items': 'اكتب اسم كل بند.'})
        qty = money(it.get('qty'), 'الكمية', allow_zero=False)
        price = money(it.get('price'), 'السعر')
        disc = money(it.get('discount'), 'الخصم')
        if disc > qty * price:
            raise ValidationError({'items': 'الخصم أكبر من قيمة البند.'})
        out.append({'code': str(it.get('code') or '').strip()[:30], 'name': name[:200], 'qty': str(qty), 'price': str(price), 'discount': str(disc)})
    return out


BUYER_FIELDS = ('name', 'building', 'street', 'district', 'city', 'country', 'postal', 'additional', 'vat', 'crn', 'otherId', 'mobile')


def clean_buyer(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {k: str(raw.get(k) or '').strip()[:120] for k in BUYER_FIELDS if str(raw.get(k) or '').strip()}


def notice_totals(items):
    rate = Decimal(str(settings.VAT_RATE))
    sub = disc = vat = Decimal('0')
    for it in items:
        net = (Decimal(it['qty']) * Decimal(it['price'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) - Decimal(it['discount'])
        sub += net
        disc += Decimal(it['discount'])
        vat += (net * rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return sub.quantize(Decimal('0.01')), disc.quantize(Decimal('0.01')), vat, rate


def clean_due(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ValidationError({'dueDate': 'تاريخ الاستحقاق غير صحيح.'})


class SuppliersView(APIView):
    """The supplier accounts a notice can be issued to."""
    permission_classes = [IsNoticesPage]

    def get(self, request):
        return Response([{'id': u.pk, 'name': u.org or u.name, 'taxNo': u.tax_no, 'code': u.code or '',
                          'mobile': u.supplier.mobile if u.supplier_id else '', 'account': u.name}
                         for u in User.objects.filter(role=User.SUPPLIER, is_active=True).select_related('supplier').order_by('org', 'name')])


def clean_supplier_payload(data, instance=None):
    errors = {}
    name = (data.get('name') or '').strip()
    code = (data.get('code') or '').strip()
    tax = normalize_digits(data.get('taxNo'))
    mobile = normalize_mobile(data.get('mobile'))
    if not name:
        errors['name'] = 'أدخل اسم المورد.'
    if not code:
        errors['code'] = 'أدخل رمز المورد.'
    elif Supplier.objects.filter(code__iexact=code).exclude(pk=getattr(instance, 'pk', None)).exists():
        errors['code'] = 'رمز المورد مستخدم لمورد آخر.'
    if tax and not TAX_RE.match(tax):
        errors['taxNo'] = 'الرقم الضريبي 15 رقماً.'
    if mobile and not MOBILE_RE.match(mobile):
        errors['mobile'] = 'رقم الجوال 10 أرقام ويبدأ بـ 05.'
    if errors:
        raise ValidationError(errors)
    return {'name': name[:200], 'code': code[:30], 'tax_no': tax, 'mobile': mobile}


class SupplierDataView(APIView):
    """Supplier master data. Everyone who needs to pick a supplier can read it; only the suppliers page edits it."""
    permission_classes = [CanReadSuppliers]

    def get(self, request):
        qs = Supplier.objects.annotate(n_users=Count('users')).order_by('name')
        return Response([supplier_out(s, s.n_users) for s in qs])

    @transaction.atomic
    def post(self, request):
        if 'suppliers' not in allowed_pages(request.user):
            raise PermissionDenied('ليست لديك صلاحية لهذه الصفحة.')
        s = Supplier.objects.create(**clean_supplier_payload(request.data))
        return Response(supplier_out(s, 0), status=201)


class SupplierDataDetailView(APIView):
    permission_classes = [IsSuppliersPage]

    @staticmethod
    def _get(pk):
        s = Supplier.objects.filter(pk=pk).first()
        if not s:
            raise NotFound('المورد غير موجود.')
        return s

    @transaction.atomic
    def patch(self, request, pk):
        s = self._get(pk)
        for k, v in clean_supplier_payload(request.data, s).items():
            setattr(s, k, v)
        if 'active' in request.data:
            s.is_active = bool(request.data.get('active'))
        s.save()                         # also refreshes the company details copied into its accounts
        return Response(supplier_out(s))

    def delete(self, request, pk):
        s = self._get(pk)
        if s.users.exists():
            raise ValidationError({'detail': 'هذا المورد مرتبط بحسابات مستخدمين، فلا يمكن حذفه. أوقفه بدلاً من ذلك، أو افصل حساباته أولاً.'})
        s.delete()
        return Response(status=204)


class NoticesView(APIView):
    permission_classes = [SupplierOrNotices]

    def get(self, request):
        qs = notice_qs()
        if request.user.role == User.SUPPLIER:
            qs = qs.filter(supplier=request.user)
        return Response([notice_out(n) for n in qs[:500]])

    @transaction.atomic
    def post(self, request):
        if request.user.role == User.SUPPLIER:
            raise PermissionDenied('إصدار الإشعارات للفريق المالي فقط.')
        supplier = User.objects.filter(pk=request.data.get('supplierId'), role=User.SUPPLIER, is_active=True).first() if str(request.data.get('supplierId') or '').isdigit() else None
        if not supplier:
            raise ValidationError({'supplierId': 'اختر المورد.'})
        items = clean_notice_items(request.data.get('items'))
        sub, disc, vat, rate = notice_totals(items)
        due = clean_due(request.data.get('dueDate'))
        n = Notice.objects.create(
            supplier=supplier, issued_by=request.user, due_date=due, items=items, buyer=clean_buyer(request.data.get('buyer')),
            payment_method=(request.data.get('paymentMethod') or 'من حساب').strip()[:40],
            description=(request.data.get('description') or '').strip()[:1000],
            subtotal=sub, discount=disc, vat=vat, total=sub + vat, vat_rate=rate)
        n.number = f'NT-{n.issued_at:%y%m}-{n.pk:04d}'
        n.save(update_fields=['number'])
        return Response(notice_out(notice_qs().get(pk=n.pk)), status=201)


class NoticeDetailView(APIView):
    permission_classes = [SupplierOrNotices]

    def get(self, request, pk):
        return Response(notice_out(get_notice(request.user, pk)))

    @transaction.atomic
    def patch(self, request, pk):
        if request.user.role == User.SUPPLIER:
            raise PermissionDenied('تعديل الإشعارات للفريق المالي فقط.')
        n = get_notice(request.user, pk)
        if 'items' in request.data:
            n.items = clean_notice_items(request.data.get('items'))
            n.subtotal, n.discount, n.vat, n.vat_rate = notice_totals(n.items)
            n.total = n.subtotal + n.vat
        if 'description' in request.data:
            n.description = (request.data.get('description') or '').strip()[:1000]
        if 'dueDate' in request.data:
            n.due_date = clean_due(request.data.get('dueDate'))
        if 'paymentMethod' in request.data:
            n.payment_method = (request.data.get('paymentMethod') or 'من حساب').strip()[:40]
        if 'buyer' in request.data:
            n.buyer = clean_buyer(request.data.get('buyer'))
        n.save()
        return Response(notice_out(notice_qs().get(pk=n.pk)))

    def delete(self, request, pk):
        if request.user.role != User.ADMIN:
            raise PermissionDenied('حذف الإشعارات لمدير النظام فقط.')
        get_notice(request.user, pk).delete()
        return Response(status=204)
