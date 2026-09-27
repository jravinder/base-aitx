"""Signal layer: evaluate rules on data/fleet.db, store what fires, write web/data/signals.json. Stdlib only.

Each rule states its threshold here and in the JSON. Each fired signal has a one-line message and a
replayable source (Socrata URL, file path, or NWS URL). A rule fires only when the store has the data
to support it; when data is missing, the rule reports "no data" and fires nothing.

  python3 store/build.py --incremental && python3 store/signals.py
"""

import glob
import gzip
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DB = os.path.join(ROOT, "data", "fleet.db")
OUT = os.path.join(ROOT, "web", "data", "signals.json")
NWS_DIR = os.path.join(ROOT, "data", "live", "nws")
NWS_URL = "https://api.weather.gov/alerts/active?zone=TXC453,TXC491"  # Travis, Williamson county zones
NWS_UA = "base-fleet signals (github.com/jravinder/base-aitx)"
SODA = "https://data.austintexas.gov/resource/3syk-w9eu.json"
BACKUP = ("generator", "battery", "solar_battery")

# Thresholds. Change them here; the JSON rule list is built from this table.
BASE_WEEK_HIGH, BASE_WEEK_LOW = 1.5, 0.5
ZIP_SURGE_MULT, ZIP_SURGE_MIN = 3.0, 5
PRICE_SPIKE = 200.0          # $/MWh, LZ_AEN day-ahead or real-time
LOW_PRC_MW = 3000.0          # ERCOT conservation threshold on physical responsive capability

RULES = [
    {"name": "base_week", "threshold": f"over {BASE_WEEK_HIGH}x or under {BASE_WEEK_LOW}x",
     "rule": "Base permits issued in the last 7 days vs the mean of the 4 prior weeks. Window ends on the newest issue_date in the mirror.",
     "source": "permits (data/mirror/energy_permits.csv.gz, Socrata 3syk-w9eu)"},
    {"name": "zip_surge", "threshold": f"over {ZIP_SURGE_MULT:g}x, min {ZIP_SURGE_MIN} permits",
     "rule": "A zip's backup permits (generator, battery, solar_battery) in the last 30 days vs its trailing 12-month monthly mean.",
     "source": "permits (data/mirror/energy_permits.csv.gz, Socrata 3syk-w9eu)"},
    {"name": "price_spike", "threshold": f"over ${PRICE_SPIKE:,.0f}/MWh",
     "rule": "LZ_AEN day-ahead or real-time settlement point price in the newest system-wide-prices snapshot.",
     "source": "dam_prices, rt_prices (ERCOT system-wide-prices dashboard)"},
    {"name": "low_reserves", "threshold": f"under {LOW_PRC_MW:,.0f} MW",
     "rule": "Physical responsive capability in the newest daily-prc snapshot (ERCOT conservation threshold).",
     "source": "prc (ERCOT daily-prc dashboard)"},
    {"name": "storm_alert", "threshold": "any active alert",
     "rule": "National Weather Service active alerts for Travis (TXC453) and Williamson (TXC491) counties.",
     "source": NWS_URL},
]


def soda(where):
    return SODA + "?" + urllib.parse.urlencode({"$select": "count(*)", "$where": where}, quote_via=urllib.parse.quote)


def day(s):
    return date.fromisoformat(s[:10])


# ---------- rules. Each returns (evaluation, [signals]) ----------

def base_week(con):
    newest = con.execute("SELECT max(issue_date) FROM permits WHERE is_base=1").fetchone()[0]
    anchor = con.execute("SELECT max(issue_date) FROM permits").fetchone()[0]
    if not newest or not anchor:
        return {"value": None, "note": "no Base permits in the store"}, []
    end = day(anchor)
    def n(a, b):  # permits issued a < date <= b
        return con.execute("SELECT count(*) FROM permits WHERE is_base=1 AND issue_date>? AND issue_date<=?",
                           (a.isoformat(), b.isoformat())).fetchone()[0]
    last = n(end - timedelta(days=7), end)
    prior = [n(end - timedelta(days=7 * (k + 1)), end - timedelta(days=7 * k)) for k in range(1, 5)]
    mean = sum(prior) / 4
    ev = {"value": last, "baseline": round(mean, 1), "window": f"{end - timedelta(days=6)} to {end}",
          "prior_weeks": prior}
    if mean == 0:
        ev["note"] = "prior 4 weeks had no Base permits; ratio undefined"
        return ev, []
    ratio = last / mean
    ev["ratio"] = round(ratio, 2)
    if BASE_WEEK_LOW <= ratio <= BASE_WEEK_HIGH:
        return ev, []
    word = "up" if ratio > 1 else "down"
    where = (f"contractor_company_name='Base Power' AND issue_date > '{end - timedelta(days=7)}' "
             f"AND issue_date <= '{end}T23:59:59'")
    return ev, [{"name": "base_week", "fired_at": end.isoformat(), "zip": "", "value": last,
                 "threshold": BASE_WEEK_HIGH if ratio > 1 else BASE_WEEK_LOW,
                 "severity": "watch" if ratio > 1 else "info",
                 "message": f"Base issued {last} permits in the 7 days to {end}, {word} to {ratio:.2f}x the 4-week mean of {mean:.1f}.",
                 "source_query": soda(where)}]


def zip_surge(con):
    anchor = con.execute("SELECT max(issue_date) FROM permits").fetchone()[0]
    if not anchor:
        return {"value": None, "note": "no permits in the store"}, []
    end = day(anchor)
    w0 = end - timedelta(days=30)
    y0 = w0 - timedelta(days=365)
    q = ",".join("?" * len(BACKUP))
    recent = dict(con.execute(f"SELECT zip, count(*) FROM permits WHERE category IN ({q}) AND issue_date>? AND issue_date<=? "
                              "AND zip<>'' AND is_base=0 GROUP BY zip", (*BACKUP, w0.isoformat(), end.isoformat())))
    trail = dict(con.execute(f"SELECT zip, count(*) FROM permits WHERE category IN ({q}) AND issue_date>? AND issue_date<=? "
                             "AND zip<>'' AND is_base=0 GROUP BY zip", (*BACKUP, y0.isoformat(), w0.isoformat())))
    out = []
    for z, n in sorted(recent.items()):
        mean = trail.get(z, 0) / 12
        if n >= ZIP_SURGE_MIN and (mean == 0 or n > ZIP_SURGE_MULT * mean):
            # Socrata has no category field; the replay filters on work class and description words.
            where = (f"original_zip='{z}' AND issue_date > '{w0}' AND issue_date <= '{end}T23:59:59' AND "
                     "(work_class='Auxiliary Power' OR upper(description) like '%BATTER%' OR upper(description) like '%GENERATOR%') "
                     "AND contractor_company_name<>'Base Power'")
            out.append({"name": "zip_surge", "fired_at": end.isoformat(), "zip": z, "value": n,
                        "threshold": round(ZIP_SURGE_MULT * mean, 1), "severity": "watch",
                        "message": (f"Zip {z}: {n} backup permits in the 30 days to {end}, "
                                    + (f"{n / mean:.1f}x its 12-month monthly mean of {mean:.1f}." if mean
                                       else "none in the 12 months before.")),
                        "source_query": soda(where)})
    ev = {"value": len(out), "window": f"{w0 + timedelta(days=1)} to {end}", "zips_checked": len(recent),
          "unit": "zips over threshold"}
    return ev, out


def price_spike(con):
    snap = con.execute("SELECT path, last_updated FROM snapshots WHERE feed='system-wide-prices' "
                       "AND body LIKE '%rtSppData%' ORDER BY last_updated DESC LIMIT 1").fetchone()
    if not snap:
        return {"value": None, "note": "no system-wide-prices snapshot"}, []
    path, lu = snap
    dam = con.execute("SELECT date, he, price FROM dam_prices WHERE point='LZ_AEN' AND source=? ORDER BY price DESC LIMIT 1",
                      (path,)).fetchone()
    rt = con.execute("SELECT ts, price FROM rt_prices WHERE point='LZ_AEN' AND source=? ORDER BY price DESC LIMIT 1",
                     (path,)).fetchone()
    ev = {"value": max(x for x in (dam and dam[2], rt and rt[1]) if x is not None), "unit": "$/MWh",
          "dam_max": dam and {"date": dam[0], "he": dam[1], "price": dam[2]},
          "rt_max": rt and {"ts": rt[0], "price": rt[1]}, "snapshot": path, "as_of": lu}
    out = []
    if dam and dam[2] > PRICE_SPIKE:
        out.append({"name": "price_spike", "fired_at": f"{dam[0]}T{dam[1]:02d}", "zip": "", "value": dam[2],
                    "threshold": PRICE_SPIKE, "severity": "high" if dam[2] > 1000 else "watch",
                    "message": f"LZ_AEN day-ahead ${dam[2]:,.2f}/MWh for {dam[0]} HE{dam[1]}, over ${PRICE_SPIKE:,.0f}.",
                    "source_query": path})
    if rt and rt[1] > PRICE_SPIKE:
        out.append({"name": "price_spike", "fired_at": rt[0], "zip": "", "value": rt[1],
                    "threshold": PRICE_SPIKE, "severity": "high" if rt[1] > 1000 else "watch",
                    "message": f"LZ_AEN real-time ${rt[1]:,.2f}/MWh at {rt[0][:16]}, over ${PRICE_SPIKE:,.0f}.",
                    "source_query": path})
    return ev, out


def low_reserves(con):
    r = con.execute("SELECT ts, prc_mw, source FROM prc ORDER BY ts DESC LIMIT 1").fetchone()
    if not r:
        return {"value": None, "note": "no daily-prc snapshot"}, []
    ts, mw, src = r
    ev = {"value": mw, "unit": "MW", "as_of": ts, "snapshot": src}
    if mw >= LOW_PRC_MW:
        return ev, []
    return ev, [{"name": "low_reserves", "fired_at": ts, "zip": "", "value": mw, "threshold": LOW_PRC_MW,
                 "severity": "high", "message": f"ERCOT physical responsive capability {mw:,.0f} MW at {ts[:16]}, under {LOW_PRC_MW:,.0f} MW.",
                 "source_query": src}]


def nws_pull():
    """Newest raw NWS file in data/live/nws/ if under 2 h old, else fetch and save one."""
    files = sorted(glob.glob(os.path.join(NWS_DIR, "*.json.gz")))
    if files and (datetime.now().timestamp() - os.path.getmtime(files[-1])) < 7200:
        with gzip.open(files[-1], "rt") as f:
            return json.load(f), os.path.relpath(files[-1], ROOT)
    req = urllib.request.Request(NWS_URL, headers={"User-Agent": NWS_UA, "Accept": "application/geo+json"})
    body = urllib.request.urlopen(req, timeout=30).read()
    os.makedirs(NWS_DIR, exist_ok=True)
    p = os.path.join(NWS_DIR, datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ") + ".json.gz")
    with gzip.open(p, "wb") as f:
        f.write(body)
    return json.loads(body), os.path.relpath(p, ROOT)


def storm_alert(con):
    try:
        d, raw = nws_pull()
    except Exception as e:  # network down: no data, fire nothing
        return {"value": None, "note": f"NWS fetch failed: {e}"}, []
    con.execute("""CREATE TABLE IF NOT EXISTS nws_alerts (id TEXT PRIMARY KEY, event TEXT, severity TEXT, onset TEXT,
                   expires TEXT, area TEXT, headline TEXT, link TEXT, raw TEXT)""")
    out = []
    for f in d.get("features", []):
        p = f.get("properties", {})
        link = p.get("@id") or f.get("id") or NWS_URL
        con.execute("INSERT OR REPLACE INTO nws_alerts VALUES (?,?,?,?,?,?,?,?,?)",
                    (p.get("id") or link, p.get("event"), p.get("severity"), p.get("onset") or p.get("effective"),
                     p.get("expires") or p.get("ends"), p.get("areaDesc"), p.get("headline"), link, raw))
        sev = {"Extreme": "high", "Severe": "high", "Moderate": "watch"}.get(p.get("severity"), "info")
        out.append({"name": "storm_alert", "fired_at": p.get("sent") or p.get("onset") or d.get("updated"), "zip": "",
                    "value": None, "threshold": None, "severity": sev,
                    "message": (f"NWS {p.get('event')} ({p.get('severity')}) for {p.get('areaDesc')}, "
                                f"onset {(p.get('onset') or '')[:16]}, expires {(p.get('expires') or '')[:16]}."),
                    "source_query": link,
                    "detail": {"event": p.get("event"), "severity": p.get("severity"), "onset": p.get("onset"),
                               "expires": p.get("expires"), "link": link}})
    return {"value": len(out), "unit": "active alerts", "as_of": d.get("updated"), "raw": raw}, out


def main():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, fired_at TEXT,
                   zip TEXT, value REAL, threshold REAL, severity TEXT, message TEXT, source_query TEXT,
                   detected_at TEXT, UNIQUE (name, zip, fired_at, source_query))""")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rules, fired = [], []
    for rule in RULES:
        fn = globals()[rule["name"]]
        try:
            ev, sigs = fn(con)
        except Exception as e:
            ev, sigs = {"value": None, "note": f"error: {e}"}, []
        rules.append({**rule, "now": ev, "fired_now": len(sigs)})
        for s in sigs:
            con.execute("INSERT OR IGNORE INTO signals (name, fired_at, zip, value, threshold, severity, message, "
                        "source_query, detected_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (s["name"], s["fired_at"], s["zip"], s["value"], s["threshold"], s["severity"], s["message"],
                         s["source_query"], now))
        fired += sigs
    con.commit()
    cols = ["id", "name", "fired_at", "zip", "value", "threshold", "severity", "message", "source_query", "detected_at"]
    latest = [dict(zip(cols, r)) for r in con.execute(
        f"SELECT {','.join(cols)} FROM signals ORDER BY detected_at DESC, fired_at DESC, id DESC LIMIT 50")]
    data = {"built_at": now, "db": "data/fleet.db", "rules": rules, "fired_now": len(fired), "latest": latest}
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
    print(f"{os.path.relpath(OUT, ROOT)}: {len(fired)} fired now, {len(latest)} in latest")
    for r in rules:
        print(f"  {r['name']:13s} fired {r['fired_now']}  now={json.dumps(r['now'], default=str)[:160]}")
    for s in fired:
        print("   -", s["message"])


if __name__ == "__main__":
    main()
