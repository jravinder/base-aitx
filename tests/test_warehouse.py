"""ERCOT + fleet warehouse tests. Build first: python3 -m warehouse.build (about 75 s).
Unit tests (DST macro, dispatch LP) need no build; the rest read data/warehouse/base.duckdb."""
import json
import os

import duckdb
import numpy as np
import pytest

from warehouse import DB, WH, dispatch, runner

BUILT = os.path.exists(DB) and os.path.exists(os.path.join(WH, "dq_report.json"))
needs_build = pytest.mark.skipif(not BUILT, reason="run python3 -m warehouse.build first")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(DB, read_only=True)
    yield c
    c.close()


# ---------- unit: time handling ----------
@pytest.fixture(scope="module")
def mem():
    c = duckdb.connect()
    c.execute(runner.Project().macros())
    return c


@pytest.mark.parametrize("local,repeated,utc", [
    ("2025-01-15 00:00", False, "2025-01-15 06:00"),   # CST
    ("2025-07-01 00:00", False, "2025-07-01 05:00"),   # CDT
    ("2025-11-02 01:00", False, "2025-11-02 06:00"),   # fall back, first 01:00 (CDT)
    ("2025-11-02 01:00", True, "2025-11-02 07:00"),    # fall back, repeated 01:00 (CST)
    ("2025-11-02 01:45", False, "2025-11-02 06:45"),
    ("2025-11-02 02:00", False, "2025-11-02 08:00"),
    ("2026-03-08 03:00", False, "2026-03-08 08:00"),   # spring forward: 02:00 local does not exist
])
def test_chicago_to_utc(mem, local, repeated, utc):
    got = mem.execute(f"select strftime(chicago_to_utc(timestamp '{local}', {repeated}), '%Y-%m-%d %H:%M')").fetchone()[0]
    assert got == utc


# ---------- unit: dispatch LP ----------
def test_dispatch_basic_bounds():
    price = np.array([10, 200, 10, 200, 50, 50] * 2, float)
    day = np.repeat([0, 1], 6)
    o = dispatch.solve(price, day, floor=0.3)
    fl = 0.3 * dispatch.CAP_KWH
    assert o["energy_usd"].sum() > 0
    assert o["soc_kwh"].min() >= fl - 1e-6 and o["soc_kwh"].max() <= dispatch.CAP_KWH + 1e-6
    assert abs(o["soc_kwh"][5] - fl) < 1e-6 and abs(o["soc_kwh"][11] - fl) < 1e-6   # each day ends at the floor
    assert o["charge_kw"].max() <= dispatch.P_KW + 1e-6 and o["discharge_kw"].max() <= dispatch.P_KW + 1e-6


def test_reserve_never_helps_and_stack_never_hurts():
    rng = np.random.default_rng(0)
    price = rng.gamma(2, 20, 24 * 10)
    day = np.repeat(np.arange(10), 24)
    vals = [dispatch.solve(price, day, floor=f)["energy_usd"].sum() for f in (0, 0.3, 0.5)]
    assert vals[0] >= vals[1] >= vals[2]
    asp = {s: rng.gamma(2, 1, len(price)) for s in ("regup", "regdn", "rrs", "ecrs", "nspin")}
    st = dispatch.solve(price, day, floor=0.3, as_prices=asp)
    assert sum(v.sum() for k, v in st.items() if k.endswith("_usd")) >= vals[1] - 1e-6


# ---------- warehouse ----------
@needs_build
def test_schema_tests_pass(con):
    res = runner.run_tests(con, runner.Project())
    bad = [r for r in res if r["status"] != "pass"]
    assert not bad, bad
    assert len(res) >= 60


@needs_build
def test_quality_no_failures():
    rep = json.load(open(os.path.join(WH, "dq_report.json")))
    fails = [c for c in rep["checks"] if c["status"] == "fail"]
    assert not fails, fails
    errors = [c for c in rep["checks"] if c["severity"] == "error"]
    assert len(errors) >= 15 and all(c["status"] == "pass" for c in errors)


@needs_build
def test_checks_catch_every_injected_fault():
    rep = json.load(open(os.path.join(WH, "dq_report.json")))
    for d in rep["fault_detection"]:
        assert d["detected"] == d["injected"] and not d["missed"], d
        assert not d["false_positive"], d


@needs_build
def test_dst_days(con):
    n = dict(con.execute("""select local_date::varchar, count(*) from stg_ercot__dam_spp where settlement_point = 'LZ_AEN'
                            and local_date in ('2025-03-09', '2025-11-02', '2026-03-08', '2025-06-01') group by 1""").fetchall())
    assert n == {"2025-03-09": 23, "2025-11-02": 25, "2026-03-08": 23, "2025-06-01": 24}
    he2 = con.execute("""select is_repeated_hour, strftime(interval_start_utc, '%H:%M') from stg_ercot__dam_spp
                         where settlement_point = 'LZ_AEN' and local_date = '2025-11-02' and hour_ending = 2 order by 1""").fetchall()
    assert he2 == [(False, "06:00"), (True, "07:00")]


@needs_build
def test_value_attribution_sums_to_cash(con):
    a, b = con.execute("""select (select sum(value_usd) from int_market__hourly_value),
                                 (select sum(cash_usd) from int_market__battery_dispatch)""").fetchone()
    assert abs(a - b) < 0.01


@needs_build
def test_reserve_cost_monotonic(con):
    rows = con.execute("""select load_zone, period, list(value_usd order by reserve_floor_pct)
                          from mart_market__reserve_cost group by all""").fetchall()
    for z, p, v in rows:
        assert all(x >= y - 1e-6 for x, y in zip(v, v[1:])), (z, p, v)


@needs_build
def test_fleet_clean_layer(con):
    raw, clean, dev = con.execute("""select (select count(*) from read_parquet('data/warehouse/raw/telemetry/*/*.parquet')),
                                            (select count(*) from int_fleet__telemetry_minute),
                                            (select count(*) from stg_fleet__devices)""").fetchone()
    assert dev == 1000 and raw > 42_000_000
    assert clean < raw                                    # duplicates removed
    assert clean <= dev * 30 * 1440                      # at most one row per device-minute


@needs_build
def test_web_export_matches_marts(con):
    D = json.load(open(os.path.join(os.path.dirname(DB), "..", "..", "web", "data", "ercot_warehouse.json")))
    top1 = con.execute("""select top1pct_share from mart_market__price_concentration
                          where load_zone = 'LZ_AEN' and period = 'last 365 days'""").fetchone()[0]
    got = next(c for c in D["concentration"] if c["load_zone"] == "LZ_AEN" and c["period"] == "last 365 days")
    assert abs(got["top1pct_share"] - top1) < 1e-3
    assert D["pipeline"]["telemetry_rows"] > 42_000_000
