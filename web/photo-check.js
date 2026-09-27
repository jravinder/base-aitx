/* One photo, checked and read on the member's device.
   1. Take or choose a photo; it stays in this page as an object URL.
   2. Quality check in the browser: resolution, light (mean luma), sharpness (Laplacian variance), framing.
   3. Reading: the PC beside the battery runs the vision model (panel/read.py prompt) at localhost:11434.
      Tried automatically only when this page itself is served from localhost, otherwise on a click.
   4. Confirm sends `home-photo-confirmed` {main_breaker_amps}; onboarding.js saves it and awards the photo milestone. */
(() => {
  'use strict';
  const OLLAMA = 'http://localhost:11434';
  const MODEL = 'gemma4:e4b';
  const PROMPT = `You are a home battery installer reviewing a customer's photo of their electrical service panel.
Return ONLY JSON with these fields:
{"photo_type": "panel_open|panel_closed|meter_exterior|other", "cover_off": bool, "main_breaker_amps": int|null, "bus_rating_amps": int|null, "brand": str|null,
 "free_slots": int|null, "subpanel_visible": bool, "location": "indoor|outdoor|unknown", "gas_meter_within_3ft": bool|null, "clear_space_9ft": bool|null, "issues": [str],
 "pass": bool, "retake_reason": str|null, "confidence": 0-1}
Rules: main_breaker_amps only if you can read the number on the main breaker handle or label. issues = double taps, rust, water, missing knockouts, no label.
pass = true only if a configuration engineer could size the battery from this photo alone. retake_reason tells the customer exactly what to photograph again.`;
  const TYPES = { panel_open: 'Open panel', panel_closed: 'Closed panel', meter_exterior: 'Meter, outside', other: 'Other' };
  // Thresholds, measured on a copy scaled to 512 px on the long side.
  const Q = { minSide: 600, dark: 50, bright: 225, sharp: 120, centre: 0.07, aspectMin: 0.5, aspectMax: 2.1 };
  const TIPS = {
    resolution: 'Small photo: take it with the camera at full size.',
    dark: 'Too dark: turn on a light or open the door.',
    bright: 'Too bright: turn off the flash or block the direct sun.',
    sharpness: 'Blurry: hold still and tap to focus.',
    far: 'Too far: step closer so the label fills a third of the frame.',
    wide: 'Wide shot: take a regular photo, not a panorama or screenshot.'
  };
  // The model sometimes asks for parts behind the cover. Members only photograph the closed panel.
  const SAFE_RETAKE = 'Photograph the label on the outside of the closed panel, close and in good light. Keep doors and covers closed.';
  function safeRetake(text) {
    if (typeof text !== 'string' || !text.trim()) return SAFE_RETAKE;
    return /\b(open|remov|cover|dead ?front|bus|lug|conductor|wire|wiring|inside|interior|breakers? inside)/i.test(text) ? SAFE_RETAKE : text.slice(0, 240);
  }
  const LOCAL_PAGE = /^(localhost|127\.0\.0\.1)$/.test(location.hostname) && !new URLSearchParams(location.search).has('static');

  function node(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = String(text);
    return el;
  }

  // Pure image measures, exported for tests.
  function measure(img) {
    const w = img.naturalWidth, h = img.naturalHeight;
    const scale = Math.min(1, 512 / Math.max(w, h));
    const cw = Math.max(3, Math.round(w * scale)), ch = Math.max(3, Math.round(h * scale));
    const c = document.createElement('canvas'); c.width = cw; c.height = ch;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, cw, ch);
    const px = ctx.getImageData(0, 0, cw, ch).data;
    const g = new Float32Array(cw * ch);
    let sum = 0;
    for (let i = 0, j = 0; j < g.length; i += 4, j++) { g[j] = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]; sum += g[j]; }
    let n = 0, m = 0, m2 = 0, all = 0, mid = 0;
    const x0 = cw / 3, x1 = 2 * cw / 3, y0 = ch / 3, y1 = 2 * ch / 3;
    for (let y = 1; y < ch - 1; y++) for (let x = 1; x < cw - 1; x++) {
      const k = y * cw + x;
      const lap = 4 * g[k] - g[k - 1] - g[k + 1] - g[k - cw] - g[k + cw];
      n++; m += lap; m2 += lap * lap;
      const a = Math.abs(lap); all += a;
      if (x >= x0 && x < x1 && y >= y0 && y < y1) mid += a;
    }
    const mean = m / n;
    return { width: w, height: h, luma: sum / g.length, sharpness: m2 / n - mean * mean, centre: all ? mid / all : 0, aspect: w / h };
  }
  function grade(m) {
    const side = Math.min(m.width, m.height);
    const wide = m.aspect < Q.aspectMin || m.aspect > Q.aspectMax;
    const lightTip = m.luma < Q.dark ? TIPS.dark : m.luma > Q.bright ? TIPS.bright : null;
    const checks = [
      { id: 'resolution', label: 'Size', value: `${m.width} × ${m.height} px`, pass: side >= Q.minSide, tip: TIPS.resolution },
      { id: 'light', label: 'Light', value: `${Math.round(m.luma)} of 255`, pass: !lightTip, tip: lightTip },
      { id: 'sharpness', label: 'Sharpness', value: String(Math.round(m.sharpness)), pass: m.sharpness >= Q.sharp, tip: TIPS.sharpness },
      { id: 'framing', label: 'Framing', value: `${Math.round(m.centre * 100)}% detail in centre`, pass: !wide && m.centre >= Q.centre, tip: wide ? TIPS.wide : TIPS.far }
    ];
    return { checks, pass: checks.every(c => c.pass), tips: checks.filter(c => !c.pass).map(c => c.tip) };
  }

  function mount() {
    const root = document.getElementById('photo-check');
    if (!root || root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    let address = '', url = '', file = null, quality = null, reading = null, readState = 'idle', edit = false, confirmed = false, token = 0, timer = 0;

    const head = node('div', 'pk-head');
    const title = node('h3', 'pk-title', 'Meter and closed panel'); title.id = 'pk-title';
    root.setAttribute('aria-labelledby', title.id);
    head.append(title, node('p', 'pk-sub', 'One clear photo shows Base the mounting space. Keep doors and covers closed.'));
    const input = node('input', 'pk-file'); input.id = 'pk-file'; input.type = 'file';
    input.accept = 'image/*'; input.setAttribute('capture', 'environment');
    const pick = node('label', 'pk-pick'); pick.htmlFor = input.id;
    const pickIcon = node('span', 'material-symbols-outlined', 'photo_camera'); pickIcon.setAttribute('aria-hidden', 'true');
    const pickText = node('span', '', 'Take or choose a photo');
    pick.append(pickIcon, pickText, input);
    const stage = node('div', 'pk-stage'); stage.hidden = true;
    const figure = node('figure', 'pk-preview');
    const img = node('img'); img.alt = 'Your photo';
    const cap = node('figcaption');
    figure.append(img, cap);
    const side = node('div', 'pk-side');
    const qHead = node('p', 'pk-k', 'Quality check');
    const chips = node('ul', 'pk-checks'); chips.setAttribute('aria-label', 'Quality check');
    const tips = node('ul', 'pk-tips');
    const verdict = node('p', 'pk-verdict'); verdict.id = 'pk-verdict';
    side.append(qHead, chips, verdict, tips);
    stage.append(figure, side);
    const read = node('div', 'pk-read'); read.id = 'pk-read'; read.hidden = true;
    read.setAttribute('aria-live', 'polite');
    const actions = node('div', 'pk-actions'); actions.hidden = true;
    const confirmBtn = btn('Confirm', confirm, 'ob-primary pk-confirm'); confirmBtn.id = 'pk-confirm';
    confirmBtn.dataset.reward = 'photo';
    const correctBtn = btn('Correct', () => { edit = true; renderRead(); root.querySelector('.pk-fields input')?.focus(); }, 'ob-btn-2'); correctBtn.id = 'pk-correct';
    const retakeBtn = btn('Retake', () => input.click(), 'ob-btn-2'); retakeBtn.id = 'pk-retake';
    actions.append(confirmBtn, correctBtn, retakeBtn);
    const msg = node('p', 'pk-msg'); msg.setAttribute('role', 'status');
    const note = node('p', 'pk-note', 'Your photo stays on this device. The quality check runs here; the reading runs on the PC beside your battery.');
    root.replaceChildren(head, pick, stage, read, actions, msg, note);

    function btn(text, fn, cls) { const b = node('button', cls, text); b.type = 'button'; b.addEventListener('click', fn); return b; }
    function clear() {
      token++; clearInterval(timer);
      if (url) URL.revokeObjectURL(url);
      url = ''; file = null; quality = null; reading = null; readState = 'idle'; edit = false; confirmed = false;
      img.removeAttribute('src'); input.value = ''; msg.textContent = '';
      render();
    }

    input.addEventListener('change', async () => {
      const f = input.files && input.files[0];
      input.value = '';
      if (!f) return;
      if (!/^image\//.test(f.type) || f.size > 25 * 1024 * 1024) { msg.textContent = 'Choose a photo up to 25 MB.'; return; }
      clear();
      const t = token;
      file = f; url = URL.createObjectURL(f);
      msg.textContent = 'Checking the photo...';
      try {
        const im = new Image(); im.src = url; await im.decode();
        if (t !== token) return;
        img.src = url; cap.textContent = f.name;
        quality = grade(measure(im));
        msg.textContent = '';
      } catch {
        if (t !== token) return;
        URL.revokeObjectURL(url); url = ''; file = null;
        msg.textContent = 'This browser opens JPEG, PNG and WebP photos. Try one of those.';
      }
      render();
      if (quality && LOCAL_PAGE) readOnPC(true);
    });

    async function timed(u, opts, ms) {
      const c = new AbortController(); const t = setTimeout(() => c.abort(), ms);
      try { return await fetch(u, { ...opts, signal: c.signal }); } finally { clearTimeout(t); }
    }
    async function ready() {
      try {
        const r = await timed(`${OLLAMA}/api/tags`, {}, 2500);
        if (!r.ok) return false;
        const d = await r.json();
        return (d.models || []).some(m => m.name === MODEL);
      } catch { return false; }
    }
    function base64(f) {
      return new Promise((resolve, reject) => {
        const im = new Image(), u = URL.createObjectURL(f);
        im.onload = () => {
          const s = Math.min(1, 1024 / Math.max(im.naturalWidth, im.naturalHeight));
          const c = document.createElement('canvas'); c.width = Math.round(im.naturalWidth * s); c.height = Math.round(im.naturalHeight * s);
          c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
          URL.revokeObjectURL(u); resolve(c.toDataURL('image/jpeg', 0.85).split(',')[1]);
        };
        im.onerror = () => { URL.revokeObjectURL(u); reject(new Error('image')); };
        im.src = u;
      });
    }
    function clean(out) {
      if (!out || typeof out !== 'object' || Array.isArray(out)) throw new Error('shape');
      const amps = Number.isInteger(out.main_breaker_amps) && out.main_breaker_amps >= 30 && out.main_breaker_amps <= 600 ? out.main_breaker_amps : null;
      const conf = typeof out.confidence === 'number' ? Math.max(0, Math.min(1, out.confidence)) : null;
      return {
        type: Object.hasOwn(TYPES, out.photo_type) ? out.photo_type : 'other',
        brand: typeof out.brand === 'string' && out.brand.trim() ? out.brand.trim().slice(0, 40) : '',
        amps, confidence: conf, pass: out.pass === true,
        retake: safeRetake(out.retake_reason)
      };
    }
    async function readOnPC(auto) {
      if (!file || readState === 'reading') return;
      const t = token, f = file;
      readState = 'reading'; renderRead();
      const t0 = performance.now();
      clearInterval(timer);
      timer = setInterval(() => { const s = root.querySelector('.pk-elapsed'); if (s) s.textContent = `${Math.round((performance.now() - t0) / 1000)} s`; }, 1000);
      try {
        if (!(await ready())) throw new Error('away');
        const b64 = await base64(f);
        const r = await timed(`${OLLAMA}/api/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: MODEL, stream: false, think: false, format: 'json',
            messages: [{ role: 'user', content: PROMPT, images: [b64] }] }) }, 300000);
        if (!r.ok) throw new Error('read');
        const out = clean(JSON.parse((await r.json()).message.content));
        if (t !== token) return;
        reading = { ...out, secs: Math.round((performance.now() - t0) / 100) / 10 };
        readState = 'done';
      } catch {
        if (t !== token) return;
        readState = auto ? 'idle' : 'away';
      } finally { if (t === token) clearInterval(timer); }
      render();
    }

    function confirm() {
      if (!quality) return;
      let amps = reading ? reading.amps : null;
      if (edit) {
        const a = root.querySelector('#pk-amps'), b = root.querySelector('#pk-brand');
        const v = a && a.value.trim() ? Number(a.value) : null;
        if (v !== null && !(Number.isInteger(v) && v >= 30 && v <= 600)) { msg.textContent = 'Type the main breaker size in amps, like 200.'; a.focus(); return; }
        amps = v;
        if (reading) { reading.amps = v; reading.brand = b ? b.value.trim().slice(0, 40) : reading.brand; }
        edit = false;
      }
      confirmed = true;
      document.dispatchEvent(new CustomEvent('home-photo-confirmed', { detail: { address, main_breaker_amps: amps } }));
      msg.textContent = amps ? `Photo confirmed. Main breaker ${amps} A saved on this device.` : 'Photo confirmed. Saved on this device.';
      render();
    }

    function field(label, value, id, inputType) {
      const row = node('div', 'pk-field');
      if (edit && id) {
        const l = node('label', 'pk-k', label); l.htmlFor = id;
        const i = node('input', 'pk-input'); i.id = id; i.type = inputType || 'text'; i.value = value || '';
        if (inputType === 'number') { i.inputMode = 'numeric'; i.min = '30'; i.max = '600'; i.placeholder = 'e.g. 200'; }
        row.append(l, i);
      } else row.append(node('span', 'pk-k', label), node('b', 'pk-v', value || 'Not read'));
      return row;
    }
    function renderRead() {
      read.replaceChildren();
      read.hidden = !quality;
      if (!quality) return;
      read.append(node('p', 'pk-k', 'Reading'));
      if (readState === 'reading') {
        const p = node('p', 'pk-wait'); p.append('Reading on the PC beside your battery... ', node('span', 'pk-elapsed', '0 s'));
        read.append(p);
      } else if (readState === 'done' && reading) {
        const ok = reading.pass;
        const v = node('p', 'pk-usable ' + (ok ? 'is-ok' : 'is-retake'), ok ? 'Usable: Base can size the battery from this photo.' : `Retake: ${reading.retake}`);
        const fields = node('div', 'pk-fields');
        fields.append(field('Photo type', TYPES[reading.type]),
          field('Manufacturer', reading.brand, 'pk-brand'),
          field('Main breaker', reading.amps ? `${reading.amps} A` : '', 'pk-amps', 'number'),
          field('Confidence', reading.confidence == null ? '' : `${Math.round(reading.confidence * 100)}%`));
        if (edit) { const a = fields.querySelector('#pk-amps'); if (a) a.value = reading.amps || ''; }
        read.append(v, fields, node('p', 'pk-time', `Read on this PC in ${reading.secs} s`));
      } else {
        read.append(node('p', 'pk-away', readState === 'away'
          ? 'Open this page on the PC beside your battery to read the photo there. Here you see the quality check.'
          : 'Reading runs on the PC beside your battery; on this site you see the quality check.'));
        if (edit) { const f = node('div', 'pk-fields'); f.append(field('Main breaker', '', 'pk-amps', 'number')); read.append(f); }
        const row = node('div', 'pk-read-actions');
        const onPC = btn('Read it on my PC', () => readOnPC(false), 'ob-btn-2'); onPC.id = 'pk-read-pc';
        const sample = btn('See a reading on a sample photo', () => {
          const d = document.getElementById('sample-reading');
          if (d) { d.open = true; d.scrollIntoView({ block: 'nearest' }); d.querySelector('summary')?.focus({ preventScroll: true }); }
        }, 'ob-link'); sample.id = 'pk-sample';
        row.append(onPC, sample);
        read.append(row);
      }
    }
    function render() {
      input.disabled = !address;
      pick.classList.toggle('is-off', !address);
      pickText.textContent = file ? 'Choose another photo' : 'Take or choose a photo';
      pick.hidden = !!quality;
      stage.hidden = !quality;
      actions.hidden = !quality;
      chips.replaceChildren();
      tips.replaceChildren();
      if (quality) {
        for (const c of quality.checks) {
          const li = node('li', 'pk-chip ' + (c.pass ? 'is-pass' : 'is-fail'));
          li.dataset.check = c.id; li.dataset.pass = String(c.pass);
          const ic = node('span', 'material-symbols-outlined', c.pass ? 'check_circle' : 'error'); ic.setAttribute('aria-hidden', 'true');
          li.append(ic, node('b', '', c.label), node('span', '', c.value));
          chips.append(li);
        }
        for (const t of quality.tips) tips.append(node('li', 'pk-tip', t));
        verdict.textContent = quality.pass ? 'Clear photo. Ready to read.' : 'Retake for a clearer reading:';
        verdict.className = 'pk-verdict ' + (quality.pass ? 'is-ok' : 'is-retake');
      }
      const usable = quality && (quality.pass || (reading && reading.pass));
      confirmBtn.disabled = !usable || confirmed;
      confirmBtn.firstChild.textContent = confirmed ? 'Confirmed' : 'Confirm';
      correctBtn.hidden = edit || confirmed;
      renderRead();
    }

    document.addEventListener('home-context-changed', e => {
      address = typeof e.detail?.address === 'string' ? e.detail.address : '';
      clear();
    });
    document.addEventListener('home-photos-reset', clear);
    window.addEventListener('pagehide', clear);
    render();
  }
  window.BasePhotoCheck = { measure, grade, safeRetake, Q, TIPS };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
