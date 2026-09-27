(() => {
  "use strict";

  // Member home view: the house as a picture. Records fill most parts;
  // the member answers only the parts that records do not settle.
  const SVGNS = "http://www.w3.org/2000/svg";
  const FIELDS = {
    main_breaker_amps: {name: "Electric panel", kind: "number",
      chips: [[100, "100 A"], [150, "150 A"], [200, "200 A"]], ask: "What size is your main breaker?"},
    has_solar: {name: "Solar panels", kind: "boolean", thing: "solar panels", one: "solar panels"},
    has_battery: {name: "Home battery", kind: "boolean", thing: "battery", one: "a home battery"},
    has_generator: {name: "Generator", kind: "boolean", thing: "generator", one: "a generator"},
    ac_age_years: {name: "A/C unit", kind: "number",
      chips: [[3, "Under 5"], [10, "5 to 15"], [20, "Over 15"]], ask: "How old is your A/C unit, in years?"}
  };
  const ORDER = ["has_solar", "has_battery", "main_breaker_amps", "ac_age_years", "has_generator"];

  // Drawing of each part, in a 640 x 380 view box. badge = status mark position, hit = tap area.
  const ART = {
    has_solar: {badge: [484, 150], hit: [330, 70, 170, 110], body: `
      <g transform="translate(338 96) rotate(30.26)"><rect class="p-body" x="0" y="0" width="150" height="40" rx="2"/>
      <path class="p-line" d="M37.5 0v40M75 0v40M112.5 0v40M0 20h150"/></g>`},
    has_battery: {badge: [186, 214], hit: [140, 196, 60, 110], body: `
      <rect class="p-body" x="152" y="218" width="30" height="74" rx="4"/>
      <rect class="p-fill" x="159" y="228" width="16" height="6" rx="1"/>
      <path class="p-line" d="M167 252l-5 12h10l-5 12"/>`},
    main_breaker_amps: {badge: [492, 204], hit: [446, 190, 62, 90], body: `
      <rect class="p-body" x="454" y="208" width="34" height="56" rx="3"/>
      <path class="p-line" d="M460 220h22M460 230h22M460 240h22M460 250h22M471 214v44"/>`},
    ac_age_years: {badge: [592, 268], hit: [506, 256, 100, 84], body: `
      <rect class="p-body" x="516" y="276" width="72" height="54" rx="4"/>
      <circle class="p-line" cx="552" cy="303" r="18"/><path class="p-line" d="M552 285v36M534 303h36M539 290l26 26M565 290l-26 26"/>`},
    has_generator: {badge: [120, 282], hit: [34, 268, 100, 76], body: `
      <rect class="p-body" x="46" y="288" width="72" height="42" rx="5"/>
      <rect class="p-line" x="56" y="298" width="22" height="14" rx="2"/>
      <path class="p-line" d="M96 296l-6 11h9l-6 11"/><path class="p-line" d="M52 330v6M112 330v6"/>`},
    meter: {badge: [440, 212], hit: [404, 198, 42, 66], body: `
      <rect class="p-body" x="412" y="218" width="28" height="36" rx="3"/>
      <circle class="p-line" cx="426" cy="232" r="8"/><path class="p-line" d="M426 232l4-4"/>`}
  };

  const KIND_ICON = {
    solar: ["Solar", '<circle cx="8" cy="8" r="3"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/>'],
    battery: ["Battery", '<rect x="4" y="3" width="8" height="11" rx="1"/><path d="M6.5 1.5h3M8 6l-1.5 3h3L8 12"/>'],
    generator: ["Generator", '<rect x="2" y="4" width="12" height="9" rx="1.5"/><path d="M8.5 5.5l-2 3.5h3l-2 3"/>'],
    service_upgrade: ["Electric service", '<path d="M9 1.5L3.5 9H8l-1 5.5L12.5 7H8z"/>'],
    temp_power: ["Temporary power", '<path d="M6 2v4M10 2v4M4 6h8v3a4 4 0 0 1-8 0zM8 13v2"/>'],
    ac_changeout: ["A/C", '<path d="M8 1.5v13M2.4 4.75l11.2 6.5M2.4 11.25l11.2-6.5"/>'],
    built: ["New home", '<path d="M2 8l6-5.5L14 8M4 7v7h8V7"/>'],
    addition: ["Addition", '<rect x="2" y="2" width="12" height="12" rx="1"/><path d="M8 5v6M5 8h6"/>'],
    remodel: ["Remodel", '<path d="M3 13l6.5-6.5M8 3.5l4.5 4.5 1.5-1.5L9.5 2z"/>'],
    pool: ["Pool", '<path d="M1.5 6c2-1.5 3 1.5 5 0s3 1.5 5 0 2.5 0 3 0M1.5 10.5c2-1.5 3 1.5 5 0s3 1.5 5 0 2.5 0 3 0"/>'],
    demolition: ["Demolition", '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/>'],
    demolition_accessory: ["Demolition", '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/>'],
    other: ["Other permit", '<path d="M4 1.5h5.5L12 4v10.5H4zM6 7.5h4M6 10h4"/>']
  };
  const KIND_RANK = ["solar", "battery", "generator", "service_upgrade", "ac_changeout", "built", "temp_power",
    "addition", "remodel", "pool", "demolition", "demolition_accessory", "other"];
  const ENERGY = new Set(["solar", "battery", "generator", "service_upgrade", "ac_changeout", "temp_power"]);

  function start() {
    const $ = id => document.getElementById(id);
    const ui = {select: $("address-select"), art: $("house-art"), tip: $("part-tip"), wrap: $("house-wrap"),
      questions: $("questions"), timeline: $("permit-timeline"), more: $("timeline-more"), status: $("status-message"),
      input: $("address-input"), list: $("address-list"), search: $("address-search"), hint: $("address-hint"),
      confirm: $("confirm-property"),
      line: $("progress-line"), reset: $("reset-progress"), retry: $("retry-load"),
      next: $("continue-question"), back: $("back-question"), help: $("panel-help")};
    if (Object.values(ui).some(v => !v)) return;

    let houses = [], house = null, saved = {}, photo = false, storageNote = "", tipFor = null, step = 0;
    let ptc = null, matches = [], active = -1, showAll = false, editing = false;

    const el = (tag, text, cls) => {
      const n = document.createElement(tag);
      if (text != null) n.textContent = String(text);
      if (cls) n.className = cls;
      return n;
    };
    const say = msg => { ui.status.textContent = msg + (storageNote ? " " + storageNote : ""); };
    const key = () => `base-fleet:journey:v1:${house.address}`;
    const asked = () => [...new Set(house.confirm_with_member)].filter(f => FIELDS[f]);
    const guess = f => house.guessable.find(g => g.field === f) || {field: f, value: null, confidence: 0, source: ""};

    function valid(f, v) {
      if (v === null) return true;
      return FIELDS[f].kind === "boolean" ? typeof v === "boolean" : Number.isInteger(v) && v >= 0;
    }

    function restore() {
      saved = {};
      photo = false;
      storageNote = "";
      try {
        const stored = JSON.parse(localStorage.getItem(key()) || "null");
        photo = !!(stored && stored.photo === true);
        if (stored && stored.saved) {
          for (const f of asked()) if (Object.hasOwn(stored.saved, f) && valid(f, stored.saved[f])) saved[f] = stored.saved[f];
        }
      } catch { storageNote = "Restart to load saved answers."; }
    }

    function persist() {
      const open = ORDER.filter(f => asked().includes(f)).length;
      try { localStorage.setItem(key(), JSON.stringify({version: 2, saved, open, photo})); storageNote = ""; }
      catch { storageNote = "Browser storage is off. Keep this page open to keep your answers."; }
      document.dispatchEvent(new Event("base-fleet:progress"));
    }

    function valueText(f, v) {
      const def = FIELDS[f];
      if (v == null) return "Not known";
      if (def.kind === "boolean") return v ? `Has ${def.thing}` : `No ${def.thing}`;
      const chip = def.chips.find(c => c[0] === v);
      if (f === "ac_age_years") return `${chip ? chip[1] : v} years old`;
      return chip ? `${chip[1]} main breaker` : `${v} A main breaker`;
    }

    function sourceText(src) {
      const s = String(src || "").trim();
      if (!s) return "No record";
      const ev = house.events.find(e => e.permit === s);
      if (ev) {
        const label = (KIND_ICON[ev.kind] || KIND_ICON.other)[0].toLowerCase().replace(/ permit$/, "");
        return `${String(ev.date).slice(0, 4)} ${label} permit`;
      }
      if (/^\d{4}-\d+/.test(s)) return `${s.slice(0, 4)} city permit`;
      return s.charAt(0).toUpperCase() + s.slice(1);
    }

    // State of one part: known (solid), guess (amber), unknown (grey dashed).
    function partState(f) {
      const g = guess(f), isAsked = asked().includes(f);
      if (Object.hasOwn(saved, f)) {
        return saved[f] === null ? {state: "unknown", by: "you", value: null} : {state: "known", by: "you", value: saved[f]};
      }
      if (FIELDS[f].kind === "boolean" && g.value === false && /^no .*permit|^no permit/i.test(g.source)) return {state: "unknown", by: "records", value: null};
      if (!isAsked) return {state: g.value == null ? "unknown" : "known", by: "records", value: g.value};
      return {state: g.value == null ? "unknown" : "guess", by: "records", value: g.value};
    }

    function meterState() {
      const ev = house.events.filter(e => e.kind === "service_upgrade" || e.kind === "temp_power")
        .sort((a, b) => String(b.date).localeCompare(String(a.date)))[0];
      return ev ? {state: "guess", value: "Electrical work recorded", source: `${sourceText(ev.permit)}; meter position not recorded.`, conf: 0.4}
        : {state: "unknown", value: "No record", source: "Meter position needs a site check.", conf: 0};
    }

    function badge(state, x, y) {
      const mark = state === "known" ? '<path class="b-mark" d="M-5 0l3.5 3.5L5.5-4"/>'
        : state === "guess" ? '<text class="b-q" x="0" y="5" text-anchor="middle">?</text>'
        : '<path class="b-mark" d="M-4.5 0h9"/>';
      return `<g class="p-badge" transform="translate(${x} ${y})"><circle r="12"/>${mark}</g>`;
    }

    function drawHouse() {
      const parts = [...ORDER, "meter"].map(f => {
        const a = ART[f];
        const st = f === "meter" ? meterState() : partState(f);
        const none = st.value === false ? " is-none" : "";
        const [x, y, w, h] = a.hit;
        const label = f === "meter" ? "Electric meter" : FIELDS[f].name;
        return `<g class="part ${st.state}${none}" data-part="${f}" tabindex="0" role="button" aria-label="${label}">
          <rect class="p-hit" x="${x}" y="${y}" width="${w}" height="${h}" rx="10"/>${a.body}${badge(st.state, ...a.badge)}</g>`;
      }).join("");
      ui.art.innerHTML = `<svg class="house-svg" viewBox="0 0 640 380" role="group" aria-label="Drawing of your home. Select a part to see what records say.">
        <rect class="h-sky" x="0" y="0" width="640" height="380" rx="10"/>
        <path class="h-ground" d="M0 330h640v40a10 10 0 0 1-10 10H10a10 10 0 0 1-10-10z"/>
        <path class="h-roof" d="M122 178L310 66l188 112z"/>
        <rect class="h-wall" x="140" y="172" width="360" height="158"/>
        <rect class="h-window" x="208" y="206" width="54" height="44" rx="2"/><path class="h-frame" d="M235 206v44M208 228h54"/>
        <rect class="h-window" x="338" y="206" width="54" height="44" rx="2"/><path class="h-frame" d="M365 206v44M338 228h54"/>
        <rect class="h-door" x="282" y="262" width="36" height="68" rx="2"/>
        <path class="h-wire" d="M440 236h14M118 306h22"/>
        ${parts}</svg>`;
      ui.art.setAttribute("aria-busy", "false");
      ui.art.querySelectorAll(".part").forEach(g => {
        const f = g.dataset.part;
        g.addEventListener("pointerenter", e => { if (e.pointerType === "mouse") showTip(f); });
        g.addEventListener("pointerleave", e => { if (e.pointerType === "mouse" && g !== document.activeElement) hideTip(); });
        g.addEventListener("focus", () => showTip(f));
        g.addEventListener("blur", hideTip);
        g.addEventListener("click", e => { e.stopPropagation(); showTip(f); });
        g.addEventListener("keydown", e => {
          if (e.key !== "Enter" && e.key !== " ") return;
          e.preventDefault();
          const first = ui.questions.querySelector(`[data-field="${f}"] button`);
          if (first) first.focus(); else showTip(f);
        });
      });
    }

    function showTip(f) {
      tipFor = f;
      let name, value, source, conf;
      if (f === "meter") {
        ({value, source, conf} = meterState());
        name = "Electric meter";
      } else {
        const st = partState(f), g = guess(f);
        name = FIELDS[f].name;
        value = st.by === "you" ? valueText(f, st.value) : g.value == null ? "Not known yet" : valueText(f, g.value);
        source = st.by === "you" ? "Your answer, saved on this device" : sourceText(g.source);
        conf = st.by === "you" ? (st.value === null ? 0 : 1) : Number(g.confidence) || 0;
      }
      const pct = Math.round(conf * 100);
      const bar = el("span", null, "tip-bar");
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", `Confidence ${pct} percent`);
      const fill = el("i");
      fill.style.width = pct + "%";
      bar.append(fill);
      ui.tip.replaceChildren(el("strong", `${name}: ${value}`), el("span", source, "tip-src"), bar);
      ui.tip.hidden = false;
      const hit = ui.art.querySelector(`[data-part="${f}"] .p-hit`);
      const r = hit.getBoundingClientRect(), w = ui.wrap.getBoundingClientRect();
      const tw = ui.tip.offsetWidth;
      const left = Math.max(4, Math.min(r.left - w.left + r.width / 2 - tw / 2, w.width - tw - 4));
      let top = r.top - w.top - ui.tip.offsetHeight - 6;
      if (top < 4) top = r.bottom - w.top + 6;
      ui.tip.style.left = left + "px";
      ui.tip.style.top = top + "px";
      ui.art.querySelectorAll(".part").forEach(p => p.classList.toggle("is-lit", p.dataset.part === f));
      ui.questions.querySelectorAll(".q-card").forEach(c => c.classList.toggle("is-lit", c.dataset.field === f));
    }

    function hideTip() {
      tipFor = null;
      ui.tip.hidden = true;
      document.querySelectorAll("#home-view .is-lit").forEach(p => p.classList.remove("is-lit"));
    }

    function answer(f, v) {
      saved[f] = v;
      persist();
      render();
      const again = ui.questions.querySelector(`[data-field="${f}"] [aria-pressed="true"]`);
      if (again) again.focus({preventScroll: true});
      say(v === null ? `${FIELDS[f].name}: left open. You can update this later.`
        : `${FIELDS[f].name}: ${valueText(f, v).toLowerCase()}. Saved on this device.`);
    }

    function choice(text, cls, pressed, onClick, label) {
      const b = el("button", text, "q-btn " + cls);
      b.type = "button";
      b.setAttribute("aria-pressed", String(pressed));
      if (label) b.setAttribute("aria-label", label);
      b.addEventListener("click", onClick);
      return b;
    }

    function renderQuestions() {
      ui.questions.replaceChildren();
      const list = ORDER.filter(f => asked().includes(f));
      const reviewing = step >= list.length;
      ui.help.hidden = reviewing || list[step] !== "main_breaker_amps";
      ui.next.hidden = reviewing;
      ui.next.disabled = !Object.hasOwn(saved, list[step]);
      ui.next.textContent = step === list.length - 1 ? "Review answers" : "Continue";
      ui.back.hidden = step === 0;
      ui.back.textContent = reviewing ? "Back to questions" : "Back";
      if (reviewing) {
        const title = el("h2", "Review your home details");
        title.tabIndex = -1;
        ui.questions.append(title);
        const rows = el("dl", null, "home-review");
        for (const f of ORDER) {
          const state = partState(f), row = el("div", null, "review-row");
          row.append(el("dt", FIELDS[f].name));
          const value = el("dd");
          value.append(el("strong", valueText(f, state.value)),
            el("span", state.by === "you" ? (state.value === null ? "Left open by you" : "Your answer")
              : sourceText(guess(f).source), "q-src"));
          row.append(value);
          if (list.includes(f)) {
            const edit = el("button", "Edit", "quiet");
            edit.type = "button";
            edit.setAttribute("aria-label", "Edit " + FIELDS[f].name);
            edit.addEventListener("click", () => { step = list.indexOf(f); render(); focusQuestion(); });
            row.append(edit);
          }
          rows.append(row);
        }
        ui.questions.append(rows, el("p", "Check each answer, then add your photos.", "review-note"));
        const actions = el("div", null, "review-actions");
        const photos = el("button", "Prepare installation photos", "primary");
        photos.type = "button";
        photos.addEventListener("click", () => {
          const checklist = document.getElementById("photo-checklist");
          const details = checklist.querySelector("details");
          if (details) details.open = true;
          checklist.scrollIntoView({block: "nearest"});
          const target = checklist.querySelector("summary,button,select");
          if (target) target.focus({preventScroll: true});
        });
        const guide = el("a", "Review with voice guidance", "primary");
        guide.href = guideHref();
        const help = el("a", "Ask a question");
        help.href = "brain.html?" + new URLSearchParams({track: "home", persona: "lead", address: house.address});
        actions.append(photos, guide, help);
        ui.questions.append(actions);
        return;
      }
      for (const f of [list[step]]) {
        const def = FIELDS[f], g = guess(f), st = partState(f);
        const has = Object.hasOwn(saved, f), cur = saved[f];
        const card = el("div", null, "q-card" + (has ? (cur === null ? " is-skipped" : " is-done") : ""));
        card.dataset.field = f;
        card.addEventListener("pointerenter", e => { if (e.pointerType === "mouse") showTip(f); });
        card.addEventListener("pointerleave", e => { if (e.pointerType === "mouse") hideTip(); });
        const icon = document.createElementNS(SVGNS, "svg");
        icon.setAttribute("viewBox", ART[f].hit.join(" "));
        icon.setAttribute("class", `q-icon part ${st.state}${st.value === false ? " is-none" : ""}`);
        icon.setAttribute("aria-hidden", "true");
        icon.innerHTML = ART[f].body;
        const words = el("div", null, "q-words");
        const missingPermit = def.kind === "boolean" && g.value === false && /^no .*permit|^no permit/i.test(g.source);
        const question = def.kind === "number" ? def.ask
          : g.value == null || missingPermit ? `Do you have ${def.one}?` : `${valueText(f, g.value)} on record. Right?`;
        words.append(el("strong", question),
          el("span", missingPermit ? "No permit found. Equipment may still be present." : g.value == null ? "Records do not say." : `From: ${sourceText(g.source)}`, "q-src"));
        const head = el("div", null, "q-head");
        head.append(icon, words);
        const row = el("div", null, "q-row" + (def.kind === "number" ? " is-chips" : ""));
        if (def.kind === "boolean" && g.value != null && !missingPermit) {
          row.append(choice("Yes, that's right", "q-yes", has && cur === g.value, () => answer(f, g.value), `Yes, that's right: ${valueText(f, g.value)}`),
            choice("No", "q-no", has && cur === !g.value, () => answer(f, !g.value), `No: ${valueText(f, !g.value)}`));
        } else if (def.kind === "boolean") {
          row.append(choice("Yes", "q-yes", cur === true, () => answer(f, true), `Yes: ${valueText(f, true)}`),
            choice("No", "q-no", cur === false, () => answer(f, false), `No: ${valueText(f, false)}`));
        } else {
          for (const [v, text] of def.chips) {
            const b = choice(text, "q-chip", cur === v, () => answer(f, v), `${def.name}: ${text}`);
            if (g.value === v) { b.classList.add("is-suggested"); b.title = "Records suggest this"; }
            row.append(b);
          }
        }
        row.append(choice("Not sure", "q-skip", has && cur === null, () => answer(f, null), `Not sure: ${def.name}`));
        card.append(head, row);
        ui.questions.append(card);
      }
    }

    function renderProgress() {
      const list = ORDER.filter(f => asked().includes(f));
      ui.line.textContent = step >= list.length ? "Review answers" : `Question ${step + 1} of ${list.length}`;
    }

    function focusQuestion() {
      const target = ui.questions.querySelector("h2, .q-btn");
      if (target) target.focus({preventScroll: true});
    }

    // Permit history, newest first. Energy permits (solar, battery, service work) are highlighted and always shown.
    const SHORT = 4;
    function renderTimeline() {
      const evs = house.events.slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
      const n = evs.length;
      setText("timeline-count", `${n} permit${n === 1 ? "" : "s"}, City of Austin`);
      setText("timeline-count-chip", String(n));
      ui.timeline.replaceChildren();
      evs.forEach((e, i) => {
        const kind = KIND_ICON[e.kind] ? e.kind : "other";
        const energy = ENERGY.has(kind);
        if (!showAll && !energy && i >= SHORT) return;
        const li = el("li", null, "jr-tl-item" + (energy ? " is-energy" : ""));
        const dot = el("span", null, "jr-tl-dot");
        const svg = document.createElementNS(SVGNS, "svg");
        svg.setAttribute("viewBox", "0 0 16 16");
        svg.setAttribute("aria-hidden", "true");
        svg.innerHTML = KIND_ICON[kind][1];
        dot.append(svg);
        const body = el("div", null, "jr-tl-body");
        const top = el("p", null, "jr-tl-top");
        top.append(el("strong", KIND_ICON[kind][0]), el("span", String(e.date || "").slice(0, 10), "jr-tl-date"));
        const meta = el("p", null, "jr-tl-meta");
        meta.append(el("span", `Permit ${e.permit}`, "jr-tl-permit"));
        if (e.old_structure) meta.append(el("span", "Earlier structure", "jr-tl-tag"));
        const text = String(e.text || "").replace(/\s+/g, " ").trim();
        body.append(top, meta);
        if (text) body.append(el("p", text.length > 140 ? text.slice(0, 137).trimEnd() + "..." : text, "jr-tl-text"));
        li.append(dot, body);
        ui.timeline.append(li);
      });
      if (!n) ui.timeline.append(el("li", "Your permit history starts with your first City of Austin permit.", "jr-tl-empty"));
      const extra = evs.filter((e, i) => i >= SHORT && !ENERGY.has(KIND_ICON[e.kind] ? e.kind : "other")).length;
      ui.more.hidden = extra === 0;
      ui.more.textContent = showAll ? "Show fewer permits" : `Show all ${n} permits`;
      ui.more.setAttribute("aria-expanded", String(showAll));
    }

    function render() {
      hideTip();
      drawHouse();
      renderQuestions();
      renderProgress();
      renderTable();
    }

    const setText = (id, text) => { const n = $(id); if (n) n.textContent = text; };

    const titleCase = t => String(t).toLowerCase().replace(/\b([a-z])/g, c => c.toUpperCase());
    const display = h => `${titleCase(h.address)}, Austin, TX${h.zip ? " " + h.zip : ""}`;

    // Find-your-home card: only fields the permit record holds.
    function renderFacts() {
      setText("record-address", display(house));
      setText("head-address", display(house));
      setText("fact-year", house.year_built || "To confirm");
      const n = house.events.length;
      setText("fact-permits", `${n} City permit${n === 1 ? "" : "s"} on file`);
      const amps = guess("main_breaker_amps");
      const src = String(amps.source || "");
      setText("fact-amps", amps.value ? `${amps.value} A service` : "Amps to confirm");
      $("fact-amps-box").classList.toggle("is-ask", !amps.value);
      setText("fact-amps-src", amps.value
        ? (/^no .*permit/i.test(src) ? "Estimate from the permit history" : `Estimate: ${src}`)
        : src ? `Panel work on permit ${src}` : "You confirm the size below");
      const fit = house.fit && typeof house.fit === "object" && Array.isArray(house.fit.reasons) ? house.fit.reasons : [];
      const fitHost = $("fact-fit");
      fitHost.replaceChildren(...fit.map(r => el("span", r.charAt(0).toUpperCase() + r.slice(1),
        "px-2.5 py-1 rounded bg-surface-subtle text-ink-primary font-body-sm text-body-sm")));
      $("fit-box").hidden = !fit.length;
      renderUtility();
      const util = ptc && ptc.zips && house.zip && ptc.zips[house.zip];
      setText("record-src", `Found in City of Austin permits${util ? " and Power to Choose" : ""}`);
      setText("house-address", titleCase(house.address));
      setText("house-zip", `Austin ${house.zip || ""}`.trim());
    }

    // Utility territory from the Power to Choose zip check (data/ptc_tdu.json). Shown only when the zip is listed.
    function renderUtility() {
      const row = ptc && ptc.zips && house.zip ? ptc.zips[house.zip] : null;
      $("fact-utility-box").hidden = !row;
      if (!row) return;
      const tdus = Object.keys(row.tdus || {});
      const when = ptc.fetched ? `, checked ${ptc.fetched}` : "";
      if (tdus.length) {
        setText("fact-utility", tdus.map(titleCase).join(", "));
        setText("fact-utility-src", `Retail choice zip: ${row.plans} plans on Power to Choose${when}.`);
      } else {
        setText("fact-utility", "Municipal or co-op utility");
        setText("fact-utility-src", `The local utility serves ${house.zip} directly (Power to Choose${when}).`);
      }
    }

    function isConfirmed() {
      try { const h = JSON.parse(localStorage.getItem("base-fleet:home:v1") || "null"); return !!(h && h.address === house.address); }
      catch { return false; }
    }

    function renderConfirm() {
      const ok = isConfirmed();
      setText("confirm-label", ok ? "Home confirmed" : "Yes, this is my home");
      setText("confirm-note", ok ? "Saved on this device." : "");
      renderStep();
    }

    // Stitch step header, driven by the shared milestone tracker (milestones.js).
    function renderStep() {
      const M = window.BaseMilestones;
      const bars = $("step-bars");
      if (!M || !house || !bars) return;
      const names = M.MILESTONES, st = M.state().status.slice();
      if (!isConfirmed()) { st[0] = "now"; for (let i = 1; i < st.length; i++) if (st[i] !== "base") st[i] = "next"; }
      let cur = st.findIndex(x => x === "now");
      if (cur < 0) cur = Math.min(st.lastIndexOf("done") + 1, names.length - 1);
      setText("step-text", `Step ${cur + 1} of ${names.length}: ${names[cur]}`);
      bars.replaceChildren(...st.map(x => el("span", null, "jr-bar" + (x === "done" ? " is-done" : x === "now" ? " is-now" : ""))));
      renderColumns(st);
    }

    // The three step cards: the current one is highlighted, done ones collapse to one line, later ones are dimmed.
    const CHIP_TEXT = {now: "You are here", done: "Done", next: ""};
    function renderColumns(st) {
      const cols = ["find-home", "details", "photos"].map($);
      let states = cols.map((c, i) => st[i] === "done" ? "done" : st[i] === "now" ? "now" : "next");
      if (!states.includes("now")) { const i = states.indexOf("next"); if (i >= 0) states[i] = "now"; }
      cols.forEach((c, i) => {
        c.dataset.state = states[i];
        const chip = c.querySelector("[data-step-chip]");
        chip.textContent = CHIP_TEXT[states[i]];
        if (states[i] === "now") c.setAttribute("aria-current", "step"); else c.removeAttribute("aria-current");
      });
      const folded = states[0] === "done" && !editing;
      $("find-body").hidden = folded;
      $("find-summary").hidden = !folded;
      const n = house.events.length;
      setText("find-summary-text", `${titleCase(house.address)} · Built ${house.year_built || "year to confirm"} · ${n} permit${n === 1 ? "" : "s"}`);
    }

    // Recorded vs estimated vs confirmed, one row per part of the house.
    const ROW_ICON = {has_solar: "solar_power", has_battery: "battery_charging_full", main_breaker_amps: "electrical_services",
      ac_age_years: "mode_fan", has_generator: "bolt"};
    function renderTable() {
      const host = $("record-table");
      if (!host) return;
      host.replaceChildren();
      let open = 0;
      for (const f of ORDER) {
        const g = guess(f), st = partState(f), isAsked = asked().includes(f);
        const list = ORDER.filter(x => asked().includes(x));
        const current = list[step] === f;
        const row = el("div", null, "st-row ob-row" + (isAsked && st.by !== "you" ? " is-ask" : "") + (current ? " is-current" : ""));
        const a = el("div", null, "ob-row-part");
        a.append(el("span", "Part", "text-label-caps font-label-caps text-outline uppercase block"));
        const name = el("div", null, "flex items-center gap-2");
        const ic = el("span", ROW_ICON[f], "material-symbols-outlined text-outline text-[18px]");
        ic.setAttribute("aria-hidden", "true");
        name.append(ic, el("p", FIELDS[f].name, "font-headline-sm text-headline-sm text-ink-primary"));
        a.append(name);
        const b = el("div", null, "ob-row-rec");
        b.append(el("span", isAsked ? "Records estimate" : "Recorded", "text-label-caps font-label-caps text-outline uppercase block"));
        b.append(el("p", g.value == null ? "Not on record" : valueText(f, g.value),
          "font-body-md text-body-md font-medium " + (g.value == null ? "text-outline italic" : "text-ink-primary")));
        b.append(el("p", sourceText(g.source), "font-body-sm text-body-sm text-outline"));
        const c = el("div", null, "ob-row-pill");
        let pill, cls, icon;
        if (st.by === "you" && st.value !== null) { pill = "Confirmed by you"; cls = "st-pill-ok"; icon = "check_circle"; }
        else if (st.by === "you") { pill = "Left open by you"; cls = "st-pill-open"; icon = "pending"; }
        else if (isAsked) { pill = "Needs your answer"; cls = "st-pill-ask"; icon = "help"; open++; }
        else { pill = "From records"; cls = "st-pill-rec"; icon = "description"; }
        const p = el("div", null, "st-pill inline-flex items-center gap-1.5 px-2.5 py-1 rounded border " + cls);
        const pi = el("span", icon, "material-symbols-outlined text-[15px]");
        pi.setAttribute("aria-hidden", "true");
        p.append(pi, el("span", pill, "font-label-md text-label-md"));
        c.append(p);
        row.append(a, b, c);
        host.append(row);
      }
      setText("record-count", open ? `${open} need${open === 1 ? "s" : ""} you` : "All settled");
      $("record-count").classList.toggle("is-ask", open > 0);
    }

    function guideHref() {
      return "voice.html?" + new URLSearchParams({track: "home", persona: "lead", address: house.address});
    }

    function selectHouse(address) {
      house = houses.find(h => h.address === address) || houses[0];
      ui.select.value = house.address;
      ui.input.value = display(house);
      closeList();
      showAll = false;
      document.dispatchEvent(new CustomEvent("home-context-changed", {detail: {address: house.address}}));
      restore();
      renderFacts();
      if (Object.keys(saved).length || photo) persist();
      else document.dispatchEvent(new Event("base-fleet:progress"));
      const q = guideHref();
      document.querySelectorAll('a[href^="voice.html"]').forEach(a => {
        a.href = a.dataset.voiceStep ? q + "&" + new URLSearchParams({step: a.dataset.voiceStep}) : q;
      });
      const list = ORDER.filter(f => asked().includes(f));
      const open = list.findIndex(f => !Object.hasOwn(saved, f));
      step = open < 0 ? list.length : open;
      ui.help.open = false;
      const url = new URL(location.href);
      url.searchParams.set("address", house.address);
      history.replaceState(null, "", url);
      render();
      renderTimeline();
      renderConfirm();
      say("Answers are saved on this device.");
    }

    async function load() {
      ui.retry.hidden = true;
      ui.select.disabled = true;
      try {
        fetch("../data/ptc_tdu.json").then(x => x.ok ? x.json() : null).catch(() => null)
          .then(d => { ptc = d; if (house) renderUtility(); });
        const r = await fetch("../house/cohort.json", {cache: "no-store"});
        if (!r.ok) throw new Error("cohort");
        const data = await r.json();
        houses = (Array.isArray(data) ? data : []).filter(h => h && typeof h.address === "string"
          && Array.isArray(h.guessable) && Array.isArray(h.confirm_with_member) && Array.isArray(h.events));
        if (!houses.length) throw new Error("empty");
        ui.select.replaceChildren(...houses.map(h => { const o = el("option", h.address); o.value = h.address; return o; }));
        // Open on the home that records settle best: fewest questions, most parts known.
        const openCount = h => new Set(h.confirm_with_member).size;
        const knownTrue = h => h.guessable.filter(g => g.value === true && !h.confirm_with_member.includes(g.field)).length;
        const first = houses.filter(h => h.events.length).slice()
          .sort((a, b) => openCount(a) - openCount(b) || knownTrue(b) - knownTrue(a))[0] || houses[0];
        selectHouse(new URL(location.href).searchParams.get("address") || first.address);
        ui.select.disabled = false;
        ui.input.disabled = false;
        ui.confirm.disabled = false;
      } catch {
        ui.retry.hidden = false;
        say("Try again to load house records.");
      }
    }

    ui.select.addEventListener("change", () => selectHouse(ui.select.value));

    // Address search: a combobox over the public-record homes in house/cohort.json.
    const norm = t => String(t).toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    function findMatches(q) {
      const words = norm(q).replace(/\b(austin|tx|texas)\b/g, "").split(" ").filter(Boolean);
      if (!words.length) return houses.slice(0, 6);
      return houses.filter(h => { const a = norm(h.address + " " + h.zip); return words.every(w => a.includes(w)); }).slice(0, 6);
    }
    function closeList() {
      ui.list.hidden = true;
      ui.input.setAttribute("aria-expanded", "false");
      ui.input.removeAttribute("aria-activedescendant");
      active = -1;
    }
    function openList() {
      // Suggestions only while the member types: an empty box shows none.
      matches = norm(ui.input.value) ? findMatches(ui.input.value) : [];
      ui.list.replaceChildren(...matches.map((h, i) => {
        const li = el("li", null, "jr-opt");
        li.id = "address-opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", String(i === active));
        li.append(el("strong", titleCase(h.address)), el("span", `Austin ${h.zip || ""} · ${h.events.length} permit${h.events.length === 1 ? "" : "s"}`));
        li.addEventListener("mousedown", e => { e.preventDefault(); pick(h); });
        return li;
      }));
      ui.list.hidden = !matches.length;
      ui.input.setAttribute("aria-expanded", String(!!matches.length));
      ui.hint.textContent = matches.length || !norm(ui.input.value) ? "" : "Try a street name, like Mount Vernon or Clawson.";
      if (active >= 0 && matches[active]) ui.input.setAttribute("aria-activedescendant", "address-opt-" + active);
      else ui.input.removeAttribute("aria-activedescendant");
    }
    function pick(h) {
      ui.hint.textContent = "";
      selectHouse(h.address);
      ui.input.focus({preventScroll: true});
    }
    ui.input.addEventListener("input", () => { active = -1; openList(); });
    ui.input.addEventListener("focus", () => ui.input.select());
    ui.input.addEventListener("blur", () => setTimeout(closeList, 0));
    ui.input.addEventListener("keydown", e => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (ui.list.hidden) { active = -1; openList(); }
        if (!matches.length) return;
        active = e.key === "ArrowDown" ? (active + 1) % matches.length : (active <= 0 ? matches.length - 1 : active - 1);
        openList();
        const opt = $("address-opt-" + active);
        if (opt) opt.scrollIntoView({block: "nearest"});
      } else if (e.key === "Enter") {
        e.preventDefault();
        const list = ui.list.hidden ? findMatches(ui.input.value) : matches;
        const h = list[active >= 0 ? active : 0];
        if (h) pick(h); else { openList(); }
      } else if (e.key === "Escape") {
        if (!ui.list.hidden) { e.preventDefault(); closeList(); }
      }
    });
    ui.search.addEventListener("click", () => {
      const h = findMatches(ui.input.value)[0];
      if (h) pick(h); else openList();
    });
    ui.more.addEventListener("click", () => { showAll = !showAll; renderTimeline(); });
    ui.confirm.addEventListener("click", () => {
      if (!house) return;
      try { localStorage.setItem("base-fleet:home:v1", JSON.stringify({address: house.address})); } catch { /* storage off */ }
      document.dispatchEvent(new Event("base-fleet:progress"));
      editing = false;
      renderConfirm();
      // Step 1 folds to one line, so on narrow screens the tracker and step 2 sit together at the top.
      if (!matchMedia("(min-width: 1024px)").matches) $("journey-milestones").scrollIntoView({block: "start"});
      focusQuestion();
    });
    document.addEventListener("base-fleet:progress", renderStep);
    ui.retry.addEventListener("click", load);
    ui.reset.addEventListener("click", () => {
      if (!house) return;
      saved = {};
      photo = false;
      persist();
      document.dispatchEvent(new Event("home-photos-reset"));
      step = 0;
      ui.help.open = false;
      render();
      say("Answers for this home cleared.");
    });
    // Photo milestone: counts once for this home when the member confirms the checked photo (ADR 0015).
    // A breaker size read from the photo (or typed by the member) answers the panel question.
    document.addEventListener("home-photo-confirmed", e => {
      if (!house) return;
      const amps = e.detail && e.detail.main_breaker_amps;
      if (Number.isInteger(amps) && amps > 0 && asked().includes("main_breaker_amps")) saved.main_breaker_amps = amps;
      photo = true;
      persist();
      render();
    });
    document.addEventListener("click", e => { if (tipFor && !e.target.closest(".part, .q-card")) hideTip(); });
    window.addEventListener("resize", () => { if (tipFor) showTip(tipFor); });
    $("open-electrical-photos").addEventListener("click", () => {
      document.dispatchEvent(new CustomEvent("home-photos-open", {detail: {group: "electrical"}}));
      document.getElementById("photo-checklist").scrollIntoView({block: "nearest"});
    });
    function openSearch() {
      $("find-search").hidden = false;
      $("address-change").setAttribute("aria-expanded", "true");
      ui.input.focus({preventScroll: true});
    }
    $("find-change").addEventListener("click", () => {
      editing = true;
      renderStep();
      openSearch();
    });
    $("address-change").addEventListener("click", openSearch);

    // Side drawer with two tabs: permit history and the records table.
    const drawer = $("ob-drawer"), tabs = ["permits", "records"];
    let opener = null;
    function showTab(name) {
      for (const t of tabs) {
        const on = t === name, tab = $("tab-" + t);
        tab.setAttribute("aria-selected", String(on));
        tab.tabIndex = on ? 0 : -1;
        $("panel-" + t).hidden = !on;
      }
    }
    function openDrawer(name, from) {
      opener = from || null;
      showTab(name);
      drawer.hidden = false;
      $("tab-" + name).focus();
    }
    function closeDrawer() {
      drawer.hidden = true;
      if (opener) opener.focus({preventScroll: true});
    }
    document.querySelectorAll("[data-drawer]").forEach(b => b.addEventListener("click", () => openDrawer(b.dataset.drawer, b)));
    $("ob-drawer-close").addEventListener("click", closeDrawer);
    tabs.forEach((t, i) => {
      const tab = $("tab-" + t);
      tab.addEventListener("click", () => showTab(t));
      tab.addEventListener("keydown", e => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        const next = tabs[(i + 1) % tabs.length];
        showTab(next);
        $("tab-" + next).focus();
      });
    });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !drawer.hidden) closeDrawer(); });
    ui.next.addEventListener("click", () => {
      const list = ORDER.filter(f => asked().includes(f));
      if (!Object.hasOwn(saved, list[step])) return;
      step++;
      ui.help.open = false;
      render();
      if (step >= list.length) {
        // Last answer given: step 2 is done, so bring the step 3 photo into view.
        document.dispatchEvent(new Event("base-fleet:progress"));
        const check = $("photo-check");
        check.scrollIntoView({block: "nearest"});
        const target = check.querySelector("input,button");
        if (target) target.focus({preventScroll: true});
      } else focusQuestion();
      say("Answers are saved on this device.");
    });
    ui.back.addEventListener("click", () => {
      step = Math.max(0, step - 1);
      ui.help.open = false;
      render();
      focusQuestion();
    });
    load();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
