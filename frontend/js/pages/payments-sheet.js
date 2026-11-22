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
  const [exportBusy, setExportBusy] = useState(false);
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
  function exportBatch() {
    setExportBusy(true);
    rcLoad('xlsx').then(function () {
      const headers = ['رقم الدفعة', 'رمز المورد', 'اسم المورد', 'الفرع', 'مركز التكلفة', 'البنك الرئيسي', 'الحساب التحليلي', 'الرصيد الحالي', 'رصيد المخزون', 'طريقة الدفع', 'تاريخ الاستحقاق', 'حالة السداد', 'الأولوية'];
      SHEET_LEVELS.forEach(function (l) { headers.push('نتيجة ' + l.head, 'مبلغ ' + l.head, 'الموظف', 'التاريخ', 'ملاحظة'); });
      const numeric = function (v) {
        if (v == null || String(v).trim() === '') return '';
        const n = Number(String(v).replace(/,/g, '').trim());
        return isFinite(n) ? n : String(v);
      };
      const body = rows.map(function (x) {
        const approvals = sheetCols(x), out = [props.batch, x.supplierCode || '', x.supplier || '', x.branch || '', x.costCenter || '', x.bank || '', x.bankSub || '', numeric(val(x, 'balance', x.balance)), numeric(val(x, 'stock', x.stockBalance)), x.method || '', x.dueDate || '', payLabel(x), payPriority(x).label];
        SHEET_LEVELS.forEach(function (l, k) {
          const e = approvals[k];
          out.push(e ? (PAY_ACTION[e.action] || e.action) : (x.status === k + 1 ? 'بانتظار الإجراء' : '—'));
          out.push(e && e.amount != null ? +e.amount : (x.status === k + 1 ? numeric(val(x, 'amount', x.amount)) : ''));
          out.push(e ? e.by || '' : '');
          out.push(e && e.at ? fmtDT(new Date(e.at)) : '');
          out.push(e ? e.note || '' : '');
        });
        return out;
      });
      const aoa = [headers].concat(body), ws = XLSX.utils.aoa_to_sheet(aoa);
      ws['!cols'] = headers.map(function (_, ci) {
        const longest = aoa.reduce(function (n, row) { return Math.max(n, String(row[ci] == null ? '' : row[ci]).length); }, 0);
        return { wch: Math.min(Math.max(longest + 2, 12), 34) };
      });
      ws['!autofilter'] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: aoa.length - 1, c: headers.length - 1 } }) };
      headers.forEach(function (head, ci) {
        if (head.indexOf('مبلغ ') !== 0 && ['الرصيد الحالي', 'رصيد المخزون'].indexOf(head) === -1) return;
        for (let ri = 1; ri < aoa.length; ri++) {
          const cell = XLSX.utils.encode_cell({ r: ri, c: ci });
          if (ws[cell] && typeof ws[cell].v === 'number') ws[cell].z = '#,##0.00';
        }
      });
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'الدفعة');
      wb.Workbook = { Sheets: [{ RTL: true }], Views: [{ RTL: true }] };
      const safeBatch = String(props.batch).replace(/[<>:"/\\|?*]/g, '-');
      XLSX.writeFile(wb, 'دفعة-' + safeBatch + '.xlsx');
      setExportBusy(false);
    }).catch(function (ex) {
      setExportBusy(false);
      props.onToast(ex && ex.message ? ex.message : 'تعذّر تصدير الدفعة إلى Excel.');
    });
  }
  function printBatch() {
    try {
      const body = document.body;
      const cleanup = function () { body.classList.remove('printing-batch'); window.removeEventListener('afterprint', cleanup); };
      body.classList.add('printing-batch');
      window.addEventListener('afterprint', cleanup, { once: true });
      window.print();
      setTimeout(cleanup, 1500);
    } catch (e) { document.body.classList.remove('printing-batch'); props.onToast('تعذّرت الطباعة في هذا المتصفح.'); }
  }
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
    div({ className: 'sh-actions noprint' },
      button({ type: 'button', className: 'btn ghost sm', onClick: printBatch }, h(Icon, { name: 'print', size: 15 }), 'طباعة'),
      button({ type: 'button', className: 'btn ghost sm', disabled: exportBusy, onClick: exportBatch }, h(Icon, { name: 'download', size: 15 }), exportBusy ? 'جارٍ تجهيز Excel…' : 'تصدير Excel')),
    div({ className: 'tablewrap pbwrap' }, table({ className: 'dt pbtable shtable' },
      thead(null, tr(null, ['رقم المورد', 'المورد', 'الرصيد', 'المخزون', 'طريقة الدفع'].map(function (t, i) { return th({ key: 'h' + i, scope: 'col' }, t); })
        .concat(SHEET_LEVELS.map(function (l, k) { return th({ key: l.role, scope: 'col', className: 'shlv' }, span({ className: 'shn' }, k + 1), l.head); }))
        .concat([th({ key: 'st', scope: 'col' }, 'الحالة')]))),
      tbody(null, rows.map(function (x) {
        const cols = sheetCols(x), er = errs[x.pk], priority = payPriority(x);
        const rowClass = 'pay-priority-' + priority.key + (er ? ' bad' : x.canAct ? ' mine' : '');
        return tr({ key: x.pk, className: rowClass },
          td({ 'data-label': 'رقم المورد', className: 'shcode' }, x.supplierCode ? span({ className: 'mono' }, x.supplierCode) : span({ className: 'muted' }, '—')),
          td({ 'data-label': 'المورد', className: 'pbsup' }, strong({ style: { fontWeight: 600 } }, x.supplier), span({ className: 'hint' }, x.id), er ? span({ className: 'err', role: 'alert' }, er) : null),
          numCell(x, 'balance', 'balance', 'الرصيد'),
          numCell(x, 'stockBalance', 'stock', 'المخزون'),
          td({ 'data-label': 'طريقة الدفع', className: 'shmethod' }, x.method ? x.method : span({ className: 'muted' }, '—')),
          SHEET_LEVELS.map(function (l, k) { return td({ key: l.role, 'data-label': l.head, className: 'shlvc' + (x.status === k + 1 && x.canAct ? ' on' : '') }, levelCell(x, k, cols)); }),
          td({ 'data-label': 'الحالة', className: 'shstat' }, h(PayPriorityPill, { level: priority }),
            span({ className: 'pill ' + payTone(x) }, span({ className: 'dot' }), payLabel(x)), x.rejected ? span({ className: 'chip-late' }, 'أعادها المدقق') : null,
            x.dueDate ? span({ className: 'shmeth' }, 'استحقاق ' + payDate(x.dueDate)) : null));
      })),
      h('tfoot', null, tr(null, td({ colSpan: 2, className: 'shtot', 'data-label': 'الإجمالي' }, 'الإجمالي'),
        td({ className: 'num', 'data-label': 'إجمالي الرصيد' }, span({ className: 'mono' }, shNum(sum(function (x) { return x.balance; })))),
        td({ className: 'num', 'data-label': 'إجمالي المخزون' }, span({ className: 'mono' }, shNum(sum(function (x) { return x.stockBalance; })))),
        td({ className: 'sum-blank' }, ''),
        [0, 1, 2, 3].map(function (k) { return td({ key: k, className: 'num' + (k === 2 ? ' sum-blank' : ''), 'data-label': k === 2 ? undefined : 'إجمالي ' + SHEET_LEVELS[k].head }, k === 2 ? null : span({ className: 'mono' }, shNum(lvSum(k)))); }),
        td({ className: 'sum-blank' }, ''))))));
}

/* Edit a supplier's proposal from its document row. */
const PAYMENT_ROW_FIELDS = [
  ['amount', 'المبلغ المقترح (ر.س)', 'decimal'],
  ['balance', 'الرصيد الحالي', 'decimal'],
  ['stockBalance', 'رصيد المخزون', 'decimal'],
  ['priority', 'الأولوية', 'priority'],
  ['method', 'طريقة السداد', 'lookup'],
  ['dueDate', 'تاريخ الاستحقاق', 'date']
].concat(PB_DIMS.map(function (dimension) { return [dimension[0], dimension[1], 'lookup']; }));

function paymentRowDraft(order) {
  const values = {};
  PAYMENT_ROW_FIELDS.forEach(function (field) {
    const key = field[0];
    values[key] = key === 'priority' ? payPriority(order).key : (order[key] == null ? '' : String(order[key]));
  });
  return { pk: order.pk, stage: order.status, initial: values, values: values };
}

function PaymentRowEditor(props) {
  const [draft, setDraft] = useState(function () { return paymentRowDraft(props.orders[0]); });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);
  const order = props.orders.find(function (item) { return item.pk === draft.pk; });

  useEffect(function () {
    const editor = ref.current;
    if (editor) {
      editor.focus({ preventScroll: true });
      editor.scrollIntoView({ block: 'start', inline: 'nearest' });
    }
  }, []);

  function setField(key, value) {
    setDraft(function (previous) {
      return Object.assign({}, previous, { values: Object.assign({}, previous.values, { [key]: value }) });
    });
    setError(null);
  }

  function submit(event) {
    event.preventDefault();
    if (busy || !order) return;
    const changes = { fromStage: draft.stage };
    PAYMENT_ROW_FIELDS.forEach(function (field) {
      const key = field[0];
      if (draft.values[key] !== draft.initial[key]) changes[key] = draft.values[key];
    });
    if (Object.keys(changes).length === 1) { props.onClose(); return; }
    setBusy(true);
    setError(null);
    props.onSave(draft.pk, changes).then(props.onClose, function (ex) {
      setBusy(false);
      setError(ex);
    });
  }

  function renderField(field) {
    const [key, text, type] = field;
    const id = 'pay-row-' + draft.pk + '-' + key;
    const value = draft.values[key];
    const controlProps = {
      id: id, value: value, required: key === 'amount' || key === 'method',
      onChange: function (event) { setField(key, event.target.value); }
    };
    let control;
    if (type === 'priority') {
      control = select(controlProps, PAY_PRIORITIES.map(function (level) {
        return option({ key: level.key, value: level.key }, level.label);
      }));
    } else if (type === 'lookup') {
      const values = lkNames(props.lookups, key);
      if (draft.initial[key] && values.indexOf(draft.initial[key]) === -1) values.unshift(draft.initial[key]);
      control = select(controlProps, option({ value: '' }, key === 'method' ? 'اختر طريقة السداد' : 'غير محدد'),
        values.map(function (name) { return option({ key: name, value: name }, name); }));
    } else {
      control = input(Object.assign(controlProps, { type: type === 'date' ? 'date' : 'text', className: 'ltr',
        inputMode: type === 'decimal' ? 'decimal' : undefined, autoComplete: 'off' }));
    }
    const message = error && error.data && error.data[key];
    return div({ className: 'field', key: key }, label({ htmlFor: id }, text), control,
      message ? span({ className: 'err', role: 'alert' }, [].concat(message)[0]) : null);
  }

  return form({ className: 'pay-row-editor', ref: ref, tabIndex: -1, onSubmit: submit, 'aria-label': 'تعديل سطر السداد' },
    h3(null, 'تعديل سطر السداد'),
    props.orders.length > 1 || !order
      ? div({ className: 'field' }, label({ htmlFor: 'pay-row-supplier' }, 'اختر سطر المورد'),
        select({ id: 'pay-row-supplier', value: order ? order.pk : '', disabled: busy, onChange: function (event) {
          const next = props.orders.find(function (item) { return String(item.pk) === event.target.value; });
          if (next) { setDraft(paymentRowDraft(next)); setError(null); }
        } }, !order ? option({ value: '', disabled: true }, 'اختر موردًا') : null,
        props.orders.map(function (item) { return option({ key: item.pk, value: item.pk }, item.supplier + ' · ' + item.id); })))
      : p({ className: 'muted small' }, order.supplier + ' · ' + order.id),
    error ? p({ className: 'err', role: 'alert' }, error.message) : null,
    order ? h('fieldset', { className: 'uform', disabled: busy, 'aria-label': 'بيانات السطر' }, PAYMENT_ROW_FIELDS.map(renderField)) : null,
    div({ className: 'formactions' },
      order ? button({ type: 'submit', className: 'btn primary sm', disabled: busy }, busy ? 'جارٍ الحفظ…' : 'حفظ السطر') : null,
      button({ type: 'button', className: 'btn ghost sm', disabled: busy, onClick: props.onClose }, 'إلغاء')));
}

