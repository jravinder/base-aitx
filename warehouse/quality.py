"""Data quality as code. Every check is one SQL query that returns (failing, detail).

  error  must be 0 for the build to be trusted (pytest fails otherwise)
  warn   a finding to look at (stale data, a faulty device); the build still stands

Results go to the DuckDB table dq_results and data/warehouse/dq_report.json. The fleet checks are
also scored against the faults warehouse/fleet_sim.py injected (dq_fault_detection): a check that
misses an injected fault, or flags a healthy device, shows up there.
"""
import datetime as dt
import json
import os

from . import DBT, WH

PRICE_MIN, PRICE_MAX = -251, 5000       # ERCOT offer floor (-$250; hubs settle to -$251) and offer cap


def _gaps(table, keys, step):
    k = ", ".join(keys)
    return f"""
    with s as (select {k}, interval_start_utc,
                      lead(interval_start_utc) over (partition by {k} order by interval_start_utc) as nxt
               from {table})
    select count(*) filter (where nxt - interval_start_utc <> interval {step}),
           'series ' || count(distinct ({k})) || ', largest step ' || max(nxt - interval_start_utc)
    from s"""


def _dups(table, keys):
    k = ", ".join(keys)
    return f"""select count(*) - count(distinct ({k})), count(*) || ' rows' from {table}"""


def _dst(table, part):
    # expected hours per local day come from the tz database: 23 spring-forward, 25 fall-back, else 24
    return f"""
    with h as (select {part} as part, local_date, count(distinct interval_start_utc) as n
               from {table} group by all),
    e as (select local_date, date_diff('hour', chicago_to_utc(local_date::timestamp, false),
                                       chicago_to_utc(local_date::timestamp + interval 1 day, false)) as want
          from (select distinct local_date from h))
    select count(*) filter (where n <> want),
           coalesce(string_agg(distinct strftime(local_date, '%Y-%m-%d') || '=' || n || 'h', ', ')
                    filter (where want <> 24), 'no DST days') from h join e using (local_date)"""


def _fresh(table, ts="interval_start_local"):
    return f"select 0, strftime(max({ts}), '%Y-%m-%d %H:%M') from {table}"


CHECKS = [
    # id, source, severity, sql, description
    ("dam_hourly_gaps", "ERCOT DAM", "error", _gaps("stg_ercot__dam_spp", ["settlement_point"], "1 hour"),
     "Every settlement point has one price per hour, no missing hour (UTC steps of exactly 1 h)."),
    ("rtm_15min_gaps", "ERCOT RTM", "error", _gaps("stg_ercot__rtm_spp", ["settlement_point", "settlement_point_type"], "15 minute"),
     "Every RTM series steps by exactly 15 minutes."),
    ("as_hourly_gaps", "ERCOT AS", "error", _gaps("stg_ercot__as_prices", ["service"], "1 hour"),
     "Every ancillary service has one clearing price per hour."),
    ("load_hourly_gaps", "ERCOT load", "error", _gaps("stg_ercot__load", ["weather_zone"], "1 hour"),
     "Every weather zone has one load value per hour."),
    ("dam_duplicates", "ERCOT DAM", "error", _dups("stg_ercot__dam_spp", ["settlement_point", "interval_start_utc"]),
     "No settlement point has two prices for the same UTC hour."),
    ("rtm_duplicates", "ERCOT RTM", "error", _dups("stg_ercot__rtm_spp", ["settlement_point", "settlement_point_type", "interval_start_utc"]),
     "No RTM series has two prices for the same interval."),
    ("as_duplicates", "ERCOT AS", "error", _dups("stg_ercot__as_prices", ["service", "interval_start_utc"]),
     "No service has two prices for the same hour."),
    ("load_duplicates", "ERCOT load", "error", _dups("stg_ercot__load", ["weather_zone", "interval_start_utc"]),
     "No zone has two loads for the same hour."),
    ("dam_dst_days", "ERCOT DAM", "error", _dst("stg_ercot__dam_spp", "settlement_point"),
     "Spring-forward days have 23 hours, fall-back days 25, all others 24."),
    ("rtm_dst_days", "ERCOT RTM", "error",
     _dst("(select *, settlement_point || settlement_point_type as sp from stg_ercot__rtm_spp where interval_in_hour = 1)", "sp"),
     "Same, for the 15-minute RTM series (counted on the first interval of each hour)."),
    ("as_dst_days", "ERCOT AS", "error", _dst("stg_ercot__as_prices", "service"), "Same, for ancillary service prices."),
    ("load_dst_days", "ERCOT load", "error", _dst("stg_ercot__load", "weather_zone"),
     "Same, for load (the repeated hour is labelled '02:00 DST' in the source)."),
    ("dam_price_bounds", "ERCOT DAM", "error",
     f"select count(*) filter (where price_usd_mwh not between {PRICE_MIN} and {PRICE_MAX}), "
     f"'min ' || min(price_usd_mwh) || ', max ' || max(price_usd_mwh) || ', negative hours ' || count(*) filter (where price_usd_mwh < 0) from stg_ercot__dam_spp",
     "Prices between the -$251 floor and the $5,000/MWh offer cap. Negative prices are allowed."),
    ("rtm_price_bounds", "ERCOT RTM", "error",
     f"select count(*) filter (where price_usd_mwh not between {PRICE_MIN} and {PRICE_MAX}), "
     f"'min ' || min(price_usd_mwh) || ', max ' || max(price_usd_mwh) || ', negative intervals ' || count(*) filter (where price_usd_mwh < 0) from stg_ercot__rtm_spp",
     "RTM prices inside the same bounds."),
    ("as_price_bounds", "ERCOT AS", "error",
     f"select count(*) filter (where price_usd_mw_h not between 0 and {PRICE_MAX}), 'max ' || max(price_usd_mw_h) from stg_ercot__as_prices",
     "AS clearing prices between $0 and the cap."),
    ("load_bounds", "ERCOT load", "error",
     "select count(*) filter (where load_mw <= 0 or (weather_zone = 'ERCOT' and load_mw not between 25000 and 95000)), "
     "'ERCOT ' || round(min(load_mw) filter (where weather_zone = 'ERCOT')) || ' to ' || round(max(load_mw) filter (where weather_zone = 'ERCOT')) || ' MW' from stg_ercot__load",
     "Zone load positive; ERCOT total between 25 and 95 GW (record about 85.5 GW)."),
    ("load_zone_sum", "ERCOT load", "error",
     "select count(*) filter (where load_scent_mw + load_ncent_mw + load_coast_mw > load_ercot_mw), "
     "'3 zones = ' || round(100 * min((load_scent_mw + load_ncent_mw + load_coast_mw) / load_ercot_mw)) || '-' || "
     "round(100 * max((load_scent_mw + load_ncent_mw + load_coast_mw) / load_ercot_mw)) || '% of ERCOT' "
     "from int_market__zone_hourly where load_ercot_mw is not null",
     "SCENT + NCENT + COAST never exceed the ERCOT total (the other five weather zones make up the rest)."),
    ("dam_legacy_reconcile", "ERCOT DAM", "error",
     """with n as (select settlement_point, local_date, hour_ending, price_usd_mwh from stg_ercot__dam_spp where not is_repeated_hour),
        j as (select l.price_usd_mwh lp, n.price_usd_mwh np from stg_ercot__dam_legacy l left join n using (settlement_point, local_date, hour_ending))
        select count(*) filter (where np is null or abs(lp - np) > 0.005),
               count(*) filter (where abs(lp - np) <= 0.005) || ' of ' || count(*) || ' legacy CSV hours match the archive' from j""",
     "The earlier CSV (grid/ercot_archive.py) agrees with the re-ingested archive, hour for hour."),
    ("market_day_coverage", "ERCOT", "error",
     """with d as (select 'dam' s, local_date from stg_ercot__dam_spp union select 'rtm', local_date from stg_ercot__rtm_spp
                 union select 'as', local_date from stg_ercot__as_prices),
        c as (select local_date, count(distinct s) n from d group by 1)
        select count(*) filter (where n < 3), count(*) || ' days, ' || min(local_date) || ' to ' || max(local_date) from c""",
     "DAM, RTM and AS prices cover the same days."),
    ("freshness_dam", "ERCOT DAM", "freshness", _fresh("stg_ercot__dam_spp"), "Latest DAM hour. Warn after 2 days, error after 14."),
    ("freshness_rtm", "ERCOT RTM", "freshness", _fresh("stg_ercot__rtm_spp"), "Latest RTM interval. Warn after 2 days, error after 14."),
    ("freshness_as", "ERCOT AS", "freshness", _fresh("stg_ercot__as_prices"), "Latest AS hour. Warn after 2 days, error after 14."),
    ("freshness_load", "ERCOT load", "freshness", _fresh("stg_ercot__load"), "Latest load hour. Warn after 30 days, error after 90."),
    # fleet (SIMULATION)
    ("tel_orphans", "Fleet telemetry", "error",
     "select count(*), 'device ids not in the device table' from (select distinct device_id from stg_fleet__telemetry) t anti join stg_fleet__devices using (device_id)",
     "Every telemetry row belongs to a known device."),
    ("tel_duplicates", "Fleet telemetry", "warn",
     "select count(*) - count(distinct (device_id, device_ts_utc)), count(*) || ' rows delivered; repeats dropped in int_fleet__telemetry_minute' from stg_fleet__telemetry",
     "Re-sent readings (same device, same timestamp). Kept out of every mart."),
    ("tel_stale_devices", "Fleet telemetry", "warn",
     "select count(*) filter (where minutes_since_last_seen > 60), coalesce('devices ' || string_agg(device_id::varchar, ', ' order by device_id) filter (where minutes_since_last_seen > 60), 'none') from mart_fleet__device_health",
     "Devices silent for more than 60 minutes at the end of the window."),
    ("tel_gaps", "Fleet telemetry", "warn",
     "select count(*) filter (where longest_gap_min > 60), sum(minutes_expected - minutes_reported) || ' device-minutes missing (' || "
     "round(100 * sum(minutes_expected - minutes_reported) / sum(minutes_expected), 2) || '%)' from mart_fleet__device_health",
     "Devices with a reporting gap over 60 minutes."),
    ("tel_out_of_range", "Fleet telemetry", "warn",
     "select count(*) filter (where soc_out_of_range or temp_out_of_range or kw_out_of_range), "
     "'SOC ' || count(*) filter (where soc_out_of_range) || ', temp ' || count(*) filter (where temp_out_of_range) || ', kW ' || count(*) filter (where kw_out_of_range) || ' readings nulled' from int_fleet__telemetry_minute",
     "Readings outside SOC 0-100 %, -30..80 C or |kW| <= 15 (set to null downstream)."),
    ("tel_clock_skew", "Fleet telemetry", "warn",
     "select count(*) filter (where is_skewed), coalesce('offsets ' || string_agg(round(clock_offset_s)::varchar || 's', ', ' order by clock_offset_s) filter (where is_skewed), 'none') from int_fleet__device_clock",
     "Devices whose clock is more than 30 s off the fleet (corrected downstream)."),
    ("tel_stuck_temp", "Fleet telemetry", "warn",
     "select count(*) filter (where longest_same_temp_min >= 240), coalesce('devices ' || string_agg(device_id::varchar, ', ') filter (where longest_same_temp_min >= 240), 'none') from mart_fleet__device_health",
     "Temperature unchanged for 4 hours or more (a live sensor jitters every minute)."),
    ("tel_stuck_soc", "Fleet telemetry", "warn",
     "select count(*) filter (where longest_same_soc_moving_min >= 60), coalesce('devices ' || string_agg(device_id::varchar, ', ') filter (where longest_same_soc_moving_min >= 60), 'none') from mart_fleet__device_health",
     "SOC unchanged for an hour or more while the battery moved power."),
    ("tel_reserve_breach", "Fleet telemetry", "error",
     """select count(*), count(distinct device_id) || ' devices' from int_fleet__telemetry_minute m
        where grid_ok and kw > 0.5 and soc_pct < reserve_floor_pct - 0.5
          and device_id not in (select device_id from mart_fleet__device_health where longest_same_soc_moving_min >= 60)""",
     "Reserve first: no device discharges to the grid below its member's floor while the grid is up."),
    ("tel_coverage", "Fleet telemetry", "warn",
     "select 0, round(100.0 * sum(minutes_reported) / sum(minutes_expected), 2) || '% of device-minutes present' from mart_fleet__device_health",
     "Share of expected device-minutes that arrived."),
]

FRESH = {"freshness_dam": (2, 14), "freshness_rtm": (2, 14), "freshness_as": (2, 14), "freshness_load": (30, 90)}

DETECT = {   # injected fault -> SQL selecting the device ids the checks flag for it
    "dead_comms": "select device_id from mart_fleet__device_health where minutes_since_last_seen > 60",
    "clock_drift": "select device_id from int_fleet__device_clock where is_skewed and abs(clock_offset_s) < 3600",
    "local_as_utc": "select device_id from int_fleet__device_clock where is_skewed and abs(clock_offset_s) >= 3600",
    "stuck_temp": "select device_id from mart_fleet__device_health where longest_same_temp_min >= 240",
    "stuck_soc": "select device_id from mart_fleet__device_health where longest_same_soc_moving_min >= 60",
    "unit_watts": "select device_id from int_fleet__telemetry_minute where kw_out_of_range group by 1",
}


def run(con, now=None):
    now = now or dt.datetime.now()
    cwd = os.getcwd()
    os.chdir(DBT)                      # stg_fleet__telemetry is a view over dbt-relative Parquet paths
    try:
        rows = []
        for cid, src, sev, sql, desc in CHECKS:
            failing, detail = con.execute(sql).fetchone()
            status = "pass"
            if sev == "freshness":
                latest = dt.datetime.strptime(detail, "%Y-%m-%d %H:%M")
                age = (now - latest).total_seconds() / 86400
                warn, err = FRESH[cid]
                failing = round(age, 1)
                status = "fail" if age > err else "warn" if age > warn else "pass"
                detail = f"latest {detail} CT, {age:.1f} days old (warn > {warn} d, error > {err} d)"
            elif failing:
                status = "fail" if sev == "error" else "warn"
            rows.append({"check_id": cid, "source": src, "severity": sev, "status": status,
                         "failing": failing, "detail": detail, "description": desc})
        det = []
        truth = con.execute("select fault, list(distinct device_id) from read_parquet('../../data/warehouse/raw/fleet_faults.parquet') group by 1").fetchall()
        truth = dict(truth)
        for fault, sql in DETECT.items():
            found = {r[0] for r in con.execute(sql).fetchall()}
            want = set(truth.get(fault, []))
            det.append({"fault": fault, "injected": len(want), "detected": len(want & found),
                        "missed": sorted(want - found), "false_positive": sorted(found - want)})
    finally:
        os.chdir(cwd)
    con.execute("create or replace table dq_results (check_id varchar, source varchar, severity varchar, status varchar, failing double, detail varchar, description varchar, checked_at timestamp)")
    con.executemany("insert into dq_results values (?, ?, ?, ?, ?, ?, ?, ?)",
                    [[r["check_id"], r["source"], r["severity"], r["status"], r["failing"], r["detail"], r["description"], now] for r in rows])
    con.execute("create or replace table dq_fault_detection (fault varchar, injected int, detected int, missed int[], false_positive int[])")
    con.executemany("insert into dq_fault_detection values (?, ?, ?, ?, ?)",
                    [[d["fault"], d["injected"], d["detected"], d["missed"], d["false_positive"]] for d in det])
    report = {"checked_at": now.isoformat(timespec="seconds"),
              "summary": {s: sum(r["status"] == s for r in rows) for s in ("pass", "warn", "fail")},
              "checks": rows, "fault_detection": det}
    json.dump(report, open(os.path.join(WH, "dq_report.json"), "w"), indent=1, default=str)
    return report
