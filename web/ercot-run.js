// Energy page first screen: the warehouse run screen and the notebook figures.
// Every number comes from data/ercot_warehouse.json (python3 -m warehouse.build -> warehouse/export.py).
(() => {
  "use strict";
  const $ = s => document.querySelector(s);
  const fmt = (n, d = 0) => Number(n).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
  const usd = (n, d = 0) => (n < 0 ? "-$" : "$") + fmt(Math.abs(n), d);
  const pct = (x, d = 0) => fmt(100 * x, d) + "%";
  const mil = n => n >= 1e6 ? fmt(n / 1e6, n >= 1e7 ? 1 : 2) + "M" : n >= 1e4 ? fmt(n / 1e3, 0) + "k" : fmt(n);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const Z = ["LZ_AEN", "LZ_NORTH", "LZ_HOUSTON"];
  const ZN = {LZ_AEN: "Austin", LZ_NORTH: "Dallas (North)", LZ_HOUSTON: "Houston"};
  const ZC = {LZ_AEN: "var(--er-aen)", LZ_NORTH: "var(--er-north)", LZ_HOUSTON: "var(--er-hou)"};
  const SV = ["energy", "regup", "regdn", "ecrs", "nspin", "rrs"];
  const SVN = {energy: "Energy arbitrage", regup: "Reg Up", regdn: "Reg Down", rrs: "RRS", ecrs: "ECRS", nspin: "Non-Spin"};
  const P365 = "last 365 days";
  const tag = k => k === "m" ? '<span class="tag m">Measured</span>' : k === "u" ? '<span class="tag u">Upper bound</span>' : '<span class="tag s">Simulation</span>';
  let D, zone = "LZ_AEN";

  // ---------------- run screen ----------------
  const DAYBINS = [[0.75, "var(--er-h1)", "under $0.75"], [1.25, "var(--er-h2)", "$0.75 to 1.25"], [2, "var(--er-h3)", "$1.25 to 2"],
    [4, "var(--er-h4)", "$2 to 4"], [10, "var(--er-h5)", "$4 to 10"], [1e9, "var(--er-h6)", "$10 or more"]];
  const dayColor = v => DAYBINS.find(b => v < b[0])[1];

  function run() {
    const P = D.pipeline, C = D.dq.checks;
    const conc = D.concentration.find(c => c.load_zone === "LZ_AEN" && c.period === P365);
    const res = D.reserve.filter(r => r.zone === "LZ_AEN" && r.period === P365);
    const r30 = res.find(r => r.floor === 30), r50 = res.find(r => r.floor === 50), r0 = res.find(r => r.floor === 0);
    const sp = D.fleet_spikes.find(x => x.is_spike), ns = D.fleet_spikes.find(x => !x.is_spike);
    const per = D.periods.find(p => p.period === P365);
    const nTop = Math.ceil(conc.hours * 0.01);
    const isFleet = s => /fleet/.test(s);
    const mk = P.models.filter(m => !isFleet(m.model)), fl = P.models.filter(m => isFleet(m.model));
    const sum = (a, f) => a.reduce((s, x) => s + f(x), 0);
    const cm = C.filter(c => !isFleet(c.source.toLowerCase())), cf = C.filter(c => isFleet(c.source.toLowerCase()));
    const cnt = (a, s) => a.filter(c => c.status === s).length;
    const lay = (a, l) => a.filter(m => m.layer === l);

    $("#er-meta").textContent = `built ${D.built_at.replace("T", " ").slice(0, 16)} · ${fmt(D.seconds.total, 1)} s · DuckDB · ${P.layers.staging.models + P.layers.intermediate.models + P.layers.marts.models} models`;
    const dl = rows => `<dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
    $("#er-d1").innerHTML = dl([["market", `${mil(P.market_raw_rows)} rows`], ["fleet", `${mil(P.telemetry_rows)} rows`]]);
    $("#er-d2").innerHTML = dl([["tests", `${P.schema_tests.pass}/${P.schema_tests.total} pass`],
      ["market", `${cnt(cm, "pass")} pass · ${cnt(cm, "warn")} warn · ${cnt(cm, "fail")} fail`],
      ["fleet", `${cnt(cf, "pass")} pass · ${cnt(cf, "warn")} warn · ${cnt(cf, "fail")} fail`]]);
    $("#er-d3").innerHTML = dl([["market", `${lay(mk, "staging").length + lay(mk, "intermediate").length} models · ${mil(sum(lay(mk, "staging").concat(lay(mk, "intermediate")), m => m.rows))}`],
      ["fleet", `${lay(fl, "staging").length + lay(fl, "intermediate").length} models · ${mil(sum(lay(fl, "intermediate"), m => m.rows))}`]]);
    $("#er-d4").innerHTML = dl([["market", `${lay(mk, "marts").length} marts · ${mil(sum(lay(mk, "marts"), m => m.rows))} rows`],
      ["fleet", `${lay(fl, "marts").length} marts · ${mil(sum(lay(fl, "marts"), m => m.rows))} rows`]]);

    $("#er-ans").innerHTML = `In ${fmt(nTop)} hours. <small>${pct(conc.top1pct_share)} of a year's value sits in the top 1% of hours.</small>`;
    $("#er-line").innerHTML = `${fmt(conc.hours)} real ERCOT day-ahead hours, ${per.s} to ${per.e}, one 39.2 kWh Base battery in Austin (LZ_AEN), dispatched with perfect foresight. ${tag("u")} ${tag("m")}`;
    $("#er-k1s").textContent = `perfect foresight, day-ahead, 30% reserve`;
    $("#er-k2s").textContent = `${fmt(nTop)} hours; the top 5% hold ${pct(conc.top5pct_share)}`;
    $("#er-k3s").textContent = `${pct(r30.share)} of the no-reserve value; a 50% floor costs ${usd(r50.cost)}`;
    $("#er-k4s").textContent = `1,000 batteries, ${fmt(sp.intervals)} zone-intervals at $250+; ${pct(ns.avail)} otherwise`;

    // load vs price finding
    const L = D.load_price["2025"];
    const top = (k) => L.hod.reduce((a, b) => b[k] > a[k] ? b : a);
    $("#er-duo").innerHTML = [[`${L.overlap_top100} of 100`, "top-load hours that were also top-price hours"],
      [`${L.top_load_months} vs ${L.top_price_months}`, "months holding the top-load vs top-price hours"],
      [`${String(top("load").h).padStart(2, "0")}:00 vs ${String(top("price").h).padStart(2, "0")}:00`, "most common start hour, load vs price"]]
      .map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join("");
    $("#er-findp").textContent = `In 2025 the 100 highest-load hours on ERCOT were summer afternoons; the 100 highest Austin day-ahead prices were spread over ${L.top_price_months} months and clustered in the evening, most often the hour starting ${String(top("price").h).padStart(2, "0")}:00. Hourly correlation of load and price: ${fmt(L.corr_load_price, 2)}. Dispatch on price, not on the load peak.`;

    // squares: one per day
    const dates = D.daily.dates, vals = D.daily.LZ_AEN.value, N = dates.length;
    $("#er-per").textContent = `${fmt(N)} days, ${dates[0]} to ${dates[N - 1]}`;
    $("#er-sq").innerHTML = dates.map((d, i) => `<i title="${d}: ${usd(vals[i], 2)}, peak ${usd(D.daily.LZ_AEN.peak[i])}/MWh"></i>`).join("");
    const cells = [...document.querySelectorAll("#er-sq i")];
    const fin = vals.map(dayColor);
    $("#er-legend").innerHTML = [["var(--bf-line)", "Queued"], ["var(--bf-blue)", "Solving"]].concat(DAYBINS.map(b => [b[1], b[2]]))
      .map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join("") + `<span>one battery, one day, upper bound</span>`;

    const k = [[$("#er-k1"), r30.value, v => usd(v)], [$("#er-k2"), conc.top1pct_share, v => pct(v)],
      [$("#er-k3"), r30.cost, v => usd(v)], [$("#er-k4"), sp.avail, v => pct(v, 1)]];
    const blocks = ["#er-b1", "#er-b2", "#er-b3", "#er-b4"].map(s => $(s));
    const stTxt = ["#er-s1", "#er-s2", "#er-s3", "#er-s4"].map(s => $(s));
    const set = f => {
      k.forEach(([el, v, ff]) => el.textContent = ff(v * f));
      blocks.forEach((b, i) => {
        const a = i / 4, st = f >= 1 ? "done" : f > a + 0.25 ? "done" : f > a ? "running" : "";
        b.className = "er-blk " + st;
        stTxt[i].textContent = st === "done" ? "Done" : st === "running" ? "Running" : "Waiting";
      });
      $("#er-prog").textContent = `${fmt(Math.round(f * N))} / ${fmt(N)} days`;
      return Math.round(f * N);
    };
    const finish = () => {
      cells.forEach((el, i) => el.style.background = fin[i]);
      set(1);
      $("#er-state").textContent = "Success"; $("#er-state").className = "er-state done";
    };
    if (reduce) return finish();
    set(0);
    const DUR = 3600, WAVE = 20, t0 = performance.now();
    const tick = now => {
      const f = Math.min(1, (now - t0) / DUR), done = set(f);
      for (let i = 0; i < cells.length; i++) {
        const want = i < done - WAVE ? fin[i] : i < done ? "var(--bf-blue)" : "";
        if (cells[i].style.background !== want) cells[i].style.background = want;
      }
      if (f < 1) requestAnimationFrame(tick); else finish();
    };
    requestAnimationFrame(tick);
  }

  // ---------------- notebook ----------------
  const W = el => Math.max(260, el.clientWidth);
  const svg = (w, h, body, label) => `<svg viewBox="0 0 ${w} ${h}" height="${h}" role="img" aria-label="${esc(label)}">${body}</svg>`;
  const line = (x1, y1, x2, y2, st = "var(--bf-line)", extra = "") => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${st}" ${extra}/>`;
  const text = (x, y, t, a = "start", cls = "") => `<text x="${x}" y="${y}" text-anchor="${a}"${cls ? ` class="${cls}"` : ""}>${t}</text>`;
  const HEAT = [[0, "--er-neg", "< $0"], [25, "--er-h0", "$0-25"], [50, "--er-h1", "25-50"], [100, "--er-h2", "50-100"], [200, "--er-h3", "100-200"],
    [500, "--er-h4", "200-500"], [1000, "--er-h5", "500-1k"], [1e9, "--er-h6", "1k+"]];

  function heat() {
    const box = $("#er-heat"), w = W(box), dates = D.daily.dates, n = dates.length, G = D.heatmap[zone];
    const ml = 28, mr = 4, mt = 4, cell = w < 500 ? 6 : 8, h = mt + 24 * cell + 22;
    const dpr = window.devicePixelRatio || 1;
    box.innerHTML = `<canvas width="${Math.round(w * dpr)}" height="${Math.round(h * dpr)}" style="height:${h}px" role="img" aria-label="Day-ahead price by day and hour, ${ZN[zone]}"></canvas>`;
    const c = box.querySelector("canvas").getContext("2d");
    c.scale(dpr, dpr);
    const cols = HEAT.map(b => css(b[1]));
    const dw = (w - ml - mr) / n;
    for (let d = 0; d < n; d++) {
      const x0 = Math.floor(ml + d * dw), x1 = Math.ceil(ml + (d + 1) * dw);
      for (let hh = 0; hh < 24; hh++) {
        const v = G[d][hh];
        if (v == null) continue;
        c.fillStyle = cols[HEAT.findIndex(b => v < b[0])];
        c.fillRect(x0, mt + hh * cell, x1 - x0, cell);
      }
    }
    c.font = `10px ${css("--bf-mono") || "monospace"}`;
    c.fillStyle = css("--bf-faint");
    c.textAlign = "right";
    [0, 6, 12, 18].forEach(hh => c.fillText(String(hh).padStart(2, "0") + "h", ml - 4, mt + hh * cell + cell));
    c.textAlign = "left";
    let lastLbl = -99;
    dates.forEach((d, i) => {
      if (d.slice(8) !== "01") return;
      const x = ml + i * dw, mo = +d.slice(5, 7);
      c.fillStyle = css("--bf-line-strong"); c.fillRect(Math.round(x), mt + 24 * cell, 1, 4);
      if (x - lastLbl < (w < 500 ? 46 : 30) || (w < 500 && mo % 3 !== 1)) return;
      c.fillStyle = css("--bf-faint");
      c.fillText(mo === 1 ? d.slice(0, 4) : ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][mo], x + 2, mt + 24 * cell + 16);
      lastLbl = x;
    });
    const cv = box.querySelector("canvas");
    cv.onmousemove = e => {
      const r = cv.getBoundingClientRect(), d = Math.floor((e.clientX - r.left - ml) / dw), hh = Math.floor((e.clientY - r.top - mt) / cell);
      if (d < 0 || d >= n || hh < 0 || hh > 23 || G[d][hh] == null) return;
      $("#er-heat-n").innerHTML = `<b>${dates[d]} ${String(hh).padStart(2, "0")}:00</b> · ${ZN[zone]} day-ahead <b>${usd(G[d][hh], 2)}</b>/MWh`;
    };
    $("#er-heat-k").innerHTML = HEAT.map(b => `<span><i style="background:var(${b[1]})"></i>${b[2]}</span>`).join("") + "<span>$/MWh, local time</span>";
    const c365 = D.concentration.find(x => x.load_zone === zone && x.period === P365);
    const c25 = D.concentration.find(x => x.load_zone === zone && x.period === "2025");
    const c26 = D.concentration.find(x => x.load_zone === zone && x.period === "2026 YTD");
    $("#er-heat-n").innerHTML = `${ZN[zone]}: max <b>${usd(Math.max(c25.max_price, c26.max_price), 2)}</b>/MWh · hours at $1,000+: 2025 <b>${c25.hours_ge_1000}</b>, 2026 <b>${c26.hours_ge_1000}</b> · negative hours, last 365 days: <b>${fmt(c365.hours_negative)}</b> · hover a cell`;
  }

  function chips() {
    $("#er-chips").innerHTML = Z.map(z => `<button type="button" aria-pressed="${z === zone}" data-z="${z}"><i style="background:${ZC[z]}"></i>${ZN[z]}</button>`).join("");
    document.querySelectorAll("#er-chips button").forEach(b => b.onclick = () => { zone = b.dataset.z; chips(); heat(); });
  }

  function curve() {
    const box = $("#er-curve"), w = W(box), h = 210, m = {l: 34, r: 10, t: 10, b: 30};
    const lx = v => m.l + (Math.log10(v) + 3) / 3 * (w - m.l - m.r), ly = v => m.t + (1 - v) * (h - m.t - m.b);
    let g = "";
    [0, .25, .5, .75, 1].forEach(v => g += line(m.l, ly(v), w - m.r, ly(v)) + text(m.l - 4, ly(v) + 3, pct(v), "end"));
    [0.001, 0.01, 0.1, 1].forEach(v => g += line(lx(v), h - m.b, lx(v), h - m.b + 4, "var(--bf-line-strong)") + text(lx(v), h - m.b + 15, v < 0.01 ? "0.1%" : pct(v), "middle"));
    g += text((m.l + w - m.r) / 2, h - 2, "share of hours, highest price first (log)", "middle");
    [0.01, 0.05].forEach(v => g += line(lx(v), m.t, lx(v), h - m.b, "var(--bf-ink)", 'stroke-dasharray="3 3"') + text(lx(v) + 3, m.t + 10, v === 0.01 ? "top 1%" : "top 5%", "start", "ink"));
    let even = "";
    for (let i = 0; i <= 40; i++) { const v = 10 ** (-3 + 3 * i / 40); even += `${i ? "L" : "M"}${lx(v).toFixed(1)},${ly(v).toFixed(1)}`; }
    g += `<path d="${even}" fill="none" stroke="var(--bf-faint)" stroke-dasharray="1 3"/>` + text(lx(0.3), ly(0.3) + 14, "even spread", "start");
    Z.forEach(z => {
      const pts = D.curve.filter(c => c.load_zone === z && c.period === P365);
      g += `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${lx(p.share_of_hours).toFixed(1)},${ly(p.share_of_value).toFixed(1)}`).join("")}" fill="none" stroke="${ZC[z]}" stroke-width="2"/>`;
    });
    box.innerHTML = svg(w, h, g, "Cumulative share of battery value against share of hours, by zone");
    $("#er-curve-k").innerHTML = Z.map(z => `<span><i class="ln" style="background:${ZC[z]}"></i>${ZN[z]}</span>`).join("");
    const c = Z.map(z => D.concentration.find(x => x.load_zone === z && x.period === P365));
    $("#er-curve-n").innerHTML = `top 1%: ${c.map(x => `<b>${pct(x.top1pct_share)}</b>`).join(" / ")} · top 5%: ${c.map(x => `<b>${pct(x.top5pct_share)}</b>`).join(" / ")} (Austin / Dallas / Houston). Each hour's share = discharge kW x (price - that day's charging cost).`;
  }

  function reserve() {
    const box = $("#er-res"), w = W(box), h = 210, m = {l: 40, r: 64, t: 12, b: 30};
    const R = D.reserve.filter(r => r.period === P365), S = D.stack.filter(s => s.zone === "LZ_AEN" && s.period === P365 && s.service === "energy");
    const ymax = Math.ceil(Math.max(...S.map(s => s.total), ...R.map(r => r.value)) / 100) * 100;
    const x = f => m.l + f / 50 * (w - m.l - m.r), y = v => m.t + (1 - v / ymax) * (h - m.t - m.b);
    let g = "";
    for (let v = 0; v <= ymax; v += 200) g += line(m.l, y(v), w - m.r, y(v)) + text(m.l - 4, y(v) + 3, usd(v), "end");
    [0, 10, 20, 30, 40, 50].forEach(f => g += text(x(f), h - m.b + 15, f + "%", "middle"));
    g += text((m.l + w - m.r) / 2, h - 2, "backup reserve floor (share of 39.2 kWh kept)", "middle");
    g += `<rect x="${x(29)}" y="${m.t}" width="${x(31) - x(29)}" height="${h - m.t - m.b}" fill="var(--bf-sunk)"/>` + text(x(30), m.t + 9, "sim floor", "middle");
    Z.forEach(z => {
      const pts = R.filter(r => r.zone === z);
      g += `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${x(p.floor).toFixed(1)},${y(p.value).toFixed(1)}`).join("")}" fill="none" stroke="${ZC[z]}" stroke-width="2"/>`;
      const e = pts[pts.length - 1];
      g += `<text x="${x(50) + 4}" y="${y(e.value) + (z === "LZ_HOUSTON" ? 14 : z === "LZ_NORTH" ? 4 : -8)}" style="fill:${ZC[z]}">${usd(e.value)}</text>`;
    });
    g += `<path d="${S.map((p, i) => `${i ? "L" : "M"}${x(p.floor).toFixed(1)},${y(p.total).toFixed(1)}`).join("")}" fill="none" stroke="var(--er-aen)" stroke-width="1.5" stroke-dasharray="5 3"/>`;
    g += `<text x="${x(50) + 4}" y="${y(S[S.length - 1].total) + 3}" class="ink">${usd(S[S.length - 1].total)}</text>`;
    box.innerHTML = svg(w, h, g, "Annual battery value against reserve floor, by zone");
    $("#er-res-k").innerHTML = Z.map(z => `<span><i class="ln" style="background:${ZC[z]}"></i>${ZN[z]}, energy only</span>`).join("") + `<span><i class="dash" style="color:var(--er-aen)"></i>Austin, energy + AS</span>`;
    const a = R.filter(r => r.zone === "LZ_AEN"), a0 = a.find(r => r.floor === 0), a30 = a.find(r => r.floor === 30), a50 = a.find(r => r.floor === 50);
    const s0 = S.find(s => s.floor === 0), s30 = S.find(s => s.floor === 30);
    $("#er-res-n").innerHTML = `Austin: <b>${usd(a0.value)}</b> at 0% → <b>${usd(a30.value)}</b> at 30% → <b>${usd(a50.value)}</b> at 50% a year. About <b>${usd((a0.value - a50.value) / 5)}</b> per 10 points of reserve. With AS in the stack the 30% floor costs <b>${usd(s0.total - s30.total)}</b>, not ${usd(a30.cost)}.`;
  }

  function stack() {
    const box = $("#er-stack"), w = W(box), h = 210, m = {l: 40, r: 8, t: 14, b: 30};
    const S = D.stack.filter(s => s.zone === "LZ_AEN" && s.period === P365), floors = [0, 10, 20, 30, 40, 50];
    const ymax = Math.ceil(Math.max(...S.map(s => s.total)) / 100) * 100;
    const bw = (w - m.l - m.r) / floors.length, y = v => m.t + (1 - v / ymax) * (h - m.t - m.b);
    let g = "";
    for (let v = 0; v <= ymax; v += 200) g += line(m.l, y(v), w - m.r, y(v)) + text(m.l - 4, y(v) + 3, usd(v), "end");
    floors.forEach((f, i) => {
      let acc = 0;
      const x0 = m.l + i * bw + bw * 0.18, bwi = bw * 0.64;
      SV.forEach(s => {
        const r = S.find(q => q.floor === f && q.service === s), v = Math.max(0, r.usd);
        g += `<rect x="${x0}" y="${y(acc + v)}" width="${bwi}" height="${y(acc) - y(acc + v)}" fill="var(--er-${s})"><title>${f}% floor, ${SVN[s]}: ${usd(r.usd)}</title></rect>`;
        acc += v;
      });
      g += text(x0 + bwi / 2, y(acc) - 3, usd(acc), "middle", "ink") + text(x0 + bwi / 2, h - m.b + 15, f + "%", "middle");
    });
    g += text((m.l + w - m.r) / 2, h - 2, "reserve floor · Austin · last 365 days", "middle");
    box.innerHTML = svg(w, h, g, "Revenue stack by reserve floor: energy arbitrage and ancillary services");
    $("#er-stack-k").innerHTML = SV.map(s => `<span><i style="background:var(--er-${s})"></i>${SVN[s]}</span>`).join("");
    const at = f => Object.fromEntries(S.filter(s => s.floor === f).map(s => [s.service, s.usd]));
    const a0 = at(0), a50 = at(50), as = o => SV.slice(1).reduce((t, s) => t + o[s], 0);
    const t30 = S.find(s => s.floor === 30);
    $("#er-stack-n").innerHTML = `At 30%: AS adds <b>${usd(t30.total - t30.energy_only)}</b> to ${usd(t30.energy_only)} of energy-only value. From 0% to 50%, energy falls <b>${usd(a0.energy - a50.energy)}</b> but AS only <b>${usd(as(a0) - as(a50))}</b>: capacity offers need less stored energy than arbitrage. Capacity payments only; residential batteries reach these markets only through an aggregation, such as ERCOT's ADER pilot.`;
  }

  function zones() {
    const g = (z, p) => D.concentration.find(c => c.load_zone === z && c.period === p);
    const st = z => D.stack.find(s => s.zone === z && s.period === P365 && s.floor === 30);
    const rt = z => { const m = D.monthly.filter(x => x.zone === z && x.rtm != null); return m.reduce((a, x) => a + x.rtm, 0) / m.reduce((a, x) => a + x.dam, 0); };
    const rows = [
      ["Value 2025, 30% floor", z => usd(g(z, "2025").value_usd), "u"],
      ["Value last 365 days", z => usd(g(z, P365).value_usd), "u"],
      ["+ AS stack, last 365", z => usd(st(z).total), "u"],
      ["Real-time / day-ahead value", z => fmt(rt(z), 2) + "x", "u"],
      ["Share in top 1% of hours", z => pct(g(z, P365).top1pct_share, 1), "u"],
      ["Share in top 5% of hours", z => pct(g(z, P365).top5pct_share, 1), "u"],
      ["Median DAM price", z => usd(g(z, P365).median_price, 2), "m"],
      ["Max DAM price", z => usd(g(z, P365).max_price), "m"],
      ["Hours at $200+", z => fmt(g(z, P365).hours_ge_200), "m"],
      ["Hours at $1,000+", z => fmt(g(z, P365).hours_ge_1000), "m"],
      ["Hours below $0", z => fmt(g(z, P365).hours_negative), "m"],
    ];
    $("#er-zones").innerHTML = `<div class="er-tbl"><table><thead><tr><th>last 365 days</th>${Z.map(z => `<th class="n" style="color:${ZC[z]}">${ZN[z].replace(" (North)", "")}</th>`).join("")}</tr></thead><tbody>`
      + rows.map(([k, f, t]) => `<tr><td>${k} <span style="color:${t === "u" ? "var(--bf-blue)" : "var(--bf-faint)"}">${t === "u" ? "UB" : "M"}</span></td>${Z.map(z => `<td class="n">${f(z)}</td>`).join("")}</tr>`).join("")
      + `</tbody></table></div>`;
  }

  function hod() {
    const box = $("#er-hod"), w = W(box), lane = 44, m = {l: 112, r: 8, t: 6}, wide = w > 520;
    const ml = wide ? m.l : 6;
    const A = (mk) => { const a = Array(24).fill(0); D.spikes_hod.filter(x => x.market === mk && x.load_zone === "LZ_AEN").forEach(x => a[x.hour_of_day] = x.ge200); return a; };
    const L = D.load_price["2025"].hod;
    const lanes = [["Day-ahead, $200+", "hours, Austin, all data", A("DAM"), "var(--er-h4)"], ["Real-time, $200+", "hours (15-min / 4)", A("RTM"), "var(--er-h5)"],
      ["Top-100 price hours", "Austin day-ahead, 2025", L.map(x => x.price), "var(--er-aen)"], ["Top-100 load hours", "ERCOT total, 2025", L.map(x => x.load), "var(--er-north)"]];
    const bw = (w - ml - m.r) / 24, top = wide ? 0 : 14;
    const H = m.t + lanes.length * (lane + top + 8) + 18;
    let g = "";
    lanes.forEach(([a, b, v, col], li) => {
      const y0 = m.t + li * (lane + top + 8) + top, mx = Math.max(...v, 1);
      g += wide ? text(0, y0 + 16, a, "start", "ink") + text(0, y0 + 29, b) : text(ml, y0 - 3, `${a} · ${b}`, "start", "ink");
      g += line(ml, y0 + lane, w - m.r, y0 + lane, "var(--bf-line-strong)");
      v.forEach((n, h) => {
        const bh = n / mx * (lane - 10);
        if (n) g += `<rect x="${ml + h * bw + bw * 0.12}" y="${y0 + lane - bh}" width="${bw * 0.76}" height="${bh}" fill="${col}"><title>${a}, ${String(h).padStart(2, "0")}:00: ${fmt(n, n % 1 ? 1 : 0)}</title></rect>`;
      });
      const pk = v.indexOf(mx);
      g += text(ml + pk * bw + bw / 2, y0 + lane - mx / mx * (lane - 10) - 2, fmt(mx, mx % 1 ? 1 : 0), "middle", "ink");
    });
    [0, 6, 12, 18, 23].forEach(h => g += text(ml + h * bw + bw / 2, H - 4, String(h).padStart(2, "0") + "h", "middle"));
    box.innerHTML = svg(w, H, g, "Spike hours and top load hours by hour of day");
    const L25 = D.load_price["2025"];
    $("#er-hod-n").innerHTML = `2025: <b>${L25.overlap_top100}</b> of the 100 top-load hours were also top-price hours; correlation <b>${fmt(L25.corr_load_price, 2)}</b> (2026 to Aug: ${D.load_price["2026"].overlap_top100} of 100, ${fmt(D.load_price["2026"].corr_load_price, 2)}). Start hour, local time.`;
  }

  function fleet() {
    const box = $("#er-fleet"), w = W(box), F = D.fleet_hourly, n = F.length;
    const m = {l: 44, r: 8, t: 8}, hp = 70, hm = 70, hd = 46, gap = 16, H = m.t + hp + gap + hm + gap + hd + 22;
    const x = i => m.l + i / (n - 1) * (w - m.l - m.r);
    const pmax = Math.max(...F.map(f => f.p || 0)), mmax = Math.max(...F.map(f => Math.abs(f.mw))), dmax = Math.max(...F.map(f => Math.max(f.down, f.below)), 1);
    let g = "";
    const y1 = v => m.t + hp - v / pmax * hp;
    const yb = m.t + hp + gap, y2 = v => yb + hm / 2 - v / mmax * (hm / 2);
    const yc = yb + hm + gap, y3 = v => yc + hd - v / dmax * hd;
    // storm-watch shading (local Jan 23 00:00 to Jan 29 00:00)
    const s0 = F.findIndex(f => f.t >= "2026-01-23"), s1 = F.findIndex(f => f.t >= "2026-01-29");
    if (s0 >= 0 && s1 > s0) g += `<rect x="${x(s0)}" y="${m.t}" width="${x(s1) - x(s0)}" height="${H - m.t - 22}" fill="var(--bf-sunk)"/>` + text(x(s0) + 4, m.t + 10, "storm watch: floors raised to 80%", "start");
    g += line(m.l, m.t + hp, w - m.r, m.t + hp, "var(--bf-line-strong)") + text(m.l - 4, m.t + 8, usd(pmax), "end") + text(m.l - 4, m.t + hp, "$0", "end");
    g += `<path d="${F.map((f, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y1(Math.max(0, f.p || 0)).toFixed(1)}`).join("")}" fill="none" stroke="var(--er-h5)" stroke-width="1.2"/>`;
    g += text(w - m.r, m.t + hp - 4, "Austin real-time price, hourly mean (real ERCOT)", "end");
    g += line(m.l, y2(0), w - m.r, y2(0), "var(--bf-line-strong)") + text(m.l - 4, y2(mmax) + 8, fmt(mmax, 1) + " MW", "end") + text(m.l - 4, y2(-mmax), "-" + fmt(mmax, 1), "end");
    const bw = Math.max(1, (w - m.l - m.r) / n);
    F.forEach((f, i) => { const yy = y2(Math.max(0, f.mw)), hh = Math.abs(y2(f.mw) - y2(0)); g += `<rect x="${x(i) - bw / 2}" y="${f.mw >= 0 ? yy : y2(0)}" width="${bw}" height="${hh}" fill="${f.mw >= 0 ? "var(--er-aen)" : "var(--er-north)"}"/>`; });
    g += text(w - m.r, yb + 10, "fleet MW: export up, charging down", "end");
    g += line(m.l, yc + hd, w - m.r, yc + hd, "var(--bf-line-strong)") + text(m.l - 4, yc + 8, fmt(dmax), "end");
    g += `<path d="${F.map((f, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y3(f.down).toFixed(1)}`).join("")}" fill="none" stroke="var(--er-h4)" stroke-width="1.5"/>`;
    g += `<path d="${F.map((f, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y3(f.below).toFixed(1)}`).join("")}" fill="none" stroke="var(--bf-ink)" stroke-width="1" stroke-dasharray="2 2"/>`;
    g += text(w - m.r, yc + 10, "devices: grid down (solid), under own reserve (dashed)", "end");
    F.forEach((f, i) => { if (f.t.endsWith("00:00") && (+f.t.slice(8, 10)) % (w < 500 ? 7 : 3) === 0) g += text(x(i), H - 6, f.t.slice(5, 10), "middle"); });
    box.innerHTML = svg(w, H, g, "Simulated fleet response to real ERCOT prices, January 2026");
    const sp = D.fleet_spikes.find(s => s.is_spike), ns = D.fleet_spikes.find(s => !s.is_spike), fd = D.fleet_devices;
    $("#er-fleet-n").innerHTML = `In <b>${fmt(sp.intervals)}</b> zone-intervals at $250+ (mean ${usd(sp.price)}), <b>${pct(sp.avail, 1)}</b> of batteries were online, grid-up and above their floor (vs ${pct(ns.avail, 1)} at other times), with <b>${fmt(sp.kwh_above)}</b> kWh above reserve per zone and <b>${fmt(sp.kw_out)}</b> kW discharging. ${fmt(fd.devices)} devices, ${D.fleet_zones.map(z => `${fmt(z.n)} ${ZN[z.load_zone].replace(" (North)", "")}`).join(", ")}; window ${D.pipeline.fleet_sim.window_local.join(" to ")}.`;
  }

  function dq() {
    const C = D.dq.checks, F = D.dq.fault_detection;
    $("#er-dq").innerHTML = `<div class="er-two"><div class="er-tbl"><table><thead><tr><th>check</th><th>source</th><th>status</th><th>result</th></tr></thead><tbody>`
      + C.map(c => `<tr><td title="${esc(c.description)}">${esc(c.check_id)}</td><td>${esc(c.source)}</td><td><span class="er-st ${c.status}">${c.status}</span></td><td class="d">${esc(c.detail)}</td></tr>`).join("")
      + `</tbody></table></div><div class="er-tbl"><table><thead><tr><th>injected fault</th><th class="n">devices</th><th class="n">caught</th><th class="n">false +</th></tr></thead><tbody>`
      + F.map(f => `<tr><td>${esc(f.fault.replace(/_/g, " "))}</td><td class="n">${f.injected}</td><td class="n">${f.detected}</td><td class="n">${f.false_positive.length}</td></tr>`).join("")
      + `</tbody></table><p class="er-src">Each fleet check is scored against the faults the simulator injected, so a check that misses a fault or flags a healthy device shows up here. Freshness warns because ERCOT posts the archives weekly.</p>`
      + `<p class="er-src">Schema tests: <b>${D.pipeline.schema_tests.pass}/${D.pipeline.schema_tests.total}</b> pass (unique, not_null, accepted_range, accepted_values, relationships), same yml under <code>dbt build</code>.</p></div></div>`;
    const s = D.dq.summary;
    $("#er-dq-h").textContent = `${s.pass} pass · ${s.warn} warn · ${s.fail} fail`;
  }

  function lineage() {
    const box = $("#er-lin"), w = W(box), L = D.pipeline.lineage, M = Object.fromEntries(D.pipeline.models.map(m => [m.model, m]));
    const layers = ["raw", "staging", "intermediate", "marts"];
    const col = Object.fromEntries(layers.map(l => [l, L.nodes.filter(n => n.layer === l).map(n => n.id).sort()]));
    const label = id => id.replace(/^source\./, "").replace(/^(stg|int|mart)_/, "").replace("__", ".");
    if (w < 640) {
      box.innerHTML = layers.map(l => `<div class="er-src"><b style="color:var(--bf-ink)">${l}</b> · ${col[l].map(label).join(", ")}</div>`).join("");
      return;
    }
    const rowH = 19, mt = 18, H = mt + Math.max(...layers.map(l => col[l].length)) * rowH + 4, cw = w / 4, pos = {};
    let g = "";
    layers.forEach((l, i) => {
      g += text(i * cw + 4, 11, `${l} · ${col[l].length}`, "start", "ink");
      col[l].forEach((id, j) => pos[id] = [i * cw + 4, mt + j * rowH + 12, i]);
    });
    L.edges.forEach(([a, b]) => {
      if (!pos[a] || !pos[b]) return;
      const [x1, y1, i1] = pos[a], [x2, y2] = pos[b], xa = x1 + cw - 14, xb = x2 - 6;
      g += `<path d="M${xa},${y1 - 4} C${(xa + xb) / 2},${y1 - 4} ${(xa + xb) / 2},${y2 - 4} ${xb},${y2 - 4}" fill="none" stroke="var(--bf-line-strong)" stroke-width="0.8" opacity="${i1 === 0 ? .9 : .7}"/>`;
    });
    Object.entries(pos).forEach(([id, [x, y]]) => {
      const m = M[id], fleet = /fleet/.test(id);
      g += `<circle cx="${x - 0}" cy="${y - 4}" r="3" fill="${fleet ? "var(--er-north)" : "var(--er-aen)"}"/>` +
        `<text x="${x + 6}" y="${y}" class="ink">${esc(label(id))}${m ? ` <tspan style="fill:var(--bf-faint)">${mil(m.rows)}</tspan>` : ""}</text>`;
    });
    box.innerHTML = svg(w, H, g, "Model lineage from raw sources to marts");
  }

  function head() {
    const P = D.pipeline, per = D.periods.find(p => p.period === P365), c = D.concentration.find(x => x.load_zone === "LZ_AEN" && x.period === P365);
    const rows = Object.fromEntries(P.models.map(m => [m.model, m.rows]));
    $("#er-sub").innerHTML = `ERCOT public archives (reports 13060, 13061, 13091 and native load), 2025-01-01 to ${D.daily.dates[D.daily.dates.length - 1]}, through raw → staging → marts in DuckDB. "Upper bound" means the battery knew every price in advance (a linear program per day, 90% round trip). The fleet figures are a simulation driven by the real prices.`;
    $("#er-strip2").innerHTML = [["DAM hours", fmt(rows.int_market__zone_hourly)], ["RTM intervals", mil(rows.stg_ercot__rtm_spp)], ["telemetry rows", mil(P.telemetry_rows)],
      ["build", fmt(D.seconds.total, 0) + " s"], ["telemetry", mil(P.throughput.rows_per_s) + " rows/s"], ["checks", `${D.dq.summary.pass + D.dq.summary.warn}/${D.dq.checks.length} run`]]
      .map(([k, v]) => `<div>${k}<b>${v}</b></div>`).join("");
    $("#er-big").innerHTML = `<b>${usd(c.value_usd)}<small>/yr</small></b><span>one battery, Austin, 30% reserve, ${per.s} to ${per.e}, upper bound</span>`;
  }

  function figures() { heat(); curve(); reserve(); stack(); hod(); fleet(); lineage(); }

  fetch("data/ercot_warehouse.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(d => {
    D = d;
    run(); head(); chips(); zones(); dq(); figures();
    let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(figures, 150); });
    new MutationObserver(() => figures()).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
  }).catch(e => { const n = $("#er-notice"); if (n) { n.style.display = "block"; n.textContent += ` (${e.message})`; } });
})();
