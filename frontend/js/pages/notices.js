'use strict';

/* ---------- supplier notices: simple tax invoices the company issues to a supplier ---------- */
const NT_METHODS = ['من حساب', 'نقداً', 'تحويل بنكي', 'شيك'];
const ntNum = function (v) { return Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
const ntDateTime = function (iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB') + ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

/* an edited copy of a notice, with every figure worked out the same way the server does it */
const ntRound = function (x) { return Math.round((x + Number.EPSILON) * 100) / 100; };
function ntModel(n, d) {
  const items = d.items.map(function (it) {
    const q = Number(it.qty) || 0, pr = Number(it.price) || 0, dc = Number(it.discount) || 0;
    const amount = ntRound(q * pr), net = amount - dc, tax = Math.floor((Math.round(net * 100) * n.vatRate + 50) / 100) / 100;
    return { code: it.code, name: it.name, qty: q, price: pr, discount: dc, amount: amount, tax: tax, total: ntRound(net + tax) };
  });
  const sub = ntRound(items.reduce(function (t, i) { return t + i.amount - i.discount; }, 0));
  const disc = ntRound(items.reduce(function (t, i) { return t + i.discount; }, 0));
  const vat = ntRound(items.reduce(function (t, i) { return t + i.tax; }, 0));
  return Object.assign({}, n, { items: items, description: d.description, dueDate: d.dueDate, paymentMethod: d.paymentMethod, buyer: d.buyer, subtotal: sub, discount: disc, vat: vat, total: ntRound(sub + vat) });
}
const ntDraftOf = function (n) {
  return {
    items: n.items.map(function (i) { return { code: i.code, name: i.name, qty: String(i.qty), price: String(i.price), discount: String(i.discount || '') }; }),
    description: n.description || '', dueDate: n.dueDate || '', paymentMethod: n.paymentMethod,
    buyer: Object.assign({ name: n.supplier, vat: n.supplierTax || '', otherId: n.supplierCode || '', mobile: n.supplierMobile || '' }, n.buyer || {})
  };
};

/* the printed document: same layout as the company's simple tax invoice. With `edit` the cells turn into fields. */
function NoticeSheet(props) {
  const n = props.n, s = n.seller, ed = props.edit;
  const b = n.buyer || {};
  const row = function (ar, en, val) {
    return div({ className: 'nt-row' }, span({ className: 'nt-a' }, ar), span({ className: 'nt-v' }, val || ''), span({ className: 'nt-l' }, en));
  };
  /* a buyer line: text when printing, a field when editing */
  /* without a value of its own, the address comes from the supplier data record */
  const brow = function (ar, en, key, fallback) {
    const fb = fallback || (n.supplierAddress || {})[key] || '';
    const shown = b[key] != null && b[key] !== '' ? b[key] : fb;
    if (!ed) return row(ar, en, shown);
    return row(ar, en, input({ className: 'nt-in', 'aria-label': ar.replace(' :', ''), value: ed.d.buyer[key] != null ? ed.d.buyer[key] : fb, onChange: function (e) { ed.setBuyer(key, e.target.value); } }));
  };
  let qr = '';
  try { qr = qrSvg(zatcaPayload(s.name, s.vat, new Date(n.issuedAt).toISOString().replace(/\.\d+Z$/, 'Z'), n.total, n.vat), 150); } catch (e) { qr = ''; }
  const totalQty = n.items.reduce(function (t, i) { return t + i.qty; }, 0);
  const field = function (i, k, extra) {
    return input(Object.assign({ className: 'nt-in num', 'aria-label': k + ' ' + (i + 1), value: ed.d.items[i][k], onChange: function (e) { ed.setItem(i, k, e.target.value); } }, extra || {}));
  };
  const numField = function (i, k, lab) { return field(i, k, { type: 'number', min: '0', step: 'any', inputMode: 'decimal', 'aria-label': lab + ' ' + (i + 1) }); };
  return div({ className: 'nt-sheet' + (ed ? ' editing' : '') },
    div({ className: 'nt-top' },
      div({ className: 'nt-meta' },
        div({ className: 'nt-co' }, strong(null, s.name), span(null, 'شارع ' + s.street)),
        div(null, span({ className: 'nt-k' }, 'رقم الفاتورة / Invoice Number'), strong({ className: 'nt-no' }, n.id)),
        div(null, span({ className: 'nt-k' }, 'تاريخ الفاتورة / Invoice Date'), strong(null, ntDateTime(n.issuedAt))),
        div(null, span({ className: 'nt-k' }, 'تاريخ الإستحقاق / Due Date.'),
          ed ? input({ className: 'nt-in', type: 'date', 'aria-label': 'تاريخ الاستحقاق', value: ed.d.dueDate || '', onChange: function (e) { ed.set('dueDate', e.target.value); } })
            : strong(null, n.dueDate ? new Date(n.dueDate).toLocaleDateString('en-GB') : '')),
        div(null, span({ className: 'nt-k' }, 'طريقة الدفع / Payment Method'),
          ed ? select({ className: 'nt-in', 'aria-label': 'طريقة الدفع', value: ed.d.paymentMethod, onChange: function (e) { ed.set('paymentMethod', e.target.value); } }, NT_METHODS.map(function (m) { return option({ key: m, value: m }, m); }))
            : strong({ className: 'nt-pm' }, n.paymentMethod))),
      div({ className: 'nt-mid' },
        div({ className: 'nt-title' }, strong(null, 'إشعار مدين'), strong(null, 'Debit Note')),
        div({ className: 'nt-page' }, 'Page', span(null, '1 of 1'))),
      div({ className: 'nt-qr', dangerouslySetInnerHTML: { __html: qr } })),
    div({ className: 'nt-parties' },
      div({ className: 'nt-box' },
        div({ className: 'nt-bh' }, span(null, 'المورد :'), span(null, 'Seller :')),
        row('الإسم :', 'Name :', s.name), row('المبنى :', 'Bulding :', s.building), row('الشارع :', 'Street :', s.street), row('الحي :', 'District :', s.district),
        row('المدينة :', 'City :', s.city), row('الدولة :', 'Country :', s.country), row('الرمز البريدي :', 'Postal Code :', s.postal),
        row('الرقم الإضافي :', 'Additional No', s.additional), row('الرقم الضريبي :', 'Vat No :', s.vat), row('السجل التجاري :', 'CRN :', s.crn), row('معرف آخر :', 'Other ID :', 'CRN')),
      div({ className: 'nt-box' },
        div({ className: 'nt-bh' }, span(null, 'العميل :'), span(null, 'Buyer :')),
        brow('الإسم :', 'Name :', 'name', n.supplier), brow('المبنى :', 'Bulding :', 'building'), brow('الشارع :', 'Street :', 'street'), brow('الحي :', 'District :', 'district'),
        brow('المدينة :', 'City :', 'city'), brow('الدولة :', 'Country :', 'country'), brow('الرمز البريدي :', 'Postal Code :', 'postal'),
        brow('الرقم الإضافي :', 'Additional No', 'additional'), brow('الرقم الضريبي :', 'Vat No :', 'vat', n.supplierTax), brow('السجل التجاري :', 'CRN :', 'crn'), brow('معرف آخر :', 'Other ID :', 'otherId', n.supplierCode), brow('رقم الجوال :', 'Mobile :', 'mobile', n.supplierMobile))),
    div({ className: 'nt-desc' }, span({ className: 'nt-dk' }, 'البيان / Description'),
      ed ? textarea({ className: 'nt-in', rows: 2, 'aria-label': 'البيان', value: ed.d.description, onChange: function (e) { ed.set('description', e.target.value); } }) : span({ className: 'nt-dv' }, n.description || '')),
    table({ className: 'nt-items' },
      thead(null, tr(null, [['الإجمالي', 'Total Due'], ['الضريبة', 'Tax'], ['الخصم', 'Discount'], [ed ? 'سعر الوحدة' : 'القيمة', ed ? 'Unit Price' : 'Amount'], ['الكمية', 'Quantity'], ['اسم الصنف  / البيـان', 'Item Name / Description'], ['الكود', 'Item ID']].map(function (c) {
        return th({ key: c[1], scope: 'col' }, c[0], h('br'), c[1]);
      }).concat(ed ? [th({ key: 'x', scope: 'col', className: 'nt-xcol' })] : []))),
      tbody(null, n.items.map(function (it, i) {
        return tr({ key: i },
          td({ className: 'num' }, ntNum(it.total)), td({ className: 'num' }, ntNum(it.tax)),
          td({ className: 'num' }, ed ? numField(i, 'discount', 'الخصم') : ntNum(it.discount)),
          td({ className: 'num' }, ed ? [numField(i, 'price', 'سعر الوحدة'), span({ key: 'a', className: 'nt-sub' }, 'القيمة ' + ntNum(it.amount))] : ntNum(it.amount)),
          td({ className: 'num' }, ed ? numField(i, 'qty', 'الكمية') : it.qty),
          td(null, ed ? field(i, 'name', { 'aria-label': 'اسم البند ' + (i + 1) }) : it.name),
          td({ className: 'num' }, ed ? field(i, 'code', { 'aria-label': 'كود البند ' + (i + 1) }) : it.code),
          ed ? td({ key: 'x', className: 'nt-xcol' }, n.items.length > 1 ? button({ type: 'button', className: 'abtn stop', 'aria-label': 'حذف البند ' + (i + 1), onClick: function () { ed.removeItem(i); } }, h(Icon, { name: 'trash', size: 15 })) : null) : null);
      }))),
    ed ? button({ type: 'button', className: 'btn ghost sm nt-add noprint', onClick: ed.addItem }, h(Icon, { name: 'plus', size: 14 }), 'إضافة بند') : null,
    div({ className: 'nt-words' }, span({ className: 'nt-ar' }, arMoney(n.total)), span({ className: 'nt-sar' }, 'SAR'), span({ className: 'nt-amt' }, ntNum(n.total))),
    div({ className: 'nt-tot' },
      div({ className: 'nt-lines' },
        [['الإجمالي غير شامل ضريبة القيمة المضافة', 'Total Excluding VAT', n.subtotal + n.discount], ['الخصم', 'Discount', n.discount], ['الأعباء', 'Charges', 0],
          ['الإجمالي الخاضع للضريبة', 'Total Taxable Amount', n.subtotal], ['الضريبة', 'Tax ' + n.vatRate + '%', n.vat], ['الإجمالي النهائي شامل الضريبة', 'Total Amt With Tax', n.total]].map(function (l, i) {
          return div({ key: i, className: 'nt-ln' + (i === 5 ? ' last' : '') }, span({ className: 'nt-ll' }, l[1] + ' / ' + l[0]), strong(null, ntNum(l[2])));
        })),
      div({ className: 'nt-qty' }, span(null, 'Total QTY / إجمالي الكمية'), strong(null, totalQty))));
}

/* one notice: view and print it, or (finance team) edit it in place and watch the figures change */
function NoticeView(props) {
  const n = props.n;
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const ed = draft ? {
    d: draft,
    set: function (k, v) { setDraft(function (d) { return Object.assign({}, d, { [k]: v }); }); },
    setBuyer: function (k, v) { setDraft(function (d) { return Object.assign({}, d, { buyer: Object.assign({}, d.buyer, { [k]: v }) }); }); },
    setItem: function (i, k, v) { setDraft(function (d) { return Object.assign({}, d, { items: d.items.map(function (x, j) { return j === i ? Object.assign({}, x, { [k]: v }) : x; }) }); }); },
    addItem: function () { setDraft(function (d) { return Object.assign({}, d, { items: d.items.concat([{ code: '', name: '', qty: '1', price: '', discount: '' }]) }); }); },
    removeItem: function (i) { setDraft(function (d) { return Object.assign({}, d, { items: d.items.filter(function (_, j) { return j !== i; }) }); }); }
  } : null;
  const shown = draft ? ntModel(n, draft) : n;
  function save() {
    if (busy) return;
    if (draft.items.some(function (x) { return !x.name.trim() || !(Number(x.qty) > 0) || x.price === ''; })) { setError('أكمل كل بند: الاسم والكمية وسعر الوحدة.'); return; }
    if (shown.items.some(function (x) { return x.discount > x.amount; })) { setError('الخصم أكبر من قيمة البند.'); return; }
    setBusy(true); setError('');
    props.onSave(n.pk, { items: draft.items, description: draft.description, dueDate: draft.dueDate || null, paymentMethod: draft.paymentMethod, buyer: draft.buyer })
      .then(function () { setBusy(false); setDraft(null); }, function (ex) { setBusy(false); setError(ex.message); });
  }
  return div({ className: 'stack' },
    div({ className: 'sechead noprint' },
      button({ type: 'button', className: 'btn ghost sm', onClick: props.onBack }, h(Icon, { name: 'back', size: 16 }), 'رجوع'),
      div({ className: 'rc-acts' },
        draft ? [button({ key: 's', type: 'button', className: 'btn primary sm', disabled: busy, onClick: save }, h(Icon, { name: 'check', size: 16 }), busy ? 'جارٍ الحفظ…' : 'حفظ التعديلات'),
          button({ key: 'c', type: 'button', className: 'btn ghost sm', onClick: function () { setDraft(null); setError(''); } }, 'إلغاء')]
          : null)),
    error ? div({ className: 'err noprint', role: 'alert' }, error) : null,
    draft ? div({ className: 'note noprint' }, 'وضع التعديل: غيّر الكمية أو سعر الوحدة أو الخصم أو بيانات العميل مباشرة في الإشعار، وتتحدث المبالغ والضريبة والإجمالي ورمز QR فوراً. اضغط «حفظ التعديلات» لاعتمادها.') : null,
    h(NoticeSheet, { n: shown, edit: ed }));
}

function NoticeForm(props) {
  const blank = { code: '', name: '', qty: '1', price: '', discount: '' };
  const [supplierId, setSupplierId] = useState('');
  const [due, setDue] = useState('');
  const [method, setMethod] = useState(NT_METHODS[0]);
  const [desc, setDesc] = useState('');
  const [items, setItems] = useState([Object.assign({}, blank)]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const setItem = function (i, k, v) { setItems(function (xs) { return xs.map(function (x, j) { return j === i ? Object.assign({}, x, { [k]: v }) : x; }); }); };
  const gross = function (x) { return (Number(x.qty) || 0) * (Number(x.price) || 0); };
  const sub = items.reduce(function (t, x) { return t + gross(x) - (Number(x.discount) || 0); }, 0);
  const disc = items.reduce(function (t, x) { return t + (Number(x.discount) || 0); }, 0);
  const vat = Math.round(sub * 15) / 100;
  function submit(e) {
    e.preventDefault();
    if (busy) return;
    if (!supplierId) { setError('اختر المورد.'); return; }
    if (items.some(function (x) { return !x.name.trim() || !(Number(x.qty) > 0) || x.price === ''; })) { setError('أكمل بيانات كل بند: الاسم والكمية والسعر.'); return; }
    if (items.some(function (x) { return (Number(x.discount) || 0) > gross(x); })) { setError('الخصم أكبر من قيمة البند.'); return; }
    setBusy(true); setError('');
    props.onCreate({ supplierId: +supplierId, dueDate: due || null, paymentMethod: method, description: desc, items: items }).then(function () { setBusy(false); }, function (ex) { setBusy(false); setError(ex.message); });
  }
  const f = function (id, lab, control) { return div({ className: 'field' }, label({ htmlFor: id }, lab), control); };
  const pickedS = supplierId ? props.suppliers.filter(function (s) { return String(s.id) === supplierId; })[0] : null;
  return section({ className: 'panel formcard nt-form' },
    h3(null, 'إشعار جديد لمورد'),
    form({ onSubmit: submit, noValidate: true },
      div({ className: 'nt-grid2' },
        f('nt-sup', 'المورد', select({ id: 'nt-sup', value: supplierId, onChange: function (e) { setSupplierId(e.target.value); } },
          option({ value: '' }, 'اختر المورد…'), props.suppliers.map(function (s) { return option({ key: s.id, value: String(s.id) }, s.name + (s.code ? ' · ' + s.code : '')); }))),
        f('nt-due', 'تاريخ الاستحقاق (اختياري)', input({ id: 'nt-due', type: 'date', value: due, onChange: function (e) { setDue(e.target.value); } })),
        f('nt-pm', 'طريقة الدفع', select({ id: 'nt-pm', value: method, onChange: function (e) { setMethod(e.target.value); } }, NT_METHODS.map(function (m) { return option({ key: m, value: m }, m); })))),
      pickedS ? h(SupplierInfo, { s: pickedS }) : null,
      f('nt-desc', 'البيان', textarea({ id: 'nt-desc', rows: 2, value: desc, onChange: function (e) { setDesc(e.target.value); }, placeholder: 'مثال: فاتورة إيجار مساحة حسب العقد رقم… عن الفترة من… إلى…' })),
      div({ className: 'nt-items-ed' },
        span({ className: 'lbl' }, 'البنود'),
        items.map(function (x, i) {
          const cell = function (lab, cls, control) { return label({ className: 'nt-c ' + (cls || '') }, span(null, lab), control); };
          const num = function (k, lab) { return cell(lab, '', input({ 'aria-label': lab + ' ' + (i + 1), type: 'number', min: '0', step: 'any', inputMode: 'decimal', value: x[k], onChange: function (e) { setItem(i, k, e.target.value); } })); };
          return div({ key: i, className: 'nt-itrow' },
            cell('الكود', '', input({ 'aria-label': 'كود البند ' + (i + 1), value: x.code, onChange: function (e) { setItem(i, 'code', e.target.value); } })),
            cell('اسم البند', 'wide', input({ 'aria-label': 'اسم البند ' + (i + 1), value: x.name, onChange: function (e) { setItem(i, 'name', e.target.value); } })),
            num('qty', 'الكمية'), num('price', 'سعر الوحدة'), num('discount', 'الخصم'),
            div({ className: 'nt-c nt-tl' }, span(null, 'الإجمالي'), strong({ className: 'mono' }, ntNum(gross(x) - (Number(x.discount) || 0)))),
            items.length > 1 ? button({ type: 'button', className: 'abtn stop nt-rm', 'aria-label': 'حذف البند ' + (i + 1), onClick: function () { setItems(items.filter(function (_, j) { return j !== i; })); } }, h(Icon, { name: 'trash', size: 16 }), span({ className: 'abl' }, 'حذف')) : null);
        }),
        button({ type: 'button', className: 'btn ghost sm', onClick: function () { setItems(items.concat([Object.assign({}, blank)])); } }, h(Icon, { name: 'plus', size: 14 }), 'إضافة بند')),
      div({ className: 'nt-sum' },
        div(null, span(null, 'الإجمالي غير شامل الضريبة'), strong({ className: 'mono' }, ntNum(sub + disc))),
        div(null, span(null, 'الخصم'), strong({ className: 'mono' }, ntNum(disc))),
        div(null, span(null, 'الضريبة 15%'), strong({ className: 'mono' }, ntNum(vat))),
        div({ className: 'tot' }, span(null, 'الإجمالي شامل الضريبة'), strong({ className: 'mono' }, ntNum(sub + vat)))),
      error ? div({ className: 'err', role: 'alert' }, error) : null,
      div({ className: 'formactions' },
        button({ type: 'submit', className: 'btn primary', disabled: busy }, h(Icon, { name: 'send' }), busy ? 'جارٍ الإصدار…' : 'إصدار الإشعار'),
        button({ type: 'button', className: 'btn ghost', onClick: props.onCancel }, 'إلغاء'))));
}

function NoticeTable(props) {
  const defs = [
    { key: 'id', label: 'رقم الإشعار', filter: 'text', val: function (n) { return n.id; }, render: function (n) { return span({ className: 'mono' }, n.id); } },
    { key: 'supplier', label: 'المورد', filter: 'text', val: function (n) { return n.supplier; }, render: function (n) { return strong({ style: { fontWeight: 600 } }, n.supplier); } },
    { key: 'date', label: 'التاريخ', val: function (n) { return new Date(n.issuedAt).getTime(); }, render: function (n) { return fmtDate(new Date(n.issuedAt)); } },
    { key: 'desc', label: 'البيان', filter: 'text', val: function (n) { return n.description || n.items[0].name; }, render: function (n) { return (n.description || n.items[0].name).slice(0, 70); } },
    { key: 'total', label: 'الإجمالي (ر.س)', val: function (n) { return n.total; }, render: function (n) { return span({ className: 'mono' }, ntNum(n.total)); } },
    openCol(props.onDelete)
  ];
  return h(DataTable, { cols: props.hide ? defs.filter(function (c) { return props.hide.indexOf(c.key) === -1; }) : defs, rows: props.rows, onOpen: props.onOpen, defaultSort: { key: 'date', dir: 'desc' }, empty: 'لا توجد إشعارات بعد.' });
}

/* shared by the staff page and the supplier panel: the list, or one notice ready to print */
function NoticesPage(props) {
  const [view, setView] = useState({ name: 'list' });
  const current = view.name === 'show' ? props.notices.filter(function (n) { return n.id === view.id; })[0] : null;
  if (view.name === 'new') {
    return h(NoticeForm, { suppliers: props.suppliers, onCancel: function () { setView({ name: 'list' }); }, onCreate: function (data) {
      return props.onCreate(data).then(function (n) { setView({ name: 'show', id: n.id }); });
    } });
  }
  if (current) {
    return h(NoticeView, { key: current.id, n: current, canEdit: !!props.canIssue && !!props.onUpdate, onSave: props.onUpdate, onToast: props.onToast, onBack: function () { setView({ name: 'list' }); } });
  }
  return section({ className: 'svcpanel' },
    div({ className: 'svchead' },
      div(null, h2(null, 'إشعارات الموردين'), p({ className: 'muted small' }, props.canIssue ? 'أصدر إشعاراً ضريبياً لمورد واطبعه بتصميم الفاتورة الرسمية.' : 'الإشعارات الصادرة لك من أسواق الرشيد، ويمكنك طباعتها.')),
      props.canIssue ? button({ className: 'btn primary', onClick: function () { setView({ name: 'new' }); } }, h(Icon, { name: 'plus' }), 'إشعار جديد') : null),
    h(NoticeTable, { rows: props.notices, hide: props.canIssue ? [] : ['supplier'], onOpen: function (id) { setView({ name: 'show', id: id }); }, onDelete: props.onDelete }));
}
