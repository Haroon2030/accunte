'use strict';

function PwInput(props) {
  const [show, setShow] = useState(false);
  return div({ className: 'pwrow' },
    input({ id: props.id, type: show ? 'text' : 'password', className: 'ltr', value: props.value, autoComplete: props.autoComplete || 'off', placeholder: props.placeholder, onChange: function (e) { props.onChange(e.target.value); } }),
    button({ type: 'button', className: 'eye', 'aria-label': show ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور', onClick: function () { setShow(!show); } }, h(Icon, { name: show ? 'eyeoff' : 'eye', size: 18 })));
}

/* Login talks to the backend: the server checks credentials, locks the account after repeated failures,
   keeps portals apart (suppliers vs staff) and forces a new password after a temporary one. */
function Login(props) {
  const [u, setU] = useState('');
  const [pw, setPw] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [lock, setLock] = useState(0);
  const [tick, setTick] = useState(Date.now());
  const [pending, setPending] = useState(null);   // a user who must pick a new password before entering
  const [np, setNp] = useState('');
  const [np2, setNp2] = useState('');
  useEffect(function () {
    if (!lock) return undefined;
    const t = setInterval(function () { setTick(Date.now()); }, 500);
    return function () { clearInterval(t); };
  }, [lock]);
  const left = lock ? Math.max(0, Math.ceil((lock - tick) / 1000)) : 0;
  useEffect(function () { if (lock && left === 0) { setLock(0); setErr(''); } }, [left, lock]);

  function submit(e) {
    e.preventDefault();
    if (left > 0 || busy) return;
    const name = normUser(u);
    if (!name || !pw) { setErr('أدخل اسم المستخدم وكلمة المرور.'); return; }
    setBusy(true); setErr('');
    API.post('/api/auth/login/', { username: name, password: pw, portal: PORTAL }).then(function (d) {
      setBusy(false);
      if (d.user.mustChange) { setPending(d.user); return; }
      props.onAuthed(d.user);
    }, function (ex) {
      setBusy(false);
      if (ex.status === 429 && ex.data && ex.data.retryAfter) { setLock(Date.now() + ex.data.retryAfter * 1000); setTick(Date.now()); }
      setErr(ex.message);
    });
  }
  function change(e) {
    e.preventDefault();
    if (busy) return;
    const m = passErr(np);
    if (m) { setErr(m); return; }
    if (np === pw) { setErr('اختر كلمة مرور مختلفة عن المؤقتة.'); return; }
    if (np !== np2) { setErr('تأكيد كلمة المرور غير مطابق.'); return; }
    setBusy(true); setErr('');
    API.post('/api/auth/change-password/', { oldPassword: pw, newPassword: np }).then(function (d) {
      setBusy(false); props.onAuthed(d.user);
    }, function (ex) { setBusy(false); setErr(ex.message); });
  }
  return div({ className: 'loginwrap' },
    div({ className: 'logincard' },
      h(Brand),
      pending
        ? form({ onSubmit: change, noValidate: true },
          h1(null, 'تعيين كلمة مرور جديدة'),
          p({ className: 'sub' }, 'هذه أول مرة تدخل فيها بكلمة مرور مؤقتة، اختر كلمة مرور خاصة بك للمتابعة.'),
          err ? div({ className: 'loginerr', role: 'alert' }, err) : null,
          div({ className: 'field' }, label({ htmlFor: 'np' }, 'كلمة المرور الجديدة'), h(PwInput, { id: 'np', value: np, onChange: setNp, autoComplete: 'new-password' }), span({ className: 'hint' }, '8 خانات على الأقل، حروف إنجليزية وأرقام.')),
          div({ className: 'field' }, label({ htmlFor: 'np2' }, 'تأكيد كلمة المرور'), h(PwInput, { id: 'np2', value: np2, onChange: setNp2, autoComplete: 'new-password' })),
          button({ type: 'submit', className: 'btn primary', style: { width: '100%' }, disabled: busy }, busy ? 'جارٍ الحفظ...' : 'حفظ والدخول'))
        : form({ onSubmit: submit, noValidate: true },
          h1(null, 'تسجيل الدخول'),
          p({ className: 'sub' }, PORTAL === 'supplier' ? 'بوابة الموردين: أدخل بيانات حساب شركتك' : 'أدخل بيانات حسابك للوصول إلى النظام'),
          err ? div({ className: 'loginerr', role: 'alert' }, err, left > 0 ? ' (' + left + ' ث)' : '') : null,
          div({ className: 'field' }, label({ htmlFor: 'lg-u' }, 'اسم المستخدم'),
            input({ id: 'lg-u', type: 'text', className: 'ltr', autoComplete: 'username', autoCapitalize: 'none', spellCheck: false, value: u, onChange: function (e) { setU(e.target.value); } })),
          div({ className: 'field' }, label({ htmlFor: 'lg-p' }, 'كلمة المرور'), h(PwInput, { id: 'lg-p', value: pw, onChange: setPw, autoComplete: 'current-password' })),
          button({ type: 'submit', className: 'btn primary', style: { width: '100%' }, disabled: left > 0 || busy }, busy ? 'جارٍ الدخول...' : 'دخول'))));
}
