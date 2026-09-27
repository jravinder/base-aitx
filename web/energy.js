/* Energy and credits: installed member view. Member = data/members.json node ?node= (default 3). */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const params = new URLSearchParams(location.search);
  const raw = params.get("node");
  const nodeId = raw !== null && raw !== "" && Number.isFinite(+raw) ? +raw : 3;
  const fmt = (n, d = 1) => Number(n).toLocaleString("en-US", {maximumFractionDigits: d});
  const money = n => "$" + Number(n).toFixed(2);
  const KIND = {member: "member questions", business: "business inference", base: "Base fleet work", external: "open-science batch"};
  const get = p => fetch(p).then(r => r.ok ? r.json() : null).catch(() => null);
  const dayName = d => new Date(d.date + "T12:00:00").toLocaleDateString("en-US", {month: "short", day: "numeric"});

  document.querySelectorAll("[data-ctx]").forEach(a => {
    const url = new URL(a.getAttribute("href"), location.href);
    url.searchParams.set("track", "compute"); url.searchParams.set("persona", "gpu"); url.searchParams.set("node", String(nodeId));
    a.href = url.href;
  });

  let member = null, draw = 1, sel = 0;

  function renderTiles() {
    const n = member.node, t = member.totals;
    $("feeder-chip").textContent = `Simulated feeder ${n.feeder}`;
    $("m-total").textContent = money(t.battery_usd + t.gpu_usd);
    $("m-total-note").textContent = `Battery ${money(t.battery_usd)} · compute ${money(t.gpu_usd)}`;
    $("m-reserve").textContent = `${n.reserve_pct}%`;
    $("m-reserve-kwh").textContent = `${fmt(n.reserve_kwh, 2)} kWh kept`;
    $("m-gpu").textContent = fmt(t.gpu_hours, 0);
    $("m-gpu-note").textContent = `On the PC beside your ${fmt(n.battery_kwh)} kWh battery`;
    const lows = member.week.map(d => d.reserve_min_pct).filter(v => v != null);
    if (lows.length) {
      const lo = Math.min(...lows);
      $("m-low").textContent = `${fmt(lo, 0)}%`;
      $("m-low-note").textContent = `${fmt(lo - n.reserve_pct, 0)} points above your ${n.reserve_pct}% reserve`;
      $("lock-chip").textContent = `${n.reserve_pct}% reserve held all week`;
    }
    if (lows.length) $("safe-note").textContent = `The fleet sends power and runs jobs only above your ${n.reserve_pct}% reserve. This week your battery stayed at ${fmt(Math.min(...lows), 0)}% or higher.`;
  }

  function renderChart() {
    const w = member.week, X = 700, base = 190, top = 24, slot = X / w.length, bw = Math.min(40, slot * 0.45);
    const max = Math.max(...w.map(d => d.battery_usd + d.gpu_usd)) || 1;
    const h = v => (v / max) * (base - top);
    const best = w.reduce((b, d, i) => d.battery_usd > w[b].battery_usd ? i : b, 0);
    const grid = [0.25, 0.5, 0.75].map(f => `<line x1="0" x2="${X}" y1="${base - f * (base - top)}" y2="${base - f * (base - top)}" stroke="#f1f5f9" stroke-dasharray="4" stroke-width="1.5"/>`).join("");
    $("flow-chart").innerHTML = grid + `<line x1="0" x2="${X}" y1="${base}" y2="${base}" stroke="#e2e8f0" stroke-width="1.5"/>` + w.map((d, i) => {
      const cx = slot * i + slot / 2, x = cx - bw / 2, hb = Math.max(3, h(d.battery_usd)), hg = h(d.gpu_usd), on = i === sel;
      return `<g data-day="${i}">${on ? `<rect x="${cx - bw / 2 - 10}" y="${top - 16}" width="${bw + 20}" height="${base - top + 16}" rx="8" fill="#bbefc1" opacity=".45"/>` : ""}
        <rect x="${x}" y="${base - hb}" width="${bw}" height="${hb}" rx="3" fill="#1e4d2b"/>
        <rect x="${x}" y="${base - hb - hg - 2}" width="${bw}" height="${hg}" rx="3" fill="#84CC16"/>
        <text x="${cx}" y="${base - hb - hg - 8}" text-anchor="middle" font-size="11" fill="#414941" font-family="Plus Jakarta Sans">${money(d.battery_usd + d.gpu_usd)}</text>
        ${i === best ? `<circle cx="${cx + bw / 2 + 4}" cy="${base - hb}" r="4" fill="#22C55E"/>` : ""}
        <text x="${cx}" y="210" text-anchor="middle" font-size="11" font-weight="${on ? 700 : 400}" fill="${on ? "#1e4d2b" : "#717970"}" font-family="Plus Jakarta Sans">Day ${d.day}</text></g>`;
    }).join("");
    $("flow-chart").querySelectorAll("g[data-day]").forEach(g => g.addEventListener("click", () => pickDay(+g.dataset.day)));
    $("flow-chart").setAttribute("aria-label", "Value by day: " + w.map(d => `day ${d.day}, battery ${money(d.battery_usd)}, compute ${money(d.gpu_usd)}`).join("; "));
    const dates = [...new Set(w.map(d => d.date))].sort().map(s => dayName({date: s}));
    $("flow-note").textContent = `${w.length} days on real ERCOT Austin prices from ${dates.join(", ")}. Green dot: best battery day.`;
    const t = member.totals;
    $("credit-split").textContent = `Battery ${money(t.battery_usd)} + compute ${money(t.gpu_usd)} for the week`;
    $("credit-total").textContent = money(t.battery_usd + t.gpu_usd);
  }

  function renderDays() {
    $("log-days").innerHTML = member.week.map((d, i) => `<button type="button" class="en-day px-2.5 py-1 rounded-full bg-surface-subtle font-label-md text-label-md text-ink-primary" data-i="${i}" aria-pressed="${i === sel}">Day ${d.day}</button>`).join("");
    $("log-days").querySelectorAll("button").forEach(b => b.addEventListener("click", () => pickDay(+b.dataset.i)));
  }

  function pickDay(i) {
    sel = i;
    $("log-days").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.i === i)));
    renderChart(); renderLog();
  }

  function renderLog() {
    const d = member.week[sel], ev = d.events, n = member.node;
    const dis = ev.filter(e => /^discharged/.test(e)), chg = ev.filter(e => /^charged/.test(e));
    const gpu = ev.filter(e => /^GPU ran/.test(e)), res = ev.find(e => /^reserve/.test(e));
    const span = e => (e.match(/\d\d:\d\d-\d\d:\d\d/) || [""])[0];
    const price = e => (e.match(/price (\d+(?:\.\d+)?) \$\/MWh/) || [])[1];
    const low = res && (res.match(/low point (\d+)%/) || [])[1];
    const top = dis[0];
    $("log-main").innerHTML = `<div class="flex items-start justify-between gap-3">
      <div class="min-w-0"><h3 class="font-headline-sm text-headline-sm text-ink-primary">${top ? "Sent power back at the evening peak" : "Battery held for you"}</h3>
      <p class="font-label-md text-label-md text-primary-container mt-0.5">Day ${d.day} · ${esc(dayName(d))} prices${top ? " · " + esc(span(top)) : ""}</p></div>
      <div class="text-right shrink-0"><span class="text-[18px] font-bold text-solar-green">+${money(d.battery_usd)}</span><span class="block text-[10px] uppercase font-bold text-on-surface-variant">Battery</span></div></div>
      <p class="font-body-sm text-body-sm text-on-surface-variant">${top ? `Sold at <strong class="text-ink-primary">${esc(price(top))} $/MWh</strong>. ` : ""}${chg.length ? `Charged at ${chg.map(e => `${esc(price(e))} $/MWh (${esc(span(e))})`).join(" and ")}. ` : ""}Reserve kept at <strong class="text-primary-container">${n.reserve_pct}%</strong>${low ? `, lowest charge ${esc(low)}%` : ""}.</p>`;
    const rows = [];
    if (gpu.length) {
      const kinds = [...new Set(gpu.map(e => (e.match(/a (\w+) job/) || [])[1]).filter(Boolean))].map(k => KIND[k] || k);
      rows.push(["memory", `Compute for ${d.gpu_hours} hours`, kinds.join(", "), `+${money(d.gpu_usd)}`]);
    }
    for (const e of chg) rows.push(["battery_charging_full", "Charged when power was cheap", span(e), ""]);
    for (const e of dis) rows.push(["bolt", "Sent power to the grid", span(e), ""]);
    $("log-list").innerHTML = rows.map(([icon, t, s, v]) => `<div class="flex items-center justify-between gap-3 py-2.5">
      <div class="flex items-center gap-2.5 min-w-0"><span class="material-symbols-outlined text-[18px] text-primary-container" aria-hidden="true">${icon}</span>
      <div class="min-w-0"><span class="font-label-md text-label-md text-ink-primary block">${esc(t)}</span><span class="font-body-sm text-[11px] text-on-surface-variant">${esc(s)}</span></div></div>
      <span class="font-label-md text-label-md text-primary-container shrink-0">${esc(v)}</span></div>`).join("");
  }

  function renderReserve() {
    const n = member.node, pct = +$("reserve").value, cap = n.battery_kwh;
    const reserve = cap * pct / 100, usable = cap - reserve, hours = usable / draw;
    $("reserve-val").textContent = pct + "%";
    $("reserve").setAttribute("aria-valuetext", pct + "%");
    $("reserve-mine").textContent = pct === n.reserve_pct ? "Your setting" : `Preview · yours is ${n.reserve_pct}%`;
    $("reserve-reset").hidden = pct === n.reserve_pct;
    $("r-reserve-hours").textContent = `${fmt(reserve / draw)} hours`;
    $("hours").textContent = `${fmt(hours)} hours`;
    $("r-margin").textContent = `${fmt(usable, 2)} kWh`;
    $("m-hours").textContent = `${fmt(n.reserve_kwh / draw)} hours at ${draw} kW from the reserve alone`;
    $("math").innerHTML = `Your <strong class="text-ink-primary">${fmt(cap)} kWh</strong> battery, starting full, keeps a <strong class="text-ink-primary">${pct}% reserve (${fmt(reserve, 2)} kWh)</strong>. That leaves <strong class="text-ink-primary">${fmt(usable, 2)} kWh</strong> for your home. ${fmt(usable, 2)} kWh ÷ ${draw} kW = <strong class="text-ink-primary">${fmt(hours)} hours</strong>. The reserve then carries you ${fmt(reserve / draw)} hours more.`;
  }

  function renderStation(block) {
    if (!block || !block.hub) return;
    const c = block.counts || {}, km = fmt(block.radius_m / 1000);
    $("hub-name").textContent = block.hub.name;
    $("hub-radius").textContent = `${km} km around · zip ${block.hub.zip}`;
    $("why-body").textContent = `A station could sit at the ${block.hub.name} library. It holds more batteries and GPUs than one home, and it serves the homes within ${km} km. Your questions go one short hop to a station near you, and your data stays in the neighborhood.`;
    const fact = (icon, t) => `<span class="flex items-center gap-1.5"><span class="material-symbols-outlined text-solar-green text-[18px]" aria-hidden="true">${icon}</span>${esc(t)}</span>`;
    $("hub-facts").innerHTML = [c.addresses != null && fact("home", `${fmt(c.addresses, 0)} addresses nearby`), c.homes_solar != null && fact("solar_power", `${fmt(c.homes_solar, 0)} homes with solar`), c.homes_battery != null && fact("battery_full", `${fmt(c.homes_battery, 0)} with a battery`)].filter(Boolean).join("")
      + `<span class="text-[11px] text-outline">City of Austin permits</span>`;
  }

  document.querySelectorAll(".en-mode").forEach(b => b.addEventListener("click", () => {
    draw = +b.dataset.draw;
    document.querySelectorAll(".en-mode").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    if (member) renderReserve();
  }));
  $("reserve").addEventListener("input", () => member && renderReserve());
  $("reserve-reset").addEventListener("click", () => { $("reserve").value = member.node.reserve_pct; renderReserve(); });

  Promise.all([get("../data/members.json"), get("data/block.json")]).then(([m, block]) => {
    renderStation(block);
    const members = m ? m.members : [];
    member = members.find(x => x.node && x.node.nid === nodeId) || members.find(x => x.node && x.node.nid === 3);
    if (!member) return;
    $("reserve").value = member.node.reserve_pct;
    $("tick-mine").textContent = `${member.node.reserve_pct}% (yours)`;
    sel = member.week.length - 1;
    renderTiles(); renderChart(); renderDays(); renderLog(); renderReserve();
  });
})();
