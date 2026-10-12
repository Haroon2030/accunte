'use strict';

function App() {
  const [role, setRole] = useState('supplier');
  const [me, setMe] = useState(undefined); // undefined while the session is checked, null when signed out
  const [users, setUsers] = useState([]);
  const [reqs, setReqs] = useState([]);
  const [view, setView] = useState({ name: 'home' });
  const [complaints, setComplaints] = useState([]);
  const [service, setService] = useState('recon');
  const [seen, setSeen] = useState({});
  const [toast, setToast] = useState('');
  useEffect(function () {
    if (!toast) return undefined;
    const t = setTimeout(function () { setToast(''); }, 4200);
    return function () { clearTimeout(t); };
  }, [toast]);

  const mySupplier = me && me.role === 'supplier' ? me.org : '';
  const goTop = function () { try { window.scrollTo(0, 0); } catch (e) { /* ignore */ } };
  const openReq = function (id) { setService('recon'); setView({ name: 'track', id: id }); goTop(); };
  const home = function () { setView({ name: 'home' }); goTop(); };
  const markSeen = function (id, who) { setSeen(function (s) { const o = Object.assign({}, s); o[id + ':' + who] = Date.now(); return o; }); };
  const openC = function (id) { setService('complaint'); setView({ name: 'trackc', id: id }); goTop(); };
  const fail = function (e) { setToast(e.message); if (e.status === 401) setMe(null); };

  function loadAll(u) {
    const jobs = [API.get('/requests/').then(function (rs) { setReqs(rs.map(API.request)); })];
    if (u.role !== 'matcher') jobs.push(API.get('/complaints/').then(function (cs) { setComplaints(cs.map(API.complaint)); }));
    if (u.role === 'admin') jobs.push(API.get('/users/').then(function (us) { setUsers(us.map(API.user)); }));
    return Promise.all(jobs);
  }
  function enter(u, welcome) {
    const user = API.user(u);
    setMe(user); setRole(HOME_PAGE[user.role]); setView({ name: 'home' }); goTop();
    if (welcome) setToast('أهلاً ' + user.name + '.');
    loadAll(user).catch(fail);
  }
  useEffect(function () {
    API.get('/auth/me').then(function (d) {
      if (d.user && !d.user.mustChange) enter(d.user, false);
      else setMe(null);
    }).catch(function () { setMe(null); });
  }, []);
  useEffect(function () {
    if (!me) return undefined;
    const t = setInterval(function () { loadAll(me).catch(function () { /* keep showing the last data */ }); }, 20000);
    return function () { clearInterval(t); };
  }, [me]);

  const replaceReq = function (r) { setReqs(function (rs) { return rs.map(function (x) { return x.pk === r.pk ? r : x; }); }); };
  const replaceC = function (c) { setComplaints(function (cs) { return cs.map(function (x) { return x.pk === c.pk ? c : x; }); }); };
  const reqOf = function (id) { return reqs.filter(function (r) { return r.id === id; })[0]; };
  const compOf = function (id) { return complaints.filter(function (c) { return c.id === id; })[0]; };

  function advance(id) {
    const r = reqOf(id);
    if (r) API.post('/requests/' + r.pk + '/advance').then(function (d) { replaceReq(API.request(d)); }).catch(fail);
  }
  function send(id, m) {
    const r = reqOf(id);
    if (!r) return;
    API.post('/requests/' + r.pk + '/messages', formOf({ text: m.text }, 'files', m.files)).then(function (d) {
      setReqs(function (rs) { return rs.map(function (x) { return x.pk === r.pk ? Object.assign({}, x, { messages: x.messages.concat([API.message(d)]) }) : x; }); });
    }).catch(fail);
  }
  function create(data) {
    API.post('/requests/', formOf({ period: data.period, notes: data.notes }, 'statement', [data.file])).then(function (d) {
      const req = API.request(d);
      setReqs(function (rs) { return [req].concat(rs); });
      setToast('وصل طلبك برقم ' + req.id + '، وأصبح بانتظار التوزيع.');
      openReq(req.id);
    }).catch(fail);
  }
  function advanceC(id) {
    const c = compOf(id);
    if (c) API.post('/complaints/' + c.pk + '/advance').then(function (d) { replaceC(API.complaint(d)); }).catch(fail);
  }
  function sendC(id, m) {
    const c = compOf(id);
    if (!c) return;
    API.post('/complaints/' + c.pk + '/messages', formOf({ text: m.text }, 'files', m.files)).then(function (d) {
      setComplaints(function (cs) { return cs.map(function (x) { return x.pk === c.pk ? Object.assign({}, x, { messages: x.messages.concat([API.message(d)]) }) : x; }); });
    }).catch(fail);
  }
  function createC(data) {
    API.post('/complaints/', formOf({ category: data.category, subject: data.subject, body: data.body, related: data.related }, 'files', data.files)).then(function (d) {
      const c = API.complaint(d);
      setComplaints(function (cs) { return [c].concat(cs); });
      setToast('وصلت شكواك إلى المدير المالي برقم ' + c.id + '.');
      openC(c.id);
    }).catch(fail);
  }
  const user = me || null;
  const allowed = user ? ROLE_PAGES[user.role] : [];
  function changeRole(r) { if (allowed.indexOf(r) === -1) return; setRole(r); home(); }
  function logout() {
    API.post('/auth/logout').catch(function () { /* already signed out */ }).then(function () {
      setMe(null); setReqs([]); setComplaints([]); setUsers([]); setView({ name: 'home' }); setToast(''); goTop();
    });
  }
  function saveUser(d) {
    const body = { name: d.name, username: d.username, role: d.role, org: d.org, code: d.code, taxNo: d.taxNo, active: d.active, password: d.password };
    const call = d.id ? API.patch('/users/' + d.id + '/', body) : API.post('/users/', body);
    return call.then(function (u) {
      const nu = API.user(u);
      setUsers(function (us) { return d.id ? us.map(function (x) { return x.id === nu.id ? nu : x; }) : [nu].concat(us); });
      setToast(d.id ? 'حُفظت تعديلات ' + nu.name + '.' : 'أُضيف المستخدم ' + nu.name + '. سلّمه اسم المستخدم وكلمة المرور المؤقتة.');
    });
  }
  function toggleUser(id) {
    API.post('/users/' + id + '/toggle').then(function (u) {
      const nu = API.user(u);
      setUsers(function (us) { return us.map(function (x) { return x.id === nu.id ? nu : x; }); });
      setToast(nu.active ? 'فُعّل حساب ' + nu.name + '.' : 'أُوقف حساب ' + nu.name + '.');
    }).catch(fail);
  }
  function resetUser(id) {
    return API.post('/users/' + id + '/reset-password').then(function (d) {
      const nu = API.user(d.user);
      setUsers(function (us) { return us.map(function (x) { return x.id === nu.id ? nu : x; }); });
      return d.password;
    });
  }

  const roleUnread = {
    supplier: unreadSum(reqs.filter(function (r) { return r.supplier === mySupplier; }), 'supplier', seen) + unreadSum(complaints.filter(function (c) { return c.supplier === mySupplier; }), 'supplier', seen),
    matcher: unreadSum(reqs.filter(function (r) { return r.matcher === (user && user.name); }), 'matcher', seen),
    manager: unreadSum(complaints, 'manager', seen)
  };

  if (me === undefined) return div({ className: 'loginwrap' }, h(Brand));
  if (!user) return h(Login, { onLogin: function (u) { enter(u, true); } });
  let body;
  const current = view.name === 'track' ? reqs.filter(function (r) { return r.id === view.id; })[0] : null;
  const currentC = view.name === 'trackc' ? complaints.filter(function (c) { return c.id === view.id; })[0] : null;
  if (view.name === 'new' && role === 'supplier') body = h(NewRequest, { onCancel: home, onSubmit: create });
  else if (view.name === 'newc' && role === 'supplier') body = h(NewComplaint, { supplier: mySupplier, reqs: reqs, onCancel: home, onSubmit: createC });
  else if (currentC && (role === 'supplier' || role === 'manager')) body = h(ComplaintTracking, { key: currentC.id + role, c: currentC, role: role, seenAt: seenAt(seen, currentC.id, role), unread: unreadOf(currentC, role, seen), onSeen: function () { markSeen(currentC.id, role); }, onBack: home, onAdvance: function () { advanceC(currentC.id); }, onSend: function (m) { sendC(currentC.id, m); } });
  else if (current) body = h(Tracking, { key: current.id + role, req: current, role: role, seenAt: seenAt(seen, current.id, role), unread: unreadOf(current, role, seen), onSeen: function () { markSeen(current.id, role); }, onBack: home, onAdvance: function () { if (current.stage === 2) setToast('فُتحت المراسلة. اكتب رسالتك للمورد في خانة المراسلات.'); advance(current.id); }, onSend: function (m) { send(current.id, m); } });
  else if (role === 'supplier') body = h(SupplierHome, { supplier: mySupplier, reqs: reqs, complaints: complaints, seen: seen, service: service, onService: setService, onOpen: openReq, onOpenC: openC, onNew: function () { setView({ name: 'new' }); goTop(); }, onNewC: function () { setView({ name: 'newc' }); goTop(); } });
  else if (role === 'users' && allowed.indexOf('users') !== -1) body = h(UsersPage, { users: users, me: user, onSave: saveUser, onToggle: toggleUser, onReset: resetUser, onToast: setToast });
  else if (role === 'recon') body = h(ReconTool, { onToast: setToast, by: user.name });
  else if (role === 'matcher') body = h(MatcherHome, { reqs: reqs, seen: seen, onOpen: openReq });
  else body = h(Dashboard, { reqs: reqs, complaints: complaints, seen: seen, onOpen: openReq, onOpenC: openC });

  return div(null,
    header({ className: 'topbar' }, div({ className: 'gutter topin' }, h(Brand),
      div({ className: 'topend' },
        allowed.length > 1 ? div({ className: 'seg', role: 'group', 'aria-label': 'صفحات النظام' }, allowed.map(function (k) {
          return button({ key: k, 'aria-pressed': role === k, onClick: function () { changeRole(k); } }, ROLE_NAME[k], h(Badge, { n: roleUnread[k] || 0 }));
        })) : null,
        div({ className: 'uchip' }, span({ className: 'av ' + user.role, 'aria-hidden': 'true' }, user.name.charAt(0)), div({ className: 'un' }, span(null, user.name), h('small', null, ROLE_LABEL[user.role])),
          button({ type: 'button', onClick: logout }, 'خروج'))))),
    main({ className: 'gutter page' }, div({ className: 'who noprint' }, role === 'recon' ? 'أداة داخلية لفريق المطابقة والمدير المالي، ولا تظهر للمورد' : (role === 'users' ? 'إدارة الحسابات والصلاحيات' : (role === 'supplier' ? user.org + ' · ' + user.name : 'تعرض النظام بصفة ' + ROLE_NAME[role] + ' · ' + (user.role === role ? user.name : ME[role])))), body),
    toast ? div({ className: 'toast', role: 'status' }, toast) : null);
}
