# Feeders: real distribution data

Goal: replace the synthetic feeders in the sim with real distribution data where the data is open.
Checked 2026-09-26. No account, login or terms acceptance was used.

## Result in one line

No utility in Base territory publishes open feeder ids or hosting capacity. The best open, keyless
real data is OpenStreetMap substations. We pulled 31 substations for 9 of the 10 zips that were the top star zips at pull time (the list below).
Hosting capacity is null everywhere, so the export cap stays at the 25 kW STUB.

## Sources

| Utility | What we looked for | What exists | Keyless and queryable | Fields | License |
|---|---|---|---|---|---|
| Oncor | DG hosting capacity map, ArcGIS FeatureServer | No public hosting capacity map found. Oncor has a DG application portal only ([plus.anbetrack.com/oncor-dg](https://plus.anbetrack.com/oncor-dg/)). ArcGIS Online search for "oncor hosting" and "oncor feeder" gives only third-party layers (811 locate tickets, transmission routes), not Oncor feeder data. | No | None | n/a |
| CenterPoint | Hosting capacity or interconnection map | No public map found. Reliability page ([centerpointenergy.com](https://www.centerpointenergy.com/en-us/Services/Pages/reliability-indexes.aspx?sa=HO&au=bus)) returned 403 to our fetch. None of the top 10 star zips is CenterPoint. | No | None | n/a |
| Austin Energy | Feeder or DER map | The Resiliency Plan says "Enhance Distributed Energy Resources Hosting Capacity Analysis: Completed" ([ESRP](https://austinenergy.com/about/reports/Electric-System-Resiliency-Plan)), but no public map or dataset. data.austintexas.gov has the service-area polygon only (i2t2-i3uy). | No | None | n/a |
| PEC | Hosting capacity map | None found. | No | None | n/a |
| DOE hosting capacity atlas | Any Texas map | [DOE atlas](https://www.energy.gov/cmei/vehicles/us-atlas-electric-distribution-system-hosting-capacity-maps) lists no Texas utility. | n/a | n/a | n/a |
| HIFLD substations | Federal substation layer | HIFLD mirror on ArcGIS returns "Invalid URL" (retired). The HARC Texas copy needs a token. Skipped. | No | n/a | n/a |
| **OpenStreetMap** | `power=substation` via Overpass API | Real substations with name, operator, voltage, type. Queried by the bounding box of each ZCTA, then kept only points inside the polygon. | **Yes** | name, operator, voltage, substation type, lat/lon. No feeder id, no load, no hosting capacity. | ODbL 1.0, attribution required, share-alike on the derived database |

Outage history:

| Source | What exists | Keyless | Ingested |
|---|---|---|---|
| Austin Energy outage map (Kubra StormCenter) | Live JSON: customers served, customers out, outage count. No history. | Yes | Snapshot in `data/outages_snapshot.json` (591,989 served, 14 out) |
| Oncor outage map (Kubra StormCenter) | Same live JSON, no history. | Yes | Snapshot (4,178,584 served, 236 out, 22 outages) |
| PUCT Annual Service Quality Reports (PUC Subst. R. 25.81) | SAIDI/SAIFI per utility, plus a list of worst-performing feeders by feeder name (example: Oncor "PGSTH 7021"). PDFs on PUC Interchange. No coordinates. | puc.texas.gov returned 402 to our fetch | No |
| CenterPoint reliability indexes | Per-year SAIDI/SAIFI page | 403 to our fetch | No |

Outage history by feeder needs the PUCT SQR PDFs. The feeder names in them do not map to a location
without the utility GIS, so they cannot join to our zips today.

## What we ingested

- `house/feeders.py` makes `data/feeders.json`. One Overpass call per zip, by envelope.
- Per zip: substations (OSM id, name, operator, voltage, lat/lon), `feeder_ids: []`,
  `hosting_capacity_kw: null`.

| Zip | City | TDU in funnel.json | Substations | Operators in OSM |
|---|---|---|---|---|
| 78613 | Cedar Park | PEC (not served) | 5 | PEC (4), unknown (1) |
| 78665 | Round Rock | Oncor | 1 | Oncor |
| 78641 | Leander | PEC (not served) | 6 | PEC (3), LCRA (1), unknown (2) |
| 78634 | Hutto | Oncor | 0 | none mapped |
| 78664 | Round Rock | Oncor | 1 | Oncor |
| 78681 | Round Rock | Oncor | 2 | Oncor |
| 78660 | Pflugerville | Oncor | 2 | Oncor (1), unknown (1) |
| 78666 | San Marcos | San Marcos Electric Utility (not served) | 11 | PEC, LCRA, San Marcos Electric Utilities, Bluebonnet |
| 76574 | Taylor | Oncor | 2 | Oncor (1), unknown (1) |
| 78745 | Austin (South) | Austin Energy | 1 | Austin Energy |

Territory: Power to Choose (`data/ptc_tdu.json`, fetched 2026-09-26) shows 0 competitive plans in
78613, 78641 and 78666, so no Oncor or AEP wires there. `house/territory.py` now gives Cedar Park and
Leander as PEC and San Marcos as San Marcos Electric Utility, all `not_served`. This agrees with the
OSM operators above (PEC and LCRA; PEC, Bluebonnet and San Marcos Electric Utilities). The utility name
is from general knowledge (MEDIUM or LOW confidence); the no-competitive-retail result is HIGH.
The three zips now have 0 star homes in `data/funnel.json` and are not in the top 10. The current top 10
(78665, 78634, 78681, 78664, 78628, 78744, 78738, 78626, 76574, 78759) hold 31,753 star homes. The other
seven zips in the table above keep Oncor or Austin Energy, which Power to Choose confirms.

## Sim result

`--real-feeders` (default off) in `sim/network.py` and `python3 -m sim`. A node in a zip from
`data/feeders.json` goes to that zip's real substations, round robin by node order. Each substation
splits into feeders of 12 homes. The export cap is the real hosting capacity where given, else
25 kW. It is never given, so every feeder keeps 25 kW. Default runs are byte-identical to before
(`out/report.json` less `runtime_s`, and `out/network.json`).

`python3 -m sim --nodes 50 --seed 7`:

| run | fleet margin, 3 days | feeders | capped discharges | nodes on real substations |
|---|---|---|---|---|
| without flag (headline, no feeder model) | $1,182.82 | n/a | n/a | 0 |
| flag, synthetic feeders | $1,165.08 | 27 | 77 | 0 |
| flag, real substations | $1,173.86 | 28 | 55 | 15 of 50 |

The +$8.78 and 22 fewer capped discharges come from our round-robin rule, not from real topology.
It spreads nodes in one zip across more substations, so fewer nodes share a 25 kW cap. Only 15 of
50 nodes land in a top-10 zip (the sim draws zips by Austin permit counts). Do not quote this delta
as a real-grid effect.

Commands:

```
python3 -m house.feeders                               # refresh data/feeders.json
python3 -m sim --nodes 50 --seed 7 --real-feeders       # adds the feeder block to out/report.*
python3 -m sim.network --nodes 50 --seed 7 --real-feeders
```

## Ceiling

- The right input is the utility feeder GIS: feeder id, substation, phase, each service point on
  the feeder, and hosting capacity per feeder or per line section (kW, with the binding constraint).
  With that, the export cap is a line rating and a voltage limit, and the sim can run a power flow
  (the M2 ceiling in `sim/network.py`). We have none of it. What we have is a real substation list
  with no link from a home to a substation.
- The 25 kW cap is still a STUB. Hosting capacity on US residential feeders is often hundreds of kW
  to a few MW per feeder (published maps from utilities in other states), so 25 kW is likely very
  conservative for export. We cannot confirm this for Texas feeders.
- Path to the real data: Base as the retail provider and the battery owner gets the ESI ID and the
  meter per home; the TDU knows the feeder for each ESI ID. An interconnection application to Oncor
  returns the feeder. A data request to Oncor and Austin Energy for feeder ids by ESI ID is the
  shortest route. Austin Energy has a completed hosting capacity analysis that is not public.
