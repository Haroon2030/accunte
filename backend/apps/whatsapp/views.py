"""
شاشة ربط واتساب بالمسح (QR). تتحكم بها الأدوار الإشرافية فقط.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.core.access import has_role, role_required
from apps.core.models import Role

from . import client
from .client import WhatsAppError

MANAGE_ROLES = (Role.RoleType.ADMIN, Role.RoleType.CFO, Role.RoleType.CS_SUPERVISOR)
manage_required = role_required(*MANAGE_ROLES)

STATE_LABELS = {'open': 'متصل', 'connecting': 'جارٍ الاتصال', 'close': 'غير متصل', 'not_found': 'غير مُنشأ'}


def _json_forbidden(request):
    """نقاط JSON لا تُعيد توجيهًا إلى صفحة HTML."""
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'سجّل الدخول أولًا'}, status=401)
    if not has_role(request.user, *MANAGE_ROLES):
        return JsonResponse({'ok': False, 'error': 'ليس لديك صلاحية'}, status=403)
    return None


def _status_payload():
    state = client.connection_state()
    out = {'ok': True, 'state': state, 'label': STATE_LABELS[state]}
    if state == 'open':
        out['account'] = client.instance_info()
    return out


@login_required
@manage_required
def connect_page(request):
    from .inbox_views import webhook_url
    return render(request, 'pages/whatsapp/connect.html', {
        'page_title': 'ربط واتساب',
        'webhook_ready': bool(webhook_url()),
        'enabled': settings.WHATSAPP_ENABLED,
        'configured': client.is_configured(),
        'instance': settings.EVOLUTION_INSTANCE,
    })


@require_GET
def status(request):
    denied = _json_forbidden(request)
    if denied:
        return denied
    try:
        return JsonResponse(_status_payload())
    except WhatsAppError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)


@require_POST
def request_qr(request):
    denied = _json_forbidden(request)
    if denied:
        return denied
    try:
        if client.connection_state() == 'open':
            return JsonResponse({'ok': True, 'state': 'open', 'qr': '', 'label': STATE_LABELS['open']})
        data = client.request_qr()
    except WhatsAppError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    if not data['qr']:
        return JsonResponse({'ok': False, 'error': 'لم يُنتج الخادم رمز QR. أعد المحاولة بعد ثوانٍ'}, status=502)
    return JsonResponse({'ok': True, 'state': 'connecting', 'qr': data['qr'], 'pairing_code': data['pairing_code']})


@require_POST
def disconnect(request):
    denied = _json_forbidden(request)
    if denied:
        return denied
    try:
        client.logout()
    except WhatsAppError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    log_action(AuditLog.Action.OTHER, entity_type='whatsapp.Instance', entity_id=settings.EVOLUTION_INSTANCE,
               entity_repr='فصل ربط واتساب', reason='تسجيل خروج من الرقم المربوط')
    return JsonResponse({'ok': True})


@require_POST
def send_test(request):
    denied = _json_forbidden(request)
    if denied:
        return denied
    number = request.POST.get('number', '')
    text = request.POST.get('text', '').strip() or 'رسالة اختبار من نظام المدفوعات ✅'
    try:
        client.send_text(number, text)
    except WhatsAppError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    to = client.normalize_number(number) or ''
    log_action(AuditLog.Action.OTHER, entity_type='whatsapp.Instance', entity_id=settings.EVOLUTION_INSTANCE,
               entity_repr='رسالة اختبار واتساب', new={'to': to[:-4] + '****' if len(to) > 4 else '****', 'chars': len(text)})
    return JsonResponse({'ok': True})
