'use strict';

function MatcherHome(props) {
  /* a matcher sees what was assigned to them; the supervisor, manager and admin see every open request */
  const own = props.userRole === 'matcher';
  const rows = props.reqs.filter(function (r) { return (own ? r.stage < 4 : r.stage < 5) && (!own || r.matcher === props.meName); })
    .sort(function (a, b) { return b.created - a.created; });
  const unr = unreadSum(rows.filter(function (r) { return r.matcher === props.meName; }), 'matcher', props.seen);
  const late = rows.filter(isLate).length;
  return section({ className: 'stack matcher-queue', 'aria-labelledby': 'matcher-queue-title' },
    header({ className: 'matcher-queue-head' },
      div({ className: 'matcher-queue-title' },
        span({ className: 'matcher-queue-icon' }, h(Icon, { name: 'reconcile', size: 22 })),
        h2({ id: 'matcher-queue-title' }, 'طابور المطابقة')),
      div({ className: 'matcher-queue-counts' },
        span({ className: 'matcher-queue-count' }, h(Icon, { name: 'file', size: 15 }), 'الطلبات المفتوحة', strong(null, rows.length)),
        span({ className: 'matcher-queue-count' + (late ? ' has-late' : '') }, h(Icon, { name: 'alert', size: 15 }), 'المتأخرة', strong(null, late)))),
    h(AlertBar, { n: unr, text: newMsgText(unr, 'الموردين') }),
    h(RequestTable, { rows: rows, role: 'matcher', seen: props.seen, fresh: props.fresh, onOpen: props.onOpen, onDelete: props.onDelete, label: 'طلبات طابور المطابقة' }));
}
