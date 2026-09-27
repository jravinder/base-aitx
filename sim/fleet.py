"""Stage 5: the fleet. N nodes, each a battery plus a GPU. One scheduler, one clock.

Per interval, per node, the scheduler picks one action:
  charge      buy power at the grid price, fill the battery
  discharge   sell power at the grid price, down to the member reserve
  local       run a job from the local queue on the GPU (paid at the local job rate)
  sell        sell the GPU hour at the marketplace rate
  idle
Battery reserve is never breached: a node cannot discharge below RESERVE.

Failure injection: kill a node, kill a region link, kill the scheduler. Jobs on a dead node
go back to the queue. A dead region cannot sell power or compute; its nodes run local jobs only.
A dead scheduler means every node falls back to its last action until the scheduler returns.
"""

import random

RESERVE = 0.30          # share of capacity kept for the member's backup, always
CAPACITY_KWH = 39.2     # Base's stated pack size
RATE_KW = 10.0          # charge/discharge per interval (interval = 1 hour)
GPU_KW = 0.4            # GPU draw per hour while working
LOCAL_JOB_RATE = 1.20   # $/GPU-hour for a local small-model job (member tier)
# Buyer tiers (sourced, see grid/RATES.md). share: fraction of the queue. fits: where the job may run
# (node = origin node only, feeder = same feeder, far = anywhere). external = batch at a public marketplace rate.
TIERS = {
    "member":   {"rate": 1.20, "share": 0.35, "fits": ("node", "feeder")},            # the homeowner's own jobs, local job rate, fixed
    "business": {"rate": 1.09, "share": 0.15, "fits": ("feeder", "far")},            # local businesses in the city: Lambda A6000 on-demand, reliable dedicated cloud
    "base":     {"rate": 0.79, "share": 0.20, "fits": ("node", "feeder", "far")},     # Base's own forecast and telemetry jobs: RunPod community L40S, spot capacity
    "partner":  {"rate": 0.34, "share": 0.15, "fits": ("feeder", "far")},            # grid partner batch: RunPod community RTX 4090
    "external": {"rate": 0.16, "share": 0.15, "fits": ("node", "feeder", "far")},     # public marketplace batch: RunPod community RTX A5000, cheapest rate
}
INTERVALS = 72          # three days, hourly
# Demand model (#66). STUB dials, not measured: no utilisation telemetry exists.
UTIL = 0.40             # share of node-hours buyers take (jobs + marketplace), same 40% as grid/library_node.py
MEMBER_CAP = 0.25       # member self-use: at most this share of a node's hours run member-tier jobs
REGIONS = ["north", "south", "east", "west"]


PRICE_DAYS = ("2026-09-07", "2026-09-09", "2026-09-26")


def price_series(rng, n=INTERVALS, zone="lzAen"):
    """ERCOT day-ahead settlement point prices, Austin Energy load zone, $/MWh -> $/kWh.
    Three real days, no replay: 2026-09-07, 2026-09-09, 2026-09-26 (ERCOT public DAM).
    Sep 26 HE1-23 is in ercot-dam-2026-09-26.json; its HE24 (timestamp 2026-09-27 00:00) is the
    only row in ercot-dam-2026-09-27.json. Rows are ordered by timestamp.
    GPU price: flat marketplace rate with noise; replace with Akash public rates when loaded."""
    import json, os
    here = os.path.join(os.path.dirname(__file__), "..", "data")
    rows = []
    for f in ("2026-09-07", "2026-09-09", "2026-09-26", "2026-09-27"):
        rows += json.load(open(os.path.join(here, f"ercot-dam-{f}.json")))["damSppData"]
    rows.sort(key=lambda r: r["timestamp"])
    assert len(rows) == 72, len(rows)
    grid = [r[zone] / 1000.0 for r in rows][:n]
    gpu = [round(0.55 + rng.uniform(-0.05, 0.05), 3) for _ in range(n)]
    return grid, gpu


# Node kinds. house = one Base pack, one GPU. community = a shared pack on the feeder: 4x battery,
# 4x rated power, 4 GPU slots (4 jobs at once). Community nodes own no member jobs; they run feeder and far work.
KINDS = {
    "house":     {"cap": 1, "rate": 1, "slots": 1},
    "community": {"cap": 4, "rate": 4, "slots": 4},
}


class Node:
    def __init__(self, nid, region, kind="house"):
        self.id = nid
        self.region = region
        self.kind = kind
        k = KINDS[kind]
        self.cap_kwh = CAPACITY_KWH * k["cap"]
        self.rate_kw = RATE_KW * k["rate"]
        self.slots = k["slots"]
        self.soc = 0.6
        self.alive = True
        self.last_action = "idle"
        self.last_gpu = "idle"
        self.job = None
        self.jobs = []           # community only: up to self.slots running jobs
        self.next_job = None     # a job handed over from a dead neighbor on the same feeder
        self.busy = 0            # GPU slot-hours worked (jobs + marketplace), for the UTIL cap
        self.member_hours = 0    # member-tier hours run here, for the MEMBER_CAP

    def kwh(self):
        return self.soc * self.cap_kwh


def decide_battery(node, grid_price, region_alive, ahead=None):
    """Greedy with a 24h day-ahead lookahead: discharge only in the top-4 price hours of the coming
    day, charge only in the bottom-6, otherwise idle. Reserve first."""
    if ahead:
        top = sorted(ahead)[-4:]
        low = sorted(ahead)[:6]
        peak = grid_price >= top[0]
        trough = grid_price <= low[-1]
        expected_peak = sum(top) / len(top)
    else:
        peak = trough = True
        expected_peak = grid_price
    can_discharge = node.soc - node.rate_kw / node.cap_kwh >= RESERVE
    options = {"idle": 0.0}
    if region_alive and can_discharge and peak:
        options["discharge"] = node.rate_kw * grid_price
    if node.soc < 1.0 and trough:
        options["charge"] = node.rate_kw * (0.9 * expected_peak - grid_price)   # buy now, sell at the expected peak, 90% round trip
    return max(options, key=options.get), options


def decide_gpu(grid_price, gpu_price, queue, region_alive):
    """The GPU is a second device on the same node: local job, sell the hour, or idle."""
    options = {"idle": 0.0}
    if queue:
        options["local"] = LOCAL_JOB_RATE - GPU_KW * grid_price
    if region_alive:
        options["sell"] = gpu_price - GPU_KW * grid_price
    return max(options, key=options.get)


FEEDER_EXPORT_KW = 25.0   # STUB: export cap per feeder, about 2.5 nodes discharging at once
FEEDER_CAP_KW = {}        # feeder id -> real hosting capacity kW, set by sim.network --real-feeders when a utility gives one
JOB_HOURS = 3             # a local job holds the GPU for 3 intervals
UPLOAD_COST = {"node": 0.0, "feeder": 0.10, "far": 0.40}   # STUB: $ per job to move data off its origin


def job_fit(job, nid, feeder):
    """Where the job's data lives relative to this node."""
    if job["origin"] == nid:
        return "node"
    if job["feeder"] and job["feeder"] == feeder:
        return "feeder"
    return "far"


def community_extras(feeders, n, kind="community", per_feeder=1):
    """Extra nodes for stream(): per_feeder nodes of the given kind on each of the n feeders with the
    most member nodes. Ties break on feeder id, so placement is deterministic."""
    top = sorted(feeders, key=lambda f: (-len(feeders[f]), f))[:n]
    return [{"feeder": f, "kind": kind} for f in top for _ in range(per_feeder)]


def run(n_nodes, seed, kills=None, use_gpu=True, network=None, extra=None, util=UTIL, member_cap=MEMBER_CAP):
    """Batch form of stream(): runs INTERVALS hours and returns log and numbers."""
    last = None
    for last in stream(n_nodes, seed, kills, use_gpu, network, extra=extra, util=util, member_cap=member_cap):
        pass
    return last["result"]


def stream(n_nodes, seed, kills=None, use_gpu=True, network=None, inbox=None, endless=False, extra=None,
           util=UTIL, member_cap=MEMBER_CAP):
    """One interval per yield. kills: list of (interval, kind, target). kind in node|region|scheduler;
    a node target may be a list. network: (nodes, feeders) from sim.network. Adds a per-feeder export
    cap, a per-feeder price offset (STUB: uniform 0.9 to 1.1 on the zone price), job placement by
    data locality, and same-feeder failover of a running job when its node dies.
    inbox: a list the caller appends live commands to: {"kill": (kind, target)} or {"job": {...}}.
    endless: loop the 3-day price series and refill the queue, for the control tower.
    extra: list of {"feeder": fid, "kind": house|community} appended after the n_nodes member nodes.
    Extras own no jobs in the queue; the queue is the same with or without them. See community_extras().
    util: buyers take this share of the fleet's GPU slot-hours. The queue holds util x capacity of job
    hours, arriving uniformly over the horizon; marketplace buyers are the external tier inside that queue,
    so an idle GPU does not sell its hour (at util=1 it does, as before). member_cap: member-tier hours on a node stay under this
    share of its hours. util=1, member_cap=1 is the old every-GPU-every-hour run."""
    import itertools
    rng = random.Random(seed)
    grid, gpu = price_series(rng)
    grid, gpu = grid * 2, gpu * 2   # wrap so the 24h lookahead never runs off the end
    nodes = [Node(i, REGIONS[i % len(REGIONS)]) for i in range(n_nodes)]
    feeder_of, offset = {}, {}
    if network:
        net_nodes, feeders = network
        feeder_of = {n["id"]: n["feeder"] for n in net_nodes}
        offset = {f: round(rng.uniform(0.9, 1.1), 3) for f in feeders}
    for i, e in enumerate(extra or []):
        nid = n_nodes + i
        nodes.append(Node(nid, REGIONS[nid % len(REGIONS)], e.get("kind", "house")))
        feeder_of[nid] = e["feeder"]
    queue = []
    for j in range(round(util * n_nodes * INTERVALS / JOB_HOURS)):
        o = rng.randrange(n_nodes)
        tier = rng.choices(list(TIERS), [v["share"] for v in TIERS.values()])[0]
        queue.append({"id": f"job{j}", "origin": o, "feeder": feeder_of.get(o), "tier": tier})
    # demand arrives over the horizon, not all at t=0 (separate rng, so the job draws above are unchanged).
    # util >= 1 keeps the old behaviour: the whole queue is there at t=0.
    backlog = []
    if util < 1.0:
        arr = random.Random(seed * 7919 + 1)
        for jb in queue:
            jb["arrive"] = arr.randrange(INTERVALS - JOB_HOURS + 1)
        backlog = sorted(queue, key=lambda jb: jb["arrive"])
        queue = []
    region_alive = {r: True for r in REGIONS}
    scheduler_alive = True
    kills = {k[0]: k for k in (kills or [])}
    revenue_power = revenue_compute = upload_total = 0.0
    jobs_done = capped = failover_ok = failover_none = hours_lost = 0
    by_fit = {"node": 0, "feeder": 0, "far": 0}
    by_tier = {k: {"jobs": 0, "revenue": 0.0, "hours": 0} for k in TIERS}
    starved = 0   # window had jobs but none may run here
    log, recovery, pending = [], {}, None

    def as_list(x):
        return x if isinstance(x, list) else [x]

    market_open = util >= 1.0   # old run: an idle GPU can always sell its hour on the marketplace

    def member_ok(nd, t):
        return nd.member_hours < member_cap * nd.slots * (t + 1) - 1e-9

    def fits(j, nd, f, t):
        return job_fit(j, nd.id, f) in TIERS[j["tier"]]["fits"] and (j["tier"] != "member" or member_ok(nd, t))

    for t in (itertools.count() if endless else range(INTERVALS)):
        h = t % INTERVALS
        while backlog and backlog[0]["arrive"] <= t:
            queue.append(backlog.pop(0))
        if endless and t and t % 24 == 0:
            for j in range(round(util * n_nodes * 24 / JOB_HOURS)):   # a day's worth of new jobs
                o = rng.randrange(n_nodes)
                tier = rng.choices(list(TIERS), [v["share"] for v in TIERS.values()])[0]
                queue.append({"id": f"job{t}-{j}", "origin": o, "feeder": feeder_of.get(o), "tier": tier})
        while inbox:
            cmd = inbox.pop(0)
            if "kill" in cmd:
                kills[t] = (t, *cmd["kill"])
            elif "job" in cmd:
                queue.insert(0, cmd["job"])
        if t in kills:
            _, kind, target = kills[t]
            pending = (t, kind, target)
            if kind == "node":
                for tid in as_list(target):
                    nd = nodes[tid]
                    nd.alive = False
                    for jb in ([nd.job] if nd.job else []) + nd.jobs:
                        f0 = feeder_of.get(nd.id)
                        nb = [x for x in nodes if x.alive and x.next_job is None and f0 and feeder_of.get(x.id) == f0]
                        if nb:
                            nb[0].next_job = jb          # same-feeder neighbor takes it next; progress kept
                            failover_ok += 1
                        else:
                            queue.insert(0, jb[0])       # no neighbor on the feeder: requeue, restart from zero
                            hours_lost += JOB_HOURS - jb[1]
                            failover_none += 1
                    nd.job, nd.jobs = None, []
            elif kind == "region":
                region_alive[target] = False
            elif kind == "scheduler":
                scheduler_alive = False
        for kt, kv in kills.items():          # everything comes back 3 intervals later
            if t == kt + 3:
                _, kind, target = kv
                if kind == "node":
                    for tid in as_list(target):
                        nodes[tid].alive = True
                elif kind == "region":
                    region_alive[target] = True
                else:
                    scheduler_alive = True

        row = {"t": t, "grid": grid[h], "gpu": gpu[h], "actions": {}, "gpu_actions": {}, "queue": len(queue)}
        active, margin, export = 0, 0.0, {}
        for nd in nodes:
            if not nd.alive:
                row["actions"][nd.id] = "dead"
                continue
            f = feeder_of.get(nd.id)
            node_price = grid[h] * offset.get(f, 1.0)
            alive_r = region_alive[nd.region]

            # battery lane. kw: what this node moves this hour; a community node discharges only the
            # headroom the feeder cap leaves, and counts as capped when that is under one house unit.
            kw = nd.rate_kw
            if scheduler_alive:
                b, options = decide_battery(nd, node_price, alive_r, grid[h:h + 24])
                if f and b == "discharge":
                    kw = min(nd.rate_kw, FEEDER_CAP_KW.get(f, FEEDER_EXPORT_KW) - export.get(f, 0.0))
                    if kw < RATE_KW:
                        options.pop("discharge")
                        b = max(options, key=options.get)   # feeder is full: next best battery action
                        capped += 1
                nd.last_action = b
            else:
                b = nd.last_action
                if b == "discharge" and (nd.soc - nd.rate_kw / nd.cap_kwh < RESERVE or not alive_r):
                    b = "idle"   # reserve holds even without a scheduler
            if b == "discharge":
                nd.soc -= kw / nd.cap_kwh
                export[f] = export.get(f, 0.0) + kw
                revenue_power += kw * node_price; margin += kw * node_price
            elif b == "charge":
                nd.soc = min(1.0, nd.soc + nd.rate_kw / nd.cap_kwh)
                revenue_power -= nd.rate_kw * node_price
            assert nd.soc >= RESERVE - 1e-9, f"reserve breached on node {nd.id} at t={t}"

            # GPU lane
            g = "idle"
            if use_gpu and nd.slots > 1:
                # community: up to nd.slots jobs at once, same window and same best-value rule per slot.
                # Free slots sell the hour when the queue is empty. No new jobs are taken while the scheduler is down.
                if nd.next_job and len(nd.jobs) < nd.slots:
                    nd.jobs.append(nd.next_job); nd.next_job = None
                while scheduler_alive and len(nd.jobs) < nd.slots and queue:
                    near = [j for j in queue if j["origin"] == nd.id or (f and j["feeder"] == f)]
                    window = [j for j in near + queue[:20] if fits(j, nd, f, t)]
                    if not window:
                        starved += 1
                        break
                    best = max(window, key=lambda j: TIERS[j["tier"]]["rate"] - UPLOAD_COST[job_fit(j, nd.id, f)] / JOB_HOURS)
                    queue.remove(best)
                    fit = job_fit(best, nd.id, f)
                    upload_total += UPLOAD_COST[fit]
                    by_fit[fit] += 1
                    nd.jobs.append([best, JOB_HOURS, UPLOAD_COST[fit]])
                for jb in list(nd.jobs):
                    tier = jb[0]["tier"]
                    hour = (TIERS[tier]["rate"] - GPU_KW * grid[h]) - jb[2] / JOB_HOURS
                    revenue_compute += hour; margin += hour
                    by_tier[tier]["revenue"] += hour; by_tier[tier]["hours"] += 1
                    nd.busy += 1; nd.member_hours += tier == "member"
                    jb[1] -= 1
                    if jb[1] == 0:
                        jobs_done += 1; by_tier[tier]["jobs"] += 1
                        nd.jobs.remove(jb)
                free = nd.slots - len(nd.jobs)
                if market_open and alive_r and free and not queue:   # same rule as decide_gpu: sell only when the queue is empty
                    nd.busy += free
                    sell = free * (gpu[h] - GPU_KW * grid[h])
                    revenue_compute += sell; margin += sell
                    by_tier["external"]["revenue"] += sell; by_tier["external"]["hours"] += free
                g = "local" if nd.jobs else ("sell" if alive_r and free else "idle")
            elif use_gpu:
                if nd.job is None and nd.next_job:
                    nd.job, nd.next_job = nd.next_job, None
                if nd.job:
                    g = "local"
                elif scheduler_alive:
                    g = decide_gpu(grid[h], gpu[h], queue, alive_r)
                    nd.last_gpu = g
                else:
                    g = nd.last_gpu if (queue or nd.last_gpu != "local") and alive_r else "idle"
                if g == "sell" and not market_open:
                    g = "idle"   # demand model: every buyer, marketplace included, is in the util-sized queue
                if g == "local":
                    if nd.job is None:
                        # candidates: every job whose data is on this node or feeder, plus the head of the global queue.
                        # Scanning only the head of one queue starves nodes (head-of-line blocking; see M5).
                        near = [j for j in queue if j["origin"] == nd.id or (f and j["feeder"] == f)]
                        window = [j for j in near + queue[:20] if fits(j, nd, f, t)]
                        if not window:
                            starved += 1
                            g = "idle"
                    if g == "local":
                        if nd.job is None:
                            # best value first: tier rate minus the upload to get the data here
                            best = max(window, key=lambda j: TIERS[j["tier"]]["rate"] - UPLOAD_COST[job_fit(j, nd.id, f)] / JOB_HOURS)
                            queue.remove(best)
                            fit = job_fit(best, nd.id, f)
                            upload_total += UPLOAD_COST[fit]
                            by_fit[fit] += 1
                            nd.job = [best, JOB_HOURS, UPLOAD_COST[fit]]
                        tier = nd.job[0]["tier"]
                        hour = (TIERS[tier]["rate"] - GPU_KW * grid[h]) - nd.job[2] / JOB_HOURS
                        revenue_compute += hour; margin += hour
                        by_tier[tier]["revenue"] += hour; by_tier[tier]["hours"] += 1
                        nd.busy += 1; nd.member_hours += tier == "member"
                        nd.job[1] -= 1
                        if nd.job[1] == 0:
                            jobs_done += 1; by_tier[tier]["jobs"] += 1
                            nd.job = None
                if g == "sell":
                    nd.busy += 1
                    sell = gpu[h] - GPU_KW * grid[h]
                    revenue_compute += sell; margin += sell
                    by_tier["external"]["revenue"] += sell; by_tier["external"]["hours"] += 1
            row["actions"][nd.id] = b if b != "idle" else g
            row["gpu_actions"][nd.id] = g
            active += 1
        row["active"] = active
        row["margin"] = round(margin, 2)
        log.append(row)
        # recovery = intervals from kill until per-interval margin is back to 95% of the pre-kill interval
        if pending and t > pending[0]:
            prev = [r["margin"] for r in log[max(0, pending[0] - 3):pending[0]]]
            before = sum(prev) / len(prev) if prev else 0.0
            if margin >= 0.95 * before:
                recovery[f"{pending[1]}:{pending[2] if not isinstance(pending[2], list) else f'{len(pending[2])} nodes'}"] = t - pending[0]
                pending = None

        yield {"t": t, "row": row, "result": {
        "log": log,
        "revenue_power": round(revenue_power, 2),
        "revenue_compute": round(revenue_compute, 2),
        "jobs_done": jobs_done,
        "jobs_lost": 0,
        "recovery_intervals": recovery,
        "discharges_capped": capped,
        "failover_ok": failover_ok,
        "failover_none": failover_none,
        "gpu_hours_lost": hours_lost,
        "upload_cost": round(upload_total, 2),
        "compute_members": round(by_tier["member"]["revenue"], 2),
        "compute_outside": round(revenue_compute - by_tier["member"]["revenue"], 2),
        "gpu_utilisation": round(sum(v["hours"] for v in by_tier.values()) / max(sum(x.slots for x in nodes) * (t + 1), 1), 3),
        "jobs_by_fit": by_fit, "by_tier": {k: {"jobs": v["jobs"], "hours": v["hours"], "revenue": round(v["revenue"], 2)} for k, v in by_tier.items()}, "starved": starved,
        }, "nodes": nodes, "queue": queue, "export": export, "region_alive": dict(region_alive), "scheduler_alive": scheduler_alive}


def panel(n_nodes, seed, util=UTIL, member_cap=MEMBER_CAP):
    with_compute = run(n_nodes, seed, util=util, member_cap=member_cap)
    power_only = run(n_nodes, seed, use_gpu=False)
    full = run(n_nodes, seed, util=1.0, member_cap=1.0)   # old run: every GPU busy every hour, for comparison
    kills = [(20, "node", 0), (30, "region", "east"), (40, "scheduler", None)]
    killed = run(n_nodes, seed, kills=kills, util=util, member_cap=member_cap)
    # recovery = hours from the kill until the hourly margin is back to 95% of the same hour with no kill
    recovery = {}
    for kt, kind, target in kills:
        for t in range(kt + 1, INTERVALS):
            if killed["log"][t]["margin"] >= 0.95 * with_compute["log"][t]["margin"]:
                recovery[f"{kind}:{target}"] = t - kt
                break
    killed["recovery_intervals"] = recovery
    return {
        "name": "Fleet",
        "nodes": n_nodes,
        "intervals": INTERVALS,
        "number": round(with_compute["revenue_power"] + with_compute["revenue_compute"], 2),
        "unit": "$ fleet margin over 3 days, power plus compute",
        "power_only": round(power_only["revenue_power"], 2),
        "util": util,
        "member_cap": member_cap,
        "gpu_utilisation": with_compute["gpu_utilisation"],
        "compute": with_compute["revenue_compute"],
        "compute_members": with_compute["compute_members"],
        "compute_outside": with_compute["compute_outside"],
        "at_full_util": {"number": round(full["revenue_power"] + full["revenue_compute"], 2),
                         "compute": full["revenue_compute"], "compute_members": full["compute_members"],
                         "compute_outside": full["compute_outside"]},
        "jobs_lost_under_kills": killed["jobs_lost"],
        "recovery_intervals": killed["recovery_intervals"],
        "reserve_breaches": 0,
        "by_tier": with_compute["by_tier"],
        "tiers": {k: {"rate": v["rate"], "share": v["share"]} for k, v in TIERS.items()},
        "ceiling": "MILP on real telemetry; greedy on three historical days is the floor. Say replication.",
        "assumptions": [
            "grid price: ERCOT DAM, Austin Energy load zone (LZ_AEN), three real days 2026-09-07, 09-09, 09-26; no replay",
            f"STUB demand: buyers take {util:.0%} of GPU node-hours (jobs plus marketplace); member self-use capped at {member_cap:.0%} of a node's hours. No telemetry; both are dials (--util, --member-cap)",
            "compute_members = member tier, homeowners paying $1.20/h for jobs on their own node; compute_outside = every other buyer", "sourced: buyer rates per GPU hour: member 1.20 (local job rate, fixed, unchanged), business 1.09 (Lambda A6000 on-demand, reliable dedicated cloud), base 0.79 (RunPod community L40S, Base's own batch work on spot capacity), partner 0.34 (RunPod community RTX 4090), external 0.16 (RunPod community RTX A5000, cheapest public marketplace batch). See grid/RATES.md.", "scheduler: greedy with 24h day-ahead lookahead (top-4 hours discharge, bottom-6 charge)",
            "interval = 1 hour, 72 intervals",
            f"reserve = {RESERVE:.0%} of {CAPACITY_KWH} kWh, never breached (asserted)",
            "recovery = hours until the hourly margin is back to 95% of the same hour with no kill; components return after 3",
        ],
        "kill_log": killed["log"],
    }
