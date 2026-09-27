/* Cloudflare Turnstile: one invisible widget that proves "a person is here" to /api/read-photo and /api/tts.
   window.BaseHuman.token() -> Promise<string>: a fresh single-use token per call, or '' on any error or after 5 s.
   Visitors see nothing unless Cloudflare asks for interaction (appearance 'interaction-only'). */
(() => {
  const SITEKEY = '0x4AAAAAAFFbC0ZsOxHPltho';
  const SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
  const TIMEOUT = 5000;
  let ready = null, widget = null, pending = null;

  function load() {
    if (ready) return ready;
    ready = new Promise((resolve, reject) => {
      if (window.turnstile) return resolve(window.turnstile);
      const s = document.createElement('script');
      s.src = SRC; s.async = true;
      s.onload = () => window.turnstile ? resolve(window.turnstile) : reject(new Error('no turnstile'));
      s.onerror = () => reject(new Error('turnstile load failed'));
      document.head.appendChild(s);
    }).then(ts => {
      const box = document.createElement('div');
      box.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:9999';
      document.body.appendChild(box);
      widget = ts.render(box, {
        sitekey: SITEKEY, appearance: 'interaction-only', execution: 'execute',
        callback: t => { const p = pending; pending = null; if (p) p(t); },
        'error-callback': () => { const p = pending; pending = null; if (p) p(''); },
        'expired-callback': () => {}
      });
      return ts;
    });
    ready.catch(() => { ready = null; });
    return ready;
  }

  // Local pages (dev, tests) never load Cloudflare; the local servers do not check tokens.
  const LOCAL = /^(localhost|127\.0\.0\.1)$/.test(location.hostname);

  function token() {
    if (LOCAL) return Promise.resolve('');
    return new Promise(resolve => {
      let done = false;
      const finish = t => { if (!done) { done = true; clearTimeout(timer); resolve(t || ''); } };
      const timer = setTimeout(() => { if (pending === finish) pending = null; finish(''); }, TIMEOUT);
      load().then(ts => {
        if (done) return;
        if (pending) pending('');          // one request in flight at a time; the older caller gets ''
        pending = finish;
        ts.reset(widget);                   // tokens are single-use
        ts.execute(widget);
      }).catch(() => finish(''));
    });
  }

  window.BaseHuman = { token };
})();
