'use strict';

const h = React.createElement;
const { useState, useRef, useEffect } = React;

/* ---------- tiny element helpers (no build step: plain createElement) ---------- */
const T = {};
['div', 'span', 'button', 'section', 'header', 'main', 'footer', 'p', 'h1', 'h2', 'h3', 'h4', 'ul', 'ol', 'li',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'label', 'input', 'select', 'option', 'textarea', 'form',
  'strong', 'dl', 'dt', 'dd'].forEach(function (t) { T[t] = function (props) { return h.apply(null, [t, props].concat([].slice.call(arguments, 1))); }; });
const { div, span, button, section, header, main, footer, p, h1, h2, h3, h4, ul, ol, li, table, thead, tbody, tr, th, td,
  label, input, select, option, textarea, form, strong, dl, dt, dd } = T;

const PATHS = {
  plus: 'M12 5v14M5 12h14',
  clip: 'M21 12.5l-8.5 8.5a5.5 5.5 0 01-7.8-7.8l9-9a3.7 3.7 0 015.2 5.2l-9 9a1.8 1.8 0 01-2.6-2.6l8.3-8.3',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4.5 20a7.5 7.5 0 0115 0',
  pencil: 'M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4',
  key: 'M15 8.5a4.5 4.5 0 11-1.6 3.4L4 21v-3h2.5v-2.5H9V13l4.4-4.4A4.5 4.5 0 0115 8.5zM17 8h.01',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6',
  ban: 'M12 3a9 9 0 100 18 9 9 0 000-18zM5.7 5.7l12.6 12.6',
  back: 'M9 6l6 6-6 6',
  chevL: 'M15 6l-6 6 6 6',
  file: 'M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5zM14 3v5h5',
  close: 'M6 6l12 12M18 6L6 18',
  alert: 'M12 8v5M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  chat: 'M21 12a8 8 0 01-11.6 7.1L4 20l1.1-4.7A8 8 0 1121 12z',
  search: 'M11 18a7 7 0 100-14 7 7 0 000 14zM21 21l-4.3-4.3',
  sort: 'M8 9l4-4 4 4M8 15l4 4 4-4',
  up: 'M6 15l6-6 6 6',
  down: 'M6 9l6 6 6-6',
  upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
  download: 'M12 4v12M7 11l5 5 5-5M4 20h16',
  eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z',
  eyeoff: 'M3 3l18 18M10.6 6.1A10 10 0 0112 5c6.5 0 10 7 10 7a17 17 0 01-3.2 4M6.5 6.9C3.8 8.7 2 12 2 12s3.5 7 10 7c1.6 0 3-.4 4.3-1M9.9 9.9a3 3 0 004.2 4.2',
  print: 'M7 9V3h10v6M7 17H5a2 2 0 01-2-2v-4a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2h-2M7 14h10v7H7z'
};
