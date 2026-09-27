"""Member records for the brain. Issues #52 and #53.

Writes data/members.json and brain/questions.json. Every value is joined from a real
source in this repo. Nothing is invented.

Sources
  house/cohort.json            40 real houses: zip, year_built, fit, guessable, confirm_with_member.
                               The street address and any owner data are dropped. Zip only.
  sim/network.py               feeder for node i, build(40, Random(7)).
  sim/fleet.py                 stream(40, 7, network=..., use_gpu=True). Hourly state for 72 hours.
                               Per-node cash is not exposed by the sim, so this file replays the
                               same cash rules (RATE_KW, GPU_KW, TIERS, UPLOAD_COST, FEEDER_EXPORT_KW,
                               feeder price offset) on the yielded state. Fleet totals are checked
                               against the sim's own revenue_power and revenue_compute.
  data/ercot-dam-2026-09-07.json, -09-09.json, -09-26.json (+ -09-27.json for Sep 26 HE24)
                               real ERCOT DAM prices, lzAen zone, used by the sim price series.
                               Sim defaults apply: 40% GPU utilisation (fleet.UTIL) and the member cap.
  grid/RATES.md                the GPU tier rates the sim uses.

The seven days are the 72 sim hours cycled: day 1..3 = sim hours 0..71, day 4..6 = the same
hours again, day 7 = sim hours 0..23 again. Day 1, 4, 7 = 2026-09-07 prices. Day 2, 5 = 2026-09-09.
Day 3, 6 = 2026-09-26. Three real days, no replay inside the sim (fleet.PRICE_DAYS).

Record schema (data/members.json is {"_meta": {...}, "members": [record x 40]})
{
  "member_id": "m001",
  "zip": "78745",
  "year_built": 2024,
  "fit": {"bucket": "easy", "reasons": [...]},          # from cohort.json as is
  "fields": {                                            # cohort.json guessable, keyed by field
    "main_breaker_amps": {"value": null, "source": "2025-076119 EP", "confidence": 0.4},
    ...
  },
  "confirm_with_member": ["main_breaker_amps", ...],     # from cohort.json as is
  "node": {"nid": 0, "feeder": "78745-f0", "region": "north", "battery_kwh": 39.2,
           "rate_kw": 10.0, "reserve_pct": 30, "reserve_kwh": 11.76, "gpu": true},
  "week": [                                              # 7 entries
    {"day": 1, "date": "2026-09-07", "sim_hours": [0, 23],
     "battery_usd": 1.23,          # discharge sales minus charge cost, node price
     "gpu_usd": 4.56,              # local job hours plus marketplace sale hours, net of GPU power
     "gpu_hours": 5,               # hours the GPU was busy (local or sell)
     "reserve_min_pct": 32.1,      # lowest state of charge in the day, percent of pack
     "events": ["discharged 17:00-20:00 on price 107 $/MWh", ...]}
  ],
  "totals": {"battery_usd", "gpu_usd", "gpu_hours"},
  "scaffolded_from": [...]                               # list of the sources above
}

Event strings, all derived from the hourly state:
  "charged HH:00-HH:00 on price P $/MWh"                 contiguous charge window, mean price
  "discharged HH:00-HH:00 on price P $/MWh"              contiguous discharge window, mean price
  "GPU ran a <tier> job HH:00-HH:00 at R $/h"             contiguous local job window, tier rate
  "GPU sold N hours to the marketplace at about R $/h"    sum of sell hours in the day
  "reserve floor 30% (11.8 kWh) held, low point S%"       one per day

Run:  python3 -m brain.members
"""

import json
import os
import random
from datetime import datetime, timezone

from sim import fleet, network

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
N_NODES = 40
SEED = 7
DAY_DATES = list(fleet.PRICE_DAYS)   # the three real ERCOT days the sim price series uses

SCAFFOLDED_FROM = [
    "house/cohort.json (zip, year_built, fit, guessable, confirm_with_member; address dropped)",
    "sim/network.py build(40, seed 7) for the feeder",
    "sim/fleet.py stream(40, seed 7, GPU on, sim defaults: 40% utilisation, member cap) for the hourly state; cash rules replayed per node",
    "data/ercot-dam-2026-09-07.json (lzAen, real ERCOT DAM)",
    "data/ercot-dam-2026-09-09.json (lzAen, real ERCOT DAM)",
    "data/ercot-dam-2026-09-26.json and -09-27.json (lzAen, real ERCOT DAM, Sep 26 HE1-24)",
    "grid/RATES.md for the GPU tier rates",
    "7 days = the 72 sim hours cycled: days 1-3 and 4-6 are the same 72 hours, day 7 repeats day 1",
]


def hhmm(h):
    return f"{h:02d}:00"


def windows(flags):
    """[(start_hour, end_hour_exclusive)] for runs of True in a 24-list."""
    out, start = [], None
    for h, on in enumerate(flags + [False]):
        if on and start is None:
            start = h
        elif not on and start is not None:
            out.append((start, h))
            start = None
    return out


def replay():
    """Run the sim once and return per-node per-hour cash and state for 72 hours."""
    rng = random.Random(SEED)
    net_nodes, feeders = network.build(N_NODES, rng)
    # stream() draws the price noise first, then one offset per feeder, from Random(SEED). Same order here.
    r2 = random.Random(SEED)
    fleet.price_series(r2)
    offset = {f: round(r2.uniform(0.9, 1.1), 3) for f in feeders}
    feeder_of = {n["id"]: n["feeder"] for n in net_nodes}

    hours = []            # hours[t][nid] = dict
    last_tier = {}
    for step in fleet.stream(N_NODES, SEED, network=(net_nodes, feeders), use_gpu=True):
        t, row, nodes = step["t"], step["row"], step["nodes"]
        grid = row["grid"]
        export = {}
        per = {}
        for nd in nodes:
            nid = nd.id
            f = feeder_of[nid]
            price = grid * offset[f]
            a = row["actions"].get(nid, "dead")
            g = row["gpu_actions"].get(nid, "idle")
            bat = a if a in ("charge", "discharge") else "idle"
            battery_usd = 0.0
            if bat == "discharge":
                kw = min(nd.rate_kw, fleet.FEEDER_EXPORT_KW - export.get(f, 0.0))
                export[f] = export.get(f, 0.0) + kw
                battery_usd = kw * price
            elif bat == "charge":
                battery_usd = -nd.rate_kw * price
            gpu_usd, tier = 0.0, None
            if g == "local":
                if nd.job:
                    tier, upload = nd.job[0]["tier"], nd.job[2]
                    last_tier[nid] = (tier, upload)
                else:
                    tier, upload = last_tier[nid]          # job ended this hour; 3-hour jobs always show earlier
                gpu_usd = (fleet.TIERS[tier]["rate"] - fleet.GPU_KW * grid) - upload / fleet.JOB_HOURS
            elif g == "sell":
                gpu_usd = row["gpu"] - fleet.GPU_KW * grid
            per[nid] = {"bat": bat, "gpu": g, "tier": tier, "price": price, "gpu_price": row["gpu"],
                        "battery_usd": battery_usd, "gpu_usd": gpu_usd, "soc": nd.soc}
        hours.append(per)
        result = step["result"]
    check = (round(sum(h[n]["battery_usd"] for h in hours for n in h), 2),
             round(sum(h[n]["gpu_usd"] for h in hours for n in h), 2))
    assert abs(check[0] - result["revenue_power"]) < 0.05, (check, result["revenue_power"])
    assert abs(check[1] - result["revenue_compute"]) < 0.05, (check, result["revenue_compute"])
    return hours, net_nodes, feeder_of


def day_record(day, hours, nid):
    start = ((day - 1) * 24) % fleet.INTERVALS
    hs = hours[start:start + 24]
    rows = [h[nid] for h in hs]
    events = []
    for kind, verb in (("charge", "charged"), ("discharge", "discharged")):
        for a, b in windows([r["bat"] == kind for r in rows]):
            p = sum(r["price"] for r in rows[a:b]) / (b - a) * 1000
            events.append(f"{verb} {hhmm(a)}-{hhmm(b)} on price {p:.0f} $/MWh")
    tiers = [r["tier"] for r in rows]
    for a, b in windows([r["gpu"] == "local" for r in rows]):
        # split a local run at tier changes
        s = a
        for h in range(a + 1, b + 1):
            if h == b or tiers[h] != tiers[s]:
                events.append(f"GPU ran a {tiers[s]} job {hhmm(s)}-{hhmm(h)} at {fleet.TIERS[tiers[s]]['rate']:.2f} $/h")
                s = h
    sold = [r for r in rows if r["gpu"] == "sell"]
    if sold:
        avg = sum(r["gpu_price"] for r in sold) / len(sold)
        events.append(f"GPU sold {len(sold)} hours to the marketplace at about {avg:.2f} $/h")
    low = min(r["soc"] for r in rows) * 100
    events.append(f"reserve floor {fleet.RESERVE:.0%} ({fleet.RESERVE * fleet.CAPACITY_KWH:.1f} kWh) held, low point {low:.0f}%")
    return {
        "day": day,
        "date": DAY_DATES[(day - 1) % 3],
        "sim_hours": [start, start + 23],
        "battery_usd": round(sum(r["battery_usd"] for r in rows), 2),
        "gpu_usd": round(sum(r["gpu_usd"] for r in rows), 2),
        "gpu_hours": sum(1 for r in rows if r["gpu"] in ("local", "sell")),
        "reserve_min_pct": round(low, 1),
        "events": events,
    }


def build_members():
    cohort = json.load(open(os.path.join(ROOT, "house", "cohort.json")))
    assert len(cohort) == N_NODES, len(cohort)
    hours, net_nodes, feeder_of = replay()
    members = []
    for i, house in enumerate(cohort):
        week = [day_record(d, hours, i) for d in range(1, 8)]
        members.append({
            "member_id": f"m{i + 1:03d}",
            "zip": house["zip"],
            "year_built": house["year_built"],
            "fit": house["fit"],
            "fields": {g["field"]: {"value": g["value"], "source": g["source"], "confidence": g["confidence"]}
                       for g in house["guessable"]},
            "confirm_with_member": house["confirm_with_member"],
            "node": {"nid": i, "feeder": feeder_of[i], "region": fleet.REGIONS[i % len(fleet.REGIONS)],
                     "battery_kwh": fleet.CAPACITY_KWH, "rate_kw": fleet.RATE_KW,
                     "reserve_pct": round(fleet.RESERVE * 100), "reserve_kwh": round(fleet.RESERVE * fleet.CAPACITY_KWH, 2),
                     "gpu": True},
            "week": week,
            "totals": {"battery_usd": round(sum(d["battery_usd"] for d in week), 2),
                       "gpu_usd": round(sum(d["gpu_usd"] for d in week), 2),
                       "gpu_hours": sum(d["gpu_hours"] for d in week)},
            "scaffolded_from": SCAFFOLDED_FROM,
        })
    return {"_meta": {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "rule": "joined from real sources, no invented policy",
                      "sim": {"seed": SEED, "nodes": N_NODES, "intervals": fleet.INTERVALS, "gpu": True,
                              "util": fleet.UTIL, "member_cap": fleet.MEMBER_CAP, "price_days": list(fleet.PRICE_DAYS)}},
            "members": members}


def build_questions(m):
    """10 questions for member m001 with answers computed from its record. Two are policy gaps."""
    d2 = m["week"][1]
    dis2 = [e for e in d2["events"] if e.startswith("discharged")]
    gpu_runs = [f"day {d['day']}: {e}" for d in m["week"] for e in d["events"] if e.startswith("GPU ran")]
    t = m["totals"]
    best = max(m["week"], key=lambda d: d["battery_usd"] + d["gpu_usd"])
    q = [
        ("why did my battery discharge at 5 pm on day 2",
         (f"On day 2 ({d2['date']}) your battery " + "; ".join(dis2) + ". The scheduler discharges only in the top-4 price hours of the coming day.") if dis2
         else f"Your battery did not discharge on day 2 ({d2['date']}). Events that day: " + "; ".join(d2["events"]),
         "week[1].events"),
        ("what did my node earn this week",
         f"Battery {t['battery_usd']:.2f} USD, GPU {t['gpu_usd']:.2f} USD, total {t['battery_usd'] + t['gpu_usd']:.2f} USD over 7 days.",
         "totals"),
        ("what is my reserve floor",
         f"{m['node']['reserve_pct']}% of the {m['node']['battery_kwh']} kWh pack, {m['node']['reserve_kwh']} kWh, always kept for your backup. Lowest point this week: {min(d['reserve_min_pct'] for d in m['week'])}%.",
         "node.reserve_pct, node.reserve_kwh, week[].reserve_min_pct"),
        ("which of my fields still need my confirmation",
         ", ".join(m["confirm_with_member"]) + ".",
         "confirm_with_member"),
        ("when did my GPU run a job",
         "; ".join(gpu_runs) if gpu_runs else "No local job ran this week.",
         "week[].events"),
        ("how many GPU hours did I sell or run this week",
         f"{t['gpu_hours']} hours, earning {t['gpu_usd']:.2f} USD.",
         "totals.gpu_hours, totals.gpu_usd"),
        ("which day was my best day",
         f"Day {best['day']} ({best['date']}): battery {best['battery_usd']:.2f} USD plus GPU {best['gpu_usd']:.2f} USD.",
         "week[].battery_usd, week[].gpu_usd"),
        ("what do you know about my house",
         f"Zip {m['zip']}, built {m['year_built']}, fit bucket {m['fit']['bucket']}: " + "; ".join(m["fit"]["reasons"]) + ". "
         + ", ".join(f"{k} = {v['value']} ({v['confidence']:.0%} from {v['source']})" for k, v in m["fields"].items()) + ".",
         "zip, year_built, fit, fields"),
        ("when is my next credit paid", "GAP", None),
        ("can I cancel", "GAP", None),
    ]
    return {"member_id": m["member_id"],
            "note": "expected answers are computed from data/members.json for m001; GAP = policy not in the record, the brain must say it does not know",
            "questions": [{"id": f"q{i + 1:02d}", "question": a, "expected": b, "source_field": c} for i, (a, b, c) in enumerate(q)]}


if __name__ == "__main__":
    data = build_members()
    out = os.path.join(ROOT, "data", "members.json")
    json.dump(data, open(out, "w"), indent=1)
    qs = build_questions(data["members"][0])
    json.dump(qs, open(os.path.join(HERE, "questions.json"), "w"), indent=1)
    m = data["members"][0]
    print(f"wrote {len(data['members'])} members to {os.path.normpath(out)}")
    print("m001 totals:", m["totals"])
    for d in m["week"][:2]:
        for e in d["events"]:
            print(f"  day {d['day']}: {e}")
    print("questions:", [q["question"] for q in qs["questions"]])
