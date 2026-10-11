"""
واجهات صندوق واتساب المشترك + استقبال الـ webhook.
"""
import datetime
import hashlib
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
from django.template.loader import render_to_string
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


def _inbox_ctx(request):
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
    qs = qs.annotate(msg_count=Count('messages'))
    page = Paginator(qs.order_by('-awaiting_reply_since', '-last_message_at', '-id') if tab != 'closed'
                     else qs.order_by('-closed_at', '-id'), 50).get_page(request.GET.get('page'))
    ctx = {
        'page_title': 'صندوق واتساب', 'tab': tab, 'tabs': TABS, 'counts': _tab_counts(request.user),
        'page_obj': page, 'q': q, 'late': request.GET.get('late', ''),
        'sla_minutes': SLAConfiguration.current().first_response_minutes,
        'can_manage': services.is_supervisor(request.user),
    }
    ctx['sig'] = _inbox_signature(ctx)
    return ctx


def _inbox_signature(ctx):
    """بصمة ما يظهر في القائمة: تتغير فقط عند تغيّر محادثة أو عدّاد، أو كل دقيقة (لتحديث «منذ ...» و«بلا رد»)."""
    rows = [(c.pk, c.status, c.unread_count, c.msg_count, c.assigned_agent_id,
             int(c.last_message_at.timestamp()) if c.last_message_at else 0, c.is_unanswered_overdue)
            for c in ctx['page_obj']]
    raw = repr((rows, sorted(ctx['counts'].items()), ctx['page_obj'].number, int(timezone.now().timestamp() // 60)))
    return hashlib.md5(raw.encode()).hexdigest()[:16]


@login_required
@view_required
def inbox(request):
    ctx = _inbox_ctx(request)
    template = 'pages/whatsapp/_inbox_list.html' if request.headers.get('HX-Request') else 'pages/whatsapp/inbox.html'
    return _no_store(render(request, template, ctx))


@login_required
@view_required
def inbox_live(request):
    """تحديث لحظي لقائمة الصندوق: لا يُرجع شيئًا إن لم يتغير ما يظهر (sig)، وإلا يُرجع القائمة الجديدة."""
    ctx = _inbox_ctx(request)
    if request.GET.get('sig') == ctx['sig']:
        return _no_store(JsonResponse({'changed': False, 'sig': ctx['sig']}))
    html = render_to_string('pages/whatsapp/_inbox_list.html', ctx, request=request)
    return _no_store(JsonResponse({'changed': True, 'sig': ctx['sig'], 'html': html}))


def _no_store(response):
    response['Cache-Control'] = 'no-store'
    response['Vary'] = 'HX-Request'
    return response


def _conv(pk):
    return get_object_or_404(SupplierConversation.objects.select_related(
        'supplier', 'assigned_agent', 'reconciliation_case', 'typing_agent'), pk=pk)


def _agents():
    """من يصلح لإسناد المحادثات إليه: نفس من تقبله services.assign (مشرفو الدعم ومدير النظام)."""
    from django.contrib.auth import get_user_model
    RT = Role.RoleType
    return get_user_model().objects.filter(
        Q(profile__role__role_type__in=[RT.CS_SUPERVISOR, RT.ADMIN, RT.CFO]) | Q(is_superuser=True),
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
                     and services.is_supervisor(request.user),
        'is_supervisor': services.is_supervisor(request.user), 'agents': _agents() if services.is_supervisor(request.user) else [],
        'typing_name': services.other_typing(conv, request.user),
        'can_create_supplier': can_act and has_role(request.user, *SUPPLIER_MANAGE_ROLES),
        'requests': conv.service_requests.select_related('service_type')[:10],
        'sla_minutes': SLAConfiguration.current().first_response_minutes,
        'cases': ReconciliationCase.objects.filter(supplier=conv.supplier).exclude(
            status__in=['cancelled']).order_by('-created_at')[:30] if conv.supplier_id else [],
    }
    template = 'pages/whatsapp/_thread.html' if request.headers.get('HX-Request') else 'pages/whatsapp/conversation.html'
    return _no_store(render(request, template, ctx))


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


# ── التحديث اللحظي لصفحة المحادثة ─────────────────────────────────────────────
def _render_message(request, conv, msg, can_act):
    return render_to_string('pages/whatsapp/_message.html', {'m': msg, 'conv': conv, 'can_act': can_act}, request=request)


def _parse_known(raw):
    """'12:sent,13:pending' ← حالات الرسائل الصادرة التي يعرضها المتصفح الآن (حد أقصى 60)."""
    out = {}
    for part in (raw or '').split(',')[:60]:
        mid, _, st = part.partition(':')
        if mid.isdigit():
            out[int(mid)] = st
    return out


@login_required
@view_required
def conversation_live(request, pk):
    """يُرجع فقط ما تغيّر منذ آخر استعلام: رسائل جديدة (بعد after) + الصادرة التي تغيّرت حالتها (known) + ميتا المحادثة."""
    conv = _conv(pk)
    can_act = services.can_act(request.user, conv)
    after = request.GET.get('after', '')
    after = int(after) if after.isdigit() else 0
    new = list(conv.messages.select_related('sent_by').filter(pk__gt=after).order_by('pk')[:100])
    if can_act and conv.unread_count and any(m.direction == 'in' for m in new):
        services.mark_read(conv.pk)               # يقرأها الموظف فعلًا الآن: يختفي العدّاد من الصندوق والشريط

    known = _parse_known(request.GET.get('known'))
    updates = []
    if known:
        for m in conv.messages.select_related('sent_by').filter(pk__in=list(known), direction='out'):
            if m.status != known[m.pk]:
                updates.append({'id': m.pk, 'html': _render_message(request, conv, m, can_act)})

    data = {
        'messages': [{'id': m.pk, 'html': _render_message(request, conv, m, can_act)} for m in new],
        'updates': updates,
        'version': conv.version,
        'status': conv.status, 'status_label': conv.get_status_display(),
        'late_minutes': conv.waiting_minutes if conv.is_unanswered_overdue else 0,
        'typing': services.other_typing(conv, request.user) or '',
    }
    return _no_store(JsonResponse(data))


@login_required
@view_required
@require_POST
def send_ajax(request, pk):
    """إرسال الرد بلا إعادة تحميل: يُرجع الرسالة جاهزة للإلحاق فورًا (⏳ ثم تتحدث حالتها حيًّا)."""
    conv = get_object_or_404(SupplierConversation, pk=pk)
    try:
        msg = services.send_reply(conv.pk, request.user, request.POST.get('text', ''))
    except ConversationError as exc:
        return _no_store(JsonResponse({'ok': False, 'error': str(exc)}, status=400))
    msg.refresh_from_db()
    conv = _conv(pk)
    return _no_store(JsonResponse({'ok': True, 'id': msg.pk, 'html': _render_message(request, conv, msg, True)}))
