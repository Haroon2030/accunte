"""
أدوات مشتركة لواجهات JSON: قراءة الجسم، الأخطاء الموحّدة، فحص الدخول والدور.
الواجهة الأمامية ترسل CSRF في X-CSRFToken، وDjango يتحقق منه تلقائياً في كل POST.
"""
import json
from functools import wraps

from django.http import JsonResponse


class ApiError(Exception):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra


def body(request):
    """جسم JSON كقاموس، أو حقول النموذج (multipart)."""
    if request.content_type and request.content_type.startswith('application/json'):
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
        except (ValueError, UnicodeDecodeError):
            raise ApiError('جسم الطلب غير صالح.')
        if not isinstance(data, dict):
            raise ApiError('جسم الطلب غير صالح.')
        return data
    return request.POST


def role_of(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


def endpoint(*, methods=('GET',), roles=None, allow_must_change=False):
    """يغلّف عرض JSON: الطريقة المسموحة، الدخول، الدور، ومنع الاستعمال قبل تغيير كلمة المرور المؤقتة."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            try:
                if request.method not in methods:
                    raise ApiError('الطريقة غير مسموحة.', 405)
                user = request.user
                if not user.is_authenticated or not user.is_active or getattr(user, 'profile', None) is None:
                    raise ApiError('سجّل الدخول أولاً.', 401)
                if user.profile.must_change_password and not allow_must_change:
                    raise ApiError('يجب تغيير كلمة المرور المؤقتة أولاً.', 403, code='must_change_password')
                if roles and user.profile.role not in roles:
                    raise ApiError('ليس لديك صلاحية لهذا الإجراء.', 403)
                response = view(request, *args, **kwargs)
            except ApiError as exc:
                response = JsonResponse({'error': exc.message, **exc.extra}, status=exc.status)
            response['Cache-Control'] = 'no-store'
            return response
        return wrapper
    return decorator


def public_endpoint(*, methods=('POST',)):
    """لعرض لا يتطلب دخولاً (تسجيل الدخول)."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            try:
                if request.method not in methods:
                    raise ApiError('الطريقة غير مسموحة.', 405)
                response = view(request, *args, **kwargs)
            except ApiError as exc:
                response = JsonResponse({'error': exc.message, **exc.extra}, status=exc.status)
            response['Cache-Control'] = 'no-store'
            return response
        return wrapper
    return decorator
