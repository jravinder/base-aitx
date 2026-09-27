"""Grid Data chapter: what one library node earns per week.

Issue #47, tasks 3 and 4. Reuses grid/earned.py for the battery arbitrage math
and the same 2 real ERCOT DAM days (2026-09-07, 2026-09-09), cycled to fill 7
days, same as EARNED.md. Reuses grid/RATES.md for GPU tier $/hour rates.

A library node = 4 batteries + 4 GPUs, one per sourced tier (business, base,
partner, external), sited at a public library so it can serve both the grid
and any small business within one hop of that library.

A house node = 1 battery + 1 GPU (business tier), for comparison. This is the
same battery math as EARNED.md's single-battery table, plus one GPU added so
the two node types compare on the same footing (power + compute).

ASSUMPTIONS (stated, not hidden):
  - GPU utilization: 40% of wall-clock hours. This is a stated planning
    assumption, not measured fleet data. No utilization telemetry exists in
    this repo yet (see EARNED.md ceiling note: real dispatch data would
    replace this).
  - GPU electricity draw: 350 W per GPU under load (typical consumer/
    workstation-class card draw, e.g. RTX 4090-class TDP). Idle hours are
    not charged.
  - Electricity cost for running the GPU is charged at the average LZ_AEN
    ERCOT DAM price across the same 7-day window used for the battery
    (mean of the two real days on file, cycled), NOT the arbitrage
    charge-window price, because GPU hours run whenever a job arrives, not
    only during the battery's 3-hour charge window.
  - GPU tier assignment for the library node's 4 GPUs: business, base,
    partner, external (skips "member", which is the homeowner's own local
    rate, not a rate the library would sell at). This gives one node that
    can serve every non-member customer class at once.
  - House node GPU: business tier only, one GPU, since a single house is one
    customer relationship, not four simultaneous tiers.
"""

import json
import os

import earned

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")

# ---- Rates, sourced from grid/RATES.md ----
GPU_TIER_RATES = {
    "business": 1.09,   # Lambda A6000 on-demand
    "base": 0.79,        # RunPod L40S community
    "partner": 0.34,     # RunPod RTX 4090 community
    "external": 0.16,    # RunPod RTX A5000 community
}

LIBRARY_NODE_GPUS = ["business", "base", "partner", "external"]
HOUSE_NODE_GPUS = ["business"]

UTILIZATION = 0.40          # stated assumption, see module docstring
GPU_DRAW_KW = 0.350         # 350 W, stated assumption
HOURS_PER_WEEK = 24 * 7


def avg_lz_aen_price_per_kwh(date_sequence):
    """Average $/kWh across all hours of the cycled 7-day window, LZ_AEN."""
    total = 0.0
    count = 0
    for date in date_sequence:
        hours = earned.load_day(date, "lzAen")  # [(hourEnding, $/kWh), ...]
        for _, price in hours:
            total += price
            count += 1
    return total / count


def battery_week_net(num_batteries, date_sequence):
    days = earned.run_week("lzAen", date_sequence)
    total_net = sum(d["net"] for d in days)
    return total_net * num_batteries


def gpu_week(tiers, utilization, draw_kw, elec_price_per_kwh):
    """Returns per-tier dict of revenue, electricity cost, and net."""
    gpu_hours_active = HOURS_PER_WEEK * utilization
    rows = []
    total_revenue = total_elec_cost = 0.0
    for tier in tiers:
        rate = GPU_TIER_RATES[tier]
        revenue = rate * gpu_hours_active
        elec_cost = draw_kw * gpu_hours_active * elec_price_per_kwh
        net = revenue - elec_cost
        rows.append({
            "tier": tier,
            "rate_per_hour": rate,
            "active_hours": gpu_hours_active,
            "revenue": revenue,
            "electricity_cost": elec_cost,
            "net": net,
        })
        total_revenue += revenue
        total_elec_cost += elec_cost
    return rows, total_revenue, total_elec_cost


def build_node(name, num_batteries, gpu_tiers, date_sequence, elec_price):
    battery_net = battery_week_net(num_batteries, date_sequence)
    gpu_rows, gpu_revenue, gpu_elec_cost = gpu_week(
        gpu_tiers, UTILIZATION, GPU_DRAW_KW, elec_price
    )
    gpu_net = gpu_revenue - gpu_elec_cost
    total = battery_net + gpu_net
    return {
        "name": name,
        "num_batteries": num_batteries,
        "battery_net_weekly": round(battery_net, 2),
        "gpu_tiers": gpu_rows,
        "gpu_revenue_weekly": round(gpu_revenue, 2),
        "gpu_electricity_cost_weekly": round(gpu_elec_cost, 2),
        "gpu_net_weekly": round(gpu_net, 2),
        "total_weekly": round(total, 2),
        "utilization_assumption": UTILIZATION,
        "gpu_draw_kw_assumption": GPU_DRAW_KW,
        "electricity_price_per_kwh": round(elec_price, 5),
    }


def print_node_table(node):
    print(f"\n{node['name']}")
    print(f"  batteries: {node['num_batteries']}  battery net/week: ${node['battery_net_weekly']:.2f}")
    print(f"  {'tier':<10}{'rate $/hr':>11}{'active hrs':>12}{'revenue $':>11}{'elec cost $':>13}{'net $':>9}")
    for r in node["gpu_tiers"]:
        print(f"  {r['tier']:<10}{r['rate_per_hour']:>11.2f}{r['active_hours']:>12.1f}"
              f"{r['revenue']:>11.2f}{r['electricity_cost']:>13.2f}{r['net']:>9.2f}")
    print(f"  GPU revenue: ${node['gpu_revenue_weekly']:.2f}  GPU electricity cost: "
          f"${node['gpu_electricity_cost_weekly']:.2f}  GPU net: ${node['gpu_net_weekly']:.2f}")
    print(f"  TOTAL weekly (battery + GPU): ${node['total_weekly']:.2f}")


if __name__ == "__main__":
    sequence = ["2026-09-07", "2026-09-09", "2026-09-07", "2026-09-09",
                "2026-09-07", "2026-09-09", "2026-09-07"]
    elec_price = avg_lz_aen_price_per_kwh(sequence)
    print(f"Average LZ_AEN price over the 7-day window: ${elec_price:.5f}/kWh "
          f"(${elec_price*1000:.2f}/MWh)")

    library = build_node("Library node (4 batteries + 4 GPUs: business/base/partner/external)",
                          4, LIBRARY_NODE_GPUS, sequence, elec_price)
    house = build_node("House node (1 battery + 1 GPU: business)",
                        1, HOUSE_NODE_GPUS, sequence, elec_price)

    print_node_table(library)
    print_node_table(house)

    out = {
        "electricity_price_per_kwh_lz_aen_avg": round(elec_price, 5),
        "library_node": library,
        "house_node": house,
    }
    out_path = os.path.join(DATA, "library_node.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path}")
