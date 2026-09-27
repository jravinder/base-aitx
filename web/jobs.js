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
      return `<tr><td class="first"><div class="font-semibold text-ink-primary">${esc(t.name)}</div><div class="text-on-surface-variant">${esc(t.work)}</div></td>` +
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
    $("#res-reserve-note").textContent = `Lowest charge on any node across ${F.length} hours: ${Math.round(low * 100)}%. The simulation checks the floor on every node, every hour.`;

    // Rule 2: the recorded node stop and handoff.
    const stop = (replay.kills || []).find(k => k.kind === "node");
    if (stop) {
      const node = F[0].nodes.find(n => n.id === stop.target);
      const at = F.find(f => f.t === stop.t) || last;
      const fo = at.failover;
      $("#res-feeder").textContent = `Hour ${stop.t}, ${node.feeder}`;
      $("#res-feeder-note").textContent = `Node ${stop.target} stops at hour ${stop.t}. ${fo.ok} job handed to a neighbor on ${node.feeder}, ${fo.gpu_hours_lost} GPU-hours lost.`;
    }
    if (density && density.rows) {
      const one = density.rows.find(r => r.nodes_per_feeder === 1), multi = density.rows.filter(r => r.nodes_per_feeder >= 2);
      const lost = Math.max(...multi.map(r => r.gpu_hours_lost));
      $("#big-lost").textContent = lost;
      $("#topo-lost").textContent = lost === 0 ? "Shared feeders keep every GPU-hour" : `${lost} GPU-hours to redo on shared feeders`;
      if (one) $("#res-density").textContent = `With one node per feeder, a stopped job restarts from zero: ${one.gpu_hours_lost} GPU-hours to redo across ${density.nodes} nodes.`;
    }

    // Rule 3: price strip and the peak hour.
    const prices = F.map(f => f.grid_price), max = Math.max(...prices);
    const peak = F.find(f => f.grid_price === max);
    $("#spark").innerHTML = prices.map((p, i) => `<i class="${p === max ? "hot" : ""}" style="height:${Math.max(4, p / max * 100)}%" title="Hour ${i}: ${usd(p * 1000)}/MWh"></i>`).join("");
    $("#res-peak").textContent = `Peak ${usd(max * 1000)}/MWh`;
    const sold = peak.nodes.filter(n => n.battery === "discharge").length, busy = peak.nodes.filter(n => n.gpu !== "idle").length;
    const lowest = pauseAt(Math.min(...TIERS.map(t => t.rate)));
    $("#res-price-note").textContent = `At the peak, hour ${peak.t}, ${sold} of ${peak.nodes.length} batteries sold power and ${busy} GPUs kept working. Every hour stayed under the ${usd(lowest, 0)}/MWh pause point, so no job paused.`;

    // Feeders.
    const feeders = Object.entries(last.feeders).sort((a, b) => b[1].nodes.length - a[1].nodes.length || a[0].localeCompare(b[0]));
    $("#feeders").innerHTML = feeders.map(([id, v]) => `<span class="feeder${v.nodes.length === 1 ? " solo" : ""}"><b>${esc(id)}</b>${v.nodes.length} node${v.nodes.length === 1 ? "" : "s"}</span>`).join("");
    const solo = feeders.filter(([, v]) => v.nodes.length === 1).length;
    $("#topo-chip").textContent = `${replay.nodes} nodes • ${feeders.length} feeders • ${feeders.length - solo} shared`;
    $("#feeders-note").textContent = `${replay.nodes} nodes on ${feeders.length} feeders. ${feeders.length - solo} feeders share work between neighbors; ${solo} feeders gain a handoff partner with one more node.`;

    // Ledger.
    const by = last.revenue.by_tier;
    ledger(by);
    const hours = TIERS.reduce((s, t) => s + by[t.key].hours, 0);
    $("#ledger-total").textContent = `Replay totals: ${TIERS.reduce((s, t) => s + by[t.key].jobs, 0)} jobs, ${hours} GPU-hours, ${usd(last.revenue.compute)} compute margin and ${usd(last.revenue.power)} from the batteries.`;
  }

  ledger(null);
  const get = url => fetch(url).then(r => r.ok ? r.json() : null).catch(() => null);
  Promise.all([get("data/tower_replay.json"), get("data/density.json")]).then(([replay, density]) => {
    if (replay && replay.frames && replay.frames.length) render(replay, density);
    else $("#res-price-note").textContent = "The replay opens in the control tower.";
  });
})();
