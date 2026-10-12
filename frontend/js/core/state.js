'use strict';

/* ---------- derived state ---------- */
const isLate = function (r) { return r.stage < 4 && r.due < NOW; };
function lastDialogue(r) {
  for (let i = r.messages.length - 1; i >= 0; i--) {
    const f = r.messages[i].from;
    if (f === 'supplier' || f === 'matcher') return f;
  }
  return null;
}
function statusOf(r, role) {
  if (r.stage === 1) return { label: 'بانتظار التوزيع', tone: 'idle', key: 'queue' };
  if (r.stage === 2) return { label: 'قيد المطابقة', tone: 'warn', key: 'matching' };
  if (r.stage === 4) return { label: 'منجز', tone: 'ok', key: 'done' };
  const last = lastDialogue(r);
  if (last === 'matcher') return { label: role === 'supplier' ? 'يحتاج ردك' : 'بانتظار رد المورد', tone: 'bad', key: 'reply' };
  if (last === 'supplier') return { label: role === 'matcher' ? 'بانتظارك' : 'بانتظار المطابق', tone: 'work', key: 'dialogue' };
  return { label: 'مراسلات واستيضاح', tone: 'work', key: 'dialogue' };
}
function dueText(r) {
  if (r.stage === 4) return 'أُنجز في ' + fmtDate(r.reached[4]);
  if (r.due < NOW) return 'متأخر ' + unit(Math.max(1, Math.ceil((NOW - r.due) / DAY)), 'يوم', 'يومين', 'أيام', 'يوماً');
  return 'متبقي ' + unit(Math.max(1, Math.ceil((r.due - NOW) / DAY)), 'يوم', 'يومين', 'أيام', 'يوماً');
}
function lastTouch(r) {
  let t = r.reached[r.stage];
  r.messages.forEach(function (m) { if (m.at > t) t = m.at; });
  return t;
}
const senderName = function (r, m) { return m.from === 'supplier' ? r.supplier : m.from === 'matcher' ? (r.matcher || 'المطابق') : 'المدير المالي'; };
const chatCount = function (r) { return r.messages.filter(function (m) { return m.from !== 'system'; }).length; };

/* unread: a message is "new" for a role until that role opens the conversation (the server stores when) */
function tracksUnread(id, role) { return id.indexOf('SH-') === 0 ? (role === 'supplier' || role === 'manager') : (role === 'supplier' || role === 'matcher'); }
function seenAt(seen, id, role) { const v = seen[id + ':' + role]; return v != null ? v : 0; }
function isFresh(m, role, since) { return m.from !== 'system' && m.from !== role && m.at.getTime() > since; }
function unreadOf(conv, role, seen) {
  if (!tracksUnread(conv.id, role)) return 0;
  const since = seenAt(seen, conv.id, role);
  return conv.messages.filter(function (m) { return isFresh(m, role, since); }).length;
}
function unreadSum(list, role, seen) { return list.reduce(function (n, c) { return n + unreadOf(c, role, seen); }, 0); }
const newMsgText = function (n, from) { return n === 1 ? 'لديك رسالة جديدة من ' + from + ' تحتاج ردك' : 'لديك ' + n + ' رسائل جديدة من ' + from + ' تحتاج ردك'; };
function useNarrow() {
  const q = '(max-width: 900px)';
  const [narrow, setNarrow] = useState(function () { try { return window.matchMedia(q).matches; } catch (e) { return false; } });
  useEffect(function () {
    let mq;
    try { mq = window.matchMedia(q); } catch (e) { return undefined; }
    const f = function () { setNarrow(mq.matches); };
    if (mq.addEventListener) mq.addEventListener('change', f); else mq.addListener(f);
    return function () { if (mq.removeEventListener) mq.removeEventListener('change', f); else mq.removeListener(f); };
  }, []);
  return narrow;
}

function statusC(c, role) {
  if (c.stage === 1) return role === 'manager' ? { label: 'جديدة', tone: 'bad', key: 'new' } : { label: 'وصلت المدير المالي', tone: 'idle', key: 'new' };
  if (c.stage === 2) return { label: 'قيد المراجعة', tone: 'warn', key: 'review' };
  return { label: 'تم الرد', tone: 'ok', key: 'closed' };
}
