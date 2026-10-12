'use strict';

const EMPTY_FORM = { id: null, name: '', username: '', role: 'supplier', org: '', taxNo: '', code: '', password: '', active: true };
function UsersPage(props) {
  const me = props.me;
  const [formV, setFormV] = useState(null);
  const [errs, setErrs] = useState({});
  const [confirm, setConfirm] = useState(null);
  const [temp, setTemp] = useState(null);
  const [q, setQ] = useState('');
  const [roleF, setRoleF] = useState('');
  const [statF, setStatF] = useState('');
  const users = props.users;
  const canManage = function (x) { return me.role === 'admin' || x.role !== 'admin'; };
  const roleOpts = me.role === 'admin' ? ['supplier', 'matcher', 'manager', 'admin'] : ['supplier', 'matcher', 'manager'];
  const normDigits = function (v) { return String(v || '').replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 1632); }).replace(/\s/g, ''); };
  const count = function (f) { return users.filter(f).length; };
  const setF = function (k, v) { setFormV(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); };
  function openNew() { setTemp(null); setConfirm(null); setErrs({}); setFormV(Object.assign({}, EMPTY_FORM, { password: genPass() })); }
  function openEdit(x) { setTemp(null); setConfirm(null); setErrs({}); setFormV({ id: x.id, name: x.name, username: x.username, role: x.role, org: x.org, taxNo: x.taxNo || '', code: x.code || '', password: '', active: x.active }); }
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
    if (!f.id) { const m = passErr(f.password); if (m) er.password = m; }
    if (f.id === me.id && f.role !== me.role) er.role = 'لا يمكنك تغيير دور حسابك الحالي.';
    setErrs(er);
    if (Object.keys(er).length) return;
    props.onSave({ id: f.id, name: f.name.trim(), username: un, role: f.role, org: f.role === 'supplier' ? f.org.trim() : (f.org.trim() || 'أسواق الرشيد'), taxNo: f.role === 'supplier' ? normDigits(f.taxNo) : '', code: f.role === 'supplier' ? f.code.trim() : '', password: f.password, active: f.active })
      .then(function () { setFormV(null); })
      .catch(function (ex) {
        const d = ex.data, known = { name: 1, username: 1, role: 1, org: 1, code: 1, taxNo: 1, password: 1 }, fe = {};
        if (d && typeof d === 'object' && !d.detail) Object.keys(d).forEach(function (k) { if (known[k]) fe[k] = [].concat(d[k])[0]; });
        if (Object.keys(fe).length) setErrs(fe); else props.onToast(ex.message);
      });
  }
  function doConfirm() {
    const x = users.filter(function (u) { return u.id === confirm.id; })[0];
    if (!x) { setConfirm(null); return; }
    if (confirm.type === 'toggle') props.onToggle(x.id);
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
    return div({ className: 'rowacts' },
      button({ type: 'button', className: 'linkbtn', onClick: function () { openEdit(x); } }, 'تعديل'),
      button({ type: 'button', className: 'linkbtn', onClick: function () { setFormV(null); setTemp(null); setConfirm({ type: 'reset', id: x.id }); } }, 'كلمة مرور جديدة'),
      x.id === me.id ? null : button({ type: 'button', className: 'linkbtn' + (x.active ? ' danger' : ''), onClick: function () { setFormV(null); setTemp(null); setConfirm({ type: 'toggle', id: x.id }); } }, x.active ? 'إيقاف' : 'تفعيل'));
  };
  const needle = normDigits(q).trim().toLowerCase();
  const shown = users.filter(function (x) {
    if (roleF && x.role !== roleF) return false;
    if (statF && (statF === 'active') !== !!x.active) return false;
    if (!needle) return true;
    return [x.name, x.username, x.org, x.code, x.taxNo].join(' ').toLowerCase().indexOf(needle) !== -1;
  }).sort(function (a, b) { return String(a.name).localeCompare(String(b.name), 'ar'); });
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
      td({ 'data-label': 'الدور' }, span({ className: 'rolepill ' + x.role }, ROLE_LABEL[x.role])),
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
      select({ 'aria-label': 'تصفية حسب الدور', value: roleF, onChange: function (e) { setRoleF(e.target.value); } },
        option({ value: '' }, 'كل الأدوار'), Object.keys(ROLE_LABEL).map(function (r) { return option({ key: r, value: r }, ROLE_LABEL[r]); })),
      select({ 'aria-label': 'تصفية حسب الحالة', value: statF, onChange: function (e) { setStatF(e.target.value); } },
        option({ value: '' }, 'كل الحالات'), option({ value: 'active' }, 'نشط'), option({ value: 'off' }, 'موقوف')),
      span({ className: 'muted small ucount' }, shown.length === users.length ? users.length + ' مستخدم' : shown.length + ' من ' + users.length)),
    div({ className: 'tablewrap' }, table({ className: 'dt utable' },
      thead(null, tr(null, ['المستخدم', 'الدور', 'الجهة', 'الحالة', 'آخر دخول', 'إجراءات'].map(function (t) { return th({ key: t, scope: 'col' }, t); }))),
      tbody(null, shown.length ? shown.map(userRow) : tr(null, td({ colSpan: 6, className: 'empty' }, users.length ? 'لا يوجد مستخدم يطابق البحث' : 'لا يوجد مستخدمون'))))));
  const fld = function (id, lbl, ctl, k, hint) {
    return div({ className: 'field' }, label({ htmlFor: id }, lbl), ctl, errs[k] ? span({ className: 'err', role: 'alert' }, errs[k]) : (hint ? span({ className: 'hint' }, hint) : null));
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
      span(null, confirm.type === 'toggle' ? (cx.active ? 'إيقاف حساب ' + cx.name + '؟ لن يستطيع الدخول حتى يُفعَّل.' : 'تفعيل حساب ' + cx.name + '؟') : 'إنشاء كلمة مرور مؤقتة جديدة لـ ' + cx.name + '؟ ستبطل كلمة مروره الحالية.'),
      button({ type: 'button', className: 'btn primary sm', onClick: doConfirm }, 'تأكيد'),
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { setConfirm(null); } }, 'إلغاء')) : null,
    formV ? form({ className: 'uformwrap', onSubmit: save, noValidate: true },
      h3(null, formV.id ? 'تعديل مستخدم' : 'مستخدم جديد'),
      div({ className: 'uform' },
        fld('uf-name', 'الاسم الكامل', input({ id: 'uf-name', type: 'text', value: formV.name, onChange: function (e) { setF('name', e.target.value); } }), 'name'),
        fld('uf-user', 'رقم المستخدم', input({ id: 'uf-user', type: 'text', className: 'ltr', autoCapitalize: 'none', value: formV.username, onChange: function (e) { setF('username', e.target.value); } }), 'username', 'يكفي رقم، مثل 1 أو 2025.'),
        fld('uf-role', 'الدور', select({ id: 'uf-role', value: formV.role, disabled: formV.id === me.id, onChange: function (e) { setF('role', e.target.value); } },
          roleOpts.map(function (r) { return option({ key: r, value: r }, ROLE_LABEL[r]); })), 'role', 'يصل إلى: ' + ROLE_PAGES[formV.role].map(function (k) { return PAGE_LABEL[k]; }).join('، ')),
        fld('uf-org', formV.role === 'supplier' ? 'اسم المورد' : 'الجهة / القسم', input({ id: 'uf-org', type: 'text', value: formV.org, onChange: function (e) { setF('org', e.target.value); } }), 'org'),
        formV.role === 'supplier' ? fld('uf-code', 'رمز المورد', input({ id: 'uf-code', type: 'text', className: 'ltr', value: formV.code, onChange: function (e) { setF('code', e.target.value); } }), 'code') : null,
        formV.role === 'supplier' ? fld('uf-tax', 'الرقم الضريبي', input({ id: 'uf-tax', type: 'text', className: 'ltr', inputMode: 'numeric', maxLength: 15, value: formV.taxNo, onChange: function (e) { setF('taxNo', e.target.value); } }), 'taxNo', '15 رقماً، اختياري.') : null,
        !formV.id ? fld('uf-pw', 'كلمة المرور المؤقتة', div({ className: 'pwgen' }, h(PwInput, { id: 'uf-pw', value: formV.password, onChange: function (v) { setF('password', v); }, autoComplete: 'new-password' }),
          button({ type: 'button', className: 'btn ghost', onClick: function () { setF('password', genPass()); } }, 'توليد')), 'password', 'سيُطلب من المستخدم تغييرها عند أول دخول.') : null,
        formV.id && formV.id !== me.id ? div({ className: 'field' }, span({ className: 'lbl' }, 'حالة الحساب'),
          label({ className: 'checkrow' }, input({ type: 'checkbox', checked: formV.active, onChange: function (e) { setF('active', e.target.checked); } }), 'الحساب نشط')) : null),
      div({ className: 'formactions' },
        button({ type: 'submit', className: 'btn primary' }, formV.id ? 'حفظ التعديلات' : 'إضافة المستخدم'),
        button({ type: 'button', className: 'btn ghost', onClick: function () { setFormV(null); } }, 'إلغاء'))) : null,
    usersList,
    section({ className: 'permwrap' },
      div({ className: 'permhead' }, h3(null, 'الصلاحيات حسب الدور'), p({ className: 'muted small' }, 'الصفحات التي يراها كل دور بعد تسجيل الدخول.')),
      div({ className: 'tablewrap' }, table({ className: 'dt matrix' },
        thead(null, tr(null, th({ scope: 'col' }, 'الصفحة'), Object.keys(ROLE_LABEL).map(function (r) { return th({ key: r, scope: 'col' }, span({ className: 'rolepill ' + r }, ROLE_LABEL[r])); }))),
        tbody(null, Object.keys(PAGE_LABEL).map(function (k) {
          return tr({ key: k }, td(null, PAGE_LABEL[k]), Object.keys(ROLE_LABEL).map(function (r) {
            const ok = ROLE_PAGES[r].indexOf(k) !== -1;
            return td({ key: r }, ok ? span({ className: 'perm yes', role: 'img', 'aria-label': 'مسموح' }, h(Icon, { name: 'check', size: 14 })) : span({ className: 'perm no', role: 'img', 'aria-label': 'غير مسموح' }, '—'));
          }));
        }))))));
}
