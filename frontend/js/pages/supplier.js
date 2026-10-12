'use strict';

/* ---------- supplier ---------- */
function SupplierHome(props) {
  const svc = props.service;
  const mine = props.reqs.filter(function (r) { return r.supplier === props.supplier; });
  const myC = props.complaints.filter(function (c) { return c.supplier === props.supplier; });
  const unR = unreadSum(mine, 'supplier', props.seen);
  const unC = unreadSum(myC, 'supplier', props.seen);
  const items = [
    { key: 'recon', icon: 'file', title: 'مطابقة كشف الحساب', sub: 'طلبات المطابقة', count: mine.length, unread: unR },
    { key: 'complaint', icon: 'alert', title: 'شكوى المدير المالي', sub: 'شكاوى مرفوعة', count: myC.length, unread: unC }
  ];
  const recon = h(ServicePanel, {
    key: 'recon', id: 'sv-recon', title: 'مطابقة كشف الحساب', sub: 'قدّم طلب مطابقة لكشف حسابك وتابع كل خطوة فيه.',
    actionLabel: 'طلب جديد', onAction: props.onNew,
    alert: h(AlertBar, { n: unR, text: newMsgText(unR, 'المطابق') }),
    rows: mine, keyOf: function (r) { return statusOf(r, 'supplier').key; }, text: function (r) { return r.id + ' ' + r.period; },
    options: [['all', 'كل الحالات'], ['reply', 'يحتاج ردك'], ['dialogue', 'بانتظار المطابق'], ['matching', 'قيد المطابقة'], ['queue', 'بانتظار التوزيع'], ['done', 'منجز']],
    render: function (rows) { return h(RequestTable, { rows: rows, role: 'supplier', seen: props.seen, hide: ['supplier', 'matcher'], onOpen: props.onOpen, defaultSort: { key: 'updated', dir: 'desc' } }); }
  });
  const complaint = h(ServicePanel, {
    key: 'complaint', id: 'sv-complaint', title: 'شكوى المدير المالي', sub: 'ترفع شكواك مباشرة إلى المدير المالي وتتابع رده.',
    actionLabel: 'شكوى جديدة', onAction: props.onNewC, alert: h(AlertBar, { n: unC, text: newMsgText(unC, 'المدير المالي') }),
    rows: myC, keyOf: function (c) { return statusC(c, 'supplier').key; }, text: function (c) { return c.id + ' ' + c.subject + ' ' + c.category; },
    options: [['all', 'كل الحالات'], ['new', 'وصلت المدير المالي'], ['review', 'قيد المراجعة'], ['closed', 'تم الرد']],
    render: function (rows) { return h(ComplaintTable, { rows: rows, role: 'supplier', seen: props.seen, hide: ['supplier'], onOpen: props.onOpenC, defaultSort: { key: 'created', dir: 'desc' } }); }
  });
  return div({ className: 'shell' },
    h('nav', { className: 'side', 'aria-label': 'الخدمات' },
      div({ className: 'sidehead' }, 'الخدمات'),
      items.map(function (it) {
        return button({ key: it.key, className: 'navitem', 'aria-current': svc === it.key ? 'page' : undefined, onClick: function () { props.onService(it.key); } },
          h(Icon, { name: it.icon, size: 20 }),
          span({ className: 'navtxt' }, strong(null, it.title), h('small', null, it.sub)),
          span({ className: 'navend' }, h(Badge, { n: it.unread }), span({ className: 'navcount' }, it.count)));
      })),
    div({ className: 'work' }, svc === 'complaint' ? complaint : recon));
}

function NewRequest(props) {
  const periods = ['سبتمبر 2026', 'الربع الثالث 2026', 'أغسطس 2026', 'من بداية السنة 2026'];
  const [period, setPeriod] = useState(periods[0]);
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  function submit(e) {
    e.preventDefault();
    if (!file) { setError('أرفق كشف الحساب أولاً (PDF أو Excel) ثم أرسل الطلب.'); return; }
    props.onSubmit({ period: period, notes: notes.trim(), file: file });
  }
  return section({ className: 'panel formcard' },
    h3(null, 'طلب مطابقة جديد'),
    form({ onSubmit: submit, noValidate: true },
      div({ className: 'field' },
        label({ htmlFor: 'nr-period' }, 'الفترة المطلوب مطابقتها'),
        select({ id: 'nr-period', value: period, onChange: function (e) { setPeriod(e.target.value); } },
          periods.map(function (x) { return option({ key: x, value: x }, x); }))),
      div({ className: 'field' },
        span({ className: 'lbl' }, 'كشف حساب المورد'),
        div({ className: 'dropzone' },
          input({ id: 'nr-file', type: 'file', hidden: true, accept: '.pdf,.xlsx,.xls,.csv', onChange: function (e) {
            const f = e.target.files[0];
            if (f) { setFile({ name: f.name, size: f.size, file: f }); setError(''); }
            e.target.value = '';
          } }),
          label({ htmlFor: 'nr-file', className: 'btn ghost' }, h(Icon, { name: 'clip' }), file ? 'تغيير الملف' : 'اختيار ملف'),
          file ? h(FileChip, { f: file, onRemove: function () { setFile(null); } }) : span({ className: 'hint' }, 'PDF أو Excel أو CSV')),
        error ? div({ className: 'err', role: 'alert' }, error) : null),
      div({ className: 'field' },
        label({ htmlFor: 'nr-notes' }, 'ملاحظات للمطابق (اختياري)'),
        textarea({ id: 'nr-notes', rows: 3, value: notes, onChange: function (e) { setNotes(e.target.value); }, placeholder: 'مثال: الفاتورة INV-88213 فيها خصم لم يظهر في كشفكم' })),
      div({ className: 'formactions' },
        button({ type: 'submit', className: 'btn primary' }, h(Icon, { name: 'send' }), 'إرسال الطلب'),
        button({ type: 'button', className: 'btn ghost', onClick: props.onCancel }, 'إلغاء'))));
}

function NewComplaint(props) {
  const mine = props.reqs.filter(function (r) { return r.supplier === props.supplier; });
  const [category, setCategory] = useState(C_CATS[0]);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [related, setRelated] = useState('');
  const [files, setFiles] = useState([]);
  const [error, setError] = useState('');
  function submit(e) {
    e.preventDefault();
    if (!subject.trim() || !body.trim()) { setError('اكتب عنوان الشكوى وتفاصيلها قبل الإرسال.'); return; }
    props.onSubmit({ category: category, subject: subject.trim(), body: body.trim(), related: related || null, files: files });
  }
  return section({ className: 'panel formcard' },
    h3(null, 'شكوى المدير المالي'),
    div({ className: 'note', style: { marginBottom: 16 } }, 'تصل الشكوى إلى المدير المالي مباشرة، ولا يطّلع عليها المطابقون.'),
    form({ onSubmit: submit, noValidate: true },
      div({ className: 'field' },
        label({ htmlFor: 'nc-category' }, 'نوع الشكوى'),
        select({ id: 'nc-category', value: category, onChange: function (e) { setCategory(e.target.value); } },
          C_CATS.map(function (x) { return option({ key: x, value: x }, x); }))),
      div({ className: 'field' },
        label({ htmlFor: 'nc-subject' }, 'عنوان الشكوى'),
        input({ id: 'nc-subject', type: 'text', value: subject, placeholder: 'مثال: دفعة معتمدة لم تصل', onChange: function (e) { setSubject(e.target.value); } })),
      div({ className: 'field' },
        label({ htmlFor: 'nc-related' }, 'طلب مطابقة مرتبط (اختياري)'),
        select({ id: 'nc-related', value: related, onChange: function (e) { setRelated(e.target.value); } },
          option({ value: '' }, 'غير مرتبطة بطلب'),
          mine.map(function (r) { return option({ key: r.id, value: r.id }, r.id + ' · ' + r.period); }))),
      div({ className: 'field' },
        label({ htmlFor: 'nc-body' }, 'تفاصيل الشكوى'),
        textarea({ id: 'nc-body', rows: 5, value: body, placeholder: 'اشرح ما حدث ومتى، وما الذي تطلبه', onChange: function (e) { setBody(e.target.value); } })),
      div({ className: 'field' },
        span({ className: 'lbl' }, 'مستندات داعمة (اختياري)'),
        div({ className: 'dropzone' },
          input({ id: 'nc-file', type: 'file', multiple: true, hidden: true, onChange: function (e) {
            const added = Array.prototype.map.call(e.target.files, function (f) { return { name: f.name, size: f.size, file: f }; });
            setFiles(files.concat(added)); e.target.value = '';
          } }),
          label({ htmlFor: 'nc-file', className: 'btn ghost' }, h(Icon, { name: 'clip' }), 'إرفاق مستند'),
          files.length ? div({ className: 'picked' }, files.map(function (f, i) {
            return h(FileChip, { key: f.name + i, f: f, onRemove: function () { setFiles(files.filter(function (_, j) { return j !== i; })); } });
          })) : span({ className: 'hint' }, 'إشعار تحويل، فاتورة، أو أي مستند يوضح الشكوى')),
        error ? div({ className: 'err', role: 'alert' }, error) : null),
      div({ className: 'formactions' },
        button({ type: 'submit', className: 'btn primary' }, h(Icon, { name: 'send' }), 'إرسال إلى المدير المالي'),
        button({ type: 'button', className: 'btn ghost', onClick: props.onCancel }, 'إلغاء'))));
}
