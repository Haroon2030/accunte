'use strict';

/* =====================================================================
   Statement reconciliation page (internal tool: reconciliation team + finance manager only)
   ===================================================================== */
const rcName = function (n) { return String(n || '').replace(/(\.[A-Za-z0-9]+)$/, '\u200E$1'); };
const rcMoney = function (n) { return n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
const rcSigned = function (n) { return (n > 0 ? '+' : '') + rcMoney(n); };
const RC_SRC = { excel: 'Excel / CSV', word: 'Word', pdf: 'PDF نصي', ocr: 'قراءة آلية (صورة)', paste: 'نص ملصوق', sample: 'بيانات تجريبية' };
const RC_PERSP_AUTO = ' (حُدّد تلقائياً)';
const RC_PERSP = {
  supplier: 'كشف المورد: المدين = فاتورة علينا، الدائن = دفعة أو خصم',
  company: 'كشف نظامنا: الدائن = فاتورة من المورد، المدين = دفعة أو خصم'
};
const RC_FIELD_LABEL = [['date', 'التاريخ'], ['type', 'نوع المستند'], ['doc', 'رقم المستند'], ['ref', 'رقم المرجع'], ['desc', 'البيان'], ['debit', 'مدين'], ['credit', 'دائن'], ['amount', 'مبلغ واحد (بدل مدين/دائن)'], ['balance', 'الرصيد']];
function rcEmptySide(persp) { return { status: 'idle', name: '', note: '', err: '', rows: [], headerIdx: 0, map: {}, detected: false, source: '', persp: persp }; }
function rcHeaderNames(side) {
  const hr = side.rows[side.headerIdx] || [];
  let n = Math.max(hr.length, 1);
  side.rows.slice(0, 400).forEach(function (r) { n = Math.max(n, (r || []).length); });
  const out = [];
  for (let i = 0; i < n; i++) out.push(hr[i] instanceof Date ? 'عمود ' + (i + 1) : (String(hr[i] == null ? '' : hr[i]).trim() || 'عمود ' + (i + 1)));
  return out;
}
function rcCsv(res) {
  const q = function (v) { return '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"'; };
  const head = ['الرقم', 'الحالة', 'النوع', 'رقم المستند (المورد)', 'رقم المستند (نظامنا)', 'التاريخ', 'عند المورد', 'عندنا', 'الفرق', 'السبب والإجراء'];
  const lines = [head.map(q).join(',')];
  res.items.forEach(function (it) {
    lines.push([it.id, RC_STATUS[it.status].label, RC_KIND[it.kind], it.docA, it.docB, it.date ? fmtDate(it.date) : '', it.amtA == null ? '' : it.amtA.toFixed(2), it.amtB == null ? '' : it.amtB.toFixed(2), it.diff.toFixed(2), it.reason].map(q).join(','));
  });
  return '﻿' + lines.join('\r\n');
}

const RC_ITEM_COLS = [
  { key: 'id', label: 'الرقم', val: function (r) { return r.id; }, render: function (r) { return span({ className: 'mono' }, r.id); } },
  { key: 'status', label: 'الحالة', filter: 'select', fv: function (r) { return RC_STATUS[r.status].label; }, val: function (r) { return RC_STATUS[r.status].label; }, render: function (r) { return h(StatusPill, { st: RC_STATUS[r.status] }); } },
  { key: 'kind', label: 'النوع', filter: 'select', fv: function (r) { return RC_KIND[r.kind]; }, val: function (r) { return RC_KIND[r.kind]; }, render: function (r) { return RC_KIND[r.kind]; } },
  { key: 'doc', label: 'رقم المستند', filter: 'text', fv: function (r) { return r.docA + ' ' + r.docB; }, val: function (r) { return r.doc; }, render: function (r) {
    return span({ className: 'mono' }, r.docA && r.docB && r.docA !== r.docB ? r.docA + ' ↔ ' + r.docB : (r.doc || '—')); } },
  { key: 'date', label: 'التاريخ', val: function (r) { return r.date ? r.date.getTime() : 0; }, render: function (r) { return r.date ? fmtDate(r.date) : '—'; } },
  { key: 'amtA', label: 'عند المورد', val: function (r) { return r.amtA == null ? -1e15 : r.amtA; }, render: function (r) { return span({ className: 'mono' }, rcMoney(r.amtA)); } },
  { key: 'amtB', label: 'عندنا', val: function (r) { return r.amtB == null ? -1e15 : r.amtB; }, render: function (r) { return span({ className: 'mono' }, rcMoney(r.amtB)); } },
  { key: 'diff', label: 'الفرق', val: function (r) { return r.diff; }, render: function (r) { return span({ className: 'mono rc-diff' + (Math.abs(r.diff) > 0.005 ? ' off' : '') }, rcSigned(r.diff)); } },
  { key: 'reason', label: 'السبب والإجراء المقترح', render: function (r) { return span({ className: 'rc-reason' }, r.reason || '—'); } }
];
const RC_LINE_COLS = [
  { key: 'date', label: 'التاريخ', val: function (r) { return r.date ? r.date.getTime() : 0; }, render: function (r) { return r.date ? fmtDate(r.date) : '—'; } },
  { key: 'doc', label: 'رقم المستند', val: function (r) { return r.doc; }, render: function (r) { return span({ className: 'mono' }, r.doc || '—'); } },
  { key: 'desc', label: 'البيان', val: function (r) { return r.desc; }, render: function (r) { return r.desc || '—'; } },
  { key: 'kind', label: 'النوع', val: function (r) { return RC_KIND[r.kind]; }, render: function (r) { return RC_KIND[r.kind]; } },
  { key: 'amount', label: 'المبلغ (موحّد)', val: function (r) { return r.amount; }, render: function (r) { return span({ className: 'mono' }, rcSigned(r.amount)); } }
];

function RcSide(props) {
  const side = props.side, k = props.k;
  const [over, setOver] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState('');
  const inputId = 'rc-file-' + k;
  const names = rcHeaderNames(side);
  const led = props.ledger;
  const ready = side.status === 'ready';
  const warnBal = ready && led && led.statedBalance != null && Math.abs(Math.abs(led.statedBalance) - Math.abs(led.sum)) > 0.5;
  const pick = function (f) { if (f) props.onFile(f); };
  return section({ className: 'panel rc-side' },
    div({ className: 'rc-sidehead' }, h3({ className: 'sidetitle' }, (props.title.match(/^(\d) · /) ? span({ className: 'stepno' }, props.title.charAt(0)) : null), props.title.replace(/^\d · /, '')), ready ? button({ type: 'button', className: 'btn ghost sm', onClick: props.onClear }, 'إزالة') : null),
    label({ htmlFor: inputId, className: 'dz' + (over ? ' over' : '') + (ready ? ' ready' : '') + (side.status === 'error' ? ' bad' : ''),
      onDragOver: function (e) { e.preventDefault(); setOver(true); }, onDragLeave: function () { setOver(false); },
      onDrop: function (e) { e.preventDefault(); setOver(false); pick(e.dataTransfer && e.dataTransfer.files[0]); } },
      h(Icon, { name: ready ? 'check' : 'upload', size: 26 }),
      side.status === 'reading' ? span({ className: 'dz-t' }, rcName(side.name), h('small', null, side.note || 'جارٍ القراءة…'))
        : ready ? span({ className: 'dz-t' }, rcName(side.name), h('small', null, RC_SRC[side.source] + ' · ' + (led ? led.lines.length : 0) + ' بند · المجموع ' + rcMoney(led ? led.sum : 0)))
        : side.status === 'error' ? span({ className: 'dz-t' }, 'تعذّرت القراءة', h('small', null, side.err))
        : span({ className: 'dz-t' }, 'اسحب الملف هنا أو اضغط للاختيار', h('small', null, 'Excel · CSV · Word · PDF · صورة')),
      input({ id: inputId, type: 'file', className: 'sr-only', accept: '.xlsx,.xlsm,.xls,.csv,.docx,.pdf,.png,.jpg,.jpeg,.webp,image/*',
        onChange: function (e) { pick(e.target.files[0]); e.target.value = ''; } })),
    side.note && ready ? div({ className: 'rc-note' + (side.source === 'ocr' ? ' warn' : '') }, side.note) : null,
    warnBal ? div({ className: 'rc-note warn' }, 'الرصيد المذكور في الملف (' + rcMoney(led.statedBalance) + ') يختلف عن مجموع البنود المقروءة (' + rcMoney(led.sum) + '). قد تكون هناك بنود لم تُقرأ.') : null,
    ready && led && !led.lines.length ? div({ className: 'rc-note warn' }, 'لم أجد بنوداً. حدّد الأعمدة يدوياً من الأسفل.') : null,
    ready && led && led.lines.length && led.lines.every(function (l) { return Math.abs(l.amount) < 1e-9; })
      ? div({ className: 'rc-note warn' }, 'كل المبالغ المقروءة صفر.' + (side.diag && side.diag.emptyFormulas ? ' الملف يحتوي ' + side.diag.emptyFormulas + ' معادلة بلا قيمة محفوظة. افتحه في Excel واحفظه ثم أعد رفعه، أو انسخ الجدول كقيم.' : ' راجع اختيار الأعمدة من الأسفل.')) : null,
    ready && !side.detected && !side.guess ? div({ className: 'rc-note warn' }, 'لم أتعرف على رؤوس الأعمدة تلقائياً. حدّدها يدوياً.') : null,
    /* two choices shown in full (a select clips the long wording on phones) */
    h('fieldset', { className: 'persp' },
      h('legend', null, 'اتجاه الكشف'),
      ['supplier', 'company'].map(function (v) {
        return label({ key: v, className: 'radiocard' + (side.persp === v ? ' on' : '') },
          input({ type: 'radio', name: 'rc-persp-' + k, id: 'rc-persp-' + k + '-' + v, value: v, checked: side.persp === v, onChange: function () { props.onPatch({ persp: v }); } }),
          span(null, RC_PERSP[v]));
      })),
    ready ? h('details', { className: 'rc-det', open: !side.detected || !(led && led.lines.length) },
      h('summary', null, 'الأعمدة ومعاينة البنود المقروءة'),
      side.diag ? div({ className: 'rc-note' }, 'الورقة: ' + side.diag.sheet + ' · أوراق الملف: ' + side.diag.sheets + ' · معادلات: ' + side.diag.formulas + (side.diag.emptyFormulas ? ' (بلا قيمة محفوظة: ' + side.diag.emptyFormulas + ')' : '')) : null,
      div({ className: 'tfield' }, label({ htmlFor: 'rc-hr-' + k }, 'صف العناوين'),
        select({ id: 'rc-hr-' + k, value: String(side.guess ? -1 : side.headerIdx), onChange: function (e) { props.onHeader(+e.target.value); } },
          option({ value: '-1' }, 'بلا عناوين (تحديد تلقائي من البيانات)'),
          side.rows.slice(0, 60).map(function (r, i) { return [r, i]; }).filter(function (x) { return x[0].some(function (c) { return String(c == null ? '' : c).trim(); }); }).slice(0, 25).map(function (x) {
            return option({ key: x[1], value: String(x[1]) }, 'الصف ' + (x[1] + 1) + ': ' + x[0].filter(function (c) { return String(c == null ? '' : c).trim(); }).slice(0, 4).join(' | ').slice(0, 50));
          }))),
      div({ className: 'rc-map' }, RC_FIELD_LABEL.map(function (f) {
        return div({ key: f[0], className: 'tfield' }, label({ htmlFor: 'rc-m-' + k + f[0] }, f[1]),
          select({ id: 'rc-m-' + k + f[0], value: side.map[f[0]] == null ? '' : String(side.map[f[0]]), onChange: function (e) {
            const m = Object.assign({}, side.map);
            if (e.target.value === '') delete m[f[0]]; else m[f[0]] = +e.target.value;
            props.onPatch({ map: m });
          } }, option({ value: '' }, 'غير موجود'), names.map(function (n, i) { return option({ key: i, value: String(i) }, n); })));
      })),
      !(led && led.lines.length) ? div({ className: 'tablewrap rc-raw' }, table({ className: 'dt' }, tbody(null,
        side.rows.filter(function (r) { return (r || []).some(function (c) { return String(c == null ? '' : c).trim(); }); }).slice(0, 12).map(function (r, i) {
          return tr({ key: i }, (r || []).slice(0, 8).map(function (c, j) { return td({ key: j }, c instanceof Date ? fmtDate(c) : String(c == null ? '' : c).slice(0, 40)); }));
        })))) : null,
      led && led.lines.length ? h(DataTable, { cols: RC_LINE_COLS, exportName: 'بنود-الكشف', rows: led.lines.map(function (l) { return Object.assign({ id: 'L' + l.n }, l); }) }) : null) : null,
    div({ className: 'rc-paste' },
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { setPasteOpen(!pasteOpen); } }, pasteOpen ? 'إخفاء اللصق' : 'أو الصق الجدول يدوياً'),
      pasteOpen ? div({ className: 'stack' },
        textarea({ rows: 5, className: 'rc-ta', placeholder: 'الصق صفوف الجدول هنا (من Excel أو Word) مع صف العناوين', value: pasteText, 'aria-label': 'لصق الجدول', onChange: function (e) { setPasteText(e.target.value); } }),
        button({ type: 'button', className: 'btn primary sm', disabled: !pasteText.trim(), onClick: function () { props.onRows(rcSplitText(pasteText.split('\n')), 'paste', 'نص ملصوق'); setPasteOpen(false); } }, 'اعتماد النص')) : null));
}

function RcResult(props) {
  const res = props.res;
  const [showMatched, setShowMatched] = useState(false);
  const [tab, setTab] = useState('diag');
  const rows = res.items.filter(function (i) { return i.status !== 'matched' && i.status !== 'cancelled'; });
  const matched = res.items.filter(function (i) { return i.status === 'matched'; });
  /* same amount and date window but no shared document number: counted as agreed, and shown separately */
  const byAmount = res.items.filter(function (i) { return i.status === 'matched_amount'; });
  const agreedItems = matched.concat(byAmount);
  const [dl, setDl] = useState(null);
  useEffect(function () {
    let live = true;
    try {
      if (window.claude && window.claude.use) window.claude.use('downloads').then(function (d) { if (live) setDl(d || null); }, function () { /* no downloads here */ });
    } catch (e) { /* ignore */ }
    return function () { live = false; };
  }, []);
  const exportCsv = function () {
    if (!dl) return;
    dl.save({ filename: 'مطابقة-الكشوف.csv', data: rcCsv(res) }).then(function () { props.onToast('تم حفظ ملف المطابقة.'); },
      function (e) { if (!e || e.code !== 'declined') props.onToast('تعذّر حفظ الملف.'); });
  };
  /* settlement statement, in the order an accountant reads it:
     1. opening entry on both sides, 2. the balance both statements agree on,
     3. what is added and deducted so that our balance becomes the balance on the supplier's statement */
  const sum = function (list, f) { return list.reduce(function (t, x) { return t + f(x); }, 0); };
  const opening = res.items.filter(function (i) { return i.kind === 'opening'; });
  const openA = sum(opening, function (i) { return i.amtA || 0; }), openB = sum(opening, function (i) { return i.amtB || 0; });
  const agreed = sum(agreedItems, function (i) { return i.amtB || 0; });
  const toYours = res.lines.map(function (l) { return Object.assign({}, l, { effect: -l.effect }); });
  const adds = toYours.filter(function (l) { return l.effect > 0; }), cuts = toYours.filter(function (l) { return l.effect < 0; });
  const addTotal = sum(adds, function (l) { return l.effect; }), cutTotal = -sum(cuts, function (l) { return l.effect; });
  const addN = sum(adds, function (l) { return l.count; }), cutN = sum(cuts, function (l) { return l.count; });
  const finalBal = res.sumB + addTotal - cutTotal;
  const gap = finalBal - res.sumA;
  const pct = res.items.length ? Math.round(agreedItems.length / res.items.length * 100) : 0;
  const fm = function (v) { return Math.abs(v) < 0.005 ? '0.00' : (v < 0 ? '(' + rcMoney(-v) + ')' : rcMoney(v)); };
  const amt = function (v, cls) { return td({ className: 'num' }, span({ className: 'mono' + (cls ? ' ' + cls : '') }, fm(v))); };
  const head = function (n, t) { return tr({ className: 'sec' }, td({ colSpan: 3 }, span({ className: 'stepno' }, n), t)); };
  const row = function (label, n, v, cls, key) { return tr({ key: key, className: cls }, td(null, label), td({ className: 'cnt' }, n == null ? '' : n), amt(v)); };
  const group = function (title, list, total, count, key, neg) {
    if (!list.length) return null;
    return tr({ key: key, className: 'strong grp' }, td(null, title), td({ className: 'cnt' }, count), amt(neg ? -total : total));
  };
  const stmt = div({ className: 'tablewrap stmt' }, table({ className: 'dt' },
    thead(null, tr(null, th({ scope: 'col' }, 'البيان'), th({ scope: 'col', className: 'cnt' }, 'البنود'), th({ scope: 'col', className: 'num' }, 'المبلغ'))),
    tbody(null,
      head('1', 'القيد الافتتاحي'),
      row('الرصيد الافتتاحي حسب دفاترنا', null, openB, '', 'ob'),
      row('الرصيد الافتتاحي حسب كشفك', null, openA, '', 'oa'),
      tr({ key: 'od', className: 'strong' }, td(null, 'فرق القيد الافتتاحي'), td({ className: 'cnt' }), td({ className: 'num' }, span({ className: 'mono rc-diff' + (Math.abs(openA - openB) > 0.5 ? ' off' : '') }, Math.abs(openA - openB) < 0.005 ? 'متطابق' : fm(openA - openB)))),
      head('2', 'الرصيد المطابق'),
      row('رصيد البنود المتطابقة في الكشفين', agreedItems.length, agreed, 'strong', 'ag'),
      byAmount.length ? tr({ key: 'agn' }, td({ colSpan: 3, className: 'rc-sub' }, 'منها ' + matched.length + ' بند برقم المستند و' + byAmount.length + ' بند بالمبلغ والتاريخ فقط (يُراجع رقم المستند في تبويب التفاصيل)')) : null,
      row('بنود حسب دفاترنا لم تتطابق مع كشفك', res.items.length - agreedItems.length, res.sumB - agreed, '', 'ou'),
      row('الرصيد حسب دفاترنا', null, res.sumB, 'strong total', 'sb'),
      head('3', 'بنود التسوية'),
      group('يُضاف: بنود عند المورد أو فروق لصالحه', adds, addTotal, addN, 'add', false),
      group('يُطرح: بنود عندنا لم تصل المورد أو فروق لصالحنا', cuts, cutTotal, cutN, 'cut', true),
      !toYours.length ? tr({ key: 'none' }, td({ colSpan: 3, className: 'muted' }, 'لا توجد بنود تسوية. الكشفان متطابقان.')) : null,
      row('الرصيد بعد التسوية', null, finalBal, 'strong total', 'fb'),
      row('الرصيد حسب كشفك', null, res.sumA, 'strong', 'sa'),
      tr({ key: 'gap', className: 'strong' }, td(null, 'فرق غير مفسَّر'), td({ className: 'cnt' }), td({ className: 'num' }, span({ className: 'mono rc-diff' + (Math.abs(gap) > 0.5 ? ' off' : '') }, fm(Math.abs(gap) < 0.005 ? 0 : gap)))))));
  const ref = 'RC-' + res.at.getFullYear() + String(res.at.getMonth() + 1).padStart(2, '0') + String(res.at.getDate()).padStart(2, '0') + '-' + String(res.at.getHours()).padStart(2, '0') + String(res.at.getMinutes()).padStart(2, '0');
  const states = Object.keys(RC_STATUS).map(function (k) { const list = res.items.filter(function (i) { return i.status === k; }); return { k: k, label: RC_STATUS[k].label, n: list.length, diff: sum(list, function (i) { return i.diff; }) }; }).filter(function (x) { return x.n > 0; });
  const balanced = Math.abs(res.diff) < 0.005;
  const doc = div({ className: 'rc-doc' },
    div({ className: 'rc-letter' },
      div({ className: 'rc-org' }, strong(null, 'أسواق الرشيد'), span(null, 'الإدارة المالية · قسم المطابقة')),
      div({ className: 'rc-ref' }, div(null, span(null, 'رقم المرجع'), strong({ className: 'mono' }, ref)), div(null, span(null, 'التاريخ'), strong(null, fmtDate(res.at))))),
    div({ className: 'rc-title' }, h2(null, 'بيان مطابقة كشف حساب مورد'), p(null, 'مطابقة أرصدة وحركات كشف المورد مع قيود دفاتر الشركة')),
    div({ className: 'rc-meta' },
      div(null, span(null, 'كشف المورد'), strong(null, rcName(res.nameA))),
      div(null, span(null, 'كشف دفاترنا'), strong(null, rcName(res.nameB))),
      div(null, span(null, 'عدد البنود المفحوصة'), strong(null, String(res.items.length))),
      div(null, span(null, 'نسبة المطابقة'), strong(null, pct + '% (' + agreedItems.length + ' بند متطابق)'))),
    div({ className: 'rc-sum' },
      div(null, span(null, 'رصيد كشف المورد'), strong({ className: 'mono' }, fm(res.sumA))),
      div(null, span(null, 'رصيد دفاترنا'), strong({ className: 'mono' }, fm(res.sumB))),
      div(null, span(null, 'الفرق بين الرصيدين'), strong({ className: 'mono rc-diff' + (balanced ? '' : ' off') }, balanced ? 'لا يوجد فرق' : fm(res.diff))),
      div(null, span(null, 'بنود تحتاج معالجة'), strong(null, String(res.items.length - agreedItems.length)))),
    h3({ className: 'rc-h' }, 'أولاً: بيان التسوية'),
    stmt,
    states.length ? [
      h3({ key: 'h', className: 'rc-h' }, 'ثانياً: ملخص حالات البنود'),
      div({ key: 't', className: 'tablewrap stmt' }, table({ className: 'dt' },
        thead(null, tr(null, th({ scope: 'col' }, 'الحالة'), th({ scope: 'col', className: 'cnt' }, 'البنود'), th({ scope: 'col', className: 'num' }, 'إجمالي الفرق'))),
        tbody(null, states.map(function (x) { return tr({ key: x.k }, td(null, x.label), td({ className: 'cnt' }, x.n), amt(x.diff)); }))))] : null,
    h3({ className: 'rc-h' }, 'ملاحظات'),
    p({ className: 'rc-note-text' }, 'أُعدّ هذا البيان آلياً من كشفي الحساب المرفوعين، ويُعتمد بعد مراجعة المختص. تفاصيل كل بند في تبويب «التفاصيل». الأرقام السالبة بين أقواس.'),
    div({ className: 'rc-sign' },
      ['أعدّه' + (props.by ? ': ' + props.by : ''), 'راجعه', 'اعتمده (المدير المالي)'].map(function (t) { return div({ key: t }, span(null, t), i0()); })));
  return div({ className: 'stack rc-result' },
    div({ className: 'sechead noprint' }, h2(null, 'نتيجة المطابقة'), div({ className: 'rc-acts' },
      dl ? button({ type: 'button', className: 'btn ghost sm', onClick: exportCsv }, h(Icon, { name: 'download', size: 16 }), 'تصدير CSV') : null,
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { try { window.print(); } catch (e) { props.onToast('الطباعة غير متاحة هنا.'); } } }, h(Icon, { name: 'print', size: 16 }), 'طباعة / PDF'))),
    div({ className: 'rc-tabs noprint', role: 'tablist', 'aria-label': 'عرض النتيجة' },
      button({ type: 'button', role: 'tab', 'aria-selected': tab === 'diag', onClick: function () { setTab('diag'); } }, 'نتيجة المطابقة'),
      button({ type: 'button', role: 'tab', 'aria-selected': tab === 'report', onClick: function () { setTab('report'); } }, 'تقرير المطابقة'),
      button({ type: 'button', role: 'tab', 'aria-selected': tab === 'letter', onClick: function () { setTab('letter'); } }, 'خطاب المطابقة'),
      button({ type: 'button', role: 'tab', 'aria-selected': tab === 'sheet', onClick: function () { setTab('sheet'); } }, 'التفاصيل', span({ className: 'rc-tabn' }, res.items.length))),
    (Math.abs(res.sumA) > 1e11 || Math.abs(res.sumB) > 1e11 || (res.items.length > 30 && !agreedItems.length)) ? div({ className: 'rc-warn noprint', role: 'alert' }, 'تحذير: النتيجة غير منطقية (أرصدة ضخمة أو لا يوجد بند متطابق). غالباً قُرئت أعمدة الملف خطأ. افتح «الأعمدة ومعاينة البنود المقروءة» لكل كشف وصحّح اختيار الأعمدة قبل الاعتماد.') : null,
    tab === 'diag' ? h(RcDiagnosis, { res: res }) : tab === 'letter' ? h(RcLetter, { res: res, by: props.by, onToast: props.onToast }) : tab === 'report' ? doc : h(RcSheet, { items: res.items, onToast: props.onToast }),
    (tab === 'report' || tab === 'sheet') && rows.length ? div({ className: 'printonly rc-annex' },
      div({ className: 'rc-annex-head' }, h3(null, 'ملحق: البنود التي تحتاج إلى معالجة (' + rows.length + ')'), span(null, 'المرجع ' + ref + ' · ' + fmtDate(res.at))),
      table(null,
        h('colgroup', null, [4, 17, 15, 9, 12, 12, 11, 20].map(function (w, k) { return h('col', { key: k, style: { width: w + '%' } }); })),
        thead(null, tr(null, ['#', 'الحالة والنوع', 'المستند', 'التاريخ', 'عند المورد', 'عندنا', 'الفرق', 'السبب'].map(function (x, k) { return th({ key: x, className: k >= 4 && k <= 6 ? 'n' : '' }, x); }))),
        tbody(null, rows.map(function (r, k) {
          const doc1 = rcPickDoc(r.docA, r.docB) || rcPickDoc(r.docB, r.docA) || r.doc || '';
          return tr({ key: r.id },
            td({ className: 'c' }, k + 1), td(null, strong(null, RC_STATUS[r.status].label), h('br'), span({ className: 'sub' }, RC_KIND[r.kind])), td({ className: 'mono' }, doc1), td({ className: 'c' }, r.date ? fmtDate(r.date) : ''),
            td({ className: 'n' }, rcMoney(r.amtA)), td({ className: 'n' }, rcMoney(r.amtB)), td({ className: 'n' }, Math.abs(r.diff) < 0.005 ? '' : rcSigned(r.diff)), td({ className: 'why' }, r.reason || ''));
        })),
        tfoot(null, tr(null, td({ colSpan: 4 }, 'الإجمالي'),
          td({ className: 'n' }, rcMoney(rows.reduce(function (t, r) { return t + (r.amtA || 0); }, 0))), td({ className: 'n' }, rcMoney(rows.reduce(function (t, r) { return t + (r.amtB || 0); }, 0))),
          td({ className: 'n' }, rcSigned(rows.reduce(function (t, r) { return t + (r.diff || 0); }, 0))), td(null, ''))))) : null);
}
const i0 = function () { return div({ className: 'rc-line' }); };

const tfoot = function (props) { return h.apply(null, ['tfoot', props].concat([].slice.call(arguments, 1))); };
/* each document number on its own chip; a number that both sides share (the one the match relied on) is highlighted */
const rcSameDoc = function (a, b) { return a === b || (a.length >= 10 && b.length >= 10 && a.slice(0, 10) === b.slice(0, 10)); };
const rcRev = function (t) { return t.split('').reverse().join(''); };
/* one number per transaction: the one both statements share, otherwise the longest (the invoice number); the rest stay in the tooltip */
function docChips(mine, other) {
  const toks = String(mine || '').split(/\s+/).filter(Boolean);
  if (!toks.length) return null;
  const theirs = String(other || '').split(/\s+/).filter(Boolean);
  let shown = null, hit = false;
  toks.forEach(function (t) {
    theirs.forEach(function (u) {
      if (hit) return;
      if (rcSameDoc(t, u)) { shown = t; hit = true; }
      else if (t.length >= 10 && rcSameDoc(rcRev(t), u)) { shown = rcRev(t); hit = true; }
    });
  });
  if (!shown) shown = toks.slice().sort(function (a, b) { return b.length - a.length; })[0];
  return span({ className: 'dchip' + (hit ? ' hit' : ''), title: (hit ? 'رقم مشترك بين الكشفين · ' : '') + 'كل الأرقام: ' + toks.join(' / ') }, shown);
}

/* the one number printed for a document: the number both statements share, otherwise the longest */
function rcPickDoc(mine, other) {
  const toks = String(mine || '').split(/\s+/).filter(Boolean);
  if (!toks.length) return '';
  const theirs = String(other || '').split(/\s+/).filter(Boolean);
  for (let a = 0; a < toks.length; a++) for (let b = 0; b < theirs.length; b++) {
    if (rcSameDoc(toks[a], theirs[b])) return toks[a];
    if (toks[a].length >= 10 && rcSameDoc(rcRev(toks[a]), theirs[b])) return rcRev(toks[a]);
  }
  return toks.slice().sort(function (x, y) { return y.length - x.length; })[0];
}

/* the details tab: every item in a spreadsheet-style grid */
function RcSheet(props) {
  const [q, setQ] = useState('');
  const [st, setSt] = useState('');
  const [lim, setLim] = useState(200);
  const needle = q.trim().toLowerCase();
  const list = props.items.filter(function (i) {
    if (st && i.status !== st) return false;
    return !needle || [i.docA, i.docB, i.descA, i.descB, i.reason, RC_KIND[i.kind]].join(' ').toLowerCase().indexOf(needle) !== -1;
  });
  const shown = list.slice(0, lim);
  const tot = function (f) { return list.reduce(function (t, x) { return t + (f(x) || 0); }, 0); };
  const num = function (v) { return td({ className: 'n' }, v == null ? '' : span({ className: 'mono' }, rcMoney(v))); };
  const HEAD = ['#', 'الحالة', 'النوع', 'مستند المورد', 'مستند نظامنا', 'التاريخ', 'عند المورد', 'عندنا', 'الفرق الحقيقي (المبلغ)', 'فرق التاريخ (يوم)', 'السبب والإجراء المقترح'];
  return div({ className: 'rc-sheetbox' },
    div({ className: 'rc-sheetbar' },
      div({ className: 'usearch' }, h(Icon, { name: 'search' }), input({ type: 'search', value: q, placeholder: 'بحث برقم المستند أو البيان أو السبب', 'aria-label': 'بحث في البنود', onChange: function (e) { setQ(e.target.value); setLim(200); } })),
      select({ 'aria-label': 'تصفية حسب الحالة', value: st, onChange: function (e) { setSt(e.target.value); setLim(200); } },
        option({ value: '' }, 'كل الحالات (' + props.items.length + ')'),
        Object.keys(RC_STATUS).map(function (k) { const n = props.items.filter(function (i) { return i.status === k; }).length; return n ? option({ key: k, value: k }, RC_STATUS[k].label + ' (' + n + ')') : null; })),
      span({ className: 'muted small' }, list.length + ' صف')),
    div({ className: 'rc-grid' }, table(null,
      thead(null, tr(null, HEAD.map(function (t, i) { return th({ key: i, scope: 'col', className: i >= 6 && i <= 9 ? 'n' : (i === 0 ? 'rn' : '') }, t); }))),
      tbody(null, shown.length ? shown.map(function (r, i) {
        return tr({ key: r.id, className: 's-' + r.status },
          td({ className: 'rn' }, i + 1),
          td({ className: 'st t-' + RC_STATUS[r.status].tone }, RC_STATUS[r.status].label),
          td(null, RC_KIND[r.kind]),
          td({ className: 'docs' }, docChips(r.docA, r.docB)), td({ className: 'docs' }, docChips(r.docB, r.docA)),
          td({ className: 'c' }, r.date ? fmtDate(r.date) : ''),
          num(r.amtA), num(r.amtB),
          td({ className: 'n' }, span({ className: 'mono rc-diff' + (Math.abs(r.diff) > 0.005 ? ' off' : '') }, Math.abs(r.diff) < 0.005 ? '' : rcSigned(r.diff))),
          td({ className: 'n' }, dayGap(r)),
          td({ className: 'why' }, r.reason || ''));
      }) : tr(null, td({ colSpan: HEAD.length, className: 'empty' }, 'لا توجد بنود مطابقة للتصفية'))),
      tfoot(null, tr(null, td({ colSpan: 6, className: 'tot' }, 'الإجمالي (' + list.length + ' صف)'), num(tot(function (x) { return x.amtA; })), num(tot(function (x) { return x.amtB; })), num(tot(function (x) { return x.diff; })), td(null), td(null))))),
    list.length > lim ? div({ className: 'rc-more' }, button({ type: 'button', className: 'btn ghost sm', onClick: function () { setLim(lim + 300); } }, 'عرض المزيد (' + (list.length - lim) + ' صف متبقٍ)')) : null);
}

/* days between the same movement on the two statements: + means our date is later than theirs */
function dayGap(r) {
  if (!r.dateA || !r.dateB) return '';
  const d = Math.round((r.dateA - r.dateB) / DAY);
  if (d === 0) return span({ className: 'muted' }, '0');
  return span({ className: 'mono rc-diff off' }, (d > 0 ? '+' : '') + d);
}

function ReconTool(props) {
  const [sides, setSides] = useState({ A: rcEmptySide('supplier'), B: rcEmptySide('company') });
  const [opts, setOpts] = useState({ tol: 0.25, days: 15 });
  const [res, setRes] = useState(null);
  const setHeader = function (k, idx) {
    const side = sides[k];
    if (idx < 0) {
      const g = rcGuessLayout(side.rows);
      patch(k, { headerIdx: g ? g.idx : -1, map: g ? rcGuessMap(g, side.persp) : {}, guess: g, detected: false });
    } else {
      const f = rcRowFields(side.rows[idx]);
      patch(k, { headerIdx: idx, map: f.map, guess: null, detected: f.hits >= 2 });
    }
  };
  const patch = function (k, o) { setSides(function (s) { const n = Object.assign({}, s); n[k] = Object.assign({}, s[k], o); return n; }); setRes(null); };
  function ingest(k, rows, source, note, name, diag) {
    let lay = rcAutoLayout(rows, sides[k].persp);
    let persp = sides[k].persp;
    if (lay && lay.map && (lay.map.debit != null || lay.map.credit != null)) {
      persp = rcDetectPersp(rows, lay.idx, lay.map);
      if (lay.guess) lay = Object.assign({}, lay, { map: rcGuessMap(lay.guess, persp) });
    }
    const gnote = lay && lay.guess ? 'لم تظهر رؤوس أعمدة واضحة، فحُدّدت الأعمدة من شكل البيانات. راجعها من الأسفل.' : (lay && lay.derived ? 'عمودا مدين ودائن فارغان أو أصفار في الملف، فاستُخرجت الحركات من فروق عمود الرصيد.' : (lay && lay.repaired ? 'صُحّح اختيار عمودي مدين ودائن بمطابقتهما مع حركة الرصيد.' : ''));
    patch(k, { status: 'ready', name: name, source: source, note: [note, gnote].filter(Boolean).join(' · '), rows: rows, persp: persp, headerIdx: lay ? lay.idx : 0, map: lay ? lay.map : {}, guess: lay ? lay.guess : null, detected: !!lay && !lay.guess, diag: diag || null, err: '' });
  }
  function load(k, file) {
    patch(k, { status: 'reading', name: file.name, err: '', note: 'جارٍ القراءة…' });
    rcReadFile(file, function (t) { patch(k, { status: 'reading', name: file.name, note: t }); })
      .then(function (r) { ingest(k, r.rows, r.source, r.note, file.name, r.diag); })
      .catch(function (e) { patch(k, { status: 'error', err: (e && e.message) || 'تعذّرت القراءة.' }); });
  }
  const ledA = React.useMemo(function () { return sides.A.status === 'ready' ? rcBuildLedger(sides.A.rows, sides.A.headerIdx, sides.A.map, sides.A.persp) : null; }, [sides.A]);
  const ledB = React.useMemo(function () { return sides.B.status === 'ready' ? rcBuildLedger(sides.B.rows, sides.B.headerIdx, sides.B.map, sides.B.persp) : null; }, [sides.B]);
  const canRun = ledA && ledB && ledA.lines.length && ledB.lines.length;
  function run() {
    const swap = sides.A.persp === 'company' && sides.B.persp === 'supplier';
    const r = rcReconcile(swap ? ledB : ledA, swap ? ledA : ledB, { tol: Math.max(0, +opts.tol || 0), days: Math.max(0, +opts.days || 0) });
    setRes(Object.assign(r, { at: new Date(), swapped: swap, nameA: swap ? sides.B.name : sides.A.name, nameB: swap ? sides.A.name : sides.B.name }));
  }
  function sample() {
    const s = rcSampleRows();
    ingest('A', s.supplier, 'sample', 'بيانات تجريبية: كشف مورد من جهته', 'كشف-المورد-سبتمبر-2026.xlsx');
    ingest('B', s.company, 'sample', 'بيانات تجريبية: كشف من نظامنا', 'كشف-نظامنا-سبتمبر-2026.xlsx');
    setSides(function (st) { return { A: Object.assign({}, st.A, { persp: 'supplier' }), B: Object.assign({}, st.B, { persp: 'company' }) }; });
  }
  function clear(k) { setSides(function (s) { const n = Object.assign({}, s); n[k] = rcEmptySide(k === 'A' ? 'supplier' : 'company'); return n; }); setRes(null); }
  return div({ className: 'stack recon' },
    div({ className: 'sechead noprint' }, h2(null, 'مطابقة الكشوف'), span({ className: 'pill idle' }, span({ className: 'dot' }), 'أداة داخلية · لا تظهر للمورد')),
    p({ className: 'muted noprint' }, 'ارفع كشف المورد وكشف نظامنا بأي صيغة (Excel أو CSV أو Word أو PDF أو صورة). تُقرأ البنود وتُطابق تلقائياً، ثم يظهر بيان التسوية والفروقات بالتفصيل.'),
    div({ className: 'rc-sides noprint' },
      h(RcSide, { k: 'A', title: '1 · كشف المورد', side: sides.A, ledger: ledA, onFile: function (f) { load('A', f); }, onRows: function (rows, src, note) { ingest('A', rows, src, note, 'نص ملصوق'); }, onPatch: function (o) { patch('A', o.persp && sides.A.guess ? Object.assign({}, o, { map: rcGuessMap(sides.A.guess, o.persp) }) : o); }, onHeader: function (i) { setHeader('A', i); }, onClear: function () { clear('A'); } }),
      h(RcSide, { k: 'B', title: '2 · كشف نظامنا', side: sides.B, ledger: ledB, onFile: function (f) { load('B', f); }, onRows: function (rows, src, note) { ingest('B', rows, src, note, 'نص ملصوق'); }, onPatch: function (o) { patch('B', o.persp && sides.B.guess ? Object.assign({}, o, { map: rcGuessMap(sides.B.guess, o.persp) }) : o); }, onHeader: function (i) { setHeader('B', i); }, onClear: function () { clear('B'); } })),
    div({ className: 'rc-bar noprint' },
      div({ className: 'tfield' }, label({ htmlFor: 'rc-tol' }, 'هامش فرق التقريب المقبول (ر.س)'),
        input({ id: 'rc-tol', type: 'number', min: 0, step: '0.01', value: opts.tol, onChange: function (e) { setOpts(Object.assign({}, opts, { tol: e.target.value })); setRes(null); } })),
      div({ className: 'tfield' }, label({ htmlFor: 'rc-days' }, 'نافذة التاريخ للمطابقة بالمبلغ (أيام)'),
        input({ id: 'rc-days', type: 'number', min: 0, step: '1', value: opts.days, onChange: function (e) { setOpts(Object.assign({}, opts, { days: e.target.value })); setRes(null); } })),
      div({ className: 'rc-bar-acts' },
        button({ type: 'button', className: 'btn primary', disabled: !canRun, onClick: run }, 'بدء المطابقة'),
        button({ type: 'button', className: 'btn ghost', onClick: sample }, 'تحميل بيانات تجريبية'))),
    res ? h(RcResult, { res: res, onToast: props.onToast, by: props.by }) : null);
}
