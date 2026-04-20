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
def active_class(request, pattern):
    """Return active class if URL matches pattern"""
    import re
    if re.search(pattern, request.path):
        return 'bg-primary-50 text-primary-700'
    return 'text-slate-600 hover:bg-slate-100'
