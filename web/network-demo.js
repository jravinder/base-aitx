(() => {
  "use strict";

  const ids = [
    "network-grid", "network-log", "job-status", "reserve-value",
    "submit-job", "fail-node", "reset-network", "network-summary",
  ];
  const elements = ids.map((id) => document.getElementById(id));
  if (elements.some((element) => !element)) return;

  const [grid, log, status, reserve, submit, fail, reset, summary] = elements;
  const QUEUE_MS = 1200;
  const RUN_MS = 6000;
  const timers = new Set();
  let generation = 0;
  let nodes = [];
  let job = null;
  let jobCount = 0;
  let eventCount = 0;

  grid.setAttribute("role", "list");
  grid.setAttribute("aria-label", "SIMULATION: 12 battery and GPU nodes");
  log.setAttribute("role", "log");
  log.setAttribute("aria-live", "polite");
  log.setAttribute("aria-relevant", "additions");
  log.setAttribute("aria-label", "Simulation event history");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  status.setAttribute("aria-atomic", "true");
  [submit, fail, reset].forEach((button) => {
    button.setAttribute("type", "button");
  });

  function cancelTimers() {
    generation += 1;
    timers.forEach((timer) => clearTimeout(timer));
    timers.clear();
  }

  // The generation guard also rejects callbacks belonging to an earlier reset.
  function schedule(callback, delay) {
    const scheduledGeneration = generation;
    const timer = setTimeout(() => {
      timers.delete(timer);
      if (scheduledGeneration === generation) callback();
    }, delay);
    timers.add(timer);
  }

  function record(message) {
    const entry = document.createElement(
      log.tagName === "OL" || log.tagName === "UL" ? "li" : "p",
    );
    entry.className = "network-event";
    entry.textContent = `${String(++eventCount).padStart(2, "0")} / ${message}`;
    log.appendChild(entry);
    if (log.children.length > 30) log.firstElementChild.remove();
  }

  function render() {
    const healthyCount = nodes.filter((node) => node.online).length;
    const pending = job && (job.state === "queued" || job.state === "running");
    nodes.forEach((node) => {
      const state = !node.online ? "offline"
        : job && job.state === "running" && job.nodeId === node.id
          ? "running" : "healthy";
      node.element.className = `network-node is-${state}`;
      node.element.dataset.state = state;
      const detail = state === "running" ? `Running job ${job.id}`
        : state === "offline" ? "Offline" : "Ready";
      node.label.textContent = `Node ${String(node.id).padStart(2, "0")}`;
      node.detail.textContent = detail;
      const description = `Node ${node.id}: ${detail}. Simulated battery and GPU.`;
      node.element.setAttribute("aria-label", description);
      node.element.setAttribute("title", description);
    });

    const state = job ? job.state : "idle";
    status.dataset.state = state;
    const labels = {
      idle: "No job submitted",
      queued: job && `Job ${job.id}: ${job.retries ? "requeued" : "queued"}`,
      running: job && `Job ${job.id}: running on Node ${job.nodeId}`,
      completed: job && `Job ${job.id}: completed on Node ${job.nodeId}`,
      blocked: job && `Job ${job.id}: blocked - no healthy nodes`,
    };
    status.textContent = labels[state];
    reserve.textContent = "30%";
    reserve.setAttribute("title", "Fixed simulation assumption, not measured battery data.");

    const context = state === "queued" && job.retries
      ? "Interrupted work is queued for another healthy node."
      : state === "running" ? "One simulated job is running."
        : state === "completed" ? "Simulated job completed; no GPU work was executed."
          : state === "blocked" || healthyCount === 0 ? "No healthy nodes remain. Reset to restore the network."
            : state === "queued" ? "One simulated job is awaiting placement."
              : "No job is running.";
    summary.textContent = `SIMULATION / ${healthyCount} of 12 nodes available. ${context} Reserve floor is a planning assumption for this demo.`;
    submit.disabled = Boolean(pending) || healthyCount === 0;
    fail.disabled = state === "queued" || healthyCount === 0;
    reset.disabled = false;
  }

  function startJob() {
    if (!job || job.state !== "queued") return;
    const destination = nodes.find((node) => node.online);
    if (!destination) {
      job.state = "blocked";
      record(`Job ${job.id} blocked: no healthy nodes remain. Reset to restore.`);
      render();
      return;
    }
    job.nodeId = destination.id;
    job.state = "running";
    record(`Job ${job.id} ${job.retries ? "restarted" : "running"} on Node ${destination.id}.`);
    render();
    schedule(() => {
      job.state = "completed";
      record(`Job ${job.id} completed on Node ${job.nodeId}. Simulated result only.`);
      render();
    }, RUN_MS);
  }

  submit.addEventListener("click", () => {
    if (submit.disabled) return;
    job = { id: ++jobCount, state: "queued", nodeId: null, retries: 0 };
    record(`Job ${job.id} queued. Simulated placement only.`);
    render();
    schedule(startJob, QUEUE_MS);
  });

  fail.addEventListener("click", () => {
    if (fail.disabled) return;
    const running = job && job.state === "running";
    const target = running ? nodes.find((node) => node.id === job.nodeId)
      : nodes.find((node) => node.online);
    if (!target) return;
    target.online = false;
    record(`Node ${target.id} offline: simulated failure. Reserve floor remains 30% (assumed).`);
    if (running) {
      cancelTimers();
      job.state = "queued";
      job.nodeId = null;
      job.retries += 1;
      record(`Job ${job.id} requeued; interrupted work will restart on a healthy node.`);
      schedule(startJob, QUEUE_MS);
    }
    render();
  });

  function resetNetwork() {
    cancelTimers();
    job = null;
    jobCount = 0;
    eventCount = 0;
    grid.replaceChildren();
    log.replaceChildren();
    nodes = Array.from({ length: 12 }, (_, index) => {
      const element = document.createElement("div");
      const label = document.createElement("span");
      const detail = document.createElement("span");
      element.setAttribute("role", "listitem");
      element.dataset.nodeId = String(index + 1);
      label.className = "network-node-label";
      detail.className = "network-node-status";
      element.append(label, detail);
      grid.appendChild(element);
      return { id: index + 1, online: true, element, label, detail };
    });
    record("SIMULATION reset: 12 healthy nodes. No real GPU work or battery measurements.");
    render();
  }

  reset.addEventListener("click", resetNetwork);
  resetNetwork();
})();
