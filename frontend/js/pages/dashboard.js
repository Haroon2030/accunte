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
const DASHBOARD_TIME_ZONE = 'Asia/Riyadh';
const dashboardDayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: DASHBOARD_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' });
const dashboardShortDate = new Intl.DateTimeFormat('ar-SA-u-ca-gregory-nu-latn', { timeZone: 'UTC', day: 'numeric', month: 'short' });

function dashboardDay(date) {
  if (!date || !Number.isFinite(date.getTime())) return '';
  const parts = {};
  dashboardDayFmt.formatToParts(date).forEach(function (part) { parts[part.type] = part.value; });
  return parts.year + '-' + parts.month + '-' + parts.day;
}

function dashboardActivity(requests, today) {
  const days = new Map();
  const end = Date.parse(today + 'T00:00:00Z');
  for (let offset = 29; offset >= 0; offset--) {
    const date = new Date(end - offset * DAY);
    days.set(date.toISOString().slice(0, 10), { date: date, received: 0, completed: 0 });
  }
  requests.forEach(function (request) {
    const received = days.get(dashboardDay(request.created));
    const completed = request.stage === 5 ? days.get(dashboardDay(request.reached[5])) : null;
    if (received) received.received++;
    if (completed) completed.completed++;
  });
  return Array.from(days.values());
}

function DashboardTrend(props) {
  const [hoverDay, setHoverDay] = useState(null);
  const days = props.days;
  const received = days.reduce(function (total, day) { return total + day.received; }, 0);
  const completed = days.reduce(function (total, day) { return total + day.completed; }, 0);
  const activeDays = days.filter(function (day) { return day.received || day.completed; });
  const end = days.length - 1;
  const peak = Math.max(1, ...days.map(function (day) { return Math.max(day.received, day.completed); }));
  const step = Math.ceil(peak / 4);
  const scale = Math.ceil(peak / step) * step;
  const ticks = Array.from({ length: scale / step + 1 }, function (_, index) { return scale - index * step; });
  const x = function (index) { return 8 + index / end * 584; };
  const y = function (value) { return 172 - value / scale * 164; };
  const series = function (key) { return days.map(function (day, index) { return x(index) + ',' + y(day[key]); }).join(' '); };
  const picked = hoverDay === null ? null : days[hoverDay];
  const range = dashboardShortDate.format(days[0].date) + ' – ' + dashboardShortDate.format(days[end].date);

  return section({ className: 'panel dashboard-trend' },
    div({ className: 'dashboard-chart-head' },
      div(null, h3(null, 'حركة طلبات المطابقة'), p({ className: 'muted small' }, 'الطلبات الواردة والمنجزة يوميًا')),
      span({ className: 'dashboard-period', title: range }, 'آخر 30 يومًا')),
    div({ className: 'dashboard-chart-legend' },
      span({ className: 'trend-received' }, 'واردة', strong(null, received)),
      span({ className: 'trend-completed' }, 'منجزة', strong(null, completed))),
    activeDays.length
      ? div({ className: 'dashboard-chart', onMouseLeave: function () { setHoverDay(null); } },
        div({ className: 'dashboard-chart-ticks', 'aria-hidden': 'true' }, ticks.map(function (n) { return span({ key: n }, n); })),
        div({ className: 'dashboard-chart-plot' },
          h('svg', { viewBox: '0 0 600 180', preserveAspectRatio: 'none', role: 'img',
            'aria-label': 'حركة الطلبات من ' + range + '، الواردة ' + received + ' والمنجزة ' + completed },
            ticks.map(function (n) { return h('line', { key: n, x1: 8, x2: 592, y1: y(n), y2: y(n), className: 'trend-gridline', vectorEffect: 'non-scaling-stroke' }); }),
            h('polygon', { points: x(0) + ',172 ' + series('received') + ' ' + x(end) + ',172', className: 'trend-area' }),
            h('polyline', { points: series('received'), className: 'trend-line trend-received', vectorEffect: 'non-scaling-stroke' }),
            h('polyline', { points: series('completed'), className: 'trend-line trend-completed', vectorEffect: 'non-scaling-stroke' }),
            picked ? h('line', { x1: x(hoverDay), x2: x(hoverDay), y1: 8, y2: 172, className: 'trend-cursor', vectorEffect: 'non-scaling-stroke' }) : null,
            days.map(function (day, index) {
              const left = index === 0 ? 0 : (x(index - 1) + x(index)) / 2;
              const right = index === end ? 600 : (x(index) + x(index + 1)) / 2;
              return h('rect', { key: index, x: left, y: 0, width: right - left, height: 180, fill: 'transparent',
                onMouseEnter: function () { setHoverDay(index); }, onClick: function () { setHoverDay(index); } });
            })),
          div({ className: 'dashboard-chart-dates', 'aria-hidden': 'true' }, [0, 7, 14, 22, end].map(function (index) {
            return span({ key: index }, dashboardShortDate.format(days[index].date));
          }))))
      : p({ className: 'dashboard-chart-empty' }, 'لا توجد طلبات واردة أو منجزة خلال آخر 30 يومًا.'),
    activeDays.length ? div({ className: 'dashboard-chart-foot' },
      span({ className: 'dashboard-chart-readout' }, picked ? dashboardShortDate.format(picked.date) + ' · واردة ' + picked.received + ' · منجزة ' + picked.completed : range),
      h('details', { className: 'dashboard-chart-data' },
        h('summary', null, 'الأيام التي شهدت نشاطًا'),
        table(null,
          thead(null, tr(null, ['التاريخ', 'واردة', 'منجزة'].map(function (label) { return th({ key: label, scope: 'col' }, label); }))),
          tbody(null, activeDays.map(function (day) {
            return tr({ key: day.date.getTime() }, td(null, dashboardShortDate.format(day.date)), td(null, day.received), td(null, day.completed));
          }))))) : null);
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
  const today = dashboardDay(new Date());
  const month = today.slice(0, 7);
  const doneMonth = doneAll.filter(function (r) { return dashboardDay(r.reached[5]).slice(0, 7) === month; });
  const durations = doneMonth.filter(function (r) { return dashboardDay(r.created) && r.reached[5] >= r.created; });
  const avg = durations.length ? durations.reduce(function (s, r) { return s + (r.reached[5] - r.created) / DAY; }, 0) / durations.length : null;
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
  const load = new Map();
  open.forEach(function (r) { const name = r.matcher || 'غير موزّع'; load.set(name, (load.get(name) || 0) + 1); });
  const loadRows = Array.from(load).sort(function (a, b) { return b[1] - a[1]; });

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
      div(null, h2(null, 'لوحة متابعة المطابقات'), p({ className: 'muted small' }, 'حركة الطلبات وتوزيعها على فريق المطابقة'))),
    newC ? div({ className: 'alertbar', role: 'status' }, h(Icon, { name: 'alert' }), newC === 1 ? 'وصلتك شكوى جديدة من مورد' : 'وصلتك ' + newC + ' شكاوى جديدة من الموردين') : null,
    h(AlertBar, { n: unrC, text: newMsgText(unrC, 'الموردين') }),
    div({ className: 'kpis dashboard-kpis' },
      h(Kpi, { label: 'طلبات مفتوحة', value: open.length, note: 'من أصل ' + reqs.length + ' طلب', icon: 'file', colorTone: 'blue' }),
      h(Kpi, { label: 'طلبات متأخرة', value: late.length, note: open.length ? Math.round(late.length / open.length * 100) + '% من الطلبات المفتوحة' : 'لا توجد طلبات مفتوحة', icon: 'alert', colorTone: 'red' }),
      h(Kpi, { label: 'منجزة هذا الشهر', value: doneMonth.length, note: avg === null ? 'لا يوجد متوسط لهذا الشهر' : 'متوسط الإنجاز ' + avg.toFixed(1) + ' يوم', icon: 'check', colorTone: 'green' }),
      h(Kpi, { label: 'شكاوى جديدة', value: newC, note: 'بانتظار المراجعة', icon: 'chat', colorTone: 'amber' })),
    div({ className: 'two dashboard-insights' },
      h(DashboardTrend, { days: dashboardActivity(reqs, today) }),
      section({ className: 'panel dashboard-load' },
        div({ className: 'dashboard-chart-head' },
          div(null, h3(null, 'توزيع الحمل على المطابقين'), p({ className: 'muted small' }, 'حصة كل مطابق من الطلبات المفتوحة'))),
        loadRows.length ? ul({ className: 'load' }, loadRows.map(function (entry) {
          const name = entry[0], count = entry[1], share = count / open.length * 100;
          return li({ key: name },
            span({ className: 'dashboard-load-name', title: name }, name),
            span({ className: 'dashboard-load-count' }, strong(null, count), span(null, Math.round(share) + '%')),
            div({ className: 'track', 'aria-hidden': 'true' }, h('i', { style: { width: share + '%' } })));
        })) : p({ className: 'dashboard-chart-empty' }, 'لا توجد طلبات مفتوحة لتوزيعها.'))),
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
