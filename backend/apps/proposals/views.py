"""
واجهات مقترحات الدفع.
الرؤية على مستوى الصف: المنشئ يرى مقترحاته، ومسؤول المدفوعات يرى المعتمد وما بعده فقط،
والمدير المالي والمدير والمدقق ومدير النظام يرون الكل. غير المرئي يعطي 404.
"""
import datetime
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from apps.core.dates import safe_parse_date as parse_date
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.services import log_action, snapshot
from apps.branches.models import Branch
from apps.core.access import get_role_type, has_role, role_required
from apps.core.models import Role
from apps.reconciliation import services as recon_services
from apps.reconciliation.models import ReconciliationCase
from apps.reconciliation.services import validate_upload, file_sha256
from apps.reconciliation.workflow import TransitionError

from . import workflow
from .models import PaymentProposal, ProposalAttachment
from .workflow import CREATOR_ROLES, ProposalError, VIEW_ROLES

S = PaymentProposal.Status
RT = Role.RoleType
view_required = role_required(*VIEW_ROLES)


def visible_proposals(user):
    qs = PaymentProposal.objects.select_related('supplier', 'branch', 'reconciliation_case', 'created_by')
    role = get_role_type(user)
    if role in (RT.ADMIN, RT.CFO, RT.MANAGER, RT.AUDITOR):
        return qs
    if role == RT.PAYMENT_OFFICER:
        return qs.filter(status__in=[S.APPROVED, S.DISPATCHED, S.CONFIRMED_PAID])
    return qs.filter(created_by=user)


def _get(request, pk):
    return get_object_or_404(visible_proposals(request.user), pk=pk)


def _money(value):
    try:
        v = Decimal(str(value).replace(',', '').strip())
    except InvalidOperation:
        raise ProposalError('قيمة مبلغ غير صالحة')
    if not v.is_finite() or abs(v) >= Decimal('10') ** 14:
        raise ProposalError('قيمة مبلغ غير صالحة')
    return v.quantize(Decimal('0.01'))


def eligible_cases(user):
    """حالات المطابقة المكتملة التي يحق للمستخدم رفع مقترح لها ولا يوجد لها مقترح نشط."""
    active = PaymentProposal.objects.exclude(status__in=PaymentProposal.INACTIVE).values('reconciliation_case')
    return (recon_services.visible_cases(user).filter(status__in=['completed', 'closed'])
            .exclude(pk__in=active).prefetch_related('branches'))


@login_required
@view_required
def proposal_list(request):
    qs = visible_proposals(request.user)
    g = request.GET
    f = {k: g.get(k, '').strip() for k in ('q', 'status')}
    if f['q']:
        qs = qs.filter(Q(reference__icontains=f['q']) | Q(supplier__name__icontains=f['q'])
                       | Q(supplier__code__icontains=f['q']))
    if f['status']:
        qs = qs.filter(status=f['status'])
    page = Paginator(qs, 20).get_page(g.get('page'))
    return render(request, 'pages/proposals/list.html', {
        'page_title': 'مقترحات الدفع', 'page_obj': page, 'f': f, 'statuses': PaymentProposal.Status.choices,
        'can_create': has_role(request.user, *CREATOR_ROLES),
        'qs_extra': '&'.join(f'{k}={v}' for k, v in f.items() if v),
        'threshold': workflow.cfo_threshold(),
    })


@login_required
@role_required(*CREATOR_ROLES)
def proposal_create(request):
    cases = list(eligible_cases(request.user))
    errors = []
    selected = request.POST.get('case') or request.GET.get('case') or ''
    if request.method == 'POST':
        p = request.POST
        case = next((c for c in cases if str(c.pk) == p.get('case')), None)
        branch = Branch.objects.filter(pk=p.get('branch') or 0).first()
        try:
            if case is None:
                raise ProposalError('اختر حالة مطابقة مكتملة ليس لها مقترح نشط')
            if branch is None:
                raise ProposalError('اختر الفرع')
            dues, amount = _money(p.get('total_dues')), _money(p.get('proposed_amount'))
            workflow._validate_amounts(dues, amount)
            if not p.get('justification', '').strip():
                raise ProposalError('المبررات مطلوبة')
            f = request.FILES.get('file')
            if f:
                validate_upload(f)
        except (ProposalError, TransitionError) as exc:
            errors.append(str(exc))
        else:
            try:
                with transaction.atomic():
                    prop = PaymentProposal.objects.create(
                        supplier=case.supplier, branch=branch, reconciliation_case=case, total_dues=dues,
                        proposed_amount=amount, justification=p['justification'].strip(), created_by=request.user,
                        requires_cfo=workflow.requires_cfo(amount))
                    log_action(AuditLog.Action.CREATE, prop, new=snapshot(prop))
                    if f:
                        _store_attachment(prop, f, request.user)
            except IntegrityError:
                errors.append('يوجد مقترح نشط لهذه المطابقة بالفعل')
            else:
                messages.success(request, f'تم إنشاء المقترح {prop.reference} كمسودة')
                return redirect('proposals:detail', pk=prop.pk)

    prefill = {}
    for c in cases:
        res = getattr(c, 'result', None)
        prefill[c.pk] = {
            'dues': str(abs(res.supplier_balance)) if res else '',
            'branches': [b.pk for b in c.branches.all()],
        }
    return render(request, 'pages/proposals/form.html', {
        'page_title': 'مقترح دفع جديد', 'cases': cases, 'errors': errors, 'selected': str(selected),
        'branches': Branch.objects.all(), 'prefill_json': json.dumps(prefill), 'post': request.POST,
        'threshold': workflow.cfo_threshold(),
    })


def _store_attachment(prop, f, user):
    att = ProposalAttachment(proposal=prop, original_name=f.name[:255], size=f.size, uploaded_by=user,
                             sha256=file_sha256(f))
    att.file.save(f.name, f, save=True)
    log_action(AuditLog.Action.CREATE, att, entity_repr=f'{prop.reference}: {att.original_name}',
               new={'name': att.original_name, 'sha256': att.sha256})
    return att


@login_required
@view_required
def proposal_detail(request, pk):
    p = _get(request, pk)
    trail = AuditLog.objects.filter(entity_type='proposals.PaymentProposal', entity_id=str(p.pk))[:50]
    return render(request, 'pages/proposals/detail.html', {
        'page_title': p.reference, 'p': p, 'approvals': p.approvals.select_related('decided_by'),
        'execution': getattr(p, 'execution', None), 'attachments': p.attachments.all(),
        'transitions': [(v, S(v).label) for v in workflow.allowed_transitions(request.user, p)],
        'can_edit': workflow.can_edit(request.user, p), 'trail': trail,
        'branches': Branch.objects.all(), 'threshold': workflow.cfo_threshold(),
        'today': datetime.date.today(),
    })


@login_required
@view_required
@require_POST
def proposal_edit(request, pk):
    p = _get(request, pk)
    try:
        branch = Branch.objects.filter(pk=request.POST.get('branch') or 0).first()
        if branch is None:
            raise ProposalError('اختر الفرع')
        workflow.update_proposal(
            p.pk, request.user, total_dues=_money(request.POST.get('total_dues')),
            proposed_amount=_money(request.POST.get('proposed_amount')),
            justification=request.POST.get('justification', '').strip(), branch=branch)
        messages.success(request, 'تم حفظ التعديلات')
    except ProposalError as exc:
        messages.error(request, str(exc))
    return redirect('proposals:detail', pk=pk)


@login_required
@view_required
@require_POST
def proposal_transition(request, pk):
    p = _get(request, pk)
    extra = {'bank_reference': request.POST.get('bank_reference', ''),
             'payment_date': parse_date(request.POST.get('payment_date', ''))}
    try:
        workflow.transition(p.pk, request.POST.get('to', ''), request.user, request.POST.get('reason', ''), extra)
        messages.success(request, 'تم تحديث حالة المقترح')
    except ProposalError as exc:
        messages.error(request, str(exc))
    return redirect('proposals:detail', pk=pk)


@login_required
@view_required
@require_POST
def attachment_upload(request, pk):
    p = _get(request, pk)
    try:
        if not workflow.can_edit(request.user, p):
            raise ProposalError('لا يمكن إضافة مرفقات في هذه الحالة')
        f = request.FILES.get('file')
        if not f:
            raise ProposalError('اختر ملفًا')
        validate_upload(f)
        _store_attachment(p, f, request.user)
        messages.success(request, 'تم رفع المرفق')
    except (ProposalError, TransitionError) as exc:
        messages.error(request, str(exc))
    return redirect('proposals:detail', pk=pk)


@login_required
@view_required
def attachment_download(request, pk, att_pk):
    p = _get(request, pk)
    att = get_object_or_404(ProposalAttachment, pk=att_pk, proposal=p)
    try:
        fh = att.file.open('rb')
    except FileNotFoundError:
        raise Http404
    log_action(AuditLog.Action.EXPORT, att, entity_repr=f'تنزيل {att.original_name}')
    return FileResponse(fh, as_attachment=True, filename=att.original_name)


@login_required
@view_required
@require_POST
def attachment_delete(request, pk, att_pk):
    p = _get(request, pk)
    att = get_object_or_404(ProposalAttachment, pk=att_pk, proposal=p)
    if not workflow.can_edit(request.user, p):
        messages.error(request, 'لا يمكن حذف المرفقات في هذه الحالة')
    else:
        log_action(AuditLog.Action.DELETE, att, previous={'name': att.original_name, 'sha256': att.sha256})
        att.file.delete(save=False)
        att.delete()
    return redirect('proposals:detail', pk=pk)
