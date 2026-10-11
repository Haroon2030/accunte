"""
استقبال أحداث واتساب (Evolution webhook) وإعداده. واجهة «صندوق الرسائل الواردة» أُزيلت.
"""
import hmac
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.access import role_required
from apps.core.models import Role

from . import client, services

log = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 1024 * 1024


# ── Webhook ───────────────────────────────────────────────────────────────────
@csrf_exempt
@require_POST
def webhook(request, secret):
    """استقبال أحداث Evolution. الرمز السري في الرابط، ويُقارن بزمن ثابت.
    الأحداث المكررة لا تُنتج رسائل مكررة (قيد فريد على معرّف الرسالة)."""
    expected = settings.WHATSAPP_WEBHOOK_SECRET
    if not settings.WHATSAPP_ENABLED or not expected or not hmac.compare_digest(secret, expected):
        raise Http404
    if len(request.body) > MAX_WEBHOOK_BYTES:
        return HttpResponseBadRequest('too large')
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest('invalid json')
    if not isinstance(payload, dict):
        return HttpResponseBadRequest('invalid payload')
    if payload.get('instance') and payload.get('instance') != settings.EVOLUTION_INSTANCE:
        return JsonResponse({'ok': True, 'processed': 0})     # مثيل آخر: نتجاهله
    try:
        processed = services.handle_event(payload)
    except Exception:
        log.exception('whatsapp webhook failed')
        return JsonResponse({'ok': False}, status=500)         # 500 ليعيد Evolution المحاولة، والمعالجة idempotent
    return JsonResponse({'ok': True, 'processed': processed})


def webhook_url():
    base = settings.WHATSAPP_PUBLIC_BASE_URL
    if not base or not settings.WHATSAPP_WEBHOOK_SECRET:
        return ''
    return base + reverse('whatsapp:webhook', args=[settings.WHATSAPP_WEBHOOK_SECRET])


@login_required
@role_required(Role.RoleType.ADMIN, Role.RoleType.CS_SUPERVISOR, Role.RoleType.CFO)
@require_POST
def setup_webhook(request):
    url = webhook_url()
    if not url:
        return JsonResponse({'ok': False, 'error': 'اضبط WHATSAPP_PUBLIC_BASE_URL و WHATSAPP_WEBHOOK_SECRET في .env'},
                            status=400)
    try:
        client.set_webhook(url)
    except client.WhatsAppError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    return JsonResponse({'ok': True})
