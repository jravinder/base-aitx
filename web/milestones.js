/* Base Fleet milestone tracker and rewards. One component for every customer page.
   Put <div data-milestones></div> (or data-milestones="compact") where the page shows progress.
   State is read from browser-saved keys only; nothing leaves the browser.
     base-fleet:journey:v1:<address>  {version, saved:{field:value|null}, open, photo}   (onboarding.js)
     base-fleet:voice:v1              {<address>: {done, photo}}                          (voice.js)
     base-fleet:home:v1               {address}  last home picked on the journey page
   Rewards are points (ADR 0015 table values, superseding its kWh unit). */
(() => {
  "use strict";
  const MILESTONES = ["Public records", "Your details", "Photo", "Engineering review", "Installation"];
  const REWARD = {field: 10, photo: 20, complete: 30, neighbour: 50};
  const LABEL = "Base Ready points";
  const UNIT = "pts";
  const ICON = '<svg viewBox="0 -960 960 960" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="m233-80 65-281L80-550l288-25 112-265 112 265 288 25-218 189 65 281-247-149L233-80Z"/></svg>'; // Material Symbols "star"

  const read = k => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } };

  function address() {
    const fromUrl = new URL(location.href).searchParams.get("address");
    if (fromUrl) return fromUrl;
    if (window.BaseShownAddress) return window.BaseShownAddress; // the house onboarding is showing, before it is confirmed
    const home = read("base-fleet:home:v1");
    return home && home.address ? home.address : null;
  }

  function state() {
    const addr = address();
    const j = addr ? read(`base-fleet:journey:v1:${addr}`) : null;
    const v = addr ? (read("base-fleet:voice:v1") || {})[addr] : null;
    const saved = j && j.saved && typeof j.saved === "object" ? j.saved : {};
    const answered = Object.keys(saved).length;
    const confirmed = Object.values(saved).filter(x => x !== null && x !== undefined).length;
    const open = j && Number.isInteger(j.open) ? j.open : null;
    const voiceDone = !!(v && v.done);
    const detailsDone = voiceDone || (open !== null && open > 0 && answered >= open);
    const photo = !!((j && j.photo) || (v && v.photo));
    const complete = detailsDone && photo;
    const joins = 0; // No neighbour join is recorded in this browser.
    const credit = confirmed * REWARD.field + (photo ? REWARD.photo : 0) + (complete ? REWARD.complete : 0) + joins * REWARD.neighbour;
    const status = [
      "done",
      detailsDone ? "done" : answered ? "now" : "next",
      photo ? "done" : detailsDone ? "now" : "next",
      complete ? "now" : "base",
      "base"];
    return {addr, confirmed, answered, open, photo, detailsDone, complete, joins, credit, status};
  }

  const STATUS_TEXT = {done: "Done", now: "In progress", next: "To do", base: "Base does this"};

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  // Most a member can earn for their own home: every answer, the photo, and finishing both.
  function maxCredit(s) {
    const fields = Number.isInteger(s.open) && s.open > 0 ? s.open : 5;
    return fields * REWARD.field + REWARD.photo + REWARD.complete;
  }

  // What each step pays. Steps 4 and 5 are Base's work, so they pay nothing to the member.
  function stepReward(i) {
    return [
      "Filled from records",
      `+${REWARD.field} ${UNIT} per answer`,
      `+${REWARD.photo} ${UNIT}`,
      "Base does this",
      "Base does this"][i];
  }

  // The single next thing the member can do, and what it pays.
  function nextReward(s) {
    const bonus = ` +${REWARD.complete} ${UNIT} for finishing`;
    if (!s.detailsDone) {
      const left = Number.isInteger(s.open) && s.open > 0 ? Math.max(1, s.open - s.answered) : null;
      if (!left) return `Next: answer your home questions (+${REWARD.field} ${UNIT} each)`;
      return `Next: answer ${left} more question${left === 1 ? "" : "s"} (+${left * REWARD.field} ${UNIT}${s.photo ? "," + bonus : ""})`;
    }
    if (!s.photo) return `Next: one photo (+${REWARD.photo} ${UNIT},${bonus})`;
    return `Next: invite a neighbour (+${REWARD.neighbour} ${UNIT})`;
  }

  function render(host) {
    const s = state();
    const variant = host.dataset.milestones || "full";
    const compact = variant === "compact";
    host.classList.add("bf-ms");
    host.classList.toggle("bf-ms-compact", compact);
    host.classList.toggle("bf-ms-ribbon", variant === "ribbon");
    host.setAttribute("role", "region");
    host.setAttribute("aria-label", "Your milestones and credits");
    host.replaceChildren();

    const max = maxCredit(s);
    const doneCount = s.status.filter(x => x === "done").length;
    const head = el("div", "bf-ms-head");
    const icon = el("span", "bf-ms-icon");
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 15c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1 0-2.9a2.1 2.1 0 0 0-3 0z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.9A12.9 12.9 0 0 1 22 2c0 2.7-.8 7.5-6 11a22.4 22.4 0 0 1-4 2z"/><path d="M9 12H4s.6-3 2-4c1.6-1.1 5 0 5 0M12 15v5s3-.6 4-2c1.1-1.6 0-5 0-5"/></svg>';
    head.append(icon);
    const title = el("div", "bf-ms-title");
    const kick = el("p", "bf-ms-kicker", "Onboarding tracker");
    kick.append(el("span", "bf-ms-live", doneCount >= 3 ? "Base has it" : "Active"));
    title.append(kick);
    title.append(el("p", "bf-ms-step", `Step ${Math.min(doneCount + 1, 5)} of 5: ${MILESTONES[Math.min(doneCount, 4)]}`));
    head.append(title);
    const total = el("p", "bf-ms-total");
    const num = el("b", "bf-ms-credit", `${s.credit} ${UNIT}`);
    num.dataset.credit = String(s.credit);
    if (Date.now() < pulseUntil) num.classList.add("bf-ms-pulse");
    total.append(num, el("span", "", ` of ${max} (${LABEL})`));
    const box = el("div", "bf-ms-box");
    box.append(total, el("span", "bf-ms-pct", `${Math.min(100, Math.round(s.credit / max * 100))}%`));
    head.append(box);
    host.append(head);

    const bar = el("div", "bf-ms-bar");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-label", "Points earned");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", String(max));
    bar.setAttribute("aria-valuenow", String(s.credit));
    const fill = el("i");
    fill.style.width = `${Math.min(100, Math.round(s.credit / max * 100))}%`;
    // The amber segment is what the current step can still add.
    const nowIdx = s.status.indexOf("now");
    const nowKwh = nowIdx === 1 ? Math.max(0, max - REWARD.photo - REWARD.complete - s.confirmed * REWARD.field)
      : nowIdx === 2 ? REWARD.photo : nowIdx === 3 ? 0 : 0;
    const pend = el("i", "bf-ms-pend");
    pend.style.width = `${Math.min(100 - Math.min(100, Math.round(s.credit / max * 100)), Math.round(nowKwh / max * 100))}%`;
    bar.append(fill, pend);
    host.append(bar);
    host.append(el("p", "bf-ms-next", nextReward(s)));
    host.append(el("p", "bf-ms-hint bf-ms-tip",
      `${REWARD.complete} ${UNIT} more when your answers and photo are both done. ${REWARD.neighbour} ${UNIT} when a neighbour joins from your invite. Base confirms points at installation.`));

    const ol = el("ol", "bf-ms-steps");
    MILESTONES.forEach((name, i) => {
      const li = el("li", `bf-ms-${s.status[i]}`);
      li.dataset.milestone = String(i + 1);
      const top = el("div", "bf-ms-top");
      top.append(el("span", "bf-ms-num", `Step ${i + 1}`));
      const dot = el("span", "bf-ms-dot", s.status[i] === "done" ? "✓" : String(i + 1));
      dot.setAttribute("aria-hidden", "true");
      top.append(dot);
      const txt = el("span", "bf-ms-name");
      txt.append(el("b", "bf-ms-label", name), el("small", "", STATUS_TEXT[s.status[i]]));
      const foot = el("span", "bf-ms-foot", stepReward(i));
      li.append(top, txt, foot);
      ol.append(li);
    });
    host.append(ol);

    if (compact) {
      const more = el("details", "bf-ms-more");
      more.append(el("summary", "", "How credits work"));
      more.append(table(s));
      host.append(more);
    } else if (variant !== "ribbon") {
      host.append(table(s));
      host.append(referral());
    }
  }

  function table(s) {
    const ul = el("ul", "bf-ms-rewards");
    const rows = [
      [`${REWARD.field} ${UNIT} per confirmed field`, s.confirmed ? `${s.confirmed} confirmed, ${s.confirmed * REWARD.field} ${UNIT}` : "Ready to earn", s.confirmed > 0],
      [`${REWARD.photo} ${UNIT} for the photo`, s.photo ? `${REWARD.photo} ${UNIT}` : "Ready to earn", s.photo],
      [`${REWARD.complete} ${UNIT} when all tasks are done`, s.complete ? `${REWARD.complete} ${UNIT}` : "Ready to earn", s.complete],
      [`${REWARD.neighbour} ${UNIT} when a neighbour joins from your invite`, s.joins ? `${s.joins * REWARD.neighbour} ${UNIT}` : "Ready to earn", s.joins > 0]];
    for (const [what, got, ok] of rows) {
      const li = el("li", ok ? "bf-ms-got" : "");
      li.append(el("span", "", what), el("b", "", got));
      ul.append(li);
    }
    const note = el("li", "bf-ms-note", "Saved on this device.");
    ul.append(note);
    return ul;
  }

  function referral() {
    const box = el("div", "bf-ms-ref");
    box.append(el("p", "", `Tell a neighbour. You get ${REWARD.neighbour} ${UNIT} when they join from your invite.`));
    const btn = el("button", "bf-ms-btn", "Copy invite message");
    btn.type = "button";
    const out = el("span", "bf-ms-ref-out");
    out.setAttribute("role", "status");
    btn.addEventListener("click", async () => {
      let code = "";
      try { code = localStorage.getItem("base-fleet:invite:v1") || ""; } catch { /* storage off */ }
      if (!code) {
        code = Math.random().toString(36).slice(2, 8);
        try { localStorage.setItem("base-fleet:invite:v1", code); } catch { /* storage off */ }
      }
      const url = new URL("onboarding.html", location.href);
      url.search = "";
      url.hash = "home";
      url.searchParams.set("invite", code);
      const text = `I checked my home for a Base battery. Start with your public records here: ${url.href}`;
      try { await navigator.clipboard.writeText(text); out.textContent = "Copied. The link holds an anonymous code only."; }
      catch { out.textContent = text; }
    });
    box.append(btn, out);
    return box;
  }

  // Every call to action that earns credit carries data-reward="field|photo|complete|neighbour".
  // The chip text comes from REWARD, so no page types its own reward number.
  const CHIP = {field: `+${REWARD.field} ${UNIT}`, photo: `+${REWARD.photo} ${UNIT}`,
    complete: `+${REWARD.complete} ${UNIT}`, neighbour: `+${REWARD.neighbour} ${UNIT}`};
  function chips(root) {
    (root || document).querySelectorAll("[data-reward]").forEach(node => {
      const text = CHIP[node.dataset.reward];
      if (!text || node.querySelector(":scope > .bf-rw")) return;
      const chip = el("span", "bf-rw", text);
      chip.title = LABEL;
      chip.setAttribute("aria-label", `earns ${text.slice(1).replace(UNIT, "points")}`);
      node.append(chip);
    });
  }

  // Earn moment: a toast and a pulse when points go up. The last seen total per address lives in
  // sessionStorage, so a page load only records it and never celebrates old points.
  const SEEN_KEY = "base-fleet:points-seen:v1";
  const seenAll = () => { try { return JSON.parse(sessionStorage.getItem(SEEN_KEY) || "{}") || {}; } catch { return {}; } };
  let seenMem = seenAll();
  function remember(addr, credit) {
    seenMem[addr] = credit;
    try { sessionStorage.setItem(SEEN_KEY, JSON.stringify(seenMem)); } catch { /* per-page only */ }
  }
  let toastTimer = 0, pulseUntil = 0;
  function toast(gain, total) {
    let t = document.getElementById("bf-ms-toast");
    if (!t) {
      t = el("div", "bf-ms-toast");
      t.id = "bf-ms-toast";
      t.setAttribute("role", "status");
      t.setAttribute("aria-live", "polite");
      document.body.append(t);
    }
    t.innerHTML = ICON;
    t.append(el("span", "", `+${gain} ${UNIT} · ${total} ${UNIT} earned`));
    t.classList.add("bf-ms-toast-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("bf-ms-toast-on"), 3000);
  }
  function celebrate(s, initial) {
    if (!s.addr) return;
    const prev = seenMem[s.addr];
    remember(s.addr, s.credit);
    if (initial || typeof prev !== "number" || s.credit <= prev) return;
    toast(s.credit - prev, s.credit);
    pulseUntil = Date.now() + 1200;
    document.querySelectorAll(".bf-ms-credit").forEach(n => n.classList.add("bf-ms-pulse"));
  }

  let booted = false;
  function renderAll() {
    document.querySelectorAll("[data-milestones]").forEach(render);
    chips();
    const s = state();
    celebrate(s, !booted);
    booted = true;
    document.dispatchEvent(new CustomEvent("base-fleet:points", {detail: {credit: s.credit, addr: s.addr}}));
  }
  window.BaseMilestones = {state, render: renderAll, chips, maxCredit, nextReward, MILESTONES, REWARD, LABEL, UNIT, ICON};
  // Pages rewrite button text (journey "Continue" / "Review answers"), which drops the chip. Put it back.
  const touches = m => (m.target.nodeType === 1 && m.target.closest("[data-reward]"))
    || [...m.addedNodes].some(n => n.nodeType === 1 && (n.matches("[data-reward]") || n.querySelector("[data-reward]")));
  new MutationObserver(list => { if (list.some(touches)) chips(); })
    .observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener("base-fleet:progress", renderAll);
  window.addEventListener("storage", e => { if (!e.key || e.key.startsWith("base-fleet:")) renderAll(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", renderAll);
  else renderAll();
})();
