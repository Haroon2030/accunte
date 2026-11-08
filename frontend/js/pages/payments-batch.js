'use strict';

/* ---------- السداد المتعدد: several suppliers in one file ----------
   Supplier services (or the admin) fills the rows by hand or imports an Excel / CSV file, and uploads them together.
   Every row becomes a payment order with a shared batch number and goes straight to the purchasing manager. All rows or none. */
const PB_HEADERS = {
  code: ['رمز المورد', 'كود المورد', 'الرمز', 'الكود', 'code', 'supplier code'],
  name: ['المورد', 'اسم المورد', 'name', 'supplier', 'supplier name'],
  amount: ['المبلغ', 'القيمة', 'amount', 'value'],
  method: ['طريقة السداد', 'طريقة الدفع', 'method', 'payment method'],
  due: ['تاريخ الاستحقاق', 'الاستحقاق', 'due', 'due date'],
  note: ['ملاحظة', 'ملاحظات', 'note', 'notes'],
  branch: ['الفرع', 'branch'],
  bank: ['البنك الرئيسي', 'البنك', 'bank', 'main bank'],
  bankSub: ['البنك التحليلي', 'تحليلي', 'bank sub', 'sub bank', 'analytical bank'],
  costCenter: ['مركز التكلفة', 'مركز تكلفة', 'cost center', 'cost centre'],
  balance: ['الرصيد الحالي', 'الرصيد', 'balance', 'current balance'],
  stockBalance: ['رصيد المخزون', 'المخزون', 'stock balance', 'stock', 'inventory balance']
};
/* accounting dimensions: key (same as the server) and label. Set once for the file, each row may change them. */
const PB_DIMS = [['branch', 'الفرع'], ['costCenter', 'مركز التكلفة'], ['bank', 'البنك الرئيسي'], ['bankSub', 'البنك التحليلي']];
/* comparison key: no diacritics or tatweel, and the usual spelling variants are one letter (أ إ آ = ا, ى = ي, ة = ه), so «افق» finds «الأفق» */
const pbNorm = function (v) { return String(v == null ? '' : v).replace(/[ً-ٟـ]/g, '').replace(/[أإآٱ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه').trim().toLowerCase(); };
const pbIso = function (d) { const p = function (n) { return (n < 10 ? '0' : '') + n; }; return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); };
/* a date typed in the file: a real date, an Excel serial number, yyyy-mm-dd or dd/mm/yyyy */
function pbDate(v) {
  if (v == null || v === '') return '';
  if (v instanceof Date && !isNaN(v)) return pbIso(v);
  if (typeof v === 'number' && window.XLSX) { const c = XLSX.SSF.parse_date_code(v); return c ? pbIso(new Date(c.y, c.m - 1, c.d)) : ''; }
  const s = digitsOf(String(v)).replace(/\//g, '-');
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s);
  if (m) return pbIso(new Date(+m[1], +m[2] - 1, +m[3]));
  m = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(s);
  return m ? pbIso(new Date(+m[3], +m[2] - 1, +m[1])) : '';
}

/* the lists of the settings page (التهيئة): active names of one kind, and the same as items for a ComboPicker */
const lkNames = function (lookups, kind) { return ((lookups || {})[kind] || []).filter(function (l) { return l.active; }).map(function (l) { return l.name; }); };
const lkActive = function (lookups, kind) { return ((lookups || {})[kind] || []).filter(function (l) { return l.active; }); };
const lkItems = function (list) { return list.map(function (l) { return { id: l.id, label: l.name, title: l.name, meta: l.code ? 'رقم ' + l.code : '', search: [l.name, l.code || ''] }; }); };

/* search box with suggestions: type, and pick from the matches (mouse, or arrows + Enter).
   items: [{id, label (what the field shows once picked), title, meta, search: [texts to match]}].
   The list is drawn on the page (not inside a scrolling table), so it is never cut off. */
function ComboPicker(props) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const [box, setBox] = useState(null);
  const ref = useRef(null);
  const q = pbNorm(props.value);
  const exact = props.items.some(function (it) { return pbNorm(it.label) === q; });     // already chosen: no list
  const matches = props.items.filter(function (it) { return !q || it.search.some(function (t) { return pbNorm(t).indexOf(q) !== -1; }); }).slice(0, 8);
  const shown = open && !exact && !props.disabled;
  function openList() {
    if (!ref.current || props.disabled) return;
    const r = ref.current.getBoundingClientRect();
    setBox({ top: r.bottom + 4, left: r.left, width: Math.max(r.width, 260) });
    setOpen(true);
  }
  useEffect(function () {
    if (!open) return undefined;
    const close = function () { setOpen(false); };
    /* a click anywhere outside this box and its list closes it, even when the field never got a blur event */
    const outside = function (e) { if (!(ref.current && ref.current.contains(e.target)) && !(e.target.closest && e.target.closest('.sugbox'))) setOpen(false); };
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    document.addEventListener('mousedown', outside);
    return function () { window.removeEventListener('scroll', close, true); window.removeEventListener('resize', close); document.removeEventListener('mousedown', outside); };
  }, [open]);
  const pick = function (it) { props.onPick(it); setOpen(false); };
  function onKey(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); if (!shown) { setHi(0); openList(); } else setHi(function (h0) { return Math.min(h0 + 1, matches.length - 1); }); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi(function (h0) { return Math.max(h0 - 1, 0); }); }
    else if (e.key === 'Enter' && shown && matches[hi]) { e.preventDefault(); pick(matches[hi]); }
    else if (e.key === 'Escape' || e.key === 'Tab') setOpen(false);
  }
  const list = shown && box ? ReactDOM.createPortal(
    div({ className: 'sugbox', role: 'listbox', style: { top: box.top, left: box.left, width: box.width } },
      matches.length ? matches.map(function (it, i) {
        return div({ key: it.id, role: 'option', 'aria-selected': i === hi, className: 'sug' + (i === hi ? ' on' : ''),
          onMouseDown: function (e) { e.preventDefault(); pick(it); }, onMouseEnter: function () { setHi(i); } },
          strong(null, it.title), it.meta ? span({ className: 'sugmeta' }, it.meta) : null);
      }) : div({ className: 'sug none' }, props.items.length ? (props.noMatch || 'لا يوجد ما يطابق بحثك.') : (props.emptyText || 'القائمة فارغة.'))),
    document.body) : null;
  return span({ className: 'sugwrap' },
    input({ id: props.id, ref: ref, type: 'text', role: 'combobox', 'aria-expanded': shown, 'aria-autocomplete': 'list', autoComplete: 'off', disabled: props.disabled, placeholder: props.placeholder || 'ابحث أو اختر', 'aria-label': props.ariaLabel, value: props.value,
      onChange: function (e) { props.onText(e.target.value); setHi(0); openList(); }, onFocus: openList, onClick: openList, onBlur: function () { setOpen(false); }, onKeyDown: onKey }),
    list);
}

function PaymentBatchForm(props) {
  const sups = props.suppliers || [];
  const lk = props.lookups || {};
  const names = function (k) { return lkNames(lk, k); };
  const supItems = sups.map(function (s) { return { id: s.id, label: s.code + ' · ' + s.name, title: s.name, meta: s.code + (s.taxNo ? ' · ' + s.taxNo : ''), search: [s.code, s.name, s.taxNo || ''] }; });
  const blank = function () { return { key: Math.random().toString(36).slice(2), text: '', amount: '', method: '', dueDate: '', note: '', balance: '', stockBalance: '' }; };
  const [rows, setRows] = useState([blank(), blank(), blank()]);
  const [common, setCommon] = useState({ method: lkNames(props.lookups, 'method')[0] || '', dueDate: '', branch: '', bank: '', bankSub: '', costCenter: '' });
  const [defErr, setDefErr] = useState({});    // default field -> message
  const [errs, setErrs] = useState({});          // row key -> message
  const [fileName, setFileName] = useState('');
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const labelOf = function (s) { return s.code + ' · ' + s.name; };
  /* what was typed or picked -> a supplier: "code · name", the code, or the exact name */
  const find = function (text) {
    const t = pbNorm(text);
    if (!t) return null;
    return sups.filter(function (s) { return pbNorm(labelOf(s)) === t || pbNorm(s.code) === t || pbNorm(s.name) === t; })[0] || null;
  };
  const isBlank = function (r) { return !r.text.trim() && !String(r.amount).trim(); };
  const setRow = function (key, k, v) { setRows(function (rs) { return rs.map(function (r) { if (r.key !== key) return r; const n = Object.assign({}, r); n[k] = v; return n; }); }); setErrs(function (e) { if (!e[key]) return e; const n = Object.assign({}, e); delete n[key]; return n; }); };
  const addRow = function () { setRows(function (rs) { return rs.concat([blank()]); }); };
  const removeRow = function (key) { setRows(function (rs) { const n = rs.filter(function (r) { return r.key !== key; }); return n.length ? n : [blank()]; }); };

  const live = rows.filter(function (r) { return !isBlank(r); });
  const total = live.reduce(function (a, r) { const v = parseFloat(digitsOf(String(r.amount)).replace(/,/g, '')); return a + (isNaN(v) || v <= 0 ? 0 : v); }, 0);

  function importFile(file) {
    if (!file) return;
    setFileName(file.name);
    rcLoad('xlsx').then(function () { return file.arrayBuffer(); }).then(function (buf) {
      const wb = XLSX.read(buf, { type: 'array', cellDates: true });
      const grid = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { header: 1, defval: '', raw: true });
      const isCol = function (cell, key) { return PB_HEADERS[key].indexOf(pbNorm(cell)) !== -1; };
      const hi = grid.findIndex(function (r) { return r.some(function (c) { return isCol(c, 'amount'); }) && r.some(function (c) { return isCol(c, 'code') || isCol(c, 'name'); }); });
      if (hi === -1) { props.onToast('لم أجد في الملف عمودي «المورد» و«المبلغ». حمّل القالب واستخدم عناوينه.'); return; }
      const at = {};
      Object.keys(PB_HEADERS).forEach(function (k) { at[k] = grid[hi].findIndex(function (c) { return isCol(c, k); }); });
      const cell = function (r, k) { return at[k] === -1 ? '' : r[at[k]]; };
      const got = grid.slice(hi + 1).filter(function (r) { return String(cell(r, 'code')).trim() || String(cell(r, 'name')).trim() || String(cell(r, 'amount')).trim(); }).map(function (r) {
        const code = String(cell(r, 'code')).trim(), name = String(cell(r, 'name')).trim();
        const s = find(code) || find(name);
        const m = String(cell(r, 'method')).trim();
        return { key: Math.random().toString(36).slice(2), text: s ? labelOf(s) : (code || name), amount: String(cell(r, 'amount')).trim(), method: names('method').indexOf(m) !== -1 ? m : '', dueDate: pbDate(cell(r, 'due')), note: String(cell(r, 'note')).trim(),
          balance: String(cell(r, 'balance')).trim(), stockBalance: String(cell(r, 'stockBalance')).trim() };
      });
      if (!got.length) { props.onToast('لا توجد أسطر بيانات في الملف.'); return; }
      setErrs({});
      setRows(function (rs) { return rs.filter(function (r) { return !isBlank(r); }).concat(got); });
      props.onToast('قُرئ ' + got.length + ' سطر من الملف. راجعها ثم ارفع الدفعة.');
    }).catch(function () { props.onToast('تعذّرت قراءة الملف. استخدم ملف Excel أو CSV.'); });
  }
  function downloadTemplate() {
    rcLoad('xlsx').then(function () {
      const ex = sups[0];
      const ws = XLSX.utils.aoa_to_sheet([['رمز المورد', 'الرصيد الحالي', 'رصيد المخزون', 'المبلغ', 'طريقة السداد', 'تاريخ الاستحقاق', 'ملاحظة'],
        [ex ? ex.code : 'S-1001', 12500, 8300, 1500, 'تحويل بنكي', pbIso(new Date(Date.now() + 14 * DAY)), 'مثال: سداد فاتورة']]);
      ws['!cols'] = [{ wch: 16 }, { wch: 14 }, { wch: 14 }, { wch: 14 }, { wch: 18 }, { wch: 18 }, { wch: 30 }];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'السداد');
      wb.Workbook = { Sheets: [{ RTL: true }], Views: [{ RTL: true }] };
      XLSX.writeFile(wb, 'قالب-سداد-متعدد.xlsx');
    }).catch(function () { props.onToast('تعذّر إنشاء القالب. تأكد من الاتصال بالإنترنت وأعد المحاولة.'); });
  }

  function submit(e) {
    e.preventDefault();
    const er = {}, used = {}, de = {};
    PB_DIMS.forEach(function (d) { const v = common[d[0]].trim(); if (v && names(d[0]).indexOf(v) === -1) de[d[0]] = 'اختر ' + d[1] + ' من القائمة.'; });
    if (common.method && names('method').indexOf(common.method) === -1) de.method = 'اختر طريقة السداد من القائمة.';
    live.forEach(function (r) {
      const s = find(r.text), v = parseFloat(digitsOf(String(r.amount)).replace(/,/g, ''));
      if (!s) er[r.key] = 'اختر المورد من القائمة أو اكتب رمزه.';
      else if (!(v > 0)) er[r.key] = 'اكتب مبلغاً أكبر من صفر.';
      else if (used[s.id]) er[r.key] = 'المورد مكرر في الدفعة، اجمع المبلغين في سطر واحد.';
      else used[s.id] = true;
      if (!er[r.key] && !(r.method || common.method)) er[r.key] = 'اختر طريقة السداد.';
    });
    if (!live.length) { props.onToast('أضف مورداً واحداً على الأقل.'); return; }
    setErrs(er); setDefErr(de);
    if (Object.keys(de).length) { props.onToast('اختر الحقول الافتراضية من القوائم المعروضة.'); return; }
    if (Object.keys(er).length) { props.onToast('راجع الأسطر المعلّمة بالأحمر.'); return; }
    setBusy(true);
    props.onSubmit({
      method: common.method, dueDate: common.dueDate, branch: common.branch, bank: common.bank, bankSub: common.bankSub, costCenter: common.costCenter,
      rows: live.map(function (r) { return { supplierId: find(r.text).id, amount: r.amount, method: r.method, dueDate: r.dueDate, note: r.note, balance: r.balance, stockBalance: r.stockBalance }; })
    }).then(function () { setBusy(false); props.onClose(); }, function (ex) {
      setBusy(false);
      const re = ex.data && ex.data.rowErrors;
      if (re) { const m = {}; Object.keys(re).forEach(function (i) { if (live[+i]) m[live[+i].key] = re[i]; }); setErrs(m); }
      props.onToast(ex.message);
    });
  }

  return form({ className: 'uformwrap pbform', onSubmit: submit, noValidate: true },
    div({ className: 'uformhead' }, h3(null, 'إضافة سداد متعدد'),
      button({ type: 'button', className: 'uformclose', 'aria-label': 'إغلاق', onClick: props.onClose }, h(Icon, { name: 'close', size: 18 }))),
    p({ className: 'muted small' }, 'أضف عدة موردين في ملف واحد، يدوياً أو باستيراد ملف Excel / CSV. تُرفع كل الأسطر معاً برقم دفعة واحد، وتنتقل مباشرة إلى مدير المشتريات للاعتماد.'),
    div({ className: 'uform' },
      PB_DIMS.map(function (d) {
        return div({ className: 'field', key: d[0] }, label({ htmlFor: 'pb-' + d[0] }, d[1] + ' (افتراضي)'),
          h(ComboPicker, { id: 'pb-' + d[0], items: lkItems(lkActive(lk, d[0])), value: common[d[0]], ariaLabel: d[1], emptyText: 'لا توجد قيم. أضفها من صفحة «التهيئة».', noMatch: 'ليس في القائمة. اختر من القائمة أو أضفه من «التهيئة».',
            onText: function (v) { setCommon(function (c) { const n = Object.assign({}, c); n[d[0]] = v; return n; }); setDefErr(function (e) { const n = Object.assign({}, e); delete n[d[0]]; return n; }); },
            onPick: function (it) { setCommon(function (c) { const n = Object.assign({}, c); n[d[0]] = it.label; return n; }); setDefErr(function (e) { const n = Object.assign({}, e); delete n[d[0]]; return n; }); } }),
          defErr[d[0]] ? span({ className: 'err', role: 'alert' }, defErr[d[0]]) : (d[0] === 'branch' ? span({ className: 'hint' }, 'القيم من صفحة «التهيئة». تُطبَّق على كل سطر.') : null));
      }),
      div({ className: 'field' }, label({ htmlFor: 'pb-method' }, 'طريقة السداد الافتراضية'),
        h(ComboPicker, { id: 'pb-method', items: lkItems(lkActive(lk, 'method')), value: common.method, ariaLabel: 'طريقة السداد الافتراضية', emptyText: 'لا توجد طرق سداد. أضفها من صفحة «التهيئة».', noMatch: 'ليست في القائمة.',
          onText: function (v) { setCommon(function (c) { return Object.assign({}, c, { method: v }); }); setDefErr(function (e) { const n = Object.assign({}, e); delete n.method; return n; }); },
          onPick: function (it) { setCommon(function (c) { return Object.assign({}, c, { method: it.label }); }); setDefErr(function (e) { const n = Object.assign({}, e); delete n.method; return n; }); } }),
        defErr.method ? span({ className: 'err', role: 'alert' }, defErr.method) : span({ className: 'hint' }, 'تُطبَّق على السطر الذي لا تحدد له طريقة.')),
      div({ className: 'field' }, label({ htmlFor: 'pb-due' }, 'تاريخ الاستحقاق الافتراضي'),
        input({ id: 'pb-due', type: 'date', className: common.dueDate ? '' : 'empty', value: common.dueDate, onChange: function (e) { const v = e.target.value; setCommon(function (c) { return Object.assign({}, c, { dueDate: v }); }); } }),
        span({ className: 'hint' }, 'اختياري، ويمكن تحديده لكل سطر.'))),
    div({ className: 'pbtools' },
      input({ ref: fileRef, type: 'file', accept: '.xlsx,.xls,.csv', className: 'pbfile', 'aria-label': 'استيراد ملف Excel أو CSV', onChange: function (e) { importFile(e.target.files[0]); e.target.value = ''; } }),
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { fileRef.current && fileRef.current.click(); } }, h(Icon, { name: 'upload', size: 15 }), 'استيراد من ملف'),
      button({ type: 'button', className: 'btn ghost sm', onClick: downloadTemplate }, h(Icon, { name: 'download', size: 15 }), 'تنزيل القالب'),
      fileName ? span({ className: 'muted small' }, h(Icon, { name: 'file', size: 14 }), ' ' + fileName) : null),
    div({ className: 'tablewrap pbwrap' }, table({ className: 'dt pbtable' },
      thead(null, tr(null, ['#', 'المورد', 'الرصيد الحالي', 'رصيد المخزون', 'اقتراح الدفعة (ر.س)', 'طريقة السداد', 'الاستحقاق', 'ملاحظة', '2 المشتريات', '3 المدقق', '4 الاعتماد النهائي', ''].map(function (t, i) { return th({ key: i, scope: 'col' }, t); }))),
      tbody(null, rows.map(function (r, i) {
        const s = find(r.text), er = errs[r.key];
        return tr({ key: r.key, className: er ? 'bad' : undefined },
          td({ 'data-label': '#', className: 'rownum' }, i + 1),
          td({ 'data-label': 'المورد', className: 'pbsup' },
            h(ComboPicker, { items: supItems, value: r.text, ariaLabel: 'المورد في السطر ' + (i + 1), placeholder: 'اكتب اسم المورد أو رمزه', emptyText: 'لا يوجد موردون. أضفهم من «بيانات الموردين».', noMatch: 'لا يوجد مورد مطابق. تأكد من الاسم أو الرمز، أو أضف المورد من «بيانات الموردين».', onText: function (v) { setRow(r.key, 'text', v); }, onPick: function (it) { setRow(r.key, 'text', it.label); } }),
            er ? span({ className: 'err', role: 'alert' }, er) : (s && pbNorm(labelOf(s)) !== pbNorm(r.text) && pbNorm(s.name) !== pbNorm(r.text) ? span({ className: 'hint' }, s.name) : null)),
          td({ 'data-label': 'الرصيد الحالي' }, input({ type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', 'aria-label': 'الرصيد الحالي في السطر ' + (i + 1), value: r.balance, onChange: function (e) { setRow(r.key, 'balance', e.target.value); } })),
          td({ 'data-label': 'رصيد المخزون' }, input({ type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', 'aria-label': 'رصيد المخزون في السطر ' + (i + 1), value: r.stockBalance, onChange: function (e) { setRow(r.key, 'stockBalance', e.target.value); } })),
          td({ 'data-label': 'اقتراح الدفعة' }, input({ type: 'text', inputMode: 'decimal', className: 'ltr', autoComplete: 'off', 'aria-label': 'المبلغ في السطر ' + (i + 1), value: r.amount, onChange: function (e) { setRow(r.key, 'amount', e.target.value); } })),
          td({ 'data-label': 'طريقة السداد' }, select({ 'aria-label': 'طريقة السداد في السطر ' + (i + 1), value: r.method, onChange: function (e) { setRow(r.key, 'method', e.target.value); } }, option({ value: '' }, 'الافتراضية'), names('method').map(function (m) { return option({ key: m, value: m }, m); }))),
          td({ 'data-label': 'الاستحقاق' }, input({ type: 'date', className: r.dueDate ? '' : 'empty', 'aria-label': 'الاستحقاق في السطر ' + (i + 1), value: r.dueDate, onChange: function (e) { setRow(r.key, 'dueDate', e.target.value); } })),
          td({ 'data-label': 'ملاحظة' }, input({ type: 'text', autoComplete: 'off', 'aria-label': 'ملاحظة السطر ' + (i + 1), value: r.note, onChange: function (e) { setRow(r.key, 'note', e.target.value); } })),
          [['المشتريات', 'يعتمد ويقترح'], ['المدقق', 'يقبل أو يرفض'], ['الاعتماد النهائي', 'يعتمد نهائياً']].map(function (c) {
            return td({ key: c[0], 'data-label': c[0], className: 'pbwait' }, span({ className: 'muted' }, 'بعد الرفع'), span({ className: 'hint' }, c[1]));
          }),
          td({ 'data-label': '', className: 'pbrm' }, button({ type: 'button', className: 'abtn stop', 'aria-label': 'حذف السطر ' + (i + 1), onClick: function () { removeRow(r.key); } }, h(Icon, { name: 'trash', size: 16 }))));
      })))),
    button({ type: 'button', className: 'btn ghost sm', onClick: addRow }, h(Icon, { name: 'plus', size: 14 }), 'إضافة سطر'),
    div({ className: 'pbsum', role: 'status' }, span(null, live.length + (live.length === 1 ? ' مورد' : ' موردين')), strong({ className: 'mono' }, payMoney(total))),
    div({ className: 'formactions' },
      button({ type: 'submit', className: 'btn primary', disabled: busy || !live.length }, busy ? 'جارٍ الرفع…' : 'رفع الدفعة وإحالتها لمدير المشتريات'),
      button({ type: 'button', className: 'btn ghost', onClick: props.onClose }, 'إلغاء')));
}
