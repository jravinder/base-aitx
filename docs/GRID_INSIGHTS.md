# What most people miss in ERCOT's public data

Six findings measured from public ERCOT data already in this repo. Nothing new was fetched.

Run: `python3 grid/insights.py` (writes `web/data/grid_insights.json`; shown on `web/grid.html#missed`).

Battery for the $ figures: one Base Core, 39.2 kWh, 10 kW, 30% reserve kept, one cycle a day, day-ahead energy only (`grid/earned.py` `simulate_day`).

## 1. A few days carry the year

**The best 4 days (1% of the year) made 18% of one battery's day-ahead arbitrage value on LZ_AEN; the best 37 days (10%) made 39%.**

The median day made $1.02; the best day made $53.01. The top 50 hours hold 25% of all price-above-daily-average dollars.

- Method: earned.simulate_day on each of the last 365 days (one cycle, cheapest 3 hours in, dearest 3 out, 27.4 kWh usable); days sorted by value, cumulative share. Hour view: each hour's price above its day's mean.
- Why it matters for Base: Dispatch: one scarcity day is worth more than a month of ordinary cycling, so being charged and available on forecast spike days is the first dispatch rule; daily optimisation comes second.
- Sources: data/ercot_dam_hourly_2025_2026.csv (ERCOT report 13060, DAM load zone prices)
- Range: 2025-09-20 to 2026-09-19
- Result: held

## 2. Price peaks after load peaks

**In 9 of 12 months the typical day-ahead price peak comes later than the load peak, by up to 4 hours in summer; the summer 8 pm price is 2.3x the 1 pm price.**

Load peaks late afternoon; price peaks as solar fades and net load climbs into the evening. Load peak hour and price peak hour by month are in the chart.

- Method: Per calendar month (2025 to 2026 pooled): hour with the highest mean ERCOT total load, and hour with the highest median LZ_AEN DAM price (median so one spike day does not decide). Summer ratio = median HE20 / median HE13 price, Jun to Sep.
- Why it matters for Base: Dispatch: holding charge through the load peak and discharging into HE19 to HE21 captures the net-load ramp; dispatch keyed to the price curve, not the load curve, captures it.
- Sources: data/ercot_dam_hourly_2025_2026.csv (ERCOT report 13060, DAM load zone prices); data/ercot_load_hourly_2024_2026.csv (ERCOT Native Load by weather zone)
- Range: prices 2025-01-01 to 2026-09-19; load 2025-01-01 to 2026-08-31
- Result: held

## 3. The cheap hours are at midday

**73% of each day's three cheapest day-ahead hours on LZ_AEN fall between 10 am and 4 pm; only 12% fall overnight (1 am to 6 am).**

2026 so far: 75% midday, 8% overnight. Peak month: 2026-03 at 92% midday.

- Method: earned.simulate_day on LZ_AEN each day; its 3 cheapest hours counted as overnight (HE1 to HE6) or midday (HE10 to HE16), share per month.
- Why it matters for Base: Members and dispatch: a battery can refill from midday prices, often from the member's own solar, and still be full for the evening peak; overnight charging is now the more costly habit.
- Sources: data/ercot_dam_hourly_2025_2026.csv (ERCOT report 13060, DAM load zone prices)
- Range: 2025-01-01 to 2026-09-19
- Result: held

## 4. Zones split in bursts, not every day

**Austin, Dallas and Houston day-ahead prices sit within $5/MWh of each other in 67% of hours; the other 33% of hours carry the congestion, and the top 1% of hours hold 20% of all spread dollars.**

Spread is widest at HE17 (mean $14.53/MWh) and narrowest at HE24 ($3.29). When zones split by more than $5, LZ_AEN is the dearest zone 53% of the time. Hours over $20 apart: 1068.

- Method: For every hour, max minus min of the three load-zone DAM prices. Share of hours over $5 and $20; mean spread by hour ending; which zone is dearest when the spread is over $5.
- Why it matters for Base: Siting: a battery in the zone that is dearest during split hours earns the congestion premium; fleet dispatch should read the member's own zone, not the hub.
- Sources: data/ercot_dam_hourly_2025_2026.csv (ERCOT report 13060, DAM load zone prices)
- Range: 2025-01-01 to 2026-09-19
- Result: held

Note: The CSV holds three zones (AEN, NORTH, HOUSTON). LZ_SOUTH and LZ_WEST exist only in one-day dashboard snapshots, so they are left out of the year view.

## 5. Near-free hours cluster at winter middays

**277 day-ahead hours on LZ_AEN cleared at $5/MWh or less (37 at or below zero); 89% of them fall between 10 am and 4 pm.**

Busiest months: Feb 103, Jan 84, Mar 49 hours. Day-ahead prices only.

- Method: Count of LZ_AEN DAM hours at or below $5/MWh and at or below $0, grouped by hour ending and month.
- Why it matters for Base: Dispatch and members: these are the hours to fill batteries and shift home load (EV, pool pump) toward.
- Sources: data/ercot_dam_hourly_2025_2026.csv (ERCOT report 13060, DAM load zone prices)
- Range: 2025-01-01 to 2026-09-19
- Result: held

## 6. The priciest hours came in winter

**Winter had 15 day-ahead hours over $1,000/MWh on LZ_AEN, summer had 0; winter days averaged $1.82 of arbitrage vs $1.42 in summer.**

The $1,000 hours all fall in 2026-01. Hours over $200: winter 66, summer 18 of 117. Weekdays averaged $1.68 a day, weekends $1.35.

- Method: LZ_AEN DAM hours over $200 and $1,000 by season; earned.simulate_day value averaged per day by season and by weekday vs weekend. 2025-01-01 to 2026-09-19 (two winters partly, one full summer plus 2026 to Sep 19).
- Why it matters for Base: Reserve policy and members: winter cold snaps pay most and hurt most; hold backup reserve through winter fronts, not just summer heat.
- Sources: data/ercot_dam_hourly_2025_2026.csv (ERCOT report 13060, DAM load zone prices)
- Range: 2025-01-01 to 2026-09-19
- Result: held

## Candidates tested that need more history

- Reserves vs price: Supply-demand history holds 289 five-minute intervals (2026-09-26 to 2026-09-27); the tightest margin was 13,623 MW, far from scarcity, so a reserve threshold effect needs more history.
- Wind and solar share at peak-price hours: Fuel-mix history covers 2 days (2026-09-25, 2026-09-26); a year of generation mix next to the year of prices would test it.
