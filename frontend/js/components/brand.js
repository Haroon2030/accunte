'use strict';

/* ---------- app shell ---------- */
function Brand() {
  return div({ className: 'brand' },
    h('svg', { width: 26, height: 26, viewBox: '0 0 26 26', fill: 'none', 'aria-hidden': 'true' },
      h('rect', { x: 2, y: 4, width: 14, height: 16, rx: 3, stroke: 'currentColor', strokeWidth: 2 }),
      h('rect', { x: 10, y: 8, width: 14, height: 16, rx: 3, fill: 'currentColor', fillOpacity: .22, stroke: 'currentColor', strokeWidth: 2 })),
    span(null, 'مطابقة الموردين'));
}
