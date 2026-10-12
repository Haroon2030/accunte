'use strict';

/* Talks to the Django backend (same origin). Session cookie + CSRF header, JSON or multipart. */
const API = (function () {
  function csrf() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  function messageOf(data) {
    if (!data) return '';
    if (Array.isArray(data)) return typeof data[0] === 'string' ? data[0] : '';
    if (typeof data.detail === 'string') return data.detail;
    const k = Object.keys(data)[0];
    const v = k ? data[k] : '';
    return Array.isArray(v) ? v[0] : (typeof v === 'string' ? v : '');
  }
  function call(method, path, body) {
    const opt = { method: method, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() } };
    if (typeof FormData !== 'undefined' && body instanceof FormData) opt.body = body;
    else if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch('/api' + path, opt).then(function (r) {
      return r.text().then(function (t) {
        let data = null;
        try { data = t ? JSON.parse(t) : null; } catch (e) { data = null; }
        if (!r.ok) {
          const err = new Error(messageOf(data) || (r.status === 401 || r.status === 403 ? 'انتهت الجلسة، سجّل الدخول من جديد.' : 'تعذّر إتمام العملية، حاول مرة أخرى.'));
          err.status = r.status; err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  const D = function (s) { return s ? new Date(s) : null; };
  const stages = function (o) { const a = []; Object.keys(o || {}).forEach(function (k) { a[+k] = D(o[k]); }); return a; };
  const msg = function (m) { return Object.assign({}, m, { at: D(m.at) }); };

  return {
    get: function (p) { return call('GET', p); },
    post: function (p, b) { return call('POST', p, b); },
    patch: function (p, b) { return call('PATCH', p, b); },
    user: function (u) { return Object.assign({}, u, { last: D(u.last), created: D(u.created) }); },
    request: function (r) { return Object.assign({}, r, { created: D(r.created), due: D(r.due), reached: stages(r.reached), messages: (r.messages || []).map(msg) }); },
    complaint: function (c) { return Object.assign({}, c, { created: D(c.created), reached: stages(c.reached), messages: (c.messages || []).map(msg) }); },
    message: msg
  };
}());

/* multipart body from plain fields + File objects picked in the UI (entries look like {name, size, file}) */
function formOf(fields, fileField, picked) {
  const fd = new FormData();
  Object.keys(fields).forEach(function (k) { if (fields[k] != null && fields[k] !== '') fd.append(k, fields[k]); });
  (picked || []).forEach(function (p) { if (p.file) fd.append(fileField, p.file, p.name); });
  return fd;
}
