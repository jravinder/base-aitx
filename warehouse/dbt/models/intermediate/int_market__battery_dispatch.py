"""UPPER BOUND. Perfect-foresight energy arbitrage for one Base battery on DAM hourly prices,
per load zone and per backup reserve floor (0-50%). LP in warehouse/dispatch.py."""
import os
import sys

import numpy as np
import pyarrow as pa

ZONES = {"aen": "LZ_AEN", "north": "LZ_NORTH", "houston": "LZ_HOUSTON"}
FLOORS = list(range(0, 55, 5))


def model(dbt, session):
    dbt.config(materialized="table")
    sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..", "..")))
    from warehouse import dispatch
    t = dbt.ref("int_market__zone_hourly").order("interval_start_utc").to_arrow_table()
    utc = t["interval_start_utc"].to_numpy()
    ld = t["local_date"].to_numpy()
    _, day = np.unique(ld, return_inverse=True)
    parts = []
    for col, zone in ZONES.items():
        price = t[col].to_numpy(zero_copy_only=False).astype(float)
        for f in FLOORS:
            o = dispatch.solve(price, day, dt=1.0, floor=f / 100)
            parts.append(pa.table({
                "load_zone": [zone] * len(price), "reserve_floor_pct": np.full(len(price), f, np.int32),
                "interval_start_utc": utc, "local_date": ld, "price_usd_mwh": price,
                "charge_kw": o["charge_kw"].round(4), "discharge_kw": o["discharge_kw"].round(4),
                "soc_kwh": o["soc_kwh"].round(4), "cash_usd": o["energy_usd"]}))
    return pa.concat_tables(parts)
