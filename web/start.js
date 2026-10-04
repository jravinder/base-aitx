(() => {
  'use strict';
  // /home and /compute both serve this page; the route (or ?track=) only sets the tab title.
  const compute = location.pathname.replace(/\/$/, '') === '/compute' || new URLSearchParams(location.search).get('track') === 'compute';
  document.title = compute ? 'Base Super Local AI' : 'Base Ready';
})();
