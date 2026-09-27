(() => {
  'use strict';
  // /home and /compute both serve this page; the route (or ?track=) marks the matching card.
  const compute = location.pathname.replace(/\/$/, '') === '/compute' || new URLSearchParams(location.search).get('track') === 'compute';
  document.title = compute ? 'Base Super Local AI' : 'Base Ready';
  document.getElementById(compute ? 'compute-card' : 'home-card').classList.add('is-route');
})();
