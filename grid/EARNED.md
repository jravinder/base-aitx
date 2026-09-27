# What your battery earned this week

Grid Data chapter for Issue #39. Numbers from `grid/earned.py`, one battery, one arbitrage cycle a day: charge in the cheapest 3 hours, discharge in the priciest 3 hours.

Battery: Base Core, 39.2 kWh ("39.2 kWh in every Base Core", basepowercompany.com), 10 kW charge/discharge, 30% member reserve kept. This is the same spec as `sim/fleet.py` (`CAPACITY_KWH`, `RATE_KW`, `RESERVE`); `grid/earned.py` imports it. 27.44 kWh usable per cycle, moved as 9.15 kWh/hour across a 3-hour window. The 10 kW rating has no public source. Earlier versions of this page used a 30 kWh / 11 kW / 80% DoD pack from an interview ($8.66 a week on LZ_SOUTH); see `grid/NUMBERS.md`.

Zone: LZ_AEN (Austin Energy load zone), the zone the sim prices. LZ_NORTH (Dallas, Oncor territory) is the comparison.

## Source

Real ERCOT day-ahead settlement point prices (`damSppData`), hourly, $/MWh, from `data/ercot-dam-2026-09-07.json` and `data/ercot-dam-2026-09-09.json`. Source: https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD

No no-login live source exists. That page and `https://api.ercot.com` both require MIS portal login or an API key. The repo has only 2 real ERCOT days on file, so the 7-day table below **cycles those 2 real days** (07, 09, 07, 09, 07, 09, 07) rather than inventing new numbers. This is labeled, not hidden: it is real ERCOT data, repeated.

## LZ_AEN (Austin Energy load zone), 7 days

| day | date | charge $ | discharge $ | net $ | charge hrs | discharge hrs | key hour |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-07 | 0.63 | 2.25 | 1.62 | 9,10,11 | 19,20,21 | HE20 discharge |
| 2 | 2026-09-09 | 0.72 | 2.76 | 2.04 | 9,10,11 | 20,21,22 | HE20 discharge |
| 3 | 2026-09-07 | 0.63 | 2.25 | 1.62 | 9,10,11 | 19,20,21 | HE20 discharge |
| 4 | 2026-09-09 | 0.72 | 2.76 | 2.04 | 9,10,11 | 20,21,22 | HE20 discharge |
| 5 | 2026-09-07 | 0.63 | 2.25 | 1.62 | 9,10,11 | 19,20,21 | HE20 discharge |
| 6 | 2026-09-09 | 0.72 | 2.76 | 2.04 | 9,10,11 | 20,21,22 | HE20 discharge |
| 7 | 2026-09-07 | 0.63 | 2.25 | 1.62 | 9,10,11 | 19,20,21 | HE20 discharge |
| **Total** | | **4.70** | **17.28** | **12.58** | | | |

LZ_NORTH (Dallas, Oncor comparison) total over the same 7 days: $4.34 charge, $17.27 discharge, **$12.93 net**.

No scarcity spike in this data: highest hourly price seen was $109/MWh (LZ_AEN, Sep 9 HE20; $108.57 raw), far under ERCOT's scarcity range of $1,000+/MWh. Both source days are ordinary demand days.

## The ceiling

This is simple energy arbitrage only: buy low, sell high, once a day. Real Base dispatch also earns from ERCOT ancillary services (regulation, responsive reserve, ECRS) and demand response events, which pay for standing ready, not just for energy moved, and would have captured value on days with no price spread at all. Our 3-hour/3-hour window is also a simplification: real dispatch can react hour-by-hour and would shift windows on a scarcity day. Treat the ~$1.60-2.10/day net shown here as a floor, not a target.
