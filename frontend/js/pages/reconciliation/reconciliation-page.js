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
    div({ className: 'rc-sidehead' }, h3(null, props.title), ready ? button({ type: 'button', className: 'btn ghost sm', onClick: props.onClear }, 'إزالة') : null),
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
    div({ className: 'tfield' },
      label({ htmlFor: 'rc-persp-' + k }, 'اتجاه الكشف'),
      select({ id: 'rc-persp-' + k, value: side.persp, onChange: function (e) { props.onPatch({ persp: e.target.value }); } },
        option({ value: 'supplier' }, RC_PERSP.supplier), option({ value: 'company' }, RC_PERSP.company))),
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
      led && led.lines.length ? h(DataTable, { cols: RC_LINE_COLS, rows: led.lines.map(function (l) { return Object.assign({ id: 'L' + l.n }, l); }) }) : null) : null,
    div({ className: 'rc-paste' },
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { setPasteOpen(!pasteOpen); } }, pasteOpen ? 'إخفاء اللصق' : 'أو الصق الجدول يدوياً'),
      pasteOpen ? div({ className: 'stack' },
        textarea({ rows: 5, className: 'rc-ta', placeholder: 'الصق صفوف الجدول هنا (من Excel أو Word) مع صف العناوين', value: pasteText, 'aria-label': 'لصق الجدول', onChange: function (e) { setPasteText(e.target.value); } }),
        button({ type: 'button', className: 'btn primary sm', disabled: !pasteText.trim(), onClick: function () { props.onRows(rcSplitText(pasteText.split('\n')), 'paste', 'نص ملصوق'); setPasteOpen(false); } }, 'اعتماد النص')) : null));
}

function RcResult(props) {
  const res = props.res;
  const [showMatched, setShowMatched] = useState(false);
  const rows = res.items.filter(function (i) { return i.status !== 'matched'; });
  const matched = res.items.filter(function (i) { return i.status === 'matched'; });
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
  const stmt = div({ className: 'tablewrap stmt' }, table({ className: 'dt' }, tbody(null,
    tr({ className: 'strong' }, td(null, 'رصيد حسب كشف المورد'), td({ className: 'num' }, span({ className: 'mono' }, rcMoney(res.sumA)))),
    res.lines.map(function (l) {
      return tr({ key: l.key }, td(null, l.label, span({ className: 'muted small' }, ' (' + l.count + ')')), td({ className: 'num' }, span({ className: 'mono' }, rcSigned(l.effect))));
    }),
    tr({ className: 'strong top' }, td(null, 'الرصيد بعد التسوية'), td({ className: 'num' }, span({ className: 'mono' }, rcMoney(res.adjusted)))),
    tr({ className: 'strong' }, td(null, 'رصيد حسب دفاترنا'), td({ className: 'num' }, span({ className: 'mono' }, rcMoney(res.sumB)))),
    tr({ className: 'strong' }, td(null, 'فرق غير مفسَّر'), td({ className: 'num' }, span({ className: 'mono rc-diff' + (Math.abs(res.unexplained) > 0.5 ? ' off' : '') }, rcMoney(Math.abs(res.unexplained) < 0.005 ? 0 : res.unexplained)))))));
  return div({ className: 'stack rc-result' },
    div({ className: 'sechead' }, h2(null, 'نتيجة المطابقة'), div({ className: 'rc-acts noprint' },
      dl ? button({ type: 'button', className: 'btn ghost sm', onClick: exportCsv }, h(Icon, { name: 'download', size: 16 }), 'تصدير CSV') : null,
      button({ type: 'button', className: 'btn ghost sm', onClick: function () { try { window.print(); } catch (e) { props.onToast('الطباعة غير متاحة هنا.'); } } }, h(Icon, { name: 'print', size: 16 }), 'طباعة / PDF'))),
    div({ className: 'printonly rc-printhead' }, 'تقرير مطابقة كشف حساب مورد · ' + fmtDate(res.at) + ' · ' + rcName(res.nameA) + ' مقابل ' + rcName(res.nameB)),
    div({ className: 'kpis' },
      h(Kpi, { label: 'رصيد كشف المورد', value: rcMoney(res.sumA), note: rcName(res.nameA) }),
      h(Kpi, { label: 'رصيد دفاترنا', value: rcMoney(res.sumB), note: rcName(res.nameB) }),
      h(Kpi, { label: 'الفرق بين الكشفين', value: rcSigned(res.diff), note: res.diff > 0 ? 'المورد يطالب بأكثر مما نسجّله' : res.diff < 0 ? 'نسجّل أكثر مما يطالب به المورد' : 'الكشفان متطابقان', tone: Math.abs(res.diff) > 0.005 ? 'bad' : '' }),
      h(Kpi, { label: 'بنود تحتاج معالجة', value: res.open, note: matched.length + ' بند مطابق تماماً' })),
    div({ className: 'sechead' }, h3(null, 'بيان التسوية')),
    stmt,
    div({ className: 'sechead noprint' }, h3(null, 'البنود المختلفة (' + rows.length + ')')),
    rows.length ? div({ className: 'noprint' }, h(DataTable, { cols: RC_ITEM_COLS, rows: rows })) : div({ className: 'panel' }, 'لا توجد فروقات. الكشفان متطابقان بنداً بنداً.'),
    matched.length ? div({ className: 'noprint stack' },
      button({ type: 'button', className: 'btn ghost', 'aria-expanded': showMatched, onClick: function () { setShowMatched(!showMatched); } }, showMatched ? 'إخفاء البنود المطابقة' : 'عرض البنود المطابقة (' + matched.length + ')'),
      showMatched ? h(DataTable, { cols: RC_ITEM_COLS, rows: matched }) : null) : null,
    div({ className: 'printonly' }, table({ className: 'dt' }, thead(null, tr(null, ['الحالة', 'النوع', 'المستند', 'التاريخ', 'عند المورد', 'عندنا', 'الفرق', 'السبب'].map(function (x) { return th({ key: x }, x); }))),
      tbody(null, rows.map(function (r) {
        return tr({ key: r.id }, td(null, RC_STATUS[r.status].label), td(null, RC_KIND[r.kind]), td(null, r.docA && r.docB && r.docA !== r.docB ? r.docA + ' / ' + r.docB : r.doc), td(null, r.date ? fmtDate(r.date) : ''),
          td(null, rcMoney(r.amtA)), td(null, rcMoney(r.amtB)), td(null, rcSigned(r.diff)), td(null, r.reason));
      })))));
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
    res ? h(RcResult, { res: res, onToast: props.onToast }) : null);
}
