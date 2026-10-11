"""
واجهات طلبات الخدمة وإدارة أنواعها والمواعيد.
الرؤية على مستوى الصف عبر visible_requests (غير المرئي يعطي 404).
"""
import datetime
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.core.dates import safe_parse_datetime as parse_datetime
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.reconciliation.storage import serve_file
from apps.audit.services import log_action
from apps.core.access import get_role_type, has_role, role_required
from apps.core.models import Role
from apps.reconciliation.services import file_sha256, validate_upload
from apps.reconciliation.workflow import TransitionError
from apps.suppliers.models import Supplier
from apps.whatsapp.models import SupplierConversation

from . import services
from .models import Appointment, ServiceRequest, ServiceRequestDocument, ServiceType
from .services import MANAGE_TYPES_ROLES, RequestError, VIEW_ROLES

view_required = role_required(*VIEW_ROLES)
types_required = role_required(*MANAGE_TYPES_ROLES)
S = ServiceRequest.Status


# ── القائمة ───────────────────────────────────────────────────────────────────
TABS = [('open', 'المفتوحة'), ('mine', 'طلباتي'), ('unassigned', 'غير مسندة'), ('overdue', 'المتأخرة'),
        ('escalated', 'المصعَّدة'), ('done', 'المنتهية'), ('all', 'الكل')]


# ── الإنشاء ───────────────────────────────────────────────────────────────────


# ── التفاصيل والإجراءات ──────────────────────────────────────────────────────


# ── المستندات ────────────────────────────────────────────────────────────────


# ── المواعيد ─────────────────────────────────────────────────────────────────


# ── إدارة الأنواع ────────────────────────────────────────────────────────────
@login_required
@types_required
def type_list(request):
    return render(request, 'pages/servicedesk/types.html', {
        'page_title': 'أنواع الخدمات', 'types': ServiceType.objects.all()})


# أدوار الموظفين فقط: حساب المورد (بوابة) لا يُسند ولا يُستلم ولا يعالج
STAFF_ROLE_CHOICES = [(v, label) for v, label in Role.RoleType.choices if v != Role.RoleType.SUPPLIER]


def _roles_from_post(post, name):
    valid = {v for v, _ in STAFF_ROLE_CHOICES}
    return [r for r in post.getlist(name) if r in valid]


@login_required
@types_required
def type_edit(request, pk=None):
    stype = get_object_or_404(ServiceType, pk=pk) if pk else None
    errors = []
    if request.method == 'POST':
        p = request.POST
        try:
            code = p.get('code', '').strip()
            name = p.get('name', '').strip()
            if not code or not name:
                raise RequestError('الرمز والاسم مطلوبان')
            try:
                schema = services.validate_schema(json.loads(p.get('field_schema') or '[]'))
            except ValueError:
                raise RequestError('تعريف الحقول غير صالح')
            docs = [d.strip() for d in p.get('required_documents', '').splitlines() if d.strip()][:20]
            sla = p.get('sla_hours', '24')
            if not sla.isdigit() or not 1 <= int(sla) <= 24 * 90:
                raise RequestError('مهلة الإنجاز يجب أن تكون بين 1 و2160 ساعة')
            valid_roles = {v for v, _ in STAFF_ROLE_CHOICES}
            if p.get('destination_role') not in valid_roles or p.get('escalation_role') not in valid_roles:
                raise RequestError('اختر الجهة المستلمة وجهة التصعيد')
            if ServiceType.objects.filter(code=code).exclude(pk=stype.pk if stype else None).exists():
                raise RequestError('الرمز مستخدم لنوع آخر')
            obj = stype or ServiceType()
            before = {k: getattr(obj, k) for k in ('code', 'name', 'sla_hours', 'destination_role')} if stype else None
            obj.code, obj.name = code, name
            obj.description = p.get('description', '').strip()
            obj.destination_role, obj.escalation_role = p['destination_role'], p['escalation_role']
            obj.sla_hours = int(sla)
            obj.field_schema, obj.required_documents = schema, docs
            obj.create_roles = _roles_from_post(p, 'create_roles')
            obj.handle_roles = _roles_from_post(p, 'handle_roles')
            obj.spawns_reconciliation = bool(p.get('spawns_reconciliation'))
            obj.whatsapp_menu = bool(p.get('whatsapp_menu'))
            obj.portal_menu = bool(p.get('portal_menu'))
            obj.confidential = bool(p.get('confidential'))
            obj.is_active = bool(p.get('is_active'))
            obj.sort_order = int(p['sort_order']) if p.get('sort_order', '').isdigit() else 100
            obj.save()
        except RequestError as exc:
            errors.append(str(exc))
        except IntegrityError:
            errors.append('الرمز مستخدم لنوع آخر')
        else:
            log_action(AuditLog.Action.UPDATE if stype else AuditLog.Action.CREATE, obj,
                       entity_type='servicedesk.ServiceType', previous=before,
                       new={'code': obj.code, 'name': obj.name, 'sla_hours': obj.sla_hours,
                            'destination_role': obj.destination_role})
            messages.success(request, 'تم حفظ النوع')
            return redirect('servicedesk:types')
    return render(request, 'pages/servicedesk/type_form.html', {
        'page_title': 'تعديل نوع خدمة' if stype else 'نوع خدمة جديد', 't': stype, 'errors': errors,
        'roles': STAFF_ROLE_CHOICES, 'field_types': [('text', 'نص'), ('textarea', 'نص طويل'), ('number', 'رقم'),
                                                        ('date', 'تاريخ'), ('select', 'قائمة')],
        'schema_json': json.dumps(stype.field_schema if stype else [], ensure_ascii=False).replace('<', '\\u003c'),
        'create_roles': stype.effective_create_roles() if stype else [],
        'handle_roles': (stype.handle_roles or []) if stype else [],
        'docs_text': '\n'.join(stype.required_documents or []) if stype else '',
    })


# ── شاشة استلام الطلبات: استلام ← إرسال للمطابق ← جاري المعالجة ← اكتمال المعالجة ──────────────────
INTAKE_STAGES = ('استلام الطلب', 'إرسال للمطابق', 'جاري المعالجة', 'اكتمال المعالجة')
INTAKE_TABS = [('open', 'المفتوحة'), ('new', 'بانتظار الاستلام'), ('mine', 'عندي'), ('done', 'المنتهية'), ('all', 'الكل')]


def intake_stage(req):
    """المرحلة الحالية 1..4، أو 5 إن اكتمل الطلب، أو 0 إن أُلغي. تُشتق من الحالة والمسؤول فلا حقول جديدة."""
    if req.status == S.CANCELLED:
        return 0
    if req.status in (S.RESOLVED, S.CLOSED):
        return 5
    if req.status in (S.IN_PROGRESS, S.WAITING_VENDOR, S.ESCALATED):
        return 3
    if req.assigned_to_id is None:
        return 1
    return 3 if services.can_receive_assignment(req.assigned_to) else 2


def _person(user, fallback=''):
    return (user.get_full_name() or user.username) if user else fallback


def _step_actors(req):
    """منفّذ كل خطوة ووقتها: {رقم الخطوة: (النص, الوقت)}. من سجل التدقيق وسجل الحالات الموجودين أصلًا."""
    from django.contrib.auth import get_user_model
    from apps.audit.models import AuditLog
    logs = list(AuditLog.objects.filter(entity_type='servicedesk.ServiceRequest', entity_id=str(req.pk),
                                        action=AuditLog.Action.UPDATE).select_related('actor').order_by('created_at', 'id'))

    def actor(log):
        return _person(log.actor, log.actor_username or 'النظام')

    out = {}
    recv = next((x for x in logs if x.reason == 'استلام الطلب'), None)
    if recv:
        out[1] = (actor(recv), recv.created_at)
    sent = next((x for x in reversed(logs) if x.reason == 'إسناد الطلب'), None)
    if sent:
        target_pk = (sent.new_state or {}).get('assigned_to')
        target = get_user_model().objects.filter(pk=target_pk).first() if target_pk else None
        out[2] = (f'{actor(sent)} ← {_person(target, "")}'.rstrip(' ←'), sent.created_at)
    hist = list(req.history.select_related('changed_by').order_by('created_at', 'id'))
    started = next((h for h in hist if h.to_status == S.IN_PROGRESS), None)
    if started:
        out[3] = (_person(started.changed_by, 'النظام'), started.created_at)
    elif req.assigned_to_id and services.can_receive_assignment(req.assigned_to):
        out[3] = (f'بانتظار {_person(req.assigned_to)}', None)
    finished = next((h for h in reversed(hist) if h.to_status == S.RESOLVED), None)
    if finished:
        out[4] = (_person(finished.changed_by, 'النظام'), finished.created_at)
    return out


def intake_steps(req):
    cur = intake_stage(req)
    actors = _step_actors(req)
    steps = []
    for i, label in enumerate(INTAKE_STAGES, start=1):
        if cur == 0:
            state = 'upcoming'
        elif cur == 5 or i < cur:
            state = 'done'
        elif i == cur:
            state = 'current'
        else:
            state = 'upcoming'
        who, at = actors.get(i, ('', None)) if state != 'upcoming' else ('', None)
        steps.append({'n': i, 'label': label, 'state': state, 'who': who, 'at': at})
    return steps


def _history_rows(req):
    labels = dict(S.choices)
    rows = []
    for h in req.history.select_related('changed_by').order_by('created_at', 'id'):
        who = (h.changed_by.get_full_name() or h.changed_by.username) if h.changed_by else 'النظام'
        rows.append({'from': labels.get(h.from_status, ''), 'to': labels.get(h.to_status, h.to_status),
                     'who': who, 'at': h.created_at, 'reason': h.reason})
    return rows


def _intake_get(request, pk):
    return get_object_or_404(services.visible_requests(request.user), pk=pk)


def _intake_back(pk):
    return redirect('servicedesk:detail', pk=pk)


@login_required
@view_required
def request_list(request):
    tab = request.GET.get('tab', 'open')
    if tab not in dict(INTAKE_TABS):
        tab = 'open'
    qs = services.visible_requests(request.user)
    if tab == 'open':
        qs = qs.filter(status__in=ServiceRequest.OPEN)
    elif tab == 'new':
        qs = qs.filter(status=S.NEW, assigned_to__isnull=True)
    elif tab == 'mine':
        qs = qs.filter(assigned_to=request.user, status__in=ServiceRequest.OPEN)
    elif tab == 'done':
        qs = qs.filter(status__in=(S.RESOLVED, S.CLOSED, S.CANCELLED))
    page = Paginator(qs.order_by('-created_at', '-id'), 30).get_page(request.GET.get('page'))
    for r in page:
        r.stage = intake_stage(r)
        r.stage_label = 'مكتمل' if r.stage == 5 else ('ملغى' if r.stage == 0 else INTAKE_STAGES[r.stage - 1])
    return render(request, 'pages/servicedesk/intake_list.html', {
        'page_title': 'استلام الطلبات', 'page_obj': page, 'tab': tab, 'tabs': INTAKE_TABS,
    })


@login_required
@view_required
def request_detail(request, pk):
    req = _intake_get(request, pk)
    stage = intake_stage(req)
    user = request.user
    supervisor = services.is_supervisor(user)
    allowed = services.allowed_transitions(user, req)
    return render(request, 'pages/servicedesk/intake_detail.html', {
        'page_title': req.reference, 'r': req, 'steps': intake_steps(req), 'stage': stage,
        'fields': services.labelled_data(req), 'history': _history_rows(req),
        'can_receive': stage == 1 and supervisor and not req.is_terminal,
        'can_send': stage in (1, 2, 3) and supervisor and req.status == S.NEW,
        'can_start': stage == 3 and req.status == S.NEW and S.IN_PROGRESS in allowed,
        'can_complete': req.status in (S.IN_PROGRESS, S.WAITING_VENDOR, S.ESCALATED) and S.RESOLVED in allowed,
        'accountants': services.assignable_users() if supervisor else [],
        'documents': req.documents.all(),
        'back_url': 'servicedesk:my_tasks' if get_role_type(user) == Role.RoleType.ACCOUNTANT else 'servicedesk:list',
    })


def _intake_run(request, pk, fn, ok):
    req = _intake_get(request, pk)
    try:
        fn(req)
        messages.success(request, ok)
    except RequestError as exc:
        messages.error(request, str(exc))
    return _intake_back(req.pk)


@login_required
@view_required
@require_POST
def request_receive(request, pk):
    return _intake_run(request, pk, lambda r: services.claim(r.pk, request.user), 'تم استلام الطلب')


@login_required
@view_required
@require_POST
def request_send(request, pk):
    def run(req):
        agent = next((u for u in services.assignable_users() if str(u.pk) == request.POST.get('accountant')), None)
        if agent is None:
            raise RequestError('اختر المطابق الذي يُرسل إليه الطلب')
        services.assign(req.pk, agent, request.user)
    return _intake_run(request, pk, run, 'تم إرسال الطلب إلى المطابق')


@login_required
@view_required
@require_POST
def request_start(request, pk):
    return _intake_run(request, pk, lambda r: services.transition(r.pk, S.IN_PROGRESS, request.user), 'بدأت معالجة الطلب')


@login_required
@view_required
@require_POST
def request_complete(request, pk):
    return _intake_run(request, pk, lambda r: services.transition(
        r.pk, S.RESOLVED, request.user, resolution_note=request.POST.get('resolution_note', '')), 'اكتملت معالجة الطلب')


# ── شاشة مهام المطابق: ما أُسند إليه، مقسَّمًا بحسب المرحلة ─────────────────────────────────────────
def _due_info(req, now):
    """نص الموعد وحالته: late | soon | ok | none."""
    from apps.reconciliation.tracking import fmt_duration
    if not req.due_at or req.status not in ServiceRequest.OPEN:
        return '', 'none'
    delta = req.due_at - now
    if delta.total_seconds() < 0:
        return f'متأخر {fmt_duration(-delta)}', 'late'
    return f'بعد {fmt_duration(delta)}', 'soon' if delta <= datetime.timedelta(hours=6) else 'ok'


@login_required
@view_required
def my_tasks(request):
    now = timezone.now()
    mine = services.visible_requests(request.user).filter(assigned_to=request.user)
    new = list(mine.filter(status=S.NEW).order_by('due_at', '-created_at'))
    working = list(mine.filter(status__in=(S.IN_PROGRESS, S.WAITING_VENDOR, S.ESCALATED)).order_by('due_at', '-created_at'))
    done = list(mine.filter(status__in=(S.RESOLVED, S.CLOSED), resolved_at__gte=now - datetime.timedelta(days=7))
                .order_by('-resolved_at')[:10])
    for group in (new, working, done):
        for r in group:
            r.due_text, r.due_state = _due_info(r, now)
    counts = {
        'new': len(new), 'working': len(working), 'done': len(done),
        'late': sum(1 for r in new + working if r.due_state == 'late'),
    }
    ctx = {'page_title': 'مهامي', 'new': new, 'working': working, 'done': done, 'counts': counts}
    template = 'pages/servicedesk/_tasks_board.html' if request.GET.get('partial') else 'pages/servicedesk/my_tasks.html'
    resp = render(request, template, ctx)
    resp['Cache-Control'] = 'no-store'
    return resp
