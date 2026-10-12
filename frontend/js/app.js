'use strict';

/* =====================================================================
   App: holds the session, loads everything from the API after login and keeps it fresh
   (refresh every 20 s). Every action goes to the server, which decides who may do what.
   ===================================================================== */
const REFRESH_MS = 20000;

function App() {
  const [phase, setPhase] = useState('loading');            // loading | login | ready
  const [user, setUser] = useState(null);
  const [users, setUsers] = useState([]);
  const [reqs, setReqs] = useState([]);
  const [complaints, setComplaints] = useState([]);
  const [seen, setSeen] = useState({});
  const [role, setRole] = useState('supplier');
  const [view, setView] = useState({ name: 'home' });
  const [service, setService] = useState('recon');
  const [toast, setToast] = useState('');
  const working = useRef(false);

  useEffect(function () {
    if (!toast) return undefined;
    const t = setTimeout(function () { setToast(''); }, 4200);
    return function () { clearTimeout(t); };
  }, [toast]);

  const goTop = function () { try { window.scrollTo(0, 0); } catch (e) { /* ignore */ } };
  const home = function () { setView({ name: 'home' }); goTop(); };

  function applyBoot(d) {
    setUser(fromUser(d.user));
    setReqs(d.requests.map(fromReq));
    setComplaints(d.complaints.map(fromComplaint));
    setSeen(d.seen || {});
    setUsers((d.users || []).map(fromUser));
  }
  function enter(u) {
    return API.get('/api/bootstrap/').then(function (d) {
      applyBoot(d);
      setRole(HOME_PAGE[u.role]); setView({ name: 'home' }); setPhase('ready'); goTop();
      setToast('أهلاً ' + u.name + '.');
    }, function (ex) { setPhase('login'); setToast(ex.message); });
  }

  /* resume an existing session on page load */
  useEffect(function () {
    API.get('/api/auth/me/').then(function (d) {
      if (d.user && !d.user.mustChange && (d.user.role === 'supplier') === (PORTAL === 'supplier')) {
        enter(d.user).then(function () { setToast(''); });
      } else { setPhase('login'); }
    }, function () { setPhase('login'); });
    API.setUnauthorizedHandler(function () { setPhase('login'); setUser(null); setToast('انتهت الجلسة. سجّل الدخول من جديد.'); });
  }, []);

  /* periodic refresh: new messages, new requests, stage changes made by other users */
  useEffect(function () {
    if (phase !== 'ready') return undefined;
    const t = setInterval(function () {
      if (document.hidden || working.current) return;
      API.get('/api/bootstrap/').then(applyBoot, function () { /* keep the screen; the next tick retries */ });
    }, REFRESH_MS);
    return function () { clearInterval(t); };
  }, [phase]);

  /* run a server action: one at a time, errors shown as a toast */
  function act(fn) {
    if (working.current) return Promise.resolve(null);
    working.current = true;
    return fn().then(function (r) { working.current = false; return r; }, function (ex) {
      working.current = false; setToast(ex.message); return null;
    });
  }
  const replaceReq = function (r) { const n = fromReq(r); setReqs(function (rs) { return rs.some(function (x) { return x.id === n.id; }) ? rs.map(function (x) { return x.id === n.id ? n : x; }) : [n].concat(rs); }); return n; };
  const replaceC = function (c) { const n = fromComplaint(c); setComplaints(function (cs) { return cs.some(function (x) { return x.id === n.id; }) ? cs.map(function (x) { return x.id === n.id ? n : x; }) : [n].concat(cs); }); return n; };

  const mySupplier = user && user.role === 'supplier' ? user.org : '';
  const openReq = function (id) { setService('recon'); setView({ name: 'track', id: id }); goTop(); };
  const openC = function (id) { setService('complaint'); setView({ name: 'trackc', id: id }); goTop(); };
  function markSeen(id, who) {
    const key = id + ':' + who;
    setSeen(function (s) { const o = Object.assign({}, s); o[key] = Date.now(); return o; });
    API.post('/api/seen/', { key: key }).then(null, function () { /* not critical */ });
  }

  function advance(id) { return act(function () { return API.post('/api/requests/' + id + '/advance/'); }).then(function (d) { if (d) replaceReq(d.request); }); }
  function send(id, m) {
    return act(function () { return API.upload('/api/requests/' + id + '/messages/', { text: m.text, from: m.from }, { files: m.files }); })
      .then(function (d) { if (d) replaceReq(d.request); });
  }
  function create(data) {
    return act(function () { return API.upload('/api/requests/', { period: data.period, notes: data.notes }, { file: data.file }); }).then(function (d) {
      if (!d) return;
      const r = replaceReq(d.request);
      setToast('وصل طلبك برقم ' + r.id + '، وأصبح بانتظار التوزيع.');
      openReq(r.id);
    });
  }
  function advanceC(id) { return act(function () { return API.post('/api/complaints/' + id + '/advance/'); }).then(function (d) { if (d) replaceC(d.complaint); }); }
  function sendC(id, m) {
    return act(function () { return API.upload('/api/complaints/' + id + '/messages/', { text: m.text, from: m.from }, { files: m.files }); })
      .then(function (d) { if (d) replaceC(d.complaint); });
  }
  function createC(data) {
    return act(function () { return API.upload('/api/complaints/', { category: data.category, subject: data.subject, body: data.body, related: data.related || '' }, { files: data.files }); })
      .then(function (d) {
        if (!d) return;
        const c = replaceC(d.complaint);
        setToast('وصلت شكواك إلى المدير المالي برقم ' + c.id + '.');
        openC(c.id);
      });
  }

  const allowed = user ? ROLE_PAGES[user.role] : [];
  function changeRole(r) { if (allowed.indexOf(r) === -1) return; setRole(r); home(); }
  function logout() {
    API.post('/api/auth/logout/').then(null, function () { /* leave anyway */ });
    setUser(null); setReqs([]); setComplaints([]); setUsers([]); setSeen({}); setView({ name: 'home' }); setToast(''); setPhase('login'); goTop();
  }

  /* admin: users (server validates, hashes passwords and enforces who may do what) */
  function saveUser(d) {
    const path = d.id ? '/api/users/' + d.id + '/' : '/api/users/';
    return act(function () { return API.post(path, d); }).then(function (r) {
      if (!r) return false;
      const u = fromUser(r.user);
      setUsers(function (us) { return us.some(function (x) { return x.id === u.id; }) ? us.map(function (x) { return x.id === u.id ? u : x; }) : [u].concat(us); });
      setToast(d.id ? 'حُفظت تعديلات ' + u.name + '.' : 'أُضيف المستخدم ' + u.name + '. سلّمه اسم المستخدم وكلمة المرور المؤقتة.');
      return true;
    });
  }
  function toggleUser(id) {
    return act(function () { return API.post('/api/users/' + id + '/toggle/'); }).then(function (r) {
      if (!r) return;
      const u = fromUser(r.user);
      setUsers(function (us) { return us.map(function (x) { return x.id === u.id ? u : x; }); });
      setToast(u.active ? 'فُعّل حساب ' + u.name + '.' : 'أُوقف حساب ' + u.name + '.');
    });
  }
  function resetUser(id) {
    return act(function () { return API.post('/api/users/' + id + '/reset-password/'); }).then(function (r) {
      if (!r) return null;
      const u = fromUser(r.user);
      setUsers(function (us) { return us.map(function (x) { return x.id === u.id ? u : x; }); });
      return r.password;
    });
  }

  const roleUnread = user ? {
    supplier: unreadSum(reqs, 'supplier', seen) + unreadSum(complaints, 'supplier', seen),
    matcher: unreadSum(reqs.filter(function (r) { return r.matcher === user.name; }), 'matcher', seen),
    manager: unreadSum(complaints, 'manager', seen)
  } : {};

  if (phase === 'loading') return div({ className: 'loginwrap' }, div({ className: 'logincard' }, h(Brand), p({ className: 'sub', role: 'status' }, 'جارٍ التحميل...')));
  if (phase === 'login' || !user) {
    return div(null, h(Login, { onAuthed: function (u) { enter(u); } }), toast ? div({ className: 'toast', role: 'status' }, toast) : null);
  }

  let body;
  const current = view.name === 'track' ? reqs.filter(function (r) { return r.id === view.id; })[0] : null;
  const currentC = view.name === 'trackc' ? complaints.filter(function (c) { return c.id === view.id; })[0] : null;
  if (view.name === 'new' && role === 'supplier') body = h(NewRequest, { onCancel: home, onSubmit: create });
  else if (view.name === 'newc' && role === 'supplier') body = h(NewComplaint, { supplier: mySupplier, reqs: reqs, onCancel: home, onSubmit: createC });
  else if (currentC && (role === 'supplier' || role === 'manager')) body = h(ComplaintTracking, { key: currentC.id + role, c: currentC, role: role, seenAt: seenAt(seen, currentC.id, role), unread: unreadOf(currentC, role, seen), onSeen: function () { markSeen(currentC.id, role); }, onBack: home, onAdvance: function () { advanceC(currentC.id); }, onSend: function (m) { sendC(currentC.id, m); } });
  else if (current) body = h(Tracking, { key: current.id + role, req: current, role: role, seenAt: seenAt(seen, current.id, role), unread: unreadOf(current, role, seen), onSeen: function () { markSeen(current.id, role); }, onBack: home, onAdvance: function () { if (current.stage === 2) setToast('فُتحت المراسلة. اكتب رسالتك للمورد في خانة المراسلات.'); advance(current.id); }, onSend: function (m) { send(current.id, m); } });
  else if (role === 'supplier') body = h(SupplierHome, { supplier: mySupplier, reqs: reqs, complaints: complaints, seen: seen, service: service, onService: setService, onOpen: openReq, onOpenC: openC, onNew: function () { setView({ name: 'new' }); goTop(); }, onNewC: function () { setView({ name: 'newc' }); goTop(); } });
  else if (role === 'users' && allowed.indexOf('users') !== -1) body = h(UsersPage, { users: users, me: user, onSave: saveUser, onToggle: toggleUser, onReset: resetUser, onToast: setToast });
  else if (role === 'recon') body = h(ReconTool, { onToast: setToast });
  else if (role === 'matcher') body = h(MatcherHome, { reqs: reqs, seen: seen, me: user, onOpen: openReq });
  else body = h(Dashboard, { reqs: reqs, complaints: complaints, seen: seen, onOpen: openReq, onOpenC: openC });

  return div(null,
    header({ className: 'topbar' }, div({ className: 'gutter topin' }, h(Brand),
      div({ className: 'topend' },
        allowed.length > 1 ? div({ className: 'seg', role: 'group', 'aria-label': 'صفحات النظام' }, allowed.map(function (k) {
          return button({ key: k, 'aria-pressed': role === k, onClick: function () { changeRole(k); } }, ROLE_NAME[k], h(Badge, { n: roleUnread[k] || 0 }));
        })) : null,
        div({ className: 'uchip' }, span({ className: 'av', 'aria-hidden': 'true' }, user.name.charAt(0)), div({ className: 'un' }, span(null, user.name), h('small', null, ROLE_LABEL[user.role])),
          button({ type: 'button', onClick: logout }, 'خروج'))))),
    main({ className: 'gutter page' }, div({ className: 'who noprint' }, role === 'recon' ? 'أداة داخلية لفريق المطابقة والمدير المالي، ولا تظهر للمورد' : (role === 'users' ? 'إدارة الحسابات والصلاحيات' : (role === 'supplier' ? user.org + ' · ' + user.name : 'تعرض النظام بصفة ' + ROLE_NAME[role] + ' · ' + user.name))), body),
    toast ? div({ className: 'toast', role: 'status' }, toast) : null);
}
