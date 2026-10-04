"""UPPER BOUND. Perfect-foresight co-optimisation of DAM energy and DAM ancillary service capacity
(RegUp, RegDn, RRS, ECRS, Non-Spin) for one Base battery, per zone and reserve floor. Capacity
payments only (deployment energy ignored); energy backing per service and the reserve floor
constrain the up services (warehouse/dispatch.py). Daily totals per service."""
import os
import sys

import numpy as np
import pyarrow as pa

ZONES = {"aen": "LZ_AEN", "north": "LZ_NORTH", "houston": "LZ_HOUSTON"}
FLOORS = [0, 10, 20, 30, 40, 50]
SERVICES = ["regup", "regdn", "rrs", "ecrs", "nspin"]


def model(dbt, session):
    dbt.config(materialized="table")
    sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..", "..")))
    from warehouse import dispatch
    t = dbt.ref("int_market__zone_hourly").filter("regup is not null").order("interval_start_utc").to_arrow_table()
    ld = t["local_date"].to_numpy()
    days, day = np.unique(ld, return_inverse=True)
    asp = {s: t[s].to_numpy(zero_copy_only=False).astype(float) for s in SERVICES}
    out = {"load_zone": [], "reserve_floor_pct": [], "local_date": [], "service": [], "usd": [], "mw_h": []}
    for col, zone in ZONES.items():
        price = t[col].to_numpy(zero_copy_only=False).astype(float)
        for f in FLOORS:
            o = dispatch.solve(price, day, dt=1.0, floor=f / 100, as_prices=asp)
            for s in ["energy"] + SERVICES:
                usd = np.bincount(day, o[f"{s}_usd"], len(days))
                mwh = np.bincount(day, (o["discharge_kw"] if s == "energy" else o[f"{s}_kw"]) / 1000, len(days))
                out["load_zone"].append(np.full(len(days), zone)); out["reserve_floor_pct"].append(np.full(len(days), f, np.int32))
                out["local_date"].append(days); out["service"].append(np.full(len(days), s))
                out["usd"].append(usd); out["mw_h"].append(mwh)
    return pa.table({k: pa.array(np.concatenate(v)) for k, v in out.items()})
