from django import template

register = template.Library()

@register.filter
def startswith(value, arg):
    """Check if value starts with arg"""
    if value and arg:
        return str(value).startswith(str(arg))
    return False

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary"""
    if dictionary and key:
        return dictionary.get(key)
    return None

def _path_is_active(request, prefix):
    path = request.path
    normalized = prefix if prefix.endswith('/') else f'{prefix}/'
    return path == normalized.rstrip('/') or path.startswith(normalized)


@register.simple_tag
def active_class(request, prefix):
    """Return nav active/idle class if current path is under prefix"""
    if _path_is_active(request, prefix):
        return 'nav-link-active'
    return 'nav-link-idle'


RECON_OWN_ITEMS = ('/reconciliation/executive', '/reconciliation/distribution')


@register.simple_tag
def nav_sub_active_class(request, prefix):
    """Return sub-nav active/idle class if current path is under prefix"""
    # صفحات لها عنصر قائمة خاص بها لا تُفعِّل عنصر «حالات المطابقة» ذا البادئة الأعم /reconciliation/
    if prefix == '/reconciliation/' and request.path.startswith(RECON_OWN_ITEMS):
        return 'nav-sub-link-idle'
    if _path_is_active(request, prefix):
        return 'nav-sub-link-active'
    return 'nav-sub-link-idle'


@register.simple_tag
def nav_group_open(request, *prefixes):
    """Whether a nav group should start expanded for the current route."""
    for prefix in prefixes:
        if _path_is_active(request, prefix):
            return True
    return False


@register.simple_tag
def nav_group_initial(request):
    """Return the id of the nav group that should start expanded."""
    groups = (
        ('payments', ('/payments/', '/suppliers/')),
        ('reconciliation', ('/reconciliation/', '/proposals/')),
        ('desk', ('/inbox/', '/service-requests/')),
        ('contracts', ('/contracts/', '/space-rentals/', '/items/')),
        ('system', ('/branches/', '/banks/', '/cost-centers/', '/roles/', '/users/', '/audit/', '/whatsapp/')),
    )
    for group_id, prefixes in groups:
        for prefix in prefixes:
            if _path_is_active(request, prefix):
                return group_id
    return ''


@register.simple_tag
def nav_group_class(request, *prefixes):
    """Highlight nav group header when any child route is active"""
    for prefix in prefixes:
        if _path_is_active(request, prefix):
            return 'nav-group-active'
    return 'nav-group-idle'


@register.simple_tag
def is_admin_user(user):
    """Check if user is admin (superuser or admin role)"""
    if getattr(user, 'is_superuser', False):
        return True
    try:
        role = user.profile.role
        return role is not None and role.role_type == 'admin'
    except Exception:
        return False


@register.simple_tag
def user_has_roles(user, roles):
    """roles: أنواع أدوار مفصولة بفواصل، مثال: 'cfo,auditor'. مدير النظام يمر دائمًا."""
    from apps.core.access import has_role
    return has_role(user, *[r.strip() for r in roles.split(',') if r.strip()])
