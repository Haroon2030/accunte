'use strict';

function MatcherHome(props) {
  /* a matcher sees what was assigned to them; the supervisor, manager and admin see every open request */
  const own = props.userRole === 'matcher';
  const rows = props.reqs.filter(function (r) { return (own ? r.stage < 4 : r.stage < 5) && (!own || r.matcher === props.meName); })
    .sort(function (a, b) { return b.created - a.created; });
  const unr = unreadSum(rows.filter(function (r) { return r.matcher === props.meName; }), 'matcher', props.seen);
  const late = rows.filter(isLate).length;
  return div({ className: 'stack' },
    div({ className: 'sechead' }, h2(null, 'طابور المطابقة'), span({ className: 'muted small' }, rows.length + ' طلب مفتوح' + (late ? ' · ' + late + ' متأخر' : ''))),
    h(AlertBar, { n: unr, text: newMsgText(unr, 'الموردين') }),
    h(RequestTable, { rows: rows, role: 'matcher', seen: props.seen, fresh: props.fresh, onOpen: props.onOpen }));
}
