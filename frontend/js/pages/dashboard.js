'use strict';

/* ---------- finance manager dashboard ---------- */
function Kpi(props) {
  return div({ className: 'kpi' + (props.tone ? ' ' + props.tone : '') },
    span({ className: 'k' }, props.label), span({ className: 'v' }, props.value), span({ className: 'n' }, props.note));
}

const FILTERS = [['all', 'الكل'], ['late', 'متأخرة'], ['reply', 'تنتظر رد المورد'], ['matching', 'قيد المطابقة'], ['queue', 'بانتظار التوزيع'], ['done', 'منجزة'], ['complaints', 'الشكاوى']];

const isComplaint = function (r) { return String(r.id).indexOf('SH') === 0; };

/* one table for both manager services: matching requests and complaints */
function UnifiedTable(props) {
  const role = 'manager';
  const kindOf = function (r) { return isComplaint(r) ? 'شكوى' : 'طلب مطابقة'; };
  const stOf = function (r) { return isComplaint(r) ? statusC(r, role) : statusOf(r, role); };
  const defs = [
    { key: 'id', label: 'الرقم', filter: 'text', val: function (r) { return r.id; }, render: function (r) { return span({ className: 'mono' }, r.id); } },
    { key: 'kind', label: 'النوع', filter: 'select', val: kindOf, render: function (r) { return span({ className: 'muted' }, kindOf(r)); } },
    { key: 'supplier', label: 'المورد', filter: 'text', val: function (r) { return r.supplier; }, render: function (r) { return strong({ style: { fontWeight: 600 } }, r.supplier); } },
    { key: 'subject', label: 'الموضوع / الفترة', filter: 'text', val: function (r) { return isComplaint(r) ? r.subject : r.period; }, render: function (r) { return isComplaint(r) ? r.subject : r.period; } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: function (r) { return stOf(r).label; }, val: function (r) { return r.stage; }, render: function (r) {
      return div({ className: 'cell-status' }, h(StatusPill, { st: stOf(r) }), !isComplaint(r) && isLate(r) ? h(LateChip) : null);
    } },
    { key: 'matcher', label: 'المطابق', filter: 'select', fv: function (r) { return isComplaint(r) ? '—' : (r.matcher || 'لم يُوزَّع بعد'); }, val: function (r) { return isComplaint(r) ? '' : (r.matcher || ''); }, render: function (r) { return isComplaint(r) ? span({ className: 'muted' }, '—') : (r.matcher || span({ className: 'muted' }, 'لم يُوزَّع بعد')); } },
    { key: 'due', label: 'الموعد المستهدف', val: function (r) { return isComplaint(r) ? 0 : r.due.getTime(); }, render: function (r) { return isComplaint(r) ? span({ className: 'muted' }, '—') : dueText(r); } },
    { key: 'updated', label: 'آخر تحديث', val: function (r) { return (isComplaint(r) ? r.created : lastTouch(r)).getTime(); }, render: function (r) { return since(isComplaint(r) ? r.created : lastTouch(r)); } },
    { key: 'msgs', label: 'المراسلات', val: chatCount, render: function (r) { return span({ className: 'msgcount' }, h(Icon, { name: 'chat', size: 15 }), chatCount(r), h(Badge, { n: unreadOf(r, role, props.seen) })); } },
    OPEN_COL
  ];
  return h(DataTable, { cols: defs, rows: props.rows, onOpen: props.onOpen, rowClass: function (r) { return unreadOf(r, role, props.seen) ? 'unread' : undefined; } });
}

function Dashboard(props) {
  const [flt, setFlt] = useState('all');
  const reqs = props.reqs;
  const keyOf = function (r) { return statusOf(r, 'manager').key; };
  const open = reqs.filter(function (r) { return r.stage < 4; });
  const late = open.filter(isLate);
  const doneAll = reqs.filter(function (r) { return r.stage === 4; });
  const doneMonth = doneAll.filter(function (r) { return r.reached[4].getMonth() === NOW.getMonth() && r.reached[4].getFullYear() === NOW.getFullYear(); });
  const avg = doneAll.length ? doneAll.reduce(function (s, r) { return s + (r.reached[4] - r.created) / DAY; }, 0) / doneAll.length : 0;
  const replyN = reqs.filter(function (r) { return keyOf(r) === 'reply'; }).length;
  const newC = props.complaints.filter(function (c) { return c.stage === 1; }).length;
  const unrC = unreadSum(props.complaints, 'manager', props.seen);
  const cRows = props.complaints.slice().sort(function (a, b) { return (a.stage === 3) - (b.stage === 3) || b.created - a.created; });

  const pipeline = [
    ['بانتظار التوزيع', 'idle', reqs.filter(function (r) { return r.stage === 1; }).length],
    ['قيد المطابقة', 'warn', reqs.filter(function (r) { return r.stage === 2; }).length],
    ['مراسلات واستيضاح', 'work', reqs.filter(function (r) { return r.stage === 3; }).length],
    ['منجز', 'ok', doneAll.length]
  ];
  const load = {};
  open.forEach(function (r) { const k = r.matcher || 'غير موزّع'; load[k] = (load[k] || 0) + 1; });
  const loadRows = Object.keys(load).map(function (k) { return [k, load[k]]; }).sort(function (a, b) { return b[1] - a[1]; });
  const maxLoad = loadRows.length ? loadRows[0][1] : 1;

  const counts = {
    all: reqs.length, late: late.length, reply: replyN,
    matching: reqs.filter(function (r) { return keyOf(r) === 'matching'; }).length,
    queue: reqs.filter(function (r) { return keyOf(r) === 'queue'; }).length, done: doneAll.length,
    complaints: props.complaints.length
  };
  const reqRows = flt === 'complaints' ? [] : reqs.filter(function (r) { return flt === 'all' ? true : flt === 'late' ? isLate(r) : keyOf(r) === flt; })
    .sort(function (a, b) { return (a.stage === 4) - (b.stage === 4) || a.due - b.due; });
  const rows = (flt === 'all' || flt === 'complaints' ? cRows : []).concat(reqRows);

  return div({ className: 'stack' },
    div({ className: 'sechead' }, h2(null, 'متابعة المطابقات'), span({ className: 'muted small' }, 'عرض للمراقبة، بدون تدخل في سير الطلبات')),
    newC ? div({ className: 'alertbar', role: 'status' }, h(Icon, { name: 'alert' }), newC === 1 ? 'وصلتك شكوى جديدة من مورد' : 'وصلتك ' + newC + ' شكاوى جديدة من الموردين') : null,
    h(AlertBar, { n: unrC, text: newMsgText(unrC, 'الموردين') }),
    div({ className: 'kpis' },
      h(Kpi, { label: 'طلبات مفتوحة', value: open.length, note: 'من أصل ' + reqs.length + ' طلب' }),
      h(Kpi, { label: 'متأخرة عن ' + SLA_DAYS + ' أيام', value: late.length, note: replyN + ' منها تنتظر رد المورد', tone: late.length ? 'bad' : '' }),
      h(Kpi, { label: 'منجزة هذا الشهر', value: doneMonth.length, note: 'طلبات أُغلقت بالاتفاق' }),
      h(Kpi, { label: 'متوسط مدة الإنجاز', value: avg.toFixed(1), note: 'يوم لكل طلب منجز' })),
    div({ className: 'two' },
      section({ className: 'panel' }, h3(null, 'أين تقف الطلبات الآن'),
        div({ className: 'strip', role: 'img', 'aria-label': pipeline.map(function (x) { return x[0] + ' ' + x[2]; }).join('، ') },
          pipeline.filter(function (x) { return x[2] > 0; }).map(function (x) { return div({ key: x[0], className: 'bg-' + x[1], style: { flexGrow: x[2], flexBasis: 0 } }); })),
        div({ className: 'legend' }, pipeline.map(function (x) { return div({ key: x[0] }, h('i', { className: 'bg-' + x[1] }), x[0], h('b', null, x[2])); }))),
      section({ className: 'panel' }, h3(null, 'الحمل على المطابقين'),
        ul({ className: 'load' }, loadRows.map(function (x) {
          return li({ key: x[0] }, span(null, x[0]), div({ className: 'track' }, h('i', { style: { width: (x[1] / maxLoad * 100) + '%' } })), h('b', null, x[1]));
        })))),
    div({ className: 'tools' },
      div({ className: 'filters', role: 'group', 'aria-label': 'تصفية الطلبات' }, FILTERS.map(function (f) {
        return button({ key: f[0], className: 'fchip', 'aria-pressed': flt === f[0], onClick: function () { setFlt(f[0]); } }, f[1], h('b', null, counts[f[0]]));
      })),
      null),
    h(UnifiedTable, { rows: rows, seen: props.seen, onOpen: function (id) { return isComplaint({ id: id }) ? props.onOpenC(id) : props.onOpen(id); } }));
}
