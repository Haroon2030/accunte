import re
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Q
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

from .models import SLA_DAYS, Attachment, Complaint, Message, MatchRequest, User
from .permissions import (supplier_or_page, IsAdmin, IsManagerPage, IsMatcherPage, IsStaff, IsSupplier, STAFF_PAGES, SupplierOrManagerPage, allowed_pages,
                          can_view_complaint, can_view_request, roles)
from .serializers import complaint_out, message_out, request_out, user_out
from .validators import INLINE_TYPES, TAX_RE, check_password_rule, extension_of, normalize_digits, validate_upload

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
    if role == User.SUPPLIER:
        if not org:
            errors['org'] = 'أدخل اسم المورد.'
        if not code:
            errors['code'] = 'أدخل رمز المورد.'
        elif User.objects.filter(code__iexact=code).exclude(pk=getattr(instance, 'pk', None)).exists():
            errors['code'] = 'رمز المورد مستخدم لمورد آخر.'
        if tax and not TAX_RE.match(tax):
            errors['taxNo'] = 'الرقم الضريبي 15 رقماً.'
    else:
        org, code, tax = org or 'أسواق الرشيد', '', ''
    if errors:
        raise ValidationError(errors)
    return {'name': name, 'username': username, 'role': role, 'org': org, 'code': code or None, 'tax_no': tax}


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
        return Response([user_out(u) for u in User.objects.order_by('name')])

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
        period = (request.data.get('period') or '').strip()
        statement = request.FILES.get('statement')
        if not period:
            raise ValidationError({'period': 'اختر فترة الكشف.'})
        if not statement:
            raise ValidationError({'statement': 'أرفق كشف الحساب.'})
        now = timezone.now()
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


class MatchersView(APIView):
    """Active matchers: the list the supervisor picks from when receiving a request."""
    permission_classes = [IsMatcherPage]

    def get(self, request):
        return Response([{'id': u.pk, 'name': u.name} for u in User.objects.filter(role=User.MATCHER, is_active=True).order_by('name')])


class RequestAdvanceView(APIView):
    permission_classes = [IsMatcherPage]

    @transaction.atomic
    def post(self, request, pk):
        req = get_request(request.user, pk)
        if req.stage >= 4:
            raise ValidationError({'detail': 'الطلب منجز.'})
        role = request.user.role
        if req.stage == 1:
            # receiving a request is for the support supervisor, the finance manager and the system admin: they hand it to a matcher
            if role not in (User.SUPERVISOR, User.MANAGER, User.ADMIN):
                raise PermissionDenied('استلام الطلبات لمشرف الدعم أو المدير المالي أو مدير النظام فقط.')
            matcher_id = request.data.get('matcherId')
            matcher = User.objects.filter(pk=matcher_id, role=User.MATCHER, is_active=True).first() if str(matcher_id or '').isdigit() else None
            if not matcher:
                raise ValidationError({'matcherId': 'اختر المطابق الذي ستُسند إليه الطلب.'})
            req.matcher = matcher
            note = f'استلم {dict(User.ROLES)[role]} {request.user.name} الطلب وأسنده إلى المطابق {matcher.name}'
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


class ComplaintAdvanceView(APIView):
    permission_classes = [IsManagerPage]

    @transaction.atomic
    def post(self, request, pk):
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
