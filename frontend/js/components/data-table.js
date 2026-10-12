'use strict';

/* ---------- data table (shared by every list): header filters, sorting, 8 rows per page ---------- */
const PAGE = 8;
function pageList(cur, pages) {
  const out = [];
  const from = Math.max(1, Math.min(cur - 2, pages - 4)), to = Math.min(pages, from + 4);
  for (let p = from; p <= to; p++) out.push(p);
  return out;
}
function DataTable(props) {
  const [sort, setSort] = useState(props.defaultSort || null);
  const [flt, setFlt] = useState({});
  const [page, setPage] = useState(1);
  const [fopen, setFopen] = useState(false);
  const cols = props.cols;
  const fvOf = function (c) { return c.fv || function (r) { return String(c.val ? c.val(r) : ''); }; };
  const activeCols = cols.filter(function (c) { return c.filter && flt[c.key]; });
  let rows = props.rows.filter(function (r) {
    return activeCols.every(function (c) {
      const want = flt[c.key], got = fvOf(c)(r);
      return c.filter === 'select' ? got === want : got.indexOf(want.trim()) !== -1;
    });
  });
  if (sort) {
    const sc = cols.filter(function (c) { return c.key === sort.key; })[0];
    if (sc && sc.val) rows.sort(function (a, b) {
      const x = sc.val(a), y = sc.val(b);
      const r = x < y ? -1 : x > y ? 1 : 0;
      return sort.dir === 'asc' ? r : -r;
    });
  }
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const cur = Math.min(page, pages);
  const shown = rows.slice((cur - 1) * PAGE, cur * PAGE);
  const firstN = rows.length ? (cur - 1) * PAGE + 1 : 0, lastN = Math.min(rows.length, cur * PAGE);
  function toggle(c) {
    setSort(function (s0) { return s0 && s0.key === c.key ? { key: c.key, dir: s0.dir === 'asc' ? 'desc' : 'asc' } : { key: c.key, dir: 'asc' }; });
  }
  function setF(k, v) { setFlt(function (o) { const n = Object.assign({}, o); n[k] = v; return n; }); setPage(1); }
  function filterCell(c) {
    if (c.filter === 'select') {
      const seen = {};
      props.rows.forEach(function (r) { seen[fvOf(c)(r)] = true; });
      const opts = Object.keys(seen).sort(function (a, b) { return a.localeCompare(b, 'ar'); });
      return select({ className: 'thf', 'aria-label': 'تصفية ' + c.label, value: flt[c.key] || '', onChange: function (e) { setF(c.key, e.target.value); } },
        option({ value: '' }, 'الكل'), opts.map(function (o) { return option({ key: o, value: o }, o); }));
    }
    if (c.filter === 'text') {
      return input({ type: 'text', className: 'thf', 'aria-label': 'تصفية ' + c.label, placeholder: 'بحث…', value: flt[c.key] || '', onChange: function (e) { setF(c.key, e.target.value); } });
    }
    return null;
  }
  const anyFilter = cols.some(function (c) { return c.filter; });
  const sortable = cols.filter(function (c) { return c.val; });
  /* phones: the header row is hidden and rows become cards, so filters and sorting live in this panel */
  const phoneTools = (anyFilter || sortable.length) ? div({ className: 'dtm' },
    button({ type: 'button', className: 'btn ghost sm dtm-toggle', 'aria-expanded': fopen, onClick: function () { setFopen(!fopen); } },
      h(Icon, { name: 'sort', size: 14 }), 'تصفية وترتيب', activeCols.length ? span({ className: 'dtm-n' }, activeCols.length) : null),
    fopen ? div({ className: 'dtm-panel' },
      sortable.length ? div({ className: 'tfield' }, label(null, 'ترتيب حسب'),
        select({ className: 'thf', 'aria-label': 'ترتيب حسب', value: sort ? sort.key + ':' + sort.dir : '', onChange: function (e) {
          const v = e.target.value.split(':'); setSort(v[0] ? { key: v[0], dir: v[1] } : null);
        } }, option({ value: '' }, 'بدون ترتيب'), sortable.map(function (c) {
          return [option({ key: c.key + 'a', value: c.key + ':asc' }, c.label + ' (تصاعدي)'), option({ key: c.key + 'd', value: c.key + ':desc' }, c.label + ' (تنازلي)')];
        }))) : null,
      cols.filter(function (c) { return c.filter; }).map(function (c) { return div({ key: c.key, className: 'tfield' }, label(null, c.label), filterCell(c)); })) : null) : null;
  return div({ className: 'dtbox' },
    phoneTools,
    div({ className: 'tablewrap' },
      table({ className: 'dt' },
        thead(null, tr(null, cols.map(function (c) {
          const on = sort && sort.key === c.key;
          return th({ key: c.key, scope: 'col', 'aria-sort': c.val ? (on ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none') : undefined },
            div({ className: 'thcell' },
              c.val ? button({ type: 'button', className: 'thbtn', onClick: function () { toggle(c); } }, c.label, h(Icon, { name: on ? (sort.dir === 'asc' ? 'up' : 'down') : 'sort', size: 14 })) : span({ className: 'thlabel' }, c.label),
              anyFilter ? div({ className: 'thslot' }, filterCell(c)) : null));
        }))),
        tbody(null, shown.length ? shown.map(function (r) {
          const open = function () { if (props.onOpen) props.onOpen(r.id); };
          return tr(Object.assign({ key: r.id, className: props.rowClass ? props.rowClass(r) : undefined }, props.onOpen ? { tabIndex: 0, onClick: open, onKeyDown: function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } } } : {}),
            cols.map(function (c) { return td({ key: c.key, 'data-label': c.label, 'data-col': c.key }, c.render(r, open)); }));
        }) : tr(null, td({ colSpan: cols.length, className: 'empty' }, props.empty || 'لا توجد نتائج مطابقة للتصفية'))))),
    div({ className: 'pager' },
      span({ className: 'muted small' }, rows.length ? 'عرض ' + firstN + '–' + lastN + ' من ' + rows.length + (rows.length !== props.rows.length ? ' (من أصل ' + props.rows.length + ')' : '') : '0 نتيجة'),
      activeCols.length ? button({ type: 'button', className: 'btn ghost sm', onClick: function () { setFlt({}); setPage(1); } }, 'مسح الفلاتر') : null,
      pages > 1 ? h('nav', { className: 'pgnav', 'aria-label': 'ترقيم الصفحات' },
        button({ type: 'button', className: 'pgbtn', disabled: cur === 1, onClick: function () { setPage(cur - 1); } }, 'السابق'),
        pageList(cur, pages).map(function (p) {
          return button({ key: p, type: 'button', className: 'pgbtn num', 'aria-current': p === cur ? 'page' : undefined, 'aria-label': 'صفحة ' + p, onClick: function () { setPage(p); } }, p);
        }),
        button({ type: 'button', className: 'pgbtn', disabled: cur === pages, onClick: function () { setPage(cur + 1); } }, 'التالي')) : null));
}

/* light red tint: a message waits for the reader, or the record was never opened by them */
function rowTone(unread, fresh, rec) { return [unread ? 'unread' : '', fresh && fresh(rec) ? 'fresh' : ''].filter(Boolean).join(' ') || undefined; }
function colsFor(defs, hide) { return defs.filter(function (c) { return !hide || hide.indexOf(c.key) === -1; }); }
const OPEN_COL = { key: 'open', label: 'إجراء', render: function (r, open) {
  return button({ type: 'button', className: 'btn ghost sm', onClick: function (e) { e.stopPropagation(); open(); } }, 'فتح', h(Icon, { name: 'chevL', size: 14 }));
} };

function ComplaintTable(props) {
  const role = props.role || 'manager';
  const defs = [
    { key: 'id', label: 'رقم الشكوى', filter: 'text', val: function (c) { return c.id; }, render: function (c) { return span({ className: 'mono' }, c.id); } },
    { key: 'supplier', label: 'المورد', filter: 'text', val: function (c) { return c.supplier; }, render: function (c) { return strong({ style: { fontWeight: 600 } }, c.supplier); } },
    { key: 'subject', label: 'الموضوع', filter: 'text', val: function (c) { return c.subject; }, render: function (c) { return c.subject; } },
    { key: 'category', label: 'النوع', filter: 'select', val: function (c) { return c.category; }, render: function (c) { return c.category; } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: function (c) { return statusC(c, role).label; }, val: function (c) { return c.stage; }, render: function (c) { return h(StatusPill, { st: statusC(c, role) }); } },
    { key: 'created', label: 'وصلت', val: function (c) { return c.created.getTime(); }, render: function (c) { return since(c.created); } },
    { key: 'msgs', label: 'المراسلات', val: chatCount, render: function (c) { return span({ className: 'msgcount' }, h(Icon, { name: 'chat', size: 15 }), chatCount(c), h(Badge, { n: unreadOf(c, role, props.seen) })); } },
    OPEN_COL
  ];
  return h(DataTable, { cols: colsFor(defs, props.hide), rows: props.rows, onOpen: props.onOpen, defaultSort: props.defaultSort, rowClass: function (c) { return rowTone(unreadOf(c, role, props.seen), props.fresh, c); } });
}

function RequestTable(props) {
  const role = props.role;
  const defs = [
    { key: 'id', label: 'رقم الطلب', filter: 'text', val: function (r) { return r.id; }, render: function (r) { return span({ className: 'mono' }, r.id); } },
    { key: 'supplier', label: 'المورد', filter: 'text', val: function (r) { return r.supplier; }, render: function (r) { return strong({ style: { fontWeight: 600 } }, r.supplier); } },
    { key: 'period', label: 'الفترة', filter: 'select', val: function (r) { return r.period; }, render: function (r) { return r.period; } },
    { key: 'status', label: 'الحالة', filter: 'select', fv: function (r) { return statusOf(r, role).label; }, val: function (r) { return r.stage; }, render: function (r) {
      return div({ className: 'cell-status' }, h(StatusPill, { st: statusOf(r, role) }), isLate(r) ? h(LateChip) : null);
    } },
    { key: 'matcher', label: 'المطابق', filter: 'select', fv: function (r) { return r.matcher || 'لم يُوزَّع بعد'; }, val: function (r) { return r.matcher || ''; }, render: function (r) { return r.matcher || span({ className: 'muted' }, 'لم يُوزَّع بعد'); } },
    { key: 'due', label: 'الموعد المستهدف', val: function (r) { return r.due.getTime(); }, render: dueText },
    { key: 'updated', label: 'آخر تحديث', val: function (r) { return lastTouch(r).getTime(); }, render: function (r) { return since(lastTouch(r)); } },
    { key: 'msgs', label: 'المراسلات', val: chatCount, render: function (r) { return span({ className: 'msgcount' }, h(Icon, { name: 'chat', size: 15 }), chatCount(r), h(Badge, { n: unreadOf(r, role, props.seen) })); } },
    OPEN_COL
  ];
  return h(DataTable, { cols: colsFor(defs, props.hide), rows: props.rows, onOpen: props.onOpen, defaultSort: props.defaultSort, rowClass: function (r) { return rowTone(unreadOf(r, role, props.seen), props.fresh, r); } });
}

/* one service = header with its main action + the table (filters live in the table header) */
function ServicePanel(props) {
  return section({ className: 'svcpanel' },
    div({ className: 'svchead' },
      div(null, h2(null, props.title), p({ className: 'muted small' }, props.sub)),
      button({ className: 'btn primary', onClick: props.onAction }, h(Icon, { name: 'plus' }), props.actionLabel)),
    props.alert || null,
    props.render(props.rows));
}
