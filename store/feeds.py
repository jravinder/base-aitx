"""Rebuild page feeds from data/fleet.db and compare them with the files the pages use now. Stdlib only.

  python3 store/feeds.py           build into data/live/feeds/ and report differences (pages untouched)
  python3 store/feeds.py --write   also replace a web/data or data file, only when it matches the
                                   current file on every value except fetch stamps

Known gaps against the current files:
  market.json annual: the mirror starts 2015, so 2013 and 2014 are missing.
  market.json contractors_2026 type: house/market.py reads descriptions; the mirror does not store
    them, so the store uses each contractor's most common category.

Feeds built here (the generator code runs unchanged; its file reads come from the store and its
file writes are caught in memory):
  web/data/explorer_zip.json     permits + demographics (same rule as house/mirror.py write_browser)
  web/data/explorer_points.json  permits through house/mirror.py write_browser
  data/market.json               permits (same rules as house/market.py, from the mirror, not Socrata)
  web/data/grid_today.json       snapshots (raw ERCOT JSON) through grid/today.py build_today
  web/data/grid_load.json        load_hourly through grid/today.py build_load
  web/data/grid_year.json        dam_prices (LZ_AEN, LZ_NORTH, LZ_HOUSTON) through grid/year.py
  data/funnel.json               demographics through house/funnel.py; still read from JSON:
                                 data/permits_by_zip.json, house/cohort.json, and the ACS fields
                                 the store does not keep (pop_disabled_under65 and two others)
  data/storms.json               permits + demographics + the store-built funnel through house/storms.py

A feed that differs from the current file is never replaced. The store copy goes beside it as
<name>.store.json for review. The page fetch paths do not change.
"""

import argparse
import builtins
import contextlib
import csv
import io
import json
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DB = os.path.join(ROOT, "data", "fleet.db")
OUTDIR = os.path.join(ROOT, "data", "live", "feeds")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "grid"))

CATEGORIES = ["battery", "solar", "solar_battery", "generator", "panel_upgrade", "ev_charger", "other_electrical"]
STAMPS = {"fetched_at", "built_at", "built"}

# Feeds that cannot come from the store yet, and why.
NOT_YET = {
    "data/permits_by_zip.json": "house/permits_by_zip.py counts all residential permits (new SFR, service "
                                "upgrades) by Socrata permit_class and description; the mirror keeps only "
                                "energy permits and drops those fields",
    "web/data/admin.json": "git log and gh issues, not data",
}


def q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def explorer_zip(con, cur):
    hh = dict(q(con, "SELECT zip, households FROM demographics"))
    blank = lambda: {**{c: 0 for c in CATEGORIES}, "base": 0}
    by_zip, by_month = defaultdict(blank), defaultdict(blank)
    for z, d, cat, b in q(con, "SELECT zip, issue_date, category, is_base FROM permits"):
        for key, bucket in ((z or "unknown", by_zip), (d[:7], by_month)):
            bucket[key][cat] += 1
            bucket[key]["base"] += b
    for z, v in by_zip.items():
        v["households"] = hh.get(z)
    meta = dict(cur.get("_meta", {}))
    meta["rows"] = q(con, "SELECT count(*) FROM permits")[0][0]
    return {"_meta": meta, "by_zip": dict(sorted(by_zip.items())), "by_month": dict(sorted(by_month.items()))}


TYPE = {"solar_battery": "solar-plus-battery", "battery": "battery", "generator": "generator", "solar": "solar only"}


def market(con, cur):
    aux = "work_class='Auxiliary Power'"
    base = f"{aux} AND is_base=1"
    all_ = dict(q(con, f"SELECT substr(issue_date,1,7), count(*) FROM permits WHERE {aux} AND issue_date>='2024-01-01' GROUP BY 1"))
    b = dict(q(con, f"SELECT substr(issue_date,1,7), count(*) FROM permits WHERE {base} GROUP BY 1"))
    monthly = [{"month": m, "base": b.get(m, 0), "others": all_[m] - b.get(m, 0)} for m in sorted(all_)]

    rows = q(con, f"SELECT contractor, count(*) FROM permits WHERE {aux} AND issue_date>='2026-01-01' AND contractor<>'' "
                  "GROUP BY contractor ORDER BY 2 DESC LIMIT 10")
    contractors, rank = [], 0
    for name, n in rows:
        if name != "Base Power":
            rank += 1
        cats = Counter(dict(q(con, f"SELECT category, count(*) FROM permits WHERE {aux} AND issue_date>='2026-01-01' "
                                   "AND contractor=? GROUP BY category", name)))
        top = cats.most_common(1)[0][0] if cats else ""
        contractors.append({"contractor": name if name == "Base Power" else f"Installer {rank}", "permits_2026": n,
                            "type": TYPE.get(top, "other")})

    def days(a, i):
        return (date.fromisoformat(i) - date.fromisoformat(a)).days
    brows = q(con, f"SELECT zip, status, applied_date, issue_date FROM permits WHERE {base}")
    demo = {r[0]: r[1] for r in q(con, "SELECT zip, owner_occupied FROM demographics")}
    zips = defaultdict(lambda: {"count": 0, "final": 0, "active": 0, "other": 0, "d": []})
    status = Counter()
    for z, s, a, i in brows:
        z = z or "unknown"
        s = (s or "").lower()
        status[s or "none"] += 1
        zz = zips[z]
        zz["count"] += 1
        zz[s if s in ("final", "active") else "other"] += 1
        if a and i:
            zz["d"].append(days(a, i))
    by_zip = []
    for z, v in zips.items():
        oo = demo.get(z)
        by_zip.append({"zip": z, "count": v["count"], "final": v["final"], "active": v["active"], "other": v["other"],
                       "median_days_applied_to_issued": float(statistics.median(v["d"])) if v["d"] else None,
                       "final_rate": round(v["final"] / v["count"], 3), "owner_occupied": oo,
                       "per_1000_owner_occupied": round(1000 * v["count"] / oo, 2) if oo else None})
    by_zip.sort(key=lambda z: (z["per_1000_owner_occupied"] is None, -(z["per_1000_owner_occupied"] or 0), -z["count"]))
    total = sum(status.values())
    alld = [days(a, i) for _, _, a, i in brows if a and i]
    totals = {"total": total, "by_status": dict(status),
              "final_rate": round(status.get("final", 0) / total, 3) if total else None,
              "median_days_applied_to_issued": float(statistics.median(alld)) if alld else None}
    annual = [{"year": int(y), "total": n} for y, n in
              q(con, f"SELECT substr(issue_date,1,4), count(*) FROM permits WHERE {aux} GROUP BY 1 ORDER BY 1")]
    return {"source": "data/fleet.db permits (mirror of Socrata 3syk-w9eu)", "fetched_at": cur.get("fetched_at"),
            "base_rule": cur.get("base_rule"), "monthly": monthly, "contractors_2026": contractors,
            "base_totals": totals, "base_by_zip": by_zip, "annual": annual}


def grid_today(con, cur):
    import today as T

    def newest(feed):
        for prefix in (f"data/live/ercot/{feed}/", f"data/ercot/{feed}-"):
            r = con.execute("SELECT path, body FROM snapshots WHERE feed=? AND path LIKE ? ORDER BY path DESC LIMIT 1",
                            (feed, prefix + "%")).fetchone()
            if r:
                return json.loads(r[1]), r[0]
        return None, None
    T.newest = newest
    return T.build_today()


class _Buf(io.StringIO):
    def close(self):
        pass


def run_with_store(mod, fn, reads, *args):
    """Run fn from mod with its open() served from memory: paths in reads return that text,
    writes are kept in memory and returned. Other reads go to disk."""
    writes = {}

    def shim(path, mode="r", *a, **k):
        full = os.path.normpath(path if os.path.isabs(path) else os.path.join(ROOT, path))
        if "w" in mode:
            writes[full] = _Buf()
            return writes[full]
        if full in reads:
            return io.StringIO(reads[full])
        return builtins.open(path, mode, *a, **k)
    mod.open = shim
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            fn(*args)
    finally:
        del mod.open
    return {p: json.loads(b.getvalue()) for p, b in writes.items()}


def _abs(rel):
    return os.path.join(ROOT, rel)


def _csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def demographics_json(con):
    """data/demographics.json shape from the store. ACS fields the store does not keep come from the
    JSON file."""
    extra = {r["zip"]: r for r in json.load(open(_abs("data/demographics.json")))["rows"]}
    cols = [c[1] for c in con.execute("PRAGMA table_info(demographics)")]
    rows = []
    for r in q(con, "SELECT * FROM demographics ORDER BY zip"):
        d = dict(zip(cols, r))
        d.pop("vintage", None)
        rows.append({**{k: v for k, v in extra.get(d["zip"], {}).items() if k not in d}, **d})
    return {"rows": rows}


def explorer_points(con, cur):
    import house.mirror as M
    cols = ["permit_number", "issue_date", "applied_date", "zip", "lat", "lon", "category", "contractor",
            "is_base", "work_class", "status"]
    rows = [{k: ("" if v is None else str(v)) for k, v in zip(cols, r)}
            for r in q(con, "SELECT " + ",".join(cols) + " FROM permits ORDER BY rowid")]
    reads = {_abs(M.DEMO_PATH): json.dumps(demographics_json(con))}
    out = run_with_store(M, M.write_browser, reads, rows, cur["_meta"].get("fetched_at"))
    return out[_abs(M.POINTS_PATH)]


def grid_load(con, cur):
    import today as T
    rows = [(f"{d[5:7]}/{d[8:10]}/{d[:4]} {he:02d}:00", d[:4], str(int(d[5:7])), he, sc, nc, co, er)
            for d, he, sc, nc, co, er in q(con, "SELECT date, he, scent, ncent, coast, ercot FROM load_hourly "
                                                "ORDER BY date, he")]
    text = _csv(["datetime", "year", "month", "hour_ending", "SCENT", "NCENT", "COAST", "ERCOT"], rows)
    result = {}
    run_with_store(T, lambda: result.update(T.build_load()), {os.path.normpath(T.LOAD_CSV): text})
    return result


def grid_year(con, cur):
    import year as Y
    by = defaultdict(dict)
    for d, he, pt, p in q(con, "SELECT date, he, point, price FROM dam_prices "
                               "WHERE point IN ('LZ_AEN','LZ_NORTH','LZ_HOUSTON') ORDER BY date, he"):
        by[(d, he)][pt] = p
    rows = [(d, he, v["LZ_AEN"], v["LZ_NORTH"], v["LZ_HOUSTON"]) for (d, he), v in sorted(by.items()) if len(v) == 3]
    out = run_with_store(Y, Y.main, {os.path.normpath(Y.CSV): _csv(["date", "he", "aen", "north", "houston"], rows)})
    return out[os.path.normpath(Y.OUT)]


BUILT = {}


def funnel(con, cur):
    import house.funnel as F
    out = run_with_store(F, F.main, {os.path.normpath(F.DEMO_PATH): json.dumps(demographics_json(con))})
    BUILT["funnel"] = out[os.path.normpath(F.OUT_PATH)]
    return BUILT["funnel"]


def storms(con, cur):
    import house.storms as S
    import types
    cols = ["zip", "category", "applied_date", "is_base"]
    text = _csv(cols, [["" if v is None else v for v in r]
                       for r in q(con, "SELECT zip, category, applied_date, is_base FROM permits ORDER BY rowid")])
    fun = BUILT.get("funnel") or funnel(con, None)
    S.gzip = types.SimpleNamespace(open=lambda *a, **k: io.StringIO(text))
    try:
        out = run_with_store(S, S.main, {_abs("data/funnel.json"): json.dumps(fun),
                                         _abs("data/demographics.json"): json.dumps(demographics_json(con))})
    finally:
        import gzip
        S.gzip = gzip
    return out[_abs("data/storms.json")]


def diff(a, b, path="", out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k in STAMPS:
                continue
            if k not in a or k not in b:
                out.append(f"{path}.{k}: {'only in store' if k in a else 'only in current'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items in store vs {len(b)} current")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out)
    elif a != b and not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 1e-9):
        out.append(f"{path}: store {json.dumps(a)[:60]} vs current {json.dumps(b)[:60]}")
    return out


FEEDS = [("web/data/explorer_zip.json", explorer_zip), ("web/data/explorer_points.json", explorer_points),
         ("data/market.json", market), ("web/data/grid_today.json", grid_today),
         ("web/data/grid_load.json", grid_load), ("web/data/grid_year.json", grid_year),
         ("data/funnel.json", funnel), ("data/storms.json", storms)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    os.makedirs(OUTDIR, exist_ok=True)
    report = {}
    for path, fn in FEEDS:
        cur = json.load(open(os.path.join(ROOT, path)))
        new = fn(con, cur)
        out = os.path.join(OUTDIR, os.path.basename(path))
        json.dump(new, open(out, "w"), separators=(",", ":"))
        d = diff(new, cur)
        report[path] = {"differences": len(d), "sample": d[:12], "built": os.path.relpath(out, ROOT)}
        print(f"{path}: {'same as current' if not d else f'{len(d)} differences'} (built {os.path.relpath(out, ROOT)})")
        for line in d[:12]:
            print("   ", line)
        beside = os.path.join(ROOT, path[:-5] + ".store.json")
        if d:
            json.dump(new, open(beside, "w"), indent=1)
            print(f"    not replaced; store copy at {os.path.relpath(beside, ROOT)}")
        else:
            if os.path.exists(beside):
                os.remove(beside)
            if a.write:
                json.dump(new, open(os.path.join(ROOT, path), "w"), separators=(",", ":"))
                print("    replaced")
    print("not from the store yet:")
    for k, v in NOT_YET.items():
        print(f"  {k}: {v}")
    report["not_yet"] = NOT_YET
    json.dump(report, open(os.path.join(OUTDIR, "report.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
