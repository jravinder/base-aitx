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

  function fig1(F, filter) {
    const box = $("#pj-f1"), W = Math.max(280, box.clientWidth), H = W < 500 ? 220 : 212;
    const m = {l: 34, r: 52, t: 8, b: 20}, Y = F.years, n = Y.length;
    const keys = filter === "all" ? ["auto", "review", "human"] : [filter];
    const series = Object.entries(F.zips).map(([z, v]) => [z, Y.map((_, i) => keys.reduce((a, k) => a + v[k][i], 0))]);
    const max = Math.max(1, ...series.flatMap(s => s[1]));
    const step = max > 200 ? 100 : max > 40 ? 20 : max > 10 ? 5 : 1, top = Math.ceil(max / step) * step;
    const x = i => m.l + i * (W - m.l - m.r) / (n - 1), y = v => m.t + (H - m.t - m.b) * (1 - v / top);
    const tot = s => s[1].reduce((a, b) => a + b, 0);
    const hi = series.slice().sort((a, b) => tot(b) - tot(a)).slice(0, 3).map(s => s[0]);
    const hiCol = filter === "all" ? "var(--bf-brand)" : COL[filter];
    let g = "";
    for (let v = 0; v <= top; v += step) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--pj-grid)" stroke-width="1"/><text x="${m.l - 6}" y="${y(v) + 3}" text-anchor="end">${v}</text>`;
    Y.forEach((yr, i) => { if (W > 500 || i % 2 === 0 || i === n - 1) g += `<text x="${x(i)}" y="${H - 4}" text-anchor="middle">${i === n - 1 && W > 500 ? yr + "*" : "’" + yr.slice(2) + (i === n - 1 ? "*" : "")}</text>`; });
    const path = d => d.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    let lines = "", labels = "";
    series.filter(s => !hi.includes(s[0])).forEach(([z, d]) => { lines += `<path d="${path(d)}" fill="none" stroke="var(--pj-trace)" stroke-width="1"><title>${z}: ${fmt(tot([z, d]))}</title></path>`; });
    const ends = [];
    hi.forEach(z => {
      const d = series.find(s => s[0] === z)[1];
      lines += `<path d="${path(d)}" fill="none" stroke="${hiCol}" stroke-width="2"><title>${z}: ${fmt(d.reduce((a, b) => a + b, 0))}</title></path>`;
      ends.push([z, y(d[n - 1])]);
    });
    ends.sort((a, b) => a[1] - b[1]).forEach((e, i) => { if (i && e[1] - ends[i - 1][1] < 11) e[1] = ends[i - 1][1] + 11; labels += `<text x="${W - m.r + 6}" y="${e[1] + 3}" class="ink">${e[0]}</text>`; });
    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Permits per year for each of ${series.length} Austin zip codes, ${filter === "all" ? "all routes" : NAME[filter] + " route"}; highest: ${hi.join(", ")}">${g}${lines}${labels}</svg>`;
    const sum = series.reduce((a, s) => a + tot(s), 0);
    $("#pj-f1n").innerHTML = `<b>${fmt(sum)}</b> permits · ${series.length} zips · top 3 <b>${hi.join(" ")}</b> · *2026 through ${F._meta.issue_dates[1].slice(5)}`;
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
      fig1(F, filter);
    });
    fig1(F, filter);
    let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => fig1(F, filter), 120); });

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
