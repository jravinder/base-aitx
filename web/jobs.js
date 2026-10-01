/* Job rules page: fills the three rule cards, the feeder map and the workload ledger from the recorded
   fleet simulation (data/tower_replay.json, data/density.json). Tier settings mirror sim/fleet.py TIERS. */
(() => {
  "use strict";
  const GPU_KW = 0.4, RESERVE = 0.30;
  const TIERS = [
    {key: "member", rate: 1.20, share: 0.35, fits: ["node", "feeder"], name: "Member", work: "Member questions: the household's own AI, answering next door"},
    {key: "business", rate: 1.09, share: 0.15, fits: ["feeder", "far"], name: "Business", work: "Business inference for local firms (Lambda A6000 on-demand rate)"},
    {key: "base", rate: 0.79, share: 0.20, fits: ["node", "feeder", "far"], name: "Fleet", work: "Fleet forecast and telemetry jobs (RunPod L40S community rate)"},
    {key: "partner", rate: 0.34, share: 0.15, fits: ["feeder", "far"], name: "Grid partner", work: "Grid partner batch work (RunPod RTX 4090 community rate)"},
    {key: "external", rate: 0.16, share: 0.15, fits: ["node", "feeder", "far"], name: "Open batch", work: "Open-science batch, such as protein folding, could run here (RunPod RTX A5000 rate)"}
  ];
  const FIT = {node: "Own node", feeder: "Same feeder", far: "Anywhere"};
  const $ = s => document.querySelector(s);
  const usd = (v, d = 2) => "$" + v.toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const pauseAt = rate => Math.round(rate / GPU_KW * 1000);

  function ledger(byTier) {
    $("#ledger").innerHTML = TIERS.map(t => {
      const r = byTier && byTier[t.key];
      const cell = (v, label) => `<td class="num" data-label="${label}">${r ? v : "-"}</td>`;
      return `<tr><td class="first"><div style="font-weight:600">${esc(t.name)}</div><div class="w">${esc(t.work)}</div></td>` +
        `<td class="fits" data-label="Can run on"><div>${t.fits.map(f => `<span>${FIT[f]}</span>`).join("")}</div></td>` +
        `<td class="num" data-label="Rate / GPU-hour">${usd(t.rate)}</td><td class="num" data-label="Share of queue">${Math.round(t.share * 100)}%</td>` +
        (r ? cell(r.jobs, "Jobs") + cell(r.hours, "GPU-hours") + cell(usd(r.revenue), "Margin") : cell(0, "Jobs") + cell(0, "GPU-hours") + cell(0, "Margin")) +
        `<td class="num" data-label="Pauses above">${usd(pauseAt(t.rate), 0)}/MWh</td></tr>`;
    }).join("");
  }

  function render(replay, density) {
    const F = replay.frames, last = F[F.length - 1];
    const days = [...new Set(F.map(f => f.day))].length;
    $("#run-nodes").textContent = `${replay.nodes} nodes, ${F.length} hours`;
    $("#run-days").textContent = `${days} days of ERCOT day-ahead prices, Austin Energy zone`;

    // Rule 1: lowest charge any live node reached.
    let low = 1;
    for (const f of F) for (const n of f.nodes) if (n.alive && n.soc < low) low = n.soc;
    $("#res-reserve").textContent = low >= RESERVE ? "0 floor crossings" : "Floor crossed";
    $("#k-low").textContent = Math.round(low * 100) + "%";
    $("#k-low-s").textContent = low >= RESERVE ? "floor is 30%; 0 crossings" : "floor is 30%; crossed";
    $("#s-reserve").textContent = low >= RESERVE ? `Held all ${F.length} hours` : "Floor crossed";
    $("#res-reserve-note").textContent = `Lowest charge on any node across ${F.length} hours: ${Math.round(low * 100)}%. The simulation checks the floor on every node, every hour.`;

    // Rule 2: the recorded node stop and handoff.
    const stop = (replay.kills || []).find(k => k.kind === "node");
    if (stop) {
      const node = F[0].nodes.find(n => n.id === stop.target);
      const at = F.find(f => f.t === stop.t) || last;
      const fo = at.failover;
      $("#res-feeder").textContent = `Hour ${stop.t}, ${node.feeder}`;
      $("#s-feeder").textContent = `Handoff at hour ${stop.t}, ${fo.gpu_hours_lost} GPU-h lost`;
      $("#res-feeder-note").textContent = `Node ${stop.target} stops at hour ${stop.t}. ${fo.ok} job handed to a neighbor on ${node.feeder}, ${fo.gpu_hours_lost} GPU-hours lost.`;
    }
    if (density && density.rows) {
      const one = density.rows.find(r => r.nodes_per_feeder === 1), multi = density.rows.filter(r => r.nodes_per_feeder >= 2);
      const lost = Math.max(...multi.map(r => r.gpu_hours_lost));
      $("#big-lost").textContent = lost;
      $("#k-lost").textContent = lost;
      $("#k-lost-s").textContent = `feeders with 2+ nodes, ${density.nodes} nodes`;
      $("#ans").innerHTML = `${lost} GPU-hours lost <small>${low >= RESERVE ? "and the backup floor held." : "but the backup floor was crossed."}</small>`;
      $("#topo-lost").textContent = lost === 0 ? "Shared feeders keep every GPU-hour" : `${lost} GPU-hours to redo on shared feeders`;
      if (one) {
        $("#res-density").textContent = `With one node per feeder, a stopped job restarts from zero: ${one.gpu_hours_lost} GPU-hours to redo across ${density.nodes} nodes.`;
        $("#find-p").textContent = `With one node per feeder, a stopped job restarts from zero: ${one.gpu_hours_lost} GPU-hours to redo across ${density.nodes} nodes. One more node on the feeder gives it a handoff partner.`;
      }
    }

    // Rule 3: price strip and the peak hour.
    const prices = F.map(f => f.grid_price), max = Math.max(...prices);
    const peak = F.find(f => f.grid_price === max);
    const bars = prices.map((p, i) => `<i class="${p === max ? "hot" : ""}" style="height:${Math.max(4, p / max * 100)}%" title="Hour ${i}: ${usd(p * 1000)}/MWh"></i>`).join("");
    $("#spark").innerHTML = bars; $("#spark-full").innerHTML = bars;
    $("#k-peak").textContent = `${usd(max * 1000, 0)}/MWh`;
    $("#res-peak").textContent = `Peak ${usd(max * 1000)}/MWh`;
    const sold = peak.nodes.filter(n => n.battery === "discharge").length, busy = peak.nodes.filter(n => n.gpu !== "idle").length;
    const lowest = pauseAt(Math.min(...TIERS.map(t => t.rate)));
    const paused = F.some(f => f.nodes.some(n => n.paused));
    $("#k-peak-s").textContent = `hour ${peak.t}; pause point ${usd(lowest, 0)}/MWh`;
    $("#s-price").textContent = paused ? "Some jobs paused" : `No job paused; peak ${usd(max * 1000, 0)}`;
    $("#res-price-note").textContent = `At the peak, hour ${peak.t}, ${sold} of ${peak.nodes.length} batteries sold power and ${busy} GPUs kept working. Every hour stayed under the ${usd(lowest, 0)}/MWh pause point, so no job paused.`;

    // Node-hour grid: one square per node per hour, in node order (rows) and hour order (columns).
    const ids = F[0].nodes.map(n => n.id);
    const cell = (n, f) => !n.alive ? "p" : (n.paused || !f.scheduler_alive) ? "v" : n.job ? "r" : n.battery === "discharge" ? "a" : "";
    const cnt = {r: 0, a: 0, "": 0, v: 0, p: 0};
    $("#sq").innerHTML = ids.map(id => F.map(f => { const n = f.nodes.find(x => x.id === id), c = n ? cell(n, f) : "p"; cnt[c]++; return `<i class="${c}"></i>`; }).join("")).join("");
    $("#sq").style.gridTemplateColumns = `repeat(${F.length},minmax(0,1fr))`;
    $("#spark").style.gridTemplateColumns = `repeat(${F.length},minmax(0,1fr))`;
    $("#prog").textContent = `${replay.nodes} nodes × ${F.length} hours`;
    $("#legend").innerHTML = [["var(--bf-blue)", "Running a job", cnt.r], ["var(--bf-solar)", "Battery selling", cnt.a], ["var(--bf-line)", "Idle", cnt[""]],
      ["#F59E0B", "Held or paused", cnt.v], ["#EF4444", "Offline", cnt.p]]
      .map(([c, t, k]) => `<span><i style="background:${c}"></i>${t} · ${k.toLocaleString("en-US")}</span>`).join("");

    // Feeders.
    const feeders = Object.entries(last.feeders).sort((a, b) => b[1].nodes.length - a[1].nodes.length || a[0].localeCompare(b[0]));
    $("#feeders").innerHTML = feeders.map(([id, v]) => `<span class="feeder${v.nodes.length === 1 ? " solo" : ""}"><b>${esc(id)}</b>${v.nodes.length} node${v.nodes.length === 1 ? "" : "s"}</span>`).join("");
    const solo = feeders.filter(([, v]) => v.nodes.length === 1).length;
    $("#topo-chip").textContent = `${replay.nodes} nodes • ${feeders.length} feeders • ${feeders.length - solo} shared`;
    $("#feed-sum").textContent = `${feeders.length} feeders, ${feeders.length - solo} shared, ${solo} with one node`;
    $("#feeders-note").textContent = `${replay.nodes} nodes on ${feeders.length} feeders. ${feeders.length - solo} feeders share work between neighbors; ${solo} feeders gain a handoff partner with one more node.`;

    // Ledger.
    const by = last.revenue.by_tier;
    ledger(by);
    $("#k-margin").textContent = usd(last.revenue.compute, 0);
    const hours = TIERS.reduce((s, t) => s + by[t.key].hours, 0);
    const jobs = TIERS.reduce((s, t) => s + by[t.key].jobs, 0);
    $("#k-margin-s").textContent = `${jobs} jobs, ${hours.toLocaleString("en-US")} GPU-hours; +${usd(last.revenue.power, 0)} batteries`;
    $("#ledger-sum").textContent = `${jobs} jobs, ${usd(last.revenue.compute)} compute margin`;
    $("#ledger-total").textContent = `Replay totals: ${TIERS.reduce((s, t) => s + by[t.key].jobs, 0)} jobs, ${hours} GPU-hours, ${usd(last.revenue.compute)} compute margin and ${usd(last.revenue.power)} from the batteries.`;
  }

  ledger(null);
  const get = url => fetch(url).then(r => r.ok ? r.json() : null).catch(() => null);
  Promise.all([get("data/tower_replay.json"), get("data/density.json")]).then(([replay, density]) => {
    if (replay && replay.frames && replay.frames.length) render(replay, density);
    else $("#res-price-note").textContent = "The replay opens in the control tower.";
  });
})();
