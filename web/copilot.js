/* Your home AI (chat first): the installed (compute-track) member view. Member = data/members.json node ?node= (default 3). */
(() => {
  "use strict";
  const ASK = "http://localhost:8742/ask";
  const HELP = "https://help.basepowercompany.com/";
  const TOPICS = ["My battery and the grid", "Storms and backup"];
  const EVERYDAY = ["private", "move"];
  const DRAWS = [0.5, 1, 2];
  const STOP = new Set("a an and are as at be by can do does for from how i if in is it my of on or the to what when where which who why will with you your me".split(" "));
  const KB_STOP = new Set("not get happens goes out need much many long base home".split(" "));
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const params = new URLSearchParams(location.search);
  const nodeId = Number.isFinite(+params.get("node")) && params.get("node") !== null && params.get("node") !== "" ? +params.get("node") : 3;
  const fmt = (n, d = 1) => Number(n).toLocaleString("en-US", {maximumFractionDigits: d});
  const money = n => "$" + Number(n).toFixed(2);
  const toks = s => String(s || "").toLowerCase().match(/[a-z0-9$%.]+/g)?.filter(t => !STOP.has(t)) || [];

  function ctx(raw) {
    const url = new URL(raw, location.href);
    if (url.origin === location.origin && url.pathname.endsWith(".html")) {
      url.searchParams.set("track", "compute"); url.searchParams.set("persona", "gpu"); url.searchParams.set("node", String(nodeId));
    }
    return url.href;
  }
  document.querySelectorAll("[data-ctx], #grid-link").forEach(a => a.href = ctx(a.getAttribute("href")));

  const get = p => fetch(p).then(r => r.ok ? r.json() : null).catch(() => null);
  let member = null, faq = null, kb = null, current = null;

  // ---------- Ask bar ----------
  const pool = () => faq ? faq.items.filter(it => it.audience === "member") : [];
  function rank(text) {
    const q = toks(text); if (!q.length) return null;
    let best = null, score = 0;
    for (const it of pool()) {
      const qq = it.q.toLowerCase(), h = (it.q + " " + it.a + " " + it.category + " " + (it.number || "")).toLowerCase();
      const s = q.reduce((a, t) => a + (qq.includes(t) ? 3 : 0) + (h.includes(t) ? 1 : 0), 0);
      if (s > score) { score = s; best = it; }
    }
    return best;
  }
  const kbHref = n => ctx("knowledge.html?kb=" + encodeURIComponent(n.short) + "#knowledge");
  function kbSearch(text, k = 2) {
    if (!kb) return [];
    const q = [...new Set(toks(text).filter(t => !KB_STOP.has(t) && t.length > 2))];
    if (!q.length) return [];
    return kb.nodes.filter(n => !["gap", "job", "persona"].includes(n.type)).map(n => {
      const t = n.title.toLowerCase(), s = (n.summary || "").toLowerCase();
      const hit = q.filter(x => t.includes(x) || s.includes(x));
      return [hit.length >= Math.min(2, q.length) && q.some(x => t.includes(x)) ? q.reduce((a, x) => a + (t.includes(x) ? 3 : 0) + (s.includes(x) ? 1 : 0), 0) : 0, n];
    }).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0]).slice(0, k).map(x => x[1]);
  }
  function kbFor(it) {
    if (!kb) return [];
    const out = kb.nodes.filter(n => n.path && (it.data || []).some(d => d.includes(n.path) || n.path.includes(d))).slice(0, 1);
    for (const n of kbSearch(it.q, 2)) if (out.length < 2 && !out.includes(n)) out.push(n);
    return out;
  }
  function kbFromServer(sources) {
    return (sources || []).slice(0, 4).map(s => {
      const key = typeof s === "string" ? s : (s.slug || s.path || s.file || s.label || s.title || "");
      const n = kb && key ? kb.nodes.find(n => n.slug === key || n.short === key || n.path === key || n.title === key || (n.path && key.includes(n.path)) || key.endsWith(": " + n.slug)) : null;
      return n ? `<a class="cp-link" href="${esc(kbHref(n))}">${esc(n.title)}</a>` : esc(typeof s === "string" ? s : (s.label || s.title || s.file || ""));
    }).filter(Boolean);
  }
  // ---------- Chat ----------
  const stream = $("chat-stream");
  let speaking = null;
  const icon = (n, c = "") => `<span class="material-symbols-outlined text-[16px] ${c}" aria-hidden="true">${n}</span>`;
  function addUser(text) {
    $("chat-empty").hidden = true; $("chat-clear").hidden = false;
    const d = document.createElement("div");
    d.className = "flex flex-col gap-1 max-w-[85%] self-end items-end";
    d.innerHTML = `<div class="bg-primary-container text-white rounded-xl rounded-tr-none px-4 py-2.5 font-body-md text-body-md" style="overflow-wrap:anywhere">${esc(text)}</div>`;
    stream.append(d);
  }
  function addBot() {
    const d = document.createElement("div");
    d.className = "cp-bot flex items-start gap-3 max-w-full sm:max-w-[92%]";
    d.innerHTML = `<div class="w-7 h-7 rounded-md bg-secondary-container text-primary-container flex items-center justify-center shrink-0 mt-1">${icon("bolt")}</div>
      <div class="flex flex-col gap-1.5 min-w-0"><div class="bg-white border border-wire-border rounded-xl rounded-tl-none p-4 flex flex-col gap-2">
      <span class="cp-kicker font-label-caps text-label-caps uppercase tracking-wider text-primary-container">Base Brain</span>
      <p class="cp-a font-body-md text-body-md text-ink-primary" style="overflow-wrap:anywhere">Finding your answer...</p>
      <div class="cp-src flex items-start gap-1.5 font-body-sm text-body-sm text-on-surface-variant" hidden>${icon("policy", "text-solar-green")}<span class="min-w-0"></span></div></div>
      <div class="flex flex-wrap items-center gap-3 px-1 font-body-sm text-[11px] text-on-surface-variant">
      <span class="cp-where inline-flex items-center gap-1">${icon("lock", "text-solar-green !text-[14px]")}<span></span></span>
      <span class="cp-read cp-mono text-[10px] text-on-surface-variant"></span>
      <button type="button" class="cp-listen inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white border border-wire-border text-primary-container font-label-md text-[12px]" aria-pressed="false" hidden><span class="material-symbols-outlined text-[16px]" aria-hidden="true">headphones</span><span>Listen</span></button></div></div>`;
    stream.append(d); stream.scrollTop = stream.scrollHeight;
    return d;
  }
  function fill(el, a, where) {
    el.querySelector(".cp-kicker").textContent = a.kicker || "Base Brain";
    el.querySelector(".cp-a").textContent = a.a;
    const s = el.querySelector(".cp-src"); s.hidden = !a.src; s.querySelector("span.min-w-0").innerHTML = a.src || "";
    el.querySelector(".cp-where span:last-child").textContent = where;
    el.querySelector(".cp-read").textContent = [member && member.node ? "Feeder " + member.node.feeder : "", (a.src.match(/<a /g) || []).length ? (a.src.match(/<a /g) || []).length + " linked sources" : ""].filter(Boolean).join(" • ");
    $("privacy").textContent = where;
    const l = el.querySelector(".cp-listen"); l.hidden = !window.BaseVoice;
    l.onclick = () => { if (speaking === l) return stopVoice(); stopVoice(); if (!window.BaseVoice) return; speaking = l; setListen(l, true); window.BaseVoice.speak(a.q + ". " + a.a, {onend: stopVoice}); };
    current = a;
    document.querySelectorAll(".inquiry-pill").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.id === a.id)));
    stream.scrollTop = stream.scrollHeight;
  }
  function fromItem(it) {
    const nodes = kbFor(it);
    const src = "Source: " + esc(String(it.source || "").replace(/\s*\([^)]*\.(?:md|json|py|csv|js)\b[^)]*\)/g, "").trim()) + (it.source_url ? ` (<a class="cp-link" href="${esc(it.source_url)}" target="_blank" rel="noopener">page</a>)` : "")
      + (nodes.length ? " · Base Brain: " + nodes.map(n => `<a class="cp-link" href="${esc(kbHref(n))}">${esc(n.title)}</a>`).join(", ") : "");
    return {id: it.id, kicker: it.category, q: it.q, a: it.a + (it.number ? " (" + it.number + ")" : ""), src};
  }
  async function ask(text) {
    text = text.trim(); if (!text) return;
    stopVoice(); addUser(text); $("brain-search-input").value = "";
    const el = addBot();
    let r = null;
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 30000);
      const res = await fetch(ASK, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({q: text, page: "copilot.html"}), signal: ctl.signal});
      clearTimeout(t);
      if (res.ok) r = await res.json();
    } catch (e) { r = null; }
    if (r && r.answer) {
      const rows = kbFromServer(r.sources);
      return fill(el, {q: text, a: r.answer, src: rows.length ? "Sources: " + rows.join(" · ") : "Base Brain"}, "Answered on your home’s PC.");
    }
    const where = "Answered in this browser.";
    const it = rank(text);
    if (it) return fill(el, Object.assign(fromItem(it), {q: text, kicker: (it.category || "Base Brain") + " · " + it.q}), where);
    const nodes = kbSearch(text, 3);
    if (nodes.length) return fill(el, {q: text, a: "These Base Brain entries cover your question.", src: "Base Brain: " + nodes.map(n => `<a class="cp-link" href="${esc(kbHref(n))}">${esc(n.title)}</a>`).join(", ")}, where);
    fill(el, {q: text, a: "The Base team can answer this one directly.", src: `<a class="cp-link" href="${HELP}" target="_blank" rel="noopener">Open Base Help Center</a>`}, where);
  }
  $("ask-form").addEventListener("submit", ev => { ev.preventDefault(); ask($("brain-search-input").value); });
  $("chat-clear").addEventListener("click", () => {
    stopVoice(); stream.querySelectorAll(":scope > :not(#chat-empty)").forEach(x => x.remove());
    $("chat-empty").hidden = false; $("chat-clear").hidden = true; $("privacy").textContent = "Your questions stay at home.";
    document.querySelectorAll(".inquiry-pill").forEach(b => b.setAttribute("aria-pressed", "false"));
  });
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Rec) {
    $("mic").classList.remove("hidden"); $("mic").classList.add("inline-flex");
    $("mic").addEventListener("click", () => {
      const r = new Rec(); r.lang = "en-US"; r.interimResults = false;
      r.onresult = ev => ask(ev.results[0][0].transcript);
      try { r.start(); } catch (e) {}
    });
  }

  // Listen (speak.js)
  function setListen(b, on) {
    b.setAttribute("aria-pressed", String(on));
    b.children[0].textContent = on ? "stop_circle" : "headphones"; b.children[1].textContent = on ? "Stop" : "Listen";
  }
  function stopVoice() {
    if (window.BaseVoice) window.BaseVoice.stop();
    if (speaking) setListen(speaking, false);
    speaking = null;
  }
  window.addEventListener("pagehide", stopVoice);

  function renderPills() {
    const box = $("pills");
    for (const it of pool().filter(it => TOPICS.includes(it.category) || EVERYDAY.includes(it.id)).filter(it => ["how-long", "storm-now", "battery-today", "private", "move"].includes(it.id))) {
      const b = document.createElement("button");
      b.type = "button"; b.dataset.id = it.id; b.setAttribute("aria-pressed", "false");
      b.className = "inquiry-pill px-3 py-1.5 rounded-full bg-surface-muted border border-wire-border hover:bg-secondary-container text-ink-primary font-body-sm text-body-sm transition-colors text-left";
      b.textContent = it.q;
      b.addEventListener("click", () => { stopVoice(); addUser(it.q); fill(addBot(), fromItem(it), "Answered in this browser."); });
      box.append(b);
    }
  }

  // ---------- Status chip ----------
  function renderStatus(sig) {
    if (!sig) { $("status-title").textContent = "Status updates hourly"; return; }
    const r = Object.fromEntries(sig.rules.map(x => [x.name, x.now]));
    const alerts = r.storm_alert ? r.storm_alert.value : 0, prc = r.low_reserves ? r.low_reserves.value : null;
    const calm = !alerts && (prc === null || prc >= 3000);
    $("status-title").textContent = calm ? "Grid normal · No weather alerts" : alerts ? `${alerts} weather alert${alerts > 1 ? "s" : ""} active` : "Grid reserves are low";
    if (!calm) { $("status-icon").textContent = "warning"; $("status-dot").className = "w-9 h-9 rounded-md bg-warning-amber/15 flex items-center justify-center text-warning-amber shrink-0"; }
    const at = r.storm_alert && r.storm_alert.as_of ? new Date(r.storm_alert.as_of) : new Date(sig.built_at);
    $("status-note").textContent = (prc !== null ? `ERCOT reserves ${fmt(prc, 0)} MW · ` : "") + "Travis and Williamson NWS alerts · as of " +
      at.toLocaleString("en-US", {month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago"}) + " CT";
  }

  // ---------- Backup math + chart ----------
  function renderBackup() {
    const n = member.node, draw = DRAWS[+$("draw").value];
    const usable = n.battery_kwh - n.reserve_kwh, hours = usable / draw;
    $("draw-label").textContent = draw + " kW"; $("draw").setAttribute("aria-valuetext", draw + " kW");
    $("hours").textContent = fmt(hours) + " hours";
    $("hours-at").textContent = `at ${draw} kW of essentials`;
    $("backup-chip").textContent = `${n.reserve_pct}% kept in reserve`;
    $("hero-hours").textContent = `${fmt(usable)} hours from full`;
    if (member.totals) $("hero-week").textContent = `This week: ${money(member.totals.battery_usd + member.totals.gpu_usd)} value`;
    $("math").innerHTML = `Your <strong class="text-ink-primary font-headline-sm">${fmt(n.battery_kwh)} kWh</strong> battery, starting full, keeps a <strong class="text-ink-primary font-headline-sm">${n.reserve_pct}% reserve (${fmt(n.reserve_kwh, 2)} kWh)</strong>. That leaves <strong class="text-ink-primary font-headline-sm">${fmt(usable, 2)} kWh</strong> for your home. ${fmt(usable, 2)} kWh ÷ ${draw} kW = <strong class="text-ink-primary font-headline-sm">${fmt(hours)} hours</strong>. The reserve then carries you further.`;
    const X = 540, Y = 160, top = 12, bot = 148, span = Math.max(48, Math.ceil(hours / 12) * 12);
    const y = kwh => bot - (kwh / n.battery_kwh) * (bot - top), x = h => (h / span) * X;
    const yr = y(n.reserve_kwh), xe = x(hours);
    const grid = [0.25, 0.5, 0.75].map(f => `<line x1="0" x2="${X}" y1="${top + f * (bot - top)}" y2="${top + f * (bot - top)}" stroke="#c1c9be" stroke-opacity=".5" stroke-width="1" vector-effect="non-scaling-stroke"/>`).join("");
    $("chart").innerHTML = `<defs><linearGradient id="depletionGrad" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#1e4d2b" stop-opacity="0.22"/><stop offset="100%" stop-color="#1e4d2b" stop-opacity="0"/></linearGradient></defs>${grid}
      <line x1="0" x2="${X}" y1="${yr}" y2="${yr}" stroke="#F59E0B" stroke-dasharray="4,4" stroke-width="2" vector-effect="non-scaling-stroke"/>
      <polygon fill="url(#depletionGrad)" points="0,${y(n.battery_kwh)} ${xe},${yr} ${xe},${Y} 0,${Y}"/>
      <path d="M0,${y(n.battery_kwh)} L${xe},${yr}" fill="none" stroke="#1e4d2b" stroke-linecap="round" stroke-width="3" vector-effect="non-scaling-stroke"/>
      <path d="M${xe},${yr} L${Math.min(X, x(hours + n.reserve_kwh / draw))},${y(0)}" fill="none" stroke="#1e4d2b" stroke-opacity=".35" stroke-dasharray="3,3" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
    $("chart").setAttribute("aria-label", `Battery energy falls from ${fmt(n.battery_kwh)} kWh to the ${fmt(n.reserve_kwh, 2)} kWh reserve floor in ${fmt(hours)} hours at ${draw} kW`);
    $("chart-labels").innerHTML = `<span>Hour 0 (full)</span><span class="text-primary-container font-label-md">Reserve floor at hour ${fmt(hours)}</span><span>Hour ${span}</span>`;
  }

  // ---------- Week events ----------
  function renderDays() {
    const seen = new Set(), days = member.week.filter(d => !seen.has(d.date) && seen.add(d.date));
    days.sort((a, b) => a.date.localeCompare(b.date));
    const box = $("days");
    days.forEach((d, i) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "cp-kw px-2.5 py-1 rounded-full bg-surface-muted hover:bg-surface-subtle font-label-md text-label-md text-ink-primary";
      b.textContent = new Date(d.date + "T12:00:00").toLocaleDateString("en-US", {month: "short", day: "numeric"});
      b.addEventListener("click", () => { box.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); renderDay(d); });
      b.setAttribute("aria-pressed", String(i === days.length - 1));
      box.append(b);
    });
    renderDay(days[days.length - 1]);
  }
  const KINDS = {member: ["Member questions", "#1e4d2b"], business: ["Business inference", "#4a6700"], base: ["Base fleet work", "#63c479"], external: ["Open-science batch", "#afd367"]};
  const span = e => { const m = e.match(/(\d\d):(\d\d)-(\d\d):(\d\d)/); return m ? [+m[1] + m[2] / 60, +m[3] + m[4] / 60] : null; };
  const seg = ([s, e], color, title) => `<div class="absolute top-0 bottom-0" style="left:${(s / 24 * 100).toFixed(2)}%;width:${((e - s) / 24 * 100).toFixed(2)}%;background:${color}" title="${esc(title)}"></div>`;
  function renderDay(d) {
    const ev = d.events;
    const pick = re => ev.filter(e => re.test(e));
    const gpu = pick(/^GPU ran/), chg = pick(/^charged/), dis = pick(/^discharged/);
    const label = new Date(d.date + "T12:00:00").toLocaleDateString("en-US", {month: "short", day: "numeric"});
    // Lanes
    $("lane-bat").innerHTML = chg.map(e => span(e) && seg(span(e), "#84CC16", e)).join("") + dis.map(e => span(e) && seg(span(e), "#1e4d2b", e)).join("");
    $("lane-gpu").innerHTML = gpu.map(e => { const k = (e.match(/a (\w+) job/) || [])[1]; return span(e) && seg(span(e), (KINDS[k] || ["", "#94a3b8"])[1], (KINDS[k] || [k])[0] + " " + (e.match(/\d\d:\d\d-\d\d:\d\d/) || [""])[0]); }).join("");
    const used = [...new Set(gpu.map(e => (e.match(/a (\w+) job/) || [])[1]).filter(k => KINDS[k]))];
    const dot = (c, t) => `<span class="inline-flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm" style="background:${c}" aria-hidden="true"></span>${esc(t)}</span>`;
    $("flow-key").innerHTML = dot("#84CC16", "Charging") + dot("#1e4d2b", "Sending power back") + used.map(k => dot(KINDS[k][1], KINDS[k][0])).join("");
    // Summary rows
    const rows = [];
    for (const e of chg) rows.push(["battery_charging_full", "Charged when power was cheap", e.replace(/^charged/, "Charged")]);
    for (const e of dis) rows.push(["bolt", "Sent power back when the grid paid more", e.replace(/^discharged/, "Sent power")]);
    if (gpu.length) rows.push(["memory", `Ran compute jobs for ${d.gpu_hours} hours`, `${gpu.length} jobs: ${used.map(k => KINDS[k][0].toLowerCase()).join(", ")}.`]);
    for (const e of pick(/^reserve/)) rows.push(["shield", "Kept your backup reserve", e.replace(/^reserve floor/, "Reserve floor")]);
    rows.push(["savings", "Value for the day", `Battery ${money(d.battery_usd)} · compute ${money(d.gpu_usd)}`]);
    $("auto").innerHTML = rows.map(([icon, t, s]) => `<div class="flex items-start p-3 rounded-lg bg-surface-muted border border-wire-border gap-3">
      <div class="w-8 h-8 rounded-lg bg-white border border-wire-border text-primary-container flex items-center justify-center shrink-0"><span class="material-symbols-outlined text-[18px]" aria-hidden="true">${icon}</span></div>
      <div class="flex flex-col min-w-0"><span class="font-label-md text-label-md text-ink-primary">${esc(t)}</span><span class="font-body-sm text-body-sm text-on-surface-variant" style="overflow-wrap:anywhere">${esc(s)}</span></div></div>`).join("");
    // Reserve card
    const n = member.node, low = d.reserve_min_pct;
    $("res-pct").textContent = fmt(low, 0) + "%";
    $("hw-badge").textContent = `Lowest charge on ${label}`;
    $("res-bar").innerHTML = `<div class="bg-primary-container flex items-center justify-center" style="width:${n.reserve_pct}%" title="Backup reserve ${n.reserve_pct}%"><span class="material-symbols-outlined text-[14px] text-white" aria-hidden="true">lock</span></div>`
      + (low > n.reserve_pct ? `<div class="bg-energy-lime flex items-center justify-center" style="width:${low - n.reserve_pct}%" title="Above the reserve at the low point"></div>` : "");
    $("res-bar").setAttribute("aria-label", `Reserve ${n.reserve_pct}%, lowest charge ${fmt(low, 0)}% on ${label}`);
    $("res-floor-t").textContent = `${n.reserve_pct}% backup reserve`;
    $("res-floor-s").textContent = `${fmt(n.reserve_kwh, 2)} kWh kept for outages.`;
    $("res-low-t").textContent = `${fmt(low, 0)}% lowest point`;
    $("res-low-s").textContent = low >= n.reserve_pct ? "The reserve held all day." : "Below the reserve that day.";
  }

  // ---------- Hardware ----------
  function renderSpecs() {
    const n = member.node;
    $("hero-feeder").textContent = "Feeder " + n.feeder;
    const cell = (k, v, s) => `<div class="p-3 rounded-lg bg-surface-muted border border-wire-border flex flex-col gap-0.5 min-w-0"><span class="font-label-caps text-label-caps uppercase text-outline">${k}</span><span class="font-label-md text-label-md text-ink-primary" style="overflow-wrap:anywhere">${v}</span><span class="font-body-sm text-[11px] text-on-surface-variant">${s}</span></div>`;
    $("specs").innerHTML = cell("Battery", `${fmt(n.battery_kwh)} kWh`, "Base Core")
      + cell("Power rate", `${fmt(n.rate_kw)} kW`, "Charge and discharge")
      + cell("Feeder", esc(n.feeder), `${esc(n.region)} region`)
      + cell("Compute this week", `${fmt(member.totals.gpu_hours, 0)} hours`, `${money(member.totals.gpu_usd)} value`);
    const safe = faq && faq.items.find(i => i.id === "safe");
    if (safe) $("safety").textContent = safe.a;
  }

  // ---------- Station near you ----------
  function renderStation(b) {
    if (b && b.hub) { $("hub-hw-chip").textContent = b.hub.name + " station"; $("hub-hw-ring").textContent = `Station ring: ${fmt(b.radius_m / 1000)} km · ${fmt(b.counts.addresses, 0)} addresses`; }
    if (!b || !b.hub) return;
    const h = b.hub, c = b.counts || {};
    $("station-title").textContent = h.name;
    $("station-note").textContent = `An example station site: this ${h.kind} could hold more batteries and PCs than one house and serve the member homes around it.`;
    const row = (k, v, tag) => `<div class="flex items-center justify-between gap-2 py-1.5 px-3 rounded bg-surface-muted border border-wire-border font-body-sm text-body-sm"><span class="text-on-surface-variant">${k}</span><span class="font-label-md text-label-md text-ink-primary text-right">${v}${tag ? ` <span class="ml-1 px-1.5 py-0.5 rounded bg-secondary-container text-primary-container text-[10px]">${tag}</span>` : ""}</span></div>`;
    const km = fmt((b.radius_m || 0) / 1000, 1);
    $("station-rows").innerHTML = row("Location", `Zip ${esc(h.zip)}${member && member.zip === h.zip ? ", same as your home" : ""}`)
      + row(`Addresses within ${km} km`, fmt(c.addresses, 0), "Measured")
      + row("Homes with solar", fmt(c.homes_solar, 0))
      + row("Homes with a battery", fmt(c.homes_battery, 0))
      + `<p class="font-body-sm text-[11px] text-outline px-1">${esc(String(h.source || "").replace(/\s*\(.*$/, ""))}; City of Austin permits (${fmt(c.permits, 0)} in the area).</p>`;
  }

  // ---------- Home records ----------
  function renderRecords(cohort, members) {
    const box = $("records");
    const srcs = new Set(Object.values(member.fields || {}).map(f => f.source));
    const fromCohort = (member.scaffolded_from || []).some(s => s.startsWith("house/cohort.json"));
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    const cands = fromCohort && cohort ? cohort.filter(h => h.zip === member.zip && same(h.year_built, member.year_built)
      && same(new Set(h.guessable.map(g => g.source)).size, srcs.size) && h.guessable.every(g => srcs.has(g.source))) : [];
    const idx = members.indexOf(member);
    const home = cands.length === 1 ? cands[0] : cands.find(h => cohort.indexOf(h) === idx);
    if (!home) { box.innerHTML = `<p class="font-body-sm text-body-sm text-on-surface-variant">Your permit history appears here once the city records are linked.</p>`; return; }
    const yb = typeof home.year_built === "object" ? `first permit ${home.year_built.lower_bound}` : `built ${home.year_built}`;
    $("rec-note").textContent = `Zip ${home.zip} · ${yb} · ${home.events.length} permits on file`;
    const KIND = {service_upgrade: "Electrical service", solar: "Solar", battery: "Battery", generator: "Generator", ac_changeout: "AC change-out", remodel: "Remodel", addition: "Addition", pool: "Pool", built: "New build", demolition: "Demolition", demolition_accessory: "Demolition", temp_power: "Temporary power", other: "Other work"};
    const ICON = {service_upgrade: "electrical_services", solar: "solar_power", battery: "battery_full", generator: "power", ac_changeout: "mode_fan"};
    const rows = home.events.slice().sort((a, b) => b.date.localeCompare(a.date));
    const draw = all => {
      box.innerHTML = (all ? rows : rows.slice(0, 5)).map(e => `<div class="flex items-center justify-between p-space-sm rounded-lg hover:bg-surface-muted transition-colors">
        <div class="flex items-center gap-space-sm min-w-0"><div class="w-8 h-8 rounded-lg bg-surface-container-high text-primary flex items-center justify-center shrink-0"><span class="material-symbols-outlined text-[18px]" aria-hidden="true">${ICON[e.kind] || "description"}</span></div>
        <div class="flex flex-col min-w-0"><span class="font-headline-sm text-headline-sm text-ink-primary truncate">${esc(KIND[e.kind] || "Permit")} · ${esc(e.permit)}</span>
        <span class="font-body-sm text-body-sm text-outline truncate" title="${esc(e.text)}">${esc(e.date.slice(0, 10))} · ${esc(e.text.toLowerCase())}</span></div></div></div>`).join("");
      $("rec-more").hidden = rows.length <= 5;
      $("rec-more").textContent = all ? "Show the latest 5" : `Show all ${rows.length} permits`;
      $("rec-more").onclick = () => draw(!all);
    };
    draw(false);
  }

  // ---------- Grid today ----------
  function renderGrid(g) {
    if (!g) { $("grid-title").textContent = "Today’s prices update each morning"; return; }
    const dam = g.prices.dam.map(r => [r.he, r.LZ_AEN]);
    const lo = dam.reduce((a, b) => b[1] < a[1] ? b : a), hi = dam.reduce((a, b) => b[1] > a[1] ? b : a);
    const hr = he => new Date(2000, 0, 1, he - 1).toLocaleTimeString("en-US", {hour: "numeric"}).replace(":00", "");
    const b = g.battery;
    $("grid-title").textContent = g.conditions ? g.conditions.title : `Austin prices for ${g.date}`;
    $("grid-note").textContent = `Austin day-ahead price: lowest ${fmt(lo[1], 2)} $/MWh at ${hr(lo[0])}, highest ${fmt(hi[1], 2)} $/MWh at ${hr(hi[0])}.`
      + (b ? ` Plan: charge ${hr(b.charge_he[0])} to ${hr(b.charge_he[b.charge_he.length - 1] + 1)}, send back ${hr(b.discharge_he[0])} to ${hr(b.discharge_he[b.discharge_he.length - 1] + 1)}.` : "")
      + ` ERCOT, ${g.date}, as of ${new Date(g.as_of).toLocaleTimeString("en-US", {hour: "numeric", minute: "2-digit", timeZone: "America/Chicago"})} CT.`;
  }

  // ---------- Load ----------
  $("draw").addEventListener("input", () => member && renderBackup());
  Promise.all([get("../data/members.json"), get("data/faq.json"), get("data/kb_graph.json"), get("data/signals.json"), get("data/grid_today.json"), get("../house/cohort.json"), get("data/block.json")])
    .then(([m, f, k, sig, g, cohort, blk]) => {
      faq = f; kb = k;
      renderPills(); renderStatus(sig); renderGrid(g);
      const members = m ? m.members : [];
      member = members.find(x => x.node && x.node.nid === nodeId) || members.find(x => x.node && x.node.nid === 3);
      renderStation(blk);
      if (!member) return;
      renderBackup(); renderDays(); renderSpecs(); renderRecords(cohort, members);
      const first = $("pills").querySelector(".inquiry-pill");
      if (first && !stream.querySelector(".cp-bot")) first.click();
    });
})();
