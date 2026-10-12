from rest_framework.permissions import BasePermission, IsAuthenticated

from .models import User


class SettledAccount(BasePermission):
    """Signed in, and past the forced first-login password change."""
    message = 'غيّر كلمة المرور المؤقتة أولاً.'

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and not u.must_change_password)


def roles(*allowed):
    class HasRole(SettledAccount):
        message = 'ليست لديك صلاحية لهذا الإجراء.'

        def has_permission(self, request, view):
            return super().has_permission(request, view) and request.user.role in allowed

    return HasRole


IsAdmin = roles(User.ADMIN)
IsStaff = roles(User.MATCHER, User.MANAGER, User.ADMIN)
IsSupplier = roles(User.SUPPLIER)


def can_view_request(user, req):
    return user.role != User.SUPPLIER or req.supplier_id == user.pk


def can_view_complaint(user, c):
    if user.role in (User.MANAGER, User.ADMIN):
        return True
    return user.role == User.SUPPLIER and c.supplier_id == user.pk
