'use strict';

/* ---------- التهيئة: the lists the payment forms read from, one tab per list ----------
   Branches, cost centers, main banks, analytical banks, payment methods. A value added here appears in the search boxes of
   "إضافة سداد متعدد" and of the payment order. Switching a value off hides it from new entries; orders already saved keep their text. */
const LOOKUP_TABS = [
  { kind: 'branch', title: 'الفروع', one: 'الفرع', hint: 'فرع الشركة الذي تُحمَّل عليه الدفعة.' },
  { kind: 'costCenter', title: 'مراكز التكلفة', one: 'مركز التكلفة', hint: 'مركز التكلفة الذي تُحمَّل عليه الدفعة.' },
  { kind: 'bank', title: 'البنوك الرئيسية', one: 'البنك الرئيسي', hint: 'البنك الذي يُسدَّد منه.' },
  { kind: 'bankSub', title: 'البنوك التحليلية', one: 'البنك التحليلي', hint: 'الحساب التحليلي أو الحساب الفرعي للبنك.' },
  { kind: 'method', title: 'طرق السداد', one: 'طريقة السداد', hint: 'تحويل بنكي، شيك، نقداً…' }
];

function SettingsPage(props) {
  const [tab, setTab] = useState('branch');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState(null);          // {id, code, name} while a row is being edited
  const info = LOOKUP_TABS.filter(function (t) { return t.kind === tab; })[0];
  const rows = (props.lookups || {})[tab] || [];
  const count = function (k) { return ((props.lookups || {})[k] || []).length; };
  const failMsg = function (ex) { const d = ex && ex.data; return d && d.code ? [].concat(d.code)[0] : (d && d.name ? [].concat(d.name)[0] : (ex && ex.message) || 'تعذّر الحفظ.'); };
  /* numbers sort as numbers (2 before 10), text codes alphabetically */
  const codeKey = function (l) { return String(l.code || '').replace(/\d+/g, function (d) { return ('000000000000' + d).slice(-12); }); };

  function pickTab(k) { setTab(k); setName(''); setCode(''); setErr(''); setEdit(null); }
  function add(e) {
    e.preventDefault();
    if (!code.trim()) { setErr('اكتب الرقم.'); const el = document.getElementById('lk-code'); if (el) el.focus(); return; }
    if (!name.trim()) { setErr('اكتب الاسم.'); const el = document.getElementById('lk-name'); if (el) el.focus(); return; }
    setBusy(true); setErr('');
    props.onAdd(tab, code, name).then(function () { setBusy(false); setName(''); setCode(''); const el = document.getElementById('lk-code'); if (el) el.focus(); }, function (ex) { setBusy(false); setErr(failMsg(ex)); });
  }
  function saveEdit() {
    if (!edit) return;
    if (!edit.code.trim() || !edit.name.trim()) { props.onToast('اكتب الرقم والاسم.'); return; }
    props.onUpdate(edit.id, { code: edit.code, name: edit.name }).then(function () { setEdit(null); props.onToast('حُفظت التعديلات. الأوامر المحفوظة سابقاً تبقى بالاسم القديم.'); }, function (ex) { props.onToast(failMsg(ex)); });
  }
  function toggle(l) { props.onUpdate(l.id, { active: !l.active }).then(function () { props.onToast(l.active ? 'أُوقفت «' + l.name + '»، لن تظهر في الإدخال الجديد.' : 'فُعّلت «' + l.name + '».'); }, function (ex) { props.onToast(failMsg(ex)); }); }
  function remove(l) {
    if (!window.confirm('حذف «' + l.name + '» نهائياً من ' + info.title + '؟ الأوامر المحفوظة سابقاً لا تتأثر.')) return;
    props.onRemove(l).then(function () { if (edit && edit.id === l.id) setEdit(null); }, function (ex) { props.onToast(failMsg(ex)); });
  }

  const editing = function (l) { return !!edit && edit.id === l.id; };
  const onEditKey = function (e) { if (e.key === 'Enter') { e.preventDefault(); saveEdit(); } else if (e.key === 'Escape') setEdit(null); };
  const cols = [
    { key: 'code', label: 'الرقم', filter: 'text', val: codeKey, fv: function (l) { return l.code || ''; }, xl: function (l) { return l.code || ''; },
      render: function (l) {
        if (editing(l)) return input({ type: 'text', className: 'ltr lkcode', autoComplete: 'off', 'aria-label': 'الرقم', value: edit.code, onChange: function (e) { const v = e.target.value; setEdit(function (o) { return { id: o.id, code: v, name: o.name }; }); }, onKeyDown: onEditKey });
        return l.code ? span({ className: 'mono' }, l.code) : span({ className: 'muted' }, '—');
      } },
    { key: 'name', label: 'الاسم', filter: 'text', val: function (l) { return l.name; },
      render: function (l) {
        if (editing(l)) {
          return div({ className: 'lkedit' },
            input({ type: 'text', autoComplete: 'off', autoFocus: true, 'aria-label': 'الاسم', value: edit.name, onChange: function (e) { const v = e.target.value; setEdit(function (o) { return { id: o.id, code: o.code, name: v }; }); }, onKeyDown: onEditKey }),
            button({ type: 'button', className: 'btn primary sm', onClick: saveEdit }, 'حفظ'),
            button({ type: 'button', className: 'btn ghost sm', onClick: function () { setEdit(null); } }, 'إلغاء'));
        }
        return strong({ style: { fontWeight: 600 } }, l.name);
      } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: function (l) { return l.active ? 'مفعّل' : 'موقوف'; }, val: function (l) { return l.active ? 0 : 1; },
      render: function (l) { return span({ className: 'pill ' + (l.active ? 'ok' : 'bad') }, span({ className: 'dot' }), l.active ? 'مفعّل' : 'موقوف'); } },
    { key: 'act', label: 'إجراءات', render: function (l) {
      return div({ className: 'rowacts' },
        button({ type: 'button', className: 'abtn edit', 'aria-label': 'تعديل ' + l.name, onClick: function (e) { e.stopPropagation(); setEdit({ id: l.id, code: l.code || '', name: l.name }); } }, h(Icon, { name: 'pencil', size: 16 }), span({ className: 'abl' }, 'تعديل')),
        button({ type: 'button', className: 'abtn ' + (l.active ? 'stop' : 'edit'), 'aria-label': (l.active ? 'إيقاف ' : 'تفعيل ') + l.name, onClick: function (e) { e.stopPropagation(); toggle(l); } }, h(Icon, { name: l.active ? 'ban' : 'check', size: 16 }), span({ className: 'abl' }, l.active ? 'إيقاف' : 'تفعيل')),
        button({ type: 'button', className: 'abtn stop', 'aria-label': 'حذف ' + l.name, onClick: function (e) { e.stopPropagation(); remove(l); } }, h(Icon, { name: 'trash', size: 16 }), span({ className: 'abl' }, 'حذف')));
    } }
  ];

  return section({ className: 'svcpanel userspage settingspage' },
    div({ className: 'svchead' },
      div(null, h2(null, 'التهيئة'), p({ className: 'muted small' }, 'القوائم التي تقرأ منها نماذج السداد. أضف القيم هنا فتظهر للبحث والاختيار في «إضافة سداد متعدد» وفي أمر السداد.'))),
    div({ className: 'settabs', role: 'tablist', 'aria-label': 'قوائم التهيئة' }, LOOKUP_TABS.map(function (t) {
      return button({ key: t.kind, type: 'button', role: 'tab', id: 'lk-tab-' + t.kind, 'aria-selected': tab === t.kind, 'aria-controls': 'lk-panel', className: 'settab' + (tab === t.kind ? ' on' : ''), onClick: function () { pickTab(t.kind); } },
        t.title, span({ className: 'settab-n' }, count(t.kind)));
    })),
    div({ id: 'lk-panel', role: 'tabpanel', 'aria-labelledby': 'lk-tab-' + tab, className: 'setpanel' },
      form({ className: 'lkadd', onSubmit: add, noValidate: true },
        div({ className: 'lkrow' },
          div({ className: 'field lkf-code' }, label({ htmlFor: 'lk-code' }, 'الرقم'),
            input({ id: 'lk-code', type: 'text', className: 'ltr', autoComplete: 'off', placeholder: 'مثل 1', value: code, onChange: function (e) { setCode(e.target.value); setErr(''); } })),
          div({ className: 'field lkf-name' }, label({ htmlFor: 'lk-name' }, 'اسم ' + info.one),
            input({ id: 'lk-name', type: 'text', autoComplete: 'off', placeholder: 'اكتب الاسم', value: name, onChange: function (e) { setName(e.target.value); setErr(''); } })),
          button({ type: 'submit', className: 'btn primary lkbtn', disabled: busy }, h(Icon, { name: 'plus' }), 'إضافة')),
        err ? span({ className: 'err', role: 'alert' }, err) : span({ className: 'hint' }, info.hint + ' الرقم فريد داخل القائمة.')),
      h(DataTable, { key: tab, cols: cols, rows: rows, exportName: 'تهيئة-' + info.title, onToast: props.onToast, defaultSort: { key: 'code', dir: 'asc' },
        empty: 'لا توجد قيم في ' + info.title + ' بعد. أضف أول قيمة من الحقل أعلاه.' })));
}
