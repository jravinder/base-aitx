/* Local models console: status bar, live answer pipeline (code routes, a WebLLM model in this browser, or the ask server on your PC), runtimes with install steps, measured model registry. */
(() => {
  "use strict";
  const ASK = "http://localhost:8742", TTS = "http://localhost:8744", LOCAL_PAGES = "http://localhost:8741/web/models.html#try";
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const calm = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const params = new URLSearchParams(location.search);
  const nodeId = /^\d+$/.test(params.get("node") || "") ? params.get("node") : "3";
  function ctx(raw) {
    const url = new URL(raw, location.href);
    if (url.origin === location.origin && url.pathname.endsWith(".html")) {
      url.searchParams.set("track", "compute"); url.searchParams.set("persona", "gpu"); url.searchParams.set("node", nodeId);
    }
    return url.href;
  }
  document.querySelectorAll("[data-ctx]").forEach(a => a.href = ctx(a.getAttribute("href")));

  // ---------- Particle brain ----------
  class Brain {
    constructor(canvas) {
      this.c = canvas; this.g = canvas.getContext("2d"); this.heat = 0; this.target = 0; this.sparks = []; this.visible = true; this.raf = 0;
      this.seed();
      new ResizeObserver(() => this.size()).observe(canvas);
      new IntersectionObserver(es => { this.visible = es[0].isIntersecting; this.kick(); }).observe(canvas);
      this.size();
    }
    seed() {
      // Two lobes and a small cerebellum, filled by rejection sampling (fixed seed so every load looks the same).
      let s = 7; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
      const inside = (x, y) => ((x + .28) / .52) ** 2 + (y / .5) ** 2 < 1 || ((x - .22) / .5) ** 2 + ((y + .04) / .52) ** 2 < 1 || ((x - .42) / .2) ** 2 + ((y - .46) / .14) ** 2 < 1;
      this.p = [];
      while (this.p.length < 150) {
        const x = rnd() * 2 - 1, y = rnd() * 2 - 1;
        if (inside(x, y)) this.p.push({x, y, ph: rnd() * 6.28, glow: 0});
      }
      this.links = [];
      for (let i = 0; i < this.p.length; i++) for (let j = i + 1; j < this.p.length; j++) {
        const a = this.p[i], b = this.p[j];
        if ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 < .045) this.links.push([i, j]);
      }
    }
    size() {
      const r = this.c.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2);
      if (!r.width || !r.height) return;
      this.c.width = Math.round(r.width * d); this.c.height = Math.round(r.height * d);
      this.g.setTransform(d, 0, 0, d, 0, 0); this.w = r.width; this.h = r.height;
      this.draw(performance.now());
    }
    think(on) { this.target = on ? 1 : 0; if (calm()) { this.heat = this.target; this.draw(0); } else this.kick(); }
    kick() { if (!this.raf && this.visible && !calm()) this.raf = requestAnimationFrame(t => this.loop(t)); }
    loop(t) {
      this.raf = 0;
      this.heat += (this.target - this.heat) * .06;
      if (this.heat > .05 && Math.random() < this.heat * .5) {
        const [i, j] = this.links[Math.floor(Math.random() * this.links.length)];
        this.sparks.push({i, j, t: 0});
      }
      this.sparks = this.sparks.filter(s => (s.t += .035) < 1);
      this.draw(t);
      if (this.visible) this.raf = requestAnimationFrame(tt => this.loop(tt));
    }
    pos(p, t) {
      const m = Math.min(this.w, this.h * 1.35) * .42, still = calm();
      const wob = still ? 0 : .012 + this.heat * .01;
      return [this.w / 2 + (p.x + Math.sin(t / 1400 + p.ph) * wob) * m, this.h / 2 + (p.y + Math.cos(t / 1700 + p.ph) * wob) * m * .95];
    }
    draw(t) {
      const g = this.g, h = this.heat;
      if (!this.w) return;
      g.clearRect(0, 0, this.w, this.h);
      const xy = this.p.map(p => this.pos(p, t));
      g.lineWidth = 1;
      g.strokeStyle = `rgba(30,77,43,${.12 + h * .14})`;
      g.beginPath();
      for (const [i, j] of this.links) { g.moveTo(xy[i][0], xy[i][1]); g.lineTo(xy[j][0], xy[j][1]); }
      g.stroke();
      for (const s of this.sparks) {
        const a = xy[s.i], b = xy[s.j], x = a[0] + (b[0] - a[0]) * s.t, y = a[1] + (b[1] - a[1]) * s.t;
        this.p[s.j].glow = Math.max(this.p[s.j].glow, s.t);
        g.fillStyle = "rgba(132,204,22,.95)"; g.beginPath(); g.arc(x, y, 2.6 * Math.min(1, this.w / 320), 0, 6.3); g.fill();
      }
      this.p.forEach((p, i) => {
        const pulse = calm() ? h * ((i % 3) === 0 ? 1 : 0) : Math.max(p.glow, h * (.5 + .5 * Math.sin(t / 260 + p.ph)) * .6);
        p.glow *= .93;
        g.fillStyle = pulse > .35 ? `rgba(132,204,22,${.55 + pulse * .45})` : "rgba(30,77,43,.78)";
        g.beginPath(); g.arc(xy[i][0], xy[i][1], (2.2 + pulse * 2.2) * Math.min(1, this.w / 320), 0, 6.3); g.fill();
      });
    }
  }
  // ---------- Data ----------
  const get = p => fetch(p).then(r => r.ok ? r.json() : null).catch(() => null);
  let faq = null, kb = null;
  const members = () => faq ? faq.items.filter(it => it.audience === "member" && it.a) : [];
  const STOP = new Set("a an and are as at be can do does for from how i if in is it my of on or the to what when where which who why will with you your me we our this that".split(" "));
  const words = t => new Set((String(t).toLowerCase().match(/[a-z0-9]+/g) || []).filter(w => !STOP.has(w) && w.length > 1));
  // Same rule as brain/ask.py faq_hit: most of the asker's words, floor 0.6.
  function faqHit(q) {
    const asked = words(q); if (asked.size < 2) return null;
    let best = null, score = 0;
    for (const it of members()) {
      const have = words(it.q); if (!have.size) continue;
      const s = [...asked].filter(w => have.has(w)).length / Math.max(asked.size, have.size);
      if (s > score) { best = it; score = s; }
    }
    return score >= .6 ? best : null;
  }
  const KB_STOP = new Set("not get happens goes out need much many long base home".split(" "));
  function kbSearch(q) {
    if (!kb) return null;
    const t = [...words(q)].filter(x => !KB_STOP.has(x) && x.length > 2);
    if (!t.length) return null;
    let best = null, score = 0;
    for (const n of kb.nodes) {
      if (["gap", "job", "persona"].includes(n.type)) continue;
      const ti = n.title.toLowerCase(), su = (n.summary || "").toLowerCase();
      const hit = t.filter(x => ti.includes(x) || su.includes(x));
      if (hit.length < Math.min(2, t.length) || !t.some(x => ti.includes(x))) continue;
      const s = t.reduce((a, x) => a + (ti.includes(x) ? 3 : 0) + (su.includes(x) ? 1 : 0), 0);
      if (s > score) { best = n; score = s; }
    }
    return best;
  }
  function looseFaq(q) {
    const t = [...words(q)]; let best = null, score = 0;
    for (const it of members()) {
      const qq = it.q.toLowerCase(), h = (it.q + " " + it.a).toLowerCase();
      const s = t.reduce((a, x) => a + (qq.includes(x) ? 3 : 0) + (h.includes(x) ? 1 : 0), 0);
      if (s > score) { best = it; score = s; }
    }
    return score >= 4 ? best : null;
  }
  const kbNode = key => kb && key ? kb.nodes.find(n => n.slug === key || n.short === key || key.endsWith(": " + n.slug) || key.endsWith(": " + n.short)) : null;
  const kbHref = n => ctx("knowledge.html?kb=" + encodeURIComponent(n.short) + "#knowledge");
  const kbFor = it => kb ? kb.nodes.filter(n => n.path && (it.data || []).some(d => d.includes(n.path) || n.path.includes(d))).slice(0, 2) : [];

  const brain = new Brain($("live-brain"));
  function thinking(on, text) { brain.think(on); if (text) $("st-last-sub").textContent = text; }
  function stat(id, state, val, sub) {
    const el = $(id), led = el.querySelector(".led"); if (led) led.dataset.s = state; el.querySelector(".val").textContent = val;
    if (sub != null) el.querySelector(".s").textContent = sub;
  }

  // ---------- Retrieval for the browser model: top 3 of faq.json + kb_graph.json ----------
  function top3(q) {
    const t = [...words(q)].filter(x => !KB_STOP.has(x) && x.length > 2);
    if (!t.length) return [];
    const hits = [];
    for (const it of members()) {
      const qq = it.q.toLowerCase(), aa = it.a.toLowerCase();
      const s = t.reduce((a, x) => a + (qq.includes(x) ? 3 : 0) + (aa.includes(x) ? 1 : 0), 0);
      if (s >= 3) hits.push({s, title: it.q, text: it.a, faq: it});
    }
    for (const n of kb ? kb.nodes : []) {
      if (["gap", "job", "persona"].includes(n.type) || !n.summary) continue;
      const ti = n.title.toLowerCase(), su = n.summary.toLowerCase();
      const s = t.reduce((a, x) => a + (ti.includes(x) ? 3 : 0) + (su.includes(x) ? 1 : 0), 0);
      if (s >= 3) hits.push({s, title: n.title, text: n.summary, node: n});
    }
    return hits.sort((a, b) => b.s - a.s).slice(0, 3);
  }
  function sourceHtml(h, i) {
    const n = h.node || (h.faq ? kbFor(h.faq)[0] : null);
    const link = n ? `<a class="text-primary-container font-semibold underline underline-offset-2" href="${esc(kbHref(n))}">${esc(h.title)}</a>`
      : h.faq && h.faq.source_url ? `<a class="text-primary-container font-semibold underline underline-offset-2" href="${esc(h.faq.source_url)}" target="_blank" rel="noopener">${esc(h.title)}</a>` : `<span>${esc(h.title)}</span>`;
    return `<li class="flex gap-2"><span class="font-label-md text-primary-container">[${i + 1}]</span>${link}<span class="text-outline">${h.node ? "Base Brain" : "FAQ"}${n && h.faq ? " · Base Brain" : ""}</span></li>`;
  }

  // ---------- Lanes and step log ----------
  const LANES = [
    ["question", "Question", "chat"],
    ["route", "Route", "alt_route"],
    ["model", "Model", "memory"],
    ["check", "Check", "fact_check"],
    ["answer", "Answer", "task_alt"]];
  const ROUTES = [["faq", "Written"], ["template", "Template"], ["kb", "Knowledge"], ["rag", "Retrieval + model"], ["agent", "Agent"], ["base_support", "Base team"]];
  const lane = {};
  let t0Run = 0;
  function buildLanes() {
    $("lanes").innerHTML = LANES.map(([id, name, icon]) => `<li class="lane" id="lane-${id}" data-state="idle">
      <div class="flex items-center gap-2"><span class="dot" aria-hidden="true"></span><span class="material-symbols-outlined text-[16px] text-primary-container" aria-hidden="true">${icon}</span><span class="font-label-md text-label-md text-ink-primary">${name}</span></div>
      <p class="lane-status font-body-sm text-body-sm text-on-surface-variant mt-1">Waiting</p>
      ${id === "route" ? `<div class="flex flex-wrap gap-1 mt-1.5">${ROUTES.map(([k, l]) => `<span class="route-opt" data-route="${k}" data-on="0">${l}</span>`).join("")}</div>` : ""}</li>`).join("");
    for (const [id] of LANES) { const li = $("lane-" + id); lane[id] = {li, status: li.querySelector(".lane-status"), ms: 0, n: 0}; }
    $("log").querySelectorAll("li:not(.hd)").forEach(li => li.remove());
  }
  const fmtMs = ms => ms < 1 ? (ms > 0 ? ms.toFixed(2) + " ms" : "under 1 ms") : ms < 1000 ? Math.round(ms) + " ms" : (ms / 1000).toFixed(2) + " s";
  function setLane(id, state, status) { const L = lane[id]; L.li.dataset.state = state; if (status) L.status.textContent = status; }
  function log(by, ms, title) {
    const li = document.createElement("li");
    const t = new Date(), stamp = t.toTimeString().slice(0, 8) + "." + String(t.getMilliseconds()).padStart(3, "0");
    li.innerHTML = `<span class="t">${stamp}</span><span class="by-${by === "model" ? "model" : "code"}">${by === "model" ? "model" : by}</span><span>${ms == null ? "" : esc(fmtMs(ms))}</span><span>${esc(title)}</span>`;
    $("log").append(li); $("log").scrollTop = $("log").scrollHeight;
  }
  function addStep(id, by, title, ms) { const L = lane[id]; L.ms += ms; L.n++; log(by, ms, title); }
  function laneFor(ev) {
    if (ev.by === "model") return "model";
    if (ev.role === "planner") return "route";
    if (ev.role === "critic") return "check";
    if (ev.role === "reporter" && /source tags/i.test(ev.title)) return "answer";
    return "model";
  }
  function routeOf(title) {
    if (/^Written answer: (?!next)|^Recorded answer/.test(title)) return "faq";
    if (/^Template /.test(title)) return "template";
    if (/^Knowledge base: /.test(title)) return "kb";
    if (/^Retrieval: /.test(title)) return "rag";
    if (/policy question/.test(title)) return "base_support";
    if (/full agent/.test(title)) return "agent";
    return null;
  }
  function lightRoute(k) { lane.route.li.querySelectorAll(".route-opt").forEach(o => o.dataset.on = o.dataset.route === k ? "1" : "0"); }

  // Events are shown in order with a short gap so each lane is seen lighting up; the times shown are the measured ones.
  let queue = [], pumping = false, runId = 0;
  function push(ev) { queue.push(ev); if (!pumping) pump(); }
  async function pump() {
    pumping = true;
    while (queue.length) {
      const ev = queue.shift();
      if (ev.run !== runId) continue;
      apply(ev);
      if (!calm()) await new Promise(r => setTimeout(r, ev.ev === "begin" ? 140 : 220));
    }
    pumping = false;
  }
  function apply(ev) {
    if (ev.ev === "begin") { const id = laneFor(ev); if (lane[id].li.dataset.state !== "done") setLane(id, "working", ev.title); return; }
    if (ev.ev === "step") {
      const id = laneFor(ev);
      addStep(id, ev.by, ev.title, ev.ms);
      if (id === "route") { const k = routeOf(ev.title); if (k) lightRoute(k); }
      setLane(id, "done", `${lane[id].n} step${lane[id].n > 1 ? "s" : ""} · ${fmtMs(lane[id].ms)}`);
      return;
    }
    if (ev.ev === "done") return finish(ev.result, ev.where, ev.total);
    if (ev.ev === "hop") { setLane("question", "done", ev.text); log("net", null, ev.text); return; }
  }
  function finish(r, where, total) {
    lightRoute(r.path === "cache" ? "faq" : r.path);
    if (!lane.route.n) setLane("route", "done", "Route chosen");
    if (!lane.model.n) setLane("model", "rest", "Rested: code answered");
    if (!lane.check.n) {
      const note = r.path === "faq" || r.path === "cache" ? "Written answer, source attached" : r.path === "kb" ? "Quoted from the page" : r.path === "base_support" ? "Handed to the Base team" : "Checked";
      setLane("check", "done", note);
    }
    let sources = r.sourcesHtml || (r.sources || []).map(s => {
      const n = kbNode(s.slug || s.label || "");
      if (n) return `<li class="flex gap-2"><span class="font-label-md text-primary-container">[${s.n || 1}]</span><a class="text-primary-container font-semibold underline underline-offset-2" href="${esc(kbHref(n))}">${esc(n.title)}</a><span class="text-outline">Base Brain</span></li>`;
      const label = esc(s.label || s.file || "Source");
      const link = s.url ? `<a class="text-primary-container font-semibold underline underline-offset-2" href="${esc(s.url)}" target="_blank" rel="noopener">${label}</a>` : `<span>${label}</span>`;
      return `<li class="flex gap-2"><span class="font-label-md text-primary-container">[${s.n || 1}]</span>${link}${s.file ? `<span class="text-outline">${esc(s.file)}</span>` : ""}</li>`;
    });
    const item = r.path === "faq" && faq ? faq.items.find(i => i.id === r.template) : null;
    for (const n of item ? kbFor(item) : []) sources.push(`<li class="flex gap-2"><span class="material-symbols-outlined text-[16px] text-primary-container" aria-hidden="true">hub</span><a class="text-primary-container font-semibold underline underline-offset-2" href="${esc(kbHref(n))}">${esc(n.title)}</a><span class="text-outline">Base Brain</span></li>`);
    if (r.path === "base_support") sources.push(`<li class="flex gap-2"><span class="material-symbols-outlined text-[16px] text-primary-container" aria-hidden="true">support_agent</span><a class="text-primary-container font-semibold underline underline-offset-2" href="${esc(ctx("brain.html"))}">Reach the Base team from Help</a></li>`);
    setLane("answer", "done", `Answered in ${fmtMs(total)}`);
    log("done", total, `Answer ready · ${where}`);
    $("answer").hidden = false;
    $("answer-text").classList.remove("caret");
    $("answer-text").innerHTML = esc(r.answer).replace(/\s?\[(\d)\]/g, "<sup>[$1]</sup>");
    $("answer-sources").innerHTML = sources.join("");
    const calls = r.model_calls || 0;
    $("answer-meta").textContent = r.meta || `${where} · ${fmtMs(total)} · ${calls ? calls + " model call" + (calls > 1 ? "s" : "") : "code only"}`;
    stat("st-last", "up", fmtMs(total), where);
    thinking(false);
    $("ask-go").disabled = false;
  }

  // ---------- Running a question ----------
  let mode = "routes";
  async function run(q) {
    q = String(q || "").trim().slice(0, 400); if (!q) return;
    runId++; queue = []; buildLanes(); t0Run = performance.now();
    $("answer").hidden = true; $("ask-q").value = q; $("ask-go").disabled = true;
    const id = runId;
    thinking(true, "Running: " + q);
    stat("st-last", "busy", "Running", null);
    setLane("question", "working", "Sending");
    log("user", null, q);
    if (mode === "pc" && await runServer(q, id)) return;
    if (mode === "browser" && engine) return runModel(q, id);
    runBrowser(q, id);
  }
  async function runServer(q, id) {
    const t0 = performance.now();
    try {
      const ctl = new AbortController(), guard = setTimeout(() => ctl.abort(), 4000);
      const res = await fetch(ASK + "/ask?stream=1", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({q, page: "models.html"}), signal: ctl.signal});
      clearTimeout(guard);
      if (!res.ok || !res.body) throw new Error("status " + res.status);
      where("Ran on your PC", "dns");
      push({run: id, ev: "hop", text: `Reached your PC in ${fmtMs(performance.now() - t0)}`});
      const rd = res.body.getReader(), dec = new TextDecoder(); let buf = "", got = false;
      for (;;) {
        const {value, done} = await rd.read();
        if (done) break;
        buf += dec.decode(value, {stream: true});
        let k;
        while ((k = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, k).trim(); buf = buf.slice(k + 1);
          if (!line) continue;
          const ev = JSON.parse(line);
          if (ev.ev === "error") throw new Error(ev.error);
          if (ev.ev === "done") { got = true; push({run: id, ev: "done", result: ev.result, where: "Ran on your PC", total: performance.now() - t0}); }
          else push({run: id, ...ev});
        }
      }
      return got;
    } catch (e) {
      pcState(false);
      return false;
    }
  }
  function runBrowser(q, id) {
    where("Code routes in this browser", "language");
    const t0 = performance.now(), evs = [{ev: "hop", text: "Read in this browser"}];
    const step = (role, by, title, fn) => { evs.push({ev: "begin", role, by, title}); const s = performance.now(); const v = fn(); evs.push({ev: "step", role, by, title: v.title, ms: performance.now() - s}); return v.val; };
    let r = null;
    const hit = step("planner", "code", "Looking for a written answer", () => { const h = faqHit(q); return {val: h, title: h ? "Written answer: " + h.id : "Written answer: next route"}; });
    if (hit) r = fromFaq(q, hit);
    if (!r) {
      const n = step("planner", "code", "Searching the knowledge base", () => { const x = kbSearch(q); return {val: x, title: x ? "Knowledge base: " + x.short : "Knowledge base: next route"}; });
      if (n) {
        const ans = step("reporter", "code", "Quoting the knowledge base page", () => ({val: n.summary + " [1]", title: "Answer quoted from the page"}));
        r = {path: "kb", answer: ans, sources: [{n: 1, slug: n.slug}], model_calls: 0};
      }
    }
    if (!r) {
      const it = step("planner", "code", "Finding the closest written answer", () => { const x = looseFaq(q); return {val: x, title: x ? "Written answer: " + x.id : "Base team answers this one"}; });
      r = it ? fromFaq(q, it) : {path: "base_support", answer: "The Base team answers this one directly. Open Help to reach them.", sources: [], model_calls: 0};
    }
    const total = performance.now() - t0;
    for (const ev of evs) push({run: id, ...ev});
    push({run: id, ev: "done", result: r, where: "Code routes in this browser", total});
  }
  const fromFaq = (q, it) => ({path: "faq", template: it.id, answer: it.a, sources: [{n: 1, label: it.source || "Base Brain FAQ", url: it.source_url}], model_calls: 0});
  function where(text, icon) {
    $("run-where-text").textContent = text;
    $("run-where").querySelector(".material-symbols-outlined").textContent = icon;
    $("mode-text").textContent = text;
  }

  // ---------- In this browser: WebLLM on WebGPU ----------
  const WL_URL = "https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.79/+esm";
  // Sizes: ndarray-cache.json on huggingface.co/mlc-ai (weights) and the model_lib wasm, WebLLM 0.2.79 prebuiltAppConfig (GPU memory).
  const WL_MODELS = {
    f16: {id: "Qwen2.5-0.5B-Instruct-q4f16_1-MLC", mb: 282, size: "278 MB + 3.8 MB", vram: 945},
    f32: {id: "Qwen2.5-0.5B-Instruct-q4f32_1-MLC", mb: 282, size: "278 MB + runtime", vram: 1060}};
  let wl = WL_MODELS.f16, engine = null, loading = false;
  const shortName = () => wl.id.replace(/-MLC$/, "");
  async function probeGpu() {
    if (!("gpu" in navigator)) return null;
    try { return await navigator.gpu.requestAdapter(); } catch { return null; }
  }
  async function cached() {
    try { const c = await caches.open("webllm/model"); return (await c.keys()).some(r => r.url.includes(wl.id)); } catch { return false; }
  }
  async function initBrowserRuntime() {
    const gpu = await probeGpu();
    if (!gpu) {
      $("wl-state").textContent = "WebGPU off in this browser"; $("wl-state").className = "pill warn";
      $("wl-text").textContent = "WebGPU runs in Chrome or Edge 113+ on a desktop and in Safari 26. On this browser, use Your PC below.";
      stat("st-browser", "down", "WebGPU: no", "Use Your PC below");
      return;
    }
    if (!(gpu.features && gpu.features.has("shader-f16"))) wl = WL_MODELS.f32;
    $("wl-model").textContent = wl.id; $("wl-size").textContent = wl.size; $("wl-vram").textContent = wl.vram + " MB";
    const inCache = await cached();
    $("wl-state").textContent = inCache ? "Cached · ready to load" : "WebGPU ready"; $("wl-state").className = "pill ok";
    $("wl-load-text").textContent = inCache ? "Load model · cached" : `Load model · ${wl.mb} MB`;
    $("wl-load").disabled = false;
    stat("st-browser", "idle", "WebGPU: yes", inCache ? "Model cached, not loaded" : "Model not loaded");
  }
  async function loadModel() {
    if (engine || loading) return;
    loading = true; $("wl-load").disabled = true;
    const t0 = performance.now();
    $("wl-bar").hidden = false; $("wl-state").textContent = "Loading"; $("wl-state").className = "pill warn";
    stat("st-browser", "busy", "Loading model", "0%");
    try {
      const webllm = await import(WL_URL);
      const rec = webllm.prebuiltAppConfig.model_list.find(m => m.model_id === wl.id);
      if (rec && rec.vram_required_MB) $("wl-vram").textContent = Math.round(rec.vram_required_MB) + " MB";
      engine = await webllm.CreateMLCEngine(wl.id, {initProgressCallback: p => {
        const pct = Math.round((p.progress || 0) * 100);
        $("wl-bar").firstElementChild.style.width = pct + "%";
        $("wl-text").textContent = p.text;
        $("st-browser").querySelector(".s").textContent = pct + "%";
      }});
      const s = (performance.now() - t0) / 1000;
      $("wl-bar").firstElementChild.style.width = "100%";
      $("wl-state").textContent = "Loaded"; $("wl-state").className = "pill ok";
      $("wl-load-text").textContent = "Loaded";
      $("wl-text").textContent = `Loaded in ${s.toFixed(1)} s. Questions in Live run now go to ${shortName()}.`;
      stat("st-browser", "up", "Model loaded", shortName());
      $("reg-wl-status").innerHTML = `<span class="pill ok">Loaded</span>`;
      const b = $("run-on").querySelector('[data-on="browser"]'); b.disabled = false; b.title = "";
      setMode("browser");
    } catch (e) {
      engine = null;
      $("wl-state").textContent = "Load stopped"; $("wl-state").className = "pill warn";
      $("wl-text").textContent = String(e && e.message || e).slice(0, 300) + " · Your PC below runs gemma4:e4b.";
      stat("st-browser", "down", "Load stopped", "See Runtimes");
      $("wl-load").disabled = false;
    }
    loading = false;
  }
  const SYSTEM = "You answer a Base Power member's question using only the numbered sources. Cite them as [1], [2] or [3]. If the sources do not cover the question, say the Base team answers it directly. Answer in at most 3 short sentences.";
  async function runModel(q, id) {
    const at = performance.now();
    where("Ran in this browser with " + shortName(), "language");
    apply({ev: "hop", text: "Read in this browser"});
    setLane("route", "working", "Retrieving");
    const s0 = performance.now(), hits = top3(q), rms = performance.now() - s0;
    apply({ev: "step", role: "planner", by: "code", title: `Retrieval: ${hits.length} of ${members().length} FAQ + ${kb ? kb.nodes.length : 0} knowledge pages`, ms: rms});
    if (!hits.length) {
      apply({ev: "done", result: {path: "base_support", answer: "The Base team answers this one directly. Open Help to reach them.", sources: [], model_calls: 0}, where: "Ran in this browser", total: performance.now() - at});
      return;
    }
    hits.forEach((h, i) => log("code", null, `[${i + 1}] ${h.title}`));
    const ctxText = hits.map((h, i) => `[${i + 1}] ${h.title}: ${h.text.slice(0, 600)}`).join("\n");
    setLane("model", "working", "Generating with " + shortName());
    $("answer").hidden = false; $("answer-sources").innerHTML = hits.map(sourceHtml).join("");
    $("answer-meta").textContent = "Generating in this browser";
    const out = $("answer-text"); out.textContent = ""; out.classList.add("caret");
    const g0 = performance.now(); let first = 0, text = "", n = 0, usage = null;
    try {
      const chunks = await engine.chat.completions.create({
        messages: [{role: "system", content: SYSTEM}, {role: "user", content: `Sources:\n${ctxText}\n\nQuestion: ${q}`}],
        stream: true, temperature: 0, max_tokens: 200, stream_options: {include_usage: true}});
      for await (const c of chunks) {
        if (id !== runId) return;
        const d = c.choices && c.choices[0] && c.choices[0].delta && c.choices[0].delta.content;
        if (d) { if (!first) first = performance.now() - g0; text += d; n++; out.textContent = text; }
        if (c.usage) usage = c.usage;
      }
    } catch (e) {
      out.classList.remove("caret");
      apply({ev: "done", result: {path: "rag", answer: "The browser model stopped: " + String(e && e.message || e).slice(0, 160), sources: [], model_calls: 1}, where: "Ran in this browser", total: performance.now() - at});
      return;
    }
    const gms = performance.now() - g0;
    const toks = usage && usage.completion_tokens || n;
    const tps = usage && usage.extra && usage.extra.decode_tokens_per_s ? usage.extra.decode_tokens_per_s : toks / Math.max(.001, (gms - first) / 1000);
    addStep("model", "model", `${shortName()}: ${toks} tokens · first token ${fmtMs(first)} · ${tps.toFixed(1)} tok/s`, gms);
    setLane("model", "done", `${toks} tokens · ${tps.toFixed(1)} tok/s`);
    // Check: every number the model wrote should appear in the sources it was given.
    const c0 = performance.now();
    const nums = (text.replace(/\[\d\]/g, "").match(/\d[\d,.]*\d|\d/g) || []).map(x => x.replace(/[,.]$/, ""));
    const found = nums.filter(x => ctxText.includes(x));
    addStep("check", "code", nums.length ? `Numbers found in sources: ${found.length} of ${nums.length}` : "No numbers to check", performance.now() - c0);
    setLane("check", "done", nums.length ? `${found.length} of ${nums.length} numbers in sources` : "No numbers to check");
    $("wl-tps").textContent = tps.toFixed(1) + " tok/s";
    $("reg-wl-speed").textContent = tps.toFixed(1) + " tok/s";
    $("reg-wl-first").textContent = fmtMs(first);
    const total = performance.now() - at;
    finish({path: "rag", answer: text.trim() || "(no text)", sourcesHtml: hits.map(sourceHtml), model_calls: 1,
      meta: `Ran in this browser with ${wl.id} · ${tps.toFixed(1)} tok/s · ${fmtMs(total)}`}, "Ran in this browser with " + shortName(), total);
  }

  // ---------- Your PC: ask server 8742, voice 8744 ----------
  const onLocal = /^(localhost|127\.0\.0\.1)$/.test(location.hostname) && location.protocol === "http:";
  let pcModel = "gemma4:e4b";
  function pcState(up, note) {
    const b = $("run-on").querySelector('[data-on="pc"]');
    b.disabled = !up; b.title = up ? "" : "Check your PC under Runtimes";
    $("pc-state").textContent = up ? "Connected to your PC" : note || "Offline";
    $("pc-state").className = up ? "pill ok" : "pill";
    stat("st-home", up ? "up" : "down", up ? "Connected" : note || "Offline", up ? pcModel + " · localhost:8742" : "localhost:8742");
    if (!up && mode === "pc") setMode("routes");
  }
  // Reachability without CORS: an opaque no-cors reply means something answers on that port.
  const reach = url => fetch(url, {mode: "no-cors", signal: AbortSignal.timeout(1500)}).then(() => true, () => false);
  async function checkPC(manual) {
    $("pc-check").disabled = true; $("pc-state").textContent = "Checking"; $("pc-state").className = "pill warn";
    // brain/tts.py answers the CORS preflight for localhost pages; from other origins the voice check runs on the local copy.
    const voice = onLocal ? fetch(TTS + "/tts", {method: "OPTIONS", signal: AbortSignal.timeout(1500)}).then(r => r.ok, () => false) : Promise.resolve(null);
    if (onLocal) {
      const h = await fetch(ASK + "/health", {signal: AbortSignal.timeout(1500)}).then(r => r.ok ? r.json() : null).catch(() => null);
      if (h) { pcModel = h.model || pcModel; pcState(true); if (manual || mode === "routes") setMode("pc"); $("pc-note").textContent = ""; }
      else { pcState(false, "Offline"); $("pc-note").textContent = "Start it with the install command above."; }
    } else {
      const up = await reach(ASK + "/health");
      pcState(false, up ? "Running on this PC" : "Offline");
      $("pc-note").innerHTML = up ? `Your PC answers on 8742. Live runs connect from the local copy: <a class="text-primary-container font-semibold underline underline-offset-2" href="${LOCAL_PAGES}">localhost:8741/web/models.html</a>` : "Start it with the install command above, then check again.";
      if (up) stat("st-home", "up", "Running", "Open the local copy to connect");
    }
    const v = await voice;
    if (v === null) stat("st-voice", "idle", "Checked on the local copy", "localhost:8741/web/models.html");
    else stat("st-voice", v ? "up" : "idle", v ? "Running" : "Off", v ? "Kokoro-82M · localhost:8744" : "Browser voice in use");
    $("pc-check").disabled = false;
  }

  function setMode(m) {
    mode = m;
    $("run-on").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.on === m)));
    where(m === "pc" ? "Connected to your PC" : m === "browser" ? "Browser model: " + shortName() : "Code routes in this browser", m === "pc" ? "dns" : "language");
  }

  // ---------- Model registry (numbers copied from the named files) ----------
  const ROWS = [
    ["gemma4:e4b", "Member chat", "M2 laptop · Ollama", "ok:Measured", "14 of 16", "4 of 4 policy to Base", "2.2 s", "0.62 s", "brain/LOCAL_VS_CLOUD.md"],
    ["gemma4:e4b", "Member chat", "Jetson · Ollama", "ok:Measured", "12 of 16", "4 of 4 policy to Base", "3.0 s", "1.45 s", "brain/LOCAL_VS_CLOUD.md"],
    ["gemma4:e4b", "Panel photo reader", "M2 laptop · Ollama", "ok:Measured", "16 of 21", "photos", "129 s", "per photo", "docs/GAPS.md"],
    ["Gemini", "Panel photo reader", "Google cloud", "ok:Measured", "18 of 21", "photos", "12.7 s", "per photo", "docs/GAPS.md"],
    ["Templates, no model", "Data questions", "Any runtime", "ok:Measured", "73 of 73", "number check · 65 of 73 on a template", "0.62 s max", "", "brain/insights.json"],
    ["gemma4:e4b agent", "Data questions off template", "M2 laptop · Ollama", "ok:Measured", "", "", "23.2 s", "", "brain/insights.json"],
    ["Kokoro-82M", "Voice · af_heart · Apache-2.0", "PC · brain/tts.py", ":Configured", "", "", "", "", "brain/tts.py"],
    ["Qwen2.5-0.5B-Instruct q4", "Try it · top 3 retrieval", "This browser · WebLLM", "wl", "Not scored", "", "", "", "WebLLM 0.2.79"],
    ["gemma4:e4b", "Member chat", "Windows PC beside the battery", ":Next measurement #80", "", "", "", "", "docs/GAPS.md"]];
  function renderCards() {
    const cell = (l, v, sub, cls = "num") => `<td data-l="${l}" class="${cls}">${v ? esc(v) : '<span class="text-outline">—</span>'}${sub ? `<span class="sub">${esc(sub)}</span>` : ""}</td>`;
    $("cards").innerHTML = `<table class="reg" id="models-table"><thead><tr><th>Model</th><th>Runs on</th><th>Status</th><th>Accuracy</th><th>Median</th><th>First token</th><th>Source</th></tr></thead><tbody>${ROWS.map(([m, tag, on, st, acc, accSub, med, ft, src]) => {
      const wlRow = st === "wl";
      const [cls, label] = wlRow ? ["", "Not loaded"] : st.split(":");
      return `<tr>
        <td class="first" data-l="Model"><span class="font-semibold text-ink-primary">${esc(m)}</span><span class="sub">${esc(tag)}</span></td>
        <td data-l="Runs on">${esc(on)}</td>
        <td data-l="Status"${wlRow ? ' id="reg-wl-status"' : ""}><span class="pill ${cls}">${esc(label)}</span></td>
        ${cell("Accuracy", acc, accSub)}
        ${wlRow ? `<td data-l="Speed" class="num" id="reg-wl-speed"><span class="text-outline">On first run</span></td><td data-l="First token" class="num" id="reg-wl-first"><span class="text-outline">—</span></td>` : cell("Median", med, "") + cell("First token", ft, "")}
        <td data-l="Source"><span class="src">${esc(src)}</span></td></tr>`;
    }).join("")}</tbody></table>`;
  }

  // ---------- What leaves your home ----------
  $("cloud-toggle").addEventListener("click", () => {
    const on = $("cloud-toggle").getAttribute("aria-pressed") !== "true";
    $("cloud-toggle").setAttribute("aria-pressed", String(on));
    $("flow").classList.toggle("cloud-on", on);
    $("cloud-toggle-text").textContent = on ? "Keep it at home" : "Show a cloud choice";
    $("cloud-label").textContent = on ? "Cloud model: picked for this question" : "Cloud model: when picked";
    $("cloud-note").textContent = on ? "This one question goes to the cloud model you picked." : "Cloud model runs only for a question you pick it for.";
  });

  // ---------- Copy buttons ----------
  document.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
    const text = $(b.dataset.copy).textContent, label = b.lastChild;
    try { await navigator.clipboard.writeText(text); label.textContent = "Copied"; }
    catch { const r = document.createRange(); r.selectNodeContents($(b.dataset.copy)); const s = getSelection(); s.removeAllRanges(); s.addRange(r); label.textContent = "Selected"; }
    setTimeout(() => label.textContent = "Copy", 1600);
  }));

  // ---------- Boot ----------
  const CHIPS = ["how-long", "private", "safe", "cancel"];
  buildLanes(); renderCards();
  $("ask-form").addEventListener("submit", e => { e.preventDefault(); run($("ask-q").value); });
  $("run-on").addEventListener("click", e => { const b = e.target.closest("button"); if (b && !b.disabled) setMode(b.dataset.on); });
  $("wl-load").addEventListener("click", loadModel);
  $("pc-check").addEventListener("click", () => checkPC(true));
  initBrowserRuntime();
  if (!onLocal) { stat("st-home", "idle", "Not checked", "Check my PC under Runtimes"); stat("st-voice", "idle", "Not checked", "Check my PC under Runtimes"); }
  Promise.all([get("data/faq.json"), get("data/kb_graph.json"), onLocal ? checkPC(false) : null]).then(([f, k]) => {
    faq = f; kb = k;
    if (mode === "routes") setMode("routes");
    const qs = CHIPS.map(id => members().find(i => i.id === id)).filter(Boolean).map(i => i.q).concat(["How many Base permits were issued in 78704 in 2026?"]);
    $("chips").innerHTML = qs.map(q => `<button type="button" class="px-3 py-1 rounded-full bg-surface-muted border border-wire-border hover:bg-secondary-container text-ink-primary font-body-sm text-body-sm text-left cursor-pointer">${esc(q)}</button>`).join("");
    $("chips").querySelectorAll("button").forEach(b => b.addEventListener("click", () => run(b.textContent)));
    if (qs.length) run(qs[0]);
  });
})();
