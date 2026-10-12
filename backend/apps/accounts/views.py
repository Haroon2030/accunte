"""واجهات الدخول وإدارة المستخدمين (JSON)."""
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie

from .api import ApiError, body, endpoint, public_endpoint
from .models import UserProfile
from .services import (generate_password, normalize_username, password_error, serialize_user, validate_user_fields)

User = get_user_model()
Role = UserProfile.Role
LOGIN_ERROR = 'اسم المستخدم أو كلمة المرور غير صحيحة.'


@ensure_csrf_cookie
@public_endpoint(methods=('GET',))
def me(request):
    user = request.user
    if user.is_authenticated and user.is_active and getattr(user, 'profile', None):
        return JsonResponse({'user': serialize_user(user)})
    return JsonResponse({'user': None})


@public_endpoint(methods=('POST',))
def login_view(request):
    data = body(request)
    username = normalize_username(data.get('username'))
    password = str(data.get('password') or '')
    portal = 'supplier' if data.get('portal') == 'supplier' else 'staff'
    if not username or not password:
        raise ApiError('أدخل اسم المستخدم وكلمة المرور.')
    user = User.objects.select_related('profile').filter(username=username).first()
    profile = getattr(user, 'profile', None) if user else None
    # بوابة الموردين للموردين فقط، وبوابة الموظفين لغيرهم؛ والرد واحد حتى لا يُكشف وجود الحساب
    if user is None or profile is None or (profile.role == Role.SUPPLIER) != (portal == 'supplier'):
        raise ApiError(LOGIN_ERROR, 401)
    now = timezone.now()
    if profile.locked_until and profile.locked_until > now:
        wait = int((profile.locked_until - now).total_seconds()) + 1
        raise ApiError('تكررت المحاولة الخاطئة. أُوقف الدخول مؤقتاً.', 429, retryAfter=wait)
    if not user.check_password(password):
        profile.failed_logins += 1
        if profile.failed_logins >= settings.LOGIN_MAX_FAILS:
            profile.failed_logins = 0
            profile.locked_until = now + datetime.timedelta(seconds=settings.LOGIN_LOCK_SECONDS)
            profile.save(update_fields=['failed_logins', 'locked_until'])
            raise ApiError('تكررت المحاولة الخاطئة. أُوقف الدخول مؤقتاً.', 429, retryAfter=settings.LOGIN_LOCK_SECONDS)
        profile.save(update_fields=['failed_logins'])
        left = settings.LOGIN_MAX_FAILS - profile.failed_logins
        raise ApiError(f'{LOGIN_ERROR} المحاولات المتبقية: {left}', 401, attemptsLeft=left)
    if not user.is_active:
        raise ApiError('هذا الحساب موقوف. تواصل مع مدير النظام لتفعيله.', 403)
    profile.failed_logins, profile.locked_until = 0, None
    profile.save(update_fields=['failed_logins', 'locked_until'])
    login(request, user)
    return JsonResponse({'user': serialize_user(user)})


@endpoint(methods=('POST',), allow_must_change=True)
def logout_view(request):
    logout(request)
    return JsonResponse({'ok': True})


@endpoint(methods=('POST',), allow_must_change=True)
def change_password(request):
    data = body(request)
    old, new = str(data.get('oldPassword') or ''), str(data.get('newPassword') or '')
    user = request.user
    if not user.check_password(old):
        raise ApiError('كلمة المرور الحالية غير صحيحة.')
    err = password_error(new)
    if err:
        raise ApiError(err)
    if new == old:
        raise ApiError('اختر كلمة مرور مختلفة عن الحالية.')
    user.set_password(new)
    user.save(update_fields=['password'])
    user.profile.must_change_password = False
    user.profile.save(update_fields=['must_change_password'])
    update_session_auth_hash(request, user)
    return JsonResponse({'user': serialize_user(user)})


# ── إدارة المستخدمين: مدير النظام فقط ──
ADMIN_ONLY = (Role.ADMIN,)


@endpoint(methods=('GET', 'POST'), roles=ADMIN_ONLY)
def users_collection(request):
    if request.method == 'GET':
        users = User.objects.select_related('profile').filter(profile__isnull=False).order_by('first_name', 'username')
        return JsonResponse({'users': [serialize_user(u) for u in users]})
    data = body(request)
    fields = validate_user_fields(data)
    password = str(data.get('password') or '')
    err = password_error(password)
    if err:
        raise ApiError(err)
    with transaction.atomic():
        user = User.objects.create_user(fields['username'], password=password, first_name=fields['name'],
                                        is_active=True, is_staff=fields['role'] == Role.ADMIN)
        UserProfile.objects.create(user=user, role=fields['role'], org=fields['org'], must_change_password=True)
    return JsonResponse({'user': serialize_user(User.objects.select_related('profile').get(pk=user.pk))}, status=201)


def _target(pk):
    user = User.objects.select_related('profile').filter(pk=pk, profile__isnull=False).first()
    if user is None:
        raise ApiError('المستخدم غير موجود.', 404)
    return user


@endpoint(methods=('POST',), roles=ADMIN_ONLY)
def user_update(request, pk):
    user = _target(pk)
    data = body(request)
    fields = validate_user_fields(data, user=user, actor=request.user)
    active = bool(data.get('active', user.is_active)) if user.pk != request.user.pk else True
    with transaction.atomic():
        user.username, user.first_name, user.is_active = fields['username'], fields['name'], active
        user.is_staff = fields['role'] == Role.ADMIN
        user.save()
        user.profile.role, user.profile.org = fields['role'], fields['org']
        user.profile.save(update_fields=['role', 'org'])
    return JsonResponse({'user': serialize_user(user)})


@endpoint(methods=('POST',), roles=ADMIN_ONLY)
def user_toggle(request, pk):
    user = _target(pk)
    if user.pk == request.user.pk:
        raise ApiError('لا يمكنك إيقاف حسابك الحالي.')
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    return JsonResponse({'user': serialize_user(user)})


@endpoint(methods=('POST',), roles=ADMIN_ONLY)
def user_reset_password(request, pk):
    user = _target(pk)
    temp = generate_password()
    user.set_password(temp)
    user.save(update_fields=['password'])
    user.profile.must_change_password = True
    user.profile.failed_logins, user.profile.locked_until = 0, None
    user.profile.save(update_fields=['must_change_password', 'failed_logins', 'locked_until'])
    return JsonResponse({'user': serialize_user(user), 'password': temp})
