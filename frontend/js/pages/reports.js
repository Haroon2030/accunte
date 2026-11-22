'use strict';

/* ---------- smart reports: supplier payment rows from multi-supplier uploads ---------- */
function reportLocalDate(d) {
  const p = function (n) { return (n < 10 ? '0' : '') + n; };
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
}
function reportPaidAt(payment) {
  const history = payment.history || [];
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].action === 'pay' && history[i].at) {
      const d = new Date(history[i].at);
      if (!isNaN(d.getTime())) return d;
    }
  }
  const reached = payment.reached || {};
  const d = new Date(reached['5'] || reached[5] || '');
  return !isNaN(d.getTime()) ? d : null;
}
function reportMoney(n) {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0);
}
function reportDateText(d, opts) {
  return new Intl.DateTimeFormat('ar-SA-u-ca-gregory', opts || { day: 'numeric', month: 'short', year: 'numeric' }).format(d);
}
function reportSelectOptions(values, placeholder) {
  return [option({ value: '' }, placeholder)].concat(values.map(function (v) { return option({ key: v, value: v }, v); }));
}

function SmartReportsPage(props) {
  const now = new Date();
  const initialFrom = reportLocalDate(new Date(now.getFullYear(), now.getMonth(), 1));
  const initialTo = reportLocalDate(now);
  const [draftFrom, setDraftFrom] = useState(initialFrom);
  const [draftTo, setDraftTo] = useState(initialTo);
  const [draftBranch, setDraftBranch] = useState('');
  const [draftBank, setDraftBank] = useState('');
  const [draftAccount, setDraftAccount] = useState('');
  const [from, setFrom] = useState(initialFrom);
  const [to, setTo] = useState(initialTo);
  const [branch, setBranch] = useState('');
  const [bank, setBank] = useState('');
  const [account, setAccount] = useState('');
  const [groupBy, setGroupBy] = useState('day');
  const [exportBusy, setExportBusy] = useState(false);
  const applyFilters = function (event) {
    event.preventDefault();
    setFrom(draftFrom); setTo(draftTo); setBranch(draftBranch); setBank(draftBank); setAccount(draftAccount);
  };

  // A batch is created only by the multi-supplier upload. Exclude unbatched
  // direct/manual payments even if they have reached final approval.
  const approvedSuppliers = props.payments.filter(function (p) { return p.status === 5 && !!p.batch; }).map(function (p) {
    const uploadedAt = p.created ? new Date(p.created) : null;
    return Object.assign({}, p, { uploadedAt: uploadedAt && !isNaN(uploadedAt.getTime()) ? uploadedAt : null, approvedAt: reportPaidAt(p) });
  }).filter(function (p) { return !!p.uploadedAt; });
  const branches = Array.from(new Set(approvedSuppliers.map(function (p) { return p.branch || 'غير محدد'; }))).sort(function (a, b) { return a.localeCompare(b, 'ar'); });
  const banks = Array.from(new Set(approvedSuppliers.map(function (p) { return p.bank || 'غير محدد'; }))).sort(function (a, b) { return a.localeCompare(b, 'ar'); });
  const accounts = Array.from(new Set(approvedSuppliers.map(function (p) { return p.bankSub || 'غير محدد'; }))).sort(function (a, b) { return a.localeCompare(b, 'ar'); });
  const fromDate = from ? new Date(from + 'T00:00:00') : null;
  const toDate = to ? new Date(to + 'T23:59:59.999') : null;
  const dimensionMatch = function (p) {
    return (!branch || (p.branch || 'غير محدد') === branch) &&
      (!bank || (p.bank || 'غير محدد') === bank) &&
      (!account || (p.bankSub || 'غير محدد') === account);
  };
  const rows = approvedSuppliers.filter(function (p) {
    return dimensionMatch(p) && (!fromDate || p.uploadedAt >= fromDate) && (!toDate || p.uploadedAt <= toDate);
  }).sort(function (a, b) { return b.uploadedAt - a.uploadedAt; });
  const total = rows.reduce(function (s, p) { return s + (+p.amount || 0); }, 0);
  const branchTotals = {};
  const accountTotals = {};
  const periods = {};
  rows.forEach(function (p) {
    const b = p.branch || 'غير محدد';
    const a = (p.bank || 'بنك غير محدد') + ' · ' + (p.bankSub || 'حساب غير محدد');
    branchTotals[b] = branchTotals[b] || { count: 0, amount: 0 };
    accountTotals[a] = accountTotals[a] || { count: 0, amount: 0, bank: p.bank || '—', latest: null };
    branchTotals[b].count += 1; branchTotals[b].amount += +p.amount || 0;
    accountTotals[a].count += 1; accountTotals[a].amount += +p.amount || 0;
    if (!accountTotals[a].latest || p.uploadedAt > accountTotals[a].latest) accountTotals[a].latest = p.uploadedAt;
    const key = groupBy === 'month' ? p.uploadedAt.getFullYear() + '-' + String(p.uploadedAt.getMonth() + 1).padStart(2, '0') : reportLocalDate(p.uploadedAt);
    periods[key] = periods[key] || { date: p.uploadedAt, count: 0, amount: 0 };
    periods[key].count += 1; periods[key].amount += +p.amount || 0;
  });
  const periodRows = Object.keys(periods).sort().map(function (k) { return Object.assign({ key: k }, periods[k]); });
  const maxPeriod = Math.max.apply(null, [1].concat(periodRows.map(function (p) { return p.amount; })));
  const branchRows = Object.keys(branchTotals).map(function (k) { return { name: k, count: branchTotals[k].count, amount: branchTotals[k].amount }; }).sort(function (a, b) { return b.amount - a.amount; });
  const accountRows = Object.keys(accountTotals).map(function (k) { return { name: k, bank: accountTotals[k].bank, count: accountTotals[k].count, amount: accountTotals[k].amount, latest: accountTotals[k].latest }; }).sort(function (a, b) { return b.amount - a.amount; });
  const branchMax = Math.max.apply(null, [1].concat(branchRows.map(function (x) { return x.amount; })));
  const accountCount = accountRows.length;
  const activeBranchCount = branchRows.length;

  let previousRows = [];
  if (fromDate && toDate && toDate >= fromDate) {
    const length = Math.max(1, toDate.getTime() - fromDate.getTime() + 1);
    const prevTo = new Date(fromDate.getTime() - 1);
    const prevFrom = new Date(fromDate.getTime() - length);
    previousRows = approvedSuppliers.filter(function (p) { return dimensionMatch(p) && p.uploadedAt >= prevFrom && p.uploadedAt <= prevTo; });
  }
  const previousTotal = previousRows.reduce(function (s, p) { return s + (+p.amount || 0); }, 0);
  const compare = function (current, previous) {
    if (!previous) return current ? 'لا توجد حركة في الفترة السابقة' : 'لا توجد حركة في الفترتين';
    const pct = Math.round((current - previous) / previous * 100);
    return (pct > 0 ? '↑ ' : pct < 0 ? '↓ ' : '') + Math.abs(pct) + '% عن الفترة السابقة';
  };
  const topAccount = accountRows[0];
  const batchCount = new Set(rows.map(function (p) { return p.batch; })).size;
  const filterSummary = [
    fromDate && toDate ? reportDateText(fromDate) + ' – ' + reportDateText(toDate)
      : fromDate ? 'من ' + reportDateText(fromDate)
        : toDate ? 'حتى ' + reportDateText(toDate) : 'جميع تواريخ الرفع',
    branch || 'كل الفروع', bank || 'كل البنوك', account || 'كل الحسابات'
  ];

  const exportCols = [
    { key: 'id', label: 'رقم أمر السداد', val: function (p) { return p.id; } },
    { key: 'batch', label: 'رقم الملف', val: function (p) { return p.batch || ''; } },
    { key: 'supplierCode', label: 'رمز المورد', val: function (p) { return p.supplierCode || ''; } },
    { key: 'supplier', label: 'المورد', val: function (p) { return p.supplier || ''; } },
    { key: 'uploadedAt', label: 'تاريخ رفع السجل', val: function (p) { return p.uploadedAt.getTime(); }, xl: function (p) { return xlDate(p.uploadedAt); } },
    { key: 'approvedAt', label: 'تاريخ التعميد النهائي', val: function (p) { return p.approvedAt ? p.approvedAt.getTime() : ''; }, xl: function (p) { return p.approvedAt ? xlDate(p.approvedAt) : ''; } },
    { key: 'branch', label: 'الفرع', val: function (p) { return p.branch || ''; } },
    { key: 'bank', label: 'البنك الرئيسي', val: function (p) { return p.bank || ''; } },
    { key: 'bankSub', label: 'الحساب البنكي', val: function (p) { return p.bankSub || ''; } },
    { key: 'reference', label: 'مرجع التحويل', val: function (p) { return p.reference || ''; } },
    { key: 'amount', label: 'المبلغ (ر.س)', val: function (p) { return +p.amount || 0; }, num: true }
  ];
  function exportReport() {
    setExportBusy(true);
    exportTableXlsx('تقرير-الموردين-المعتمدين-' + (to || reportLocalDate(new Date())) + '.xlsx', exportCols, rows)
      .then(function () { setExportBusy(false); }, function () { setExportBusy(false); if (props.onToast) props.onToast('تعذّر تصدير التقرير. تأكد من الاتصال بالإنترنت وأعد المحاولة.'); });
  }
  const tableCols = [
    { key: 'supplier', label: 'المورد', filter: 'text', val: function (p) { return p.supplier || ''; }, render: function (p) { return p.supplier || '—'; } },
    { key: 'batch', label: 'رقم الدفعة', filter: 'text', val: function (p) { return p.batch || ''; }, render: function (p) { return p.batch ? span({ className: 'mono' }, p.batch) : '—'; } },
    { key: 'supplierCode', label: 'رمز المورد', filter: 'text', val: function (p) { return p.supplierCode || ''; }, render: function (p) { return p.supplierCode || '—'; } },
    { key: 'uploadedAt', label: 'تاريخ الرفع', val: function (p) { return p.uploadedAt.getTime(); }, xl: function (p) { return xlDate(p.uploadedAt); }, render: function (p) { return reportDateText(p.uploadedAt, { day: 'numeric', month: 'short', year: 'numeric' }); } },
    { key: 'approvedAt', label: 'تاريخ التعميد', val: function (p) { return p.approvedAt ? p.approvedAt.getTime() : 0; }, xl: function (p) { return p.approvedAt ? xlDate(p.approvedAt) : ''; }, render: function (p) { return p.approvedAt ? reportDateText(p.approvedAt, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'; } },
    { key: 'branch', label: 'الفرع', filter: 'select', fv: function (p) { return p.branch || 'غير محدد'; }, val: function (p) { return p.branch || ''; }, render: function (p) { return p.branch || 'غير محدد'; } },
    { key: 'bank', label: 'البنك', val: function (p) { return p.bank || ''; }, render: function (p) { return p.bank || '—'; } },
    { key: 'bankSub', label: 'الحساب البنكي', val: function (p) { return p.bankSub || ''; }, render: function (p) { return p.bankSub || '—'; } },
    { key: 'id', label: 'رقم الأمر', filter: 'text', val: function (p) { return p.id || ''; }, render: function (p) { return span({ className: 'mono' }, p.id || '—'); } },
    { key: 'reference', label: 'مرجع التحويل', val: function (p) { return p.reference || ''; }, render: function (p) { return p.reference ? span({ className: 'mono' }, p.reference) : '—'; } },
    { key: 'amount', label: 'المبلغ', val: function (p) { return +p.amount || 0; }, xl: function (p) { return +p.amount || 0; }, num: true, render: function (p) { return span({ className: 'mono' }, reportMoney(p.amount) + ' ر.س'); } }
  ];

  return section({ className: 'smart-reports stack' },
    header({ className: 'report-head' },
      div({ className: 'report-heading' }, span({ className: 'report-heading-icon' }, h(Icon, { name: 'chart', size: 26 })),
        div(null, h2(null, 'التقارير الذكية'), p(null, 'سجلات الموردين من دفعات السداد متعددة الموردين بعد التعميد النهائي.'))),
      div({ className: 'report-actions noprint' },
        button({ type: 'button', className: 'btn ghost sm', disabled: exportBusy || !rows.length, onClick: exportReport }, h(Icon, { name: 'download', size: 15 }), exportBusy ? 'جارٍ التصدير…' : 'تصدير Excel'),
        button({ type: 'button', className: 'btn ghost sm', onClick: function () { window.print(); } }, h(Icon, { name: 'print', size: 15 }), 'طباعة')),
      div({ className: 'report-scope' }, strong(null, 'نطاق الرفع المعروض'),
        filterSummary.map(function (value, i) { return span({ key: i }, value); }))),
    form({ className: 'panel report-filters noprint', onSubmit: applyFilters },
      h3(null, 'تصفية التقرير'),
      div({ className: 'report-filter-grid' },
        label({ className: 'report-field' }, 'الرفع من', input({ type: 'date', value: draftFrom, max: draftTo || undefined, onChange: function (e) { setDraftFrom(e.target.value); } })),
        label({ className: 'report-field' }, 'الرفع إلى', input({ type: 'date', value: draftTo, min: draftFrom || undefined, onChange: function (e) { setDraftTo(e.target.value); } })),
        label({ className: 'report-field' }, 'الفرع', select({ value: draftBranch, onChange: function (e) { setDraftBranch(e.target.value); } }, reportSelectOptions(branches, 'كل الفروع'))),
        label({ className: 'report-field' }, 'البنك الرئيسي', select({ value: draftBank, onChange: function (e) { setDraftBank(e.target.value); } }, reportSelectOptions(banks, 'كل البنوك'))),
        label({ className: 'report-field' }, 'الحساب البنكي', select({ value: draftAccount, onChange: function (e) { setDraftAccount(e.target.value); } }, reportSelectOptions(accounts, 'كل الحسابات')))),
      div({ className: 'report-filter-submit' },
        button({ type: 'submit', className: 'btn primary sm' }, h(Icon, { name: 'search', size: 15 }), 'عرض التقرير'))),
    div({ className: 'report-kpis' },
      h(ReportKpi, { icon: 'chart', tone: 'teal', label: 'إجمالي المبالغ المعتمدة', value: reportMoney(total), unit: 'ر.س', note: fromDate && toDate ? compare(total, previousTotal) : null }),
      h(ReportKpi, { icon: 'file', tone: 'blue', label: 'سجلات الموردين المعتمدة', value: rows.length, note: 'عدد الدفعات: ' + batchCount }),
      h(ReportKpi, { icon: 'sort', tone: 'amber', label: 'الفروع في النتائج', value: activeBranchCount }),
      h(ReportKpi, { icon: 'key', tone: 'violet', label: 'الحسابات المستخدمة', value: accountCount, note: topAccount ? 'الأعلى: ' + topAccount.name : 'لا توجد حسابات في النطاق' })),
    div({ className: 'report-insights' },
      section({ className: 'panel report-trend' },
        div({ className: 'report-panel-head' },
          div(null, h3(null, 'المبالغ المعتمدة حسب تاريخ الرفع'), p({ className: 'muted small' }, 'المبالغ بالريال السعودي')),
          div({ className: 'report-granularity noprint', role: 'group', 'aria-label': 'تجميع الرسم البياني' },
            button({ type: 'button', 'aria-pressed': groupBy === 'day', onClick: function () { setGroupBy('day'); } }, 'يومي'),
            button({ type: 'button', 'aria-pressed': groupBy === 'month', onClick: function () { setGroupBy('month'); } }, 'شهري'))),
        periodRows.length ? div({ className: 'report-chart', role: 'img', 'aria-label': 'مخطط الموردين المعتمدين حسب ' + (groupBy === 'day' ? 'يوم الرفع' : 'شهر الرفع') }, periodRows.map(function (x) {
          const height = Math.max(4, Math.round(x.amount / maxPeriod * 100));
          const labelText = reportDateText(x.date, groupBy === 'month' ? { month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short' });
          return div({ className: 'report-bar-col', key: x.key, title: labelText + ': ' + reportMoney(x.amount) + ' ر.س' },
            span({ className: 'report-bar-value' }, reportMoney(x.amount)), div({ className: 'report-bar-track' }, h('i', { style: { height: height + '%' } })), span({ className: 'report-bar-label' }, labelText));
        })) : p({ className: 'report-empty' }, 'لا توجد بيانات زمنية ضمن هذه التصفية.')),
      section({ className: 'panel report-branches' },
        div({ className: 'report-panel-head' }, div(null, h3(null, 'الموردون حسب الفرع'), p({ className: 'muted small' }, 'مرتبة حسب إجمالي المبلغ المعتمد')), span({ className: 'report-panel-total' }, activeBranchCount + ' فروع')),
        branchRows.length ? ul({ className: 'report-rank' }, branchRows.map(function (x) {
          return li({ key: x.name }, div({ className: 'report-rank-copy' }, strong(null, x.name), span({ className: 'report-rank-amount' }, reportMoney(x.amount) + ' ر.س'), span({ className: 'muted small' }, 'عدد السجلات: ' + x.count)),
            div({ className: 'report-rank-track' }, h('i', { style: { width: Math.max(4, x.amount / branchMax * 100) + '%' } })));
        })) : p({ className: 'report-empty' }, 'اختر فترة تحتوي على تحويلات معتمدة.'))),
    section({ className: 'panel report-accounts' },
      div({ className: 'report-panel-head' }, div(null, h3(null, 'ملخص الحسابات البنكية'), p({ className: 'muted small' }, 'عدد السجلات وإجمالي المبالغ حسب الحساب')), span({ className: 'report-panel-total' }, 'عدد الحسابات: ' + accountCount)),
      accountRows.length ? div({ className: 'report-account-grid' }, accountRows.map(function (x) {
        return div({ className: 'report-account', key: x.name }, span({ className: 'report-bank-name' }, x.bank), strong({ className: 'report-account-name' }, x.name),
          span({ className: 'report-account-amount mono' }, reportMoney(x.amount) + ' ر.س'), span({ className: 'muted small' }, 'عدد السجلات: ' + x.count + ' · آخر رفع ' + reportDateText(x.latest, { day: 'numeric', month: 'short' })));
      })) : p({ className: 'report-empty' }, 'لا توجد حسابات بنكية ضمن النطاق المحدد.')),
    section({ className: 'panel report-transfers' },
      div({ className: 'report-panel-head' }, div(null, h3(null, 'سجلات الموردين'), p({ className: 'muted small' }, 'تاريخ الرفع والتعميد النهائي لكل سجل')), span({ className: 'report-panel-total' }, 'عدد السجلات: ' + rows.length)),
      h(DataTable, { cols: tableCols, rows: rows, pageSize: 20, hideExport: true, defaultSort: { key: 'uploadedAt', dir: 'desc' }, empty: 'لا توجد سجلات معتمدة تطابق عوامل التصفية.' })));
}

function ReportKpi(props) {
  return div({ className: 'report-kpi tone-' + props.tone },
    span({ className: 'report-kpi-icon' }, h(Icon, { name: props.icon, size: 18 })),
    span({ className: 'report-kpi-label' }, props.label),
    div({ className: 'report-kpi-reading' }, strong({ className: 'report-kpi-value', dir: 'ltr' }, props.value),
      props.unit ? span({ className: 'report-kpi-unit' }, props.unit) : null),
    props.note ? span({ className: 'report-kpi-note' }, props.note) : null);
}
