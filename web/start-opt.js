// Landing design options A/B/C (web/start-{a,b,c}.html). Every visual is drawn from web/data; numbers in the HTML are static.
(() => {
  'use strict';
  const $ = s => document.getElementById(s);
  const V = document.body.dataset.variant;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const get = u => fetch(u).then(r => r.ok ? r.json() : Promise.reject(r.status));
  const ramp = n => `var(--ramp-${n})`;
  const BINS = [0.75, 1.25, 2, 4, 10]; // same breakpoints as the Energy page, $ per day
  const bin = v => { const i = BINS.findIndex(b => v < b); return i < 0 ? 5 : i; };

  // Grow a list of cells to their final colours, left to right.
  const fillIn = (cells, fin, dur = 1800) => {
    if (reduce) return cells.forEach((c, i) => c.style.background = fin[i]);
    const t0 = performance.now();
    const tick = now => {
      const done = Math.round(Math.min(1, (now - t0) / dur) * cells.length);
      for (let i = 0; i < done; i++) if (!cells[i].style.background) cells[i].style.background = fin[i];
      if (done < cells.length) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };

  // Tiny sparkline: one line, one hue (currentColor), optional dashed floor.
  const spark = (el, ys, {floor, min, max} = {}) => {
    if (!el) return;
    const w = 240, h = 40, lo = min ?? Math.min(...ys), hi = max ?? Math.max(...ys);
    const x = i => (i / (ys.length - 1)) * w, y = v => h - 2 - ((v - lo) / (hi - lo || 1)) * (h - 4);
    const d = ys.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join('');
    const f = floor != null ? `<line x1="0" x2="${w}" y1="${y(floor)}" y2="${y(floor)}" stroke="currentColor" stroke-opacity=".45" stroke-dasharray="3 3"/>` : '';
    el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">${f}<path d="${d}" fill="none" stroke="currentColor" stroke-width="1.75" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`;
  };

  // The 634-day battery value grid (A and C), single-hue ramp.
  if (V === 'a' || V === 'c') get('/web/data/ercot_warehouse.json').then(D => {
    const vals = D.daily.LZ_AEN.value, dates = D.daily.dates, box = $('days');
    box.innerHTML = dates.map((d, i) => `<i title="${d}: $${vals[i].toFixed(2)}"></i>`).join('');
    const sorted = [...vals].sort((a, b) => a - b), mx = vals.indexOf(sorted[sorted.length - 1]);
    box.setAttribute('aria-label', `${vals.length} days, ${dates[0]} to ${dates[dates.length - 1]}: dollars per day for one 39.2 kWh Base battery in Austin, upper bound. Median $${sorted[Math.floor(sorted.length / 2)].toFixed(2)}; highest $${vals[mx].toFixed(2)} on ${dates[mx]}.`);
    fillIn([...box.children], vals.map(v => ramp(bin(v))), 2200);
    if (V === 'a') {
      spark($('sp-ercot'), D.monthly.filter(m => m.zone === 'LZ_AEN').map(m => m.dam));
      spark($('sp-fleet'), D.fleet_soc.map(s => s.soc_p10), {floor: 30, min: 0, max: 100});
    }
  }).catch(() => {});

  if (V === 'a') get('/web/data/explorer_zip.json').then(Z => {
    const months = Object.keys(Z.by_month).sort();
    spark($('sp-lead'), months.map(m => Object.values(Z.by_month[m]).reduce((a, b) => a + b, 0)));
  }).catch(() => {});

  // B: the run screen. One square per 50 permits; only "to a person" gets a status colour.
})();
