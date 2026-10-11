"""
مسار مقترح الدفع: الانتقالات، فصل المهام، والتوجيه حسب حد المبلغ.

قواعد فصل المهام:
  - من أنشأ المقترح لا يعتمده ولا يصرفه.
  - من صرف الدفعة لا يؤكد سدادها.
  - اعتماد المبالغ ≥ الحد يقتصر على المدير المالي (ومدير النظام).
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.core.access import has_role
from apps.core.models import Notification, Role, SystemSettings

from .models import PaymentApproval, PaymentExecutionRecord, PaymentProposal

S = PaymentProposal.Status
RT = Role.RoleType

CREATOR_ROLES = (RT.ADMIN, RT.CFO, RT.CS_SUPERVISOR, RT.ACCOUNTANT)
OVERSIGHT_ROLES = (RT.ADMIN, RT.CFO)
VIEW_ROLES = CREATOR_ROLES

DEFAULT_CFO_THRESHOLD = Decimal('50000')
THRESHOLD_KEY = 'proposal_cfo_threshold'


class ProposalError(Exception):
    """رسالة عربية جاهزة للعرض."""


def cfo_threshold():
    row = SystemSettings.objects.filter(key=THRESHOLD_KEY).first()
    try:
        return Decimal(row.value) if row else DEFAULT_CFO_THRESHOLD
    except Exception:
        return DEFAULT_CFO_THRESHOLD


def requires_cfo(amount):
    return amount >= cfo_threshold()


# الحالة الحالية ← {التالية: نوع المنفذ}
TRANSITIONS = {
    S.DRAFT: {S.SUBMITTED: 'owner', S.CANCELLED: 'owner'},
    S.SUBMITTED: {S.PENDING_REVIEW: 'reviewer', S.CANCELLED: 'owner'},
    S.NEEDS_INFO: {S.SUBMITTED: 'owner', S.CANCELLED: 'owner'},
    S.PENDING_REVIEW: {S.APPROVED: 'approver', S.REJECTED: 'approver', S.NEEDS_INFO: 'approver'},
    S.APPROVED: {S.DISPATCHED: 'dispatcher', S.CANCELLED: 'cfo'},
    S.DISPATCHED: {S.CONFIRMED_PAID: 'confirmer'},
    S.REJECTED: {}, S.CONFIRMED_PAID: {}, S.CANCELLED: {},
}
REASON_REQUIRED = {S.REJECTED, S.NEEDS_INFO, S.CANCELLED}
EDITABLE = (S.DRAFT, S.NEEDS_INFO)


def _allowed(kind, user, p, execution=None):
    is_creator = user.pk == p.created_by_id
    if kind == 'owner':
        return is_creator or has_role(user, RT.CFO)
    if kind == 'reviewer':
        return has_role(user, RT.CFO) and not is_creator
    if kind == 'approver':
        return has_role(user, RT.CFO) and not is_creator
    if kind == 'cfo':
        return has_role(user, RT.CFO)
    if kind == 'dispatcher':
        return has_role(user, RT.CFO) and not is_creator
    if kind == 'confirmer':
        if execution is not None and execution.dispatched_by_id == user.pk:
            return False                    # من صرف لا يؤكد: يؤكد الآخر (المدير المالي أو مدير النظام)
        return has_role(user, RT.CFO)
    return False


def allowed_transitions(user, p):
    execution = getattr(p, 'execution', None)
    return [to for to, kind in TRANSITIONS.get(p.status, {}).items() if _allowed(kind, user, p, execution)]


def can_edit(user, p):
    return p.status in EDITABLE and (user.pk == p.created_by_id or has_role(user, RT.CFO))


def _notify(recipients, title, message, p):
    seen = set()
    rows = []
    for u in recipients:
        if u.pk in seen or not u.is_active:
            continue
        seen.add(u.pk)
        rows.append(Notification(recipient=u, category=Notification.Category.PAYMENT, title=title,
                                 message=message, link=f'/proposals/{p.pk}/'))
    Notification.objects.bulk_create(rows)


def _users_with_role(*role_types):
    from django.contrib.auth import get_user_model
    return list(get_user_model().objects.filter(is_active=True, profile__role__role_type__in=role_types))


def _precheck(p, to, extra):
    if to == S.SUBMITTED:
        if not p.justification.strip():
            raise ProposalError('المبررات مطلوبة قبل التقديم')
        case = p.reconciliation_case
        if case.status not in ('completed', 'closed'):
            raise ProposalError('لا يمكن تقديم مقترح لمطابقة غير مكتملة')
    if to == S.DISPATCHED:
        if not (extra.get('bank_reference') or '').strip():
            raise ProposalError('مرجع التحويل البنكي مطلوب')
        if not isinstance(extra.get('payment_date'), date):
            raise ProposalError('تاريخ الصرف مطلوب')


@transaction.atomic
def transition(proposal_id, to_status, user, reason='', extra=None):
    extra = extra or {}
    p = PaymentProposal.objects.select_for_update().select_related('reconciliation_case').get(pk=proposal_id)
    if to_status not in S.values:
        raise ProposalError('حالة غير معروفة')
    to = S(to_status)
    kind = TRANSITIONS.get(p.status, {}).get(to)
    if kind is None:
        raise ProposalError(f'لا يمكن الانتقال من "{p.get_status_display()}" إلى "{to.label}"')
    execution = getattr(p, 'execution', None)
    if not _allowed(kind, user, p, execution):
        raise ProposalError('ليس لديك صلاحية تنفيذ هذا الإجراء (قد يكون السبب فصل المهام)')
    reason = (reason or '').strip()
    if to in REASON_REQUIRED and not reason:
        raise ProposalError('السبب/الملاحظات مطلوبة لهذا الإجراء')
    _precheck(p, to, extra)

    old = p.status
    p.status = to
    now = timezone.now()
    if to == S.SUBMITTED:
        p.submitted_at = now
        p.requires_cfo = requires_cfo(p.proposed_amount)   # التوجيه يُحسم عند التقديم
    if to in (S.APPROVED, S.REJECTED):
        p.decided_at = now
    p.save()

    if to in (S.APPROVED, S.REJECTED, S.NEEDS_INFO):
        PaymentApproval.objects.create(proposal=p, decision=to, decided_by=user, notes=reason,
                                       amount_at_decision=p.proposed_amount)
        log_action(AuditLog.Action.APPROVAL, p, previous={'status': old},
                   new={'decision': to.value, 'amount': p.proposed_amount, 'requires_cfo': p.requires_cfo},
                   reason=reason, actor=user)
    if to == S.DISPATCHED:
        PaymentExecutionRecord.objects.create(
            proposal=p, executed_amount=p.proposed_amount, bank_reference=extra['bank_reference'].strip()[:100],
            payment_date=extra['payment_date'], dispatched_by=user, notes=reason)
    if to == S.CONFIRMED_PAID:
        PaymentExecutionRecord.objects.filter(proposal=p).update(confirmed_by=user, confirmed_at=now)
    log_action(AuditLog.Action.STATUS_CHANGE, p, previous={'status': old}, new={'status': to.value},
               reason=reason, actor=user)

    _notify_after(p, to, user)
    return p


def _notify_after(p, to, user):
    creator = [p.created_by]
    if to == S.SUBMITTED:
        recipients = _users_with_role(RT.CFO)
        _notify([u for u in recipients if u.pk != user.pk], 'مقترح دفع بانتظار المراجعة',
                f'{p.reference} · {p.supplier.name} · {p.proposed_amount} {p.currency}', p)
    elif to in (S.APPROVED, S.REJECTED, S.NEEDS_INFO):
        label = {S.APPROVED: 'اعتماد', S.REJECTED: 'رفض', S.NEEDS_INFO: 'طلب استيضاح'}[to]
        _notify(creator, f'قرار على مقترحك: {label}', f'{p.reference} · {p.supplier.name}', p)
        if to == S.APPROVED:
            _notify(_users_with_role(RT.CFO), 'مقترح معتمد جاهز للصرف',
                    f'{p.reference} · {p.supplier.name} · {p.proposed_amount} {p.currency}', p)
    elif to == S.DISPATCHED:
        _notify(creator + _users_with_role(RT.CFO), 'تم صرف دفعة بانتظار التأكيد',
                f'{p.reference} · {p.supplier.name}', p)
    elif to == S.CONFIRMED_PAID:
        _notify(creator, 'تأكد سداد مقترحك', f'{p.reference} · {p.supplier.name}', p)


# ── التعديل (المبالغ مقفلة بعد التقديم) ──────────────────────────────────────
@transaction.atomic
def update_proposal(proposal_id, user, *, total_dues, proposed_amount, justification, branch):
    p = PaymentProposal.objects.select_for_update().get(pk=proposal_id)
    if not can_edit(user, p):
        raise ProposalError('لا يمكن تعديل المقترح في وضعه الحالي')
    total_dues = total_dues.quantize(Decimal('0.01'))          # نفس دقة القاعدة، فلا يظهر فرق وهمي في السجل
    proposed_amount = proposed_amount.quantize(Decimal('0.01'))
    _validate_amounts(total_dues, proposed_amount)
    before = {'total_dues': p.total_dues, 'proposed_amount': p.proposed_amount,
              'justification': p.justification, 'branch': p.branch_id}
    p.total_dues, p.proposed_amount, p.justification, p.branch = total_dues, proposed_amount, justification, branch
    p.save()
    after = {'total_dues': p.total_dues, 'proposed_amount': p.proposed_amount,
             'justification': p.justification, 'branch': p.branch_id}
    changed_prev = {k: v for k, v in before.items() if v != after[k]}
    if changed_prev:
        amounts = {'total_dues', 'proposed_amount'} & set(changed_prev)
        log_action(AuditLog.Action.AMOUNT_EDIT if amounts else AuditLog.Action.UPDATE, p,
                   previous=changed_prev, new={k: after[k] for k in changed_prev}, actor=user)
    return p


def _validate_amounts(total_dues, proposed_amount):
    if proposed_amount <= 0:
        raise ProposalError('المبلغ المقترح يجب أن يكون أكبر من صفر')
    if total_dues <= 0:
        raise ProposalError('إجمالي المستحقات يجب أن يكون أكبر من صفر')
    if proposed_amount > total_dues:
        raise ProposalError('المبلغ المقترح لا يمكن أن يتجاوز إجمالي المستحقات')


# ── التحليلات: كل مقترح يُحسب مرة واحدة فقط ───────────────────────────────────
def totals_by_status(queryset=None):
    """يُرجع {status: {'count': n, 'total': Decimal}}.
    يعتمد على جدول المقترحات وحده دون ربط بالقرارات أو المرفقات، فلا يتضاعف العدّ مهما تعددت القرارات.
    القيد one_active_proposal_per_case يمنع تكرار المقترح لنفس المطابقة."""
    from django.db.models import Count, Sum
    qs = queryset if queryset is not None else PaymentProposal.objects.all()
    rows = qs.order_by().values('status').annotate(count=Count('pk'), total=Sum('proposed_amount'))
    return {r['status']: {'count': r['count'], 'total': r['total'] or Decimal('0')} for r in rows}
