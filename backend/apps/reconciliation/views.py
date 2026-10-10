"""
واجهات المطابقة المالية.
مبدأ الأمان: كل وصول لحالة يمر عبر visible_cases (المحاسب لا يرى إلا حالاته، وغيرها يعطي 404)،
وكل تعديل يمر عبر can_work_on أو آلة الحالات.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.services import diff, log_action, snapshot
from apps.branches.models import Branch
from apps.core.access import get_role_type, has_role, role_required
from apps.suppliers.models import Supplier

from . import kpis, services, workflow
from .models import (ReconciliationCase as Case, ReconciliationDifference, ReconciliationDocument,
                     ReconciliationResult)
from .workflow import (CREATOR_ROLES, SUPERVISOR_ROLES, TransitionError, VIEW_ROLES, allowed_transitions,
                       can_work_on)

view_required = role_required(*VIEW_ROLES)
S = Case.Status


def _get_case(request, pk):
    """404 (لا 403) كي لا يُكشف وجود حالات غير مسندة للمحاسب."""
    return get_object_or_404(services.visible_cases(request.user), pk=pk)


def _decimal(value, default=Decimal('0')):
    try:
        amount = Decimal(str(value).replace(',', '').strip() or default)
    except InvalidOperation:
        raise TransitionError('قيمة مبلغ غير صالحة')
    if not amount.is_finite() or abs(amount) >= Decimal('10') ** 14:
        raise TransitionError('قيمة مبلغ غير صالحة')
    return amount.quantize(Decimal('0.01'))   # صيغة موحدة تمنع اختلاف السجل (650 مقابل 650.00)


def _guard(request, case, *, work=True):
    """يرفع TransitionError إن لم يحق للمستخدم العمل على الحالة."""
    if work and not can_work_on(request.user, case):
        raise TransitionError('لا يمكنك تعديل هذه الحالة في وضعها الحالي')


def _back(case, tab=''):
    return redirect(f'/reconciliation/{case.pk}/' + (f'?tab={tab}' if tab else ''))


# ── القائمة ──────────────────────────────────────────────────────────────────
FILTER_KEYS = ('q', 'status', 'priority', 'accountant', 'from', 'to', 'overdue', 'kpi', 'period', 'branch')


def _filtered_cases(request):
    """يطبّق كل مرشحات القائمة (ومنها مؤشر التفاصيل). مشتركة بين العرض والتصدير والطباعة."""
    qs = services.visible_cases(request.user)
    g = request.GET
    f = {k: g.get(k, '').strip() for k in FILTER_KEYS}
    if f['period'] or f['branch']:
        qs = kpis.apply_scope(qs, f['period'] or 'all', f['branch'] if f['branch'].isdigit() else None)
    if f['kpi'] in kpis.KPI_LABELS:
        qs = kpis.kpi_queryset(f['kpi'], qs)
    if f['q']:
        qs = qs.filter(Q(reference__icontains=f['q']) | Q(supplier__name__icontains=f['q'])
                       | Q(supplier__code__icontains=f['q']))
    if f['status']:
        qs = qs.filter(status=f['status'])
    if f['priority']:
        qs = qs.filter(priority=f['priority'])
    if f['accountant'].isdigit():
        qs = qs.filter(assigned_accountant_id=f['accountant'])
    if parse_date(f['from']):
        qs = qs.filter(due_date__gte=f['from'])
    if parse_date(f['to']):
        qs = qs.filter(due_date__lte=f['to'])
    if f['overdue']:
        qs = qs.filter(due_date__lt=timezone.localdate()).exclude(status__in=Case.TERMINAL)
    return qs.order_by('-created_at', '-pk'), f


@login_required
@view_required
def case_list(request):
    qs, f = _filtered_cases(request)
    page = Paginator(qs, 20).get_page(request.GET.get('page'))
    is_accountant = get_role_type(request.user) == 'accountant'
    return render(request, 'pages/reconciliation/list.html', {
        'page_title': 'مهامي' if is_accountant else 'حالات المطابقة',
        'page_obj': page, 'f': f, 'statuses': Case.Status.choices, 'priorities': Case.Priority.choices,
        'accountants': [] if is_accountant else services.accountants(),
        'can_create': has_role(request.user, *CREATOR_ROLES),
        'can_distribute': has_role(request.user, *SUPERVISOR_ROLES),
        'qs_extra': '&'.join(f'{k}={v}' for k, v in f.items() if v),
        'kpi_label': kpis.KPI_LABELS.get(f['kpi']),
    })


EXPORT_LIMIT = 5000


def _xl(value):
    """يمنع حقن الصيغ في Excel: نص يبدأ بـ = + - @ يُعامل كصيغة عند الفتح."""
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


@login_required
@view_required
def case_export_excel(request):
    from apps.core.excel_export import ModernExcelBuilder
    qs, f = _filtered_cases(request)
    cases = list(qs.select_related('supplier', 'assigned_accountant', 'result')[:EXPORT_LIMIT])
    today = timezone.localdate()
    rows = []
    for i, c in enumerate(cases, 1):
        res = getattr(c, 'result', None)
        rows.append([
            i, c.reference, _xl(c.supplier.name), f'{c.period_start:%Y/%m/%d} - {c.period_end:%Y/%m/%d}',
            c.get_status_display(), c.get_priority_display(),
            _xl(c.assigned_accountant.get_username()) if c.assigned_accountant else '-',
            f'{c.due_date:%Y/%m/%d}' if c.due_date else '-',
            'نعم' if c.is_overdue else 'لا',
            float(res.supplier_balance) if res else None, float(res.company_balance) if res else None,
            float(res.difference) if res else None,
        ])
    meta = [('عدد الحالات', len(cases))]
    if f['kpi'] in kpis.KPI_LABELS:
        meta.append(('المؤشر', kpis.KPI_LABELS[f['kpi']]))
    if len(cases) == EXPORT_LIMIT:
        meta.append(('تنبيه', f'اقتُصر التصدير على أول {EXPORT_LIMIT} حالة'))
    builder = ModernExcelBuilder('تقرير حالات المطابقة', sheet_name='الحالات')
    start = builder.write_report_header(12, meta)
    builder.write_table(start, ['#', 'الرقم', 'المورد', 'الفترة', 'الحالة', 'الأولوية', 'المحاسب', 'الاستحقاق',
                                'متأخرة', 'رصيد المورد', 'رصيد الشركة', 'الفرق'], rows,
                        col_widths=[6, 18, 30, 24, 18, 12, 16, 14, 10, 16, 16, 16])
    log_action(AuditLog.Action.EXPORT, entity_type='reconciliation.ReconciliationCase',
               entity_repr='تصدير حالات المطابقة (Excel)', new={'rows': len(cases), 'filters': {k: v for k, v in f.items() if v}})
    return builder.to_response('reconciliation_cases')


@login_required
@view_required
def case_print(request):
    """صفحة مهيأة للطباعة: احفظها PDF من المتصفح (Ctrl+P)."""
    qs, f = _filtered_cases(request)
    cases = list(qs.select_related('supplier', 'assigned_accountant', 'result')[:EXPORT_LIMIT])
    log_action(AuditLog.Action.EXPORT, entity_type='reconciliation.ReconciliationCase',
               entity_repr='تصدير حالات المطابقة (PDF)', new={'rows': len(cases)})
    return render(request, 'pages/reconciliation/print_cases.html', {
        'cases': cases, 'f': f, 'kpi_label': kpis.KPI_LABELS.get(f['kpi']), 'now': timezone.localtime(),
    })


# ── الإنشاء ──────────────────────────────────────────────────────────────────
@login_required
@role_required(*CREATOR_ROLES)
def case_create(request):
    errors = []
    if request.method == 'POST':
        p = request.POST
        supplier = Supplier.objects.filter(pk=p.get('supplier') or 0, is_active=True).first()
        start, end, due = parse_date(p.get('period_start', '')), parse_date(p.get('period_end', '')), \
            parse_date(p.get('due_date', ''))
        if not supplier:
            errors.append('اختر موردًا من القائمة')
        if not start or not end:
            errors.append('حدد بداية ونهاية الفترة المالية')
        elif end < start:
            errors.append('نهاية الفترة قبل بدايتها')
        if p.get('priority') not in Case.Priority.values:
            errors.append('أولوية غير صالحة')
        stmt = request.FILES.get('statement')
        if stmt:
            try:
                services.validate_upload(stmt)
            except TransitionError as exc:
                errors.append(str(exc))
        if not errors:
            with transaction.atomic():
                case = Case.objects.create(
                    supplier=supplier, period_start=start, period_end=end, priority=p['priority'],
                    due_date=due, notes=p.get('notes', '').strip(), created_by=request.user,
                    assigned_accountant=None)
                case.branches.set(Branch.objects.filter(pk__in=p.getlist('branches')))
                workflow.StatusHistory.objects.create(case=case, from_status='', to_status=case.status,
                                                      changed_by=request.user, reason='إنشاء الحالة')
                log_action(AuditLog.Action.CREATE, case, new=snapshot(case))
                if stmt:
                    _store_document(case, stmt, 'statement', request.user)
                    workflow.transition(case.pk, S.READY_FOR_DISTRIBUTION, request.user, 'اكتمال المستندات')
            messages.success(request, f'تم إنشاء الحالة {case.reference}')
            return redirect('reconciliation:detail', pk=case.pk)
    return render(request, 'pages/reconciliation/form.html', {
        'page_title': 'حالة مطابقة جديدة', 'errors': errors, 'branches': Branch.objects.all(),
        'priorities': Case.Priority.choices, 'post': request.POST,
    })


def _store_document(case, f, doc_type, user):
    doc = ReconciliationDocument(
        case=case, doc_type=doc_type, original_name=f.name[:255], size=f.size, uploaded_by=user,
        sha256=services.file_sha256(f))
    doc.file.save(f.name, f, save=True)
    log_action(AuditLog.Action.CREATE, doc, entity_repr=f'{case.reference}: {doc.original_name}',
               new={'name': doc.original_name, 'size': doc.size, 'sha256': doc.sha256, 'type': doc_type})
    return doc


# ── التفاصيل ─────────────────────────────────────────────────────────────────
@login_required
@view_required
def case_detail(request, pk):
    case = _get_case(request, pk)
    result = getattr(case, 'result', None)
    diffs = list(case.differences.all())
    return render(request, 'pages/reconciliation/detail.html', {
        'page_title': case.reference, 'case': case, 'result': result, 'diffs': diffs,
        'documents': case.documents.select_related('uploaded_by'),
        'history': case.history.select_related('changed_by'),
        'assignments': case.assignments.select_related('accountant', 'assigned_by'),
        'transitions': [(v, S(v).label) for v in allowed_transitions(request.user, case)],
        'can_work': can_work_on(request.user, case),
        'can_propose': case.status in ('completed', 'closed') and has_role(request.user, *CREATOR_ROLES)
                       and not case.payment_proposals.exclude(status__in=['rejected', 'cancelled']).exists(),
        'proposals': case.payment_proposals.all(),
        'tab': request.GET.get('tab', 'info'),
        'diff_total': sum((d.difference for d in diffs if not d.is_resolved), Decimal('0')),
        'kinds': ReconciliationDifference.Kind.choices,
        'doc_types': ReconciliationDocument.DocType.choices,
    })


@login_required
@view_required
@require_POST
def case_transition(request, pk):
    case = _get_case(request, pk)
    try:
        workflow.transition(case.pk, request.POST.get('to', ''), request.user, request.POST.get('reason', ''))
        messages.success(request, 'تم تحديث حالة المطابقة')
    except TransitionError as exc:
        messages.error(request, str(exc))
    return _back(case)


# ── المستندات ────────────────────────────────────────────────────────────────
@login_required
@view_required
@require_POST
def document_upload(request, pk):
    case = _get_case(request, pk)
    try:
        _guard(request, case)
        f = request.FILES.get('file')
        if not f:
            raise TransitionError('اختر ملفًا')
        services.validate_upload(f)
        doc_type = request.POST.get('doc_type')
        _store_document(case, f, doc_type if doc_type in ReconciliationDocument.DocType.values else 'other',
                        request.user)
        messages.success(request, 'تم رفع المستند')
    except TransitionError as exc:
        messages.error(request, str(exc))
    return _back(case, 'documents')


@login_required
@view_required
def document_download(request, pk, doc_pk):
    case = _get_case(request, pk)
    doc = get_object_or_404(ReconciliationDocument, pk=doc_pk, case=case)
    try:
        fh = doc.file.open('rb')
    except FileNotFoundError:
        raise Http404
    log_action(AuditLog.Action.EXPORT, doc, entity_repr=f'تنزيل {doc.original_name}')
    return FileResponse(fh, as_attachment=True, filename=doc.original_name)


@login_required
@view_required
@require_POST
def document_delete(request, pk, doc_pk):
    case = _get_case(request, pk)
    doc = get_object_or_404(ReconciliationDocument, pk=doc_pk, case=case)
    try:
        _guard(request, case)
        if doc.uploaded_by_id != request.user.pk and not has_role(request.user, *SUPERVISOR_ROLES):
            raise TransitionError('لا يمكنك حذف مستند رفعه غيرك')
        log_action(AuditLog.Action.DELETE, doc, previous={'name': doc.original_name, 'sha256': doc.sha256})
        doc.file.delete(save=False)
        doc.delete()
        messages.success(request, 'تم حذف المستند')
    except TransitionError as exc:
        messages.error(request, str(exc))
    return _back(case, 'documents')


# ── النتيجة والفروقات ────────────────────────────────────────────────────────
@login_required
@view_required
@require_POST
def result_save(request, pk):
    case = _get_case(request, pk)
    try:
        _guard(request, case)
        p = request.POST
        result = getattr(case, 'result', None) or ReconciliationResult(case=case)
        before = snapshot(result) if result.pk else {}
        result.supplier_balance = _decimal(p.get('supplier_balance'))
        result.company_balance = _decimal(p.get('company_balance'))
        result.recommended_resolution = p.get('recommended_resolution', '').strip()
        result.notes = p.get('notes', '').strip()
        result.recorded_by = request.user
        result.save()
        prev, new = diff(before, snapshot(result))
        amounts = {'supplier_balance', 'company_balance'} & set(new)
        log_action(AuditLog.Action.AMOUNT_EDIT if amounts and before else AuditLog.Action.UPDATE if before
                   else AuditLog.Action.CREATE, result, previous=prev or None, new=new)
        messages.success(request, 'تم حفظ نتيجة المطابقة')
    except TransitionError as exc:
        messages.error(request, str(exc))
    return _back(case, 'result')


@login_required
@view_required
@require_POST
def difference_add(request, pk):
    case = _get_case(request, pk)
    try:
        _guard(request, case)
        p = request.POST
        d = ReconciliationDifference(
            case=case, kind=p.get('kind') if p.get('kind') in ReconciliationDifference.Kind.values else 'other',
            document_ref=p.get('document_ref', '').strip()[:100], document_date=parse_date(p.get('document_date', '')),
            supplier_amount=_decimal(p.get('supplier_amount')), company_amount=_decimal(p.get('company_amount')),
            description=p.get('description', '').strip(),
            recommended_resolution=p.get('recommended_resolution', '').strip(), created_by=request.user)
        f = request.FILES.get('attachment')
        if f:
            services.validate_upload(f)
            d.attachment_name = f.name[:255]
            d.attachment.save(f.name, f, save=False)
        d.save()
        log_action(AuditLog.Action.CREATE, d, entity_repr=f'{case.reference}: {d}',
                   new={k: v for k, v in snapshot(d).items() if k != 'attachment'})
        messages.success(request, 'تم تسجيل الفرق')
    except TransitionError as exc:
        messages.error(request, str(exc))
    return _back(case, 'differences')


@login_required
@view_required
@require_POST
def difference_toggle(request, pk, diff_pk):
    case = _get_case(request, pk)
    d = get_object_or_404(ReconciliationDifference, pk=diff_pk, case=case)
    try:
        # التسوية: المحاسب المسؤول أو المشرفون، والحالة ليست منتهية
        if case.is_terminal or not (can_work_on(request.user, case) or has_role(request.user, *SUPERVISOR_ROLES)):
            raise TransitionError('لا يمكنك تغيير حالة التسوية')
        d.is_resolved = not d.is_resolved
        d.save(update_fields=['is_resolved'])
        log_action(AuditLog.Action.UPDATE, d, entity_repr=f'{case.reference}: {d}',
                   previous={'is_resolved': not d.is_resolved}, new={'is_resolved': d.is_resolved})
    except TransitionError as exc:
        messages.error(request, str(exc))
    return _back(case, 'differences')


@login_required
@view_required
@require_POST
def difference_delete(request, pk, diff_pk):
    case = _get_case(request, pk)
    d = get_object_or_404(ReconciliationDifference, pk=diff_pk, case=case)
    try:
        _guard(request, case)
        log_action(AuditLog.Action.DELETE, d, entity_repr=f'{case.reference}: {d}',
                   previous={k: v for k, v in snapshot(d).items() if k != 'attachment'})
        if d.attachment:
            d.attachment.delete(save=False)
        d.delete()
    except TransitionError as exc:
        messages.error(request, str(exc))
    return _back(case, 'differences')


# ── لوحة التوزيع (المشرف) ────────────────────────────────────────────────────
@login_required
@role_required(*SUPERVISOR_ROLES)
def distribution(request):
    ready = list(Case.objects.filter(status=S.READY_FOR_DISTRIBUTION)
                 .select_related('supplier').order_by('due_date', '-created_at'))
    loads = services.accountant_loads()
    suggestion = None
    if request.method == 'POST':
        action = request.POST.get('action')
        ids = [int(i) for i in request.POST.getlist('case_ids') if i.isdigit()]
        try:
            if action == 'assign':
                accountant = next((u for u in loads if str(u.pk) == request.POST.get('accountant')), None)
                if not ids or accountant is None:
                    raise TransitionError('اختر حالات ومحاسبًا')
                n = services.assign_cases([(i, accountant) for i in ids], request.user,
                                          request.POST.get('note', ''))
                messages.success(request, f'تم إسناد {n} حالة إلى {accountant.get_username()}')
                return redirect('reconciliation:distribution')
            if action == 'suggest':
                chosen = [c for c in ready if c.pk in ids] or ready
                if not loads:
                    raise TransitionError('لا يوجد محاسبون فعّالون. أنشئ مستخدمين بدور "محاسب"')
                suggestion = services.suggest_distribution(chosen, loads)
            elif action == 'apply':
                users = {str(u.pk): u for u in loads}
                pairs = [(int(k[7:]), users[v]) for k, v in request.POST.items()
                         if k.startswith('assign_') and k[7:].isdigit() and v in users]
                n = services.assign_cases(pairs, request.user, 'توزيع متوازن مقترح')
                messages.success(request, f'تم اعتماد التوزيع: {n} حالة')
                return redirect('reconciliation:distribution')
        except TransitionError as exc:
            messages.error(request, str(exc))
    max_open = max([u.open_count for u in loads] + [1])
    return render(request, 'pages/reconciliation/distribution.html', {
        'page_title': 'توزيع الملفات', 'ready': ready, 'loads': loads, 'max_open': max_open,
        'suggestion': suggestion,
    })
