"""
خدمات التدقيق: تسجيل الإجراءات وتنقية البيانات الحساسة.
"""
import contextvars
import datetime
import decimal
import uuid

from .models import AuditLog

_current_request = contextvars.ContextVar('audit_request', default=None)

SENSITIVE_MARKERS = ('password', 'secret', 'token', 'api_key', 'apikey', 'authorization', 'csrf', 'signature')
MAX_VALUE_LEN = 2000


def set_request(request):
    return _current_request.set(request)


def reset_request(token):
    _current_request.reset(token)


def _is_sensitive(key):
    k = str(key).lower()
    return any(m in k for m in SENSITIVE_MARKERS)


def sanitize(value, _key=None):
    """يحوّل القيمة إلى JSON آمن ويحجب الحقول الحساسة."""
    if _key is not None and _is_sensitive(_key):
        return '***'
    if isinstance(value, dict):
        return {str(k): sanitize(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize(v) for v in value]
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_VALUE_LEN]


def snapshot(instance, fields=None):
    """لقطة من حقول النموذج (القيم المباشرة فقط) لمقارنة قبل/بعد."""
    data = {}
    for f in instance._meta.concrete_fields:
        if fields and f.name not in fields:
            continue
        if getattr(f, 'auto_now', False) or getattr(f, 'auto_now_add', False):
            continue   # حقول تلقائية تُحدَّث في كل حفظ فتُلوّث المقارنة
        data[f.name] = getattr(instance, f.attname)
    return sanitize(data)


def diff(previous, new):
    """يُرجع (قبل, بعد) للحقول التي تغيرت فقط."""
    prev_out, new_out = {}, {}
    for k in set(previous) | set(new):
        if previous.get(k) != new.get(k):
            prev_out[k] = previous.get(k)
            new_out[k] = new.get(k)
    return prev_out, new_out


def _client_ip(request):
    # لا نثق بـ X-Forwarded-For إلا إذا فُعّل صراحةً (خادم خلف وكيل موثوق)
    from django.conf import settings
    if getattr(settings, 'AUDIT_TRUST_FORWARDED', False):
        fwd = request.META.get('HTTP_X_FORWARDED_FOR')
        if fwd:
            return fwd.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def log_action(action, entity=None, *, entity_type=None, entity_id=None, entity_repr='',
               previous=None, new=None, reason='', actor=None, request=None):
    """سجّل إجراءً واحدًا، ويأخذ المستخدم وIP من الطلب الحالي تلقائيًا."""
    request = request or _current_request.get()
    if actor is None and request is not None:
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            actor = user
    if entity is not None:
        entity_type = entity_type or entity._meta.label
        entity_id = entity_id if entity_id is not None else entity.pk
        entity_repr = entity_repr or str(entity)
    ip = ua = path = None
    if request is not None:
        ip = _client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')[:300]
        path = request.path[:300]
    has_actor = actor is not None and getattr(actor, 'pk', None)
    return AuditLog.objects.create(
        actor=actor if has_actor else None,
        actor_username=actor.get_username()[:150] if has_actor else '',
        action=action,
        entity_type=entity_type or '',
        entity_id=str(entity_id) if entity_id is not None else '',
        entity_repr=str(entity_repr)[:300],
        previous_state=sanitize(previous) if previous is not None else None,
        new_state=sanitize(new) if new is not None else None,
        reason=reason or '',
        ip_address=ip,
        user_agent=ua or '',
        request_path=path or '',
    )
