"""
آلة حالات المطابقة: الانتقالات المسموحة ومن يحق له تنفيذها، مع سجل الحالة والتدقيق.
"""
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.core.access import has_role
from apps.core.models import Role

from .models import ReconciliationCase as Case
from .models import StatusHistory

S = Case.Status
RT = Role.RoleType

SUPERVISOR_ROLES = (RT.ADMIN, RT.CFO, RT.CS_SUPERVISOR)
REVIEWER_ROLES = (RT.ADMIN, RT.CFO)
CREATOR_ROLES = SUPERVISOR_ROLES
VIEW_ROLES = SUPERVISOR_ROLES + (RT.ACCOUNTANT,)

# الحالة الحالية ← {الحالة التالية: نوع المنفذ}
TRANSITIONS = {
    S.NEW: {S.PENDING_DOCS: 'creator', S.READY_FOR_DISTRIBUTION: 'creator', S.CANCELLED: 'supervisor'},
    S.PENDING_DOCS: {S.READY_FOR_DISTRIBUTION: 'creator', S.CANCELLED: 'supervisor'},
    S.READY_FOR_DISTRIBUTION: {S.PENDING_DOCS: 'creator', S.CANCELLED: 'supervisor'},
    S.ASSIGNED: {S.RECONCILING: 'assignee', S.READY_FOR_DISTRIBUTION: 'supervisor', S.CANCELLED: 'supervisor'},
    S.RECONCILING: {S.WAITING_VENDOR: 'assignee', S.DISCREPANCY_FOUND: 'assignee',
                    S.PENDING_REVIEW: 'assignee', S.CANCELLED: 'supervisor'},
    S.WAITING_VENDOR: {S.RECONCILING: 'assignee', S.CANCELLED: 'supervisor'},
    S.DISCREPANCY_FOUND: {S.RECONCILING: 'assignee', S.WAITING_VENDOR: 'assignee',
                          S.PENDING_REVIEW: 'assignee', S.CANCELLED: 'supervisor'},
    S.PENDING_REVIEW: {S.COMPLETED: 'reviewer', S.RECONCILING: 'reviewer', S.CANCELLED: 'supervisor'},
    S.COMPLETED: {S.CLOSED: 'supervisor'},
    S.CLOSED: {},
    S.CANCELLED: {},
}
# انتقالات تتطلب سببًا مكتوبًا
REASON_REQUIRED = {S.CANCELLED, (S.PENDING_REVIEW, S.RECONCILING)}
# حالات يُسمح فيها للمحاسب بتعديل النتيجة والفروقات
WORKING_STATUSES = (S.ASSIGNED, S.RECONCILING, S.WAITING_VENDOR, S.DISCREPANCY_FOUND)


class TransitionError(Exception):
    """رسالتها عربية وجاهزة للعرض للمستخدم."""


def is_supervisor(user):
    return has_role(user, *SUPERVISOR_ROLES)


def _actor_allowed(kind, user, case):
    if kind == 'supervisor':
        return has_role(user, *SUPERVISOR_ROLES)
    if kind == 'creator':
        return has_role(user, *CREATOR_ROLES)
    if kind == 'reviewer':
        # المحاسب لا يعتمد مطابقة هو منفذها حتى لو كان له دور مراجع
        return has_role(user, *REVIEWER_ROLES) and user.pk != case.assigned_accountant_id
    if kind == 'assignee':
        return user.pk == case.assigned_accountant_id or has_role(user, *SUPERVISOR_ROLES)
    return False


def allowed_transitions(user, case):
    """الحالات التي يستطيع المستخدم نقل الحالة إليها الآن."""
    return [to for to, kind in TRANSITIONS.get(case.status, {}).items() if _actor_allowed(kind, user, case)]


def can_work_on(user, case):
    """هل يحق للمستخدم تعديل النتيجة/الفروقات/المستندات؟"""
    if case.status not in WORKING_STATUSES and not (
            case.status in (S.NEW, S.PENDING_DOCS, S.READY_FOR_DISTRIBUTION) and has_role(user, *CREATOR_ROLES)):
        return False
    if user.pk == case.assigned_accountant_id:
        return True
    return has_role(user, *SUPERVISOR_ROLES)


def _check_preconditions(case, to):
    if to == S.READY_FOR_DISTRIBUTION and not case.documents.filter(doc_type='statement').exists():
        raise TransitionError('أرفق كشف حساب المورد قبل تجهيز الحالة للتوزيع')
    if to == S.DISCREPANCY_FOUND and not case.differences.exists():
        raise TransitionError('سجّل بند فرق واحدًا على الأقل قبل الانتقال إلى "تم رصد فروقات"')
    if to == S.PENDING_REVIEW:
        if not hasattr(case, 'result'):
            raise TransitionError('سجّل نتيجة المطابقة (الرصيدان) قبل إرسالها للمراجعة')
    if to == S.COMPLETED:
        if case.differences.filter(is_resolved=False).exists():
            raise TransitionError('توجد فروقات غير مسوّاة. سوِّها أو أعدها للمحاسب')


@transaction.atomic
def transition(case_id, to_status, user, reason=''):
    """ينفّذ الانتقال بقفل تشاؤمي على الصف لمنع تعارض مستخدمَين."""
    case = Case.objects.select_for_update().get(pk=case_id)
    to = S(to_status) if to_status in S.values else None
    if to is None:
        raise TransitionError('حالة غير معروفة')
    kind = TRANSITIONS.get(case.status, {}).get(to)
    if kind is None:
        raise TransitionError(f'لا يمكن الانتقال من "{case.get_status_display()}" إلى "{to.label}"')
    if not _actor_allowed(kind, user, case):
        raise TransitionError('ليس لديك صلاحية تنفيذ هذا الانتقال')
    reason = (reason or '').strip()
    if (to in REASON_REQUIRED or (case.status, to) in REASON_REQUIRED) and not reason:
        raise TransitionError('السبب مطلوب لهذا الإجراء')
    _check_preconditions(case, to)

    old = case.status
    case.status = to
    if to == S.READY_FOR_DISTRIBUTION and old == S.ASSIGNED:
        _end_active_assignment(case)
        case.assigned_accountant = None
    if to in (S.CLOSED, S.CANCELLED, S.COMPLETED):
        case.closed_at = timezone.now()
    case.save()
    StatusHistory.objects.create(case=case, from_status=old, to_status=to, changed_by=user, reason=reason)
    log_action(AuditLog.Action.STATUS_CHANGE, case, previous={'status': old}, new={'status': to}, reason=reason,
               actor=user)
    if to == S.COMPLETED:
        log_action(AuditLog.Action.APPROVAL, case, new={'decision': 'completed'}, reason=reason, actor=user)
    return case


def _end_active_assignment(case):
    case.assignments.filter(is_active=True).update(is_active=False, active_case=None, ended_at=timezone.now())
