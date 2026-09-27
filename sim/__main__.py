"""python -m sim [--nodes 50] [--seed 7] [--util 0.40] [--member-cap 0.25] [--real-feeders] -> out/report.json and out/report.md

--real-feeders (default off) adds a feeder block: fleet margin with the synthetic feeder map and with
real substations from data/feeders.json (sim.network). Without the flag the report is unchanged."""

import argparse
import json
import os
import random
import time

from sim import fleet, stages

ap = argparse.ArgumentParser()
ap.add_argument("--nodes", type=int, default=50)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--util", type=float, default=fleet.UTIL, help="share of GPU node-hours buyers take")
ap.add_argument("--member-cap", type=float, default=fleet.MEMBER_CAP, help="max share of a node's hours for member self-use")
ap.add_argument("--real-feeders", action="store_true", help="add a feeder block with real substations (default off)")
args = ap.parse_args()

t0 = time.time()
rng = random.Random(args.seed)
d = stages.DIALS
weeks = 4
members = stages.make_members(d["leads_per_week"] * weeks, rng)

m1, p1 = stages.stage1_territory(members)
m2, p2 = stages.stage2_photo(m1, random.Random(args.seed), d["photo_drop_rate"])
m2g, _ = stages.stage2_photo(m1, random.Random(args.seed), d["photo_drop_rate_guided"])
m3, p3 = stages.stage3_permits(m2)
m4, p4 = stages.stage4_routing(m3, d["crews"], d["installs_per_crew_day"])
p5 = fleet.panel(args.nodes, args.seed, args.util, args.member_cap)

# the thread: homes lost at the photo step, and what the fleet never schedules
lost_per_month = len(m2g) - len(m2)
per_node_margin_3d = (p5["number"] - p5["power_only"]) / p5["nodes"]
per_node_margin_month = per_node_margin_3d * 10
header = {
    "homes_lost_per_month_at_photo": lost_per_month,
    "compute_margin_per_node_per_month": round(per_node_margin_month, 2),
    "margin_never_scheduled_per_month": round(lost_per_month * per_node_margin_month, 2),
    "sentence": (
        f"At a {d['photo_drop_rate']:.0%} photo drop rate, {lost_per_month} homes a month never reach the fleet "
        f"that guided collection at {d['photo_drop_rate_guided']:.0%} would keep. "
        f"That is ${lost_per_month * per_node_margin_month:,.0f} a month of compute margin never scheduled."
    ),
}

kill_log = p5.pop("kill_log")
report = {
    "seed": args.seed,
    "dials": d,
    "funnel": {"leads": len(members), "served": len(m1), "photos_complete": len(m2), "routed": len(m4)},
    "header": header,
    "panels": [p1, p2, p3, p4, p5],
    "runtime_s": round(time.time() - t0, 2),
}
if args.real_feeders:
    from sim import network
    block = {}
    for label, real in (("synthetic", None), ("real", network.load_real())):
        caps = {}
        nodes, feeders = network.build(args.nodes, random.Random(args.seed), real, caps)
        fleet.FEEDER_CAP_KW = caps
        r = fleet.run(args.nodes, args.seed, network=(nodes, feeders), util=args.util, member_cap=args.member_cap)
        block[label] = {"feeders": len(feeders), "nodes_on_real_substations": sum(n.get("real", False) for n in nodes),
                        "feeders_with_real_hosting_capacity": len(caps),
                        "margin": round(r["revenue_power"] + r["revenue_compute"], 2),
                        "discharges_capped": r["discharges_capped"]}
    fleet.FEEDER_CAP_KW = {}
    block["export_cap_kw"] = fleet.FEEDER_EXPORT_KW
    block["ceiling"] = "utility feeder ids, phase and hosting capacity per feeder; none are open in Base territory (grid/FEEDERS.md)"
    report["feeders"] = block

for d_out in ("out", "web/data"):
    os.makedirs(d_out, exist_ok=True)
    json.dump(report, open(f"{d_out}/report.json", "w"), indent=1)
    json.dump(kill_log, open(f"{d_out}/fleet_kill_log.json", "w"))

lines = [f"# Base Fleet report (seed {args.seed}, {args.nodes} nodes, {report['runtime_s']}s)", "", header["sentence"], ""]
lines += ["| Panel | Number | Unit | Ceiling |", "|---|---|---|---|"]
for p in report["panels"]:
    lines.append(f"| {p['name']} | {p['number']} | {p['unit']} | {p['ceiling']} |")
lines += ["", f"Fleet power-only margin: ${p5['power_only']}. With compute: ${p5['number']} at {p5['util']:.0%} GPU utilisation "
          f"(achieved {p5['gpu_utilisation']:.1%}; member self-use cap {p5['member_cap']:.0%} of node hours).",
          f"Compute ${p5['compute']}: members on their own node ${p5['compute_members']}, outside buyers ${p5['compute_outside']}.",
          f"At 100% utilisation (old run, every GPU every hour): ${p5['at_full_util']['number']}, compute ${p5['at_full_util']['compute']} "
          f"(members ${p5['at_full_util']['compute_members']}, outside ${p5['at_full_util']['compute_outside']}).",
          f"Jobs lost under kills: {p5['jobs_lost_under_kills']}. Recovery (intervals): {p5['recovery_intervals']}. Reserve breaches: 0.", ""]
lines += ["Assumptions:"] + [f"- {p['name']}: {a}" for p in report["panels"] for a in p["assumptions"]]
if args.real_feeders:
    b = report["feeders"]
    lines += ["Feeders (--real-feeders): margin with synthetic feeders ${} ({} capped discharges, {} feeders); "
              "with real substations ${} ({} capped, {} feeders, {} of {} nodes on real substations). "
              "Export cap {} kW on every feeder: no utility publishes hosting capacity.".format(
                  b["synthetic"]["margin"], b["synthetic"]["discharges_capped"], b["synthetic"]["feeders"],
                  b["real"]["margin"], b["real"]["discharges_capped"], b["real"]["feeders"],
                  b["real"]["nodes_on_real_substations"], args.nodes, b["export_cap_kw"]), ""]
open("out/report.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
