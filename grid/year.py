"""A year of ERCOT DAM prices: scarcity hours, top 10 price days, battery arbitrage.

Input: data/ercot_dam_hourly_2025_2026.csv (built by grid/ercot_archive.py from ERCOT
report 13060). Battery logic: grid/earned.py simulate_day (imported, not copied), one
Base Core (39.2 kWh, 10 kW, 30% reserve kept, from sim/fleet.py), one cycle a day.

Run:
  python3 grid/year.py
Writes web/data/grid_year.json and prints the numbers used in grid/YEAR.md.
"""
import csv
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import earned  # noqa: E402  simulate_day, battery spec from sim/fleet.py

CSV = os.path.join(HERE, "..", "data", "ercot_dam_hourly_2025_2026.csv")
OUT = os.path.join(HERE, "..", "web", "data", "grid_year.json")
ZONES = ["aen", "north", "houston"]
LABEL = {"aen": "LZ_AEN", "north": "LZ_NORTH", "houston": "LZ_HOUSTON"}
THRESHOLDS = [200, 500, 1000]
SIM_DAYS = ["2026-09-07", "2026-09-09", "2026-09-26"]


def load():
    days = defaultdict(list)
    for r in csv.DictReader(open(CSV)):
        days[r["date"]].append((int(r["he"]), {z: float(r[z]) for z in ZONES}))
    return days


def sep26(zone):
    key = {"aen": "lzAen", "north": "lzNorth", "houston": "lzHouston"}[zone]
    d = json.load(open(os.path.join(HERE, "..", "data", "ercot-dam-2026-09-26.json")))
    return [(r["hourEnding"], r[key] / 1000.0) for r in d["damSppData"]]


def main():
    days = load()
    out = {"source": "ERCOT report 13060, Historical DAM Load Zone and Hub Prices",
           "battery": {"kwh": earned.CAPACITY_KWH, "kw": earned.RATE_KW, "reserve": earned.RESERVE},
           "first": min(days), "last": max(days)}

    # scarcity hours by month and zone
    scarcity = defaultdict(lambda: {z: {t: 0 for t in THRESHOLDS} for z in ZONES})
    for date, hrs in days.items():
        for _, p in hrs:
            for z in ZONES:
                for t in THRESHOLDS:
                    if p[z] > t:
                        scarcity[date[:7]][z][t] += 1
    months = sorted({d[:7] for d in days})
    out["scarcity"] = [{"month": m, **{z: scarcity[m][z] for z in ZONES}} for m in months]

    # battery per day per zone (earned.simulate_day wants $/kWh)
    net = {z: {} for z in ZONES}
    for date, hrs in days.items():
        for z in ZONES:
            net[z][date] = earned.simulate_day([(h, p[z] / 1000.0) for h, p in hrs])["net"]

    peak = {d: {z: max(p[z] for _, p in hrs) for z in ZONES} for d, hrs in days.items()}

    # top 10 price days (by LZ_AEN daily peak hour)
    top = sorted(days, key=lambda d: peak[d]["aen"], reverse=True)[:10]
    out["top10"] = [{"date": d, "peak": peak[d], "net": {z: round(net[z][d], 2) for z in ZONES},
                     "peak_he": max(days[d], key=lambda hp: hp[1]["aen"])[0]} for d in top]

    # annual $ per battery, per year, per zone; share from each zone's own top 10 price days
    years = {}
    trailing = sorted(days)[-365:]
    for y in ("2025", "2026", "trailing365"):
        ds = trailing if y == "trailing365" else [d for d in days if d.startswith(y)]
        yz = {}
        for z in ZONES:
            total = sum(net[z][d] for d in ds)
            t10 = sorted(ds, key=lambda d: peak[d][z], reverse=True)[:10]
            t10_net = sum(net[z][d] for d in t10)
            e10 = sorted(ds, key=lambda d: net[z][d], reverse=True)[:10]
            yz[z] = {"days": len(ds), "total": round(total, 2), "per_day": round(total / len(ds), 2),
                     "top10_price_days": round(t10_net, 2), "top10_share": round(t10_net / total, 3),
                     "top10_earning_days": round(sum(net[z][d] for d in e10), 2),
                     "median_day": round(sorted(net[z][d] for d in ds)[len(ds) // 2], 2),
                     "hours_over": {t: sum(1 for d in ds for _, p in days[d] if p[z] > t)
                                    for t in THRESHOLDS},
                     "max_price": max(peak[d][z] for d in ds)}
        years[y] = yz
    out["years"] = years
    out["trailing_range"] = [trailing[0], trailing[-1]]

    # battery $ by month per zone
    out["monthly"] = [{"month": m, **{z: round(sum(v for d, v in net[z].items() if d.startswith(m)), 2)
                                       for z in ZONES}} for m in months]

    # daily series for the chart: daily peak and mean per zone, and net
    out["daily"] = [{"date": d, "peak": peak[d]["aen"],
                     "mean": round(sum(p["aen"] for _, p in days[d]) / len(days[d]), 2),
                     "net": round(net["aen"][d], 2)} for d in sorted(days)]

    # the three sim days
    sim = []
    for d in SIM_DAYS:
        row = {"date": d}
        for z in ZONES:
            hrs = [(h, p[z] / 1000.0) for h, p in days[d]] if d in days else sep26(z)
            r = earned.simulate_day(hrs)
            row[z] = {"net": round(r["net"], 2), "peak": round(r["max_price"], 2)}
        sim.append(row)
    out["sim_days"] = sim

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)

    print(f"range {out['first']} to {out['last']}")
    for y, yz in years.items():
        for z, v in yz.items():
            print(f"{y} {LABEL[z]:<11} days {v['days']} total ${v['total']:.2f} (${v['per_day']}/day, "
                  f"median ${v['median_day']}) top10 price days ${v['top10_price_days']:.2f} "
                  f"= {v['top10_share']:.1%}; top10 earning days ${v['top10_earning_days']:.2f}; "
                  f"hours >200/500/1000: {v['hours_over']}; max ${v['max_price']:.2f}")
    print("\ntop 10 days by LZ_AEN peak:")
    for t in out["top10"]:
        print(f"  {t['date']} HE{t['peak_he']} peaks {t['peak']} net {t['net']}")
    print("\nscarcity by month (aen >200/500/1000 | north | houston):")
    for s in out["scarcity"]:
        if any(s[z][200] for z in ZONES):
            print(f"  {s['month']}", *[f"{LABEL[z]} {list(s[z].values())}" for z in ZONES])
    print("\nsim days:", json.dumps(sim))
    print("monthly aen:", [(m["month"], m["aen"]) for m in out["monthly"]])


if __name__ == "__main__":
    main()
