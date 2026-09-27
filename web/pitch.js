/* Track 3 pitch: audience filter for the 9-step matrix, the "How it works" local-AI demo and the mesh panel. */
(() => {
  "use strict";
  const ASK = "http://localhost:8742/ask";
  const CHIPS = ["how-long", "outage", "storm-now", "battery-today", "private"];
  const STOP = new Set("a an and are as at be by can do does for from how i if in is it my of on or the to what when where which who why will with you your me".split(" "));
  const KB_STOP = new Set("not get happens goes out need much many long base home".split(" "));
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const toks = s => String(s || "").toLowerCase().match(/[a-z0-9$%.]+/g)?.filter(t => !STOP.has(t)) || [];
  const reduced = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const state = {off: false, spike: false, reserve: false};
  let faq = null, kb = null, current = null;

  // ---------- Matrix audience filter ----------
  const tabs = document.querySelectorAll(".tab");
  const ON = "font-bold bg-primary text-on-primary".split(" "), OFF = "font-medium bg-transparent text-on-surface-variant hover:text-on-surface".split(" ");
  tabs.forEach(btn => btn.addEventListener("click", () => {
    const f = btn.dataset.filter;
    tabs.forEach(b => {
      const active = b === btn;
      b.setAttribute("aria-pressed", String(active));
      b.classList.remove(...(active ? OFF : ON)); b.classList.add(...(active ? ON : OFF));
    });
    document.querySelectorAll(".matrix-row").forEach(r => { r.hidden = !(f === "all" || r.dataset.audience === f); });
  }));

  // ---------- Answers: local model first, this browser second ----------
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
  const kbHref = n => "knowledge.html?kb=" + encodeURIComponent(n.short) + "#knowledge";
  const kbLink = n => `<a class="text-primary underline" href="${esc(kbHref(n))}">${esc(n.title)}</a>`;
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
      return n ? kbLink(n) : esc(typeof s === "string" ? s : (s.label || s.title || s.file || ""));
    }).filter(Boolean);
  }

  // ---------- Listen ----------
  function stopVoice() {
    if (window.BaseVoice) window.BaseVoice.stop();
    $("hiw-listen").setAttribute("aria-pressed", "false"); $("hiw-listen-text").textContent = "Listen"; $("hiw-listen-icon").textContent = "headphones";
  }
  $("hiw-listen").addEventListener("click", () => {
    if ($("hiw-listen").getAttribute("aria-pressed") === "true") return stopVoice();
    if (!current || !window.BaseVoice) return;
    $("hiw-listen").setAttribute("aria-pressed", "true"); $("hiw-listen-text").textContent = "Stop"; $("hiw-listen-icon").textContent = "stop_circle";
    window.BaseVoice.speak(current.a, {onend: stopVoice});
  });
  window.addEventListener("pagehide", stopVoice);

  function show(a) {
    stopVoice();
    current = a;
    $("hiw-answer").hidden = false;
    $("hiw-where").textContent = a.where;
    $("hiw-aq").textContent = a.q;
    $("hiw-aa").textContent = a.a;
    $("hiw-src").innerHTML = a.src || "";
    stateLine();
  }
  const took = ms => ms < 1 ? "under 1 ms" : ms < 1000 ? Math.round(ms) + " ms" : (ms / 1000).toFixed(1) + " s";
  const answeringStation = () => state.off ? "the next station on the same feeder" : "the station near you";
  // One line on the answer card that says what the fleet toggles changed.
  function stateLine() {
    const el = $("hiw-state"), causes = [];
    if (state.off) causes.push("Station near you offline");
    if (state.spike) causes.push("Price spike");
    if (state.reserve) causes.push("Battery at reserve");
    el.hidden = !causes.length;
    if (!causes.length) return;
    const stress = state.spike || state.reserve;
    const effect = stress ? "background jobs paused" + (state.reserve ? ", 30% backup reserve held" : "") + "; " : "";
    el.textContent = `${causes.join(" + ")}: ${effect}your question still answered by ${answeringStation()}.`;
  }

  // ---------- The hop ----------
  let hopId = 0;
  function hop() {
    const dot = $("hiw-dot"), path = $(state.off ? "hiw-pb" : "hiw-pa");
    const mine = ++hopId;
    if (reduced() || !path.getTotalLength) { dot.setAttribute("opacity", "0"); return Promise.resolve(); }
    const len = path.getTotalLength(), dur = 1400, t0 = performance.now();
    dot.setAttribute("opacity", "1");
    return new Promise(done => {
      const step = now => {
        if (mine !== hopId) return done();
        const k = Math.min(1, (now - t0) / dur);
        const d = (k < 0.5 ? k * 2 : 2 - k * 2) * len; // out to the model and back home
        const p = path.getPointAtLength(d);
        dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y);
        if (k < 1) requestAnimationFrame(step); else { dot.setAttribute("opacity", "0"); done(); }
      };
      requestAnimationFrame(step);
    });
  }

  async function ask(text) {
    text = String(text || "").trim(); if (!text) return;
    show({q: text, a: "Sending your question to the station near you...", where: "On its way"});
    const t0 = performance.now();
    const trip = hop();
    let r = null;
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 30000);
      const res = await fetch(ASK, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({q: text, page: "pitch.html"}), signal: ctl.signal});
      clearTimeout(t);
      if (res.ok) r = await res.json();
    } catch { r = null; }
    const ms = performance.now() - t0; // measured round trip for this question
    await trip;
    if (r && r.answer) {
      const rows = kbFromServer(r.sources);
      const who = r.model_calls > 0 ? "the local model at " + answeringStation() : answeringStation();
      return show({q: text, a: r.answer, where: `Answered by ${who} in ${took(ms)}`, src: rows.length ? "Sources: " + rows.join(" · ") : ""});
    }
    const l0 = performance.now();
    const it = rank(text);
    const local = () => `Answered in this browser in ${took(performance.now() - l0)}`;
    if (it) {
      const nodes = kbFor(it);
      return show({q: it.q, a: it.a + (it.number ? " (" + it.number + ")" : ""), where: local(),
        src: "Source: " + esc(String(it.source || "").replace(/\s*\([^)]*\.(?:md|json|py|csv|js)\b[^)]*\)/g, "").trim()) + (nodes.length ? " · Base Brain: " + nodes.map(kbLink).join(", ") : "")});
    }
    const nodes = kbSearch(text, 3);
    if (nodes.length) return show({q: text, a: "These Base Brain entries cover your question.", where: local(), src: "Base Brain: " + nodes.map(kbLink).join(", ")});
    show({q: text, a: "The Base team answers this one directly. Ask Base Brain for more.", where: local(), src: '<a class="text-primary underline" href="brain.html">Ask Base Brain</a>'});
  }
  $("hiw-form").addEventListener("submit", ev => { ev.preventDefault(); ask($("hiw-q").value); });

  function renderChips() {
    const box = $("hiw-chips");
    for (const id of CHIPS) {
      const it = pool().find(x => x.id === id); if (!it) continue;
      const b = document.createElement("button");
      b.type = "button"; b.textContent = it.q;
      b.className = "px-3 py-1 rounded-full bg-surface-container-low hover:bg-surface-container-high text-on-surface text-xs border border-outline cursor-pointer font-sans";
      b.addEventListener("click", () => { $("hiw-q").value = it.q; ask(it.q); });
      box.append(b);
    }
  }

  // ---------- Fleet state (shared by both panels) ----------
  const JOBS = ["RUN", "THROTTLE", "PAUSE"];
  let jobTimer = 0, jobLevel = 0;
  function setJobs(target) {
    clearTimeout(jobTimer);
    const paint = () => document.querySelectorAll("#hiw-jobs span").forEach(s => s.toggleAttribute("aria-current", s.dataset.s === JOBS[jobLevel]));
    if (reduced()) { jobLevel = target; return paint(); }
    const tick = () => { if (jobLevel === target) return paint(); jobLevel += jobLevel < target ? 1 : -1; paint(); jobTimer = setTimeout(tick, 500); };
    tick();
  }
  function tiers() {
    const stress = (state.spike ? 1 : 0) + (state.reserve ? 1 : 0);
    return {1: "RUN", 2: stress === 0 ? "RUN" : stress === 1 ? "THROTTLE" : "PAUSE", 3: stress ? "PAUSE" : "RUN", stress};
  }
  function applyState() {
    document.querySelectorAll("[data-sync]").forEach(i => { i.checked = state[i.dataset.sync]; });
    const t = tiers();
    // panel 1
    $("hiw-na-x").style.display = state.off ? "" : "none";
    $("hiw-na").setAttribute("opacity", state.off ? ".45" : "1");
    $("hiw-nb").setAttribute("opacity", state.off ? "1" : ".55");
    $("hiw-pa").setAttribute("stroke", state.off ? "#cbd5e1" : "#1e4d2b"); $("hiw-pa").setAttribute("stroke-dasharray", state.off ? "6 6" : "");
    $("hiw-pb").setAttribute("stroke", state.off ? "#1e4d2b" : "#cbd5e1"); $("hiw-pb").setAttribute("stroke-dasharray", state.off ? "" : "6 6");
    $("hiw-move").hidden = !state.off;
    $("hiw-route").textContent = state.off
      ? "The station near you is offline. Your question moves to the next station on the same feeder."
      : "Your question goes to the station on your street, and the answer comes back.";
    setJobs(t.stress ? 2 : 0);
    $("hiw-batt").style.width = state.reserve ? "30%" : "70%";
    $("hiw-batt").className = "h-full rounded-full " + (state.reserve ? "bg-warning" : "bg-tertiary");
    $("hiw-batt-label").textContent = state.reserve ? "At reserve, held for backup" : "Above reserve";
    // panel 2
    document.querySelectorAll("#mesh-queue [data-tier]").forEach(li => {
      const s = t[li.dataset.tier], el = li.querySelector(".tier-state");
      el.textContent = s;
      el.className = "tier-state font-mono text-[11px] font-bold px-1.5 py-0.5 rounded " + (s === "RUN" ? "bg-tertiary-container text-on-tertiary-container" : s === "THROTTLE" ? "bg-warning-container text-on-warning-container" : "bg-surface-container-high text-on-surface-variant");
    });
    drawMesh();
    stateLine();
  }
  // A toggle re-asks the current question so the answer card shows the new route and time.
  document.querySelectorAll("[data-sync]").forEach(i => i.addEventListener("change", () => {
    state[i.dataset.sync] = i.checked; applyState();
    if (current && current.q && !/^On its way/.test(current.where)) ask(current.q);
  }));

  // ---------- Mesh ----------
  const NS = "http://www.w3.org/2000/svg";
  const TOWER = {x: 180, y: 26};
  const STATIONS = [
    {id: "S1", feeder: "A", x: 50, y: 120, label: "Near you"}, {id: "S2", feeder: "A", x: 120, y: 175}, {id: "S3", feeder: "A", x: 50, y: 215},
    {id: "S4", feeder: "B", x: 250, y: 120}, {id: "S5", feeder: "B", x: 320, y: 175}, {id: "S6", feeder: "B", x: 250, y: 215}];
  const TIER_COLOR = {1: "#1e4d2b", 2: "#0ea5e9", 3: "#a855f7"};
  const COLOR = {running: "#22c55e", throttled: "#f59e0b", paused: "#94a3b8", offline: "#ef4444"};
  const mk = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.append(e); return e; };
  const memberStation = () => state.off ? "S2" : "S1";
  const stationState = s => (state.off && s.id === "S1") ? "offline" : ["running", "throttled", "paused"][tiers().stress];
  function drawMesh() {
    const svg = $("mesh-map"); if (!svg) return;
    [...svg.querySelectorAll(":scope > g, :scope > line, :scope > text, :scope > rect")].forEach(e => e.remove());
    const links = mk("g", {}, svg);
    for (const f of ["A", "B"]) {
      const st = STATIONS.filter(s => s.feeder === f);
      for (let i = 0; i < st.length; i++) for (let j = i + 1; j < st.length; j++) mk("line", {x1: st[i].x, y1: st[i].y, x2: st[j].x, y2: st[j].y, stroke: "#cbd5e1", "stroke-width": 2.5}, links);
      const cx = st.reduce((a, s) => a + s.x, 0) / st.length;
      mk("text", {x: cx, y: 247, "text-anchor": "middle", "font-size": 9, fill: "#64748b"}, svg).textContent = "Feeder " + f;
    }
    const lines = mk("g", {}, svg);
    for (const s of STATIONS) mk("line", {x1: TOWER.x, y1: TOWER.y + 14, x2: s.x, y2: s.y, stroke: "#e2e8f0", "stroke-width": 1, "stroke-dasharray": "3 4"}, lines);
    if (state.off) mk("line", {x1: 50, y1: 120, x2: 120, y2: 175, stroke: "#1e4d2b", "stroke-width": 3}, links);
    const tw = mk("g", {}, svg);
    mk("rect", {x: TOWER.x - 44, y: TOWER.y - 16, width: 88, height: 30, rx: 8, fill: "#1e4d2b"}, tw);
    mk("text", {x: TOWER.x, y: TOWER.y + 3, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: "#fff"}, tw).textContent = "Control tower";
    for (const s of STATIONS) {
      const g = mk("g", {"data-station": s.id}, svg);
      for (const [dx, dy] of [[-22, -14], [22, -14], [-24, 12], [24, 12]]) mk("rect", {x: s.x + dx - 4, y: s.y + dy - 4, width: 8, height: 8, rx: 1.5, fill: "#d3f5d6", stroke: "#1e4d2b", "stroke-width": 1}, g);
      const st = stationState(s);
      if (s.id === memberStation()) mk("circle", {cx: s.x, cy: s.y, r: 15, fill: "none", stroke: "#84cc16", "stroke-width": 3}, g);
      mk("circle", {cx: s.x, cy: s.y, r: 11, fill: COLOR[st], stroke: "#fff", "stroke-width": 2}, g);
      mk("text", {x: s.x, y: s.y + 3.5, "text-anchor": "middle", "font-size": 9, "font-weight": 700, fill: "#fff"}, g).textContent = s.id;
      if (s.label) mk("text", {x: s.x, y: s.y - 24, "text-anchor": "middle", "font-size": 9, "font-weight": 700, fill: "#0f172a"}, g).textContent = s.label;
    }
    mk("g", {id: "mesh-jobs"}, svg);
    const t = tiers();
    $("mesh-note").textContent = (state.off ? "S1 is offline: its work moved to S2 on the same feeder. " : "") +
      (t.stress === 0 ? "All three kinds of work run. Open-science batch uses idle GPU time." :
       t.stress === 1 ? "Open-science batch paused first; business inference throttled. Member questions keep running." :
       "Open-science batch and business inference paused. Member questions keep running; the reserve stays held.");
  }
  let flowTimer = 0;
  function dispatch() {
    const g = $("mesh-jobs"); if (!g || reduced() || document.hidden) return;
    const t = tiers(), live = STATIONS.filter(s => stationState(s) !== "offline");
    const pick = [1];
    if (t[2] === "RUN" || (t[2] === "THROTTLE" && Math.random() < 0.4)) pick.push(2);
    if (t[3] === "RUN") pick.push(3);
    const tier = pick[Math.floor(Math.random() * pick.length)];
    const dest = tier === 1 ? STATIONS.find(s => s.id === memberStation()) : live[Math.floor(Math.random() * live.length)];
    const dot = mk("circle", {r: 4, fill: TIER_COLOR[tier], cx: TOWER.x, cy: TOWER.y + 14}, g);
    const t0 = performance.now(), dur = 900;
    const step = now => {
      const k = Math.min(1, (now - t0) / dur);
      dot.setAttribute("cx", TOWER.x + (dest.x - TOWER.x) * k); dot.setAttribute("cy", TOWER.y + 14 + (dest.y - TOWER.y - 14) * k);
      if (k < 1) requestAnimationFrame(step); else dot.remove();
    };
    requestAnimationFrame(step);
  }
  function startFlow() { clearInterval(flowTimer); if (!reduced()) flowTimer = setInterval(dispatch, 700); }

  // ---------- Boot ----------
  const get = p => fetch(p).then(r => r.ok ? r.json() : null).catch(() => null);
  applyState();
  startFlow();
  if (window.matchMedia) matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", startFlow);
  Promise.all([get("data/faq.json"), get("data/kb_graph.json")]).then(([f, k]) => {
    faq = f && Array.isArray(f.items) ? f : null; kb = k && Array.isArray(k.nodes) ? k : null;
    renderChips();
    // Open with one real exchange: the first suggested question, answered through ask().
    const first = CHIPS.map(id => pool().find(x => x.id === id)).find(Boolean);
    if (first) ask(first.q);
  });
})();
