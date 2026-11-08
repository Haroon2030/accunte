'use strict';

/* ---------- ورقة الدفعة: every supplier of one batch on one sheet, one column per approval level ----------
   المورد | الرصيد الحالي | رصيد المخزون | 1 اقتراح خدمات الموردين | 2 اقتراح المشتريات وتعميده | 3 المدقق (قبول / رفض) | 4 التعميد النهائي (مع اقتراح مبلغ أو بدونه)
   Each role works only in its own column: it edits the amounts of the rows waiting at its level and approves (or, for the auditor, rejects)
   the selected rows in one go. Everything else is read-only. The server checks the level of every row again. */
const SHEET_LEVELS = [
  { role: 'services', head: 'اقتراح خدمات الموردين' },
  { role: 'purchasing', head: 'اقتراح مدير المشتريات وتعميده' },
  { role: 'auditor', head: 'قرار المدقق (قبول / رفض)' },
  { role: 'treasury', head: 'التعميد النهائي (مع اقتراح مبلغ أو بدونه)' }
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
  const [sel, setSel] = useState({});        // pk -> true
  const [edit, setEdit] = useState({});      // pk -> amount text typed in the row
  const [note, setNote] = useState('');
  const [errs, setErrs] = useState({});      // pk -> message from the server
  const [noteErr, setNoteErr] = useState('');
  const [busy, setBusy] = useState(false);
  const mine = rows.filter(function (x) { return x.canAct; });
  const chosen = mine.filter(function (x) { return sel[x.pk]; });
  const levels = chosen.map(function (x) { return x.status; }).filter(function (v, i, a) { return a.indexOf(v) === i; });
  const level = levels.length === 1 ? levels[0] : 0;
  const amountOf = function (x) { return edit[x.pk] != null ? edit[x.pk] : (x.amount == null ? '' : String(x.amount)); };
  const numOf = function (x) { const v = parseFloat(digitsOf(String(amountOf(x))).replace(/,/g, '')); return isNaN(v) ? 0 : v; };
  const chosenSum = chosen.reduce(function (a, x) { return a + numOf(x); }, 0);
  const allMine = mine.length > 0 && mine.every(function (x) { return sel[x.pk]; });
  const toggleAll = function () { const on = !allMine; const n = {}; if (on) mine.forEach(function (x) { n[x.pk] = true; }); setSel(n); };
  const setAmount = function (x, v) { setEdit(function (o) { const n = Object.assign({}, o); n[x.pk] = v; return n; }); setErrs(function (e) { if (!e[x.pk]) return e; const n = Object.assign({}, e); delete n[x.pk]; return n; }); };

  function run(action) {
    if (!chosen.length) { props.onToast('حدّد أمراً واحداً على الأقل من الأوامر التي بانتظارك.'); return; }
    if (!level) { props.onToast('حدّد أوامر من مستوى واحد في كل مرة.'); return; }
    if (action === 'reject' && !note.trim()) { setNoteErr('اكتب سبب الرفض.'); const el = document.getElementById('sh-note'); if (el) el.focus(); return; }
    setBusy(true); setErrs({}); setNoteErr('');
    props.onBulk(action, chosen.map(function (x) { return { pk: x.pk, fromStage: x.status, amount: amountOf(x) }; }), note).then(function () {
      setBusy(false); setSel({}); setEdit({}); setNote('');
    }, function (ex) {
      setBusy(false);
      if (ex.data && ex.data.rowErrors) setErrs(ex.data.rowErrors);
      props.onToast(ex.message);
    });
  }

  /* one level's cell in one row */
  function levelCell(x, k, cols) {
    const lv = k + 1, e = cols[k];
    if (x.status === lv && x.canAct) {
      return div({ className: 'shcell edit' },
        input({ type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', 'aria-label': 'المبلغ: ' + x.supplier, value: amountOf(x), onChange: function (ev) { setAmount(x, ev.target.value); } }),
        span({ className: 'shwho' }, lv === 4 ? 'غيّر المبلغ إن أردت اقتراح مبلغ آخر' : 'عدّل المبلغ إن أردت اقتراح مبلغ آخر'));
    }
    if (e) {
      return div({ className: 'shcell' },
        lv === 3 ? span({ className: 'pill ' + (e.action === 'reject' ? 'bad' : 'ok') }, e.action === 'reject' ? 'رفض' : 'قبول') : null,
        e.amount != null ? span({ className: 'mono' }, shNum(+e.amount)) : null,
        span({ className: 'shwho' }, e.by + (e.note && e.note.indexOf('ضمن الدفعة') !== 0 ? ' · ' + e.note : '')));
    }
    if (x.status === lv) return div({ className: 'shcell' }, span({ className: 'pill idle' }, span({ className: 'dot' }), 'بانتظار ' + PAY_STEPS[k].who));
    return div({ className: 'shcell' }, span({ className: 'muted' }, '—'));
  }

  const sum = function (f) { return rows.reduce(function (a, x) { const v = f(x); return a + (v == null ? 0 : v); }, 0); };
  const lvSum = function (k) { return sum(function (x) { const e = sheetCols(x)[k]; return e && e.amount != null && e.action !== 'reject' ? +e.amount : 0; }); };
  const steps = [1, 2, 3, 4, 5].map(function (s) { return rows.filter(function (x) { return x.status === s; }).length; });

  return section({ className: 'uformwrap pbform shsheet', 'aria-label': 'ورقة الدفعة ' + props.batch },
    div({ className: 'uformhead' }, h3(null, 'ورقة الدفعة ' + props.batch + ' · ' + rows.length + (rows.length === 1 ? ' مورد' : ' موردين')),
      button({ type: 'button', className: 'uformclose', 'aria-label': 'إغلاق', onClick: props.onClose }, h(Icon, { name: 'close', size: 18 }))),
    div({ className: 'shsteps' }, SHEET_LEVELS.map(function (l, k) { return span({ key: l.role, className: 'chip-batch' }, 'عند ' + PAY_STEPS[k].who + ': ' + steps[k]); }).concat([span({ key: 'p', className: 'chip-batch' }, 'تم السداد: ' + steps[4])])),
    div({ className: 'shbar' },
      mine.length ? [
        label({ key: 'a', className: 'checkrow' }, input({ type: 'checkbox', checked: allMine, onChange: toggleAll }), 'تحديد كل ما بانتظاري (' + mine.length + ')'),
        span({ key: 'n', className: 'muted small' }, chosen.length ? 'المحدد: ' + chosen.length + ' · ' + payMoney(chosenSum) : 'حدّد الأوامر التي تريد تنفيذ الإجراء عليها'),
        div({ key: 'f', className: 'field shnote' }, input({ id: 'sh-note', type: 'text', autoComplete: 'off', placeholder: level === 3 ? 'ملاحظة (سبب الرفض مطلوب عند الرفض)' : 'ملاحظة على الإجراء (اختياري)', 'aria-label': 'ملاحظة', value: note, onChange: function (e) { setNote(e.target.value); setNoteErr(''); } }), noteErr ? span({ className: 'err', role: 'alert' }, noteErr) : null),
        button({ key: 'ok', type: 'button', className: 'btn primary', disabled: busy || !chosen.length || !level, onClick: function () { run('advance'); } }, level ? PAY_STEPS[level - 1].act : 'نفّذ للمحدد'),
        level === 3 ? button({ key: 'no', type: 'button', className: 'btn ghost', style: { color: 'var(--bad)' }, disabled: busy || !chosen.length, onClick: function () { run('reject'); } }, 'رفض المحدد') : null
      ] : span({ className: 'muted small' }, 'لا يوجد في هذه الدفعة ما ينتظر إجراءك الآن. الأعمدة للعرض فقط.')),
    div({ className: 'tablewrap pbwrap' }, table({ className: 'dt pbtable shtable' },
      thead(null, tr(null, [h('span', { key: 'c' }, ''), 'المورد', 'الرصيد الحالي', 'رصيد المخزون'].map(function (t, i) { return th({ key: 'h' + i, scope: 'col' }, t); })
        .concat(SHEET_LEVELS.map(function (l, k) { return th({ key: l.role, scope: 'col', className: 'shlv' }, span({ className: 'shn' }, k + 1), l.head); }))
        .concat([th({ key: 'st', scope: 'col' }, 'الحالة')]))),
      tbody(null, rows.map(function (x) {
        const cols = sheetCols(x), er = errs[x.pk];
        return tr({ key: x.pk, className: er ? 'bad' : (x.canAct ? 'mine' : undefined) },
          td({ 'data-label': '', className: 'shchk' }, x.canAct ? input({ type: 'checkbox', 'aria-label': 'تحديد ' + x.supplier, checked: !!sel[x.pk], onChange: function (e) { const v = e.target.checked; setSel(function (o) { const n = Object.assign({}, o); if (v) n[x.pk] = true; else delete n[x.pk]; return n; }); } }) : null),
          td({ 'data-label': 'المورد', className: 'pbsup' }, strong({ style: { fontWeight: 600 } }, x.supplier), span({ className: 'hint' }, x.supplierCode + (x.method ? ' · ' + x.method : '') + (x.dueDate ? ' · ' + payDate(x.dueDate) : '')), er ? span({ className: 'err', role: 'alert' }, er) : null),
          td({ 'data-label': 'الرصيد الحالي', className: 'num' }, x.balance == null ? span({ className: 'muted' }, '—') : span({ className: 'mono' }, shNum(x.balance))),
          td({ 'data-label': 'رصيد المخزون', className: 'num' }, x.stockBalance == null ? span({ className: 'muted' }, '—') : span({ className: 'mono' }, shNum(x.stockBalance))),
          SHEET_LEVELS.map(function (l, k) { return td({ key: l.role, 'data-label': l.head, className: 'shlvc' + (x.status === k + 1 && x.canAct ? ' on' : '') }, levelCell(x, k, cols)); }),
          td({ 'data-label': 'الحالة' }, span({ className: 'pill ' + payTone(x) }, span({ className: 'dot' }), payLabel(x)), x.rejected ? span({ className: 'chip-late' }, 'أعادها المدقق') : null));
      })),
      h('tfoot', null, tr(null, td({ colSpan: 2, className: 'shtot' }, 'الإجمالي'),
        td({ className: 'num' }, span({ className: 'mono' }, shNum(sum(function (x) { return x.balance; })))),
        td({ className: 'num' }, span({ className: 'mono' }, shNum(sum(function (x) { return x.stockBalance; })))),
        [0, 1, 2, 3].map(function (k) { return td({ key: k, className: 'num' }, k === 2 ? null : span({ className: 'mono' }, shNum(lvSum(k)))); }),
        td(null, ''))))));
}
