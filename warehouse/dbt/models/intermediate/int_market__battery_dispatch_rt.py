"""UPPER BOUND. The same perfect-foresight arbitrage on RTM 15-minute load-zone prices (type LZ),
reserve floors 0% and 30%, to compare what real-time volatility is worth against day-ahead."""
import os
import sys

import numpy as np
import pyarrow as pa

ZONES = ["LZ_AEN", "LZ_NORTH", "LZ_HOUSTON"]
FLOORS = [0, 30]


def model(dbt, session):
    dbt.config(materialized="table")
    sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..", "..")))
    from warehouse import dispatch
    rel = dbt.ref("stg_ercot__rtm_spp")
    parts = []
    for zone in ZONES:
        t = rel.filter(f"settlement_point = '{zone}' and settlement_point_type = 'LZ'").order("interval_start_utc").to_arrow_table()
        price = t["price_usd_mwh"].to_numpy()
        ld = t["local_date"].to_numpy()
        _, day = np.unique(ld, return_inverse=True)
        for f in FLOORS:
            o = dispatch.solve(price, day, dt=0.25, floor=f / 100)
            parts.append(pa.table({
                "load_zone": [zone] * len(price), "reserve_floor_pct": np.full(len(price), f, np.int32),
                "interval_start_utc": t["interval_start_utc"], "local_date": t["local_date"],
                "price_usd_mwh": price, "charge_kw": o["charge_kw"].round(4),
                "discharge_kw": o["discharge_kw"].round(4), "cash_usd": o["energy_usd"]}))
    return pa.concat_tables(parts)
