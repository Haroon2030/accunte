'use strict';

/* ---------- finance manager dashboard ---------- */
function Kpi(props) {
  return div({ className: 'kpi' + (props.tone ? ' ' + props.tone : '') },
    span({ className: 'k' }, props.label), span({ className: 'v' }, props.value), span({ className: 'n' }, props.note));
}

const FILTERS = [['all', 'الكل'], ['late', 'متأخرة'], ['reply', 'تنتظر رد المورد'], ['matching', 'قيد المطابقة'], ['queue', 'بانتظار التوزيع'], ['sending', 'بانتظار إرسال الملف'], ['done', 'منجزة'], ['complaints', 'الشكاوى']];

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
    { key: 'due', label: 'الموعد المستهدف', val: function (r) { return isComplaint(r) ? 0 : r.due.getTime(); }, xl: function (r) { return isComplaint(r) ? '' : xlDate(r.due); }, render: function (r) { return isComplaint(r) ? span({ className: 'muted' }, '—') : dueText(r); } },
    { key: 'updated', label: 'آخر تحديث', val: function (r) { return (isComplaint(r) ? r.created : lastTouch(r)).getTime(); }, xl: function (r) { return xlDate(isComplaint(r) ? r.created : lastTouch(r)); }, render: function (r) { return since(isComplaint(r) ? r.created : lastTouch(r)); } },
    { key: 'msgs', label: 'المراسلات', val: chatCount, render: function (r) { return span({ className: 'msgcount' }, h(Icon, { name: 'chat', size: 15 }), chatCount(r), h(Badge, { n: unreadOf(r, role, props.seen) })); } },
    openCol(props.onDelete)
  ];
  return h(DataTable, { cols: defs, rows: props.rows, onOpen: props.onOpen, exportName: 'طلبات-ومطابقات', rowClass: function (r) { return rowTone(unreadOf(r, role, props.seen), props.fresh, r); } });
}

function Dashboard(props) {
  const fromHash = function () { const m = /(?:^|[#&])f=([a-z]+)/.exec(window.location.hash || ''); return m && FILTERS.some(function (f) { return f[0] === m[1]; }) ? m[1] : 'all'; };
  const [flt, setFltState] = useState(fromHash);
  /* the filter lives in the address (#f=late): the back button and a shared link restore the same view */
  const setFlt = function (k) {
    setFltState(k);
    try { history.pushState(null, '', k === 'all' ? window.location.pathname + window.location.search : '#f=' + k); } catch (e) { /* ignore */ }
  };
  useEffect(function () {
    const back = function () { setFltState(fromHash()); };
    window.addEventListener('popstate', back);
    return function () { window.removeEventListener('popstate', back); };
  }, []);
  const reqs = props.reqs;
  const keyOf = function (r) { return statusOf(r, 'manager').key; };
  const open = reqs.filter(function (r) { return r.stage < 5; });
  const late = open.filter(isLate);
  const doneAll = reqs.filter(function (r) { return r.stage === 5; });
  const doneMonth = doneAll.filter(function (r) { return r.reached[5].getMonth() === NOW.getMonth() && r.reached[5].getFullYear() === NOW.getFullYear(); });
  const avg = doneAll.length ? doneAll.reduce(function (s, r) { return s + (r.reached[5] - r.created) / DAY; }, 0) / doneAll.length : 0;
  const replyN = reqs.filter(function (r) { return keyOf(r) === 'reply'; }).length;
  const newC = props.complaints.filter(function (c) { return c.stage === 1; }).length;
  const unrC = unreadSum(props.complaints, 'manager', props.seen);
  const cRows = props.complaints.slice().sort(function (a, b) { return (a.stage === 3) - (b.stage === 3) || b.created - a.created; });

  const pipeline = [
    ['بانتظار التوزيع', 'idle', reqs.filter(function (r) { return r.stage === 1; }).length],
    ['قيد المطابقة', 'warn', reqs.filter(function (r) { return r.stage === 2; }).length],
    ['مراسلات واستيضاح', 'work', reqs.filter(function (r) { return r.stage === 3; }).length],
    ['بانتظار إرسال الملف', 'work', reqs.filter(function (r) { return r.stage === 4; }).length],
    ['منجز', 'ok', doneAll.length]
  ];
  const load = {};
  open.forEach(function (r) { const k = r.matcher || 'غير موزّع'; load[k] = (load[k] || 0) + 1; });
  const loadRows = Object.keys(load).map(function (k) { return [k, load[k]]; }).sort(function (a, b) { return b[1] - a[1]; });
  const maxLoad = loadRows.length ? loadRows[0][1] : 1;

  const cOpen = props.complaints.filter(function (c) { return c.stage < 3; }).length;
  const cReplied = props.complaints.length - cOpen;
  const cBySup = {};
  props.complaints.forEach(function (c) { cBySup[c.supplier] = (cBySup[c.supplier] || 0) + 1; });
  const cTop = Object.keys(cBySup).map(function (k) { return [k, cBySup[k]]; }).sort(function (a, b) { return b[1] - a[1]; })[0];
  const doneBy = {};
  doneAll.forEach(function (r) { if (r.matcher) doneBy[r.matcher] = (doneBy[r.matcher] || 0) + 1; });
  const doneRows = Object.keys(doneBy).map(function (k) { return [k, doneBy[k]]; }).sort(function (a, b) { return b[1] - a[1]; });
  const maxDone = doneRows.length ? doneRows[0][1] : 1;

  const counts = {
    all: reqs.length, late: late.length, reply: replyN,
    matching: reqs.filter(function (r) { return keyOf(r) === 'matching'; }).length,
    queue: reqs.filter(function (r) { return keyOf(r) === 'queue'; }).length, done: doneAll.length,
    complaints: props.complaints.length
  };
  const reqRows = flt === 'complaints' ? [] : reqs.filter(function (r) { return flt === 'all' ? true : flt === 'late' ? isLate(r) : keyOf(r) === flt; })
    .sort(function (a, b) { return (a.stage === 5) - (b.stage === 5) || b.created - a.created; });
  const rows = (flt === 'all' || flt === 'complaints' ? cRows : []).concat(reqRows);

  return div({ className: 'stack' },
    div({ className: 'sechead' }, h2(null, 'متابعة المطابقات'), span({ className: 'muted small' }, 'عرض للمراقبة، بدون تدخل في سير الطلبات')),
    newC ? div({ className: 'alertbar', role: 'status' }, h(Icon, { name: 'alert' }), newC === 1 ? 'وصلتك شكوى جديدة من مورد' : 'وصلتك ' + newC + ' شكاوى جديدة من الموردين') : null,
    h(AlertBar, { n: unrC, text: newMsgText(unrC, 'الموردين') }),
    h3({ className: 'kgroup' }, 'طلبات المطابقة'),
    div({ className: 'kpis' },
      h(Kpi, { label: 'طلبات مفتوحة', value: open.length, note: 'من أصل ' + reqs.length + ' طلب' }),
      h(Kpi, { label: 'متأخرة عن ' + SLA_DAYS + ' أيام', value: late.length, note: replyN + ' منها تنتظر رد المورد', tone: late.length ? 'bad' : '' }),
      h(Kpi, { label: 'منجزة هذا الشهر', value: doneMonth.length, note: 'طلبات أُغلقت بالاتفاق' }),
      h(Kpi, { label: 'متوسط مدة الإنجاز', value: avg.toFixed(1), note: 'يوم لكل طلب منجز' })),
    h3({ className: 'kgroup' }, 'شكاوى الموردين'),
    div({ className: 'kpis' },
      h(Kpi, { label: 'شكاوى مفتوحة', value: cOpen, note: 'من أصل ' + props.complaints.length + ' شكوى', tone: cOpen ? 'bad' : '' }),
      h(Kpi, { label: 'شكاوى جديدة', value: newC, note: 'لم تُراجع بعد', tone: newC ? 'bad' : '' }),
      h(Kpi, { label: 'شكاوى تم الرد عليها', value: cReplied, note: props.complaints.length ? Math.round(cReplied / props.complaints.length * 100) + '% من الشكاوى' : 'لا توجد شكاوى' }),
      h(Kpi, { label: 'أكثر مورد شكوى', value: cTop ? cTop[1] : 0, note: cTop ? cTop[0] : 'لا توجد شكاوى' })),
    div({ className: 'two' },
      section({ className: 'panel' }, h3(null, 'أين تقف الطلبات الآن'),
        div({ className: 'strip', role: 'img', 'aria-label': pipeline.map(function (x) { return x[0] + ' ' + x[2]; }).join('، ') },
          pipeline.filter(function (x) { return x[2] > 0; }).map(function (x) { return div({ key: x[0], className: 'bg-' + x[1], style: { flexGrow: x[2], flexBasis: 0 } }); })),
        div({ className: 'legend' }, pipeline.map(function (x) { return div({ key: x[0] }, h('i', { className: 'bg-' + x[1] }), x[0], h('b', null, x[2])); }))),
      section({ className: 'panel' }, h3(null, 'الحمل على المطابقين'),
        ul({ className: 'load' }, loadRows.map(function (x) {
          return li({ key: x[0] }, span(null, x[0]), div({ className: 'track', role: 'img', 'aria-label': x[0] + ': ' + x[1] + ' طلب مفتوح' }, h('i', { style: { width: (x[1] / maxLoad * 100) + '%' } })), h('b', null, x[1]));
        })))),
    section({ className: 'panel' }, h3(null, 'المطابقون الأكثر إنجازاً'),
      doneRows.length ? ul({ className: 'load top' }, doneRows.map(function (x, i) {
        return li({ key: x[0], className: i === 0 ? 'first' : '' }, span(null, x[0], i === 0 ? span({ className: 'crown' }, 'الأول') : null), div({ className: 'track', role: 'img', 'aria-label': x[0] + ': ' + x[1] + ' طلب منجز' }, h('i', { style: { width: (x[1] / maxDone * 100) + '%' } })), h('b', null, x[1]));
      })) : p({ className: 'muted' }, 'لا توجد طلبات منجزة بعد.')),
    div({ className: 'tools' },
      div({ className: 'filters', role: 'group', 'aria-label': 'تصفية الطلبات' }, FILTERS.map(function (f) {
        return button({ key: f[0], className: 'fchip', 'aria-pressed': flt === f[0], onClick: function () { setFlt(f[0]); } }, f[1], h('b', null, counts[f[0]]));
      })),
      null),
    h(UnifiedTable, { onDelete: props.onDelete, rows: rows, seen: props.seen, fresh: props.fresh, onOpen: function (id) { return isComplaint({ id: id }) ? props.onOpenC(id) : props.onOpen(id); } }));
}
