(() => {
  'use strict';
  // /home and /compute both serve this page. Visuals are drawn from web/data; every number on the page is static text.
  document.title = 'Base Power Case Study';
  const $ = s => document.getElementById(s);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const get = u => fetch(u).then(r => r.ok ? r.json() : Promise.reject(r.status));
  // Run fn while a card is hovered or focused.
  const onActive = (id, start, stop) => {
    const card = $(id);
    ['mouseenter', 'focus'].forEach(e => card.addEventListener(e, start));
    ['mouseleave', 'blur'].forEach(e => card.addEventListener(e, stop));
  };

  // Hero: battery value by day, Austin (same bins as the Energy page run screen).
  const DAYBINS = [[0.75, '--er-h1'], [1.25, '--er-h2'], [2, '--er-h3'], [4, '--er-h4'], [10, '--er-h5'], [1e9, '--er-h6']];
  const HEAT = [[0, '--er-neg'], [25, '--er-h0'], [50, '--er-h1'], [100, '--er-h2'], [200, '--er-h3'], [500, '--er-h4'], [1000, '--er-h5'], [1e9, '--er-h6']];
  get('/web/data/ercot_warehouse.json').then(D => {
    const vals = D.daily.LZ_AEN.value, dates = D.daily.dates, box = $('days-sq'), tip = $('days-tip');
    const usd = v => '$' + v.toFixed(2);
    box.innerHTML = dates.map((d, i) => `<i title="${d}: ${usd(vals[i])}"></i>`).join('');
    const cells = [...box.children], fin = vals.map(v => `var(${DAYBINS.find(b => v < b[0])[1]})`);
    // Summary for screen readers.
    const sorted = [...vals].sort((x, y) => x - y), med = sorted[Math.floor(sorted.length / 2)], mx = vals.indexOf(sorted[sorted.length - 1]);
    box.setAttribute('aria-label', `${vals.length} days, ${dates[0]} to ${dates[dates.length - 1]}: dollars per day for one 39.2 kWh Base battery in Austin, upper bound. Median ${usd(med)}; highest ${usd(vals[mx])} on ${dates[mx]}. Use arrow keys to read each day.`);
    // Tooltip on hover, and on focus with arrow keys.
    let sel = -1;
    const show = i => {
      if (sel >= 0) cells[sel].classList.remove('sel');
      sel = i; if (i < 0) { tip.hidden = true; return; }
      const c = cells[i], r = c.getBoundingClientRect(), p = box.parentElement.getBoundingClientRect();
      c.classList.add('sel');
      tip.textContent = `${dates[i]} · ${usd(vals[i])}`;
      tip.hidden = false;
      tip.style.left = Math.min(Math.max(r.left - p.left + r.width / 2, 60), p.width - 60) + 'px';
      tip.style.top = (r.top - p.top - 6) + 'px';
    };
    cells.forEach((c, i) => { c.removeAttribute('title'); c.addEventListener('mouseenter', () => show(i)); });
    box.addEventListener('mouseleave', () => { if (document.activeElement !== box) show(-1); });
    box.addEventListener('focus', () => show(sel >= 0 ? sel : cells.length - 1));
    box.addEventListener('blur', () => show(-1));
    box.addEventListener('keydown', e => {
      const cols = Math.max(1, Math.round(box.clientWidth / (cells[1].offsetLeft - cells[0].offsetLeft || 12)));
      const step = {ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols, Home: -1e9, End: 1e9}[e.key];
      if (step == null) return;
      e.preventDefault();
      show(Math.min(cells.length - 1, Math.max(0, (sel < 0 ? 0 : sel) + step)));
    });
    if (reduce) cells.forEach((c, i) => c.style.background = fin[i]);
    else {
      const t0 = performance.now(), DUR = 2400, WAVE = 24;
      const tick = now => {
        const done = Math.round(Math.min(1, (now - t0) / DUR) * cells.length);
        for (let i = 0; i < cells.length; i++) {
          const want = i < done - WAVE ? fin[i] : i < done ? 'var(--bf-line-strong)' : '';
          if (cells[i].style.background !== want) cells[i].style.background = want;
        }
        if (done < cells.length) requestAnimationFrame(tick); else cells.forEach((c, i) => c.style.background = fin[i]);
      };
      requestAnimationFrame(tick);
    }
    // ERCOT card: hour x day heatmap of Austin day-ahead $/MWh, drawn 1.8x wider than the card so hover can pan it.
    const G = D.heatmap.LZ_AEN, strip = $('viz-strip'), n = G.length, H = strip.clientHeight || 76;
    const vw = Math.max(200, strip.clientWidth), W = Math.round(vw * 1.8), dpr = devicePixelRatio || 1;
    strip.innerHTML = `<canvas width="${Math.round(W * dpr)}" height="${H * dpr}" style="width:${W}px"></canvas>`;
    strip.style.setProperty('--pan', `${vw - W}px`);
    const c = strip.firstChild.getContext('2d'), cols = HEAT.map(b => css(b[1])), dw = W / n, ch = H / 24;
    c.scale(dpr, dpr);
    for (let d = 0; d < n; d++) for (let h = 0; h < 24; h++) {
      const v = G[d][h]; if (v == null) continue;
      c.fillStyle = cols[HEAT.findIndex(b => v < b[0])];
      c.fillRect(Math.floor(d * dw), h * ch, Math.ceil(dw), Math.ceil(ch));
    }
  }).catch(() => {});

  // Lead card: permits routed, scaled to the squares that fit (auto, review, to a person) from judgments.json.
  get('/web/data/judgments.json').then(J => {
    const p = J.counts.permit, total = p.auto + p.review + p.human, box = $('viz-permits');
    const cols = Math.floor((box.clientWidth + 3) / 12), N = cols * Math.floor((box.clientHeight + 3) / 12);
    const red = Math.round(p.human / total * N), amber = Math.round(p.review / total * N), routed = red + amber;
    const kinds = Array(N).fill('');
    // Spread the routed squares evenly; every third one (up to the red count) goes to a person.
    for (let i = 0, r = 0; i < routed; i++) kinds[Math.floor((i + 0.5) * N / routed)] = (i % 3 === 0 && r < red) ? (r++, 'p') : 'v';
    box.innerHTML = kinds.map(k => `<i class="${k}"></i>`).join('');
    const cells = [...box.children];
    let raf = 0;
    if (!reduce) onActive('choose-install', () => {
      cancelAnimationFrame(raf);
      cells.forEach(c => c.classList.add('off'));
      const t0 = performance.now();
      const tick = now => {
        const done = Math.round(Math.min(1, (now - t0) / 900) * cells.length);
        for (let i = 0; i < done; i++) cells[i].classList.remove('off');
        if (done < cells.length) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, () => { cancelAnimationFrame(raf); cells.forEach(c => c.classList.remove('off')); });
  }).catch(() => {});

  // Fleet card: the simulated nodes, reserve (green) always held, GPU work (blue) on the share the sim achieved.
  get('/web/data/report.json').then(R => {
    const F = R.panels.find(x => x.name === 'Fleet');
    const nodes = F.nodes, lit = Math.round(F.gpu_utilisation * nodes), box = $('viz-nodes');
    box.innerHTML = '<i></i>'.repeat(nodes);
    const cells = [...box.children];
    const shuffle = () => { const idx = new Set(cells.map((_, i) => i).sort(() => Math.random() - 0.5).slice(0, lit)); cells.forEach((c, i) => c.classList.toggle('on', idx.has(i))); };
    shuffle();
    let timer = 0;
    if (!reduce) onActive('choose-fleet', () => { clearInterval(timer); shuffle(); timer = setInterval(shuffle, 650); }, () => clearInterval(timer));
  }).catch(() => {});
})();
