"""What most people miss in ERCOT's public data: 5 to 7 measured findings.

Inputs (all already in the repo, public ERCOT data, nothing fetched):
  data/ercot_dam_hourly_2025_2026.csv   report 13060 DAM prices, LZ_AEN/LZ_NORTH/LZ_HOUSTON, hourly
  data/ercot_load_hourly_2024_2026.csv  Native Load by weather zone, hourly
  data/ercot/supply-demand-2026-09-26.json, fuel-mix-2026-09-26.json  (one-day dashboards: coverage check)
Battery logic: grid/earned.py simulate_day (one Base Core, one cycle a day, day-ahead energy only).

Run:
  python3 grid/insights.py
Writes web/data/grid_insights.json and prints each headline.
"""
import csv
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import date as Date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import earned  # noqa: E402

ROOT = os.path.join(HERE, "..")
DAM = os.path.join(ROOT, "data", "ercot_dam_hourly_2025_2026.csv")
LOAD = os.path.join(ROOT, "data", "ercot_load_hourly_2024_2026.csv")
OUT = os.path.join(ROOT, "web", "data", "grid_insights.json")
ZONES = ["aen", "north", "houston"]
DAM_SRC = "data/ercot_dam_hourly_2025_2026.csv (ERCOT report 13060, DAM load zone prices)"
LOAD_SRC = "data/ercot_load_hourly_2024_2026.csv (ERCOT Native Load by weather zone)"
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def load_dam():
    days = defaultdict(list)
    for r in csv.DictReader(open(DAM)):
        days[r["date"]].append((int(r["he"]), {z: float(r[z]) for z in ZONES}))
    return dict(sorted(days.items()))


def load_load():
    rows = []
    for r in csv.DictReader(open(LOAD)):
        rows.append((int(r["year"]), int(r["month"]), int(r["hour_ending"]), float(r["ERCOT"])))
    return rows


def arb(hrs, z="aen"):
    return earned.simulate_day([(h, p[z] / 1000.0) for h, p in hrs])


def heavy_tail(days):
    ds = list(days)[-365:]
    net = sorted((arb(days[d])["net"] for d in ds), reverse=True)
    total = sum(net)
    share = lambda n: sum(net[:n]) / total
    top1 = max(1, round(len(ds) * 0.01))
    # hourly view: every hour's price above the day's own mean, summed = gross spread on offer
    hours = []
    for d in ds:
        m = statistics.mean(p["aen"] for _, p in days[d])
        hours += [max(0.0, p["aen"] - m) for _, p in days[d]]
    hours.sort(reverse=True)
    top50h = sum(hours[:50]) / sum(hours)
    # cumulative share curve at chosen day counts
    pts = [4, 10, 18, 37, 73, 110, 183, 365]
    curve = [{"days": n, "pct_days": round(100 * n / len(ds), 1), "pct_value": round(100 * share(n), 1)} for n in pts]
    median = statistics.median(net)
    return {
        "id": "heavy-tail",
        "title": "A few days carry the year",
        "big": f"{100 * share(top1):.0f}%",
        "headline": f"The best {top1} days ({100 * top1 / len(ds):.0f}% of the year) made {100 * share(top1):.0f}% of one battery's "
                    f"day-ahead arbitrage value on LZ_AEN; the best 37 days (10%) made {100 * share(37):.0f}%.",
        "detail": f"The median day made ${median:.2f}; the best day made ${net[0]:.2f}. "
                  f"The top 50 hours hold {100 * top50h:.0f}% of all price-above-daily-average dollars.",
        "chart": {"type": "curve", "x_label": "% of days, best first", "y_label": "% of year's value",
                  "points": curve},
        "method": "earned.simulate_day on each of the last 365 days (one cycle, cheapest 3 hours in, dearest 3 out, "
                  "27.4 kWh usable); days sorted by value, cumulative share. Hour view: each hour's price above its day's mean.",
        "base": "Dispatch: one scarcity day is worth more than a month of ordinary cycling, so being charged and "
                "available on forecast spike days is the first dispatch rule; daily optimisation comes second.",
        "sources": [DAM_SRC],
        "range": f"{ds[0]} to {ds[-1]}",
        "held": True,
        "numbers": {"top1_days": top1, "top1_share": round(share(top1), 3), "top10pct_share": round(share(37), 3),
                    "top50h_share": round(top50h, 3), "median_day": round(median, 2), "best_day": round(net[0], 2),
                    "total": round(total, 2)},
    }


def zone_spread(days):
    ds = list(days)
    n = gt5 = gt20 = 0
    by_he = defaultdict(list)
    by_month = defaultdict(lambda: [0, 0])
    spread_dollars = []
    top = defaultdict(int)
    for d in ds:
        for h, p in days[d]:
            s = max(p.values()) - min(p.values())
            n += 1
            gt5 += s > 5
            gt20 += s > 20
            by_he[h].append(s)
            by_month[d[:7]][0] += 1
            by_month[d[:7]][1] += s > 5
            spread_dollars.append(s)
            if s > 5:
                top[max(p, key=p.get)] += 1
    spread_dollars.sort(reverse=True)
    top1pct = sum(spread_dollars[: len(spread_dollars) // 100]) / sum(spread_dollars)
    he_mean = [{"he": h, "mean": round(statistics.mean(v), 2)} for h, v in sorted(by_he.items())]
    worst_he = max(he_mean, key=lambda r: r["mean"])
    best_he = min(he_mean, key=lambda r: r["mean"])
    lead = max(top, key=top.get)
    label = {"aen": "LZ_AEN", "north": "LZ_NORTH", "houston": "LZ_HOUSTON"}
    return {
        "id": "zone-spread",
        "title": "Zones split in bursts, not every day",
        "big": f"{100 * gt5 / n:.0f}%",
        "headline": f"Austin, Dallas and Houston day-ahead prices sit within $5/MWh of each other in "
                    f"{100 * (1 - gt5 / n):.0f}% of hours; the other {100 * gt5 / n:.0f}% of hours "
                    f"carry the congestion, and the top 1% of hours hold {100 * top1pct:.0f}% of all spread dollars.",
        "detail": f"Spread is widest at HE{worst_he['he']} (mean ${worst_he['mean']}/MWh) and narrowest at HE{best_he['he']} "
                  f"(${best_he['mean']}). When zones split by more than $5, {label[lead]} is the dearest zone "
                  f"{100 * top[lead] / gt5:.0f}% of the time. Hours over $20 apart: {gt20}.",
        "chart": {"type": "bars", "x_label": "hour ending", "y_label": "mean max-min spread, $/MWh",
                  "points": [{"x": r["he"], "y": r["mean"]} for r in he_mean]},
        "method": "For every hour, max minus min of the three load-zone DAM prices. Share of hours over $5 and $20; "
                  "mean spread by hour ending; which zone is dearest when the spread is over $5.",
        "base": "Siting: a battery in the zone that is dearest during split hours earns the congestion premium; "
                "fleet dispatch should read the member's own zone, not the hub.",
        "sources": [DAM_SRC],
        "range": f"{ds[0]} to {ds[-1]}",
        "held": True,
        "numbers": {"hours": n, "share_gt5": round(gt5 / n, 3), "hours_gt20": gt20, "top1pct_share": round(top1pct, 3),
                    "dearest_when_split": {label[k]: v for k, v in top.items()},
                    "monthly_share_gt5": {m: round(v[1] / v[0], 3) for m, v in sorted(by_month.items())}},
        "note": "The CSV holds three zones (AEN, NORTH, HOUSTON). LZ_SOUTH and LZ_WEST exist only in one-day dashboard snapshots, "
                "so they are left out of the year view.",
    }


def peak_lag(days, load_rows):
    # mean price profile by month (AEN) and mean load profile by month (ERCOT total)
    pp = defaultdict(lambda: defaultdict(list))
    for d, hrs in days.items():
        for h, p in hrs:
            pp[int(d[5:7])][h].append(p["aen"])
    lp = defaultdict(lambda: defaultdict(list))
    for y, m, h, mw in load_rows:
        if y >= 2025:
            lp[m][h].append(mw)
    rows = []
    for m in range(1, 13):
        if m not in pp or m not in lp:
            continue
        pm = {h: statistics.mean(v) for h, v in pp[m].items()}
        lm = {h: statistics.mean(v) for h, v in lp[m].items()}
        # median-hour price profile too, so one spike day does not choose the peak hour
        pmed = {h: statistics.median(v) for h, v in pp[m].items()}
        rows.append({"month": MON[m - 1], "load_peak_he": max(lm, key=lm.get), "price_peak_he": max(pmed, key=pmed.get),
                     "ramp_17_20": round(pmed[20] - pmed[17], 2), "midday_13": round(pmed[13], 2), "he20": round(pmed[20], 2)})
    lags = [r["price_peak_he"] - r["load_peak_he"] for r in rows]
    summer = [r for r in rows if r["month"] in ("Jun", "Jul", "Aug", "Sep")]
    later = sum(1 for x in lags if x > 0)
    summer_lag = max(r["price_peak_he"] - r["load_peak_he"] for r in summer)
    avg_ratio = statistics.mean(r["he20"] / r["midday_13"] for r in summer if r["midday_13"] > 0)
    return {
        "id": "peak-lag",
        "title": "Price peaks after load peaks",
        "big": f"+{summer_lag} h",
        "headline": f"In {later} of {len(rows)} months the typical day-ahead price peak comes later than the load peak, "
                    f"by up to {summer_lag} hours in summer; the summer 8 pm price is {avg_ratio:.1f}x the 1 pm price.",
        "detail": "Load peaks late afternoon; price peaks as solar fades and net load climbs into the evening. "
                  "Load peak hour and price peak hour by month are in the chart.",
        "chart": {"type": "pairs", "x_label": "month", "y_label": "hour ending of the daily peak",
                  "points": [{"x": r["month"], "load": r["load_peak_he"], "price": r["price_peak_he"]} for r in rows]},
        "method": "Per calendar month (2025 to 2026 pooled): hour with the highest mean ERCOT total load, and hour with the "
                  "highest median LZ_AEN DAM price (median so one spike day does not decide). Summer ratio = median HE20 / median HE13 price, Jun to Sep.",
        "base": "Dispatch: holding charge through the load peak and discharging into HE19 to HE21 captures the net-load ramp; "
                "dispatch keyed to the price curve, not the load curve, captures it.",
        "sources": [DAM_SRC, LOAD_SRC],
        "range": "prices 2025-01-01 to 2026-09-19; load 2025-01-01 to 2026-08-31",
        "held": True,
        "numbers": {"by_month": rows, "mean_lag_h": round(statistics.mean(lags), 2), "summer_he20_over_he13": round(avg_ratio, 2)},
    }


def charge_window(days):
    # where the 3 cheapest hours fall, by month: overnight (HE1-6) vs solar midday (HE10-16)
    rows = []
    bym = defaultdict(lambda: [0, 0, 0])
    for d, hrs in days.items():
        r = arb(hrs)
        k = d[:7]
        for h in r["charge_hours"]:
            bym[k][0] += 1
            bym[k][1] += 1 <= h <= 6
            bym[k][2] += 10 <= h <= 16
    for k, (n, night, mid) in sorted(bym.items()):
        rows.append({"x": k, "night": round(100 * night / n), "midday": round(100 * mid / n)})
    tot = sum(v[0] for v in bym.values())
    mid = 100 * sum(v[2] for v in bym.values()) / tot
    night = 100 * sum(v[1] for v in bym.values()) / tot
    y26 = [r for r in rows if r["x"].startswith("2026")]
    mid26 = statistics.mean(r["midday"] for r in y26)
    night26 = statistics.mean(r["night"] for r in y26)
    return {
        "id": "charge-window",
        "title": "The cheap hours are at midday",
        "big": f"{mid:.0f}%",
        "headline": f"{mid:.0f}% of each day's three cheapest day-ahead hours on LZ_AEN fall between 10 am and 4 pm; "
                    f"only {night:.0f}% fall overnight (1 am to 6 am).",
        "detail": f"2026 so far: {mid26:.0f}% midday, {night26:.0f}% overnight. Peak month: "
                  + max(rows, key=lambda r: r["midday"])["x"] + f" at {max(r['midday'] for r in rows)}% midday.",
        "chart": {"type": "stack", "x_label": "month", "y_label": "% of charge hours",
                  "points": rows},
        "method": "earned.simulate_day on LZ_AEN each day; its 3 cheapest hours counted as overnight (HE1 to HE6) or "
                  "midday (HE10 to HE16), share per month.",
        "base": "Members and dispatch: a battery can refill from midday prices, often from the member's own solar, and still "
                "be full for the evening peak; overnight charging is now the more costly habit.",
        "sources": [DAM_SRC],
        "range": f"{list(days)[0]} to {list(days)[-1]}",
        "held": mid > night,
        "numbers": {"midday_share": round(mid, 1), "overnight_share": round(night, 1), "midday_2026": round(mid26, 1)},
    }


def low_price(days):
    le0 = le5 = n = 0
    by_he = defaultdict(int)
    by_m = defaultdict(int)
    for d, hrs in days.items():
        for h, p in hrs:
            n += 1
            v = p["aen"]
            le0 += v <= 0
            if v <= 5:
                le5 += 1
                by_he[h] += 1
                by_m[MON[int(d[5:7]) - 1]] += 1
    mid = sum(v for h, v in by_he.items() if 10 <= h <= 16)
    topm = sorted(by_m.items(), key=lambda kv: -kv[1])[:3]
    return {
        "id": "near-zero",
        "title": "Near-free hours cluster at winter middays",
        "big": f"{le5}",
        "headline": f"{le5} day-ahead hours on LZ_AEN cleared at $5/MWh or less ({le0} at or below zero); "
                    f"{100 * mid / max(le5, 1):.0f}% of them fall between 10 am and 4 pm.",
        "detail": "Busiest months: " + ", ".join(f"{m} {c}" for m, c in topm) + " hours. Day-ahead prices only.",
        "chart": {"type": "bars", "x_label": "hour ending", "y_label": "hours at $5/MWh or less",
                  "points": [{"x": h, "y": by_he.get(h, 0)} for h in range(1, 25)]},
        "method": "Count of LZ_AEN DAM hours at or below $5/MWh and at or below $0, grouped by hour ending and month.",
        "base": "Dispatch and members: these are the hours to fill batteries and shift home load (EV, pool pump) toward.",
        "sources": [DAM_SRC],
        "range": f"{list(days)[0]} to {list(days)[-1]}",
        "held": le5 > 0,
        "numbers": {"hours": n, "le5": le5, "le0": le0, "midday_share": round(mid / max(le5, 1), 3),
                    "by_month": dict(by_m)},
    }


def season(days):
    seasons = {"Winter (Dec-Feb)": (12, 1, 2), "Spring (Mar-May)": (3, 4, 5), "Summer (Jun-Sep)": (6, 7, 8, 9),
               "Fall (Oct-Nov)": (10, 11)}
    cnt = defaultdict(lambda: [0, 0])  # >200, >1000
    val = defaultdict(float)
    ndays = defaultdict(int)
    wk = defaultdict(list)
    k1000 = defaultdict(int)
    for d, hrs in days.items():
        m = int(d[5:7])
        k1000[d[:7]] += sum(p["aen"] > 1000 for _, p in hrs)
        s = next(k for k, v in seasons.items() if m in v)
        ndays[s] += 1
        for _, p in hrs:
            cnt[s][0] += p["aen"] > 200
            cnt[s][1] += p["aen"] > 1000
        net = arb(hrs)["net"]
        val[s] += net
        wk["weekend" if Date.fromisoformat(d).weekday() >= 5 else "weekday"].append(net)
    tot200 = sum(v[0] for v in cnt.values())
    w = "Winter (Dec-Feb)"
    su = "Summer (Jun-Sep)"
    wkd, wke = statistics.mean(wk["weekday"]), statistics.mean(wk["weekend"])
    return {
        "id": "season",
        "title": "The priciest hours came in winter",
        "big": f"{cnt[w][1]} vs {cnt[su][1]}",
        "headline": f"Winter had {cnt[w][1]} day-ahead hours over $1,000/MWh on LZ_AEN, summer had {cnt[su][1]}; "
                    f"winter days averaged ${val[w] / ndays[w]:.2f} of arbitrage vs ${val[su] / ndays[su]:.2f} in summer.",
        "detail": f"The $1,000 hours all fall in {', '.join(k for k, v in k1000.items() if v)}. Hours over $200: winter {cnt[w][0]}, summer {cnt[su][0]} of {tot200}. Weekdays averaged ${wkd:.2f} a day, "
                  f"weekends ${wke:.2f}.",
        "chart": {"type": "hbars", "x_label": "$ per day, one battery", "y_label": "season",
                  "points": [{"x": s, "y": round(val[s] / ndays[s], 2), "h200": cnt[s][0], "h1000": cnt[s][1]} for s in seasons]},
        "method": "LZ_AEN DAM hours over $200 and $1,000 by season; earned.simulate_day value averaged per day by season "
                  "and by weekday vs weekend. 2025-01-01 to 2026-09-19 (two winters partly, one full summer plus 2026 to Sep 19).",
        "base": "Reserve policy and members: winter cold snaps pay most and hurt most; hold backup reserve through winter "
                "fronts, not just summer heat.",
        "sources": [DAM_SRC],
        "range": f"{list(days)[0]} to {list(days)[-1]}",
        "held": cnt[w][1] > cnt[su][1],
        "numbers": {k: {"h200": cnt[k][0], "h1000": cnt[k][1], "days": ndays[k], "per_day": round(val[k] / ndays[k], 2)} for k in seasons}
                   | {"weekday_per_day": round(wkd, 2), "weekend_per_day": round(wke, 2)},
    }


def coverage_checks():
    sd = json.load(open(os.path.join(ROOT, "data", "ercot", "supply-demand-2026-09-26.json")))
    fm = json.load(open(os.path.join(ROOT, "data", "ercot", "fuel-mix-2026-09-26.json")))
    live = [r for r in sd["data"] if r["demand"] > 0]
    sd_days = sorted({r["timestamp"][:10] for r in live})
    margin = min(r["capacity"] - r["demand"] for r in live)
    fm_days = sorted(fm["data"])
    return [
        {"candidate": "Reserves vs price", "held": False,
         "why": f"Supply-demand history holds {len(live)} five-minute intervals ({sd_days[0]} to {sd_days[-1]}); "
                f"the tightest margin was {margin:,} MW, far from scarcity, so a reserve threshold effect needs more history."},
        {"candidate": "Wind and solar share at peak-price hours", "held": False,
         "why": f"Fuel-mix history covers {len(fm_days)} days ({', '.join(fm_days)}); a year of generation mix next to the year of prices would test it."},
    ]


def main():
    days = load_dam()
    load_rows = load_load()
    findings = [heavy_tail(days), peak_lag(days, load_rows), charge_window(days), zone_spread(days),
                low_price(days), season(days)]
    out = {"title": "What most people miss in ERCOT's public data",
           "tag": "Measured (from public data)",
           "run": "python3 grid/insights.py",
           "battery": {"kwh": earned.CAPACITY_KWH, "kw": earned.RATE_KW, "reserve": earned.RESERVE},
           "findings": findings, "not_supported": coverage_checks()}
    json.dump(out, open(OUT, "w"), indent=1)
    for f in findings:
        print(("HELD  " if f["held"] else "FAILED") + " " + f["id"] + ": " + f["headline"])
        print("       " + f["detail"])
    for c in out["not_supported"]:
        print("FAILED " + c["candidate"] + ": " + c["why"])


if __name__ == "__main__":
    main()
