"""Basenet M1: topology. Node -> feeder -> substation (zip) -> load zone.

Feeder ids are synthetic: nodes in one zip are split into feeders of at most FEEDER_CAP homes.
STUB: a real map would come from the utility's feeder GIS. Density = nodes per feeder.

python -m sim.network [--nodes 50] [--seed 7] [--community N] -> out/network.json
--community N adds N community nodes (4x battery, 4 GPU slots) on the N feeders with the most
member nodes. 0 (default) leaves the house-only fleet exactly as before.
--real-feeders (default off) puts nodes in a zip from data/feeders.json on that zip's real
substations (OpenStreetMap), round robin by node id, then splits each substation into feeders of
FEEDER_CAP homes. A feeder takes its real hosting capacity as the export cap when the file gives
one; no utility publishes one today, so the cap stays FEEDER_EXPORT_KW. Other zips stay synthetic.
"""

import argparse
import json
import os
import random

ZIPS = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "austin_zips.json")))["rows"]
FEEDER_CAP = 12     # STUB: homes per feeder that one Base cluster can fill
ZONE = "lzAen"      # ERCOT load zone for all of Austin


def load_real():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "feeders.json")
    return json.load(open(path))["zips"]


def build(n_nodes, rng, real=None, caps=None):
    """real: the zips dict from data/feeders.json, or None for the synthetic map. caps: optional
    dict, filled with feeder id -> hosting capacity kW where the data gives one."""
    picks = rng.choices(ZIPS, weights=[z["permits"] for z in ZIPS], k=n_nodes)
    by_zip = {}
    for i, z in enumerate(picks):
        by_zip.setdefault(z["zip"], []).append(i)
    nodes = [None] * n_nodes
    feeders = {}
    caps = {} if caps is None else caps
    for zip_code, ids in by_zip.items():
        subs = (real or {}).get(zip_code, {}).get("substations") or []
        per_sub = {}
        for k, nid in enumerate(ids):
            if subs:
                sub = subs[k % len(subs)]
                sid = (sub["name"] or sub["osm"]).replace(" ", "_")
                j = per_sub.setdefault(sid, 0); per_sub[sid] += 1
                fid, station = f"{zip_code}-{sid}-f{j // FEEDER_CAP}", sid
                hc = real[zip_code].get("hosting_capacity_kw")
                if hc:
                    caps[fid] = hc
            else:
                fid, station = f"{zip_code}-f{k // FEEDER_CAP}", zip_code
            feeders.setdefault(fid, []).append(nid)
            nodes[nid] = {"id": nid, "zip": zip_code, "feeder": fid, "substation": station, "zone": ZONE,
                          "x": rng.uniform(0, 30), "y": rng.uniform(0, 30)}
            if real is not None:
                nodes[nid]["real"] = bool(subs)
    return nodes, feeders


def stats(nodes, feeders):
    sizes = sorted((len(v) for v in feeders.values()), reverse=True)
    dense = sum(1 for s in sizes if s >= 3)
    return {
        "nodes": len(nodes),
        "feeders": len(feeders),
        "substations": len({n["substation"] for n in nodes}),
        "nodes_per_feeder_mean": round(len(nodes) / len(feeders), 2),
        "nodes_per_feeder_max": sizes[0],
        "feeders_with_1_node": sum(1 for s in sizes if s == 1),
        "feeders_with_3_or_more": dense,
        "share_of_nodes_with_a_neighbor": round(sum(s for s in sizes if s >= 2) / len(nodes), 2),
        "ceiling": "real feeder GIS from the utility; density is then a Base routing choice (Panel 4), not a draw",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--community", type=int, default=0, help="community nodes, one per feeder, densest feeders first")
    ap.add_argument("--real-feeders", action="store_true", help="real substations from data/feeders.json (default off)")
    a = ap.parse_args()
    caps = {}
    nodes, feeders = build(a.nodes, random.Random(a.seed), load_real() if a.real_feeders else None, caps)
    s = stats(nodes, feeders)
    from sim import fleet
    fleet.FEEDER_CAP_KW = caps
    if a.real_feeders:
        s["real_feeders"] = {"nodes_on_real_substations": sum(n["real"] for n in nodes),
                             "feeders_with_real_hosting_capacity": len(caps)}
    extra = fleet.community_extras(feeders, a.community) if a.community else None
    if extra:
        s["community"] = {"nodes": a.community, "feeders": [e["feeder"] for e in extra]}
    flat = fleet.run(a.nodes, a.seed)
    net = fleet.run(a.nodes, a.seed, network=(nodes, feeders), extra=extra)
    s["m2"] = {
        "margin_flat": round(flat["revenue_power"] + flat["revenue_compute"], 2),
        "margin_with_feeder_caps": round(net["revenue_power"] + net["revenue_compute"], 2),
        "discharges_capped": net["discharges_capped"],
        "export_cap_kw": fleet.FEEDER_EXPORT_KW,
        "ceiling": "optimal power flow on a real feeder; the cap is one number standing in for a line rating",
    }
    victims = random.Random(1).sample(range(a.nodes), a.nodes // 5)
    kills = [(22, "node", victims)]          # 20% of nodes die at hour 22, mid-job
    fk = fleet.run(a.nodes, a.seed, kills=kills)
    nk = fleet.run(a.nodes, a.seed, kills=kills, network=(nodes, feeders), extra=extra)
    s["m3"] = {
        "nodes_killed": len(victims),
        "flat": {"failover_ok": fk["failover_ok"], "requeued": fk["failover_none"], "gpu_hours_lost": fk["gpu_hours_lost"], "upload_cost": fk["upload_cost"]},
        "net": {"failover_ok": nk["failover_ok"], "requeued": nk["failover_none"], "gpu_hours_lost": nk["gpu_hours_lost"], "upload_cost": nk["upload_cost"], "jobs_by_fit": nk["jobs_by_fit"]},
        "ceiling": "placement as a min-cost assignment over the whole queue; failover with checkpointing so no hours are lost even without a neighbor",
    }
    os.makedirs("out", exist_ok=True)
    json.dump({"stats": s, "feeders": feeders, "nodes": nodes}, open("out/network.json", "w"), indent=1)
    print(json.dumps(s, indent=1))
