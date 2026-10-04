"""Ingest: ERCOT public archives (as downloaded) -> raw Parquet, columns kept as published.

Sources (ERCOT MIS public reports, no login, no API key):
  13060 NP4-180-ER  Historical DAM Load Zone and Hub Prices   DAMLZHBSPP_<year>.zip (xlsx, hourly)
  13061 NP6-785-ER  Historical RTM Load Zone and Hub Prices   RTMLZHBSPP_<year>.zip (xlsx, 15-minute)
  13091 NP4-181-ER  Historical DAM Clearing Prices for Capacity DAMASMCPC_<year>.zip (csv, hourly AS MCPC)
  ERCOT Native Load by weather zone: data/ercot_load_hourly_2024_2026.csv (built earlier, grid/LOAD.md)

Download: https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId=<id>
Raw keeps every row, including the DST repeated hour (flag Y) that grid/ercot_archive.py dropped.
Idempotent: a source whose sha256 matches the manifest is not re-parsed (use --force).

  python3 -m warehouse.ingest [--fetch] [--force]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import time
import urllib.request
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq

from . import RAW, ROOT, ZIPS

# doclookupIds as listed on https://www.ercot.com/misapp/GetReports.do?reportTypeId=<id> (fetched 2026-10-02)
ARCHIVES = {
    "DAMLZHBSPP_2025.zip": 1177667469, "DAMLZHBSPP_2026.zip": 1279577316,
    "RTMLZHBSPP_2025.zip": 1177737535, "RTMLZHBSPP_2026.zip": 1279579209,
    "DAMASMCPC_2025.zip": 1177658395, "DAMASMCPC_2026.zip": 1279576956,
}
URL = "https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId={}"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch():
    os.makedirs(ZIPS, exist_ok=True)
    for name, doc in ARCHIVES.items():
        dst = os.path.join(ZIPS, name)
        if not os.path.exists(dst):
            print(f"fetch {name}")
            with urllib.request.urlopen(URL.format(doc), timeout=120) as r, open(dst, "wb") as f:
                shutil.copyfileobj(r, f)


def _xlsx_rows(zpath):
    import python_calamine as pc
    z = zipfile.ZipFile(zpath)
    inner = z.namelist()[0]
    wb = pc.CalamineWorkbook.from_filelike(io.BytesIO(z.read(inner)))
    header = None
    for s in wb.sheet_names:
        rows = wb.get_sheet_by_name(s).to_python()
        if not rows:
            continue
        header = header or [h.strip() for h in rows[0]]
        yield from (r for r in rows[1:] if any(c not in ("", None) for c in r))
    _xlsx_rows.header = header


def dam_spp(zpath):
    cols = {"delivery_date": [], "hour_ending": [], "repeated_hour_flag": [], "settlement_point": [], "price": []}
    for r in _xlsx_rows(zpath):
        for k, v in zip(cols, r):
            cols[k].append(v)
    return pa.table({"delivery_date": pa.array(cols["delivery_date"], pa.string()),
                     "hour_ending": pa.array(cols["hour_ending"], pa.string()),
                     "repeated_hour_flag": pa.array(cols["repeated_hour_flag"], pa.string()),
                     "settlement_point": pa.array(cols["settlement_point"], pa.string()),
                     "settlement_point_price": pa.array(cols["price"], pa.float64())})


def rtm_spp(zpath):
    names = ["delivery_date", "delivery_hour", "delivery_interval", "repeated_hour_flag",
             "settlement_point_name", "settlement_point_type", "settlement_point_price"]
    cols = {k: [] for k in names}
    for r in _xlsx_rows(zpath):
        for k, v in zip(names, r):
            cols[k].append(v)
    return pa.table({"delivery_date": pa.array(cols["delivery_date"], pa.string()),
                     "delivery_hour": pa.array([int(v) for v in cols["delivery_hour"]], pa.int16()),
                     "delivery_interval": pa.array([int(v) for v in cols["delivery_interval"]], pa.int16()),
                     "repeated_hour_flag": pa.array(cols["repeated_hour_flag"], pa.string()),
                     "settlement_point_name": pa.array(cols["settlement_point_name"], pa.string()),
                     "settlement_point_type": pa.array(cols["settlement_point_type"], pa.string()),
                     "settlement_point_price": pa.array(cols["settlement_point_price"], pa.float64())})


def as_mcpc(zpath):
    z = zipfile.ZipFile(zpath)
    rd = csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8"))
    header = [h.strip().lower() for h in next(rd)]   # REGUP is published with a trailing space
    rows = list(rd)
    out = {}
    for i, h in enumerate(header):
        key = h.replace(" ", "_")
        vals = [r[i] for r in rows]
        out[key] = pa.array(vals, pa.string()) if i < 3 else pa.array([float(v) for v in vals], pa.float64())
    return pa.table(out)


PARSERS = {"DAMLZHBSPP": ("dam_spp", dam_spp), "RTMLZHBSPP": ("rtm_spp", rtm_spp), "DAMASMCPC": ("as_mcpc", as_mcpc)}


def run(force=False, do_fetch=False):
    if do_fetch:
        fetch()
    os.makedirs(RAW, exist_ok=True)
    mpath = os.path.join(RAW, "_manifest.json")
    man = json.load(open(mpath)) if os.path.exists(mpath) and not force else {}
    t0 = time.time()
    for name in sorted(ARCHIVES):
        zpath = os.path.join(ZIPS, name)
        if not os.path.exists(zpath):
            raise SystemExit(f"missing {zpath}: run python3 -m warehouse.ingest --fetch")
        prefix, year = name[:-4].split("_")
        table, parse = PARSERS[prefix]
        out = os.path.join(RAW, table, f"{year}.parquet")
        digest = sha(zpath)
        if man.get(name, {}).get("sha256") == digest and os.path.exists(out):
            continue
        t = time.time()
        tbl = parse(zpath)
        tbl = tbl.append_column("_source_file", pa.array([name] * len(tbl), pa.string()))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pq.write_table(tbl, out, compression="zstd")
        man[name] = {"table": table, "sha256": digest, "rows": len(tbl), "bytes": os.path.getsize(zpath),
                     "doclookupId": ARCHIVES[name], "parquet": os.path.relpath(out, ROOT)}
        print(f"ingest {name} -> {table}/{year}.parquet {len(tbl):,} rows {time.time() - t:.1f}s")
    # local CSV sources are read in place by the raw sources (sources.yml); record their hashes too
    for rel in ("data/ercot_load_hourly_2024_2026.csv", "data/ercot_dam_hourly_2025_2026.csv"):
        p = os.path.join(ROOT, rel)
        man[os.path.basename(rel)] = {"table": "load_hourly" if "load" in rel else "dam_legacy_csv",
                                      "sha256": sha(p), "rows": sum(1 for _ in open(p)) - 1, "path": rel}
    json.dump(man, open(mpath, "w"), indent=1, sort_keys=True)
    return man, time.time() - t0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    run(a.force, a.fetch)
