"""
واجهات صندوق واتساب المشترك + استقبال الـ webhook.
"""
import datetime
import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.core.access import SUPPLIER_MANAGE_ROLES, has_role, role_required
from apps.core.models import Role
from apps.reconciliation.models import ReconciliationCase
from apps.reconciliation.storage import serve_file
from apps.suppliers.models import Supplier

from . import client, services
from .models import ConversationMessage, SLAConfiguration, SupplierConversation
from .services import ConversationError, VIEW_ROLES

log = logging.getLogger(__name__)
S = SupplierConversation.Status
view_required = role_required(*VIEW_ROLES)
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
@role_required(Role.RoleType.ADMIN, Role.RoleType.CS_SUPERVISOR, Role.RoleType.MANAGER, Role.RoleType.CFO)
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


# ── الصندوق ───────────────────────────────────────────────────────────────────
TABS = [
    ('new', 'جديدة'), ('unassigned', 'غير مسندة'), ('mine', 'محادثاتي'), ('pending', 'بانتظار العميل'),
    ('escalated', 'مصعَّدة'), ('closed', 'مغلقة'), ('all', 'الكل'),
]


def _tab_qs(tab, user):
    qs = SupplierConversation.objects.select_related('supplier', 'assigned_agent')
    if tab == 'new':
        return qs.filter(status=S.NEW)
    if tab == 'unassigned':
        return qs.filter(assigned_agent__isnull=True).exclude(status=S.CLOSED)
    if tab == 'mine':
        return qs.filter(assigned_agent=user).exclude(status=S.CLOSED)
    if tab == 'pending':
        return qs.filter(status=S.PENDING)
    if tab == 'escalated':
        return qs.filter(status=S.ESCALATED)
    if tab == 'closed':
        return qs.filter(status=S.CLOSED)
    return qs


def _tab_counts(user):
    base = SupplierConversation.objects
    open_qs = base.exclude(status=S.CLOSED)
    return {
        'new': base.filter(status=S.NEW).count(),
        'unassigned': open_qs.filter(assigned_agent__isnull=True).count(),
        'mine': open_qs.filter(assigned_agent=user).count(),
        'pending': base.filter(status=S.PENDING).count(),
        'escalated': base.filter(status=S.ESCALATED).count(),
        'closed': base.filter(status=S.CLOSED).count(),
        'all': base.count(),
    }


@login_required
@view_required
def inbox(request):
    tab = request.GET.get('tab', 'new')
    if tab not in dict(TABS):
        tab = 'new'
    qs = _tab_qs(tab, request.user)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(contact_number__icontains=q) | Q(display_name__icontains=q)
                       | Q(supplier__name__icontains=q) | Q(supplier__code__icontains=q))
    if request.GET.get('late'):
        limit = SLAConfiguration.current().first_response_minutes
        qs = qs.filter(awaiting_reply_since__lt=timezone.now() - datetime.timedelta(minutes=limit)).exclude(status=S.CLOSED)
    page = Paginator(qs.order_by('-awaiting_reply_since', '-last_message_at', '-id') if tab != 'closed'
                     else qs.order_by('-closed_at', '-id'), 25).get_page(request.GET.get('page'))
    ctx = {
        'page_title': 'صندوق واتساب', 'tab': tab, 'tabs': TABS, 'counts': _tab_counts(request.user),
        'page_obj': page, 'q': q, 'late': request.GET.get('late', ''),
        'sla_minutes': SLAConfiguration.current().first_response_minutes,
        'can_manage': services.is_supervisor(request.user),
    }
    template = 'pages/whatsapp/_inbox_list.html' if request.headers.get('HX-Request') else 'pages/whatsapp/inbox.html'
    return render(request, template, ctx)


def _conv(pk):
    return get_object_or_404(SupplierConversation.objects.select_related(
        'supplier', 'assigned_agent', 'reconciliation_case', 'typing_agent'), pk=pk)


def _agents():
    """من يصلح لإسناد المحادثات إليه: نفس من تقبله services.assign (موظف/مشرف خدمة العملاء، المدير، مدير النظام)."""
    from django.contrib.auth import get_user_model
    RT = Role.RoleType
    return get_user_model().objects.filter(
        Q(profile__role__role_type__in=[RT.CS_AGENT, RT.CS_SUPERVISOR, RT.MANAGER, RT.ADMIN]) | Q(is_superuser=True),
        is_active=True).distinct().order_by('username')


@login_required
@view_required
def conversation(request, pk):
    conv = _conv(pk)
    if request.method == 'GET' and conv.unread_count and services.can_act(request.user, conv):
        services.mark_read(conv.pk)
    msgs = list(conv.messages.select_related('sent_by'))
    can_act = services.can_act(request.user, conv)
    ctx = {
        'page_title': conv.display_name or conv.contact_number, 'conv': conv, 'msgs': msgs, 'can_act': can_act,
        'can_claim': conv.assigned_agent_id is None and conv.status != S.CLOSED
                     and has_role(request.user, Role.RoleType.CS_AGENT, Role.RoleType.CS_SUPERVISOR, Role.RoleType.ADMIN,
                                  Role.RoleType.MANAGER),
        'is_supervisor': services.is_supervisor(request.user), 'agents': _agents() if services.is_supervisor(request.user) else [],
        'typing_name': services.other_typing(conv, request.user),
        'can_create_supplier': can_act and has_role(request.user, *SUPPLIER_MANAGE_ROLES),
        'requests': conv.service_requests.select_related('service_type')[:10],
        'sla_minutes': SLAConfiguration.current().first_response_minutes,
        'cases': ReconciliationCase.objects.filter(supplier=conv.supplier).exclude(
            status__in=['cancelled']).order_by('-created_at')[:30] if conv.supplier_id else [],
    }
    template = 'pages/whatsapp/_thread.html' if request.headers.get('HX-Request') else 'pages/whatsapp/conversation.html'
    return render(request, template, ctx)


def _act(request, pk, fn, success=None):
    conv = get_object_or_404(SupplierConversation, pk=pk)
    try:
        fn(conv)
        if success:
            messages.success(request, success)
    except ConversationError as exc:
        messages.error(request, str(exc))
    return redirect('whatsapp_inbox:conversation', pk=pk)


@login_required
@view_required
@require_POST
def claim(request, pk):
    return _act(request, pk, lambda c: services.claim(c.pk, request.user), 'تم استلام المحادثة')


@login_required
@view_required
@require_POST
def release(request, pk):
    return _act(request, pk, lambda c: services.release(c.pk, request.user), 'أُعيدت المحادثة إلى الصندوق')


@login_required
@view_required
@require_POST
def assign(request, pk):
    from django.contrib.auth import get_user_model
    agent = get_user_model().objects.filter(pk=request.POST.get('agent') or 0).first()
    version = request.POST.get('version')

    def run(c):
        if agent is None:
            raise ConversationError('اختر الموظف')
        services.assign(c.pk, agent, request.user, int(version) if version and version.isdigit() else None)
    return _act(request, pk, run, 'تم إسناد المحادثة')


@login_required
@view_required
@require_POST
def set_status(request, pk):
    return _act(request, pk, lambda c: services.set_status(
        c.pk, request.user, request.POST.get('to', ''), request.POST.get('reason', '')), 'تم تحديث حالة المحادثة')


@login_required
@view_required
@require_POST
def send(request, pk):
    conv = get_object_or_404(SupplierConversation, pk=pk)
    try:
        services.send_reply(conv.pk, request.user, request.POST.get('text', ''))
    except ConversationError as exc:
        messages.error(request, str(exc))
    return redirect('whatsapp_inbox:conversation', pk=pk)


@login_required
@view_required
@require_POST
def resend(request, pk, msg_pk):
    msg = get_object_or_404(ConversationMessage, pk=msg_pk, conversation_id=pk)
    try:
        services.resend(msg.pk, request.user)
    except ConversationError as exc:
        messages.error(request, str(exc))
    return redirect('whatsapp_inbox:conversation', pk=pk)


@login_required
@view_required
@require_POST
def typing(request, pk):
    conv = get_object_or_404(SupplierConversation, pk=pk)
    if services.can_act(request.user, conv):
        services.ping_typing(conv.pk, request.user)
    return HttpResponse(status=204)


@login_required
@view_required
@require_POST
def link_supplier(request, pk):
    """يربط المحادثة بمورد (بمعرّفه من البحث، أو بالكود)، أو يفكّ الربط إن لم يُرسَل شيء."""
    sid = request.POST.get('supplier', '').strip()
    code = request.POST.get('supplier_code', '').strip()
    supplier = None
    if sid.isdigit():
        supplier = Supplier.objects.filter(pk=sid).first()
    elif code:
        supplier = Supplier.objects.filter(code=code).first()
    if (sid or code) and supplier is None:
        messages.error(request, 'لا يوجد مورد مطابق. ابحث بالاسم واختر من القائمة')
        return redirect('whatsapp_inbox:conversation', pk=pk)
    return _act(request, pk, lambda c: services.link_supplier(c.pk, request.user, supplier),
                'تم ربط المورد' if supplier else 'تم فك ربط المورد')


@login_required
@view_required
@require_POST
def create_supplier(request, pk):
    p = request.POST
    return _act(request, pk, lambda c: services.create_supplier_from_conversation(
        c.pk, request.user, p.get('name', ''), p.get('code', ''), p.get('tax_number', '')),
        'تم إنشاء المورد وربطه بالمحادثة')


@login_required
@view_required
@require_POST
def link_case(request, pk):
    case_id = request.POST.get('case') or ''
    case = ReconciliationCase.objects.filter(pk=case_id).first() if case_id.isdigit() else None
    return _act(request, pk, lambda c: services.link_case(c.pk, request.user, case), 'تم تحديث ربط حالة المطابقة')


# ── ملفات الرسائل الواردة ─────────────────────────────────────────────────────
# الملف قادم من جهة خارجية: يُقدَّم دائمًا كمرفق، والاستثناء معاينة الصور والصوت المعروفة فقط (لا SVG ولا HTML)
INLINE_MIMETYPES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/gif',
    'audio/ogg', 'audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/webm', 'audio/x-m4a',
}


@login_required
@view_required
def media_download(request, pk, msg_pk):
    msg = get_object_or_404(ConversationMessage.objects.exclude(kind=ConversationMessage.Kind.TEXT),
                            pk=msg_pk, conversation_id=pk)
    if not msg.media_file:
        # لم يُجلب عند الاستقبال (أو فشل): نحاول الآن عند الفتح
        try:
            services.fetch_and_store_media(msg.pk)
            msg.refresh_from_db()
        except client.WhatsAppError as exc:
            messages.error(request, f'تعذر جلب الملف من واتساب: {exc}')
            return redirect('whatsapp_inbox:conversation', pk=pk)
    name = msg.media_name or msg.media_file.name.rsplit('/', 1)[-1]
    if request.GET.get('inline') == '1' and msg.media_mimetype in INLINE_MIMETYPES:
        try:
            response = FileResponse(msg.media_file.open('rb'), content_type=msg.media_mimetype,
                                    as_attachment=False, filename=name)
        except (FileNotFoundError, OSError):
            raise Http404
    else:
        response = serve_file(msg.media_file, name)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['Cache-Control'] = 'private, no-store'
    log_action(AuditLog.Action.EXPORT, msg, entity_type='whatsapp.Message',
               entity_repr=f'فتح ملف واتساب {name}'[:300], new={'type': msg.kind, 'size': msg.media_size})
    return response
