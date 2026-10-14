'use strict';

const EMPTY_FORM = { id: null, name: '', username: '', role: 'supplier', org: '', taxNo: '', code: '', password: '', active: true, pages: ROLE_PAGES.supplier.slice() };
function UsersPage(props) {
  const me = props.me;
  const [formV, setFormV] = useState(null);
  const [errs, setErrs] = useState({});
  const [confirm, setConfirm] = useState(null);
  const [temp, setTemp] = useState(null);
  const [q, setQ] = useState('');
  const [roleF, setRoleF] = useState('');
  const [statF, setStatF] = useState('');
  const [nameF, setNameF] = useState('');
  const [orgF, setOrgF] = useState('');
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' });
  const baseRef = useRef('');
  const users = props.users;
  const canManage = function (x) { return me.role === 'admin' || x.role !== 'admin'; };
  const roleOpts = me.role === 'admin' ? ['supplier', 'matcher', 'supervisor', 'manager', 'admin'] : ['supplier', 'matcher', 'supervisor', 'manager'];
  const normDigits = function (v) { return String(v || '').replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 1632); }).replace(/\s/g, ''); };
  const count = function (f) { return users.filter(f).length; };
  const setF = function (k, v) { setFormV(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); };
  function openNew() { setTemp(null); setConfirm(null); setErrs({}); const f = Object.assign({}, EMPTY_FORM, { password: genPass() }); baseRef.current = JSON.stringify(f); setFormV(f); }
  function openEdit(x) { setTemp(null); setConfirm(null); setErrs({}); const f = { id: x.id, name: x.name, username: x.username, role: x.role, org: x.org, taxNo: x.taxNo || '', code: x.code || '', password: '', mustChange: false, active: x.active, pages: (x.pages || ROLE_PAGES[x.role] || []).slice() }; baseRef.current = JSON.stringify(f); setFormV(f); }
  const dirty = !!formV && JSON.stringify(formV) !== baseRef.current;
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
  function focusFirst(er) {
    const ids = { name: 'uf-name', username: 'uf-user', role: 'uf-role', org: 'uf-org', code: 'uf-code', taxNo: 'uf-tax', password: formV.id ? 'uf-pw2' : 'uf-pw' };
    const k = ['name', 'username', 'role', 'org', 'code', 'taxNo', 'password'].filter(function (x) { return er[x]; })[0];
    const el = k ? document.getElementById(ids[k]) : (er.pages ? document.querySelector('.uform .opts input') : null);
    if (el) setTimeout(function () { el.focus(); }, 0);
  }
  function save(e) {
    e.preventDefault();
    const f = formV, er = {};
    const un = normUser(f.username);
    if (!f.name.trim()) er.name = 'أدخل الاسم الكامل.';
    if (!/^[a-z0-9._-]{1,30}$/.test(un)) er.username = 'أرقام أو حروف إنجليزية صغيرة، حتى 30 خانة.';
    else if (users.some(function (x) { return x.username === un && x.id !== f.id; })) er.username = 'رقم المستخدم مستخدم لحساب آخر.';
    if (f.role === 'supplier' && !f.org.trim()) er.org = 'أدخل اسم المورد التابع له الحساب.';
    if (f.role === 'supplier') {
      const tx = normDigits(f.taxNo), cd = f.code.trim();
      if (!cd) er.code = 'أدخل رمز المورد.';
      else if (users.some(function (x) { return x.role === 'supplier' && (x.code || '').toLowerCase() === cd.toLowerCase() && x.id !== f.id; })) er.code = 'رمز المورد مستخدم لمورد آخر.';
      if (tx && !/^\d{15}$/.test(tx)) er.taxNo = 'الرقم الضريبي 15 رقماً.';
    }
    if (!f.id || f.password) { const m = passErr(f.password); if (m) er.password = m; }
    if (f.role !== 'supplier' && !(f.pages || []).length) er.pages = 'اختر صفحة واحدة على الأقل.';
    if (f.id && f.id === me.id && f.pages.indexOf('users') === -1) er.pages = 'لا يمكنك سحب صلاحية إدارة المستخدمين من حسابك الحالي.';
    if (f.id === me.id && f.role !== me.role) er.role = 'لا يمكنك تغيير دور حسابك الحالي.';
    setErrs(er);
    if (Object.keys(er).length) { focusFirst(er); return; }
    props.onSave({ id: f.id, name: f.name.trim(), username: un, role: f.role, org: f.role === 'supplier' ? f.org.trim() : (f.org.trim() || 'أسواق الرشيد'), taxNo: f.role === 'supplier' ? normDigits(f.taxNo) : '', code: f.role === 'supplier' ? f.code.trim() : '', password: f.password, mustChange: !!f.mustChange, active: f.active, pages: f.role === 'supplier' || samePages(f.pages, ROLE_PAGES[f.role]) ? null : f.pages })
      .then(function () { setFormV(null); })
      .catch(function (ex) {
        const d = ex.data, known = { name: 1, username: 1, role: 1, org: 1, code: 1, taxNo: 1, password: 1, pages: 1 }, fe = {};
        if (d && typeof d === 'object' && !d.detail) Object.keys(d).forEach(function (k) { if (known[k]) fe[k] = [].concat(d[k])[0]; });
        if (Object.keys(fe).length) setErrs(fe); else props.onToast(ex.message);
      });
  }
  function doConfirm() {
    const x = users.filter(function (u) { return u.id === confirm.id; })[0];
    if (!x) { setConfirm(null); return; }
    if (confirm.type === 'toggle') props.onToggle(x.id);
    else if (confirm.type === 'delete') props.onDelete(x.id);
    else {
      props.onReset(x.id).then(function (pw) { setTemp({ name: x.name, username: x.username, pw: pw }); }).catch(function (ex) { props.onToast(ex.message); });
    }
    setConfirm(null);
  }
  function copy(text) {
    try { navigator.clipboard.writeText(text).then(function () { props.onToast('نُسخت كلمة المرور.'); }, function () { props.onToast('تعذّر النسخ، انسخها يدوياً.'); }); } catch (e) { props.onToast('تعذّر النسخ، انسخها يدوياً.'); }
  }
  const cx = confirm ? users.filter(function (u) { return u.id === confirm.id; })[0] : null;
  const actions = function (x) {
    if (!canManage(x)) return span({ className: 'muted small' }, 'للمدير فقط');
    const ab = function (cls, icon, label, on) {
      return button({ type: 'button', className: 'abtn ' + cls, title: label, 'aria-label': label + ' ' + x.name, onClick: on }, h(Icon, { name: icon, size: 16 }), span({ className: 'abl' }, label));
    };
    return div({ className: 'rowacts' },
      ab('edit', 'pencil', 'تعديل', function () { openEdit(x); }),
      ab('pw', 'key', 'كلمة مرور جديدة', function () { setFormV(null); setTemp(null); setConfirm({ type: 'reset', id: x.id }); }),
      x.id === me.id ? null : ab(x.active ? 'stop' : 'go', x.active ? 'ban' : 'check', x.active ? 'إيقاف' : 'تفعيل', function () { setFormV(null); setTemp(null); setConfirm({ type: 'toggle', id: x.id }); }),
      x.id === me.id ? null : ab('stop', 'trash', 'حذف', function () { setFormV(null); setTemp(null); setConfirm({ type: 'delete', id: x.id }); }));
  };
  const samePages = function (a, b) { return (a || []).slice().sort().join() === (b || []).slice().sort().join(); };
  const STAFF_PAGE_KEYS = ['matcher', 'manager', 'recon', 'notices', 'users'];
  const togglePage = function (k, on) {
    setFormV(function (o) { const set = (o.pages || []).filter(function (p) { return p !== k; }); if (on) set.push(k); return Object.assign({}, o, { pages: STAFF_PAGE_KEYS.filter(function (p) { return set.indexOf(p) !== -1; }) }); });
  };
  const hay = function (list) { return list.join(' ').toLowerCase(); };
  const needle = normDigits(q).trim().toLowerCase(), nameN = normDigits(nameF).trim().toLowerCase(), orgN = normDigits(orgF).trim().toLowerCase();
  const ROLE_ORDER = { admin: 0, manager: 1, supervisor: 2, matcher: 3, supplier: 4 };
  const sorters = {
    name: function (a, b) { return String(a.name).localeCompare(String(b.name), 'ar'); },
    role: function (a, b) { return ROLE_ORDER[a.role] - ROLE_ORDER[b.role]; },
    org: function (a, b) { return String(a.org || '').localeCompare(String(b.org || ''), 'ar'); },
    status: function (a, b) { return (b.active ? 1 : 0) - (a.active ? 1 : 0); },
    last: function (a, b) { return (a.last ? a.last.getTime() : 0) - (b.last ? b.last.getTime() : 0); }
  };
  const shown = users.filter(function (x) {
    if (roleF && x.role !== roleF) return false;
    if (statF && (statF === 'active') !== !!x.active) return false;
    if (nameN && hay([x.name, x.username]).indexOf(nameN) === -1) return false;
    if (orgN && hay([x.org, x.code, x.taxNo]).indexOf(orgN) === -1) return false;
    return !needle || hay([x.name, x.username, x.org, x.code, x.taxNo]).indexOf(needle) !== -1;
  }).sort(function (a, b) { const r = (sorters[sort.key] || sorters.name)(a, b); return sort.dir === 'asc' ? r : -r; });
  const anyFilter = !!(q || roleF || statF || nameF || orgF);
  const clearFilters = function () { setQ(''); setRoleF(''); setStatF(''); setNameF(''); setOrgF(''); };
  const toggleSort = function (k) { setSort(function (o) { return o.key === k ? { key: k, dir: o.dir === 'asc' ? 'desc' : 'asc' } : { key: k, dir: 'asc' }; }); };
  const textF = function (v, set, lbl) { return input({ type: 'text', className: 'thf', placeholder: 'بحث…', 'aria-label': 'تصفية ' + lbl, value: v, onChange: function (e) { set(e.target.value); } }); };
  const roleSel = function (cls) {
    return select({ className: cls, 'aria-label': 'تصفية حسب الدور', value: roleF, onChange: function (e) { setRoleF(e.target.value); } },
      option({ value: '' }, 'كل الأدوار'), Object.keys(ROLE_LABEL).map(function (r) { return option({ key: r, value: r }, ROLE_LABEL[r]); }));
  };
  const statSel = function (cls) {
    return select({ className: cls, 'aria-label': 'تصفية حسب الحالة', value: statF, onChange: function (e) { setStatF(e.target.value); } },
      option({ value: '' }, 'كل الحالات'), option({ value: 'active' }, 'نشط'), option({ value: 'off' }, 'موقوف'));
  };
  const HEAD = [
    { k: 'name', t: 'المستخدم', f: textF(nameF, setNameF, 'المستخدم') },
    { k: 'role', t: 'الدور', f: roleSel('thf') },
    { k: 'org', t: 'الجهة', f: textF(orgF, setOrgF, 'الجهة') },
    { k: 'status', t: 'الحالة', f: statSel('thf') },
    { k: 'last', t: 'آخر دخول' },
    { k: 'act', t: 'إجراءات', nosort: true }
  ];
  const statusPill = function (x) {
    return span({ className: 'pill ' + (x.active ? (x.mustChange ? 'warn' : 'ok') : 'bad') }, span({ className: 'dot' }), x.active ? (x.mustChange ? 'لم يغيّر كلمة المرور' : 'نشط') : 'موقوف');
  };
  const userRow = function (x) {
    return tr({ key: x.id, className: x.active ? '' : 'off' },
      td({ 'data-label': 'المستخدم' }, div({ className: 'ucell' },
        span({ className: 'uav ' + x.role, 'aria-hidden': 'true' }, String(x.name).charAt(0)),
        div({ className: 'utxt' },
          strong(null, x.name, x.id === me.id ? span({ className: 'you' }, 'أنت') : null),
          span({ className: 'unum' }, 'رقم ', span({ className: 'mono' }, x.username))))),
      td({ 'data-label': 'الدور' }, span({ className: 'rolepill ' + x.role }, ROLE_LABEL[x.role]), x.customPages ? span({ className: 'cust', title: 'صفحات مخصّصة: ' + (x.pages || []).map(function (k) { return PAGE_LABEL[k]; }).join('، ') }, 'مخصّص') : null),
      td({ 'data-label': 'الجهة' }, div({ className: 'utxt' },
        span(null, x.org || '—'),
        x.role === 'supplier' && (x.code || x.taxNo) ? span({ className: 'usub' },
          x.code ? span(null, 'رمز ', span({ className: 'mono' }, x.code)) : null,
          x.code && x.taxNo ? ' · ' : null,
          x.taxNo ? span(null, 'ضريبي ', span({ className: 'mono' }, x.taxNo)) : null) : null)),
      td({ 'data-label': 'الحالة' }, statusPill(x)),
      td({ 'data-label': 'آخر دخول' }, x.last ? since(x.last) : span({ className: 'muted' }, 'لم يدخل بعد')),
      td({ 'data-label': 'إجراءات', className: 'actcell' }, actions(x)));
  };
  const usersList = div({ className: 'ulist' },
    div({ className: 'utools' },
      div({ className: 'usearch' }, h(Icon, { name: 'search' }),
        input({ type: 'search', value: q, placeholder: 'ابحث بالاسم أو الرقم أو الجهة أو رمز المورد', 'aria-label': 'بحث في المستخدمين', onChange: function (e) { setQ(e.target.value); } })),
      roleSel('tool-mobile'), statSel('tool-mobile'),
      anyFilter ? button({ type: 'button', className: 'btn ghost sm', onClick: clearFilters }, 'مسح التصفية') : null,
      span({ className: 'muted small ucount' }, shown.length === users.length ? users.length + ' مستخدم' : shown.length + ' من ' + users.length)),
    div({ className: 'tablewrap' }, table({ className: 'dt utable' },
      thead(null, tr(null, HEAD.map(function (c) {
        const on = sort.key === c.k;
        return th({ key: c.k, scope: 'col', 'aria-sort': c.nosort ? undefined : (on ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none') },
          div({ className: 'thcell' },
            c.nosort ? span({ className: 'thlabel' }, c.t) : button({ type: 'button', className: 'thbtn', onClick: function () { toggleSort(c.k); } }, c.t, h(Icon, { name: on ? (sort.dir === 'asc' ? 'up' : 'down') : 'sort', size: 14 })),
            c.f ? div({ className: 'thslot' }, c.f) : null));
      }))),
      tbody(null, shown.length ? shown.map(userRow) : tr(null, td({ colSpan: 6, className: 'empty' }, users.length ? 'لا يوجد مستخدم يطابق التصفية' : 'لا يوجد مستخدمون'))))));
  const fld = function (id, lbl, ctl, k, hint, cls) {
    return div({ className: 'field' + (cls ? ' ' + cls : '') }, label({ htmlFor: id }, lbl), ctl, errs[k] ? span({ className: 'err', role: 'alert' }, errs[k]) : (hint ? span({ className: 'hint' }, hint) : null));
  };
  return section({ className: 'svcpanel userspage' },
    div({ className: 'svchead' },
      div(null, h2(null, 'إدارة المستخدمين'), p({ className: 'muted small' }, 'إضافة الحسابات وتعديلها وإيقافها وإعادة تعيين كلمات المرور، وتحديد دور كل مستخدم.')),
      button({ className: 'btn primary', onClick: openNew }, h(Icon, { name: 'plus' }), 'مستخدم جديد')),
    div({ className: 'ustats' },
      [['الإجمالي', users.length], ['النشطون', count(function (x) { return x.active; })], ['الموقوفون', count(function (x) { return !x.active; })],
        ['الموردون', count(function (x) { return x.role === 'supplier'; })], ['المطابقون', count(function (x) { return x.role === 'matcher'; })], ['الإدارة', count(function (x) { return x.role === 'manager' || x.role === 'admin'; })]]
        .map(function (s) { return div({ key: s[0], className: 'ustat' }, h('b', null, s[1]), span(null, s[0])); })),
    temp ? div({ className: 'tempbox', role: 'status' },
      span(null, 'كلمة المرور المؤقتة لـ ', strong(null, temp.name), ' (', span({ className: 'mono' }, temp.username), '):'),
      span({ className: 'mono' }, temp.pw),
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { copy(temp.pw); } }, 'نسخ'),
      span({ className: 'hint' }, 'تظهر مرة واحدة، وسيُطلب منه تغييرها عند أول دخول.'),
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { setTemp(null); } }, 'إخفاء')) : null,
    cx ? div({ className: 'confirmbar', role: 'alertdialog' },
      span(null, confirm.type === 'delete' ? 'حذف حساب ' + cx.name + ' نهائياً؟ لا يمكن التراجع، وإن كان له طلبات فسيُرفض الحذف.' : confirm.type === 'toggle' ? (cx.active ? 'إيقاف حساب ' + cx.name + '؟ لن يستطيع الدخول حتى يُفعَّل.' : 'تفعيل حساب ' + cx.name + '؟') : 'إنشاء كلمة مرور مؤقتة جديدة لـ ' + cx.name + '؟ ستبطل كلمة مروره الحالية.'),
      button({ type: 'button', className: 'btn primary sm', onClick: doConfirm }, 'تأكيد'),
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { setConfirm(null); } }, 'إلغاء')) : null,
    formV ? form({ className: 'uformwrap', onSubmit: save, noValidate: true },
      div({ className: 'uformhead' }, h3(null, formV.id ? 'تعديل مستخدم' : 'مستخدم جديد'),
        button({ type: 'button', className: 'uformclose', 'aria-label': 'إغلاق', onClick: closeForm }, h(Icon, { name: 'close', size: 18 }))),
      div({ className: 'uform' },
        fld('uf-name', 'الاسم الكامل', input({ id: 'uf-name', name: 'full-name', autoComplete: 'off', type: 'text', value: formV.name, onChange: function (e) { setF('name', e.target.value); } }), 'name'),
        fld('uf-user', 'رقم المستخدم', input({ id: 'uf-user', name: 'user-number', autoComplete: 'off', type: 'text', className: 'ltr', autoCapitalize: 'none', value: formV.username, onChange: function (e) { setF('username', e.target.value); } }), 'username', 'يكفي رقم، مثل 1 أو 2025.'),
        fld('uf-role', 'الدور', select({ id: 'uf-role', value: formV.role, disabled: formV.id === me.id, onChange: function (e) { const r = e.target.value; setFormV(function (o) { return Object.assign({}, o, { role: r, pages: ROLE_PAGES[r].slice() }); }); } },
          roleOpts.map(function (r) { return option({ key: r, value: r }, ROLE_LABEL[r]); })), 'role', 'يصل إلى: ' + ROLE_PAGES[formV.role].map(function (k) { return PAGE_LABEL[k]; }).join('، ')),
        fld('uf-org', formV.role === 'supplier' ? 'اسم المورد' : 'الجهة / القسم', input({ id: 'uf-org', name: 'organisation', autoComplete: 'off', type: 'text', value: formV.org, onChange: function (e) { setF('org', e.target.value); } }), 'org'),
        formV.role === 'supplier' ? fld('uf-code', 'رمز المورد', input({ id: 'uf-code', name: 'supplier-code', autoComplete: 'off', type: 'text', className: 'ltr', value: formV.code, onChange: function (e) { setF('code', e.target.value); } }), 'code') : null,
        formV.role === 'supplier' ? fld('uf-tax', 'الرقم الضريبي', input({ id: 'uf-tax', name: 'tax-number', autoComplete: 'off', type: 'text', className: 'ltr', inputMode: 'numeric', maxLength: 15, value: formV.taxNo, onChange: function (e) { setF('taxNo', e.target.value); } }), 'taxNo', '15 رقماً، اختياري.') : null,
        !formV.id ? fld('uf-pw', 'كلمة المرور المؤقتة', div({ className: 'pwgen' }, h(PwInput, { id: 'uf-pw', value: formV.password, onChange: function (v) { setF('password', v); }, autoComplete: 'new-password' }),
          button({ type: 'button', className: 'btn ghost', onClick: function () { setF('password', genPass()); } }, 'توليد')), 'password', 'سيُطلب من المستخدم تغييرها عند أول دخول.', 'wide') : null,
        formV.id ? fld('uf-pw2', 'كلمة مرور جديدة', div({ className: 'pwgen' }, h(PwInput, { id: 'uf-pw2', value: formV.password, onChange: function (v) { setF('password', v); }, autoComplete: 'new-password', placeholder: 'اتركها فارغة بدون تغيير' }),
          button({ type: 'button', className: 'btn ghost', onClick: function () { setF('password', genPass()); } }, 'توليد')), 'password', '4 خانات على الأقل. تُحفظ مع «حفظ التعديلات» ويُوقَف دخول المستخدم الحالي ليدخل بها.', 'wide') : null,
        formV.role !== 'supplier' ? div({ className: 'field wide opts' }, span({ className: 'lbl' }, 'الصفحات المسموحة'),
          div({ className: 'optrow' }, STAFF_PAGE_KEYS.map(function (k) {
            return label({ key: k, className: 'checkrow' }, input({ type: 'checkbox', checked: (formV.pages || []).indexOf(k) !== -1, onChange: function (e) { togglePage(k, e.target.checked); } }), PAGE_LABEL[k]);
          }), !samePages(formV.pages, ROLE_PAGES[formV.role]) ? button({ type: 'button', className: 'btn ghost sm', onClick: function () { setF('pages', ROLE_PAGES[formV.role].slice()); } }, 'استعادة صلاحيات الدور') : null),
          errs.pages ? span({ className: 'err', role: 'alert' }, errs.pages) : span({ className: 'hint' }, 'تبدأ من صفحات الدور، وتقدر تضيف أو تسحب صفحات لهذا المستخدم وحده.')) : null,
        formV.id ? div({ className: 'field wide opts' }, span({ className: 'lbl' }, 'خيارات الحساب'),
          div({ className: 'optrow' },
            formV.id !== me.id ? label({ className: 'checkrow' }, input({ type: 'checkbox', checked: formV.active, onChange: function (e) { setF('active', e.target.checked); } }), 'الحساب نشط') : null,
            formV.password ? label({ className: 'checkrow' }, input({ type: 'checkbox', checked: !!formV.mustChange, onChange: function (e) { setF('mustChange', e.target.checked); } }), 'يختار المستخدم كلمة مرور خاصة به عند أول دخول') : null)) : null),
      div({ className: 'formactions' },
        button({ type: 'submit', className: 'btn primary' }, formV.id ? 'حفظ التعديلات' : 'إضافة المستخدم'),
        button({ type: 'button', className: 'btn ghost', onClick: closeForm }, 'إلغاء'))) : null,
    usersList,
    section({ className: 'permwrap' },
      div({ className: 'permhead' }, h3(null, 'الصلاحيات الافتراضية للأدوار'), p({ className: 'muted small' }, 'تُطبَّق عند إنشاء المستخدم، ويمكن تخصيصها لأي مستخدم من نموذج التعديل.')),
      div({ className: 'tablewrap' }, table({ className: 'dt matrix' },
        thead(null, tr(null, th({ scope: 'col' }, 'الصفحة'), Object.keys(ROLE_LABEL).map(function (r) { return th({ key: r, scope: 'col' }, span({ className: 'rolepill ' + r }, ROLE_LABEL[r])); }))),
        tbody(null, Object.keys(PAGE_LABEL).map(function (k) {
          return tr({ key: k }, td(null, PAGE_LABEL[k]), Object.keys(ROLE_LABEL).map(function (r) {
            const ok = ROLE_PAGES[r].indexOf(k) !== -1;
            return td({ key: r }, ok ? span({ className: 'perm yes', role: 'img', 'aria-label': 'مسموح' }, h(Icon, { name: 'check', size: 14 })) : span({ className: 'perm no', role: 'img', 'aria-label': 'غير مسموح' }, '—'));
          }));
        }))))));
}
