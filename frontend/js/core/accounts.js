'use strict';

/* =====================================================================
   Accounts: roles, page access, small helpers. Accounts, passwords and
   permissions live in the backend (Django); nothing sensitive is kept here.
   ===================================================================== */
const ROLE_LABEL = { supplier: 'مورد', matcher: 'مطابق', manager: 'مدير مالي', admin: 'مدير النظام' };
const ROLE_PAGES = {
  supplier: ['supplier'],
  matcher: ['matcher', 'recon'],
  manager: ['matcher', 'manager', 'recon'],
  admin: ['matcher', 'manager', 'recon', 'users']
};
const HOME_PAGE = { supplier: 'supplier', matcher: 'matcher', manager: 'manager', admin: 'users' };
const PAGE_LABEL = { supplier: 'صفحة المورد', matcher: 'صفحة المطابق', manager: 'لوحة المدير المالي', recon: 'مطابقة الكشوف', users: 'إدارة المستخدمين' };
/* two separate entrances: suppliers use /portal/ (supplier.html), staff use / (index.html) */
const PORTAL = document.body.getAttribute('data-portal') || 'staff';

/* temporary password suggestion for the admin form (the server validates every password again) */
function genPass() {
  const sets = ['abcdefghjkmnpqrstuvwxyz', 'ABCDEFGHJKMNPQRSTUVWXYZ', '23456789', '@#$%'];
  const all = sets.join('');
  const rnd = function (n) {
    try { const a = new Uint32Array(1); window.crypto.getRandomValues(a); return a[0] % n; } catch (e) { return Math.floor(Math.random() * n); }
  };
  const out = sets.map(function (s) { return s.charAt(rnd(s.length)); });
  while (out.length < 11) out.push(all.charAt(rnd(all.length)));
  for (let i = out.length - 1; i > 0; i--) { const j = rnd(i + 1); const t = out[i]; out[i] = out[j]; out[j] = t; }
  return out.join('');
}
function passErr(pw) {
  if (!pw || pw.length < 8) return 'كلمة المرور 8 خانات على الأقل.';
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return 'يجب أن تحتوي حروفاً إنجليزية وأرقاماً.';
  return '';
}
const normUser = function (v) { return rcLatin(String(v || '')).trim().toLowerCase(); };
