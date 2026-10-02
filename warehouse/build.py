"""Rebuild the whole warehouse, idempotently: python3 -m warehouse.build

  1 ingest     ERCOT archive zips -> raw Parquet (skipped per file when the zip's sha256 is unchanged)
  2 simulate   fleet telemetry Parquet (SIMULATION; skipped when present, --resim to regenerate)
  3 model      staging -> intermediate -> marts in DuckDB (warehouse/dbt models, run by runner.py)
  4 test       the dbt schema tests (same yml dbt reads)
  5 quality    data-quality checks -> dq_results table + data/warehouse/dq_report.json
  6 export     web/data/ercot_warehouse.json for web/grid.html

Every table is create-or-replace, so a rebuild gives the same tables. Flags: --fetch (download
missing zips), --resim, --skip-export.
"""
import argparse
import json
import os
import time

import duckdb

from . import DB, RAW, WH, export, fleet_sim, ingest, quality, runner


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--resim", action="store_true")
    ap.add_argument("--skip-export", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(WH, exist_ok=True)
    T = {}
    t0 = time.time()

    t = time.time()
    manifest, _ = ingest.run(do_fetch=a.fetch)
    T["ingest"] = time.time() - t

    t = time.time()
    simp = os.path.join(WH, "fleet_sim.json")
    if a.resim or not os.path.exists(os.path.join(RAW, "telemetry")) or not os.path.exists(simp):
        json.dump(fleet_sim.simulate(), open(simp, "w"), indent=1)
    sim = json.load(open(simp))
    T["simulate"] = time.time() - t

    con = duckdb.connect(DB)
    con.execute("set TimeZone = 'UTC'")
    project = runner.Project()
    print(f"model: {len(project.models)} models")
    t = time.time()
    models = runner.run_models(con, project)
    T["model"] = time.time() - t

    t = time.time()
    tests = runner.run_tests(con, project)
    T["test"] = time.time() - t
    print(f"schema tests: {sum(x['status'] == 'pass' for x in tests)}/{len(tests)} pass")

    t = time.time()
    dq = quality.run(con)
    T["quality"] = time.time() - t
    print(f"quality: {dq['summary']}")
    for r in dq["checks"]:
        if r["status"] != "pass":
            print(f"  {r['status']:<5} {r['check_id']:<22} {r['failing']}  {r['detail']}")
    for d in dq["fault_detection"]:
        print(f"  detect {d['fault']:<13} {d['detected']}/{d['injected']} missed {d['missed']} false+ {d['false_positive']}")

    tel_models = [m for m in models if m["model"] in ("int_fleet__device_clock", "int_fleet__telemetry_minute")]
    tel_s = sum(m["seconds"] for m in tel_models)
    report = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": {k: round(v, 2) for k, v in T.items()},
        "raw": {k: {"rows": v["rows"], "table": v["table"]} for k, v in manifest.items()},
        "fleet_sim": sim,
        "models": models,
        "schema_tests": {"pass": sum(x["status"] == "pass" for x in tests), "total": len(tests),
                         "failing": [x for x in tests if x["status"] != "pass"]},
        "telemetry_throughput": {"rows_in": sim["rows"], "seconds": round(tel_s, 2),
                                 "rows_per_s": round(sim["rows"] / tel_s) if tel_s else None},
        "lineage": project.lineage(),
    }
    T["total"] = time.time() - t0
    report["seconds"]["total"] = round(T["total"], 2)
    json.dump(report, open(os.path.join(WH, "build_report.json"), "w"), indent=1, default=str)
    if not a.skip_export:
        out = export.run(con, report, dq)
        print(f"export: {out}")
    con.close()
    print(f"built in {T['total']:.1f}s  ({', '.join(f'{k} {v:.1f}s' for k, v in T.items() if k != 'total')})")
    print(f"telemetry: {sim['rows']:,} rows clock-corrected + deduplicated in {tel_s:.1f}s = {report['telemetry_throughput']['rows_per_s']:,} rows/s")
    return report


if __name__ == "__main__":
    main()
