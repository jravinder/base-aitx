"""Basenet M4: density sweep. Same fleet, same prices, same kills; only nodes-per-feeder changes.

For each density d, every feeder holds exactly d nodes (n_nodes / d feeders). Report, per node:
compute margin, GPU hours lost under a 20% kill, upload cost, and feeder relief (peak kW the
batteries take off the feeder at the top price hour).

python3 -m sim.density [--nodes 120] [--seed 7] [--util 0.40] -> out/density.json
120 nodes is the run the docs quote (#65).
"""

import argparse
import json
import os
import random

from sim import fleet


def build_at_density(n_nodes, d, rng):
    nodes, feeders = [], {}
    for i in range(n_nodes):
        fid = f"f{i // d}"
        feeders.setdefault(fid, []).append(i)
        nodes.append({"id": i, "feeder": fid, "substation": fid, "zone": "lzAen",
                      "x": rng.uniform(0, 30), "y": rng.uniform(0, 30)})
    return nodes, feeders


def sweep(n_nodes, seed, densities, util=fleet.UTIL, member_cap=fleet.MEMBER_CAP):
    rows = []
    victims = random.Random(1).sample(range(n_nodes), n_nodes // 5)
    kills = [(22, "node", victims)]
    for d in densities:
        nodes, feeders = build_at_density(n_nodes, d, random.Random(seed))
        r = fleet.run(n_nodes, seed, kills=kills, network=(nodes, feeders), util=util, member_cap=member_cap)
        # feeder relief: at the top price hour, kW discharged per feeder, averaged over feeders
        top = max(range(fleet.INTERVALS), key=lambda t: r["log"][t]["grid"])
        n_dis = sum(1 for a in r["log"][top]["actions"].values() if a == "discharge")
        rows.append({
            "nodes_per_feeder": d,
            "feeders": len(feeders),
            "margin_per_node": round((r["revenue_power"] + r["revenue_compute"]) / n_nodes, 2),
            "compute_per_node": round(r["revenue_compute"] / n_nodes, 2),
            "failover_rate": round(r["failover_ok"] / max(r["failover_ok"] + r["failover_none"], 1), 2),
            "gpu_hours_lost": r["gpu_hours_lost"],
            "upload_cost_per_node": round(r["upload_cost"] / n_nodes, 2),
            "discharges_capped": r["discharges_capped"],
            "peak_relief_kw_per_feeder": round(n_dis * fleet.RATE_KW / len(feeders), 1),
        })
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=120)
    ap.add_argument("--util", type=float, default=fleet.UTIL)
    ap.add_argument("--member-cap", type=float, default=fleet.MEMBER_CAP)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rows = sweep(a.nodes, a.seed, [1, 2, 3, 4, 6, 8, 12, 20, 30], a.util, a.member_cap)
    cp = [r["compute_per_node"] for r in rows]
    out = {"nodes": a.nodes, "seed": a.seed, "util": a.util, "member_cap": a.member_cap, "rows": rows,
           "compute_per_node_range": [min(cp), max(cp)],
           "ceiling": "real feeder map and line ratings; density then set by routing (Panel 4), not assumed"}
    os.makedirs("out", exist_ok=True)
    json.dump(out, open("out/density.json", "w"), indent=1)
    print("d  feeders  margin/node  compute/node  failover  gpu_h_lost  upload/node  capped  relief kW/feeder")
    for r in rows:
        print(*r.values(), sep="  ")
    print(f"compute per node: ${min(cp):.2f} to ${max(cp):.2f} across the sweep ({a.nodes} nodes, {a.util:.0%} utilisation)")
