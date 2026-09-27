"""Build web/data/grid_today.json and web/data/grid_load.json for web/grid.html.

Today: for each ERCOT dashboard feed, read the newest hourly snapshot in
data/live/ercot/<feed>/<UTC stamp>.json.gz (saved by collect/ercot_feeds.sh). When a feed has
no snapshot, read the newest data/ercot/<feed>-<date>.json (saved by grid/ercot_system.js).
Load: data/ercot_load_hourly_2024_2026.csv (see grid/LOAD.md).

Run:
  python3 grid/today.py
collect/ercot_feeds.sh runs it after each hourly pull.
"""
import csv
import glob
import gzip
import json
import os
from collections import defaultdict
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
LIVE = os.path.join(ROOT, "data", "live", "ercot")
SRC = os.path.join(ROOT, "data", "ercot")
OUT = os.path.join(ROOT, "web", "data", "grid_today.json")
LOAD_CSV = os.path.join(ROOT, "data", "ercot_load_hourly_2024_2026.csv")
LOAD_OUT = os.path.join(ROOT, "web", "data", "grid_load.json")
CONSERVATION_PRC_MW = 3000   # ERCOT asks for conservation when PRC falls under this
WINDOW_HE = (17, 20)         # hour ending 17 to 20 = 16:00 to 20:00, the stress window in grid/LOAD.md

sys.path.insert(0, HERE)
import earned  # noqa: E402  one battery rule for the page and grid/earned.py

# ERCOT field -> settlement point name, in the order the tile grid shows them.
POINTS = [("lzAen", "LZ_AEN"), ("lzCps", "LZ_CPS"), ("lzHouston", "LZ_HOUSTON"), ("lzLcra", "LZ_LCRA"),
          ("lzNorth", "LZ_NORTH"), ("lzRaybn", "LZ_RAYBN"), ("lzSouth", "LZ_SOUTH"), ("lzWest", "LZ_WEST"),
          ("hbHouston", "HB_HOUSTON"), ("hbNorth", "HB_NORTH"), ("hbPan", "HB_PAN"), ("hbSouth", "HB_SOUTH"),
          ("hbWest", "HB_WEST"), ("hbBusAvg", "HB_BUSAVG"), ("hbHubAvg", "HB_HUBAVG")]


def newest(feed):
    """Return (data, source) for the newest copy of one feed, or (None, None)."""
    for p in sorted(glob.glob(os.path.join(LIVE, feed, "*.json.gz")), reverse=True):
        try:
            with gzip.open(p, "rt") as f:
                return json.load(f), os.path.relpath(p, ROOT)
        except (OSError, ValueError):
            continue
    files = sorted(glob.glob(os.path.join(SRC, f"{feed}-*.json")))
    if files:
        return json.load(open(files[-1])), os.path.relpath(files[-1], ROOT)
    return None, None


def iso(ts):
    """'2026-09-26 16:11:00-0500' -> '2026-09-26T16:11:00-05:00'."""
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S%z").isoformat()


def hhmm(ts):
    return ts[11:16]


def build_today():
    out, sources = {}, {}

    p, sources["system-wide-prices"] = newest("system-wide-prices")
    out["date"] = p["damSppData"][0]["timestamp"][:10]
    out["prices"] = {
        "updated": iso(p["lastUpdated"]),
        "points": [n for _, n in POINTS],
        "dam": [{"he": r["hourEnding"], **{n: r.get(k) for k, n in POINTS}} for r in p["damSppData"]],
        "rt": [{"t": r["intervalEnding"], **{n: r.get(k) for k, n in POINTS}} for r in p["rtSppData"]]}

    sd, sources["supply-demand"] = newest("supply-demand")
    # rows with forecast=0 are measured; forecast=1 rows are ERCOT's forecast for the rest of today
    actual = [r for r in sd["data"] if r["demand"] and not r.get("forecast")]
    rest = [r for r in sd["data"] if r["demand"] and r.get("forecast") and r["timestamp"][:10] == out["date"]]
    keep = actual[::3] + ([actual[-1]] if (len(actual) - 1) % 3 else [])
    out["supply_demand"] = {
        "updated": iso(sd["lastUpdated"]),
        "actual": [{"t": hhmm(r["timestamp"]), "cap": r["capacity"], "dem": r["demand"]} for r in keep],
        "rest_of_today": [{"t": hhmm(r["timestamp"]), "cap": r["capacity"], "dem": r["demand"]} for r in rest[::3]],
        "forecast": [{"date": r["deliveryDate"], "he": r["hourEnding"], "cap": r["availCapGen"],
                      "dem": r["forecastedDemand"]} for r in sd["forecast"]]}

    fm, sources["fuel-mix"] = newest("fuel-mix")
    day = fm["data"].get(out["date"]) or fm["data"][max(fm["data"])]
    stamps = sorted(day)
    gen = {ts: {k: round(v["gen"]) for k, v in day[ts].items()} for ts in stamps}
    out["fuel_mix"] = {"updated": iso(fm["lastUpdated"]), "at": iso(stamps[-1]), "now": gen[stamps[-1]],
                       "series": [{"t": hhmm(ts), **gen[ts]} for ts in stamps[::3]]}

    # net load = demand minus wind and solar, at the 15 min demand points
    ws_at = {hhmm(ts): g.get("Wind", 0) + g.get("Solar", 0) for ts, g in gen.items()}
    out["net_load"] = [{"t": r["t"], "load": r["dem"], "ws": ws_at[r["t"]], "net": r["dem"] - ws_at[r["t"]]}
                       for r in out["supply_demand"]["actual"] if r["t"] in ws_at]

    prc, sources["daily-prc"] = newest("daily-prc")
    if prc:
        c = prc["current_condition"]
        out["conditions"] = {"title": c["title"], "note": c["condition_note"], "eea": c["eea_level"],
                             "prc_mw": int(str(c["prc_value"]).replace(",", "")),
                             "updated": iso(prc["lastUpdated"]),
                             "prc": [{"t": hhmm(r["timestamp"]), "mw": r["prc"]} for r in prc["data"]][::30]}

    ws, sources["combine-wind-solar"] = newest("combine-wind-solar")
    if ws:
        out["wind_solar"] = [{"he": r["hourEnding"], "wind": r.get("actualWind"), "solar": r.get("actualSolar"),
                              "wind_fc": r.get("stwpf"), "solar_fc": r.get("stppf") or r.get("copHslSolar")}
                             for r in ws["currentDay"]["data"].values()]

    go, sources["generation-outages"] = newest("generation-outages")
    if go:
        cur = go["current"][sorted(go["current"])[-1]]
        out["outages"] = {"at": cur["deliveryTime"], "total_mw": cur["Combined"]["total"],
                          "unplanned_mw": cur["Combined"]["unplanned"], "planned_mw": cur["Combined"]["planned"]}

    es, sources["energy-storage-resources"] = newest("energy-storage-resources")
    if es:
        out["storage_now_mw"] = round(es["currentDay"]["data"][-1]["netOutput"])

    a, sources["ancillary-services"] = newest("ancillary-services")
    if a:
        out["ancillary"] = {"rrs": a["lastRrs"], "ecrs": a["lastEcrs"], "nsrs": a["lastNsrs"],
                            "frequency": a["data"][-1]["currentFrequency"]}

    w, sources["weather-forecast"] = newest("weather-forecast")
    if w:
        aus = w[0]["data"]["Austin"]
        out["weather_austin"] = {k: aus[k] for k in ("low", "high", "low15yr", "high15yr")}

    out["battery"] = battery_plan(out["prices"]["dam"], "LZ_AEN")
    out["conservation_prc_mw"] = CONSERVATION_PRC_MW

    out["as_of"] = max(out["prices"]["updated"], out["supply_demand"]["updated"], out["fuel_mix"]["updated"])
    out["sources"] = {k: v for k, v in sources.items() if v}
    return out


def battery_plan(dam, zone):
    """Today's plan for one Base Core battery, with the grid/earned.py rule on day-ahead prices:
    charge in the cheapest hours, discharge in the priciest hours, keep the member reserve."""
    r = earned.simulate_day([(h["he"], h[zone] / 1000.0) for h in dam if h.get(zone) is not None])
    return {"zone": zone, "kwh": earned.CAPACITY_KWH, "kw": earned.RATE_KW, "reserve": earned.RESERVE,
            "hours_per_window": earned.HOURS_PER_WINDOW, "kwh_per_hour": round(earned.KWH_PER_HOUR, 2),
            "charge_he": r["charge_hours"], "discharge_he": r["discharge_hours"],
            "charge_cost": round(r["charge_cost"], 2), "discharge_revenue": round(r["discharge_revenue"], 2),
            "net": round(r["net"], 2),
            "rule": f"Day-ahead plan from grid/earned.py: charge in the {earned.HOURS_PER_WINDOW} cheapest hours, "
                    f"discharge in the {earned.HOURS_PER_WINDOW} priciest hours, one cycle a day, "
                    f"{earned.RESERVE:.0%} of the {earned.CAPACITY_KWH} kWh always kept for the member's backup."}


def build_load():
    rows = list(csv.DictReader(open(LOAD_CSV)))
    zones = [("SCENT", "SCENT (Austin)"), ("NCENT", "NCENT (DFW)"), ("COAST", "COAST (Houston)"),
             ("ERCOT", "ERCOT total")]
    by_year = defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)
    years = sorted(by_year)
    out = {"source": "ERCOT Native Load hourly, data/ercot_load_hourly_2024_2026.csv",
           "last": rows[-1]["datetime"], "zones": [n for _, n in zones], "years": years}

    out["peaks"] = []
    for y in years:
        row = {"year": y}
        for z, n in zones:
            r = max(by_year[y], key=lambda r: float(r[z]))
            row[n] = {"mw": round(float(r[z])), "at": r["datetime"]}
        out["peaks"].append(row)

    # top 100 ERCOT-total hours per year: hour-ending histogram, and the count in HE17 to HE20 (16:00 to 20:00)
    out["top100"] = []
    for y in years:
        top = sorted(by_year[y], key=lambda r: float(r["ERCOT"]), reverse=True)[:100]
        he = [0] * 24
        for r in top:
            he[int(r["hour_ending"]) - 1] += 1
        out["top100"].append({"year": y, "by_he": he, "window": sum(he[WINDOW_HE[0] - 1:WINDOW_HE[1]])})
    top = sorted(rows, key=lambda r: float(r["ERCOT"]), reverse=True)[:100]
    he = [0] * 24
    for r in top:
        he[int(r["hour_ending"]) - 1] += 1
    out["window_he"] = list(WINDOW_HE)
    out["top100_pooled"] = {"years": f"{years[0]} to {years[-1]}", "by_he": he,
                            "window": sum(he[WINDOW_HE[0] - 1:WINDOW_HE[1]])}

    # mean ERCOT load by hour ending, July and August, per year
    out["summer_profile"] = []
    for y in years:
        s, n = [0.0] * 24, [0] * 24
        for r in by_year[y]:
            if r["month"] in ("7", "8"):
                h = int(r["hour_ending"]) - 1
                s[h] += float(r["ERCOT"])
                n[h] += 1
        out["summer_profile"].append({"year": y, "mw": [round(s[i] / n[i]) if n[i] else None for i in range(24)]})
    return out


def main():
    today = build_today()
    json.dump(today, open(OUT, "w"))
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB) for {today['date']}, as of {today['as_of']}")
    print("sources:", json.dumps(today["sources"]))
    load = build_load()
    json.dump(load, open(LOAD_OUT, "w"))
    print(f"wrote {LOAD_OUT} ({os.path.getsize(LOAD_OUT) // 1024} KB), top 100 hours in 16:00 to 20:00:",
          [(t["year"], t["window"]) for t in load["top100"]])


if __name__ == "__main__":
    main()
