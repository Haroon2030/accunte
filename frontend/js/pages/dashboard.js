'use strict';

/* ---------- finance manager dashboard ---------- */
function Kpi(props) {
  return div({ className: 'kpi' + (props.tone ? ' ' + props.tone : '') + (props.colorTone ? ' color-' + props.colorTone : '') },
    div({ className: 'kpi-head' }, span({ className: 'k' }, props.label),
      props.icon ? span({ className: 'kpi-icon ' + (props.iconTone || '') }, h(Icon, { name: props.icon, size: 18 })) : null),
    span({ className: 'v' }, props.value), span({ className: 'n' }, props.note));
}

const FILTERS = [['all', 'الكل'], ['late', 'متأخرة'], ['reply', 'تنتظر رد المورد'], ['matching', 'قيد المطابقة'], ['queue', 'بانتظار التوزيع'], ['sending', 'بانتظار إرسال الملف'], ['done', 'منجزة'], ['complaints', 'الشكاوى']];
const FILTER_ICONS = { all: 'file', late: 'alert', reply: 'chat', matching: 'search', queue: 'sort', sending: 'send', done: 'check', complaints: 'chat' };

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

  const counts = {
    all: reqs.length, late: late.length, reply: replyN,
    matching: reqs.filter(function (r) { return keyOf(r) === 'matching'; }).length,
    queue: reqs.filter(function (r) { return keyOf(r) === 'queue'; }).length,
    sending: reqs.filter(function (r) { return keyOf(r) === 'sending'; }).length, done: doneAll.length,
    complaints: props.complaints.length
  };
  const reqRows = flt === 'complaints' ? [] : reqs.filter(function (r) { return flt === 'all' ? true : flt === 'late' ? isLate(r) : keyOf(r) === flt; })
    .sort(function (a, b) { return (a.stage === 5) - (b.stage === 5) || b.created - a.created; });
  return div({ className: 'stack manager-dashboard' },
    div({ className: 'sechead dashboard-head' },
      div(null, h2(null, 'لوحة متابعة المطابقات'), p({ className: 'muted small' }, 'نظرة شاملة على الطلبات وأداء فريق المطابقة')),
      span({ className: 'dashboard-period' }, 'مؤشرات محدثة مباشرة')),
    newC ? div({ className: 'alertbar', role: 'status' }, h(Icon, { name: 'alert' }), newC === 1 ? 'وصلتك شكوى جديدة من مورد' : 'وصلتك ' + newC + ' شكاوى جديدة من الموردين') : null,
    h(AlertBar, { n: unrC, text: newMsgText(unrC, 'الموردين') }),
    div({ className: 'kpis dashboard-kpis' },
      h(Kpi, { label: 'طلبات مفتوحة', value: open.length, note: 'من أصل ' + reqs.length + ' طلب', icon: 'file', colorTone: 'teal' }),
      h(Kpi, { label: 'طلبات متأخرة', value: late.length, note: 'تجاوزت مهلة ' + SLA_DAYS + ' أيام', icon: 'alert', colorTone: 'red' }),
      h(Kpi, { label: 'منجزة هذا الشهر', value: doneMonth.length, note: 'متوسط الإنجاز ' + avg.toFixed(1) + ' يوم', icon: 'check', colorTone: 'green' }),
      h(Kpi, { label: 'شكاوى جديدة', value: newC, note: 'بانتظار المراجعة', icon: 'chat', colorTone: 'amber' })),
    div({ className: 'two dashboard-insights' },
      section({ className: 'panel dashboard-pipeline' },
        div({ className: 'pipeline-head' },
          div(null, h3(null, 'مسار الطلبات'), p({ className: 'muted small' }, 'توزيع الطلبات الحالية حسب مرحلة المعالجة')),
          span({ className: 'pipeline-total' }, reqs.length, ' طلبًا')),
        div({ className: 'pipeline-timeline', role: 'list', 'aria-label': 'مراحل الطلبات من اليمين إلى اليسار' },
          pipeline.map(function (x, i) {
            return div({ key: x[0], className: 'pipeline-step tone-' + x[1], role: 'listitem', 'aria-label': x[0] + ': ' + x[2] + ' طلب' },
              span({ className: 'pipeline-marker', 'aria-hidden': 'true' }, i === pipeline.length - 1 ? '✓' : i + 1),
              strong({ className: 'pipeline-count' }, x[2]),
              span({ className: 'pipeline-label' }, x[0]));
          }))),
      section({ className: 'panel dashboard-load' }, h3(null, 'توزيع الحمل على المطابقين'),
        ul({ className: 'load' }, loadRows.map(function (x) {
          return li({ key: x[0] }, span(null, x[0]), div({ className: 'track', role: 'img', 'aria-label': x[0] + ': ' + x[1] + ' طلب مفتوح' }, h('i', { style: { width: (x[1] / maxLoad * 100) + '%' } })), h('b', null, x[1]));
        })))),
    section({ className: 'panel dashboard-list' },
      div({ className: 'dashboard-listhead' },
        div(null, h3(null, flt === 'complaints' ? 'شكاوى الموردين' : 'أحدث طلبات المطابقة'), p({ className: 'muted small' }, flt === 'complaints' ? 'متابعة البلاغات الواردة من الموردين' : 'تابع حالة الطلبات ومهلها الزمنية')),
        span({ className: 'dashboard-total' }, flt === 'complaints' ? props.complaints.length + ' شكوى' : reqRows.length + ' طلب')),
      div({ className: 'filters dashboard-filters', role: 'group', 'aria-label': 'تصفية الطلبات' }, FILTERS.map(function (f) {
        return button({ key: f[0], className: 'fchip fchip-' + f[0], 'aria-pressed': flt === f[0], onClick: function () { setFlt(f[0]); } }, h(Icon, { name: FILTER_ICONS[f[0]], size: 14 }), span({ className: 'fchip-label' }, f[1]), h('b', null, counts[f[0]]));
      })),
      flt === 'complaints'
        ? h(ComplaintTable, { role: 'manager', rows: cRows, seen: props.seen, fresh: props.fresh, onOpen: props.onOpenC, pageSize: 6, hideExport: true })
        : h(RequestTable, { role: 'manager', rows: reqRows, seen: props.seen, fresh: props.fresh, onOpen: props.onOpen, hide: ['updated', 'msgs'], pageSize: 6, hideExport: true })));
}
