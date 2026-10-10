"""
مؤشرات لوحة المدير المالي.

مبدأ التصميم: كل مؤشر يُعرَّف مرة واحدة في kpi_queryset. اللوحة تعدّه، والنقر عليه يفتح القائمة المفلترة
بنفس الدالة، فلا يختلف الرقم عن الصفوف المعروضة تحت "التفاصيل".
"""
import datetime
from decimal import Decimal

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Max, Q, Sum
from django.db.models.functions import Abs
from django.utils import timezone

from apps.proposals.models import PaymentProposal

from .models import ReconciliationCase as Case
from .models import ReconciliationDifference, StatusHistory

S = Case.Status
STALE_DAYS = 7
PERIODS = {'30': 30, '90': 90, '365': 365, 'all': None}
DEFAULT_PERIOD = '90'

NEW_STATUSES = (S.NEW, S.PENDING_DOCS, S.READY_FOR_DISTRIBUTION)
WORKED_STATUSES = (S.RECONCILING, S.WAITING_VENDOR, S.DISCREPANCY_FOUND, S.PENDING_REVIEW, S.COMPLETED, S.CLOSED)

KPI_LABELS = {
    'all': 'كل الحالات المستلمة',
    'new': 'جديدة / قبل الإسناد',
    'in_progress': 'قيد التنفيذ',
    'overdue': 'متأخرة',
    'waiting_vendor': 'بانتظار رد المورد',
    'discrepancy': 'بها فروقات',
    'stale': 'راكدة (بلا نشاط)',
    'completed': 'مكتملة',
}


def apply_scope(qs, period=DEFAULT_PERIOD, branch_id=None):
    """نطاق التقرير: الفترة (حسب تاريخ الإنشاء) والفرع."""
    days = PERIODS.get(period if period in PERIODS else DEFAULT_PERIOD)
    if days:
        qs = qs.filter(created_at__gte=timezone.now() - datetime.timedelta(days=days))
    if branch_id:
        # بالمعرفات لا بالربط المباشر: الحالة ذات الفروع المتعددة لا تُعدّ مرتين
        qs = qs.filter(pk__in=Case.branches.through.objects.filter(branch_id=branch_id).values('reconciliationcase_id'))
    return qs


def kpi_queryset(kpi, qs):
    """الحالات التي يندرج تحتها المؤشر. تُعيد queryset بلا تكرار."""
    today = timezone.localdate()
    if kpi == 'new':
        return qs.filter(status__in=NEW_STATUSES)
    if kpi == 'in_progress':
        return qs.filter(status__in=Case.OPEN_STATUSES)
    if kpi == 'overdue':
        return qs.filter(due_date__lt=today).exclude(status__in=Case.TERMINAL)
    if kpi == 'waiting_vendor':
        return qs.filter(status=S.WAITING_VENDOR)
    if kpi == 'discrepancy':
        # الربط بالفروقات يُنتج صفًا لكل فرق: distinct يمنع عدّ الحالة أكثر من مرة
        return qs.filter(pk__in=ReconciliationDifference.objects.values('case'))
    if kpi == 'stale':
        cutoff = timezone.now() - datetime.timedelta(days=STALE_DAYS)
        return (qs.exclude(status__in=Case.TERMINAL)
                .annotate(last_activity=Max('history__created_at'))
                .filter(Q(last_activity__lt=cutoff) | Q(last_activity__isnull=True, created_at__lt=cutoff)))
    if kpi == 'completed':
        return qs.filter(status__in=(S.COMPLETED, S.CLOSED))
    return qs


def _fmt_duration(td):
    if td is None:
        return None
    hours = td.total_seconds() / 3600
    return {'days': round(hours / 24, 1), 'hours': round(hours, 1)}


def build(base_qs, period=DEFAULT_PERIOD, branch_id=None):
    """يبني كل أرقام اللوحة. base_qs هو visible_cases للمستخدم."""
    scoped = apply_scope(base_qs, period, branch_id)
    ids = scoped.values('pk')           # نعمل بالمعرفات لتفادي تضاعف الربط في الاستعلامات اللاحقة

    counts = {k: kpi_queryset(k, scoped).count() for k in KPI_LABELS if k != 'all'}
    counts['all'] = scoped.count()

    by_status = {r['status']: r['n'] for r in scoped.order_by().values('status').annotate(n=Count('pk'))}
    status_rows = [(v, label, by_status.get(v, 0)) for v, label in Case.Status.choices]

    # متوسط زمن الحل: من الإنشاء إلى لحظة "مكتملة" الأولى
    avg = (StatusHistory.objects.filter(to_status=S.COMPLETED, case__in=ids)
           .annotate(d=ExpressionWrapper(F('created_at') - F('case__created_at'), output_field=DurationField()))
           .aggregate(avg=Avg('d'))['avg'])

    worked = scoped.filter(status__in=WORKED_STATUSES)
    worked_n = worked.count()
    with_diff = kpi_queryset('discrepancy', worked).count()
    unresolved = (ReconciliationDifference.objects.filter(case__in=ids, is_resolved=False)
                  .aggregate(total=Sum(Abs(F('supplier_amount') - F('company_amount'))), n=Count('pk')))

    prop_qs = PaymentProposal.objects.filter(reconciliation_case__in=ids)
    from apps.proposals.workflow import totals_by_status
    prop_totals = totals_by_status(prop_qs)
    pending = [prop_totals.get(s, {'count': 0, 'total': Decimal('0')}) for s in ('submitted', 'pending_review')]
    stale_cut = timezone.now() - datetime.timedelta(days=STALE_DAYS)
    stale_props = prop_qs.filter(status__in=['submitted', 'pending_review'], submitted_at__lt=stale_cut)

    return {
        'counts': counts,
        'status_rows': status_rows,
        'status_max': max([r[2] for r in status_rows] + [1]),
        'avg_resolution': _fmt_duration(avg),
        'resolved_n': StatusHistory.objects.filter(to_status=S.COMPLETED, case__in=ids).count(),
        'discrepancy': {
            'cases': with_diff, 'worked': worked_n,
            'rate': round(100 * with_diff / worked_n, 1) if worked_n else 0,
            'unresolved_items': unresolved['n'] or 0,
            'unresolved_amount': unresolved['total'] or Decimal('0'),
        },
        'proposals': {
            'by_status': [(s.value, s.label, prop_totals.get(s.value, {'count': 0, 'total': Decimal('0')}))
                          for s in PaymentProposal.Status],
            'grand_count': sum(v['count'] for v in prop_totals.values()),
            'grand_total': sum((v['total'] for v in prop_totals.values()), Decimal('0')),
            'pending_count': pending[0]['count'] + pending[1]['count'],
            'pending_total': pending[0]['total'] + pending[1]['total'],
            'stale_count': stale_props.count(),
        },
        'stale_days': STALE_DAYS,
        'overdue_list': list(kpi_queryset('overdue', scoped).select_related('supplier', 'assigned_accountant')
                             .order_by('due_date')[:10]),
        'stale_list': list(kpi_queryset('stale', scoped).select_related('supplier', 'assigned_accountant')
                           .order_by('last_activity')[:10]),
    }
