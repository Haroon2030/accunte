'use strict';

/* ---------- supplier data: the master record of each supplier company (name, code, tax number, mobile) ----------
   Accounts are linked to a supplier from the users page, and notices print these details. */
const digitsOf = function (v) {
  return String(v || '').replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 1632); }).replace(/[\s\-()+]/g, '');
};
/* 05XXXXXXXX; also accepts 9665XXXXXXXX and 5XXXXXXXX, like the server */
const mobileOf = function (v) {
  let d = digitsOf(v);
  if (d.indexOf('00966') === 0) d = '0' + d.slice(5);
  else if (d.indexOf('966') === 0) d = '0' + d.slice(3);
  else if (d.length === 9 && d.charAt(0) === '5') d = '0' + d;
  return d;
};
/* compact "name · code · tax · mobile" block reused by the users form and the notice form */
function SupplierInfo(props) {
  const s = props.s;
  if (!s) return null;
  const row = function (k, v, mono) { return div({ className: 'sinfo-row', key: k }, dt(null, k), dd(null, v ? (mono ? span({ className: 'mono' }, v) : v) : span({ className: 'muted' }, '—'))); };
  return div({ className: 'sinfo' + (props.className ? ' ' + props.className : ''), role: 'group', 'aria-label': 'بيانات المورد' },
    dl(null, row('الاسم', s.name), row('الرمز', s.code, true), row('الرقم الضريبي', s.taxNo, true), row('رقم الجوال', s.mobile, true)));
}

/* national address, printed in the buyer box of notices; the keys match the server's Supplier.ADDRESS_FIELDS */
const ADDR_FIELDS = [['building', 'المبنى'], ['street', 'الشارع'], ['district', 'الحي'], ['city', 'المدينة'], ['country', 'الدولة'], ['postal', 'الرمز البريدي']];
const addressOf = function (s) {
  const a = s.address || {};
  return ADDR_FIELDS.reduce(function (o, f) { o[f[0]] = a[f[0]] || ''; return o; }, {});
};
const EMPTY_SUPPLIER = { id: null, name: '', code: '', taxNo: '', mobile: '', building: '', street: '', district: '', city: '', country: '', postal: '', active: true };

function SuppliersPage(props) {
  const list = props.suppliers;
  const canEdit = props.canEdit;
  const [formV, setFormV] = useState(null);
  const [errs, setErrs] = useState({});
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const baseRef = useRef('');
  const setF = function (k, v) { setFormV(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); };
  const dirty = !!formV && JSON.stringify(formV) !== baseRef.current;
  function openForm(s) {
    setConfirm(null); setErrs({});
    const f = s ? Object.assign({ id: s.id, name: s.name, code: s.code, taxNo: s.taxNo || '', mobile: s.mobile || '', active: s.active }, addressOf(s)) : Object.assign({}, EMPTY_SUPPLIER);
    baseRef.current = JSON.stringify(f);
    setFormV(f);
    setTimeout(function () { const el = document.getElementById('sf-name'); if (el) el.focus(); }, 0);
  }
  function closeForm() {
    if (dirty && !window.confirm('عندك تعديلات لم تُحفظ. تُغلق النموذج وتفقدها؟')) return;
    setFormV(null);
  }
  useEffect(function () {
    if (!dirty) return undefined;
    const warn = function (e) { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return function () { window.removeEventListener('beforeunload', warn); };
  }, [dirty]);

  function save(e) {
    e.preventDefault();
    const f = formV, er = {};
    const tax = digitsOf(f.taxNo), mob = mobileOf(f.mobile), code = f.code.trim();
    if (!f.name.trim()) er.name = 'أدخل اسم المورد.';
    if (!code) er.code = 'أدخل رمز المورد.';
    else if (list.some(function (x) { return x.code.toLowerCase() === code.toLowerCase() && x.id !== f.id; })) er.code = 'رمز المورد مستخدم لمورد آخر.';
    if (tax && !/^\d{15}$/.test(tax)) er.taxNo = 'الرقم الضريبي 15 رقماً.';
    if (mob && !/^05\d{8}$/.test(mob)) er.mobile = 'رقم الجوال 10 أرقام ويبدأ بـ 05.';
    const postal = digitsOf(f.postal);
    if (postal && !/^\d{5}$/.test(postal)) er.postal = 'الرمز البريدي 5 أرقام.';
    setErrs(er);
    const first = ['name', 'code', 'taxNo', 'mobile', 'postal'].filter(function (k) { return er[k]; })[0];
    if (first) { const el = document.getElementById('sf-' + first); if (el) el.focus(); return; }
    const addr = {};
    ADDR_FIELDS.forEach(function (x) { addr[x[0]] = f[x[0]].trim(); });
    addr.postal = postal;
    setBusy(true);
    props.onSave(Object.assign({ id: f.id, name: f.name.trim(), code: code, taxNo: tax, mobile: mob, active: f.active }, addr)).then(function () { setBusy(false); setFormV(null); }, function (ex) {
      setBusy(false);
      const d = ex.data, known = { name: 1, code: 1, taxNo: 1, mobile: 1, postal: 1 }, fe = {};
      if (d && typeof d === 'object' && !d.detail) Object.keys(d).forEach(function (k) { if (known[k]) fe[k] = [].concat(d[k])[0]; });
      if (Object.keys(fe).length) setErrs(fe); else props.onToast(ex.message);
    });
  }
  function doDelete() {
    const s = confirm;
    setConfirm(null);
    props.onDelete(s.id);
  }
  const fld = function (id, lbl, ctl, k, hint) {
    return div({ className: 'field', key: k }, label({ htmlFor: id }, lbl), ctl, errs[k] ? span({ className: 'err', role: 'alert' }, errs[k]) : (hint ? span({ className: 'hint' }, hint) : null));
  };
  const txt = function (id, k, cls, extra) {
    return input(Object.assign({ id: id, type: 'text', autoComplete: 'off', className: cls || '', value: formV[k], onChange: function (e) { setF(k, e.target.value); } }, extra || {}));
  };

  const cols = [
    { key: 'code', label: 'الرمز', filter: 'text', val: function (s) { return s.code; }, render: function (s) { return span({ className: 'mono' }, s.code); } },
    { key: 'name', label: 'اسم المورد', filter: 'text', val: function (s) { return s.name; }, render: function (s) { return strong({ style: { fontWeight: 600 } }, s.name); } },
    { key: 'taxNo', label: 'الرقم الضريبي', filter: 'text', val: function (s) { return s.taxNo; }, render: function (s) { return s.taxNo ? span({ className: 'mono' }, s.taxNo) : span({ className: 'muted' }, '—'); } },
    { key: 'mobile', label: 'رقم الجوال', filter: 'text', val: function (s) { return s.mobile; }, render: function (s) { return s.mobile ? span({ className: 'mono' }, s.mobile) : span({ className: 'muted' }, '—'); } },
    { key: 'users', label: 'الحسابات', val: function (s) { return s.users; }, render: function (s) { return s.users ? s.users + (s.users === 1 ? ' حساب' : ' حسابات') : span({ className: 'muted' }, 'بلا حساب'); } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: function (s) { return s.active ? 'نشط' : 'موقوف'; }, val: function (s) { return s.active ? 0 : 1; },
      render: function (s) { return span({ className: 'pill ' + (s.active ? 'ok' : 'bad') }, span({ className: 'dot' }), s.active ? 'نشط' : 'موقوف'); } }
  ];
  if (canEdit) {
    cols.push({ key: 'act', label: 'إجراءات', render: function (s) {
      return div({ className: 'rowacts' },
        button({ type: 'button', className: 'abtn edit', 'aria-label': 'تعديل ' + s.name, onClick: function (e) { e.stopPropagation(); openForm(s); } }, h(Icon, { name: 'pencil', size: 16 }), span({ className: 'abl' }, 'تعديل')),
        props.canDelete ? button({ type: 'button', className: 'abtn stop', 'aria-label': 'حذف ' + s.name, onClick: function (e) { e.stopPropagation(); setFormV(null); setConfirm(s); } }, h(Icon, { name: 'trash', size: 16 }), span({ className: 'abl' }, 'حذف')) : null);
    } });
  }
  const count = function (f) { return list.filter(f).length; };

  return section({ className: 'svcpanel userspage' },
    div({ className: 'svchead' },
      div(null, h2(null, 'بيانات الموردين'), p({ className: 'muted small' }, 'التهيئة الأساسية لكل مورد: الاسم والرمز والرقم الضريبي ورقم الجوال. تظهر عند ربط حساب مستخدم بالمورد وفي إشعارات الموردين.')),
      canEdit ? button({ className: 'btn primary', onClick: function () { openForm(null); } }, h(Icon, { name: 'plus' }), 'مورد جديد') : null),
    div({ className: 'ustats' },
      [['الإجمالي', list.length], ['النشطون', count(function (s) { return s.active; })], ['الموقوفون', count(function (s) { return !s.active; })],
        ['بلا حساب', count(function (s) { return !s.users; })], ['بلا رقم جوال', count(function (s) { return !s.mobile; })]]
        .map(function (x) { return div({ key: x[0], className: 'ustat' }, h('b', null, x[1]), span(null, x[0])); })),
    confirm ? div({ className: 'confirmbar', role: 'alertdialog' },
      span(null, 'حذف المورد ' + confirm.name + ' (' + confirm.code + ') نهائياً؟ لا يمكن التراجع.'),
      button({ type: 'button', className: 'btn primary sm', onClick: doDelete }, 'تأكيد'),
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { setConfirm(null); } }, 'إلغاء')) : null,
    formV ? form({ className: 'uformwrap', onSubmit: save, noValidate: true },
      div({ className: 'uformhead' }, h3(null, formV.id ? 'تعديل بيانات مورد' : 'مورد جديد'),
        button({ type: 'button', className: 'uformclose', 'aria-label': 'إغلاق', onClick: closeForm }, h(Icon, { name: 'close', size: 18 }))),
      div({ className: 'uform' },
        fld('sf-name', 'اسم المورد', txt('sf-name', 'name'), 'name'),
        fld('sf-code', 'رمز المورد', txt('sf-code', 'code', 'ltr'), 'code', 'رمز فريد لكل مورد، مثل S-1001.'),
        fld('sf-taxNo', 'الرقم الضريبي', txt('sf-taxNo', 'taxNo', 'ltr', { inputMode: 'numeric', maxLength: 15 }), 'taxNo', '15 رقماً، ويمكن تركه فارغاً.'),
        fld('sf-mobile', 'رقم الجوال', txt('sf-mobile', 'mobile', 'ltr', { inputMode: 'tel', maxLength: 16, placeholder: '05XXXXXXXX' }), 'mobile', 'جوال سعودي يبدأ بـ 05.'),
        div({ className: 'addrgrid' }, span({ className: 'addrtitle' }, 'العنوان الوطني'),
          ADDR_FIELDS.map(function (x) {
            const isPostal = x[0] === 'postal';
            return fld('sf-' + x[0], x[1], txt('sf-' + x[0], x[0], isPostal ? 'ltr' : '', isPostal ? { inputMode: 'numeric', maxLength: 5 } : {}), x[0]);
          })),
        formV.id ? div({ className: 'field wide opts' }, span({ className: 'lbl' }, 'الحالة'),
          div({ className: 'optrow' }, label({ className: 'checkrow' }, input({ type: 'checkbox', checked: formV.active, onChange: function (e) { setF('active', e.target.checked); } }), 'المورد نشط (يمكن ربط حسابات به وإصدار إشعارات له)'))) : null),
      div({ className: 'formactions' },
        button({ type: 'submit', className: 'btn primary', disabled: busy }, formV.id ? 'حفظ التعديلات' : 'إضافة المورد'),
        button({ type: 'button', className: 'btn ghost', onClick: closeForm }, 'إلغاء'))) : null,
    h(DataTable, { cols: cols, rows: list, exportName: 'بيانات-الموردين', onOpen: canEdit ? function (id) { const s = list.filter(function (x) { return x.id === id; })[0]; if (s) openForm(s); } : undefined,
      empty: 'لا يوجد موردون بعد. أضف أول مورد من زر «مورد جديد».', defaultSort: { key: 'name', dir: 'asc' } }));
}
