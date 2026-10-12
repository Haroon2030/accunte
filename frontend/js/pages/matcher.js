'use strict';

function MatcherHome(props) {
  const rows = props.reqs.filter(function (r) { return r.stage < 4; })
    .sort(function (a, b) { return a.due - b.due; });
  const unr = unreadSum(rows.filter(function (r) { return r.matcher === props.me.name; }), 'matcher', props.seen);
  const late = rows.filter(isLate).length;
  return div({ className: 'stack' },
    div({ className: 'sechead' }, h2(null, 'طابور المطابقة'), span({ className: 'muted small' }, rows.length + ' طلب مفتوح' + (late ? ' · ' + late + ' متأخر' : ''))),
    h(AlertBar, { n: unr, text: newMsgText(unr, 'الموردين') }),
    h(RequestTable, { rows: rows, role: 'matcher', seen: props.seen, onOpen: props.onOpen }));
}
