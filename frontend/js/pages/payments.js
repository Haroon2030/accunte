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
  const [batchOpen, setBatchOpen] = useState(false);
  const [sheet, setSheet] = useState('');      // batch number whose sheet is open
  const [editDoc, setEditDoc] = useState('');  // batch number whose basic data is being edited
  const cur = sel ? list.filter(function (x) { return x.pk === sel; })[0] : null;
  const set = function (k, v) { setF(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); };
  /* a document opens its table: every supplier of the batch, the approvals inside each row */
  function open(id) {
    const d = list.filter(function (x) { return (x.batch || x.id) === id; })[0];
    if (!d) return;
    setBatchOpen(false); setEditDoc(''); setSel(null); setSheet(d.batch || '');
    if (d.batch) setTimeout(function () { const el = document.querySelector('.shsheet'); if (el && el.scrollIntoView) el.scrollIntoView({ block: 'start' }); }, 60);
  }
  function fail(ex) {
    setBusy(false);
    const d = ex.data, known = { amount: 1, method: 1, dueDate: 1, note: 1, balance: 1, stockBalance: 1 }, fe = {};
    if (d && typeof d === 'object' && !d.detail) Object.keys(d).forEach(function (k) { if (known[k]) fe[k] = [].concat(d[k])[0]; });
    if (Object.keys(fe).length) setErrs(fe); else props.onToast(ex.message);
  }
  const fields = function () { return { amount: f.amount, method: f.method, dueDate: f.dueDate, note: f.note, branch: f.branch, costCenter: f.costCenter, bank: f.bank, bankSub: f.bankSub, balance: f.balance, stockBalance: f.stockBalance, fromStage: cur.status }; };
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

  /* the table lists documents: every batch is one document (many suppliers inside); an order without a batch is its own document */
  const uniq = function (xs) { return xs.filter(function (v, k, a) { return v && a.indexOf(v) === k; }); };
  const groups = {};
  list.forEach(function (x) { const k = x.batch || x.id; (groups[k] = groups[k] || []).push(x); });
  const docs = Object.keys(groups).map(function (k) {
    const os = groups[k], first = os.slice().sort(function (a, b) { return new Date(a.created) - new Date(b.created); })[0];
    const h0 = (first.history || [])[0];
    const branches = uniq(os.map(function (x) { return x.branch; }));
    const sts = uniq(os.map(function (x) { return x.status; }));
    return { id: k, orders: os, n: os.length, names: uniq(os.map(function (x) { return x.supplier; })).sort(function (a, b) { return a.localeCompare(b, 'ar'); }), by: h0 ? h0.by : '', created: new Date(first.created),
      branch: !branches.length ? '' : (branches.length === 1 ? branches[0] : 'عدة فروع'),
      status: sts.length === 1 ? sts[0] : 0, paid: os.filter(function (x) { return x.status === 5; }).length,
      mine: os.some(function (x) { return x.canAct; }), rejected: os.some(function (x) { return x.rejected; }), late: os.some(payLate) };
  });
  /* services (and the admin) may edit while nobody is past purchasing's turn; the admin may always delete */
  const isBatchDoc = function (d) { return !!d.orders[0].batch; };      // only documents made by "إضافة سداد متعدد"
  const canEditDoc = function (d) { return isBatchDoc(d) && props.canBatch && d.orders.every(function (x) { return x.status <= 2; }); };
  const canDeleteDoc = function (d) { return isBatchDoc(d) && (props.isAdmin || canEditDoc(d)); };
  function removeDoc(d) {
    if (!window.confirm('حذف الوثيقة ' + d.id + ' مع ' + (d.n === 1 ? 'أمرها' : 'أوامرها الـ ' + d.n) + ' نهائياً؟ لا يمكن التراجع عن الحذف.')) return;
    props.onDeleteBatch(d.id).then(function () { if (sheet === d.id) setSheet(''); if (editDoc === d.id) setEditDoc(''); }, function (ex) { props.onToast(ex.message); });
  }
  /* the state of a document: one step when all its orders are there, otherwise "in approval" with how many are paid */
  const docLabel = function (d) { return d.status === 5 ? PAY_PAID : (d.status ? PAY_STEPS[d.status - 1].pill : 'قيد الاعتماد'); };
  const docTone = function (d) { return d.status === 5 ? 'ok' : (d.rejected ? 'bad' : (d.status === 4 ? 'work' : 'warn')); };
  const cols = [
    /* the supplier's name; a document with several shows the first two and how many more. The document number stays in the tooltip and in search. */
    { key: 'id', label: 'المورد', filter: 'text', val: function (d) { return d.names[0] || ''; }, fv: function (d) { return d.names.join(' ') + ' ' + d.id; },
      render: function (d) { return strong({ style: { fontWeight: 600 }, title: d.id + ' · ' + d.names.join('، ') }, d.names.slice(0, 2).join('، ') + (d.names.length > 2 ? ' +' + (d.names.length - 2) : '')); } },
    { key: 'by', label: 'الشخص المدخل', filter: 'select', fv: function (d) { return d.by || '—'; }, val: function (d) { return d.by; }, render: function (d) { return d.by || span({ className: 'muted' }, '—'); } },
    { key: 'branch', label: 'الفرع', filter: 'select', fv: function (d) { return d.branch || '—'; }, val: function (d) { return d.branch; }, render: function (d) { return d.branch || span({ className: 'muted' }, '—'); } },
    { key: 'created', label: 'تاريخ الإدخال', val: function (d) { return d.created.getTime(); }, xl: function (d) { return xlDate(d.created); }, render: function (d) { return fmtDT(d.created); } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: function (d) { return docLabel(d); }, val: function (d) { return d.status; },
      render: function (d) { return div({ className: 'cell-status' }, span({ className: 'pill ' + docTone(d) }, span({ className: 'dot' }), docLabel(d)), d.status === 0 ? span({ className: 'muted small' }, d.paid + ' من ' + d.n + ' مسدّد') : null, d.rejected ? span({ className: 'chip-late' }, 'فيها مرفوض') : null, d.late ? h(LateChip) : null); } },
    { key: 'act', label: 'إجراءات', render: function (d) {
      const e = canEditDoc(d), x = canDeleteDoc(d);
      if (!e && !x) return span({ className: 'muted' }, '—');
      return div({ className: 'rowacts' },
        e ? button({ type: 'button', className: 'abtn edit', title: 'تعديل', 'aria-label': 'تعديل ' + d.id, onClick: function (ev) { ev.stopPropagation(); setBatchOpen(false); setSheet(''); setSel(null); setEditDoc(d.id); setTimeout(function () { const el = document.querySelector('.pbform'); if (el && el.scrollIntoView) el.scrollIntoView({ block: 'start' }); }, 60); } }, h(Icon, { name: 'pencil', size: 16 }), span({ className: 'abl' }, 'تعديل')) : null,
        x ? button({ type: 'button', className: 'abtn stop', title: 'حذف', 'aria-label': 'حذف ' + d.id, onClick: function (ev) { ev.stopPropagation(); removeDoc(d); } }, h(Icon, { name: 'trash', size: 16 }), span({ className: 'abl' }, 'حذف')) : null);
    } }
  ];
  const n = function (s) { return list.filter(function (x) { return x.status === s; }).length; };
  const mine = list.filter(function (x) { return x.canAct; }).length;
  const unpaid = list.filter(function (x) { return x.status < 5 && x.amount; }).reduce(function (a, x) { return a + x.amount; }, 0);
  const paid = list.filter(function (x) { return x.status === 5 && x.amount; }).reduce(function (a, x) { return a + x.amount; }, 0);
  const batches = {};
  list.forEach(function (x) { if (x.batch) batches[x.batch] = (batches[x.batch] || 0) + 1; });
  const batchIds = Object.keys(batches).sort().reverse();
  const editable = !!cur && cur.canAct;
  const fld = function (id, lbl, ctl, k, hint, wide) {
    return div({ className: 'field' + (wide ? ' wide' : ''), key: k }, label({ htmlFor: id }, lbl), ctl, errs[k] ? span({ className: 'err', role: 'alert' }, errs[k]) : (hint ? span({ className: 'hint' }, hint) : null));
  };
  const lastBy = function (c, k) { const hs = (c.history || []).filter(function (e) { return e.role === ['services', 'purchasing', 'auditor', 'treasury'][k] && e.action !== 'reject'; }); return hs.length ? hs[hs.length - 1] : null; };

  return section({ className: 'svcpanel userspage payspage' },
    div({ className: 'svchead' },
      div(null, h2(null, 'السداد'), p({ className: 'muted small' }, 'أوامر السداد التي تُضاف من «إضافة سداد متعدد»، وتمر بأربعة مستويات: خدمات الموردين، مدير المشتريات، المدقق، مسؤول التحويل.')),
      div({ className: 'payhead-acts' }, batchIds.length ? select({ className: 'batchpick', 'aria-label': 'فتح ورقة دفعة', value: sheet, onChange: function (e) { setSel(null); setBatchOpen(false); setEditDoc(''); setSheet(e.target.value); } }, option({ value: '' }, 'ورقة دفعة…'), batchIds.map(function (b) { return option({ key: b, value: b }, b + ' (' + batches[b] + ')'); })) : null,
        span({ className: 'paycount' }, docs.length === 1 ? 'وثيقة واحدة' : docs.length + ' وثائق'),
        props.canBatch ? button({ type: 'button', className: 'btn primary', onClick: function () { setSel(null); setSheet(''); setEditDoc(''); setBatchOpen(true); } }, h(Icon, { name: 'plus' }), 'إضافة سداد متعدد') : null)),
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
    editDoc && groups[editDoc] ? h(PaymentDocEdit, { key: editDoc, batch: editDoc, orders: groups[editDoc], lookups: props.lookups, onSave: function (data) { return props.onEditBatch(editDoc, data); }, onClose: function () { setEditDoc(''); }, onToast: props.onToast }) : null,
    sheet ? h(PaymentSheet, { batch: sheet, payments: list, onBulk: props.onBulk, onClose: function () { setSheet(''); }, onToast: props.onToast }) : null,
    batchOpen && props.canBatch ? h(PaymentBatchForm, { suppliers: props.suppliers, lookups: props.lookups, onSubmit: props.onBatch, onClose: function () { setBatchOpen(false); }, onToast: props.onToast }) : null,
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
      div({ className: 'sinfo', role: 'group', 'aria-label': cur.request ? 'بيانات الطلب' : 'بيانات الدفعة' }, dl(null,
        (cur.request ? [['طلب المطابقة', cur.request, true], ['الفترة', cur.period], ['فرق المطابقة', cur.diff == null ? '—' : (cur.diff === 0 ? 'لا فروقات' : payMoney(cur.diff))]]
          : [['الدفعة', cur.batch || '—', true], ['المورد', cur.supplier + (cur.supplierCode ? ' · ' + cur.supplierCode : '')], ['ملاحظة', cur.note || '—']]).map(function (r) {
          return div({ className: 'sinfo-row', key: r[0] }, dt(null, r[0]), dd(null, r[2] ? span({ className: 'mono' }, r[1]) : r[1]));
        }))),
      div({ className: 'uform' },
        fld('pf-amount', cur.status === 1 ? 'المبلغ المقترح (ر.س)' : 'المبلغ (ر.س) — يمكنك اقتراح مبلغ آخر', input({ id: 'pf-amount', type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', disabled: !editable, value: f.amount, onChange: function (e) { set('amount', e.target.value); } }), 'amount', cur.diff ? 'المقترح من فرق المطابقة: ' + payMoney(Math.abs(cur.diff)) : null),
        fld('pf-method', 'طريقة السداد', select({ id: 'pf-method', disabled: !editable, value: f.method, onChange: function (e) { set('method', e.target.value); } }, option({ value: '' }, 'اختر…'), (function () { const ms = lkNames(props.lookups, 'method'); if (f.method && ms.indexOf(f.method) === -1) ms.unshift(f.method); return ms; }()).map(function (m) { return option({ key: m, value: m }, m); })), 'method'),
        fld('pf-dueDate', 'تاريخ الاستحقاق', input({ id: 'pf-dueDate', type: 'date', className: 'ltr', disabled: !editable, value: f.dueDate, onChange: function (e) { set('dueDate', e.target.value); } }), 'dueDate'),
        fld('pf-balance', 'الرصيد الحالي (ر.س)', input({ id: 'pf-balance', type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', disabled: !editable || cur.status !== 1, value: f.balance, onChange: function (e) { set('balance', e.target.value); } }), 'balance'),
        fld('pf-stockBalance', 'رصيد المخزون (ر.س)', input({ id: 'pf-stockBalance', type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', disabled: !editable || cur.status !== 1, value: f.stockBalance, onChange: function (e) { set('stockBalance', e.target.value); } }), 'stockBalance'),
        PB_DIMS.map(function (d) { return fld('pf-' + d[0], d[1], h(ComboPicker, { id: 'pf-' + d[0], items: lkItems(lkActive(props.lookups, d[0])), value: f[d[0]], disabled: !editable, ariaLabel: d[1], emptyText: 'لا توجد قيم. أضفها من صفحة «التهيئة».', noMatch: 'ليس في القائمة.', onText: function (v) { set(d[0], v); }, onPick: function (it) { set(d[0], it.label); } }), d[0]); }),
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
    h(DataTable, { cols: cols, rows: docs, dateFilter: { label: 'تاريخ الإدخال', get: function (d) { return d.created; } }, exportName: 'وثائق-السداد', inlineHead: true, onToast: props.onToast, onOpen: open, defaultSort: { key: 'created', dir: 'desc' }, rowClass: function (d) { return d.mine ? 'unread' : undefined; },
      empty: props.canBatch ? 'لا توجد وثائق سداد بعد. أضف أول وثيقة من زر «إضافة سداد متعدد».' : 'لا توجد وثائق سداد بعد. تضيفها خدمات الموردين من «إضافة سداد متعدد».' }));
}
