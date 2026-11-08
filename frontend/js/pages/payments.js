'use strict';

/* ---------- السداد: four-level approval of the settlement that follows a finished reconciliation ----------
   1 supplier services proposes the payment  ->  2 purchasing manager approves (may propose another amount)
   ->  3 auditor approves or rejects (a rejection returns it to level 1)  ->  4 transfer officer gives the final approval and pays.
   A payment appears by itself once the reconciliation file was sent to the supplier. */
const PAY_STEPS = [
  { who: 'خدمات الموردين', title: 'اقتراح الدفعة', desc: 'تقترح خدمات الموردين المبلغ وطريقة السداد وترفعه للاعتماد.', doneDesc: 'رُفع الاقتراح إلى مدير المشتريات.', pill: 'عند خدمات الموردين', act: 'رفع الاقتراح لمدير المشتريات' },
  { who: 'مدير المشتريات', title: 'اعتماد مدير المشتريات', desc: 'يعتمد الدفعة أو يقترح مبلغاً مختلفاً ثم يحيلها للمدقق.', doneDesc: 'اعتمدها مدير المشتريات.', pill: 'عند مدير المشتريات', act: 'اعتماد وإحالة للمدقق' },
  { who: 'المدقق', title: 'تدقيق المدقق', desc: 'يعتمد الدفعة أو يرفضها مع السبب، وله اقتراح مبلغ آخر.', doneDesc: 'اعتمدها المدقق.', pill: 'عند المدقق', act: 'اعتماد وإحالة لمسؤول التحويل' },
  { who: 'مسؤول التحويل', title: 'التعميد النهائي والتحويل', desc: 'يعمّد الدفعة نهائياً فتُعدّ مسدّدة.', doneDesc: 'عُمّدت نهائياً وسُدّدت للمورد.', pill: 'عند مسؤول التحويل', act: 'تعميد نهائي' }
];
const PAY_PAID = 'تم السداد';
const PAY_METHODS = ['تحويل بنكي', 'شيك', 'نقداً', 'خصم من الحساب'];
const PAY_ACTION = { propose: 'اقترح', approve: 'اعتمد', reject: 'رفض', pay: 'عمّد نهائياً وحوّل' };
const payLabel = function (x) { return x.status === 5 ? PAY_PAID : PAY_STEPS[x.status - 1].pill; };
const payTone = function (x) { return x.status === 5 ? 'ok' : (x.rejected ? 'bad' : (x.status === 4 ? 'work' : 'warn')); };
const payLate = function (x) { return x.status < 5 && !!x.dueDate && new Date(x.dueDate + 'T23:59:59') < new Date(); };
const payMoney = function (n) { return n == null ? '—' : new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) + ' ر.س'; };
const payDate = function (s) { return s ? fmtDate(new Date(s.length > 10 ? s : s + 'T00:00:00')) : '—'; };

function PaymentPage(props) {
  const list = props.payments;
  const [sel, setSel] = useState(null);       // pk of the payment being handled
  const [f, setF] = useState(null);
  const [errs, setErrs] = useState({});
  const [busy, setBusy] = useState(false);
  const cur = sel ? list.filter(function (x) { return x.pk === sel; })[0] : null;
  const set = function (k, v) { setF(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); };
  function open(id) {
    const x = list.filter(function (r) { return r.id === id; })[0];
    if (!x) return;
    setErrs({}); setSel(x.pk);
    setF({ amount: x.amount == null ? '' : String(x.amount), method: x.method || '', dueDate: x.dueDate || '', note: '' });
    setTimeout(function () { const el = document.getElementById('pf-amount'); if (el && x.canAct) el.focus(); }, 0);
  }
  function fail(ex) {
    setBusy(false);
    const d = ex.data, known = { amount: 1, method: 1, dueDate: 1, note: 1 }, fe = {};
    if (d && typeof d === 'object' && !d.detail) Object.keys(d).forEach(function (k) { if (known[k]) fe[k] = [].concat(d[k])[0]; });
    if (Object.keys(fe).length) setErrs(fe); else props.onToast(ex.message);
  }
  const fields = function () { return { amount: f.amount, method: f.method, dueDate: f.dueDate, note: f.note, fromStage: cur.status }; };
  function save(e) {
    e.preventDefault();
    setBusy(true); setErrs({});
    props.onSave(cur.pk, fields()).then(function () { setBusy(false); props.onToast('حُفظت تعديلات ' + cur.id + '.'); }, fail);
  }
  function advance() {
    setBusy(true); setErrs({});
    const b = fields();
    props.onAdvance(cur.pk, b).then(function () { setBusy(false); setSel(null); }, fail);
  }
  function reject() {
    if (!f.note.trim()) { setErrs({ note: 'اكتب سبب الرفض.' }); const el = document.getElementById('pf-note'); if (el) el.focus(); return; }
    setBusy(true); setErrs({});
    props.onReject(cur.pk, fields()).then(function () { setBusy(false); setSel(null); }, fail);
  }

  const cols = [
    { key: 'id', label: 'رقم السداد', filter: 'text', val: function (x) { return x.id; }, render: function (x) { return span({ className: 'mono' }, x.id); } },
    { key: 'supplier', label: 'المورد', filter: 'text', val: function (x) { return x.supplier; }, render: function (x) { return strong({ style: { fontWeight: 600 } }, x.supplier); } },
    { key: 'request', label: 'طلب المطابقة', filter: 'text', val: function (x) { return x.request; }, render: function (x) { return span({ className: 'mono' }, x.request); } },
    { key: 'period', label: 'الفترة', filter: 'select', val: function (x) { return x.period; }, render: function (x) { return x.period; } },
    { key: 'amount', label: 'المبلغ', num: true, val: function (x) { return x.amount == null ? -1 : x.amount; }, xl: function (x) { return x.amount; }, render: function (x) { return x.amount == null ? span({ className: 'muted' }, 'لم يُحدَّد') : span({ className: 'mono' }, payMoney(x.amount)); } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: payLabel, val: function (x) { return x.status; },
      render: function (x) { return div({ className: 'cell-status' }, span({ className: 'pill ' + payTone(x) }, span({ className: 'dot' }), payLabel(x)), x.rejected ? span({ className: 'chip-late' }, 'أعادها المدقق') : null, payLate(x) ? h(LateChip) : null); } },
    { key: 'mine', label: 'دورك', filter: 'select', fv: function (x) { return x.canAct ? 'بانتظارك' : '—'; }, val: function (x) { return x.canAct ? 0 : 1; },
      render: function (x) { return x.canAct ? span({ className: 'pill work' }, span({ className: 'dot' }), 'بانتظارك') : span({ className: 'muted' }, '—'); } },
    { key: 'due', label: 'الاستحقاق', val: function (x) { return x.dueDate ? new Date(x.dueDate).getTime() : 0; }, xl: function (x) { return x.dueDate || ''; }, render: function (x) { return x.dueDate ? payDate(x.dueDate) : span({ className: 'muted' }, '—'); } },
    openCol(props.onDelete)
  ];
  const n = function (s) { return list.filter(function (x) { return x.status === s; }).length; };
  const mine = list.filter(function (x) { return x.canAct; }).length;
  const unpaid = list.filter(function (x) { return x.status < 5 && x.amount; }).reduce(function (a, x) { return a + x.amount; }, 0);
  const paid = list.filter(function (x) { return x.status === 5 && x.amount; }).reduce(function (a, x) { return a + x.amount; }, 0);
  const editable = !!cur && cur.canAct;
  const fld = function (id, lbl, ctl, k, hint, wide) {
    return div({ className: 'field' + (wide ? ' wide' : ''), key: k }, label({ htmlFor: id }, lbl), ctl, errs[k] ? span({ className: 'err', role: 'alert' }, errs[k]) : (hint ? span({ className: 'hint' }, hint) : null));
  };
  const lastBy = function (c, k) { const hs = (c.history || []).filter(function (e) { return e.role === ['services', 'purchasing', 'auditor', 'treasury'][k] && e.action !== 'reject'; }); return hs.length ? hs[hs.length - 1] : null; };

  return section({ className: 'svcpanel userspage payspage' },
    div({ className: 'svchead' },
      div(null, h2(null, 'السداد'), p({ className: 'muted small' }, 'تظهر أوامر السداد هنا تلقائياً بعد إرسال ملف المطابقة إلى المورد، وتمر بأربعة مستويات: خدمات الموردين، مدير المشتريات، المدقق، مسؤول التحويل.')),
      span({ className: 'paycount' }, list.length === 1 ? 'أمر واحد' : list.length + ' أوامر')),
    mine ? div({ className: 'alertbar', role: 'status' }, h(Icon, { name: 'alert' }), span(null, mine === 1 ? 'عندك أمر سداد واحد بانتظار إجرائك.' : 'عندك ' + mine + ' أوامر سداد بانتظار إجرائك.')) : null,
    div({ className: 'paystats' },
      div({ className: 'paysteps', role: 'group', 'aria-label': 'الأوامر حسب المستوى' },
        PAY_STEPS.map(function (st, k) { return [st.who, n(k + 1)]; }).concat([[PAY_PAID, n(5)]]).map(function (x) {
          return div({ key: x[0], className: 'paycell' + (x[1] ? ' on' : '') }, h('b', null, x[1]), span(null, x[0]));
        })),
      div({ className: 'paymoney', role: 'group', 'aria-label': 'المبالغ' },
        [['مستحق غير مسدّد', unpaid], ['إجمالي المسدّد', paid]].map(function (x) {
          return div({ key: x[0], className: 'paycell on' }, h('b', null, new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(x[1]), h('small', null, 'ر.س')), span(null, x[0]));
        }))),
    cur && f ? form({ className: 'uformwrap', onSubmit: save, noValidate: true },
      div({ className: 'uformhead' }, h3(null, 'أمر السداد ' + cur.id + ' · ' + cur.supplier),
        button({ type: 'button', className: 'uformclose', 'aria-label': 'إغلاق', onClick: function () { setSel(null); } }, h(Icon, { name: 'close', size: 18 }))),
      cur.rejected ? div({ className: 'confirmbar', role: 'alert' }, span(null, 'أعادها المدقق: ' + cur.history[cur.history.length - 1].note)) : null,
      ol({ className: 'stepper', style: { marginBottom: 14 } }, PAY_STEPS.map(function (s, i) {
        const k = i + 1, state = cur.status > k ? 'done' : (cur.status === k ? 'current' : 'todo');
        const e = state === 'done' ? lastBy(cur, i) : null;
        return li({ key: k, className: 'step ' + state }, div({ className: 'mark' }, state === 'done' ? h(Icon, { name: 'check', size: 14 }) : k),
          div(null, h4(null, s.title + ' · ' + s.who), div({ className: 'desc' }, state === 'done' ? s.doneDesc + (e ? ' ' + e.by + ' · ' + fmtDT(new Date(e.at)) : '') : s.desc)));
      })),
      cur.status === 5 ? div({ className: 'sinfo' }, dl(null, div({ className: 'sinfo-row' }, dt(null, 'تم السداد'), dd(null, 'عمّده نهائياً ' + cur.paidBy)))) : null,
      !editable && cur.status < 5 ? div({ className: 'sinfo', role: 'note' }, dl(null, div({ className: 'sinfo-row' }, dt(null, 'بانتظار'), dd(null, PAY_STEPS[cur.status - 1].who + ' (للعرض فقط عندك)')))) : null,
      div({ className: 'sinfo', role: 'group', 'aria-label': 'بيانات الطلب' }, dl(null,
        [['طلب المطابقة', cur.request, true], ['الفترة', cur.period], ['فرق المطابقة', cur.diff == null ? '—' : (cur.diff === 0 ? 'لا فروقات' : payMoney(cur.diff))]].map(function (r) {
          return div({ className: 'sinfo-row', key: r[0] }, dt(null, r[0]), dd(null, r[2] ? span({ className: 'mono' }, r[1]) : r[1]));
        }))),
      div({ className: 'uform' },
        fld('pf-amount', cur.status === 1 ? 'المبلغ المقترح (ر.س)' : 'المبلغ (ر.س) — يمكنك اقتراح مبلغ آخر', input({ id: 'pf-amount', type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', disabled: !editable, value: f.amount, onChange: function (e) { set('amount', e.target.value); } }), 'amount', cur.diff ? 'المقترح من فرق المطابقة: ' + payMoney(Math.abs(cur.diff)) : null),
        fld('pf-method', 'طريقة السداد', select({ id: 'pf-method', disabled: !editable, value: f.method, onChange: function (e) { set('method', e.target.value); } }, option({ value: '' }, 'اختر…'), PAY_METHODS.map(function (m) { return option({ key: m, value: m }, m); })), 'method'),
        fld('pf-dueDate', 'تاريخ الاستحقاق', input({ id: 'pf-dueDate', type: 'date', className: 'ltr', disabled: !editable, value: f.dueDate, onChange: function (e) { set('dueDate', e.target.value); } }), 'dueDate'),
        editable ? fld('pf-note', cur.status === 3 ? 'ملاحظة (سبب الرفض مطلوب عند الرفض)' : 'ملاحظة على هذا الإجراء (اختياري)', textarea({ id: 'pf-note', rows: 2, value: f.note, onChange: function (e) { set('note', e.target.value); } }), 'note', null, true) : null),
      (cur.history || []).length ? div({ className: 'tablewrap', style: { marginTop: 14 } }, table({ className: 'dt' },
        thead(null, tr(null, ['الوقت', 'الدور', 'الموظف', 'الإجراء', 'المبلغ', 'ملاحظة'].map(function (t) { return th({ key: t, scope: 'col' }, t); }))),
        tbody(null, cur.history.map(function (e, i) {
          return tr({ key: i }, td({ 'data-label': 'الوقت' }, fmtDT(new Date(e.at))), td({ 'data-label': 'الدور' }, ROLE_LABEL[e.role] || e.role), td({ 'data-label': 'الموظف' }, e.by),
            td({ 'data-label': 'الإجراء' }, span({ className: 'pill ' + (e.action === 'reject' ? 'bad' : e.action === 'pay' ? 'ok' : 'work') }, PAY_ACTION[e.action] || e.action)),
            td({ 'data-label': 'المبلغ' }, e.amount ? span({ className: 'mono' }, payMoney(+e.amount)) : '—'), td({ 'data-label': 'ملاحظة' }, e.note || '—'));
        })))) : null,
      editable ? div({ className: 'formactions' },
        button({ type: 'button', className: 'btn primary', disabled: busy, onClick: advance }, PAY_STEPS[cur.status - 1].act),
        cur.status === 3 ? button({ type: 'button', className: 'btn ghost', disabled: busy, style: { color: 'var(--bad)' }, onClick: reject }, 'رفض وإعادة لخدمات الموردين') : null,
        button({ type: 'submit', className: 'btn ghost', disabled: busy }, 'حفظ دون إحالة'),
        button({ type: 'button', className: 'btn ghost', onClick: function () { setSel(null); } }, 'إلغاء')) : null) : null,
    h(DataTable, { cols: cols, rows: list, dateFilter: { label: 'تاريخ الأمر', get: function (x) { return x.created ? new Date(x.created) : null; } }, exportName: 'السداد', onToast: props.onToast, onOpen: open, defaultSort: { key: 'mine', dir: 'asc' }, rowClass: function (x) { return x.canAct ? 'unread' : undefined; },
      empty: 'لا توجد أوامر سداد بعد. تظهر هنا تلقائياً عند إرسال ملف المطابقة إلى المورد.' }));
}
