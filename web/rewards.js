/* Rewards page: totals, ledger, invite and policy from BaseMilestones (milestones.js). Browser-only. */
(() => {
  "use strict";
  const KEY = "base-fleet:invite:v1";
  const $ = id => document.getElementById(id);
  const read = k => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } };
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };

  // Same anonymous-code rule as milestones.js referral().
  function getCode(make) {
    let code = "";
    try { code = localStorage.getItem(KEY) || ""; } catch { /* storage off */ }
    if (!code && make) {
      code = Math.random().toString(36).slice(2, 8);
      try { localStorage.setItem(KEY, code); } catch { /* storage off */ }
    }
    return code;
  }
  function inviteUrl(code) {
    const url = new URL("onboarding.html", location.href);
    url.search = ""; url.hash = "home";
    url.searchParams.set("invite", code);
    return url.href;
  }

  let firstHome = null;
  fetch("../house/cohort.json").then(r => r.ok ? r.json() : null).then(d => {
    firstHome = Array.isArray(d) && d[0] && d[0].address || null; render();
  }).catch(() => {});

  const pill = (text, tone) => {
    const tones = {
      ok: "bg-emerald-50 text-solar-green border-emerald-200/60", dotok: "bg-solar-green",
      wait: "bg-amber-50 text-warning-amber border-amber-200", dotwait: "bg-warning-amber",
      off: "bg-slate-100 text-outline border-slate-200", dotoff: "bg-outline"};
    const s = el("span", `inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border ${tones[tone]}`);
    s.append(el("span", `w-1.5 h-1.5 rounded-full ${tones["dot" + tone]}`), document.createTextNode(text));
    return s;
  };

  // Same names as FIELDS in onboarding.js.
  const NAMES = {main_breaker_amps: "Electric panel", has_solar: "Solar panels", has_battery: "Home battery",
    has_generator: "Generator", ac_age_years: "A/C unit"};

  function rows(s) {
    const R = window.BaseMilestones.REWARD;
    const j = s.addr ? read(`base-fleet:journey:v1:${s.addr}`) : null;
    const saved = j && j.saved && typeof j.saved === "object" ? j.saved : {};
    const out = [];
    for (const [k, v] of Object.entries(saved)) {
      if (v === null || v === undefined) continue;
      out.push(["This browser", `Confirmed: ${NAMES[k] || k.replace(/_/g, " ")}`, "Your details", R.field, ["Earned", "ok"], "Your answers on Onboarding"]);
    }
    if (!out.length) out.push(["", "Confirm your home details", "Your details", 0, ["To do", "off"], "Your answers on Onboarding", ["Answer", "edit_note", "onboarding.html#home"]]);
    out.push(s.photo
      ? ["This browser", "Photo added", "Photo", R.photo, ["Earned", "ok"], "Photo checklist or voice guide"]
      : ["", "Add your panel photo", "Photo", 0, ["To do", "off"], "Photo checklist or voice guide", ["Add photo", "photo_camera", "onboarding.html#photo-checklist"]]);
    out.push(s.complete
      ? ["This browser", "Your details and photo both done", "Finishing your tasks", R.complete, ["Earned", "ok"], "Your details and photo"]
      : ["", "Finish your details and photo", "Finishing your tasks", 0, ["Next", "off"], "Your details and photo", ["Status", "visibility", "status.html"]]);
    out.push(s.joins
      ? ["", "Neighbour joined from your invite", "Referral", s.joins * R.neighbour, ["Earned", "ok"], "Invite code"]
      : ["", "Invite a neighbour", "Referral", 0, ["Open", "off"], "Invite code", ["Invite", "share", ""]]);
    return out;
  }

  function render() {
    if (!window.BaseMilestones) return;
    const s = window.BaseMilestones.state();
    const R = window.BaseMilestones.REWARD;
    const addr = s.addr || firstHome;
    $("rw-addr").textContent = addr || "Pick a home on Onboarding";
    $("rw-proposed").textContent = String(s.credit);
    $("rw-total").textContent = String(s.credit);
    const left = Math.max(0, window.BaseMilestones.maxCredit(s) - s.credit);
    $("rw-waiting").textContent = String(left);
    $("rw-waiting-note").textContent = left ? "Still open from your own steps" : "You earned all you can for your home";
    $("rw-joins").textContent = `${s.joins} joins recorded`;
    $("rw-booster").textContent = `+${R.neighbour} pts when a neighbour joins from your invite.`;
    redeem(s.credit);

    const body = $("rw-ledger");
    body.replaceChildren();
    const list = rows(s);
    for (const [date, desc, tier, kwh, [st, tone], src, act] of list) {
      const tr = el("tr", "hover:bg-surface-subtle/50 transition-colors");
      tr.append(
        el("td", "py-3 px-4 font-body-sm text-body-sm text-outline whitespace-nowrap", date),
        el("td", "py-3 px-4 text-ink-primary font-medium", desc),
        el("td", "py-3 px-4 text-outline font-body-sm text-body-sm", tier));
      const c = el("td", `py-3 px-4 font-semibold whitespace-nowrap ${kwh ? "text-primary-container" : "text-outline"}`, kwh ? `+${kwh} pts` : "0 pts");
      const p = el("td", "py-3 px-4 whitespace-nowrap"); p.append(pill(st, tone));
      tr.append(c, p, el("td", "py-3 px-4 text-outline font-body-sm text-body-sm", src));
      const a = el("td", "py-3 px-4 whitespace-nowrap text-right");
      if (act) {
        const [label, icon, href] = act;
        const b = el(href ? "a" : "button", "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-subtle hover:bg-surface-subtle/70 border border-wire-border font-label-md text-xs text-ink-primary font-medium transition-colors no-underline");
        if (href) b.href = href; else { b.type = "button"; b.dataset.invite = ""; b.dataset.reward = "neighbour"; }
        b.append(el("span", "material-symbols-outlined text-[14px] text-warning-amber", icon), el("span", "", label));
        b.firstChild.setAttribute("aria-hidden", "true");
        a.append(b);
      }
      tr.append(a);
      body.append(tr);
    }
    const earned = list.filter(r => r[3] > 0).length;
    $("rw-count").textContent = `${earned} earning, ${list.length} rows`;

    const code = getCode(false);
    $("rw-code-state").textContent = code ? "Code made" : "Ready to make";
    $("rw-link").textContent = code ? inviteUrl(code) : "Copy the link to make a code";

    const pol = $("rw-policy");
    pol.replaceChildren();
    const items = [["Each confirmed home detail", R.field], ["Photo added", R.photo], ["All onboarding tasks done", R.complete], ["Neighbour joins from your invite", R.neighbour]];
    items.forEach(([what, n], i) => {
      const row = el("div", `flex items-center justify-between gap-3 py-1 ${i < items.length - 1 ? "border-b border-surface-subtle" : ""}`);
      row.append(el("span", "text-ink-primary font-medium", what), el("span", "font-semibold text-primary-container whitespace-nowrap", `+${n} pts`));
      pol.append(row);
    });
  }

  // Redeem options: a proposal. Each shows points available against points needed; nothing is spent.
  const OPTIONS = [
    {icon: "receipt_long", title: "Bill credit", need: 100, text: "100 pts = $10 off your energy bill."},
    {icon: "engineering", title: "Priority engineering review", need: 150, text: "150 pts moves your home to an earlier review slot."},
    {icon: "volunteer_activism", title: "Gift to a neighbour", need: 1, text: "Give any amount toward a neighbour's first month."}];
  function redeem(have) {
    $("rw-avail").textContent = String(have);
    const box = $("rw-options");
    box.replaceChildren();
    for (const o of OPTIONS) {
      const card = el("div", "p-4 rounded-xl border border-wire-border bg-surface-subtle flex flex-col gap-2");
      card.dataset.redeem = String(o.need);
      const head = el("div", "flex items-center gap-2");
      const ic = el("span", "material-symbols-outlined text-primary-container text-[20px]", o.icon);
      ic.setAttribute("aria-hidden", "true");
      head.append(ic, el("h3", "font-headline-sm text-[15px] font-bold text-ink-primary", o.title));
      const ready = have >= o.need;
      const need = o.need > 1 ? `${Math.min(have, o.need)} of ${o.need} pts` : (have ? `${have} pts to give` : "Any amount");
      const meter = el("div", "h-1.5 rounded-full bg-surface-container-lowest border border-wire-border overflow-hidden");
      const fill = el("i", "block h-full bg-solar-green");
      fill.style.width = `${Math.min(100, Math.round(have / o.need * 100))}%`;
      meter.append(fill);
      const btn = el("button", "mt-auto inline-flex items-center justify-center gap-1.5 min-h-[44px] px-3 rounded-lg border border-wire-border bg-surface-container-lowest text-xs font-semibold text-outline cursor-default");
      btn.type = "button";
      btn.setAttribute("aria-disabled", "true");
      btn.textContent = "Proposal: redeeming is not live";
      card.append(head, el("p", "text-body-sm text-outline", o.text),
        el("p", `text-xs font-semibold ${ready ? "text-primary-container" : "text-outline"}`, ready ? `Ready: ${need}` : need), meter, btn);
      box.append(card);
    }
  }

  document.addEventListener("click", async e => {
    const btn = e.target.closest("[data-invite]");
    if (!btn) return;
    const url = inviteUrl(getCode(true));
    const text = `I checked my home for a Base battery. Start with your public records here: ${url}`;
    const out = document.querySelector(".rw-out");
    try { await navigator.clipboard.writeText(text); out.textContent = "Copied. The link holds an anonymous code. Points arrive when a neighbour joins."; }
    catch { out.textContent = text; }
    render();
  });
  document.addEventListener("base-fleet:progress", render);
  window.addEventListener("storage", e => { if (!e.key || e.key.startsWith("base-fleet:")) render(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render); else render();
})();
