(() => {
  "use strict";
  // Step 4 status page. Home = public-record home (cohort.json); progress = BaseMilestones.state().
  const FIELDS = {
    has_solar: {name: "Solar panels", ask: "Do you have solar panels?", thing: "solar panels"},
    has_battery: {name: "Home battery", ask: "Do you have a home battery?", thing: "battery"},
    main_breaker_amps: {name: "Electric panel", ask: "What size is your main breaker?"},
    ac_age_years: {name: "A/C unit", ask: "How old is your A/C unit, in years?"},
    has_generator: {name: "Generator", ask: "Do you have a generator?", thing: "generator"}
  };
  const ORDER = ["has_solar", "has_battery", "main_breaker_amps", "ac_age_years", "has_generator"];
  const $ = id => document.getElementById(id);
  const read = k => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } };

  function valueText(f, v) {
    if (v === null || v === undefined) return "Not known";
    if (typeof v === "boolean") return v ? `Has ${FIELDS[f].thing}` : `No ${FIELDS[f].thing}`;
    return f === "ac_age_years" ? `About ${v} years old` : `${v} A main breaker`;
  }

  function reason(house, f) {
    const g = house.guessable.find(x => x.field === f) || {};
    const words = f === "main_breaker_amps" ? /amp|panel|service/i : new RegExp(FIELDS[f].thing || f, "i");
    const fit = ((house.fit && house.fit.reasons) || []).find(r => words.test(r));
    const src = g.source ? `Source: ${g.source}` : "No record for this detail";
    const conf = typeof g.confidence === "number" ? `, record confidence ${Math.round(g.confidence * 100)}%` : "";
    return fit ? `${fit.charAt(0).toUpperCase() + fit.slice(1)}. ${src}${conf}.` : `${src}${conf}.`;
  }

  function chip(text, tone) {
    const c = {green: ["bg-emerald-50 text-emerald-800", "bg-solar-green"], amber: ["bg-amber-50 text-amber-900", "bg-warning-amber"],
      grey: ["bg-surface-subtle text-outline", "bg-outline"]}[tone];
    const s = document.createElement("span");
    s.className = `inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold shrink-0 ${c[0]}`;
    const d = document.createElement("span");
    d.className = `w-1.5 h-1.5 rounded-full ${c[1]}`;
    s.append(d, text);
    return s;
  }

  function render(house) {
    const s = window.BaseMilestones.state();
    const addr = house.address;
    const saved = (read(`base-fleet:journey:v1:${addr}`) || {}).saved || {};
    const asked = ORDER.filter(f => house.confirm_with_member.includes(f));
    const unanswered = asked.filter(f => !Object.hasOwn(saved, f));
    const q = `?address=${encodeURIComponent(addr)}`;

    $("addr").textContent = addr;
    document.title = `Application status | Base Fleet`;
    $("crumb-home").href = `onboarding.html${q}#home`;
    $("brain-link").href = `brain.html${q}`;

    // Stage: first milestone not done.
    const idx = s.addr === addr ? s.status.findIndex(x => x !== "done") : 1;
    const stage = window.BaseMilestones.MILESTONES[idx < 0 ? 4 : idx];
    $("stage-chip").textContent = `Application stage: ${stage}`;
    $("crumb-step").textContent = `Step ${(idx < 0 ? 4 : idx) + 1} of 5: ${stage}`;
    const pending = unanswered.length + (s.photo && s.addr === addr ? 0 : 1);
    $("pending-text").textContent = pending ? (pending > 1 ? `One thing now, ${pending - 1} after` : "One thing left") : "You are all set";
    $("pending-chip").className = pending
      ? "inline-flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg font-label-md text-label-md"
      : "inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg font-label-md text-label-md";
    $("stage-dot").className = `w-1.5 h-1.5 rounded-full ${pending ? "bg-warning-amber" : "bg-solar-green"}`;

    // Action card.
    const main = $("action-main"), voice = $("action-voice");
    main.href = `onboarding.html${q}#home`;
    voice.href = `voice.html${q}`;
    const hasPhoto = s.photo && s.addr === addr;
    // A photo the member asked a Base reviewer to check (photo-check.js).
    $("photo-review").hidden = !read(`base-fleet:review:v1:${addr}`);
    // Voice answers earn no per-answer credit (milestones.js); a voice-guide photo does.
    const mark = (a, kind) => {
      if ((a.dataset.reward || null) === kind) return;
      a.querySelectorAll(":scope > .bf-rw").forEach(c => c.remove());
      if (kind) a.dataset.reward = kind; else delete a.dataset.reward;
    };
    // Voice answers earn no per-answer credit (milestones.js); a voice-guide photo does.
    const setReward = kind => { mark(main, kind); mark(voice, kind === "photo" ? kind : null); };
    $("action-reason-box").hidden = $("action-ctas").hidden = false;
    if (unanswered.length) {
      const f = unanswered[0];
      $("action-title").textContent = FIELDS[f].ask;
      $("action-body").textContent = `Your answer confirms your ${FIELDS[f].name.toLowerCase()} before the engineering review.`;
      $("action-reason").textContent = reason(house, f);
      $("action-main-text").textContent = "Answer on your home page";
      setReward("field");
    } else if (!hasPhoto) {
      $("action-title").textContent = "Add a photo of your electric panel";
      $("action-body").textContent = "Your answers are in. A clear photo of the closed panel and meter helps Base check mounting space.";
      $("action-reason").textContent = "Permits show past electrical work. Your photo shows the panel label and wall space.";
      $("action-main-text").textContent = "Add the panel photo";
      setReward("photo");
    } else {
      $("action-card").className = "bg-surface-container-lowest border border-wire-border rounded-xl p-5 sm:p-6 shadow-sm";
      $("action-icon-box").className = "w-10 h-10 rounded-lg bg-emerald-50 text-emerald-800 flex items-center justify-center shrink-0";
      $("action-icon").textContent = "task_alt";
      $("action-kicker").textContent = "All set";
      $("action-kicker").className = "font-label-caps text-label-caps text-emerald-800 uppercase tracking-wider font-bold";
      $("action-title").textContent = "You are all set";
      $("action-body").textContent = "Your details and photo are in. The engineering review and installation are steps Base does.";
      $("action-reason-box").hidden = true;
      $("action-ctas").hidden = true;
      setReward(null);
    }

    // Verified data list.
    const list = $("verified-list");
    list.replaceChildren();
    let settled = 0;
    for (const f of ORDER) {
      const g = house.guessable.find(x => x.field === f) || {};
      let label, tone, sub;
      if (!asked.includes(f)) { label = "From public records"; tone = "green"; sub = valueText(f, g.value); settled++; }
      else if (Object.hasOwn(saved, f) && saved[f] !== null) { label = "Confirmed by you"; tone = "green"; sub = valueText(f, saved[f]); settled++; }
      else if (Object.hasOwn(saved, f)) { label = "Needed from you"; tone = "amber"; sub = "You left this open. You can answer it later."; }
      else { label = "Needed from you"; tone = "amber"; sub = g.source ? `Records: ${g.source}` : "Not on record."; }
      const row = document.createElement("div");
      row.className = "py-3.5 flex items-center justify-between gap-3";
      row.dataset.field = f;
      const t = document.createElement("div");
      t.className = "min-w-0";
      const n = document.createElement("p");
      n.className = "font-label-md text-label-md font-semibold text-ink-primary";
      n.textContent = FIELDS[f].name;
      const p = document.createElement("p");
      p.className = `font-body-sm text-body-sm ${tone === "amber" ? "text-amber-900 font-medium" : "text-outline"}`;
      p.textContent = sub;
      t.append(n, p);
      row.append(t, chip(label, tone));
      list.append(row);
    }
    if (window.BaseMilestones.chips) window.BaseMilestones.chips();
    $("verified-count").textContent = `${settled} of ${ORDER.length} settled`;

    // Site plan facts.
    $("spec-zip").textContent = house.zip || "Not on record";
    $("spec-year").textContent = house.year_built || "Not on record";
    $("spec-permits").textContent = String(new Set(house.events.map(e => e.permit)).size);
    $("twin").alt = `Drawing of a single-family home, standing in for ${addr}`;
  }

  async function load() {
    let houses = [];
    try {
      const r = await fetch("../house/cohort.json", {cache: "no-store"});
      houses = (await r.json()).filter(h => h && typeof h.address === "string" && Array.isArray(h.events));
    } catch {
      $("action-title").textContent = "Reload the page to load house records";
      return;
    }
    const want = window.BaseMilestones.state().addr;
    const house = houses.find(h => h.address === want) || houses[0];
    house.guessable = house.guessable || [];
    house.confirm_with_member = house.confirm_with_member || [];
    const draw = () => render(house);
    draw();
    document.addEventListener("base-fleet:progress", draw);
    window.addEventListener("storage", draw);
  }
  load();
})();
