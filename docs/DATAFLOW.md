# Data flow

Page: `web/dataflow.html`. Date: 2026-09-26.

**Where does every number on this site come from?**
Public records in, one database in the middle, small files out to the pages.

## The seven steps

1. **Sources.** Eight public sources. None needs a login.
2. **Collectors.** Three launchd jobs on the Mac (hourly, daily, monthly), plus scripts that someone runs by hand.
3. **Raw and mirror files.** `data/live/` (snapshots and `collect.log`, gitignored), `data/mirror/` (permit and deed rows), `data/*.json` and `data/*.csv`, `faq/corpus/`.
4. **One database.** `data/fleet.db` (SQLite). `store/build.py` loads each file with natural keys, so a second run gives the same rows.
5. **Derived.** Signals (`store/signals.py`), judgments with confidence routing (`store/judgments.py`), the easy-fit funnel (`house/funnel.py`), member records (`brain/members.py`), the fleet sim (`sim/`), and page builders (`grid/today.py`, `grid/year.py`, `house/mirror.py`, `store/feeds.py`).
6. **Page files.** Small JSON in `web/data/` and `data/`.
7. **Pages.** Each page reads only page files, or a local server on the Mac.

## Sources

| Source | URL | Cadence | Script | Output | Rows | Caveat |
|---|---|---|---|---|---|---|
| City of Austin permits | https://data.austintexas.gov/resource/3syk-w9eu.json | Daily 06:15 (com.basefleet.daily) | house/mirror.py --incremental, house/market.py, house/permits_by_zip.py | data/mirror/energy_permits.csv.gz, data/market.json, data/permits_by_zip.json | 34,334 energy permits since 2015 (31,338 with a location); 316 Base permits in 2026; 27 zips | Austin only. No open permit feed with the contractor name in Oncor and CenterPoint cities (#57). |
| ERCOT system-wide prices, supply-demand, fuel mix | https://www.ercot.com/api/1/services/read/dashboards/system-wide-prices.json (and supply-demand.json, fuel-mix.json) | Hourly at :07 (com.basefleet.ercot) | collect/ercot_feeds.sh | data/live/ercot/<feed>/<UTC>.json.gz | 1 snapshot per feed per hour | Use the hyphen URL. The camel-case URL redirects to a bot wall. |
| ERCOT daily-prc | https://www.ercot.com/api/1/services/read/dashboards/daily-prc.json | Daily at 12 UTC | collect/ercot_feeds.sh | data/live/ercot/daily-prc/ | 0 so far | Stale until the first 12 UTC run. low_reserves fires nothing until then. |
| ERCOT dashboards, full set | https://www.ercot.com/gridmktinfo/dashboards | One pull | grid/ercot_system.js | data/ercot/*.json | 11 feeds | Snapshot only. |
| ERCOT DAM archive (report 13060) | https://www.ercot.com/misapp/GetReports.do?reportTypeId=13060 | One pull (annual archive) | grid/ercot_archive.py | data/ercot_dam_hourly_2025_2026.csv | 15,046 hours; 46,074 dam_prices rows in the store | Day-ahead energy only. No ancillary prices in the year view. |
| ERCOT load history | https://www.ercot.com/gridinfo/load/load_hist | One pull | none in repo (grid/LOAD.md) | data/ercot_load_hourly_2024_2026.csv | 23,373 hours | Manual download. |
| Census ACS via Census Reporter | https://api.censusreporter.org | Monthly, 2nd at 06:30 (com.basefleet.monthly) | house/demographics.py | data/demographics.json | 59 zips (ACS 2024 5-year) | Survey estimates. Every funnel stage built on them is an estimate. |
| Power to Choose | http://api.powertochoose.org/api/PowerToChoose/plans | One pull | house/territory.py | data/ptc_tdu.json | 59 zips | Retail plans, not Base coverage. Mixed zips have a city utility or co-op in part. |
| Travis appraisal (TCAD) | https://traviscad.org/publicinformation | Once a year (July 2026 roll) | house/cad_deeds.py | data/mirror/deeds_min.csv.gz, data/deeds_by_zip.json | 352,216 parcels | No deed type in the export. Owner names and addresses dropped at read time. |
| Williamson appraisal (WCAD) | https://data.wcad.org | Once a year (2026 certified) | house/cad_deeds.py | same as above | 235,919 parcels | A "sale" is any deed transfer. Filter to warranty deeds with the deed type. |
| National Weather Service | https://api.weather.gov/alerts/active?zone=TXC453,TXC491 | Hourly at :07 | collect/ercot_feeds.sh, store/signals.py | data/live/nws/<UTC>.json.gz, table nws_alerts | 0 active alerts now | Active alerts only. No history before 2026-09-26. |
| OpenStreetMap substations | https://overpass-api.de | One pull | house/feeders.py | data/feeders.json | 31 substations | No open feeder or hosting capacity data. feeder_ids is empty. |
| Base public pages | https://basepowercompany.com | One pull | manual copy (faq/FAQ.md) | faq/corpus/*.md | 4 pages | A manual copy. It does not change when Base changes its site. |

Other one-time pulls listed in `web/data/admin.json`: ZCTA boundaries (tigerweb, 59 polygons), public buildings (72 sites, house/public_buildings.py), an outage snapshot (Kubra, 2 snapshots, no history), WCAD per-address appraisal (local only, not stored).

## The database: data/fleet.db

Row counts on 2026-09-26 (23.7 MB):

| Table | Rows | From |
|---|---|---|
| permits | 34,334 | data/mirror/energy_permits.csv.gz |
| dam_prices | 46,074 | ERCOT archive CSV, dam and dashboard snapshots |
| rt_prices | 2,160 | rtSppData in system-wide-prices snapshots |
| load_hourly | 23,373 | data/ercot_load_hourly_2024_2026.csv |
| fuel_mix | 3,864 | fuel-mix snapshots |
| supply_demand | 195 | supply-demand snapshots (measured rows) |
| prc | 5,839 | daily-prc snapshots |
| conditions | 1 | daily-prc current condition |
| snapshots | 18 | every ERCOT dashboard file, raw body |
| demographics | 59 | data/demographics.json |
| territory | 59 | house/territory.py ZIP_TABLE plus data/ptc_tdu.json |
| collector_runs | 5 | data/live/collect.log |
| nws_alerts | 0 | data/live/nws/ |
| signals | 0 | store/signals.py |
| judgments | 34,636 | store/judgments.py |

## Derived data

| Item | Script | Rows | Caveat |
|---|---|---|---|
| Signals | store/signals.py | 5 rules, 0 fired | A rule with no data reports "no data" and fires nothing. |
| Judgments | store/judgments.py | 34,636: auto 29,967 (0.85 or more), model review 3,092 (0.70 to 0.85), human 1,577 (under 0.70) | Permit confidence is per rule, because the mirror has no descriptions. |
| Easy-fit funnel | house/funnel.py | 59 zips, 56,658 easy-fit homes (estimate) | The easy-fit share (22 of 40) comes from one 40-house cohort. |
| Member records | brain/members.py | 40 | Zip only. Three real price days, repeated. |
| Fleet sim | sim/ | 40 to 50 nodes | Simulated values on real price days. |
| Page builders | grid/today.py, grid/year.py, house/mirror.py, store/feeds.py | 8 feeds checked | store/feeds.py never replaces a file that differs. It writes `<name>.store.json` beside it. |

## Bypasses

Not every file goes through the database yet:

- `data/deeds_by_zip.json` goes straight to star.html.
- `data/permits_by_zip.json` goes straight to the funnel (see NOT_YET in store/feeds.py).
- `data/market.json` is written by the daily job from Socrata. The store copy starts in 2015.
- `web/data/admin.json` reads files, git log and gh issues.

## Page files and pages

| Page file | Pages |
|---|---|
| web/data/signals.json | grid.html, admin.html |
| web/data/judgments.json | judgments.html |
| web/data/grid_today.json, grid_year.json, grid_load.json | grid.html, story.html |
| web/data/explorer_points.json, explorer_zip.json | explorer.html |
| data/market.json, data/storms.json | market.html, explorer.html, star.html, story.html |
| data/funnel.json, data/deeds_by_zip.json, web/data/star_cards.json | star.html, story.html |
| web/data/block.json, density.json, fleet_kill_log.json, tower_replay.json | index.html, block.html, tower.html |
| data/members.json | member.html |
| web/data/admin.json | admin.html, dataflow.html |

## Live only on the Mac

| Service | Start | Used by | Without it |
|---|---|---|---|
| Ask server | `python3 -m brain.ask --serve 8742` | ask.html | Stored answers only (brain/insights.json). |
| Control tower live mode | `python3 -m sim.server` (port 8732) | tower.html | Plays web/data/tower_replay.json. |
| Local gemma4 | Ollama, gemma4:e4b, port 11434 | member.html, the ask agent, house/mirror.py --llm, store/judge.py --backend gemma | Typed questions fail. Stored answers still work. |

The collectors also run only on the Mac. `data/live/` is not in git.

## Freshness

The page reads `web/data/admin.json` when it opens and shows feeds ok, stale, failed, one-time, the last collector pull, and the build time. `admin/build.py` runs at the end of each hourly and daily job.
