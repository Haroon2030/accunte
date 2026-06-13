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

@register.simple_tag
def active_class(request, prefix):
    """Return active class if current path is under prefix"""
    path = request.path
    normalized = prefix if prefix.endswith('/') else f'{prefix}/'
    if path == normalized.rstrip('/') or path.startswith(normalized):
        return 'bg-primary-50 text-primary-700'
    return 'text-slate-600 hover:bg-slate-100'


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
