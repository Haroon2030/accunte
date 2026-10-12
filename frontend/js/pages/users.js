'use strict';

const EMPTY_FORM = { id: null, name: '', username: '', role: 'supplier', org: '', password: '', active: true };
function UsersPage(props) {
  const me = props.me;
  const [formV, setFormV] = useState(null);
  const [errs, setErrs] = useState({});
  const [confirm, setConfirm] = useState(null);
  const [temp, setTemp] = useState(null);
  const users = props.users;
  const canManage = function (x) { return me.role === 'admin' || x.role !== 'admin'; };
  const roleOpts = me.role === 'admin' ? ['supplier', 'matcher', 'manager', 'admin'] : ['supplier', 'matcher', 'manager'];
  const count = function (f) { return users.filter(f).length; };
  const setF = function (k, v) { setFormV(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); };
  function openNew() { setTemp(null); setConfirm(null); setErrs({}); setFormV(Object.assign({}, EMPTY_FORM, { password: genPass() })); }
  function openEdit(x) { setTemp(null); setConfirm(null); setErrs({}); setFormV({ id: x.id, name: x.name, username: x.username, role: x.role, org: x.org, password: '', active: x.active }); }
  function save(e) {
    e.preventDefault();
    const f = formV, er = {};
    const un = normUser(f.username);
    if (!f.name.trim()) er.name = 'أدخل الاسم الكامل.';
    if (!/^[a-z0-9._-]{3,30}$/.test(un)) er.username = 'من 3 إلى 30 خانة: حروف إنجليزية صغيرة وأرقام و . _ - فقط.';
    else if (users.some(function (x) { return x.username === un && x.id !== f.id; })) er.username = 'اسم المستخدم مستخدم لحساب آخر.';
    if (f.role === 'supplier' && !f.org.trim()) er.org = 'أدخل اسم المورد التابع له الحساب.';
    if (!f.id) { const m = passErr(f.password); if (m) er.password = m; }
    if (f.id === me.id && f.role !== me.role) er.role = 'لا يمكنك تغيير دور حسابك الحالي.';
    setErrs(er);
    if (Object.keys(er).length) return;
    props.onSave({ id: f.id, name: f.name.trim(), username: un, role: f.role, org: f.role === 'supplier' ? f.org.trim() : (f.org.trim() || 'أسواق الراشد'), password: f.password, active: f.active })
      .then(function (ok) { if (ok) setFormV(null); });
  }
  function doConfirm() {
    const x = users.filter(function (u) { return u.id === confirm.id; })[0];
    if (!x) { setConfirm(null); return; }
    if (confirm.type === 'toggle') props.onToggle(x.id);
    else props.onReset(x.id).then(function (pw) { if (pw) setTemp({ name: x.name, username: x.username, pw: pw }); });
    setConfirm(null);
  }
  function copy(text) {
    try { navigator.clipboard.writeText(text).then(function () { props.onToast('نُسخت كلمة المرور.'); }, function () { props.onToast('تعذّر النسخ، انسخها يدوياً.'); }); } catch (e) { props.onToast('تعذّر النسخ، انسخها يدوياً.'); }
  }
  const cx = confirm ? users.filter(function (u) { return u.id === confirm.id; })[0] : null;
  const cols = [
    { key: 'name', label: 'الاسم', filter: 'text', val: function (x) { return x.name; }, render: function (x) { return strong({ style: { fontWeight: 600 } }, x.name, x.id === me.id ? span({ className: 'muted small' }, ' (أنت)') : null); } },
    { key: 'username', label: 'اسم المستخدم', filter: 'text', val: function (x) { return x.username; }, render: function (x) { return span({ className: 'mono' }, x.username); } },
    { key: 'role', label: 'الدور', filter: 'select', fv: function (x) { return ROLE_LABEL[x.role]; }, val: function (x) { return ROLE_LABEL[x.role]; }, render: function (x) { return ROLE_LABEL[x.role]; } },
    { key: 'org', label: 'الجهة', filter: 'text', val: function (x) { return x.org; }, render: function (x) { return x.org; } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: function (x) { return x.active ? 'نشط' : 'موقوف'; }, val: function (x) { return x.active ? 1 : 0; },
      render: function (x) { return span({ className: 'pill ' + (x.active ? (x.mustChange ? 'warn' : 'ok') : 'bad') }, span({ className: 'dot' }), x.active ? (x.mustChange ? 'نشط، لم يغيّر كلمة المرور' : 'نشط') : 'موقوف'); } },
    { key: 'last', label: 'آخر دخول', val: function (x) { return x.last ? x.last.getTime() : 0; }, render: function (x) { return x.last ? since(x.last) : span({ className: 'muted' }, 'لم يدخل بعد'); } },
    { key: 'act', label: 'إجراءات', render: function (x) {
      if (!canManage(x)) return span({ className: 'muted small' }, 'للمدير فقط');
      return div({ style: { display: 'flex', flexWrap: 'wrap', gap: 6 } },
        button({ type: 'button', className: 'btn ghost sm', onClick: function () { openEdit(x); } }, 'تعديل'),
        button({ type: 'button', className: 'btn ghost sm', onClick: function () { setFormV(null); setTemp(null); setConfirm({ type: 'reset', id: x.id }); } }, 'كلمة مرور جديدة'),
        x.id === me.id ? null : button({ type: 'button', className: 'btn ghost sm', onClick: function () { setFormV(null); setTemp(null); setConfirm({ type: 'toggle', id: x.id }); } }, x.active ? 'إيقاف' : 'تفعيل'));
    } }
  ];
  const fld = function (id, lbl, ctl, k, hint) {
    return div({ className: 'field' }, label({ htmlFor: id }, lbl), ctl, errs[k] ? span({ className: 'err', role: 'alert' }, errs[k]) : (hint ? span({ className: 'hint' }, hint) : null));
  };
  return section({ className: 'svcpanel' },
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
    formV ? form({ className: 'panel', onSubmit: save, noValidate: true },
      h3(null, formV.id ? 'تعديل مستخدم' : 'مستخدم جديد'),
      div({ className: 'uform' },
        fld('uf-name', 'الاسم الكامل', input({ id: 'uf-name', type: 'text', value: formV.name, onChange: function (e) { setF('name', e.target.value); } }), 'name'),
        fld('uf-user', 'اسم المستخدم', input({ id: 'uf-user', type: 'text', className: 'ltr', autoCapitalize: 'none', value: formV.username, onChange: function (e) { setF('username', e.target.value); } }), 'username', 'حروف إنجليزية صغيرة وأرقام.'),
        fld('uf-role', 'الدور', select({ id: 'uf-role', value: formV.role, disabled: formV.id === me.id, onChange: function (e) { setF('role', e.target.value); } },
          roleOpts.map(function (r) { return option({ key: r, value: r }, ROLE_LABEL[r]); })), 'role', 'يصل إلى: ' + ROLE_PAGES[formV.role].map(function (k) { return PAGE_LABEL[k]; }).join('، ')),
        fld('uf-org', formV.role === 'supplier' ? 'اسم المورد' : 'الجهة / القسم', input({ id: 'uf-org', type: 'text', value: formV.org, onChange: function (e) { setF('org', e.target.value); } }), 'org'),
        !formV.id ? fld('uf-pw', 'كلمة المرور المؤقتة', div({ className: 'pwgen' }, h(PwInput, { id: 'uf-pw', value: formV.password, onChange: function (v) { setF('password', v); }, autoComplete: 'new-password' }),
          button({ type: 'button', className: 'btn ghost', onClick: function () { setF('password', genPass()); } }, 'توليد')), 'password', 'سيُطلب من المستخدم تغييرها عند أول دخول.') : null,
        formV.id && formV.id !== me.id ? div({ className: 'field' }, span({ className: 'lbl' }, 'حالة الحساب'),
          label({ className: 'checkrow' }, input({ type: 'checkbox', checked: formV.active, onChange: function (e) { setF('active', e.target.checked); } }), 'الحساب نشط')) : null),
      div({ className: 'formactions' },
        button({ type: 'submit', className: 'btn primary' }, formV.id ? 'حفظ التعديلات' : 'إضافة المستخدم'),
        button({ type: 'button', className: 'btn ghost', onClick: function () { setFormV(null); } }, 'إلغاء'))) : null,
    h(DataTable, { cols: cols, rows: users, defaultSort: { key: 'name', dir: 'asc' }, empty: 'لا يوجد مستخدمون' }),
    section({ className: 'panel' },
      h3(null, 'الصلاحيات حسب الدور'),
      div({ className: 'tablewrap' }, table({ className: 'dt matrix' },
        thead(null, tr(null, th({ scope: 'col' }, 'الصفحة'), Object.keys(ROLE_LABEL).map(function (r) { return th({ key: r, scope: 'col' }, ROLE_LABEL[r]); }))),
        tbody(null, Object.keys(PAGE_LABEL).map(function (k) {
          return tr({ key: k }, td(null, PAGE_LABEL[k]), Object.keys(ROLE_LABEL).map(function (r) {
            const ok = ROLE_PAGES[r].indexOf(k) !== -1;
            return td({ key: r }, span({ className: ok ? 'yes' : 'no', 'aria-label': ok ? 'مسموح' : 'غير مسموح' }, ok ? '✓' : '—'));
          }));
        }))))));
}
