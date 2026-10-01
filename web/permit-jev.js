// Permits page notebook figures (judgments.html). Reads data/judgments.json and data/permit_jev.json
// (built by web/data/build_permit_jev.py). Every number on screen comes from those two files.
(() => {
  "use strict";
  const $ = s => document.querySelector(s);
  const fmt = n => n.toLocaleString("en-US");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const NS = "http://www.w3.org/2000/svg";
  const COL = {auto: "var(--pj-auto)", review: "var(--pj-review)", human: "var(--pj-human)"};
  const NAME = {auto: "auto", review: "review", human: "person"};
  const CAT = {solar: "solar", battery: "battery", solar_battery: "solar+battery", generator: "generator",
    ev_charger: "EV charger", panel_upgrade: "service upgrade", other_electrical: "other"};

  // FIG. 1: one confidence axis. Top lane: rule confidence for every permit (log bars, by route).
  // Bottom lane: the 100 lowest-confidence permits (all 0.40 by rules) as the local model re-judged them.
  function fig1(D, filter) {
    const box = $("#pj-f1"), W = Math.max(280, box.clientWidth), wide = W > 560, T = D.thresholds, J = D.judge_compare;
    const p = wide ? 7 : 5, cols = wide ? 5 : 2, lo = 0.3, hi = 1.03;
    const m = {l: wide ? 104 : 4, r: 12, t: wide ? 16 : 30};
    const x = v => m.l + (v - lo) / (hi - lo) * (W - m.l - m.r);
    const tiers = D.permit_rules.map(r => ({v: r.confidence, n: r.rows, route: r.route}));
    const A = 104, yA = m.t + A, gap = wide ? 30 : 44;
    const byConf = {};
    J.rows.forEach(r => (byConf[r.confidence] = byConf[r.confidence] || []).push(r));
    Object.values(byConf).forEach(a => a.sort((q, w) => (q.value === q.rules) - (w.value === w.rules)));
    const rows = Math.max(...Object.values(byConf).map(a => Math.ceil(a.length / cols)));
    const yB = yA + gap, B = Math.max(40, rows * p + 6), H = yB + B + 22;
    const on = r => filter === "all" || filter === r;
    const max = Math.log10(Math.max(...tiers.map(t => t.n)));
    let g = "";
    [[lo, T.review, "human"], [T.review, T.auto, "review"], [T.auto, hi, "auto"]].forEach(([a, b, r]) =>
      g += `<rect x="${x(a)}" y="${m.t - 4}" width="${x(b) - x(a)}" height="${H - 22 - m.t + 4}" fill="${COL[r]}" opacity="${on(r) ? .09 : .03}"/>`);
    [[T.review, (wide ? "review ≥ " : "≥ ") + T.review.toFixed(2), "start"], [T.auto, (wide ? "auto ≥ " : "≥ ") + T.auto.toFixed(2), "start"]].forEach(([v, t]) =>
      g += `<line x1="${x(v)}" x2="${x(v)}" y1="${m.t - 4}" y2="${H - 22}" stroke="var(--bf-ink)" stroke-dasharray="3 3" stroke-width="1"/><text x="${x(v) + 4}" y="${yA + 13}" class="ink">${t}</text>`);
    for (let v = 0.3; v <= 1.0001; v += 0.1) g += `<line x1="${x(v)}" x2="${x(v)}" y1="${H - 22}" y2="${H - 18}" stroke="var(--bf-line-strong)"/><text x="${x(v)}" y="${H - 6}" text-anchor="middle">${v.toFixed(1)}</text>`;
    g += `<line x1="${m.l}" x2="${W - m.r}" y1="${yA}" y2="${yA}" stroke="var(--bf-line-strong)"/><line x1="${m.l}" x2="${W - m.r}" y1="${H - 22}" y2="${H - 22}" stroke="var(--bf-line-strong)"/>`;
    const lane = (y, a, b) => wide ? `<text x="0" y="${y}" class="ink">${a}</text><text x="0" y="${y + 13}">${b}</text>` : `<text x="${m.l}" y="${y}" class="ink">${a} <tspan style="fill:var(--bf-faint)">${b}</tspan></text>`;
    g += wide ? lane(m.t + 40, "rules", fmt(tiers.reduce((a, t) => a + t.n, 0)) + " permits") + lane(m.t + 66, "", "log scale")
      : lane(m.t - 12, "rules", fmt(tiers.reduce((a, t) => a + t.n, 0)) + " permits, log scale");
    g += wide ? lane(yB + 14, "model", J.sample + " hardest") + lane(yB + 40, "", J.model) : lane(yB - 8, "model", J.sample + " hardest, " + J.model);
    const bw = wide ? 14 : 7;
    tiers.forEach(t => {
      const h = Math.max(2, Math.log10(t.n) / max * (A - 14));
      g += `<rect x="${x(t.v) - bw / 2}" y="${yA - h}" width="${bw}" height="${h}" fill="${COL[t.route]}" opacity="${on(t.route) ? 1 : .2}"><title>rule confidence ${t.v.toFixed(2)}: ${fmt(t.n)} permits, ${NAME[t.route]}</title></rect>`;
      if (wide) g += `<text x="${x(t.v)}" y="${yA - h - 4}" text-anchor="middle" class="ink" opacity="${on(t.route) ? 1 : .3}">${fmt(t.n)}</text>`;
    });
    // bottom lane: rules put all 100 at 0.40; the model moved them
    const rc = J.rows[0].rules_confidence, cy = yB + B / 2;
    g += `<circle cx="${x(rc)}" cy="${cy}" r="${wide ? 13 : 10}" fill="none" stroke="${COL.human}" stroke-width="1.5" opacity="${on("human") ? 1 : .3}"/><text x="${x(rc)}" y="${cy + 3}" text-anchor="middle" class="ink">${J.sample}</text>`;
    g += `<line x1="${x(rc) + (wide ? 18 : 14)}" x2="${x(0.8) - 10}" y1="${cy}" y2="${cy}" stroke="var(--bf-faint)" stroke-dasharray="2 3"/>${wide ? `<text x="${(x(rc) + x(0.8)) / 2}" y="${cy - 5}" text-anchor="middle">rules ${rc.toFixed(2)} → model</text>` : ""}`;
    Object.entries(byConf).forEach(([v, a]) => a.forEach((r, i) => {
      const cx = x(+v) + (i % cols - (cols - 1) / 2) * p, y = yB + B - 4 - Math.floor(i / cols) * p, ag = r.value === r.rules;
      g += `<circle cx="${cx}" cy="${y}" r="${p * 0.38}" fill="${ag ? "var(--bf-ink)" : COL.human}" opacity="${on(r.route) ? 1 : .15}"><title>${esc(r.permit)}: rules ${esc(r.rules)} ${r.rules_confidence}, model ${esc(r.value)} ${r.confidence}${ag ? " (agrees)" : ""}</title></circle>`;
    }));
    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Rule confidence for ${fmt(tiers.reduce((a, t) => a + t.n, 0))} permits by route, and ${J.sample} hard permits re-judged by ${J.model}: ${J.agree_with_rules} agree with the rules">${g}</svg>`;
    $("#pj-f1n").innerHTML = `<span style="color:var(--pj-human)">●</span> model disagrees with rules · <span style="color:var(--bf-ink)">●</span> agrees (<b>${J.agree_with_rules}</b>) · rules: <b>${fmt(D.counts.permit.auto)}</b> at ≥ ${T.auto.toFixed(2)}; model: <b>${J.routes.auto}</b> of ${J.sample} would skip a person`;
  }

  function render(D, F) {
    const c = D.counts.permit, N = c.auto + c.review + c.human, J = D.judge_compare, M = F.model;
    $("#pj-sub").textContent = `Austin energy permits ${F._meta.issue_dates[0].slice(0, 4)}–${F._meta.issue_dates[1].slice(0, 4)}. Seven keyword rules set category + confidence; confidence sets the route. ${J.model} (local) re-judged the ${J.sample} lowest-confidence permits; ${fmt(F.check.n)} were checked by hand.`;
    $("#pj-strip").innerHTML = [[fmt(N), "permits judged"], [fmt(c.auto), "auto ≥ " + D.thresholds.auto.toFixed(2)], [fmt(c.review), "review"],
      [fmt(c.human), "to a person"], [`${F.check.correct}/${F.check.n}`, "hand-check right"], [J.seconds_median + " s", "median, local model"]]
      .map(([b, s]) => `<div><b>${b}</b>${s}</div>`).join("");
    $("#pj-big").innerHTML = `<b>${J.agree_with_rules}<small>/${J.sample}</small></b><span>hard permits where the local model agreed with the rules, though ${M.confident} of ${J.sample} said ≥ 0.90</span>`;

    // FIG. 1
    let filter = "all";
    const chips = [["all", "All", N], ["auto", "Auto", c.auto], ["review", "Review", c.review], ["human", "Person", c.human]];
    $("#pj-chips").innerHTML = chips.map(([k, t, v]) => `<button type="button" data-k="${k}" aria-pressed="${k === "all"}"><i style="background:${k === "all" ? "var(--bf-brand)" : COL[k]}"></i>${t} ${fmt(v)}</button>`).join("");
    $("#pj-chips").addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b) return;
      filter = b.dataset.k;
      document.querySelectorAll("#pj-chips button").forEach(x => x.setAttribute("aria-pressed", x === b));
      fig1(D, filter);
    });
    fig1(D, filter);
    let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => fig1(D, filter), 120); });

    // FIG. 2: observed accuracy (hand check, Wilson 95% interval) vs predicted (mean rule confidence)
    const lo = 0.3, sc = v => ((v - lo) / (1 - lo) * 100).toFixed(1) + "%";
    $("#pj-f2").innerHTML = `<div class="pj-row" style="color:var(--bf-faint)"><span></span><span style="display:flex;justify-content:space-between"><span>0.3</span><span>0.65</span><span>1.0</span></span><span>n</span></div>`
      + F.categories.map(k => `<div class="pj-row" title="${esc(CAT[k.cat])}: ${k.correct} of ${k.checked} right by hand; rules predicted ${k.predicted.toFixed(2)}"><span>${CAT[k.cat]}</span><span class="pj-bar" style="background:transparent;border-bottom:1px solid var(--pj-grid);height:14px">`
        + `<i style="left:${sc(k.ci[0])};width:calc(${sc(k.ci[1])} - ${sc(k.ci[0])});top:6px;bottom:auto;height:2px;background:var(--bf-muted)"></i>`
        + `<i style="left:calc(${sc(k.correct / k.checked)} - 4px);top:3px;bottom:auto;width:8px;height:8px;border-radius:50%;background:${k.human ? COL.human : COL.auto}"></i>`
        + `<i style="left:calc(${sc(k.predicted)} - 4px);top:3px;bottom:auto;width:7px;height:7px;transform:rotate(45deg);border:1.5px solid var(--bf-ink)"></i>`
        + `</span><span>${k.correct}/${k.checked}</span></div>`).join("")
      + `<div class="pj-key"><span><i class="dot" style="background:var(--pj-auto)"></i>observed, hand check</span><span><i style="height:2px;background:var(--bf-muted)"></i>95% interval</span><span><i class="dia"></i>predicted (rule conf.)</span></div>`;

    // FIG. 3: one permit, end to end
    const T = M.traced[0];
    $("#pj-f3").innerHTML = `<div class="pj-id">${esc(T.permit)}</div>
      <ol class="pj-tl">
        <li><span>applied</span><span>${T.applied_date}</span></li>
        <li><span>issued</span><span>${T.issue_date} · zip ${T.zip}</span></li>
        <li style="--c:var(--pj-human)"><span>rules</span><span><b>${CAT[T.rules]}</b> ${T.rules_confidence.toFixed(2)} → person</span></li>
        <li style="--c:var(--pj-auto)"><span>model</span><span><b>upgrade</b> ${T.confidence.toFixed(2)} → auto</span></li>
        <li style="--c:var(--pj-human)"><span>by hand</span><span><b>${CAT[T.true_category]}</b> · model wrong</span></li>
      </ol>
      <table class="pj-kv"><tr><td>work_class</td><td>${esc(T.work_class)}</td></tr><tr><td>status</td><td>${esc(T.status)}</td></tr>
      <tr><td>route kept</td><td>person (rules)</td></tr></table>
      <div class="pj-note">${M.traced.length} of ${J.sample} model-checked permits were hand-checked too; both look like this.</div>`;

    // FIG. 4: calibration by rule-confidence tier
    $("#pj-f4").innerHTML = F.tiers.map(t => `<div class="pj-row" style="grid-template-columns:92px minmax(0,1fr) 40px" title="${t.permits} permits at ${t.conf}; ${t.correct} of ${t.checked} hand-checked right"><span>${t.conf.toFixed(2)} ${NAME[t.route]}</span><span class="pj-bar"><i style="width:${(100 * t.correct / t.checked).toFixed(1)}%;background:${COL[t.route]}"></i><u style="left:calc(${(t.conf * 100).toFixed(1)}% - 1px)"></u></span><span>${t.correct}/${t.checked}</span></div>`).join("")
      + `<div class="pj-key"><span><i style="background:var(--pj-auto)"></i>share right, by hand</span><span><i style="width:2px;background:var(--bf-ink)"></i>stated confidence</span></div>
      <div class="pj-note">Review tiers hold <b>${F.tiers.filter(t => t.route === "review").reduce((a, t) => a + t.checked, 0)}</b> checked permits; read as direction only.</div>`;

    // FIG. 5: confidently wrong
    const auto = F.tiers.filter(t => t.route === "auto"), ac = auto.reduce((a, t) => a + t.checked, 0), ar = auto.reduce((a, t) => a + t.correct, 0);
    $("#pj-f5").innerHTML = `<div class="pj-huge">${M.confident_disagree}%</div>
      <div class="pj-note">of ${J.sample} hard permits: ${J.model} said ≥ 0.90 <b>and</b> disagreed with the rules (${M.pairs["other_electrical>panel_upgrade"]} called a service upgrade).</div>
      <div class="pj-vs"><div><b>${M.traced.filter(t => t.value !== t.true_category).length}/${M.traced.length}</b><span>model wrong where a hand label exists</span></div>
      <div><b>${ac - ar}/${ac}</b><span>rules wrong at auto (≥ ${D.thresholds.auto.toFixed(2)}), hand check</span></div></div>`;

    // FIG. 6: routing by category
    $("#pj-f6").innerHTML = F.categories.slice().sort((a, b) => b.n - a.n).map(k => `<div class="pj-row" style="grid-template-columns:112px minmax(0,1fr) 46px" title="${esc(CAT[k.cat])}: ${fmt(k.auto)} auto, ${fmt(k.review)} review, ${fmt(k.human)} person"><span>${CAT[k.cat]}</span><span class="pj-stack">${["auto", "review", "human"].map(r => k[r] ? `<i style="width:${(100 * k[r] / k.n).toFixed(2)}%;background:${COL[r]}"></i>` : "").join("")}</span><span>${fmt(k.n)}</span></div>`).join("")
      + `<div class="pj-key">${["auto", "review", "human"].map(r => `<span><i style="background:${COL[r]}"></i>${NAME[r]}</span>`).join("")}</div>`;
  }

  Promise.all(["data/judgments.json", "data/permit_jev.json"].map(u => fetch(u).then(r => { if (!r.ok) throw new Error(u); return r.json(); })))
    .then(([D, F]) => render(D, F))
    .catch(() => { const n = $("#notice"); if (n) n.style.display = "block"; });
})();
