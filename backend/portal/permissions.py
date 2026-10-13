from rest_framework.permissions import BasePermission, IsAuthenticated

from .models import User

PAGE_KEYS = ('supplier', 'matcher', 'manager', 'recon', 'users')
STAFF_PAGES = ('matcher', 'manager', 'recon', 'users')
ROLE_PAGES = {
    User.SUPPLIER: ['supplier'],
    User.MATCHER: ['matcher', 'recon'],
    User.SUPERVISOR: ['matcher', 'recon'],      # the requests queue; only the supervisor receives and assigns
    User.MANAGER: ['matcher', 'manager', 'recon'],
    User.ADMIN: ['matcher', 'manager', 'recon', 'users'],
}


def allowed_pages(user):
    """Pages an account may open: its own list when an admin set one, otherwise the role's default."""
    return list(user.pages) if user.pages is not None else list(ROLE_PAGES.get(user.role, []))


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


def has_page(*pages):
    """Staff account that may open at least one of the given pages."""
    class HasPage(SettledAccount):
        message = 'ليست لديك صلاحية لهذه الصفحة.'

        def has_permission(self, request, view):
            u = request.user
            return super().has_permission(request, view) and u.role != User.SUPPLIER and any(p in allowed_pages(u) for p in pages)

    return HasPage


def supplier_or_page(*pages):
    class SupplierOrPage(SettledAccount):
        message = 'ليست لديك صلاحية لهذه الصفحة.'

        def has_permission(self, request, view):
            u = request.user
            if not super().has_permission(request, view):
                return False
            return u.role == User.SUPPLIER or any(p in allowed_pages(u) for p in pages)

    return SupplierOrPage


IsAdmin = has_page('users')                       # the users page
IsStaff = has_page('matcher', 'manager')          # requests
IsMatcherPage = has_page('matcher')
IsManagerPage = has_page('manager')
SupplierOrManagerPage = supplier_or_page('manager')
IsSupplier = roles(User.SUPPLIER)


def can_view_request(user, req):
    return user.role != User.SUPPLIER or req.supplier_id == user.pk


def can_view_complaint(user, c):
    if user.role == User.SUPPLIER:
        return c.supplier_id == user.pk
    return 'manager' in allowed_pages(user)
