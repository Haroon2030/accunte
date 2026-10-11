"""
لوحة المدير المالي: المؤشرات، التفاصيل، وتصديرها (Excel / صفحة طباعة PDF).
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.branches.models import Branch
from apps.core.access import AUDIT_VIEW_ROLES, role_required

from . import kpis, services
from .views import _xl

executive_required = role_required(*AUDIT_VIEW_ROLES)


def _context(request):
    period = request.GET.get('period', kpis.DEFAULT_PERIOD)
    if period not in kpis.PERIODS:
        period = kpis.DEFAULT_PERIOD
    branch = request.GET.get('branch', '')
    branch_id = int(branch) if branch.isdigit() else None
    data = kpis.build(services.visible_cases(request.user), period, branch_id)
    data['loads'] = services.accountant_loads()
    data['load_max'] = max([u.open_count for u in data['loads']] + [1])
    data['request_rows'], data['request_rows_max'] = kpis.request_stage_rows(period)
    data.update({
        'period': period, 'branch_id': branch_id,
        'period_label': {'30': 'آخر 30 يومًا', '90': 'آخر 90 يومًا', '365': 'آخر سنة', 'all': 'كل الفترات'}[period],
        'branch_name': Branch.objects.filter(pk=branch_id).values_list('name', flat=True).first() if branch_id else 'كل الفروع',
        'scope_qs': f'period={period}' + (f'&branch={branch_id}' if branch_id else ''),
        'now': timezone.localtime(),
    })
    return data


@login_required
@executive_required
def executive_dashboard(request):
    ctx = _context(request)
    ctx.update({'page_title': 'لوحة المدير المالي', 'branches': Branch.objects.all(),
                'periods': [('30', 'آخر 30 يومًا'), ('90', 'آخر 90 يومًا'), ('365', 'آخر سنة'), ('all', 'كل الفترات')]})
    return render(request, 'pages/reconciliation/executive.html', ctx)


@login_required
@executive_required
def executive_print(request):
    ctx = _context(request)
    log_action(AuditLog.Action.EXPORT, entity_type='reconciliation.Dashboard', entity_repr='تصدير لوحة المدير المالي (PDF)',
               new={'period': ctx['period'], 'branch': ctx['branch_id']})
    return render(request, 'pages/reconciliation/executive_print.html', ctx)


@login_required
@executive_required
def executive_export_excel(request):
    from apps.core.excel_export import ModernExcelBuilder
    ctx = _context(request)
    meta = [('الفترة', ctx['period_label']), ('الفرع', ctx['branch_name'])]

    c = ctx['counts']
    d = ctx['discrepancy']
    avg = ctx['avg_resolution']
    kpi_rows = [[label, c[key]] for key, label in kpis.KPI_LABELS.items()]
    kpi_rows += [
        ['متوسط زمن الحل (أيام)', avg['days'] if avg else '-'],
        ['حالات منتهية المحسوبة في المتوسط', ctx['resolved_n']],
        ['نسبة الحالات ذات الفروقات %', d['rate']],
        ['بنود فروقات غير مسوّاة', d['unresolved_items']],
        ['إجمالي فروقات غير مسوّاة (ر.س)', float(d['unresolved_amount'])],
        ['مقترحات بانتظار القرار', ctx['proposals']['pending_count']],
        ['مقترحات متأخرة القرار', ctx['proposals']['stale_count']],
        ['طلبات الخدمة المستلمة', ctx['requests']['total']],
        ['طلبات الخدمة المفتوحة', ctx['requests']['open']],
        ['طلبات الخدمة المتأخرة', ctx['requests']['overdue']],
        ['طلبات الخدمة المصعَّدة', ctx['requests']['escalated']],
        ['متوسط زمن حل الطلبات (ساعة)', ctx['requests']['avg_resolution']['hours'] if ctx['requests']['avg_resolution'] else '-'],
    ]
    builder = ModernExcelBuilder('لوحة المدير المالي', sheet_name='المؤشرات')
    start = builder.write_report_header(2, meta)
    builder.write_table(start, ['المؤشر', 'القيمة'], kpi_rows, col_widths=[44, 18])

    ws = builder.add_sheet('الحالات حسب الحالة')
    builder.write_sheet_table(ws, 'توزيع الحالات', ['الحالة', 'العدد'],
                              [[label, n] for _, label, n in ctx['status_rows']], col_widths=[30, 14], meta_items=meta)

    ws = builder.add_sheet('أحمال المحاسبين')
    builder.write_sheet_table(
        ws, 'أحمال المحاسبين', ['المحاسب', 'مفتوحة', 'متأخرة', 'عاجلة'],
        [[_xl(u.get_full_name() or u.get_username()), u.open_count, u.overdue_count, u.urgent_count] for u in ctx['loads']],
        col_widths=[28, 12, 12, 12], meta_items=meta)

    ws = builder.add_sheet('مقترحات الدفع')
    p = ctx['proposals']
    builder.write_sheet_table(
        ws, 'مقترحات الدفع حسب الحالة', ['الحالة', 'العدد', 'الإجمالي (ر.س)'],
        [[label, v['count'], float(v['total'])] for _, label, v in p['by_status']],
        col_widths=[26, 12, 20], meta_items=meta, totals_row=['الإجمالي', p['grand_count'], float(p['grand_total'])])

    for sheet, title, key in (('متأخرة', 'الحالات المتأخرة (أول 10)', 'overdue_list'),
                              ('راكدة', 'الحالات الراكدة (أول 10)', 'stale_list')):
        ws = builder.add_sheet(sheet)
        builder.write_sheet_table(
            ws, title, ['الرقم', 'المورد', 'المحاسب', 'الاستحقاق'],
            [[x.reference, _xl(x.supplier.name), _xl(x.assigned_accountant.get_username()) if x.assigned_accountant else '-',
              f'{x.due_date:%Y/%m/%d}' if x.due_date else '-'] for x in ctx[key]],
            col_widths=[18, 34, 18, 14], meta_items=meta)

    log_action(AuditLog.Action.EXPORT, entity_type='reconciliation.Dashboard', entity_repr='تصدير لوحة المدير المالي (Excel)',
               new={'period': ctx['period'], 'branch': ctx['branch_id']})
    return builder.to_response('cfo_dashboard')
