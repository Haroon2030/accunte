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
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.core.dates import safe_parse_date as parse_date
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.reconciliation.storage import serve_file
from apps.audit.services import diff, log_action, snapshot
from apps.branches.models import Branch
from apps.core.access import get_role_type, has_role, role_required
from apps.suppliers.models import Supplier

from . import kpis, services, tracking, workflow
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




def _xl(value):
    """يمنع حقن الصيغ في Excel: نص يبدأ بـ = + - @ يُعامل كصيغة عند الفتح."""
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


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
            _link_service_request(request, case)
            messages.success(request, f'تم إنشاء الحالة {case.reference}')
            return redirect('reconciliation:detail', pk=case.pk)
    pre_supplier = None
    pre = (request.GET.get('supplier') or request.POST.get('supplier') or '')
    if pre.isdigit():
        pre_supplier = Supplier.objects.filter(pk=pre, is_active=True).first()
    return render(request, 'pages/reconciliation/form.html', {
        'pre_supplier': pre_supplier, 'service_request_id': request.GET.get('service_request') or request.POST.get('service_request') or '',
        'page_title': 'حالة مطابقة جديدة', 'errors': errors, 'branches': Branch.objects.all(),
        'priorities': Case.Priority.choices, 'post': request.POST,
    })


def _link_service_request(request, case):
    """يربط الحالة الجديدة بطلب الخدمة الذي فُتحت منه (إن كان مرئيًا للمستخدم)."""
    sr_id = request.POST.get('service_request', '')
    if not sr_id.isdigit():
        return
    from apps.servicedesk.models import ServiceRequest
    from apps.servicedesk.services import visible_requests
    sr = visible_requests(request.user).filter(pk=sr_id, reconciliation_case__isnull=True).first()
    if sr is not None:
        ServiceRequest.objects.filter(pk=sr.pk).update(reconciliation_case=case)
        log_action(AuditLog.Action.UPDATE, sr, entity_type='servicedesk.ServiceRequest',
                   previous={'reconciliation_case': None}, new={'reconciliation_case': case.pk},
                   reason='فتح حالة مطابقة من الطلب', actor=request.user)


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
def case_track(request, pk):
    """صفحة تتبّع المسار: المراحل، ومن تقف عنده الحالة، والسجل الزمني."""
    case = _get_case(request, pk)
    allowed = allowed_transitions(request.user, case)
    return render(request, 'pages/reconciliation/track.html', {
        'page_title': f'تتبّع {case.reference}', 'case': case, 'track': tracking.build(case),
        'can_approve': case.status == S.PENDING_REVIEW and S.COMPLETED in allowed,
        'can_return': case.status == S.PENDING_REVIEW and S.RECONCILING in allowed,
        'can_close': case.status == S.COMPLETED and S.CLOSED in allowed,
        'can_approve_close': case.status == S.PENDING_REVIEW and S.COMPLETED in allowed
                             and has_role(request.user, *SUPERVISOR_ROLES),
    })


@login_required
@view_required
@require_POST
def case_transition(request, pk):
    case = _get_case(request, pk)
    try:
        workflow.transition(case.pk, request.POST.get('to', ''), request.user, request.POST.get('reason', ''))
        if request.POST.get('then_close') and request.POST.get('to') == S.COMPLETED:
            workflow.transition(case.pk, S.CLOSED, request.user, 'اعتماد وإغلاق')   # الصلاحية تُفحص كالمعتاد
            messages.success(request, 'تم اعتماد المطابقة وإغلاق الملف')
        else:
            messages.success(request, 'تم تحديث حالة المطابقة')
    except TransitionError as exc:
        messages.error(request, str(exc))
    if request.POST.get('next') == 'track':
        return redirect('reconciliation:track', pk=case.pk)
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
    response = serve_file(doc.file, doc.original_name)      # R2 أو القرص، بعد فحص الصلاحية أعلاه
    log_action(AuditLog.Action.EXPORT, doc, entity_repr=f'تنزيل {doc.original_name}')
    return response


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


