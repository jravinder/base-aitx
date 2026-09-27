/* One photo, checked and read on the member's device.
   1. The member picks the shot (web/data/photo-shots.json, the same list as Base's photo checklist) and takes or chooses a photo.
      The photo stays in this page as an object URL.
   2. Quality check in the browser: resolution, light (mean luma), sharpness (Laplacian variance), framing.
   3. Reading, on a click (automatic when this page is served from localhost): {image, mime, shot} goes to our server
      (/api/read-photo, or the local ask server), which asks Gemini with the shot prompt. On localhost the PC model is the second try.
      A progress bar shows the stage and the elapsed time. One 30 s deadline covers the whole reading.
   4. A failed, slow (> 30 s) or unsure (confidence < 0.6) reading, or "Not right", offers a Base reviewer:
      localStorage base-fleet:review:v1:<address> = {shot, time, reason}; status.html shows it under step 4.
   5. Confirm (or Submit for review) sends `home-photo-confirmed` {main_breaker_amps}; onboarding.js saves it and awards the photo milestone. */
(() => {
  'use strict';
  const scriptURL = document.currentScript?.src || new URL('photo-check.js', location.href).href;
  const OLLAMA = 'http://localhost:11434';
  const MODEL = 'gemma4:e4b';
  const LIMITS = { deadline: 30000, lowConfidence: 0.6 };
  const EXPECT = { gemini: { secs: 5, text: 'Usually 3 to 6 seconds' }, pc: { secs: 20, text: 'About 20 seconds on this PC' } };
  const STAGES = ['Checking quality', 'Sending', 'Reading', 'Done'];
  const REVIEW_NOTE = 'A Base reviewer will check this photo during the engineering review. You can keep going.';
  const TYPES = { panel_open: 'Open panel', panel_closed: 'Closed panel', meter_exterior: 'Meter, outside', other: 'Other' };
  // Thresholds, measured on a copy scaled to 512 px on the long side.
  const Q = { minSide: 600, dark: 50, bright: 225, sharp: 120, centre: 0.07, aspectMin: 0.5, aspectMax: 2.1 };
  const TIPS = {
    resolution: 'Small photo: take it with the camera at full size.',
    dark: 'Too dark: turn on a light or use the flash.',
    bright: 'Too bright: turn off the flash or block the direct sun.',
    sharpness: 'Blurry: hold still and tap to focus.',
    far: 'Too far: step closer so the label fills a third of the frame.',
    wide: 'Wide shot: take a regular photo, not a panorama or screenshot.'
  };
  // Shots and the reading prompt, shared with brain/ask.py and api/read-photo.js.
  let SHOTS = null;
  const shotsReady = fetch(new URL('data/photo-shots.json', scriptURL)).then(r => r.json()).then(d => { SHOTS = d; return d; });
  function promptFor(id) {
    const s = SHOTS.shots[id] || SHOTS.shots[SHOTS.default];
    return SHOTS.prompt.replace('{label}', s.label).replace('{asks}', s.asks);
  }
  // Members photograph only what is visible with doors and covers closed. Advice that points inside is replaced.
  function safeRetake(text, shot) {
    const s = SHOTS && (SHOTS.shots[shot] || SHOTS.shots[SHOTS.default]);
    const fallback = s ? `Take the photo again to show ${s.asks.replace(/\.$/, '')}. Keep doors and covers closed.`
      : 'Take the photo again from outside, close and in good light. Keep doors and covers closed.';
    if (typeof text !== 'string' || !text.trim()) return fallback;
    return /\b(open|remov|lift|take (the |a )?(door|cover|panel)|(cover|door|panel) off|dead ?front|bus|lug|conductor|wire|wiring|inside|interior|touch)/i.test(text) ? fallback : text.slice(0, 240);
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
    // Size, light and sharpness block Confirm; framing is advice only.
    const blocked = checks.some(c => !c.pass && c.id !== 'framing');
    return { checks, pass: checks.every(c => c.pass), blocked, tips: checks.filter(c => !c.pass).map(c => c.tip) };
  }


  function mount() {
    const root = document.getElementById('photo-check');
    if (!root || root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    let address = '', url = '', file = null, quality = null, reading = null, readState = 'idle', edit = false, confirmed = false, token = 0, timer = 0;
    let shot = 'meter_closeup', stage = 0, backend = 'gemini', t0 = 0, offer = '', review = null, corrected = false;

    const head = node('div', 'pk-head');
    const title = node('h3', 'pk-title', 'Meter and closed panel'); title.id = 'pk-title';
    root.setAttribute('aria-labelledby', title.id);
    head.append(title, node('p', 'pk-sub', 'One clear photo shows Base the mounting space. Keep doors and covers closed.'));
    const shotRow = node('div', 'pk-shot');
    const shotLabel = node('label', 'pk-k', 'This photo shows'); shotLabel.htmlFor = 'pk-shot';
    const shotSelect = node('select', 'pk-select'); shotSelect.id = 'pk-shot';
    shotRow.append(shotLabel, shotSelect);
    shotSelect.addEventListener('change', () => {
      shot = shotSelect.value;
      token++; clearInterval(timer);
      reading = null; readState = 'idle'; offer = ''; edit = false; review = null; confirmed = false; corrected = false;
      render();
    });
    shotsReady.then(d => {
      shotSelect.replaceChildren(...Object.entries(d.shots).map(([id, s]) => { const o = node('option', '', s.label); o.value = id; return o; }));
      shotSelect.value = shot;
    });
    const input = node('input', 'pk-file'); input.id = 'pk-file'; input.type = 'file';
    input.accept = 'image/*'; input.setAttribute('capture', 'environment');
    const pick = node('label', 'pk-pick'); pick.htmlFor = input.id;
    const pickIcon = node('span', 'material-symbols-outlined', 'photo_camera'); pickIcon.setAttribute('aria-hidden', 'true');
    const pickText = node('span', '', 'Take or choose a photo');
    pick.append(pickIcon, pickText, input);
    const stageEl = node('div', 'pk-stage'); stageEl.hidden = true;
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
    stageEl.append(figure, side);
    const read = node('div', 'pk-read'); read.id = 'pk-read'; read.hidden = true;
    // Stage changes and results are announced once; the ticking timer is not.
    const live = node('p', 'pk-sr-only'); live.id = 'pk-live'; live.setAttribute('aria-live', 'polite');
    const actions = node('div', 'pk-actions'); actions.hidden = true;
    const confirmBtn = btn('Confirm', confirm, 'ob-primary pk-confirm'); confirmBtn.id = 'pk-confirm';
    confirmBtn.dataset.reward = 'photo';
    const correctBtn = btn('Correct', () => { edit = true; corrected = true; render(); root.querySelector('.pk-fields input')?.focus(); }, 'ob-btn-2'); correctBtn.id = 'pk-correct';
    const retakeBtn = btn('Retake', () => input.click(), 'ob-btn-2'); retakeBtn.id = 'pk-retake';
    actions.append(confirmBtn, correctBtn, retakeBtn);
    const msg = node('p', 'pk-msg'); msg.setAttribute('role', 'status');
    const note = node('p', 'pk-note', 'Your photo stays on this device. The quality check runs here. Reading sends this one photo for checking.');
    root.replaceChildren(head, shotRow, pick, stageEl, read, live, actions, msg, note);

    function btn(text, fn, cls) { const b = node('button', cls, text); b.type = 'button'; b.addEventListener('click', fn); return b; }
    const reviewKey = () => `base-fleet:review:v1:${address}`;
    function clear() {
      token++; clearInterval(timer);
      if (url) URL.revokeObjectURL(url);
      url = ''; file = null; quality = null; reading = null; readState = 'idle'; edit = false; confirmed = false; offer = ''; review = null; corrected = false;
      img.removeAttribute('src'); input.value = ''; msg.textContent = ''; live.textContent = '';
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
      if (quality && !new URLSearchParams(location.search).has('static')) readPhoto();
    });

    async function ready(signal) {
      try {
        const r = await fetch(`${OLLAMA}/api/tags`, { signal });
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
        retake: safeRetake(out.retake_reason, shot)
      };
    }
    function setStage(n) {
      stage = n;
      live.textContent = n === 3 ? '' : `${STAGES[n]}.`;
      renderRead();
    }
    function tick() {
      const secs = (performance.now() - t0) / 1000;
      const el = root.querySelector('.pk-elapsed'); if (el) el.textContent = `${Math.round(secs)} s`;
      const bar = root.querySelector('.pk-bar');
      if (!bar) return;
      const pct = stage < 2 ? [8, 20][stage] : Math.round(25 + 65 * Math.min(1, secs / EXPECT[backend].secs));
      bar.setAttribute('aria-valuenow', String(pct));
      bar.firstChild.style.width = pct + '%';
    }
    async function readPhoto() {
      if (!file || readState === 'reading') return;
      const t = token, f = file, s = shot;
      readState = 'reading'; offer = ''; backend = 'gemini'; t0 = performance.now();
      setStage(0);
      clearInterval(timer); timer = setInterval(tick, 250);
      // One deadline for the whole reading, however many readers it tries.
      const stop = new AbortController();
      const deadline = setTimeout(() => stop.abort(), LIMITS.deadline);
      const post = (u, body) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: stop.signal });
      try {
        await shotsReady;
        const b64 = await base64(f);
        if (t !== token) return;
        setStage(1);
        const sent = setTimeout(() => { if (t === token && stage === 1) setStage(2); }, 600);
        let out = null, by = '';
        try {
          const g = await post(LOCAL_PAGE ? 'http://localhost:8742/photo/read' : '/api/read-photo', { image: b64, mime: 'image/jpeg', shot: s });
          if (g.ok) {
            const d = await g.json();
            out = clean({ photo_type: d.photo_type, brand: d.manufacturer || '', main_breaker_amps: d.main_breaker_amps,
              confidence: d.confidence, pass: d.usable, retake_reason: d.retake_reason });
            by = 'Gemini';
          }
        } catch (e) { if (stop.signal.aborted) throw e; }
        clearTimeout(sent);
        // Second reader, only when this page runs on the PC beside the battery.
        if (!out && LOCAL_PAGE && !stop.signal.aborted && await ready(stop.signal)) {
          backend = 'pc'; setStage(2);
          const r = await post(`${OLLAMA}/api/chat`, { model: MODEL, stream: false, think: false, format: 'json',
            messages: [{ role: 'user', content: promptFor(s), images: [b64] }] });
          if (r.ok) { out = clean(JSON.parse((await r.json()).message.content)); by = 'this PC'; }
        }
        if (t !== token) return;
        if (!out) throw new Error('read');
        reading = { ...out, secs: Math.round((performance.now() - t0) / 100) / 10, by };
        readState = 'done';
        if (reading.confidence !== null && reading.confidence < LIMITS.lowConfidence) offer = 'low_confidence';
        live.textContent = reading.pass ? 'Done. This photo is usable.' : `Done. Retake: ${reading.retake}`;
      } catch {
        if (t !== token) return;
        readState = 'failed';
        offer = stop.signal.aborted ? 'timeout' : 'failed';
        live.textContent = 'A Base reviewer can check this photo.';
      } finally {
        clearTimeout(deadline);
        if (t === token) { clearInterval(timer); stage = 3; }
      }
      if (t === token) render();
    }

    function askReviewer() {
      const reason = quality && quality.blocked ? 'quality' : offer;
      if (!address || !reason) return;
      review = { shot, time: new Date().toISOString(), reason };
      try { localStorage.setItem(reviewKey(), JSON.stringify(review)); } catch { /* the note below still shows */ }
      msg.textContent = REVIEW_NOTE;
      render();
      confirmBtn.focus();
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
      msg.textContent = review ? 'Photo saved on this device for Base review. You can keep going.'
        : amps ? `Photo confirmed. Main breaker ${amps} A saved on this device.` : 'Photo confirmed. Saved on this device.';
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
    function progress() {
      const box = node('div', 'pk-progress');
      const steps = node('ol', 'pk-steps');
      STAGES.forEach((name, i) => {
        const li = node('li', 'pk-step', name);
        li.dataset.state = i < stage ? 'done' : i === stage ? 'now' : 'next';
        if (i === stage) li.setAttribute('aria-current', 'step');
        steps.append(li);
      });
      const bar = node('div', 'pk-bar'); bar.id = 'pk-progress';
      bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-label', 'Reading the photo');
      bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100');
      bar.setAttribute('aria-valuetext', STAGES[stage]);
      bar.append(node('span', 'pk-bar-fill'));
      const wait = node('p', 'pk-wait');
      wait.append(node('span', 'pk-elapsed', `${Math.round((performance.now() - t0) / 1000)} s`), ` · ${EXPECT[backend].text}`);
      box.append(steps, bar, wait);
      return box;
    }
    function reviewBox() {
      const box = node('div', 'pk-review'); box.id = 'pk-review-box';
      if (review) { box.append(node('p', 'pk-review-note', REVIEW_NOTE)); return box; }
      const why = { failed: 'A Base reviewer can check this photo for you.', timeout: 'This reading is taking longer than usual. A Base reviewer can check this photo for you.',
        low_confidence: 'The reading is unsure about this photo. A Base reviewer can check it for you.', not_right: 'A Base reviewer can check this photo for you.' }[offer];
      const text = quality && quality.blocked ? 'Retake the photo with the tip above, or a Base reviewer can check it for you.' : why;
      box.append(node('p', 'pk-review-why', text), btn('Ask a Base reviewer to check it', askReviewer, 'ob-btn-2 pk-review-btn'));
      box.lastChild.id = 'pk-ask-review';
      return box;
    }
    function renderRead() {
      read.replaceChildren();
      read.hidden = !quality;
      if (!quality) return;
      read.append(node('p', 'pk-k', 'Reading'));
      // A photo that fails size, light or sharpness: only Retake and a Base reviewer are offered.
      if (quality.blocked && readState !== 'reading') { read.append(reviewBox()); return; }
      if (readState === 'reading') {
        read.append(progress());
        tick();
      } else if (readState === 'done' && reading) {
        const ok = reading.pass;
        const v = node('p', 'pk-usable ' + (ok ? 'is-ok' : 'is-retake'), ok ? 'Usable: this photo shows what Base asks for.' : `Retake: ${reading.retake}`);
        const fields = node('div', 'pk-fields');
        fields.append(field('Photo type', TYPES[reading.type]),
          field('Manufacturer', reading.brand, 'pk-brand'),
          field('Main breaker', reading.amps ? `${reading.amps} A` : '', 'pk-amps', 'number'),
          field('Confidence', reading.confidence == null ? '' : `${Math.round(reading.confidence * 100)}%`));
        if (edit) { const a = fields.querySelector('#pk-amps'); if (a) a.value = reading.amps || ''; }
        const time = node('p', 'pk-time', reading.by === 'this PC' ? `Read on this PC in ${reading.secs} s` : `Read by ${reading.by} in ${reading.secs} s`);
        read.append(v, fields, time);
        if (offer || review) read.append(reviewBox());
        else if (!confirmed) {
          const wrong = btn('Not right', () => { offer = 'not_right'; renderRead(); root.querySelector('#pk-ask-review')?.focus(); }, 'ob-link');
          wrong.id = 'pk-not-right';
          read.append(wrong);
        }
      } else {
        if (readState === 'failed') read.append(reviewBox());
        else read.append(node('p', 'pk-away', 'Read the photo to check it against this shot and get the main breaker size if a label shows it. Reading sends this one photo to Google Gemini; everything else stays on your device.'));
        if (edit) { const f = node('div', 'pk-fields'); f.append(field('Main breaker', '', 'pk-amps', 'number')); read.append(f); }
        const row = node('div', 'pk-read-actions');
        const onPC = btn(readState === 'failed' ? 'Read again' : 'Read this photo', readPhoto, 'ob-btn-2'); onPC.id = 'pk-read-pc';
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
      shotSelect.disabled = !address;
      pick.classList.toggle('is-off', !address);
      pickText.textContent = file ? 'Choose another photo' : 'Take or choose a photo';
      pick.hidden = !!quality;
      stageEl.hidden = !quality;
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
      // A photo a Base reviewer will check still moves the member on and earns the photo points.
      // Confirm needs a photo that passes size, light and sharpness, and a usable reading or the member's own correction.
      const usable = quality && ((!quality.blocked && ((reading && reading.pass) || corrected)) || review);
      confirmBtn.hidden = !!(quality && quality.blocked && !review);
      confirmBtn.disabled = !usable || confirmed || readState === 'reading';
      confirmBtn.firstChild.textContent = confirmed ? (review ? 'Submitted for review' : 'Confirmed') : review ? 'Submit for review' : 'Confirm';
      correctBtn.hidden = edit || confirmed || !!(quality && quality.blocked);
      renderRead();
    }

    document.addEventListener('home-context-changed', e => {
      address = typeof e.detail?.address === 'string' ? e.detail.address : '';
      clear();
    });
    document.addEventListener('home-photos-reset', () => {
      if (address) try { localStorage.removeItem(reviewKey()); } catch { /* nothing stored */ }
      clear();
    });
    window.addEventListener('pagehide', clear);
    render();
  }
  window.BasePhotoCheck = { measure, grade, safeRetake, promptFor, shotsReady, Q, TIPS, LIMITS };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
