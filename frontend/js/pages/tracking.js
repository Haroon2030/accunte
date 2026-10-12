'use strict';

/* ---------- tracking page ---------- */
function Stepper(props) {
  const r = props.req;
  return ol({ className: 'stepper' }, props.stages.map(function (s, i) {
    const state = r.stage === props.stages.length - 1 || i < r.stage ? 'done' : i === r.stage ? 'current' : 'todo';
    const canAct = state === 'current' && props.canAct && !!props.adv[r.stage];
    return li({ key: s.title, className: 'step ' + state, 'aria-current': state === 'current' ? 'step' : undefined },
      div({ className: 'mark' }, state === 'done' ? h(Icon, { name: 'check', size: 17 }) : String(i + 1)),
      div(null,
        h4(null, s.title, state === 'current' ? span({ className: 'now' }, 'الخطوة الحالية') : null),
        state !== 'todo' && r.reached[i] ? span({ className: 'when' }, fmtDT(r.reached[i])) : null,
        div({ className: 'desc' }, s.desc),
        (canAct || (props.onChat && state === 'current')) ? div({ className: 'act' },
          canAct ? button({ className: 'btn primary', onClick: props.onAdvance }, props.adv[r.stage].label) : null,
          props.onChat && state === 'current' ? button({ className: 'btn ghost to-chat', onClick: props.onChat }, h(Icon, { name: 'chat' }), 'كتابة رسالة') : null) : null));
  }));
}

function Chat(props) {
  const r = props.req, role = props.role;
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const observer = !!props.observer;
  const mode = props.mode || (r.stage < 3 ? 'wait' : r.stage === 4 ? 'closed' : 'open');
  const [composerOpen, setComposerOpen] = useState(!observer);
  const listRef = useRef(null);
  const prevMode = useRef(mode);
  useEffect(function () {
    if (prevMode.current !== 'open' && mode === 'open') {
      const el = document.getElementById('chat-text');
      if (el) el.focus();
    }
    prevMode.current = mode;
  }, [mode]);
  const didInit = useRef(false);
  const baseline = props.baseline;
  const track = tracksUnread(r.id, role);
  const isNew = function (m) { return track && baseline != null && isFresh(m, role, baseline); };
  const newOnes = r.messages.filter(isNew);
  useEffect(function () {
    const el = listRef.current;
    if (!el || props.visible === false) return;
    const d = !didInit.current ? el.querySelector('.newdiv') : null;
    didInit.current = true;
    el.scrollTop = d ? Math.max(0, d.offsetTop - 12) : el.scrollHeight;
  }, [r.messages.length, props.visible]);
  const canSend = text.trim() || files.length;
  function send() {
    if (!canSend) return;
    props.onSend({ from: role, text: text.trim(), files: files });
    setText(''); setFiles([]);
  }
  let footerNode;
  if (mode === 'wait') footerNode = div({ className: 'note' }, props.waitNote || 'تُفتح المراسلة عندما يطلب المطابق استيضاحاً على أحد البنود. ستظهر هنا مع المرفقات.');
  else if (mode === 'closed') footerNode = div({ className: 'note' }, props.closedNote || 'أُغلقت المراسلة بعد إنجاز الطلب. السجل محفوظ للمراجعة.');
  else if (!composerOpen) footerNode = div({ className: 'composer' }, button({ className: 'btn ghost', onClick: function () { setComposerOpen(true); } }, 'إضافة ملاحظة مراقب'));
  else footerNode = div({ className: 'composer' },
    textarea({ id: 'chat-text', rows: 2, 'aria-label': 'نص الرسالة', value: text, placeholder: observer ? 'ملاحظة مراقب تظهر للطرفين' : 'اكتب رسالتك، ويمكنك إرفاق مستند',
      onChange: function (e) { setText(e.target.value); },
      onKeyDown: function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } } }),
    files.length ? div({ className: 'picked' }, files.map(function (f, i) {
      return h(FileChip, { key: f.name + i, f: f, onRemove: function () { setFiles(files.filter(function (_, j) { return j !== i; })); } });
    })) : null,
    div({ className: 'row' },
      input({ id: 'chat-file', type: 'file', multiple: true, hidden: true, onChange: function (e) {
        const added = Array.prototype.map.call(e.target.files, function (f) { return { name: f.name, size: f.size, file: f }; });
        setFiles(files.concat(added)); e.target.value = '';
      } }),
      label({ htmlFor: 'chat-file', className: 'btn ghost' }, h(Icon, { name: 'clip' }), 'إرفاق مستند'),
      button({ className: 'btn primary', disabled: !canSend, onClick: send }, h(Icon, { name: 'send' }), 'إرسال')));

  const items = [];
  r.messages.forEach(function (m) {
    if (newOnes[0] && m.id === newOnes[0].id) items.push(li({ key: 'newdiv', className: 'newdiv' }, 'رسائل جديدة'));
    if (m.from === 'system') { items.push(li({ key: m.id, className: 'bubble system' }, m.text + ' · ' + fmtDT(m.at))); return; }
    const fresh = isNew(m);
    items.push(li({ key: m.id, className: 'bubble ' + m.from + (m.from === role ? ' own' : '') + (observer && m.from === 'manager' ? ' obs' : '') + (fresh ? ' fresh' : '') },
      div({ className: 'bhead' }, fresh ? span({ className: 'rdot', role: 'img', 'aria-label': 'رسالة جديدة' }) : null, strong(null, senderName(r, m)), span(null, fmtDT(m.at))),
      m.text ? div(null, m.text) : null,
      m.files.length ? div({ className: 'files' }, m.files.map(function (f, i) { return h(FileChip, { key: f.name + i, f: f }); })) : null));
  });

  return section({ className: 'panel' },
    div({ className: 'chathead' }, div({ className: 'hrow' }, h3(null, 'المراسلات'), h(Badge, { n: newOnes.length })), span({ className: 'muted small' }, chatCount(r) + ' رسالة')),
    observer ? div({ className: 'note', style: { marginBottom: 12 } }, 'وضع المراقبة: ترى كل المراسلات والمرفقات بالتسلسل الزمني، ويمكنك إضافة ملاحظة عند الحاجة.') : null,
    r.messages.length
      ? ul({ className: 'msgs', ref: listRef, 'aria-live': 'polite' }, items)
      : div({ className: 'note' }, 'لا توجد رسائل بعد.'),
    footerNode);
}

function Tracking(props) {
  const r = props.req, role = props.role;
  const [panel, setPanel] = useState('path');
  const narrow = useNarrow();
  const chatVisible = !narrow || panel === 'chat';
  const [baseline] = useState(props.seenAt);
  useEffect(function () { if (chatVisible) props.onSeen(); }, [chatVisible, r.messages.length]);
  const writable = r.stage === 3;
  const goChat = function () { setPanel('chat'); };
  const advance = function () { const toDialogue = r.stage === 2; props.onAdvance(); if (toDialogue) setPanel('chat'); };
  const st = statusOf(r, role);
  const late = isLate(r);
  const allFiles = r.statement ? [{ name: r.statement.name, size: r.statement.size, url: r.statement.url, by: r.supplier, at: r.created }] : [];
  r.messages.forEach(function (m) { m.files.forEach(function (f) { allFiles.push({ name: f.name, size: f.size, url: f.url, by: senderName(r, m), at: m.at }); }); });
  return div({ className: 'stack' },
    div({ className: 'thead' },
      button({ className: 'btn ghost tback', 'aria-label': 'رجوع', onClick: props.onBack }, h(Icon, { name: 'back' }), span({ className: 'tbacktxt' }, 'رجوع')),
      div({ className: 'tmain' },
        div({ className: 'ttitle' }, span({ className: 'mono big' }, r.id), h(StatusPill, { st: st }), late ? h(LateChip) : null),
        div({ className: 'muted' }, r.supplier + ' · ' + r.period)),
      div({ className: 'tdue' + (late ? ' late' : '') }, dueText(r))),
    div({ className: 'mtabs', role: 'tablist' },
      button({ role: 'tab', 'aria-selected': panel === 'path', onClick: function () { setPanel('path'); } }, 'مسار الطلب'),
      button({ role: 'tab', 'aria-selected': panel === 'chat', onClick: function () { setPanel('chat'); } }, 'المراسلات (' + chatCount(r) + ')', props.unread ? h(Badge, { n: props.unread }) : (writable ? span({ className: 'tabdot', 'aria-hidden': 'true' }) : null))),
    div({ className: 'grid-track' },
      div({ className: 'col', 'data-on': panel === 'path' },
        section({ className: 'panel' }, h3(null, 'مسار الطلب'), h(Stepper, { req: r, stages: STAGES, adv: ADVANCE, canAct: role === 'matcher', onAdvance: advance, onChat: writable ? goChat : undefined })),
        section({ className: 'panel' }, h3(null, 'تفاصيل الطلب'),
          dl({ className: 'dl' },
            dt(null, 'المورد'), dd(null, r.supplier),
            dt(null, 'الفترة'), dd(null, r.period),
            dt(null, 'تاريخ التقديم'), dd(null, fmtDT(r.created)),
            dt(null, 'الموعد المستهدف'), dd(null, fmtDate(r.due)),
            dt(null, 'المطابق'), dd(null, r.matcher || 'لم يُوزَّع بعد'),
            dt(null, 'الفرق المبدئي'), dd(null, sar(r.diff)),
            r.notes ? dt(null, 'ملاحظات المورد') : null, r.notes ? dd(null, r.notes) : null),
          ul({ className: 'filelist', 'aria-label': 'المرفقات' }, allFiles.map(function (f, i) {
            return li({ key: f.name + i }, h(Icon, { name: 'file', size: 16 }), span({ className: 'fn', dir: 'auto' }, f.url ? h('a', { href: f.url, target: '_blank', rel: 'noopener' }, f.name) : f.name), span({ className: 'fm' }, f.by + ' · ' + fmtSize(f.size)));
          })))),
      div({ className: 'col', 'data-on': panel === 'chat' },
        h(Chat, { req: r, role: role, observer: role === 'manager', baseline: baseline, visible: chatVisible, onSend: props.onSend }))));
}

function ComplaintTracking(props) {
  const c = props.c, role = props.role;
  const [panel, setPanel] = useState('path');
  const narrow = useNarrow();
  const chatVisible = !narrow || panel === 'chat';
  const [baseline] = useState(props.seenAt);
  useEffect(function () { if (chatVisible) props.onSeen(); }, [chatVisible, c.messages.length]);
  const writable = c.stage < 3;
  const goChat = function () { setPanel('chat'); };
  const st = statusC(c, role);
  const allFiles = [];
  c.messages.forEach(function (m) { m.files.forEach(function (f) { allFiles.push({ name: f.name, size: f.size, url: f.url, by: senderName(c, m) }); }); });
  return div({ className: 'stack' },
    div({ className: 'thead' },
      button({ className: 'btn ghost tback', 'aria-label': 'رجوع', onClick: props.onBack }, h(Icon, { name: 'back' }), span({ className: 'tbacktxt' }, 'رجوع')),
      div({ className: 'tmain' },
        div({ className: 'ttitle' }, span({ className: 'mono big' }, c.id), h(StatusPill, { st: st })),
        div({ className: 'muted' }, c.supplier + ' · ' + c.subject)),
      div({ className: 'tdue' }, 'وصلت ' + since(c.created))),
    div({ className: 'mtabs', role: 'tablist' },
      button({ role: 'tab', 'aria-selected': panel === 'path', onClick: function () { setPanel('path'); } }, 'مسار الشكوى'),
      button({ role: 'tab', 'aria-selected': panel === 'chat', onClick: function () { setPanel('chat'); } }, 'المراسلات (' + chatCount(c) + ')', props.unread ? h(Badge, { n: props.unread }) : (writable ? span({ className: 'tabdot', 'aria-hidden': 'true' }) : null))),
    div({ className: 'grid-track' },
      div({ className: 'col', 'data-on': panel === 'path' },
        section({ className: 'panel' }, h3(null, 'مسار الشكوى'), h(Stepper, { req: c, stages: C_STAGES, adv: C_ADV, canAct: role === 'manager', onAdvance: props.onAdvance, onChat: writable ? goChat : undefined })),
        section({ className: 'panel' }, h3(null, 'تفاصيل الشكوى'),
          dl({ className: 'dl' },
            dt(null, 'المورد'), dd(null, c.supplier),
            dt(null, 'نوع الشكوى'), dd(null, c.category),
            dt(null, 'العنوان'), dd(null, c.subject),
            dt(null, 'تاريخ التقديم'), dd(null, fmtDT(c.created)),
            dt(null, 'طلب المطابقة المرتبط'), dd(null, c.related ? span({ className: 'mono' }, c.related) : 'غير مرتبطة بطلب')),
          allFiles.length ? ul({ className: 'filelist', 'aria-label': 'المرفقات' }, allFiles.map(function (f, i) {
            return li({ key: f.name + i }, h(Icon, { name: 'file', size: 16 }), span({ className: 'fn', dir: 'auto' }, f.url ? h('a', { href: f.url, target: '_blank', rel: 'noopener' }, f.name) : f.name), span({ className: 'fm' }, f.by + ' · ' + fmtSize(f.size)));
          })) : null)),
      div({ className: 'col', 'data-on': panel === 'chat' },
        h(Chat, { req: c, role: role, observer: false, baseline: baseline, visible: chatVisible, mode: c.stage === 3 ? 'closed' : 'open', closedNote: 'أُغلقت الشكوى بعد رد المدير المالي. السجل محفوظ للمراجعة.', onSend: props.onSend }))));
}
