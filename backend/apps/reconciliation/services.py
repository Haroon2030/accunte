"""
خدمات المطابقة: الرؤية على مستوى الصف، توزيع الحالات، أحمال المحاسبين، والمرفقات.
"""
import datetime
import hashlib
import os

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.core.access import get_role_type, has_role
from apps.core.models import Notification, Role

from .models import ReconciliationCase as Case
from .models import StatusHistory, WorkAssignment
from .workflow import SUPERVISOR_ROLES, TransitionError

S = Case.Status
User = get_user_model()

ALLOWED_EXTENSIONS = {'.xlsx', '.xls', '.csv', '.pdf', '.png', '.jpg', '.jpeg'}
MAX_FILE_BYTES = 10 * 1024 * 1024
PRIORITY_WEIGHT = {'urgent': 4, 'high': 3, 'normal': 2, 'low': 1}


# ── الرؤية ───────────────────────────────────────────────────────────────────
def visible_cases(user):
    """الحالات التي يحق للمستخدم رؤيتها. المحاسب لا يرى إلا حالاته."""
    qs = Case.objects.select_related('supplier', 'assigned_accountant')
    if get_role_type(user) == Role.RoleType.ACCOUNTANT:
        return qs.filter(assigned_accountant=user)
    return qs


# ── المحاسبون وأحمالهم ───────────────────────────────────────────────────────
def accountants():
    return User.objects.filter(is_active=True, profile__role__role_type=Role.RoleType.ACCOUNTANT,
                               profile__role__is_active=True)


def accountant_loads():
    """قائمة المحاسبين مع عدد حالاتهم المفتوحة والمتأخرة والعاجلة."""
    today = timezone.localdate()
    open_q = Q(assigned_reconciliations__status__in=Case.OPEN_STATUSES)
    return list(accountants().annotate(
        open_count=Count('assigned_reconciliations', filter=open_q, distinct=True),
        overdue_count=Count('assigned_reconciliations', filter=open_q & Q(assigned_reconciliations__due_date__lt=today),
                            distinct=True),
        urgent_count=Count('assigned_reconciliations',
                           filter=open_q & Q(assigned_reconciliations__priority='urgent'), distinct=True),
    ).order_by('open_count', 'username'))


def suggest_distribution(cases, loads=None):
    """يقترح محاسبًا لكل حالة بحيث تتساوى الأحمال. يُرجع [(case, user)].
    الحالات الأعلى أولوية والأقرب استحقاقًا تُوزَّع أولًا. الحمل يُحسب بوزن الأولوية."""
    loads = loads if loads is not None else accountant_loads()
    if not loads:
        return []
    score = {u.pk: u.open_count + 0.5 * u.urgent_count for u in loads}
    by_id = {u.pk: u for u in loads}
    ordered = sorted(cases, key=lambda c: (-PRIORITY_WEIGHT.get(c.priority, 2), c.due_date is None,
                                           c.due_date or datetime.date.max, c.pk))
    plan = []
    for case in ordered:
        uid = min(score, key=lambda k: (score[k], k))
        plan.append((case, by_id[uid]))
        score[uid] += 1 + (0.5 if case.priority == 'urgent' else 0)
    return plan


# ── الإسناد ──────────────────────────────────────────────────────────────────
@transaction.atomic
def assign_cases(pairs, by_user, note=''):
    """pairs: [(case_id, accountant)]. يُسند الحالات الجاهزة أو المُسندة (إعادة إسناد). يُرجع عدد المنفذ."""
    if not has_role(by_user, *SUPERVISOR_ROLES):
        raise TransitionError('ليس لديك صلاحية توزيع الحالات')
    valid_ids = set(accountants().values_list('pk', flat=True))
    done = 0
    for case_id, accountant in pairs:
        if accountant.pk not in valid_ids:
            raise TransitionError('المستخدم المختار ليس محاسبًا فعّالًا')
        case = Case.objects.select_for_update().get(pk=case_id)
        if case.status not in (S.READY_FOR_DISTRIBUTION, S.ASSIGNED):
            continue
        old_status, old_acc = case.status, case.assigned_accountant_id
        case.assignments.filter(is_active=True).update(is_active=False, active_case=None, ended_at=timezone.now())
        WorkAssignment.objects.create(case=case, accountant=accountant, assigned_by=by_user, note=note[:300])
        case.assigned_accountant = accountant
        case.status = S.ASSIGNED
        case.save()
        if old_status != S.ASSIGNED:
            StatusHistory.objects.create(case=case, from_status=old_status, to_status=S.ASSIGNED,
                                         changed_by=by_user, reason=f'أُسندت إلى {accountant.get_username()}')
        log_action(AuditLog.Action.UPDATE, case, previous={'assigned_accountant': old_acc, 'status': old_status},
                   new={'assigned_accountant': accountant.pk, 'status': S.ASSIGNED},
                   reason='توزيع حالة مطابقة', actor=by_user)
        Notification.objects.create(
            recipient=accountant, category=Notification.Category.SYSTEM,
            title='حالة مطابقة جديدة مسندة إليك',
            message=f'{case.reference} · {case.supplier.name}',
            link=f'/reconciliation/{case.pk}/')
        done += 1
    return done


# ── المرفقات ─────────────────────────────────────────────────────────────────
def validate_upload(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise TransitionError('نوع الملف غير مسموح. المسموح: ' + '، '.join(sorted(ALLOWED_EXTENSIONS)))
    if f.size > MAX_FILE_BYTES:
        raise TransitionError('حجم الملف يتجاوز 10 ميجابايت')
    return ext


def file_sha256(f):
    h = hashlib.sha256()
    for chunk in f.chunks():
        h.update(chunk)
    f.seek(0)
    return h.hexdigest()
