"""Export the marts the Energy page (web/grid.html) draws into web/data/ercot_warehouse.json.
Every number on the page comes from this file; every number in this file comes from a mart."""
import json
import os

from . import ROOT

OUT = os.path.join(ROOT, "web", "data", "ercot_warehouse.json")
ZONES = ["LZ_AEN", "LZ_NORTH", "LZ_HOUSTON"]


def q(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def r(x, n=2):
    return None if x is None else round(float(x), n)


def run(con, report, dq):
    D = {"built_at": report["built_at"], "seconds": report["seconds"]}

    # ---- pipeline blocks (real counts) ----
    raw = report["raw"]
    mk = lambda t: sum(v["rows"] for v in raw.values() if v["table"] == t)
    m = {x["model"]: x for x in report["models"]}
    layer_rows = {}
    for x in report["models"]:
        layer_rows.setdefault(x["layer"], [0, 0])
        layer_rows[x["layer"]][0] += 1
        layer_rows[x["layer"]][1] += x["rows"]
    D["pipeline"] = {
        "raw": {"dam_spp": mk("dam_spp"), "rtm_spp": mk("rtm_spp"), "as_mcpc": mk("as_mcpc"),
                "load_hourly": mk("load_hourly"), "telemetry": report["fleet_sim"]["rows"]},
        "market_raw_rows": mk("dam_spp") + mk("rtm_spp") + mk("as_mcpc") + mk("load_hourly"),
        "telemetry_rows": report["fleet_sim"]["rows"],
        "telemetry_clean_rows": m["int_fleet__telemetry_minute"]["rows"],
        "layers": {k: {"models": v[0], "rows": v[1]} for k, v in layer_rows.items()},
        "schema_tests": {"pass": report["schema_tests"]["pass"], "total": report["schema_tests"]["total"]},
        "dq": dq["summary"],
        "models": [{"model": x["model"], "layer": x["layer"], "rows": x["rows"], "seconds": x["seconds"], "kind": x["kind"]}
                   for x in report["models"]],
        "throughput": report["telemetry_throughput"],
        "fleet_sim": report["fleet_sim"],
        "lineage": report["lineage"],
    }
    D["dq"] = dq

    # ---- market ----
    D["periods"] = q(con, "select period, start_date::varchar s, end_date::varchar e from int_market__periods")
    D["concentration"] = [{**c, "value_usd": r(c["value_usd"]), "top1pct_share": r(c["top1pct_share"], 4),
                           "top5pct_share": r(c["top5pct_share"], 4), "top10pct_share": r(c["top10pct_share"], 4),
                           "median_price": r(c["median_price"]), "max_price": r(c["max_price"])}
                          for c in q(con, "select * from mart_market__price_concentration")]
    D["curve"] = [{**c, "share_of_value": r(c["share_of_value"], 4)} for c in q(con, "select * from mart_market__concentration_curve")]
    D["reserve"] = [{"zone": c["load_zone"], "period": c["period"], "floor": c["reserve_floor_pct"], "value": r(c["value_usd"]),
                     "cost": r(c["reserve_cost_usd"]), "share": r(c["reserve_cost_share"], 4)}
                    for c in q(con, "select * from mart_market__reserve_cost")]
    D["stack"] = [{"zone": c["load_zone"], "period": c["period"], "floor": c["reserve_floor_pct"], "service": c["service"],
                   "usd": r(c["usd"]), "total": r(c["stack_total_usd"]), "energy_only": r(c["energy_only_usd"])}
                  for c in q(con, "select * from mart_market__revenue_stack")]
    D["monthly"] = [{"zone": c["load_zone"], "month": c["month"], "dam": r(c["dam_value_usd"]), "rtm": r(c["rtm_value_usd"]),
                     "best_day": r(c["best_day_usd"]), "days": c["days"]} for c in q(con, "select * from mart_market__battery_value_monthly")]
    days = q(con, "select local_date::varchar d, load_zone z, value_usd_floor30 v, value_usd_floor0 v0, peak_price_usd_mwh p from mart_market__battery_value_daily order by d")
    D["daily"] = {"dates": sorted({x["d"] for x in days})}
    for z in ZONES:
        zz = [x for x in days if x["z"] == z]
        D["daily"][z] = {"value": [r(x["v"]) for x in zz], "peak": [r(x["p"], 1) for x in zz]}
    hm = q(con, "select local_date::varchar d, hour_of_day h, aen, north, houston from mart_market__price_heatmap order by d, h")
    idx = {d: i for i, d in enumerate(D["daily"]["dates"])}
    D["heatmap"] = {}
    for z, col in (("LZ_AEN", "aen"), ("LZ_NORTH", "north"), ("LZ_HOUSTON", "houston")):
        grid = [[None] * 24 for _ in D["daily"]["dates"]]
        for x in hm:
            grid[idx[x["d"]]][x["h"]] = r(x[col], 1)
        D["heatmap"][z] = grid
    D["spikes_hod"] = q(con, """select market, load_zone, hour_of_day, sum(hours_ge_200) ge200, sum(hours_ge_1000) ge1000, sum(hours) n_hours
                               from mart_market__spike_hours group by all order by 1, 2, 3""")
    D["spikes_month"] = q(con, """select market, load_zone, month, sum(hours_ge_200) ge200, sum(hours_ge_500) ge500, sum(hours_ge_1000) ge1000,
                                  sum(hours_negative) neg from mart_market__spike_hours group by all order by 1, 2, 3""")
    lp = q(con, "select * from mart_market__load_vs_price")
    D["load_price"] = {str(y): {"hod": [{"h": x["hour_of_day"], "load": x["top_load_hours"], "price": x["top_price_hours"]}
                                        for x in lp if x["yr"] == y],
                                **{k: (r(v, 3) if isinstance(v, float) else str(v) if k.endswith("day") else v)
                                   for k, v in next(x for x in lp if x["yr"] == y).items()
                                   if k in ("hours", "first_day", "last_day", "overlap_top100", "corr_load_price", "peak_load_mw", "top_load_months", "top_price_months")}}
                       for y in sorted({x["yr"] for x in lp})}

    # ---- fleet (SIMULATION) ----
    D["fleet_hourly"] = [{"t": x["hour_local"].strftime("%Y-%m-%d %H:%M"), "mw": r(x["fleet_mw"], 3), "soc": r(x["soc_mean_pct"], 1),
                          "online": x["devices_online"], "rep": x["devices_reporting"], "down": x["devices_grid_down"],
                          "below": x["devices_below_reserve"], "kwh": r(x["kwh_above_reserve"], 0), "p": r(x["rt_price_aen"], 1)}
                         for x in q(con, "select * from mart_fleet__hourly order by hour_utc")]
    D["fleet_spikes"] = q(con, """select is_spike, count(*) intervals, round(avg(available_share), 4) avail,
                                  round(avg(reporting::double / devices), 4) reporting, round(avg(kwh_above_reserve), 1) kwh_above,
                                  round(avg(kw_discharging), 1) kw_out, round(avg(price_usd_mwh), 1) price
                                  from mart_fleet__spike_availability group by 1 order by 1""")
    D["fleet_spike_list"] = [{**x, "t": x["t"].strftime("%Y-%m-%d %H:%M")} for x in q(con, """
        select utc_to_chicago(interval_start_utc) t, load_zone z, round(price_usd_mwh, 1) p, devices, reporting, available,
               round(available_share, 4) as share, round(kwh_above_reserve, 0) kwh, round(kw_discharging, 0) kw
        from mart_fleet__spike_availability where is_spike order by interval_start_utc, load_zone""")]
    D["fleet_soc"] = [{**x, "local_date": str(x["local_date"]), "soc_p10": r(x["soc_p10"], 1), "soc_p50": r(x["soc_p50"], 1),
                       "soc_p90": r(x["soc_p90"], 1)} for x in q(con, "select * from mart_fleet__soc_daily order by 1")]
    D["fleet_devices"] = q(con, """select count(*) devices, count(*) filter (where is_skewed) skewed,
        count(*) filter (where minutes_since_last_seen > 60) stale, round(avg(missing_share) * 100, 2) missing_pct,
        count(*) filter (where longest_same_temp_min >= 240) stuck_temp, count(*) filter (where longest_same_soc_moving_min >= 60) stuck_soc
        from mart_fleet__device_health""")[0]
    D["fleet_zones"] = q(con, "select load_zone, count(*) n, round(avg(reserve_floor_pct), 1) floor from stg_fleet__devices group by 1 order by 1")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(D, open(OUT, "w"), separators=(",", ":"), default=str)
    return f"{os.path.relpath(OUT, ROOT)} {os.path.getsize(OUT) / 1024:.0f} KB"
