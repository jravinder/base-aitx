"""Build data/fleet.db: one SQLite store for the files the collectors write. Stdlib only.

Tables and sources:
  permits         data/mirror/energy_permits.csv.gz (house/mirror.py)
  dam_prices      data/ercot_dam_hourly_2025_2026.csv, plus damSppData in data/ercot-dam-*.json,
                  data/ercot/system-wide-prices-*.json and data/live/ercot/system-wide-prices/*.json.gz
  rt_prices       rtSppData (15 min settlement point prices) in the same snapshot files
  load_hourly     data/ercot_load_hourly_2024_2026.csv
  fuel_mix        fuel-mix snapshots (data/live/ercot/fuel-mix, data/ercot/fuel-mix-*.json)
  supply_demand   supply-demand snapshots (measured rows only, forecast=0)
  prc             daily-prc snapshots: physical responsive capability, MW
  conditions      daily-prc current_condition per snapshot
  snapshots       every ERCOT dashboard snapshot file, raw JSON body (for replay and page feeds)
  demographics    data/demographics.json (ACS 5-year)
  territory       house/territory.py ZIP_TABLE plus data/ptc_tdu.json plan counts
  collector_runs  data/live/collect.log
  judgments       typed guesses with confidence and route (store/judgments.py)
  loaded_files    path and mtime of each file loaded (for --incremental)

Natural keys make every load an upsert, so a run twice gives the same rows.

  python3 store/build.py                 rebuild from zero
  python3 store/build.py --incremental   load only files that are new or changed since the last run
"""

import argparse
import csv
import glob
import gzip
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DB = os.path.join(ROOT, "data", "fleet.db")
sys.path.insert(0, ROOT)

# ERCOT field -> settlement point name (same list as grid/today.py)
POINTS = {"lzAen": "LZ_AEN", "lzCps": "LZ_CPS", "lzHouston": "LZ_HOUSTON", "lzLcra": "LZ_LCRA",
          "lzNorth": "LZ_NORTH", "lzRaybn": "LZ_RAYBN", "lzSouth": "LZ_SOUTH", "lzWest": "LZ_WEST",
          "hbHouston": "HB_HOUSTON", "hbNorth": "HB_NORTH", "hbPan": "HB_PAN", "hbSouth": "HB_SOUTH",
          "hbWest": "HB_WEST", "hbBusAvg": "HB_BUSAVG", "hbHubAvg": "HB_HUBAVG"}
CSV_POINTS = {"aen": "LZ_AEN", "north": "LZ_NORTH", "houston": "LZ_HOUSTON"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS permits (permit_number TEXT PRIMARY KEY, issue_date TEXT, applied_date TEXT, zip TEXT,
  lat REAL, lon REAL, category TEXT, contractor TEXT, is_base INTEGER, work_class TEXT, status TEXT);
CREATE INDEX IF NOT EXISTS permits_issue ON permits(issue_date);
CREATE INDEX IF NOT EXISTS permits_zip ON permits(zip);
CREATE TABLE IF NOT EXISTS dam_prices (date TEXT, he INTEGER, point TEXT, price REAL, source TEXT,
  PRIMARY KEY (date, he, point));
CREATE TABLE IF NOT EXISTS rt_prices (ts TEXT, point TEXT, price REAL, source TEXT, PRIMARY KEY (ts, point));
CREATE TABLE IF NOT EXISTS load_hourly (date TEXT, he INTEGER, scent REAL, ncent REAL, coast REAL, ercot REAL,
  PRIMARY KEY (date, he));
CREATE TABLE IF NOT EXISTS fuel_mix (ts TEXT, fuel TEXT, gen_mw REAL, source TEXT, PRIMARY KEY (ts, fuel));
CREATE TABLE IF NOT EXISTS supply_demand (ts TEXT PRIMARY KEY, capacity_mw REAL, demand_mw REAL, source TEXT);
CREATE TABLE IF NOT EXISTS prc (ts TEXT PRIMARY KEY, prc_mw REAL, source TEXT);
CREATE TABLE IF NOT EXISTS conditions (last_updated TEXT PRIMARY KEY, title TEXT, state TEXT, eea_level INTEGER,
  prc_mw REAL, note TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS snapshots (path TEXT PRIMARY KEY, feed TEXT, last_updated TEXT, body TEXT);
CREATE INDEX IF NOT EXISTS snapshots_feed ON snapshots(feed, last_updated);
CREATE TABLE IF NOT EXISTS demographics (zip TEXT PRIMARY KEY, households INTEGER, owner_occupied INTEGER,
  single_family_detached INTEGER, median_year_built INTEGER, median_income INTEGER, median_home_value INTEGER,
  population INTEGER, pop_65plus INTEGER, pop_disabled INTEGER, vintage TEXT);
CREATE TABLE IF NOT EXISTS territory (zip TEXT PRIMARY KEY, city TEXT, county TEXT, tdu TEXT, mixed_with TEXT,
  status TEXT, zip_confidence TEXT, tdu_confidence TEXT, ptc_plans INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS collector_runs (stamp TEXT, job TEXT, status TEXT, line TEXT, PRIMARY KEY (stamp, job));
CREATE TABLE IF NOT EXISTS loaded_files (path TEXT PRIMARY KEY, mtime REAL, loaded_at TEXT);
"""


def rel(p):
    return os.path.relpath(p, ROOT)


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def iso(ts):
    """'2026-09-26 16:11:00-0500' -> '2026-09-26T16:11:00-05:00'."""
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S%z").isoformat()


class Loader:
    def __init__(self, con, incremental):
        self.con, self.incremental = con, incremental
        self.done = dict(con.execute("SELECT path, mtime FROM loaded_files")) if incremental else {}

    def want(self, path):
        return not (self.incremental and self.done.get(rel(path)) == os.path.getmtime(path))

    def mark(self, path):
        self.con.execute("INSERT OR REPLACE INTO loaded_files VALUES (?,?,?)",
                         (rel(path), os.path.getmtime(path), datetime.now().isoformat(timespec="seconds")))

    def many(self, sql, rows):
        self.con.executemany(sql, rows)


def load_permits(L):
    p = os.path.join(ROOT, "data/mirror/energy_permits.csv.gz")
    if not os.path.exists(p) or not L.want(p):
        return
    with gzip.open(p, "rt", newline="") as f:
        rows = [(r["permit_number"], r["issue_date"], r["applied_date"], r["zip"], num(r["lat"]), num(r["lon"]),
                 r["category"], r["contractor"], int(r["is_base"] or 0), r["work_class"], r["status"])
                for r in csv.DictReader(f)]
    L.many("INSERT OR REPLACE INTO permits VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    L.mark(p)


def load_dam_csv(L):
    p = os.path.join(ROOT, "data/ercot_dam_hourly_2025_2026.csv")
    if not os.path.exists(p) or not L.want(p):
        return
    rows = []
    for r in csv.DictReader(open(p)):
        for col, point in CSV_POINTS.items():
            if r.get(col) not in (None, ""):
                rows.append((r["date"], int(r["he"]), point, float(r[col]), rel(p)))
    # Snapshot rows are newer than the archive, so the archive never replaces them.
    L.many("INSERT OR IGNORE INTO dam_prices VALUES (?,?,?,?,?)", rows)
    L.mark(p)


def load_load_csv(L):
    p = os.path.join(ROOT, "data/ercot_load_hourly_2024_2026.csv")
    if not os.path.exists(p) or not L.want(p):
        return
    rows = []
    for r in csv.DictReader(open(p)):
        d = datetime.strptime(r["datetime"][:10], "%m/%d/%Y").strftime("%Y-%m-%d")
        rows.append((d, int(r["hour_ending"]), num(r["SCENT"]), num(r["NCENT"]), num(r["COAST"]), num(r["ERCOT"])))
    L.many("INSERT OR REPLACE INTO load_hourly VALUES (?,?,?,?,?,?)", rows)
    L.mark(p)


def snapshot_files():
    """(feed, path) for every ERCOT dashboard snapshot on disk."""
    out = []
    for p in glob.glob(os.path.join(ROOT, "data/live/ercot/*/*.json.gz")):
        out.append((os.path.basename(os.path.dirname(p)), p))
    for p in glob.glob(os.path.join(ROOT, "data/ercot/*.json")):
        out.append((re.sub(r"-\d{4}-\d\d-\d\d\.json$", "", os.path.basename(p)), p))
    for p in glob.glob(os.path.join(ROOT, "data/ercot-dam-*.json")):
        out.append(("system-wide-prices", p))
    return sorted(out, key=lambda t: t[1])


def read_json(p):
    with (gzip.open(p, "rt") if p.endswith(".gz") else open(p)) as f:
        return json.load(f)


def load_prices(L, d, src):
    rows = []
    for r in d.get("damSppData", []):
        # timestamp is the hour end; HE24 carries the next day's 00:00
        day = (datetime.strptime(r["timestamp"][:19], "%Y-%m-%d %H:%M:%S") - timedelta(hours=1)).strftime("%Y-%m-%d")
        for k, point in POINTS.items():
            if r.get(k) is not None:
                rows.append((day, int(r["hourEnding"]), point, r[k], src))
    L.many("INSERT OR REPLACE INTO dam_prices VALUES (?,?,?,?,?)", rows)
    rows = [(iso(r["timestamp"]), point, r[k], src) for r in d.get("rtSppData", [])
            for k, point in POINTS.items() if r.get(k) is not None]
    L.many("INSERT OR REPLACE INTO rt_prices VALUES (?,?,?,?)", rows)


def load_fuel(L, d, src):
    rows = [(iso(ts), fuel, v.get("gen"), src) for day in d.get("data", {}).values()
            for ts, fuels in day.items() for fuel, v in fuels.items()]
    L.many("INSERT OR REPLACE INTO fuel_mix VALUES (?,?,?,?)", rows)


def load_sd(L, d, src):
    rows = [(iso(r["timestamp"]), r["capacity"], r["demand"], src) for r in d.get("data", [])
            if r.get("demand") and not r.get("forecast")]
    L.many("INSERT OR REPLACE INTO supply_demand VALUES (?,?,?,?)", rows)


def load_prc(L, d, src):
    L.many("INSERT OR REPLACE INTO prc VALUES (?,?,?)",
           [(iso(r["timestamp"]), r["prc"], src) for r in d.get("data", []) if r.get("prc") is not None])
    c = d.get("current_condition") or {}
    if c:
        L.con.execute("INSERT OR REPLACE INTO conditions VALUES (?,?,?,?,?,?,?)",
                      (iso(d["lastUpdated"]), c.get("title"), c.get("state"), c.get("eea_level"),
                       num(c.get("prc_value")), c.get("condition_note"), src))


PARSERS = {"system-wide-prices": load_prices, "fuel-mix": load_fuel, "supply-demand": load_sd, "daily-prc": load_prc}


def load_snapshots(L):
    for feed, p in snapshot_files():
        if not L.want(p):
            continue
        try:
            d = read_json(p)
        except (OSError, ValueError) as e:
            print(f"skip {rel(p)}: {e}", file=sys.stderr)
            continue
        lu = d.get("lastUpdated") if isinstance(d, dict) else None
        try:
            lu = iso(lu) if lu and len(lu) > 19 else lu
        except ValueError:
            pass
        L.con.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)",
                      (rel(p), feed, lu, json.dumps(d, separators=(",", ":"))))
        if feed in PARSERS:
            PARSERS[feed](L, d, rel(p))
        L.mark(p)


def load_demographics(L):
    p = os.path.join(ROOT, "data/demographics.json")
    if not os.path.exists(p) or not L.want(p):
        return
    d = json.load(open(p))
    L.many("INSERT OR REPLACE INTO demographics VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           [(r["zip"], r.get("households"), r.get("owner_occupied"), r.get("single_family_detached"),
             r.get("median_year_built"), r.get("median_income"), r.get("median_home_value"), r.get("population"),
             r.get("pop_65plus"), r.get("pop_disabled"), d.get("vintage")) for r in d["rows"]])
    L.mark(p)


def load_territory(L):
    from house import territory as T
    ptc = {}
    pp = os.path.join(ROOT, "data/ptc_tdu.json")
    if os.path.exists(pp):
        ptc = {z: v.get("plans") for z, v in json.load(open(pp)).get("zips", {}).items()}
    rows = []
    for z, (tdu, city, county, conf, note, mixed) in T.ZIP_TABLE.items():
        status, tdu_conf, _ = T.zip_status(z)
        rows.append((z, city, county, tdu, mixed, status, conf, tdu_conf, ptc.get(z), note))
    L.many("INSERT OR REPLACE INTO territory VALUES (?,?,?,?,?,?,?,?,?,?)", rows)


def load_log(L):
    p = os.path.join(ROOT, "data/live/collect.log")
    if not os.path.exists(p):
        return
    rows = []
    for line in open(p).read().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            rows.append((parts[0], " ".join(parts[2:]) if parts[1] != "skip:" else "disk", parts[1].rstrip(":"), line))
    L.many("INSERT OR REPLACE INTO collector_runs VALUES (?,?,?,?)", rows)


TABLES = ["permits", "dam_prices", "rt_prices", "load_hourly", "fuel_mix", "supply_demand", "prc", "conditions",
          "snapshots", "demographics", "territory", "collector_runs", "judgments"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental", action="store_true", help="load only new or changed files")
    a = ap.parse_args()
    if not a.incremental and os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    L = Loader(con, a.incremental)
    # snapshots before the DAM archive: snapshot rows win on the same hour
    for step in (load_permits, load_snapshots, load_dam_csv, load_load_csv, load_demographics, load_territory, load_log):
        step(L)
        con.commit()
    from store import judgments
    judgments.fill(con)
    con.close()
    con = sqlite3.connect(DB)
    print(f"{rel(DB)} ({os.path.getsize(DB) / 1e6:.1f} MB){' incremental' if a.incremental else ''}")
    for t in TABLES:
        print(f"  {t:15s} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>8,}")
    last = con.execute("SELECT max(date) FROM dam_prices").fetchone()[0]
    print(f"  newest DAM day {last}; newest permit {con.execute('SELECT max(issue_date) FROM permits').fetchone()[0]}")


if __name__ == "__main__":
    main()
