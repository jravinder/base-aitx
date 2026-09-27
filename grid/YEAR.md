# A year of ERCOT prices, one battery

Numbers from `python3 grid/year.py`. Prices: ERCOT public report 13060, "Historical DAM Load Zone and Hub Prices" (NP4-180-ER), no login. Listing: https://www.ercot.com/misapp/GetReports.do?reportTypeId=13060 . Files: `DAMLZHBSPP_2025.zip` (full 2025, 2.0 MB) and `DAMLZHBSPP_2026.zip` (posted 2026-09-20, data to 2026-09-19, 1.5 MB). `grid/ercot_archive.py` extracts LZ_AEN, LZ_NORTH and LZ_HOUSTON hourly day-ahead prices to `data/ercot_dam_hourly_2025_2026.csv` (627 days, 15,046 hours).

Battery: one Base Core, 39.2 kWh, 10 kW, 30% reserve kept (from `sim/fleet.py`). Logic: `grid/earned.py` `simulate_day`, imported: one cycle a day, charge in the cheapest 3 hours, discharge in the most expensive 3 hours, 9.15 kWh an hour. Day-ahead energy only. Check: the script gives $1.62 for Sep 7 and $2.04 for Sep 9 on LZ_AEN, the same as `grid/EARNED.md`.

Data path: no data on this page came through the `gridstatus` library. The report 13060 zips were already fetched directly (plain HTTPS, no login, no key) before gridstatus was proposed, so it was not installed. gridstatus wraps the same ERCOT public archives; use it if the RTM archive (report 13061) is added later.

## Annual $ per battery

| zone | 2025 (365 days) | $/day 2025 | 2026 to Sep 19 (262 days) | last 365 days (2025-09-20 to 2026-09-19) |
|---|---|---|---|---|
| LZ_AEN | **$603.45** | 1.65 | $391.26 | $558.67 |
| LZ_NORTH | **$546.22** | 1.50 | $404.94 | $542.88 |
| LZ_HOUSTON | **$501.88** | 1.38 | $342.01 | $467.38 |

## Share of annual $ from the top 10 price days

Top 10 days = the 10 days with the highest hourly DAM price in that zone.

| zone | 2025: top 10 days $ | share of 2025 | last 365 days: top 10 days $ | share of last 365 |
|---|---|---|---|---|
| LZ_AEN | $85.04 | 14.1% | $138.42 | 24.8% |
| LZ_NORTH | $78.81 | 14.4% | $132.70 | 24.4% |
| LZ_HOUSTON | $71.01 | 14.1% | $112.28 | 24.0% |

10 days are 2.7% of the year. In 2025 they earned about 14% of the money. In the last 365 days, which hold the January 2026 price spike, they earned about 25%. The single best day, 2026-01-26, earned $53.01 on LZ_AEN: the same as 34 ordinary days.

## Scarcity hours (DAM price over the threshold)

| zone | 2025 >$200 | 2025 >$500 | 2025 >$1,000 | 2026 YTD >$200 | 2026 YTD >$500 | 2026 YTD >$1,000 | max $/MWh |
|---|---|---|---|---|---|---|---|
| LZ_AEN | 44 | 6 | 0 | 73 | 36 | 15 | 2,160.97 |
| LZ_NORTH | 27 | 6 | 0 | 69 | 22 | 14 | 1,937.00 |
| LZ_HOUSTON | 23 | 4 | 0 | 62 | 17 | 9 | 1,694.30 |

By month (hours over $200 / $500 / $1,000). Months with no hour over $200 in any zone are left out.

| month | LZ_AEN | LZ_NORTH | LZ_HOUSTON |
|---|---|---|---|
| 2025-02 | 6 / 2 / 0 | 6 / 2 / 0 | 5 / 2 / 0 |
| 2025-03 | 2 / 0 / 0 | 2 / 0 / 0 | 2 / 0 / 0 |
| 2025-04 | 4 / 0 / 0 | 3 / 0 / 0 | 1 / 0 / 0 |
| 2025-05 | 13 / 2 / 0 | 4 / 2 / 0 | 3 / 2 / 0 |
| 2025-06 | 1 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| 2025-07 | 5 / 2 / 0 | 4 / 2 / 0 | 3 / 0 / 0 |
| 2025-08 | 9 / 0 / 0 | 8 / 0 / 0 | 8 / 0 / 0 |
| 2025-11 | 3 / 0 / 0 | 0 / 0 / 0 | 1 / 0 / 0 |
| 2025-12 | 1 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| 2026-01 | 59 / 36 / 15 | 54 / 20 / 14 | 50 / 17 / 9 |
| 2026-04 | 11 / 0 / 0 | 11 / 2 / 0 | 9 / 0 / 0 |
| 2026-07 | 3 / 0 / 0 | 4 / 0 / 0 | 3 / 0 / 0 |

All 2025 scarcity was short: 44 hours over $200 on LZ_AEN, none over $1,000. January 2026 alone had 59 hours over $200 and 15 over $1,000 on LZ_AEN.

## Top 10 price days (ranked by LZ_AEN peak hour)

| date | peak hour | LZ_AEN peak | LZ_NORTH peak | LZ_HOUSTON peak | battery $ LZ_AEN | LZ_NORTH | LZ_HOUSTON |
|---|---|---|---|---|---|---|---|
| 2026-01-26 | HE8 | 2,160.97 | 1,937.00 | 1,694.30 | 53.01 | 47.22 | 38.23 |
| 2026-01-25 | HE23 | 1,583.34 | 1,574.13 | 1,308.68 | 28.79 | 30.71 | 27.58 |
| 2025-02-20 | HE7 | 793.50 | 959.39 | 788.76 | 16.39 | 19.22 | 15.28 |
| 2025-05-20 | HE20 | 542.58 | 538.06 | 537.08 | 11.00 | 10.97 | 10.89 |
| 2025-07-30 | HE20 | 520.92 | 507.92 | 463.30 | 12.70 | 12.36 | 11.24 |
| 2026-04-27 | HE20 | 485.56 | 529.59 | 457.55 | 12.27 | 13.54 | 11.28 |
| 2026-01-24 | HE23 | 406.29 | 434.69 | 305.13 | 8.76 | 8.99 | 6.17 |
| 2026-01-27 | HE8 | 347.78 | 274.75 | 258.75 | 7.29 | 5.76 | 5.18 |
| 2025-08-19 | HE20 | 312.01 | 298.99 | 293.19 | 7.61 | 7.26 | 6.88 |
| 2025-04-14 | HE20 | 296.71 | 122.29 | 109.05 | 6.79 | 2.21 | 1.91 |

## Battery $ by month (LZ_AEN)

| month | $ | month | $ |
|---|---|---|---|
| 2025-01 | 37.78 | 2025-12 | 39.72 |
| 2025-02 | 43.93 | 2026-01 | 126.92 |
| 2025-03 | 46.20 | 2026-02 | 23.38 |
| 2025-04 | 54.50 | 2026-03 | 34.38 |
| 2025-05 | 68.03 | 2026-04 | 52.37 |
| 2025-06 | 42.01 | 2026-05 | 31.15 |
| 2025-07 | 54.32 | 2026-06 | 21.21 |
| 2025-08 | 65.29 | 2026-07 | 35.87 |
| 2025-09 | 45.53 | 2026-08 | 43.05 |
| 2025-10 | 53.27 | 2026-09 | 22.93 |
| 2025-11 | 52.86 |  |  |

2026-09 runs to Sep 19 only.

## What the three days in the sim miss

The sim (`sim/fleet.py`) prices Sep 7, Sep 9 and Sep 26 2026. On LZ_AEN they earn $1.62, $2.04, $0.95 (mean $1.54 a day), with peaks of $88, $109, $60 /MWh.

- **The mean is right.** 2025 averaged $1.65 a day and the last 365 days $1.53. So the sim's energy $ a day is a fair typical day. The median day is lower: $1.26 (2025), $0.89 (2026 YTD).
- **The tail is missing.** No sim hour is over $109/MWh. The year had 77 LZ_AEN hours over $200 in the last 365 days and a peak of $2,160.97. The top 10 days carry 14% (2025) to 25% (last 365) of the annual $. A 3-day sim can not show that, because the value is in a few days that it does not hold.
- **Season is missing.** September is a calm month (2025-09: $45.53; 2026-09 to date: $22.93). January 2026 ($126.92) was worth more than 5 times September 2026 to date.
- **The daily cycle is fixed.** `simulate_day` moves 27.44 kWh once, in fixed 3-hour windows. On 2026-01-26 the peak was HE8 (morning) and on 2026-01-25 it was HE23, so a real dispatcher that cycles twice or holds charge for the peak gets more on the days that matter.

## The ceiling

This is day-ahead energy arbitrage only, about $603 a year per battery on LZ_AEN. Two things this data can not show: real-time prices (15-minute spikes are larger than hourly DAM prices; report 13061 is the RTM archive) and ancillary services (RRS, ECRS, regulation), which pay for standing ready. So treat $603 as a floor. We can not state the ceiling from this data; to get it, price the same battery against RTM and ancillary service clearing prices.
