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
def is_admin_user(user):
    """Check if user is admin (superuser or admin role)"""
    if getattr(user, 'is_superuser', False):
        return True
    try:
        role = user.profile.role
        return role is not None and role.role_type in ('admin', 'cfo')
    except Exception:
        return False


@register.simple_tag
def user_has_roles(user, roles):
    """roles: أنواع أدوار مفصولة بفواصل، مثال: 'cfo,auditor'. مدير النظام يمر دائمًا."""
    from apps.core.access import has_role
    return has_role(user, *[r.strip() for r in roles.split(',') if r.strip()])
