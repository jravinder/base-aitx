# ERCOT live pull

## Run command

```
node grid/ercot_live.js
```

This opens headless Chromium, loads https://www.ercot.com, then fetches the
systemWidePrices JSON from inside the page context. It saves one file per
operating day found in the data, as `data/ercot-dam-<date>.json`, in the same
format as existing files (`lastUpdated`, `rtSppData`, `damSppData`). It never
overwrites a file that already exists.

## All dashboard feeds: `node grid/ercot_system.js`

Loads https://www.ercot.com/gridmktinfo/dashboards in headless Chromium, records every JSON
feed the page requests under `/api/1/services/read/dashboards/`, and saves each one to
`data/ercot/<feed>-<date>.json` (date in Central time; a rerun the same day overwrites).
No login. Then `python3 grid/today.py` compacts them to `web/data/grid_today.json` for
`web/grid.html`. First run 2026-09-26 16:13 CT saved 11 feeds:

- `system-wide-prices` - today's DAM hourly and RT 15-minute settlement point prices, all hubs and load zones (LZ_AEN, LZ_NORTH, LZ_HOUSTON and others).
- `supply-demand` - today's 5-minute demand vs. available capacity (MW), plus a 6-day hourly forecast of demand and available generation.
- `daily-prc` - Physical Responsive Capability (MW of fast reserves) every ~10 s today, and the current grid condition (Normal / Conservation / EEA level) with ERCOT's plain-language note.
- `fuel-mix` - generation by fuel (gas, coal, nuclear, wind, solar, hydro, storage, other) every 5 minutes for yesterday and today, and installed capacity by fuel this month.
- `combine-wind-solar` - hourly actual wind and solar output vs. ERCOT forecasts (STWPF, STPPF, COP) for today and tomorrow.
- `generation-outages` - MW of generation out, planned vs. unplanned, dispatchable vs. renewable, every 5 minutes for today and the prior 6 days.
- `energy-storage-resources` - grid batteries' total charging, discharging and net output every 5 minutes, yesterday and today.
- `ancillary-services` - system frequency, and reserves on hand every 10 s: RRS, ECRS, Non-Spin, Reg-Up and Reg-Down (deployed and undeployed).
- `system-wide-demand` - hourly system load vs. current and day-ahead load forecast, and HSL capacity, for yesterday, today and tomorrow.
- `dc-tie-flows` - MW on the DC ties to other grids (East, North, Laredo, Railroad) and system inertia, every ~15 s.
- `weather-forecast` - today's high and low for 12 Texas cities (Austin included) vs. the 15-year normal.

For a home battery the useful ones are prices, supply-demand, daily-prc (grid condition),
outages, wind-solar and fuel-mix: they say when the grid is tight and when prices spike.

## History: report 13060

ERCOT posts a year of DAM load zone and hub prices as a public zip, no login:
https://www.ercot.com/misapp/GetReports.do?reportTypeId=13060 . See `grid/ercot_archive.py`
and `grid/YEAR.md`.
