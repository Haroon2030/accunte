'use strict';

/* ---------- small shared components ---------- */
function StatusPill(props) { return span({ className: 'pill ' + props.st.tone }, span({ className: 'dot' }), props.st.label); }
function LateChip() { return span({ className: 'chip-late' }, 'متأخر'); }
function Badge(props) {
  if (!props.n) return null;
  return span({ className: 'rbadge', role: 'img', 'aria-label': props.n === 1 ? 'رسالة جديدة' : props.n + ' رسائل جديدة' }, props.n);
}
function AlertBar(props) {
  if (!props.n) return null;
  return div({ className: 'alertbar', role: 'status' }, h(Icon, { name: 'alert' }), span(null, props.text), h(Badge, { n: props.n }));
}

function FileChip(props) {
  /* a file already on the server (has an id) downloads through the permission-checked API; a picked File is just shown */
  const label = props.f.id
    ? h('a', { href: API.attachmentUrl(props.f.id), dir: 'auto', download: props.f.name, className: 'filelink' }, props.f.name)
    : span({ dir: 'auto' }, props.f.name);
  return span({ className: 'file' }, h(Icon, { name: 'file', size: 14 }),
    label, span({ className: 'sz' }, h('em', null, fmtSize(props.f.size))),
    props.onRemove ? button({ type: 'button', 'aria-label': 'إزالة ' + props.f.name, onClick: props.onRemove, className: 'rm' }, h(Icon, { name: 'close', size: 14 })) : null);
}
