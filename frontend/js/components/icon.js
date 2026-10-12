'use strict';

function Icon(props) {
  const s = props.size || 18;
  return h('svg', { className: 'ic', width: s, height: s, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true' }, h('path', { d: PATHS[props.name] }));
}
