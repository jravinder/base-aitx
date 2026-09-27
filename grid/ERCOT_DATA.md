# ERCOT public data catalog

Public, no-login data useful to a home-battery fleet project. Sources: ercot.com/gridmktinfo
(dashboards), ercot.com/gridinfo (load, generation), ercot.com/mktinfo (market reports), plus
two third-party mirrors of the same public data (gridstatus, PUDL).

| Name | URL | Format | Cadence | Login needed | Ingested today | Use for a home-battery fleet |
|---|---|---|---|---|---|---|
| System-wide prices dashboard | https://www.ercot.com/api/1/services/read/dashboards/system-wide-prices.json | JSON | ~5 min (RT), hourly (DAM) | No | Yes, `data/ercot/system-wide-prices-*.json` via `grid/ercot_system.js` | Live signal for when to discharge for arbitrage. |
| Supply vs. demand dashboard | https://www.ercot.com/api/1/services/read/dashboards/supply-demand.json | JSON | 5 min, plus 6-day forecast | No | Yes, `data/ercot/supply-demand-*.json` | Tells you how tight the grid is right now and over the next week; discharge trigger. |
| Daily PRC / grid condition | https://www.ercot.com/api/1/services/read/dashboards/daily-prc.json | JSON | ~10 sec | No | Yes, `data/ercot/daily-prc-*.json` | Grid condition flag (Normal/Conservation/EEA); hard trigger to hold reserve or discharge to grid. |
| Fuel mix | https://www.ercot.com/api/1/services/read/dashboards/fuel-mix.json | JSON | 5 min, yesterday+today | No | Yes, `data/ercot/fuel-mix-*.json` | Shows renewable share; low wind/solar plus high demand = highest price risk. |
| Wind and solar actual vs. forecast | https://www.ercot.com/api/1/services/read/dashboards/combine-wind-solar.json | JSON | Hourly, today+tomorrow | No | Yes, `data/ercot/combine-wind-solar-*.json` | Forecast solar/wind shortfall the evening before to plan discharge. |
| Generation outages | https://www.ercot.com/api/1/services/read/dashboards/generation-outages.json | JSON | 5 min, today + 6 days | No | Yes, `data/ercot/generation-outages-*.json` | Large unplanned outages raise scarcity price risk. |
| Energy storage resources | https://www.ercot.com/api/1/services/read/dashboards/energy-storage-resources.json | JSON | 5 min, yesterday+today | No | Yes, `data/ercot/energy-storage-resources-*.json` | Shows how grid-scale batteries are already behaving; a leading indicator. |
| Ancillary services | https://www.ercot.com/api/1/services/read/dashboards/ancillary-services.json | JSON | ~10 sec | No | Yes, `data/ercot/ancillary-services-*.json` | Frequency and reserve levels; a home battery in a VPP program can watch this for dispatch signals. |
| System-wide demand | https://www.ercot.com/api/1/services/read/dashboards/system-wide-demand.json | JSON | Hourly, yesterday/today/tomorrow | No | Yes, `data/ercot/system-wide-demand-*.json` | Load forecast vs. actual and HSL capacity; near-term peak warning. |
| DC tie flows | https://www.ercot.com/api/1/services/read/dashboards/dc-tie-flows.json | JSON | ~15 sec | No | Yes, `data/ercot/dc-tie-flows-*.json` | Interconnection flow and system inertia; secondary stress signal. |
| Weather forecast (12 TX cities) | https://www.ercot.com/api/1/services/read/dashboards/weather-forecast.json | JSON | Daily | No | Yes, `data/ercot/weather-forecast-*.json` | Extreme high/low forecast drives next-day peak-demand planning. |
| Native Load history (by weather zone) | https://www.ercot.com/gridinfo/load/load_hist | XLSX/ZIP per year | Annual, one file per year, updated during the year | No | Yes, `data/ercot_load_hourly_2024_2026.csv` (2024-2026 YTD) | Historical hourly load by zone (SCENT/NCENT/COAST/etc.); establishes when annual peaks happen, for reserve/discharge scheduling (see `grid/LOAD.md`). |
| DAM/RTM settlement point price archive (report 13060) | https://www.ercot.com/misapp/GetReports.do?reportTypeId=13060 | ZIP of CSVs, one year each | Annual archive, updated through the year | No | Yes, see `grid/YEAR.md` / `grid/ercot_archive.py` | Full-year hourly DAM and RTM prices by load zone/hub; needed to backtest a battery arbitrage or VPP strategy against real dispatch decisions. |
| Hourly load history, pre-2015 | https://www.ercot.com/files/docs/2015/10/22/*_ercot_hourly_load_data.xls | XLS, one per year 2002-2014 | Static archive | No | No | Long-run baseline load growth; low value for current battery sizing, useful only for long-horizon trend context. |
| Generation by fuel type, installed capacity | Included in fuel-mix dashboard ("this month" capacity block) | JSON | Monthly | No | Yes (same feed as fuel-mix) | Tracks how much dispatchable vs. renewable capacity ERCOT can call on; slow-moving context for scarcity risk. |
| Weather zone / forecast zone maps | https://www.ercot.com/gridinfo/weather (zone definitions, PDFs/maps) | PDF/HTML | Static, rarely updated | No | No | Confirms which counties/cities map to SCENT/NCENT/COAST for matching a fleet site to the right zone. |
| gridstatus (third-party, Python library) | https://github.com/gridstatus/gridstatus | Python package, wraps ERCOT public data into pandas DataFrames | Library releases, pulls live from ERCOT on call | No (mirrors ERCOT's own no-login public data) | No | Third-party mirror/parser for ERCOT (and other ISO) load, price, and generation data; useful to skip writing our own scraping/parsing code for load-by-weather-zone and price archives. |
| PUDL (third-party, Catalyst Cooperative) | https://catalyst.coop/pudl/ | Parquet/SQLite bulk download, includes EIA-861 service territories | Periodic releases | No | No | Third-party cleaned mirror of EIA-861 utility service territory data and other public utility data; useful to map ERCOT weather zones and utilities to actual service-territory boundaries for siting a battery fleet. |

18 rows.

## Notes

- All dashboard feeds above are unauthenticated JSON hit directly or via headless Chromium (see
  `grid/ercot_system.js` / `grid/ERCOT_LIVE.md`); `collect/ercot_feeds.sh` pulls a subset (prices,
  supply-demand, fuel-mix hourly, daily-prc once a day) with plain curl, no browser needed.
- gridstatus and PUDL are not ERCOT itself; they are open-source projects that already parse the
  same public ERCOT/EIA files this project pulls directly. They are listed here as a reuse option,
  not as a currently ingested source.
