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


@register.simple_tag
def nav_dashboard_class(request):
    """Active class for dashboard nav item"""
    try:
        if request.resolver_match.url_name == 'dashboard':
            return 'nav-link-active'
    except Exception:
        pass
    return 'nav-link-idle'


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
