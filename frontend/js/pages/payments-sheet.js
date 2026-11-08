'use strict';

/* ---------- ورقة الدفعة: every supplier of one batch in one table, the approvals inside each row ----------
   المورد | الرصيد الحالي | رصيد المخزون | 1 اقتراح خدمات الموردين | 2 اقتراح المشتريات وتعميده | 3 المدقق (قبول / رفض) | 4 الاعتماد النهائي
   In every row the column of the level that is waiting holds the controls: an amount (propose another one if you wish) and the button of that
   level. Each role sees controls only in the rows waiting at its own level; everything else is read-only. The server checks every action again. */
const SHEET_LEVELS = [
  { role: 'services', head: 'اقتراح الخدمات', act: 'رفع الاقتراح' },
  { role: 'purchasing', head: 'اعتماد المشتريات', act: 'اعتماد' },
  { role: 'auditor', head: 'قرار المدقق', act: 'قبول' },
  { role: 'treasury', head: 'الاعتماد النهائي', act: 'اعتماد نهائي' }
];
const shNum = function (n) { return n == null ? '—' : new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n); };

/* what each level did last: a rejection clears the later levels (the round starts again) but stays visible in the auditor's column */
function sheetCols(p) {
  const c = [null, null, null, null];
  (p.history || []).forEach(function (e) {
    const lv = e.level || ({ services: 1, purchasing: 2, auditor: 3, treasury: 4 })[e.role];
    if (!lv) return;
    if (e.action === 'reject') { c[1] = null; c[3] = null; c[2] = e; } else c[lv - 1] = e;
  });
  return c;
}

function PaymentSheet(props) {
  const rows = props.payments.filter(function (x) { return x.batch === props.batch; }).sort(function (a, b) { return a.supplier.localeCompare(b.supplier, 'ar'); });
  const [edit, setEdit] = useState({});        // pk -> { amount, balance, stock } typed in the row
  const [rejecting, setRejecting] = useState({});   // pk -> reason text while the auditor is writing it
  const [errs, setErrs] = useState({});        // pk -> message
  const [busy, setBusy] = useState({});        // pk -> true while a request is on its way
  const val = function (x, k, fallback) { const e = edit[x.pk]; return e && e[k] != null ? e[k] : (fallback == null ? '' : String(fallback)); };
  const flag = function (setter, x, v) { setter(function (o) { const n = Object.assign({}, o); if (v == null) delete n[x.pk]; else n[x.pk] = v; return n; }); };
  const setVal = function (x, k, v) {
    setEdit(function (o) { const n = Object.assign({}, o); const row = Object.assign({}, n[x.pk]); row[k] = v; n[x.pk] = row; return n; });
    flag(setErrs, x, null);
  };

  /* one action on one row: the same bulk endpoint, with a single item */
  function act(x, action, note) {
    flag(setBusy, x, true); flag(setErrs, x, null);
    const item = { pk: x.pk, fromStage: x.status, amount: val(x, 'amount', x.amount) };
    if (x.status === 1) { item.balance = val(x, 'balance', x.balance); item.stockBalance = val(x, 'stock', x.stockBalance); }
    props.onBulk(action, [item], note).then(function () {
      flag(setBusy, x, null); flag(setRejecting, x, null);
      setEdit(function (o) { const n = Object.assign({}, o); delete n[x.pk]; return n; });
    }, function (ex) {
      flag(setBusy, x, null);
      const re = ex.data && ex.data.rowErrors;
      flag(setErrs, x, (re && re[x.pk]) || ex.message);
    });
  }

  /* one level's cell in one row */
  function levelCell(x, k, cols) {
    const lv = k + 1, e = cols[k];
    if (x.status === lv && x.canAct) {
      const rj = rejecting[x.pk];
      return div({ className: 'shcell edit' },
        input({ type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', 'aria-label': 'المبلغ: ' + x.supplier, value: val(x, 'amount', x.amount), onChange: function (ev) { setVal(x, 'amount', ev.target.value); } }),
        rj != null ? [
          input({ key: 'r', type: 'text', autoComplete: 'off', autoFocus: true, placeholder: 'سبب الرفض', 'aria-label': 'سبب الرفض: ' + x.supplier, value: rj, onChange: function (ev) { flag(setRejecting, x, ev.target.value); },
            onKeyDown: function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); if (rj.trim()) act(x, 'reject', rj); } else if (ev.key === 'Escape') flag(setRejecting, x, null); } }),
          div({ key: 'b', className: 'shbtns' },
            button({ type: 'button', className: 'btn sm shno', disabled: !!busy[x.pk] || !rj.trim(), onClick: function () { act(x, 'reject', rj); } }, 'تأكيد الرفض'),
            button({ type: 'button', className: 'btn ghost sm', onClick: function () { flag(setRejecting, x, null); } }, 'إلغاء'))
        ] : div({ className: 'shbtns' },
          button({ type: 'button', className: 'btn primary sm', disabled: !!busy[x.pk], onClick: function () { act(x, 'advance'); } }, SHEET_LEVELS[k].act),
          lv === 3 ? button({ type: 'button', className: 'btn ghost sm shno', disabled: !!busy[x.pk], onClick: function () { flag(setRejecting, x, ''); } }, 'رفض') : null));
    }
    if (e) {
      const who = e.by + (e.note && e.note.indexOf('ضمن الدفعة') !== 0 ? ' · ' + e.note : '');   // who did it (and why), cut with … in the cell and complete on hover
      return div({ className: 'shcell' },
        lv === 3 ? span({ className: 'pill ' + (e.action === 'reject' ? 'bad' : 'ok') }, e.action === 'reject' ? 'رفض' : 'قبول') : (lv === 4 ? span({ className: 'pill ok' }, 'معتمد') : null),
        e.amount != null ? span({ className: 'mono' }, shNum(+e.amount)) : null,
        span({ className: 'shwho', title: who }, who));
    }
    if (x.status === lv) return div({ className: 'shcell' }, span({ className: 'pill idle' }, span({ className: 'dot' }), 'بانتظار ' + PAY_STEPS[k].who));
    return div({ className: 'shcell' }, span({ className: 'muted' }, '—'));
  }

  const sum = function (f) { return rows.reduce(function (a, x) { const v = f(x); return a + (v == null ? 0 : v); }, 0); };
  const lvSum = function (k) { return sum(function (x) { const e = sheetCols(x)[k]; return e && e.amount != null && e.action !== 'reject' ? +e.amount : 0; }); };
  /* the two balances: typed in the row while supplier services holds it, read-only otherwise */
  const numCell = function (x, key, k, label) {
    if (x.status === 1 && x.canAct) return td({ key: key, 'data-label': label, className: 'num' }, input({ type: 'text', inputMode: 'decimal', className: 'ltr shin', autoComplete: 'off', 'aria-label': label + ': ' + x.supplier, value: val(x, k, x[key]), onChange: function (ev) { setVal(x, k, ev.target.value); } }));
    return td({ key: key, 'data-label': label, className: 'num' }, x[key] == null ? span({ className: 'muted' }, '—') : span({ className: 'mono' }, shNum(x[key])));
  };

  /* the batch's basic data: the same for every supplier of the file (the defaults chosen when it was uploaded); when rows differ, say so */
  const baseData = [['branch', 'الفرع'], ['costCenter', 'مركز التكلفة'], ['bank', 'البنك الرئيسي'], ['bankSub', 'الحساب (البنك التحليلي)']].map(function (d) {
    const seen = rows.map(function (x) { return x[d[0]]; }).filter(function (v, i, a2) { return v && a2.indexOf(v) === i; });
    return { key: d[0], label: d[1], text: !seen.length ? '' : (seen.length === 1 ? seen[0] : 'عدة قيم (' + seen.length + ')'), title: seen.join('، ') };
  });
  return section({ className: 'uformwrap pbform shsheet', 'aria-label': 'جدول الدفعة ' + props.batch },
    div({ className: 'uformhead' }, h3(null, 'الدفعة ' + props.batch + ' · ' + rows.length + (rows.length === 1 ? ' مورد' : ' موردين')),
      button({ type: 'button', className: 'uformclose', 'aria-label': 'إغلاق', onClick: props.onClose }, h(Icon, { name: 'close', size: 18 }))),
    dl({ className: 'shmeta', 'aria-label': 'البيانات الأساسية للدفعة' }, baseData.map(function (d) {
      return div({ key: d.key, className: 'shmeta-c' }, dt(null, d.label), dd({ title: d.title || undefined }, d.text || span({ className: 'muted' }, '—')));
    })),
    div({ className: 'tablewrap pbwrap' }, table({ className: 'dt pbtable shtable' },
      thead(null, tr(null, ['رقم المورد', 'المورد', 'الرصيد', 'المخزون', 'طريقة الدفع'].map(function (t, i) { return th({ key: 'h' + i, scope: 'col' }, t); })
        .concat(SHEET_LEVELS.map(function (l, k) { return th({ key: l.role, scope: 'col', className: 'shlv' }, span({ className: 'shn' }, k + 1), l.head); }))
        .concat([th({ key: 'st', scope: 'col' }, 'الحالة')]))),
      tbody(null, rows.map(function (x) {
        const cols = sheetCols(x), er = errs[x.pk];
        return tr({ key: x.pk, className: er ? 'bad' : (x.canAct ? 'mine' : undefined) },
          td({ 'data-label': 'رقم المورد', className: 'shcode' }, x.supplierCode ? span({ className: 'mono' }, x.supplierCode) : span({ className: 'muted' }, '—')),
          td({ 'data-label': 'المورد', className: 'pbsup' }, strong({ style: { fontWeight: 600 } }, x.supplier), span({ className: 'hint' }, x.id), er ? span({ className: 'err', role: 'alert' }, er) : null),
          numCell(x, 'balance', 'balance', 'الرصيد'),
          numCell(x, 'stockBalance', 'stock', 'المخزون'),
          td({ 'data-label': 'طريقة الدفع', className: 'shmethod' }, x.method ? x.method : span({ className: 'muted' }, '—')),
          SHEET_LEVELS.map(function (l, k) { return td({ key: l.role, 'data-label': l.head, className: 'shlvc' + (x.status === k + 1 && x.canAct ? ' on' : '') }, levelCell(x, k, cols)); }),
          td({ 'data-label': 'الحالة', className: 'shstat' }, span({ className: 'pill ' + payTone(x) }, span({ className: 'dot' }), payLabel(x)), x.rejected ? span({ className: 'chip-late' }, 'أعادها المدقق') : null,
            x.dueDate ? span({ className: 'shmeth' }, 'استحقاق ' + payDate(x.dueDate)) : null));
      })),
      h('tfoot', null, tr(null, td({ colSpan: 2, className: 'shtot' }, 'الإجمالي'),
        td({ className: 'num' }, span({ className: 'mono' }, shNum(sum(function (x) { return x.balance; })))),
        td({ className: 'num' }, span({ className: 'mono' }, shNum(sum(function (x) { return x.stockBalance; })))),
        td(null, ''),
        [0, 1, 2, 3].map(function (k) { return td({ key: k, className: 'num' }, k === 2 ? null : span({ className: 'mono' }, shNum(lvSum(k)))); }),
        td(null, ''))))));
}

/* ---------- editing a document: its basic data, applied to every order of the batch ---------- */
function PaymentDocEdit(props) {
  const first = props.orders[0] || {};
  const lk = props.lookups || {};
  const names = function (k) { return lkNames(lk, k); };
  const [c, setC] = useState({ method: first.method || '', dueDate: first.dueDate || '', branch: first.branch || '', costCenter: first.costCenter || '', bank: first.bank || '', bankSub: first.bankSub || '' });
  const [errs, setErrs] = useState({});
  const [busy, setBusy] = useState(false);
  const set = function (k, v) { setC(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); setErrs(function (e) { const n = Object.assign({}, e); delete n[k]; return n; }); };
  const fields = PB_DIMS.concat([['method', 'طريقة السداد']]);
  function submit(e) {
    e.preventDefault();
    const er = {};
    fields.forEach(function (d) { const v = c[d[0]].trim(); if (v && names(d[0]).indexOf(v) === -1 && v !== (first[d[0]] || '')) er[d[0]] = 'اختر ' + d[1] + ' من القائمة.'; });
    setErrs(er);
    if (Object.keys(er).length) { props.onToast('اختر الحقول من القوائم المعروضة.'); return; }
    setBusy(true);
    props.onSave(c).then(function () { setBusy(false); props.onClose(); }, function (ex) { setBusy(false); props.onToast(ex.message); });
  }
  return form({ className: 'uformwrap pbform', onSubmit: submit, noValidate: true },
    div({ className: 'uformhead' }, h3(null, 'تعديل الوثيقة ' + props.batch + ' · ' + props.orders.length + (props.orders.length === 1 ? ' مورد' : ' موردين')),
      button({ type: 'button', className: 'uformclose', 'aria-label': 'إغلاق', onClick: props.onClose }, h(Icon, { name: 'close', size: 18 }))),
    p({ className: 'muted small' }, 'تُطبَّق هذه البيانات على كل أوامر الوثيقة. لتعديل المبالغ والاعتماد افتح جدول الوثيقة.'),
    div({ className: 'uform' },
      fields.map(function (d) {
        return div({ className: 'field', key: d[0] }, label({ htmlFor: 'de-' + d[0] }, d[1]),
          h(ComboPicker, { id: 'de-' + d[0], items: lkItems(lkActive(lk, d[0])), value: c[d[0]], ariaLabel: d[1], emptyText: 'لا توجد قيم. أضفها من صفحة «التهيئة».', noMatch: 'ليس في القائمة.',
            onText: function (v) { set(d[0], v); }, onPick: function (it) { set(d[0], it.label); } }),
          errs[d[0]] ? span({ className: 'err', role: 'alert' }, errs[d[0]]) : null);
      }),
      div({ className: 'field' }, label({ htmlFor: 'de-due' }, 'تاريخ الاستحقاق'),
        input({ id: 'de-due', type: 'date', className: c.dueDate ? '' : 'empty', value: c.dueDate, onChange: function (e) { set('dueDate', e.target.value); } }))),
    div({ className: 'formactions' },
      button({ type: 'submit', className: 'btn primary', disabled: busy }, 'حفظ التعديلات'),
      button({ type: 'button', className: 'btn ghost', onClick: props.onClose }, 'إلغاء')));
}

