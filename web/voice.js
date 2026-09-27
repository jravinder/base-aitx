(() => {
  "use strict";

  const OLLAMA = "http://localhost:11434";
  const MODEL = "gemma4:e4b";
  const SAMPLE_ADDRESS = "706 HUNTINGDON PL";
  const RECORDED_SAMPLE = "156.jpg";
  const SAFE_RETAKE = "Keep all doors and covers closed. Photograph the whole closed box from a safe distance in good light. Skip the photo if it feels unsafe or you are unsure.";
  const PROMPT = `Check only the framing and clarity of a closed electrical panel exterior photo.
Return ONLY JSON with these fields:
{"photo_type": "panel_open|panel_closed|meter_exterior|other", "pass": boolean, "retake_reason": null}
pass is true only when the whole closed panel exterior is visible and clearly framed. It is not an electrical assessment, engineering sizing, or installation approval. Do not infer electrical ratings. Never request opening doors or covers, touching equipment, or approaching hazards. Return retake_reason as null; the application supplies fixed safety instructions.`;
  const PHOTO_TYPES = {
    panel_open: "Open electric panel, door open",
    panel_closed: "Electric panel, door closed",
    meter_exterior: "Electric meter, not the panel",
    other: "Not an electric panel"
  };
  const STREET = {PL: "Place", DR: "Drive", LN: "Lane", AVE: "Avenue", ST: "Street", RD: "Road",
    TRL: "Trail", CIR: "Circle", CV: "Cove", BLVD: "Boulevard", CT: "Court", PASS: "Pass"};

  const $ = id => document.getElementById(id);
  const ui = {guided: $("vg-guided"), cgView: $("vg-caregiver-view"), cgList: $("vg-cg-list"),
    caregiver: $("vg-caregiver"), voice: $("vg-voice"), repeat: $("vg-repeat"), status: $("vg-status"),
    speed: $("vg-speed"), caption: $("vg-caption"),
    rail: $("vg-rail"), railPct: $("vg-rail-pct"), railBar: $("vg-rail-bar"), railCount: $("vg-rail-count")};

  const synth = "speechSynthesis" in window ? window.speechSynthesis : null;
  // Kokoro voice (speak.js): a pre-rendered clip, the local voice server, then the browser voice.
  const kokoro = () => window.BaseVoice && window.BaseVoice.available ? window.BaseVoice : null;
  const canSpeak = () => !!(synth || kokoro());
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  let voiceOn = false, caregiver = false, steps = [], index = 0, house = null;
  let speechVersion = 0, recognition = null;
  const answers = {};        // step id -> "yes" | "no" | "unsure"
  let photo = null;          // {mode, type, pass, retake, secs, file}
  let photoUrl = null, checking = false;

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function button(label, cls, onClick) {
    const b = el("button", cls, label);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }
  function titleCase(s) { return s.toLowerCase().replace(/\b\w/g, c => c.toUpperCase()); }
  function spokenAddress(addr) {
    return titleCase(addr.split(/\s+/).map(w => STREET[w] || w).join(" "));
  }

  // ---------- speech ----------
  function speechControls() {
    ui.voice.disabled = caregiver || !canSpeak() || !steps.length;
    ui.voice.setAttribute("aria-pressed", String(voiceOn));
    ui.voice.textContent = !canSpeak() ? "Voice not available" : voiceOn ? "Stop voice" : "Start voice";
    ui.repeat.disabled = caregiver || !voiceOn || !steps.length;
    ui.speed.disabled = caregiver || !canSpeak() || !steps.length;
  }
  function stopSpeech() {
    speechVersion++;
    try { synth?.cancel(); } catch { /* Touch navigation does not depend on speech. */ }
    try { kokoro()?.stop(); } catch { /* Same: buttons keep working without audio. */ }
  }
  function stopListening() {
    const active = recognition;
    recognition = null;
    try { active?.abort(); } catch { /* Browser recognition may already be stopped. */ }
  }
  function speak(text) {
    ui.caption.textContent = text;
    if (!canSpeak() || !voiceOn || caregiver) return;
    stopSpeech();
    const version = speechVersion;
    if (kokoro()) { kokoro().speak(text); return; }
    const failed = () => {
      if (version !== speechVersion || !voiceOn) return;
      voiceOn = false;
      stopSpeech();
      speechControls();
      statusLine("Spoken steps are unavailable right now. Continue with the buttons, or try Start voice again.");
    };
    try {
      const u = new SpeechSynthesisUtterance(text);
      u.rate = ui.speed.value === "1" ? 1 : 0.8;
      u.lang = "en-US";
      u.onerror = failed;
      synth.speak(u);
    } catch { failed(); }
  }
  function statusLine(message) {
    const parts = [];
    if (message) parts.push(message);
    else if (!synth) parts.push("Spoken steps are unavailable in this browser. All steps remain available on screen.");
    else if (caregiver) parts.push("Caregiver view. Voice is off.");
    else parts.push(voiceOn ? "Voice is on." : "Voice is off. Choose Start voice to hear the current step.");
    if (Recognition) parts.push("The microphone is optional. Choose Say my answer to request microphone access.");
    else parts.push("Voice answers are unavailable in this browser. Use the answer buttons.");
    ui.status.textContent = parts.join(" ");
    ui.status.classList.toggle("warn", !!message || !Recognition || !synth);
  }
  function listen(heard, step) {
    if (!Recognition || caregiver || steps[index] !== step) return;
    stopListening();
    stopSpeech();
    try {
      const r = new Recognition();
      recognition = r;
      r.lang = "en-US";
      r.interimResults = false;
      r.maxAlternatives = 1;
      heard.textContent = "Listening. Say yes, no, or not sure.";
      r.onresult = e => {
        if (recognition !== r || caregiver || steps[index] !== step) return;
        const said = String(e.results?.[0]?.[0]?.transcript || "").toLowerCase();
        stopListening();
        const ans = /not sure|don'?t know|unsure|maybe/.test(said) ? "unsure"
          : /\b(no|nope|wrong|not right)\b/.test(said) ? "no"
          : /\b(yes|yeah|yep|right|correct|true)\b/.test(said) ? "yes" : null;
        if (ans) { heard.textContent = `I heard "${said}".`; answer(step, ans); }
        else { heard.textContent = `I heard "${said}". I did not understand. Please press a button.`; speak("I did not understand. Please press a button."); }
      };
      r.onerror = () => {
        if (recognition !== r) return;
        stopListening();
        heard.textContent = "Use the buttons, or try speaking again.";
      };
      r.onend = () => {
        if (recognition !== r) return;
        recognition = null;
        heard.textContent = "Listening ended. Use the buttons or try again.";
      };
      r.start();
    } catch {
      stopListening();
      heard.textContent = "Voice answers did not start. Please press a button.";
    }
  }

  // ---------- script ----------
  function permitYear(source) {
    const ev = house.events.find(e => e.permit === source);
    return ev ? ev.date.slice(0, 4) : null;
  }
  function buildSteps() {
    const g = Object.fromEntries(house.guessable.map(x => [x.field, x]));
    const addr = spokenAddress(house.address);
    const list = [{id: "greet", kind: "info", label: "Welcome", text: "Check your home details",
      help: "Confirm the address and the details you know. Anything uncertain can stay unknown.",
      next: "Start"}];
    list.push({id: "address", kind: "q", label: "Your address", field: "Home address", record: `${addr}, Austin ${house.zip}`, source: "Austin public records",
      text: `Records show your home is at ${addr}, Austin. Is that right?`});

    const amps = g.main_breaker_amps;
    const ampsText = amps && amps.value
      ? (/^\d{4}-/.test(amps.source)
        ? `Records show a ${amps.value} amp electric service, from permit ${amps.source}.`
        : `Records suggest a ${amps.value} amp electric service, based on the year your home was built.`)
      : "The electric service size is not on record.";
    list.push({id: "amps", kind: "info", label: "Electric service", text: ampsText, source: amps && amps.value ? amps.source : null,
      help: "The closed box is all you need to show. An electrical professional would confirm the service size on site.",
      next: "Okay, next"});

    const things = [["has_solar", "solar panels", "Solar panels"], ["has_battery", "a home battery", "Home battery"],
      ["has_generator", "a backup generator", "Backup generator"]];
    for (const [field, noun, label] of things) {
      const f = g[field];
      if (!f) continue;
      const year = f.value ? permitYear(f.source) : null;
      const text = f.value
        ? `Records show ${noun} ${year ? "added in " + year : "on your home"}. Is that right?`
        : `Records show no ${noun.replace(/^an? /, "")} at your home. Is that right?`;
      list.push({id: field, kind: "q", label, field: label, source: f.source, record: f.value ? `Yes${year ? ", added " + year : ""}` : "None on record", text,
        flip: f.value ? "Member says no" : "Member says yes"});
    }
    const ac = g.ac_age_years;
    if (ac && ac.value != null) {
      const y = permitYear(ac.source);
      list.push({id: "ac", kind: "q", label: "Air conditioner", field: "Air conditioner", source: ac.source, record: `Replaced ${y || "about " + ac.value + " years ago"}`,
        text: `Records show your air conditioner was replaced${y ? " in " + y : ""}, about ${ac.value} years ago. Is that right?`,
        flip: "Member says the date is different"});
    } else if (ac) {
      list.push({id: "ac", kind: "q", label: "Air conditioner", field: "Air conditioner", source: ac.source, record: "Not on record",
        text: "Was your air conditioner replaced in the last 10 years?",
        yesMeans: "Member says replaced in the last 10 years", flip: "Member says older than 10 years"});
    }
    list.push({id: "photo", kind: "photo", label: "Photo of the grey box", text: "Now one photo, if it is safe.",
      steps: ["Walk to the grey box beside your electric meter. It is usually on the outside wall. Some homes have it inside, in a garage or hallway.",
        "Stand one big step back, so the whole box fits in the picture.",
        "Keep all doors and covers closed.",
        "If it is dark, raining, flooded, unsafe, or you are unsure, skip the photo."]});
    list.push({id: "summary", kind: "summary", label: "Done", text: "Thank you. Here is what we have."});
    return list;
  }
  function spokenFor(step) {
    if (step.kind === "photo") return step.text + " " + step.steps.join(" ");
    if (step.kind === "summary") return step.text + " This summary stays on this page. No application, human review, or callback has been requested.";
    return step.text + (step.help ? " " + step.help : "");
  }

  // ---------- state ----------
  function answer(step, value) {
    answers[step.id] = value;
    if (caregiver) { renderCaregiver(); return; }
    go(index + 1);
  }
  function go(i) {
    stopListening();
    index = Math.max(0, Math.min(i, steps.length - 1));
    // Rewards hook (ADR 0015): mark the guide finished for this home, in this browser only.
    if (steps[index].kind === "summary") {
      try {
        const k = "base-fleet:voice:v1", v = JSON.parse(localStorage.getItem(k) || "{}") || {};
        v[house.address] = {done: true, photo: !!photo};
        localStorage.setItem(k, JSON.stringify(v));
        document.dispatchEvent(new Event("base-fleet:progress"));
      } catch { /* storage off: no credit tick */ }
    }
    renderGuided();
    speak(spokenFor(steps[index]));
  }
  function buckets() {
    const out = {confirmed: [], corrected: [], unknown: []};
    for (const s of steps.filter(s => s.kind === "q")) {
      const a = answers[s.id];
      if (a === "yes" && s.yesMeans) out.corrected.push(`${s.field}: ${s.yesMeans}`);
      else if (a === "yes") out.confirmed.push(`${s.field}: ${s.record}`);
      else if (a === "no") out.corrected.push(`${s.field}: ${s.flip || "Member says this is wrong"} (record said ${s.record})`);
      else out.unknown.push(`${s.field}: ${a === "unsure" ? "member not sure" : "not asked yet"}`);
    }
    const amps = house.guessable.find(x => x.field === "main_breaker_amps");
    const ampsLine = `Electric service: ${amps && amps.value ? amps.value + " amps from records" : "not on record"}, not professionally verified`;
    out.unknown.push(ampsLine);
    if (!photo) out.unknown.push("Panel photo: skipped or not taken");
    else if (photo.mode === "preview") out.unknown.push("Panel photo: preview only, not analyzed or submitted.");
    else if (photo.mode === "recorded") out.unknown.push("Panel photo: not checked; recorded example only. No review requested.");
    else if (photo.pass === true) out.unknown.push(`Panel photo: ${PHOTO_TYPES[photo.type] || photo.type}, local model suggests clear framing; unverified`);
    else out.unknown.push(`Panel photo: ${PHOTO_TYPES[photo.type] || photo.type}, retake needed`);
    return out;
  }

  // ---------- rendering ----------
  function answerButtons(step) {
    const box = el("div", "vg-answers");
    const helps = {yes: step.record ? `Record: ${step.record}` : "", no: "The record is wrong",
      unsure: "It can stay unknown"};
    for (const [v, label, icon] of [["yes", "Yes", "check"], ["no", "No", "close"], ["unsure", "Not sure", "help"]]) {
      const b = button(label, `vg-big ${v}`, () => answer(step, v));
      b.setAttribute("aria-pressed", String(answers[step.id] === v));
      b.setAttribute("data-icon", icon);
      if (helps[v]) b.setAttribute("data-help", helps[v]);
      box.append(b);
    }
    return box;
  }
  function photoBlock(step, host) {
    const figure = el("figure", "vg-example");
    const example = el("img");
    example.src = "assets/guide-panel.png";
    example.alt = "Illustration of a closed electrical panel enclosure";
    figure.append(example, el("figcaption", "", "Illustration, for reference only. Keep doors and covers closed."));
    host.append(figure);
    const input = el("input", "vg-file");
    input.type = "file";
    input.accept = "image/*";
    input.setAttribute("capture", "environment");
    input.id = `vg-file-${caregiver ? "cg" : "main"}`;
    const take = el("label", "vg-big yes", photo ? "Take the photo again" : "Take the photo");
    take.htmlFor = input.id;
    take.setAttribute("role", "button");
    take.tabIndex = 0;
    take.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    const result = el("div");
    result.setAttribute("aria-live", "polite");
    input.addEventListener("change", () => { if (input.files[0]) checkPhoto(input.files[0], result, step); });
    const row = el("div", "vg-row");
    row.append(take);
    if (!caregiver) row.append(button(photo ? "Next" : "Skip the photo", "vg-big", () => go(index + 1)));
    host.append(input, row, result);
    if (photo) showPhoto(result);
  }
  function icon(name, cls) {
    const i = el("span", "ms" + (cls ? " " + cls : ""), name);
    i.setAttribute("aria-hidden", "true");
    return i;
  }
  function renderRail() {
    if (!ui.rail) return;
    const qCount = steps.length - 1;
    const done = steps[index].kind === "summary" ? qCount : index;
    const pct = Math.round(done / qCount * 100);
    if (ui.railPct) ui.railPct.textContent = `${pct}% complete`;
    if (ui.railBar) ui.railBar.style.width = pct + "%";
    if (ui.railCount) ui.railCount.textContent = steps[index].kind === "summary" ? `All ${qCount} steps done` : `Step ${index + 1} of ${qCount}`;
    ui.rail.replaceChildren();
    steps.slice(0, qCount).forEach((s, i) => {
      const state = i < done ? "done" : i === index ? "now" : "next";
      const li = el("li", state);
      const dot = el("span", "dot");
      if (state === "done") dot.append(icon("check")); else dot.textContent = String(i + 1);
      const lbl = el("span", "lbl", `${i + 1}. ${s.label}`);
      if (state === "now") { lbl.textContent = s.label; lbl.append(el("small", "", "Current step")); li.setAttribute("aria-current", "step"); }
      li.append(dot, lbl);
      if (state === "done") li.append(el("span", "end", "Done"));
      if (state === "now") li.append(el("span", "end"));
      ui.rail.append(li);
    });
  }
  function renderGuided() {
    const step = steps[index];
    ui.caption.textContent = step.kind === "photo" && photo ? photoSpeech() : spokenFor(step);
    const card = ui.guided;
    const hadFocus = card.contains(document.activeElement);
    card.replaceChildren();
    const qCount = steps.length - 1;
    const meta = el("div", "vg-meta");
    const badges = el("div", "flex flex-wrap items-center gap-3");
    badges.append(el("p", "vg-step", step.kind === "summary" ? "Done" : `Step ${index + 1} of ${qCount}`));
    if (voiceOn && !caregiver) {
      const spoken = el("span", "vg-spoken");
      spoken.append(icon("record_voice_over"), el("span", "", "Spoken aloud"));
      badges.append(spoken);
    }
    meta.append(badges);
    card.append(meta);
    const h = el("h2", "vg-q", step.text);
    h.tabIndex = -1;
    card.append(h);
    if (step.kind === "info") {
      card.append(el("p", "vg-help", step.help));
      card.append(button(step.next, "vg-big yes", () => go(index + 1)));
    } else if (step.kind === "q") {
      card.append(el("p", "vg-help", "Press Yes, No, or Not sure."));
      card.append(answerButtons(step));
      const heard = el("p", "vg-heard");
      heard.setAttribute("role", "status");
      heard.setAttribute("aria-live", "polite");
      if (Recognition) card.append(button("Say my answer", "vg-big vg-mic", () => listen(heard, step)));
      card.append(heard);
    } else if (step.kind === "photo") {
      const ol = el("ol", "vg-steps");
      step.steps.forEach(s => ol.append(el("li", "", s)));
      card.append(ol);
      photoBlock(step, card);
    } else {
      card.append(summaryCard());
      card.append(button("Start over", "vg-big", () => { for (const k in answers) delete answers[k]; photo = null; go(0); }));
    }
    if (step.source || step.kind === "q") {
      const cite = el("div", "vg-cite");
      if (step.source) {
        const src = el("span");
        src.append(icon("verified"), el("span", "", `Source: ${step.source}`));
        cite.append(src);
      }
      const calm = el("span", "calm");
      calm.append(icon("schedule"), el("span", "", "Take your time."));
      cite.append(calm);
      card.append(cite);
    }
    if (index > 0) card.append(button("Go back one step", "vg-tool vg-back", () => go(index - 1)));
    renderRail();
    if (hadFocus) { h.focus({preventScroll: true}); h.scrollIntoView({block: "nearest"}); }
  }
  function summaryCard() {
    const b = buckets();
    const box = el("div", "vg-sum");
    for (const [key, title] of [["confirmed", "Your answers"], ["corrected", "Corrections"], ["unknown", "Unknown or unverified"]]) {
      box.append(el("h3", "", `${title} (${b[key].length})`));
      const ul = el("ul");
      if (!b[key].length) ul.append(el("li", "none", "Nothing here."));
      b[key].forEach(t => ul.append(el("li", "", t)));
      box.append(ul);
    }
    const call = el("div", "vg-call", "Your summary is complete.");
    call.append(el("small", "", "No application, human review, or callback has been requested. Nothing here is installation approval."));
    box.append(call);
    return box;
  }
  function renderCaregiver() {
    ui.cgList.replaceChildren();
    for (const step of steps) {
      const li = el("li");
      if (step.kind === "summary") {
        li.append(el("p", "", "Summary"));
        li.append(summaryCard());
      } else {
        li.append(el("p", "", step.text));
        if (step.help) li.append(el("p", "vg-help", step.help));
        if (step.kind === "q") li.append(answerButtons(step));
        if (step.kind === "photo") {
          const ol = el("ol", "vg-steps");
          step.steps.forEach(s => ol.append(el("li", "", s)));
          li.append(ol);
          photoBlock(step, li);
        }
      }
      ui.cgList.append(li);
    }
  }

  // ---------- photo check ----------
  async function timed(url, opts, ms) {
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), ms);
    try { return await fetch(url, {...opts, signal: c.signal}); } finally { clearTimeout(t); }
  }
  // A static host cannot reach the member's local model, so do not probe from there.
  const LOCAL_PAGE = /^(localhost|127\.0\.0\.1)$/.test(location.hostname)
    && !new URLSearchParams(location.search).has("static");
  async function ollamaReady() {
    if (!LOCAL_PAGE) return false;
    try {
      const r = await timed(`${OLLAMA}/api/tags`, {}, 2500);
      if (!r.ok) return false;
      const d = await r.json();
      return (d.models || []).some(m => m.name === MODEL);
    } catch { return false; }
  }
  function toBase64(file) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        const scale = Math.min(1, 1024 / Math.max(img.naturalWidth, img.naturalHeight));
        const c = document.createElement("canvas");
        c.width = Math.round(img.naturalWidth * scale);
        c.height = Math.round(img.naturalHeight * scale);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL("image/jpeg", 0.85).split(",")[1]);
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("not an image")); };
      img.src = url;
    });
  }
  async function recorded() {
    try {
      const response = await fetch("../panel/pred_gemini.jsonl");
      if (!response.ok) return null;
      const text = await response.text();
      const rows = text.trim().split("\n").map(l => JSON.parse(l));
      return validatePhoto(rows.find(r => r.file === RECORDED_SAMPLE) || rows[0]);
    } catch { return null; }
  }
  function validatePhoto(out) {
    if (!out || Array.isArray(out) || typeof out !== "object"
        || typeof out.pass !== "boolean" || !Object.hasOwn(PHOTO_TYPES, out.photo_type)
        || !(out.retake_reason === null || typeof out.retake_reason === "string")) {
      throw new Error("Invalid photo result");
    }
    return out;
  }
  async function checkPhoto(file, host, step) {
    if (checking) return;
    checking = true;
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = URL.createObjectURL(file);
    if (!LOCAL_PAGE) {
      photo = {mode: "preview"};
      checking = false;
      if (caregiver) renderCaregiver(); else renderGuided();
      speak(photoSpeech());
      return;
    }
    host.replaceChildren(el("p", "vg-result", "Checking whether the local model is available. A photo check can take up to five minutes. You can skip this step."));
    speak("Checking your photo. Please wait.");
    try {
      if (await ollamaReady()) {
        const t0 = performance.now();
        const b64 = await toBase64(file);
        const r = await timed(`${OLLAMA}/api/chat`, {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({model: MODEL, stream: false, think: false, format: "json",
            messages: [{role: "user", content: PROMPT, images: [b64]}]})}, 300000);
        if (!r.ok) throw new Error("Photo check unavailable");
        const out = validatePhoto(JSON.parse((await r.json()).message.content));
        photo = {mode: "live", type: out.photo_type, pass: out.pass, retake: out.retake_reason,
          secs: Math.round((performance.now() - t0) / 100) / 10};
      } else {
        const rec = await recorded();
        photo = {mode: "recorded", type: rec && rec.photo_type, pass: rec && rec.pass, retake: rec && rec.retake_reason, file: rec && rec.file};
      }
    } catch {
      const rec = await recorded();
      photo = {mode: "recorded", type: rec && rec.photo_type, pass: rec && rec.pass, retake: rec && rec.retake_reason, file: rec && rec.file};
    }
    checking = false;
    if (caregiver) { renderCaregiver(); return; }
    renderGuided();
    if (steps[index].kind === "photo") speak(photoSpeech());
  }
  function photoSpeech() {
    if (photo.mode === "preview") return "Your photo is a preview only. It was not analyzed, saved, or submitted. You can continue or choose another photo.";
    if (photo.mode === "recorded") return "Any recorded result below is an unrelated sample. No human review or callback has been requested. You can continue or try again.";
    if (photo.pass === true) return "The local model suggests the framing is clear. This is unverified, not an electrical assessment or installation approval. You can continue.";
    return `The local model suggests a clearer photo. ${SAFE_RETAKE} This is not an electrical assessment or installation approval.`;
  }
  function showPhoto(host) {
    host.replaceChildren();
    if (photoUrl) {
      const img = el("img", "vg-photo");
      img.src = photoUrl;
      img.alt = "Your photo";
      host.append(img);
    }
    if (photo.mode === "preview") {
      host.append(el("p", "vg-result", photoSpeech()));
      return;
    }
    const box = el("div", "vg-result");
    const dl = el("dl");
    const add = (k, v) => { dl.append(el("dt", "", k), el("dd", "", v)); };
    if (photo.mode === "recorded") {
      box.append(el("p", "", "This is an unrelated sample result. No human review or callback has been requested."));
      box.append(el("span", "vg-tag", photo.file ? "Recorded example, not your photo" : "Photo check not available"));
      box.append(el("p", "", photo.file
        ? `Below is a recorded result from an earlier cloud run on sample photo ${photo.file}, shown as an example only.`
        : "You can continue without a photo check, or try again."));
    } else {
      box.append(el("span", "vg-tag live", `On-device check, ${photo.secs} s`));
    }
    if (photo.mode === "live" || photo.file) {
      add(photo.mode === "recorded" ? "Sample photo type" : "Suggested photo type", PHOTO_TYPES[photo.type] || "Unclear");
      add("Model suggestion", photo.pass === true ? (photo.mode === "recorded" ? "Sample result only; not a check of your photo's framing" : "Framing appears clear, unverified") : "Retake suggested, unverified");
      if (photo.pass === false) add("Retake suggestion", SAFE_RETAKE);
      box.append(dl);
    }
    box.append(el("p", "", "Model suggestions are informal, not professional verification or installation approval. The closed box is all you need to show."));
    box.append(el("p", "", SAFE_RETAKE));
    host.append(box);
  }

  // ---------- controls ----------
  ui.caregiver.addEventListener("click", () => {
    if (!steps.length) return;
    caregiver = !caregiver;
    ui.caregiver.setAttribute("aria-checked", String(caregiver));
    stopListening();
    voiceOn = false;
    stopSpeech();
    ui.guided.hidden = caregiver;
    ui.cgView.hidden = !caregiver;
    speechControls();
    statusLine();
    if (caregiver) renderCaregiver(); else renderGuided();
  });
  ui.voice.addEventListener("click", () => {
    if (!synth || caregiver || !steps.length) return;
    voiceOn = !voiceOn;
    stopListening();
    speechControls();
    statusLine();
    renderGuided();
    if (voiceOn) speak(currentSpeech()); else stopSpeech();
  });
  function currentSpeech() {
    const step = steps[index];
    return step.kind === "photo" && photo ? photoSpeech() : spokenFor(step);
  }
  ui.repeat.addEventListener("click", () => {
    if (!voiceOn || caregiver || !steps.length) return;
    stopListening();
    speak(currentSpeech());
  });
  ui.speed.addEventListener("change", () => {
    if (voiceOn && !caregiver && steps.length) speak(currentSpeech());
  });
  speechControls();

  async function start() {
    statusLine();
    ui.guided.replaceChildren(el("p", "vg-help", "Loading your home records..."));
    try {
      const data = await (await fetch("../house/cohort.json")).json();
      const want = new URLSearchParams(location.search).get("address") || SAMPLE_ADDRESS;
      house = data.find(h => h.address === want) || data.find(h => h.address === SAMPLE_ADDRESS) || data[0];
    } catch {
      ui.guided.replaceChildren(el("p", "vg-help", "Your home records did not load. Please reload the page, or ask a caregiver for help."));
      ui.caption.textContent = "Reload the page to load sample records.";
      return;
    }
    steps = buildSteps();
    index = 0;
    renderGuided();
    speechControls();
  }
  start();
})();
