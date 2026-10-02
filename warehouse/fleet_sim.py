"""SIMULATION: 1-minute telemetry for a fleet of Base batteries, driven by REAL ERCOT prices.

Nothing here is Base data. Base's real telemetry is private; this generator produces the same
shape (device, timestamp, SOC, kW, temperature, online) so the pipeline, checks and marts can be
exercised at fleet scale (1,000 devices x 1,440 minutes x 30 days = 43.2M rows).

Driven by real prices: ERCOT RTM 15-minute load-zone prices (report 13061) and DAM hourly prices
(report 13060) for each device's zone, read from the raw Parquet written by warehouse/ingest.py.
Window 2026-01-12 .. 2026-02-10 (Central Standard Time throughout, no DST change), which holds
the January 2026 winter price spike.

Dispatch, reserve first (per device, per minute):
  grid down  -> backup: battery carries the home (1.2-4.5 kW, more in the cold), may go below the
                member's reserve floor (that is what the reserve is for), cuts off at 5%.
  storm watch (Jan 23 - Jan 28) -> grid floor raised to 80%; the battery fills to 100%.
  RT price >= $250/MWh, or a DAM top-3 hour with RT >= 1.2x the day's DAM mean -> discharge 10 kW
                down to the floor, never below it.
  DAM cheapest-4 hours or RT price < 0 -> charge 10 kW to 100% (derated to 3 kW below 0 C).
Battery: 39.2 kWh, 10 kW (sim/fleet.py), 95% one-way efficiency.

Injected faults (ground truth written to faults.parquet so the checks can be scored):
  dropouts (missing minutes), dead comms (device stops reporting), stuck temperature / SOC
  sensors, clock skew (small drift, and devices stamping local time as UTC), duplicate
  deliveries, out-of-range sentinels (-40 / 127 C, SOC > 100), a W-vs-kW unit bug, inverter trips
  (online = false).

  python3 -m warehouse.fleet_sim [--devices 1000] [--days 30] [--seed 11]
"""
import argparse
import datetime as dt
import os
import shutil
import time

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import RAW

START_LOCAL = dt.datetime(2026, 1, 12)          # CST, UTC-6 for the whole window
UTC_OFFSET = dt.timedelta(hours=6)
STORM = (dt.datetime(2026, 1, 23), dt.datetime(2026, 1, 29))   # local, watch window
ZONES = ["LZ_AEN", "LZ_NORTH", "LZ_HOUSTON"]
ZONE_P = [0.25, 0.40, 0.35]
FLOORS = np.array([0.20, 0.30, 0.40, 0.50])
FLOOR_P = [0.25, 0.45, 0.20, 0.10]
CAP, PKW, ETA = 39.2, 10.0, 0.95


def prices(days):
    """Minute-level RT price and per-minute DAM plan flags for each zone, from raw Parquet."""
    end = START_LOCAL + dt.timedelta(days=days)
    dates = [(START_LOCAL + dt.timedelta(days=i)).strftime("%m/%d/%Y") for i in range(days)]
    c = duckdb.connect()
    rt = c.execute(f"""
        select settlement_point_name sp, strptime(delivery_date, '%m/%d/%Y') + to_hours(delivery_hour - 1)
               + to_minutes((delivery_interval - 1) * 15) ts, settlement_point_price p
        from read_parquet('{RAW}/rtm_spp/*.parquet')
        where settlement_point_type = 'LZ' and settlement_point_name in {tuple(ZONES)}
          and delivery_date in {tuple(dates)} order by 1, 2""").fetchall()
    da = c.execute(f"""
        select settlement_point sp, strptime(delivery_date, '%m/%d/%Y') d, cast(left(hour_ending, 2) as int) he,
               settlement_point_price p
        from read_parquet('{RAW}/dam_spp/*.parquet')
        where settlement_point in {tuple(ZONES)} and delivery_date in {tuple(dates)} order by 1, 2, 3""").fetchall()
    n = days * 1440
    out = {}
    for z in ZONES:
        r = np.array([p for sp, ts, p in rt if sp == z])
        assert len(r) == days * 96, (z, len(r))
        rtm = np.repeat(r, 15)
        dam = np.array([p for sp, d, he, p in da if sp == z]).reshape(days, 24)
        chg = np.zeros((days, 24), bool)
        dis = np.zeros((days, 24), bool)
        o = np.argsort(dam, axis=1)
        np.put_along_axis(chg, o[:, :4], True, axis=1)
        np.put_along_axis(dis, o[:, -3:], True, axis=1)
        dmean = np.repeat(dam.mean(axis=1), 1440)
        out[z] = {"rt": rtm, "chg": np.repeat(chg.ravel(), 60), "dis": np.repeat(dis.ravel(), 60), "dmean": dmean}
        assert len(out[z]["rt"]) == n
    assert end <= dt.datetime(2026, 3, 8), "window must stay inside CST"
    return out


def outdoor_temp(days, rng):
    """Outdoor C per zone per minute: Jan diurnal cycle plus the Jan 24-27 cold snap."""
    m = np.arange(days * 1440)
    hod = (m % 1440) / 60.0
    day = m / 1440.0
    base = {"LZ_AEN": 9.0, "LZ_NORTH": 6.0, "LZ_HOUSTON": 12.0}
    out = {}
    for z in ZONES:
        t = base[z] + 6.0 * np.sin((hod - 9) / 24 * 2 * np.pi) + 2.5 * np.sin(day / 5.3 * 2 * np.pi)
        s0 = (dt.datetime(2026, 1, 24) - START_LOCAL).days * 1440
        s1 = (dt.datetime(2026, 1, 28) - START_LOCAL).days * 1440
        dip = np.zeros_like(t)
        dip[s0:s1] = -14.0 if z != "LZ_HOUSTON" else -10.0
        dip = np.convolve(dip, np.ones(720) / 720, mode="same")
        out[z] = t + dip
    return out


def simulate(n_dev=1000, days=30, seed=11, out_dir=None):
    out_dir = out_dir or os.path.join(RAW, "telemetry")
    rng = np.random.default_rng(seed)
    t0 = time.time()
    P = prices(days)
    T = outdoor_temp(days, rng)
    N = days * 1440
    ids = np.arange(1, n_dev + 1, dtype=np.int32)
    zone = rng.choice(len(ZONES), n_dev, p=ZONE_P)
    floor = rng.choice(FLOORS, n_dev, p=FLOOR_P)
    soc = rng.uniform(0.55, 0.95, n_dev)        # fraction
    cell = np.array([T[ZONES[z]][0] for z in zone]) + 4

    # outages: background (rare) + storm (6% of devices, 1-18 h)
    grid_down = np.zeros((N, n_dev), bool)
    s0 = (dt.datetime(2026, 1, 24) - START_LOCAL).days * 1440
    s1 = (dt.datetime(2026, 1, 28) - START_LOCAL).days * 1440
    for d in rng.choice(n_dev, int(0.06 * n_dev), replace=False):
        a = rng.integers(s0, s1 - 60)
        grid_down[a:a + int(rng.uniform(1, 18) * 60), d] = True
    for d in rng.choice(n_dev, int(0.02 * n_dev), replace=False):
        a = rng.integers(0, N - 300)
        grid_down[a:a + int(rng.uniform(0.3, 4) * 60), d] = True
    trip = np.zeros((N, n_dev), bool)          # inverter trip: reports online = false
    for d in rng.choice(n_dev, 12, replace=False):
        a = rng.integers(0, N - 600)
        trip[a:a + int(rng.uniform(1, 9) * 60), d] = True

    storm_a = (STORM[0] - START_LOCAL).days * 1440
    storm_b = (STORM[1] - START_LOCAL).days * 1440
    home_kw = rng.uniform(1.2, 3.0, n_dev)

    SOC = np.empty((N, n_dev), np.float32)
    KW = np.empty((N, n_dev), np.float32)
    TMP = np.empty((N, n_dev), np.float32)
    rt = np.stack([P[z]["rt"] for z in ZONES])[zone]          # (dev, N) views per zone
    chg = np.stack([P[z]["chg"] for z in ZONES])[zone]
    dis = np.stack([P[z]["dis"] for z in ZONES])[zone]
    dmean = np.stack([P[z]["dmean"] for z in ZONES])[zone]
    out_t = np.stack([T[z] for z in ZONES])[zone]
    for m in range(N):
        p = rt[:, m]
        storm = storm_a <= m < storm_b
        gfloor = np.maximum(floor, 0.80) if storm else floor
        cold = out_t[:, m] < 0
        kw = np.zeros(n_dev)
        want_dis = (p >= 250) | (dis[:, m] & (p >= 1.2 * dmean[:, m]))
        want_chg = chg[:, m] | (p < 0) | storm | (soc < gfloor)   # restore the reserve first
        kw = np.where(want_dis & (soc > gfloor), PKW, kw)
        kw = np.where(~want_dis & want_chg & (soc < 1.0), -np.where(cold, 3.0, PKW), kw)
        gd = grid_down[m]
        load = home_kw * (1 + np.clip(-out_t[:, m], 0, 15) / 10)
        kw = np.where(gd, np.minimum(load, 4.5), kw)
        kw = np.where(trip[m], 0.0, kw)
        # energy limits for this minute
        de = np.where(kw > 0, -kw / ETA, -kw * ETA) / 60.0 / CAP
        lo = np.where(gd, 0.05, gfloor)
        new = soc + de
        clip_lo = (kw > 0) & (new < lo)                       # never discharge through the floor
        kw = np.where(clip_lo, np.maximum(0, soc - lo) * CAP * 60 * ETA, kw)
        new = np.where(clip_lo, np.where(soc > lo, lo, soc), new)
        clip_hi = (kw < 0) & (new > 1.0)
        kw = np.where(clip_hi, -(1.0 - soc) * CAP * 60 / ETA, kw)
        soc = np.minimum(new, 1.0)
        cell += (out_t[:, m] + 4 + 0.35 * np.abs(kw) - cell) / 90.0
        SOC[m], KW[m], TMP[m] = soc * 100, kw, cell
    t_sim = time.time() - t0

    # sensor noise
    TMP += rng.normal(0, 0.15, TMP.shape).astype(np.float32)
    faults = []

    def fault(kind, d, a=None, b=None, note=""):
        faults.append({"device_id": int(ids[d]), "fault": kind,
                       "start_min": None if a is None else int(a), "end_min": None if b is None else int(b), "note": note})

    pick = rng.permutation(n_dev)
    k = iter(pick)
    for _ in range(6):                     # stuck temperature sensor for the rest of the window
        d = next(k); a = int(rng.integers(N // 4, N // 2))
        TMP[a:, d] = TMP[a, d]; fault("stuck_temp", d, a, N)
    for _ in range(3):                     # stuck SOC reading (BMS freeze) for 1-3 days
        d = next(k); a = int(rng.integers(0, N - 4320)); b = a + int(rng.integers(1440, 4320))
        SOC[a:b, d] = SOC[a, d]; fault("stuck_soc", d, a, b)
    unit = next(k); a = int(rng.integers(0, N - 1440))                     # firmware sent W, not kW, for a day
    KW[a:a + 1440, unit] *= 1000; fault("unit_watts", unit, a, a + 1440)
    sent = rng.random(TMP.shape) < 1e-4                                     # sentinel temperatures
    TMP[sent] = np.where(rng.random(sent.sum()) < 0.5, -40.0, 127.0)
    socbad = rng.random(SOC.shape) < 2e-5
    SOC[socbad] = rng.uniform(100.5, 110, socbad.sum())

    present = np.ones((N, n_dev), bool)
    for d in range(n_dev):                 # dropouts: ~1 per 3 days, median 10 min, long tail
        for _ in range(rng.poisson(days / 3)):
            a = int(rng.integers(0, N)); L = int(min(rng.lognormal(np.log(10), 1.3), 720))
            present[a:a + L, d] = False
    for _ in range(5):                     # dead comms: stops reporting for good
        d = next(k); a = int(rng.integers(N // 2, N - 600))
        present[a:, d] = False; fault("dead_comms", d, a, N)
    skew = np.zeros(n_dev, np.int64)       # seconds added to the device clock
    for _ in range(15):
        d = next(k); skew[d] = int(rng.choice([-1, 1]) * rng.integers(45, 540)); fault("clock_drift", d, note=f"{skew[d]}s")
    for _ in range(4):
        d = next(k); skew[d] = -6 * 3600; fault("local_as_utc", d, note="-21600s")
    online = ~trip
    for d in np.where(trip.any(axis=0))[0]:
        w = np.where(trip[:, d])[0]; fault("inverter_trip", d, int(w[0]), int(w[-1]) + 1)

    # write one Parquet file per local day
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    t_w = time.time()
    epoch0 = np.datetime64(START_LOCAL + UTC_OFFSET, "ms")
    rows = dups = 0
    for day in range(days):
        sl = slice(day * 1440, (day + 1) * 1440)
        mins = np.arange(sl.start, sl.stop)
        pres = present[sl]
        mi, di = np.nonzero(pres)                      # time-major order
        true_ts = epoch0 + (mins[mi] * 60_000).astype("timedelta64[ms]")
        lat = rng.integers(400, 6000, len(mi)).astype("timedelta64[ms]")
        recv = true_ts + lat
        dev_ts = true_ts + (skew[di] * 1000).astype("timedelta64[ms]") + rng.integers(0, 900, len(mi)).astype("timedelta64[ms]")
        cols = {"device_id": ids[di], "ts": dev_ts, "received_at": recv,
                "soc_pct": np.round(SOC[sl][mi, di], 1), "kw": np.round(KW[sl][mi, di], 2),
                "temp_c": np.round(TMP[sl][mi, di], 1), "online": online[sl][mi, di], "grid_ok": ~grid_down[sl][mi, di]}
        dup = np.nonzero(rng.random(len(mi)) < 0.003)[0]   # re-sent after a retry
        if len(dup):
            for c in cols:
                cols[c] = np.concatenate([cols[c], cols[c][dup]])
            cols["received_at"][-len(dup):] += rng.integers(30_000, 300_000, len(dup)).astype("timedelta64[ms]")
            dups += len(dup)
        tbl = pa.table({
            "device_id": pa.array(cols["device_id"], pa.int32()),
            "ts": pa.array(cols["ts"], pa.timestamp("ms")),
            "received_at": pa.array(cols["received_at"], pa.timestamp("ms")),
            "soc_pct": pa.array(cols["soc_pct"], pa.float32()), "kw": pa.array(cols["kw"], pa.float32()),
            "temp_c": pa.array(cols["temp_c"], pa.float32()),
            "online": pa.array(cols["online"]), "grid_ok": pa.array(cols["grid_ok"])})
        d = (START_LOCAL + dt.timedelta(days=day)).date().isoformat()
        os.makedirs(os.path.join(out_dir, f"day={d}"), exist_ok=True)
        pq.write_table(tbl, os.path.join(out_dir, f"day={d}", "part-0.parquet"), compression="zstd", row_group_size=500_000)
        rows += len(tbl)
    t_write = time.time() - t_w

    inst = [(START_LOCAL - dt.timedelta(days=int(x))).date() for x in rng.integers(30, 700, n_dev)]
    pq.write_table(pa.table({
        "device_id": pa.array(ids, pa.int32()),
        "serial": pa.array([f"BP-{i:05d}" for i in ids]),
        "load_zone": pa.array([ZONES[z] for z in zone]),
        "reserve_floor_pct": pa.array((floor * 100).astype(np.int32)),
        "capacity_kwh": pa.array(np.full(n_dev, CAP)), "power_kw": pa.array(np.full(n_dev, PKW)),
        "installed_on": pa.array(inst, pa.date32())}), os.path.join(RAW, "devices.parquet"))
    to_ts = lambda m: None if m is None else (START_LOCAL + UTC_OFFSET + dt.timedelta(minutes=m))
    pq.write_table(pa.table({
        "device_id": pa.array([f["device_id"] for f in faults], pa.int32()),
        "fault": pa.array([f["fault"] for f in faults]),
        "start_utc": pa.array([to_ts(f["start_min"]) for f in faults], pa.timestamp("ms")),
        "end_utc": pa.array([to_ts(f["end_min"]) for f in faults], pa.timestamp("ms")),
        "note": pa.array([f["note"] for f in faults])}), os.path.join(RAW, "fleet_faults.parquet"))
    stats = {"devices": n_dev, "days": days, "rows": rows, "duplicates": dups, "sim_s": round(t_sim, 1),
             "write_s": round(t_write, 1), "window_local": [START_LOCAL.date().isoformat(),
                                                           (START_LOCAL + dt.timedelta(days=days - 1)).date().isoformat()],
             "faults": len(faults), "seed": seed}
    print(f"fleet_sim {rows:,} rows ({dups:,} dup) {n_dev} devices x {days} days: sim {t_sim:.1f}s write {t_write:.1f}s")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", type=int, default=1000)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    simulate(a.devices, a.days, a.seed)
