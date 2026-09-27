"""Basenet M6: community nodes. Same fleet, same prices, same 20% kill; only where the added
capacity sits changes.

Three arms at the same member fleet (default 240 nodes, seed 7, real zip feeders from sim.network):
  baseline    the member fleet alone
  houses      the same added capacity as 4 extra house nodes per chosen feeder (4N packs, 4N GPUs)
  community   N community nodes, one per chosen feeder (each 4x battery, 4x power, 4 GPU slots)
Chosen feeders: the N feeders with the most member nodes. Extras own no jobs; the queue is identical
across arms. Reports GPU hours lost under the kill, fleet margin, upload cost paid by fit, and
discharges capped by the feeder export cap.

python -m sim.community [--nodes 240] [--seed 7] [--community 5] -> data/community.json
"""

import argparse
import json
import os
import random

from sim import fleet, network


def arms(n_nodes, seed, n_comm):
    nodes, feeders = network.build(n_nodes, random.Random(seed))
    victims = random.Random(1).sample(range(n_nodes), n_nodes // 5)
    kills = [(22, "node", victims)]
    plans = {
        "baseline": None,
        "houses": fleet.community_extras(feeders, n_comm, kind="house", per_feeder=4),
        "community": fleet.community_extras(feeders, n_comm),
    }
    rows = []
    for name, extra in plans.items():
        r = fleet.run(n_nodes, seed, kills=kills, network=(nodes, feeders), extra=extra)
        rows.append({
            "arm": name,
            "extra_nodes": len(extra or []),
            "gpu_hours_lost": r["gpu_hours_lost"],
            "failover_ok": r["failover_ok"],
            "requeued": r["failover_none"],
            "margin": round(r["revenue_power"] + r["revenue_compute"], 2),
            "margin_power": r["revenue_power"],
            "margin_compute": r["revenue_compute"],
            "jobs_done": r["jobs_done"],
            "upload_cost": r["upload_cost"],
            "jobs_by_fit": r["jobs_by_fit"],
            "discharges_capped": r["discharges_capped"],
        })
    chosen = [e["feeder"] for e in plans["community"]]
    return rows, {"feeders": len(feeders), "chosen": chosen, "chosen_sizes": [len(feeders[f]) for f in chosen], "killed": len(victims)}


def table(rows):
    head = "arm        extra  gpu_h_lost  failover/requeued  margin      upload $  fit node/feeder/far  capped"
    lines = [head]
    for r in rows:
        bf = r["jobs_by_fit"]
        lines.append(f"{r['arm']:<10} {r['extra_nodes']:>5}  {r['gpu_hours_lost']:>10}  {r['failover_ok']:>8}/{r['requeued']:<8}  "
                     f"{r['margin']:>9.2f}  {r['upload_cost']:>8.2f}  {bf['node']:>5}/{bf['feeder']}/{bf['far']:<7}  {r['discharges_capped']:>6}")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--community", type=int, default=5)
    a = ap.parse_args()
    rows, meta = arms(a.nodes, a.seed, a.community)
    out = {"nodes": a.nodes, "seed": a.seed, "community": a.community, "network": meta, "rows": rows,
           "upload_cost": fleet.UPLOAD_COST, "feeder_export_kw": fleet.FEEDER_EXPORT_KW,
           "ceiling": "placement as an optimiser over feeder load, queue origin and kill risk, not the N densest feeders"}
    here = os.path.join(os.path.dirname(__file__), "..", "data")
    json.dump(out, open(os.path.join(here, "community.json"), "w"), indent=1)
    print(f"{a.nodes} nodes, seed {a.seed}, {meta['feeders']} feeders, {meta['killed']} killed at h22. "
          f"Chosen feeders {meta['chosen']} sizes {meta['chosen_sizes']}")
    print(table(rows))
