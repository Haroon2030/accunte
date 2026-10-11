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
from apps.core.access import has_role, role_required
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


def _get(request, pk):
    return get_object_or_404(services.visible_requests(request.user), pk=pk)


def _back(pk, tab=''):
    return redirect(f'/service-requests/{pk}/' + (f'?tab={tab}' if tab else ''))


# ── القائمة ───────────────────────────────────────────────────────────────────
TABS = [('open', 'المفتوحة'), ('mine', 'طلباتي'), ('unassigned', 'غير مسندة'), ('overdue', 'المتأخرة'),
        ('escalated', 'المصعَّدة'), ('done', 'المنتهية'), ('all', 'الكل')]


def filtered(request):
    qs = services.visible_requests(request.user)
    g = request.GET
    tab = g.get('tab', 'open')
    if tab not in dict(TABS):
        tab = 'open'
    now = timezone.now()
    if tab == 'open':
        qs = qs.filter(status__in=ServiceRequest.OPEN)
    elif tab == 'mine':
        qs = qs.filter(assigned_to=request.user).exclude(status__in=ServiceRequest.TERMINAL)
    elif tab == 'unassigned':
        qs = qs.filter(assigned_to__isnull=True, status__in=ServiceRequest.OPEN)
    elif tab == 'overdue':
        qs = qs.filter(due_at__lt=now, status__in=ServiceRequest.OPEN)
    elif tab == 'escalated':
        qs = qs.filter(status=S.ESCALATED)
    elif tab == 'done':
        qs = qs.filter(status__in=(S.RESOLVED, S.CLOSED, S.CANCELLED))
    f = {k: g.get(k, '').strip() for k in ('q', 'type', 'priority', 'supplier')}
    if f['q']:
        from django.db.models import Q
        qs = qs.filter(Q(reference__icontains=f['q']) | Q(subject__icontains=f['q'])
                       | Q(supplier__name__icontains=f['q']) | Q(supplier__code__icontains=f['q']))
    if f['type'].isdigit():
        qs = qs.filter(service_type_id=f['type'])
    if f['priority'] in ServiceRequest.Priority.values:
        qs = qs.filter(priority=f['priority'])
    if f['supplier'].isdigit():
        qs = qs.filter(supplier_id=f['supplier'])
    return qs, tab, f


@login_required
@view_required
def request_list(request):
    qs, tab, f = filtered(request)
    page = Paginator(qs.order_by('due_at', '-created_at'), 20).get_page(request.GET.get('page'))
    return render(request, 'pages/servicedesk/list.html', {
        'page_title': 'طلبات الخدمة', 'page_obj': page, 'tab': tab, 'tabs': TABS, 'f': f,
        'types': ServiceType.objects.filter(is_active=True),
        'priorities': ServiceRequest.Priority.choices,
        'can_create': any(services.can_create(request.user, t) for t in ServiceType.objects.filter(is_active=True)),
        'can_manage_types': has_role(request.user, *MANAGE_TYPES_ROLES),
        'assignable': services.assignable_users() if services.is_supervisor(request.user) else [],
        'qs_extra': '&'.join(f'{k}={v}' for k, v in {**f, 'tab': tab}.items() if v),
    })


# ── الإنشاء ───────────────────────────────────────────────────────────────────
@login_required
@view_required
def request_create(request):
    types = [t for t in ServiceType.objects.filter(is_active=True) if services.can_create(request.user, t)]
    errors = []
    assignable = services.assignable_users() if services.is_supervisor(request.user) else []
    p = request.POST if request.method == 'POST' else request.GET
    stype = next((t for t in types if str(t.pk) == (p.get('type') or '')), None)
    conversation = None
    if p.get('conversation', '').isdigit():
        conversation = SupplierConversation.objects.select_related('supplier').filter(pk=p['conversation']).first()
    supplier = Supplier.objects.filter(pk=p['supplier']).first() if p.get('supplier', '').isdigit() else None
    if supplier is None and conversation is not None:
        supplier = conversation.supplier

    if request.method == 'POST' and p.get('step') == 'create':
        try:
            if stype is None:
                raise RequestError('اختر نوع الطلب')
            if supplier is None:
                raise RequestError('اختر المورد')
            assign_to = None
            if p.get('assign_to', '').isdigit():
                assign_to = next((u for u in assignable if u.pk == int(p['assign_to'])), None)
                if assign_to is None:
                    raise RequestError('اختر موظفًا من القائمة')
            req = services.create_request(
                request.user, stype, supplier, p.get('subject', ''), p.get('details', ''),
                p.get('priority', 'normal'), getter=p.get, conversation=conversation, assign_to=assign_to)
        except RequestError as exc:
            errors.append(str(exc))
        else:
            messages.success(request, f'تم إنشاء الطلب {req.reference}')
            return redirect('servicedesk:detail', pk=req.pk)
    return render(request, 'pages/servicedesk/form.html', {
        'page_title': 'طلب خدمة جديد', 'types': types, 'stype': stype, 'errors': errors, 'post': p,
        'supplier': supplier, 'conversation': conversation, 'priorities': ServiceRequest.Priority.choices,
        'assignable': assignable, 'schema': stype.field_schema if stype else [],
    })


# ── التفاصيل والإجراءات ──────────────────────────────────────────────────────
@login_required
@view_required
def request_detail(request, pk):
    req = _get(request, pk)
    docs = list(req.documents.select_related('uploaded_by'))
    have = {d.label for d in docs}
    return render(request, 'pages/servicedesk/detail.html', {
        'page_title': req.reference, 'r': req, 'data': services.labelled_data(req), 'docs': docs,
        'required_docs': [(lbl, lbl in have) for lbl in (req.service_type.required_documents or [])],
        'transitions': [(v, S(v).label) for v in services.allowed_transitions(request.user, req)],
        'history': req.history.select_related('changed_by'),
        'appointments': req.appointments.select_related('assigned_to'),
        'can_claim': req.assigned_to_id is None and req.status in ServiceRequest.OPEN
                     and services.can_handle(request.user, req.service_type),
        'is_supervisor': services.is_supervisor(request.user),
        'can_docs': services.can_edit_documents(request.user, req),
        'agents': services.assignable_users() if services.is_supervisor(request.user) else [],
        'tab': request.GET.get('tab', 'info'),
        'appt_statuses': Appointment.Status.choices,
    })


def _run(request, pk, fn, ok, tab=''):
    try:
        fn()
        if ok:
            messages.success(request, ok)
    except RequestError as exc:
        messages.error(request, str(exc))
    return _back(pk, tab)


@login_required
@view_required
@require_POST
def request_claim(request, pk):
    req = _get(request, pk)
    return _run(request, pk, lambda: services.claim(req.pk, request.user), 'تم استلام الطلب')


@login_required
@view_required
@require_POST
def request_assign(request, pk):
    from django.contrib.auth import get_user_model
    req = _get(request, pk)
    agent = get_user_model().objects.filter(pk=request.POST.get('agent') or 0).first()

    def run():
        if agent is None:
            raise RequestError('اختر الموظف')
        services.assign(req.pk, agent, request.user)
    nxt = request.POST.get('next', '')
    if nxt.startswith('/service-requests/') and not nxt.startswith('//'):       # عودة آمنة إلى القائمة فقط
        try:
            run()
            messages.success(request, 'تم إسناد الطلب')
        except RequestError as exc:
            messages.error(request, str(exc))
        return redirect(nxt)
    return _run(request, pk, run, 'تم إسناد الطلب')


@login_required
@view_required
@require_POST
def request_transition(request, pk):
    req = _get(request, pk)
    return _run(request, pk, lambda: services.transition(
        req.pk, request.POST.get('to', ''), request.user, request.POST.get('reason', ''),
        request.POST.get('resolution_note', '')), 'تم تحديث حالة الطلب')


# ── المستندات ────────────────────────────────────────────────────────────────
@login_required
@view_required
@require_POST
def document_upload(request, pk):
    req = _get(request, pk)
    try:
        if not services.can_edit_documents(request.user, req):
            raise RequestError('لا يمكنك رفع مستندات لهذا الطلب')
        f = request.FILES.get('file')
        if not f:
            raise RequestError('اختر ملفًا')
        validate_upload(f)
        label = request.POST.get('label', '').strip()[:120]
        shared = bool(request.POST.get('share')) and req.source == ServiceRequest.Source.PORTAL
        doc = ServiceRequestDocument(request=req, label=label, original_name=f.name[:255], size=f.size,
                                     uploaded_by=request.user, sha256=file_sha256(f), shared_with_supplier=shared)
        doc.file.save(f.name, f, save=True)
        log_action(AuditLog.Action.CREATE, doc, entity_type='servicedesk.Document',
                   entity_repr=f'{req.reference}: {doc.original_name}',
                   new={'label': label, 'name': doc.original_name, 'sha256': doc.sha256, 'shared': shared})
        messages.success(request, 'تم رفع المستند')
    except (RequestError, TransitionError) as exc:
        messages.error(request, str(exc))
    return _back(pk, 'documents')


@login_required
@view_required
def document_download(request, pk, doc_pk):
    req = _get(request, pk)
    doc = get_object_or_404(ServiceRequestDocument, pk=doc_pk, request=req)
    response = serve_file(doc.file, doc.original_name)      # R2 أو القرص، بعد فحص الصلاحية أعلاه
    log_action(AuditLog.Action.EXPORT, doc, entity_type='servicedesk.Document', entity_repr=f'تنزيل {doc.original_name}')
    return response


@login_required
@view_required
@require_POST
def document_delete(request, pk, doc_pk):
    req = _get(request, pk)
    doc = get_object_or_404(ServiceRequestDocument, pk=doc_pk, request=req)
    if not services.can_edit_documents(request.user, req):
        messages.error(request, 'لا يمكنك حذف مستندات هذا الطلب')
    else:
        log_action(AuditLog.Action.DELETE, doc, entity_type='servicedesk.Document', previous={'name': doc.original_name})
        doc.file.delete(save=False)
        doc.delete()
    return _back(pk, 'documents')


# ── المواعيد ─────────────────────────────────────────────────────────────────
@login_required
@view_required
@require_POST
def appointment_add(request, pk):
    req = _get(request, pk)
    try:
        if not services.can_edit_documents(request.user, req):
            raise RequestError('لا يمكنك إضافة مواعيد لهذا الطلب')
        when = parse_datetime(request.POST.get('scheduled_at', ''))
        if when is None:
            raise RequestError('موعد غير صالح')
        if timezone.is_naive(when):
            when = timezone.make_aware(when)
        title = request.POST.get('title', '').strip() or req.subject
        minutes = request.POST.get('duration_minutes', '30')
        appt = Appointment.objects.create(
            supplier=req.supplier, request=req, title=title[:200], scheduled_at=when,
            duration_minutes=int(minutes) if minutes.isdigit() and 5 <= int(minutes) <= 480 else 30,
            location=request.POST.get('location', '').strip()[:200], notes=request.POST.get('notes', '').strip(),
            assigned_to=req.assigned_to or request.user, created_by=request.user)
        log_action(AuditLog.Action.CREATE, appt, entity_type='servicedesk.Appointment',
                   new={'request': req.pk, 'scheduled_at': when, 'title': appt.title})
        messages.success(request, 'تمت جدولة الموعد')
    except RequestError as exc:
        messages.error(request, str(exc))
    return _back(pk, 'appointments')


@login_required
@view_required
@require_POST
def appointment_status(request, pk, appt_pk):
    req = _get(request, pk)
    appt = get_object_or_404(Appointment, pk=appt_pk, request=req)
    to = request.POST.get('to')
    if to not in Appointment.Status.values or not services.can_edit_documents(request.user, req):
        messages.error(request, 'إجراء غير مسموح')
    else:
        old = appt.status
        appt.status = to
        appt.save(update_fields=['status'])
        log_action(AuditLog.Action.STATUS_CHANGE, appt, entity_type='servicedesk.Appointment',
                   previous={'status': old}, new={'status': to})
    return _back(pk, 'appointments')


@login_required
@view_required
def appointment_list(request):
    qs = Appointment.objects.select_related('supplier', 'request', 'assigned_to')
    if not has_role(request.user, *services.OVERSIGHT_ROLES):
        qs = qs.filter(assigned_to=request.user)
    show_all = request.GET.get('all')
    if not show_all:
        qs = qs.filter(scheduled_at__gte=timezone.now() - datetime.timedelta(hours=2), status='scheduled')
    return render(request, 'pages/servicedesk/appointments.html', {
        'page_title': 'المواعيد', 'appointments': qs.order_by('scheduled_at')[:200], 'show_all': show_all})


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
