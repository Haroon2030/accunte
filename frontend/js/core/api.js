'use strict';

/* =====================================================================
   API client. Same origin as the page: the session cookie authenticates
   and Django checks the CSRF token we echo back in X-CSRFToken.
   ===================================================================== */
const API = (function () {
  let onUnauthorized = function () {};

  function csrf() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  function apiError(status, message, data) {
    const e = new Error(message);
    e.status = status; e.data = data || null;
    return e;
  }
  /* files: { fieldName: File | File[] } turns the call into multipart/form-data */
  function call(method, url, payload, files) {
    const opts = { method: method, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf(), Accept: 'application/json' } };
    if (files) {
      const fd = new FormData();
      Object.keys(payload || {}).forEach(function (k) { if (payload[k] != null) fd.append(k, payload[k]); });
      Object.keys(files).forEach(function (k) {
        [].concat(files[k] || []).forEach(function (f) { fd.append(k, f, f.name); });
      });
      opts.body = fd;
    } else if (method !== 'GET' && payload !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(payload);
    }
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok) {
          if (res.status === 401 && url.indexOf('/api/auth/') !== 0) onUnauthorized();
          throw apiError(res.status, (data && data.error) || 'حدث خطأ غير متوقع. حاول مرة أخرى.', data);
        }
        return data;
      });
    }, function () {
      throw apiError(0, 'تعذّر الاتصال بالخادم. تحقق من الاتصال وأعد المحاولة.');
    });
  }

  return {
    get: function (url) { return call('GET', url); },
    post: function (url, payload) { return call('POST', url, payload || {}); },
    upload: function (url, payload, files) { return call('POST', url, payload, files); },
    setUnauthorizedHandler: function (fn) { onUnauthorized = fn; },
    attachmentUrl: function (id) { return '/api/attachments/' + id + '/'; }
  };
})();

/* ---------- server JSON -> the shapes the pages already use (ISO strings become Dates) ---------- */
const toDate = function (s) { return s ? new Date(s) : null; };
const fromMsg = function (m) { return Object.assign({}, m, { at: new Date(m.at) }); };
const fromReq = function (r) {
  return Object.assign({}, r, { created: toDate(r.created), due: toDate(r.due), reached: r.reached.map(toDate), messages: r.messages.map(fromMsg) });
};
const fromComplaint = function (c) {
  return Object.assign({}, c, { created: toDate(c.created), reached: c.reached.map(toDate), messages: c.messages.map(fromMsg) });
};
const fromUser = function (u) { return Object.assign({}, u, { last: toDate(u.last), created: toDate(u.created) }); };
