"""
التحكم في الوصول حسب الدور (RBAC) - Role-based access helpers
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import Role

RT = Role.RoleType

# المجموعات المستخدمة عبر الوحدات
SUPERVISION_ROLES = (RT.ADMIN, RT.CFO)
AUDIT_VIEW_ROLES = (RT.ADMIN, RT.CFO)
SUPPLIER_VIEW_ROLES = (RT.ADMIN, RT.CFO, RT.ACCOUNTANT, RT.CS_SUPERVISOR)
SUPPLIER_MANAGE_ROLES = (RT.ADMIN, RT.CFO, RT.ACCOUNTANT)
SUPPLIER_IMPORT_ROLES = (RT.ADMIN, RT.CFO)


def get_role_type(user):
    """نوع دور المستخدم، أو None. السوبر يوزر يُعامل كمدير نظام."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return RT.ADMIN
    profile = getattr(user, 'profile', None)
    role = getattr(profile, 'role', None) if profile else None
    return role.role_type if role and role.is_active else None


def is_portal_supplier(user):
    """حساب مورد (بوابة الموردين): يصل إلى /portal/ فقط."""
    return get_role_type(user) == RT.SUPPLIER and not user.is_superuser


def has_role(user, *role_types):
    role = get_role_type(user)
    if role is None:
        return False
    return role == RT.ADMIN or role in role_types


def role_required(*role_types, message='ليس لديك صلاحية للوصول إلى هذه الصفحة'):
    """ديكوريتر: يسمح فقط للأدوار المحددة (ومدير النظام دائمًا)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('auth:login')
            if not has_role(request.user, *role_types):
                messages.error(request, message)
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


class RoleRequiredMixin:
    """Mixin للـ CBVs: عرّف allowed_roles = (...)."""
    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('auth:login')
        if not has_role(request.user, *self.allowed_roles):
            messages.error(request, 'ليس لديك صلاحية للوصول إلى هذه الصفحة')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)
