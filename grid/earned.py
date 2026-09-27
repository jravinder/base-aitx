"""Grid Data chapter: what one Base battery earned this week from ERCOT prices.

Source: data/ercot-dam-2026-09-07.json and data/ercot-dam-2026-09-09.json.
These are real ERCOT day-ahead settlement point prices (damSppData), $/MWh, hourly,
for LZ_AEN (Austin Energy load zone) and LZ_NORTH (Dallas, Oncor comparison). ERCOT has only two days of
real price data checked into this repo (no no-login source for a live 7-day pull
was found: the ERCOT data-product page and api.ercot.com both require MIS login or
an API key). To fill 7 days we CYCLE the two real days (07, 09, 07, 09, 07, 09, 07).
This is honestly labeled below, not hidden: days 1,3,5,7 are 2026-09-07 and
days 2,4,6 are 2026-09-09, both real ERCOT DAM prices, repeated.

Battery: one spec shared with sim/fleet.py (#62): Base Core 39.2 kWh ("39.2 kWh in every
Base Core", basepowercompany.com), 10 kW charge/discharge (sim RATE_KW; no public source for the
kW rating), 30% member reserve kept (sim RESERVE) -> 27.44 kWh usable per cycle. One cycle a day:
charge in the cheapest 3 hours, discharge in the most expensive 3 hours, 9.15 kWh an hour
(within 10 kW).

Zone: LZ_AEN (Austin Energy load zone), the zone sim/fleet.py prices. LZ_NORTH (Dallas, Oncor
territory) is the comparison.
"""

import json
import os

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")

import sys
sys.path.insert(0, os.path.join(HERE, ".."))
from sim.fleet import CAPACITY_KWH, RATE_KW, RESERVE  # noqa: E402  one battery spec for grid/ and sim/

USABLE_KWH = CAPACITY_KWH * (1 - RESERVE)   # 27.44 kWh usable per cycle
HOURS_PER_WINDOW = 3
KWH_PER_HOUR = USABLE_KWH / HOURS_PER_WINDOW   # 9.15 kWh/hour
assert KWH_PER_HOUR <= RATE_KW

DAY_FILES = {
    "2026-09-07": "ercot-dam-2026-09-07.json",
    "2026-09-09": "ercot-dam-2026-09-09.json",
}


def load_day(date, zone):
    d = json.load(open(os.path.join(DATA, DAY_FILES[date])))
    # $/MWh -> $/kWh
    return [(r["hourEnding"], r[zone] / 1000.0) for r in d["damSppData"]]


def simulate_day(hours):
    """hours: list of (hourEnding, price $/kWh). Returns dict of day's arbitrage result."""
    by_price = sorted(hours, key=lambda hp: hp[1])
    cheapest = sorted(by_price[:HOURS_PER_WINDOW], key=lambda hp: hp[0])
    priciest = sorted(by_price[-HOURS_PER_WINDOW:], key=lambda hp: hp[0])

    charge_cost = sum(p * KWH_PER_HOUR for _, p in cheapest)
    discharge_revenue = sum(p * KWH_PER_HOUR for _, p in priciest)
    net = discharge_revenue - charge_cost

    # single hour that mattered most: biggest absolute cash flow in either window
    flows = [(-p * KWH_PER_HOUR, h, "charge") for h, p in cheapest] + \
            [(p * KWH_PER_HOUR, h, "discharge") for h, p in priciest]
    best = max(flows, key=lambda f: abs(f[0]))

    return {
        "charge_cost": charge_cost,
        "discharge_revenue": discharge_revenue,
        "net": net,
        "charge_hours": [h for h, _ in cheapest],
        "discharge_hours": [h for h, _ in priciest],
        "key_hour": best[1],
        "key_flow": best[0],
        "key_kind": best[2],
        "max_price": max(p for _, p in hours) * 1000,  # back to $/MWh for display
    }


def run_week(zone, date_sequence):
    days = []
    for date in date_sequence:
        hours = load_day(date, zone)
        result = simulate_day(hours)
        result["date"] = date
        days.append(result)
    return days


def print_table(zone_label, days):
    print(f"\n{zone_label} -- 7-day arbitrage, {CAPACITY_KWH} kWh / {RATE_KW:.0f} kW battery, "
          f"{RESERVE:.0%} reserve kept, one cycle/day")
    print(f"{'day':<12}{'date':<12}{'charge $':>10}{'discharge $':>12}{'net $':>9}"
          f"{'charge hrs':>13}{'disch hrs':>12}{'key hour':>10}")
    total_net = total_cost = total_rev = 0.0
    for i, d in enumerate(days, 1):
        print(f"{'day ' + str(i):<12}{d['date']:<12}{d['charge_cost']:>10.2f}"
              f"{d['discharge_revenue']:>12.2f}{d['net']:>9.2f}"
              f"{str(d['charge_hours']):>13}{str(d['discharge_hours']):>12}"
              f"{'HE' + str(d['key_hour']) + ' ' + d['key_kind']:>10}")
        total_net += d["net"]; total_cost += d["charge_cost"]; total_rev += d["discharge_revenue"]
    print(f"{'TOTAL':<12}{'':<12}{total_cost:>10.2f}{total_rev:>12.2f}{total_net:>9.2f}")
    return total_net


def check_scarcity(days):
    spikes = [d for d in days if d["max_price"] > 500]  # ERCOT scarcity territory, $/MWh
    if spikes:
        print("\nScarcity spike present:")
        for d in spikes:
            print(f"  {d['date']}: peak {d['max_price']:.0f} $/MWh")
    else:
        top = max(d["max_price"] for d in days)
        print(f"\nNo scarcity spike in this data (highest hourly price seen: {top:.0f} $/MWh, "
              f"well under ERCOT's scarcity range of $1,000+/MWh). Both days are ordinary demand days.")


if __name__ == "__main__":
    # 7 days built from the 2 real ERCOT DAM days on file, cycled and labeled.
    sequence = ["2026-09-07", "2026-09-09", "2026-09-07", "2026-09-09",
                "2026-09-07", "2026-09-09", "2026-09-07"]

    aen_days = run_week("lzAen", sequence)
    net_aen = print_table("LZ_AEN (Austin Energy)", aen_days)
    check_scarcity(aen_days)

    north_days = run_week("lzNorth", sequence)
    net_north = print_table("LZ_NORTH (Dallas, Oncor comparison)", north_days)
    check_scarcity(north_days)

    print(f"\nSummary: LZ_AEN battery earned ${net_aen:.2f} net over 7 days "
          f"({net_aen/7:.2f}/day average). LZ_NORTH earned ${net_north:.2f} net "
          f"({net_north/7:.2f}/day average).")
