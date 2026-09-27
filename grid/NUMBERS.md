# Headline numbers

Every headline number from the sim and the grid scripts, before and after the fixes for
#59, #62, #64, #65 and #66 and the territory table fix (2026-09-26). The new column was rerun
after the territory fix. Seed 7 for every sim run. Each command is
deterministic: two reruns give byte-identical `out/report.json` (less `runtime_s`) and `out/density.json`.

What changed:

- **#66 demand model.** `sim/fleet.py` no longer books every GPU every hour. `--util` (default 0.40)
  sizes the job queue to 40% of GPU node-hours, and jobs arrive spread over the 72 hours. Marketplace
  buyers are the external tier inside that queue, so an idle GPU does not sell its hour.
  `--member-cap` (default 0.25) caps member-tier hours on a node at 25% of its hours. Both are STUB
  dials: no utilisation telemetry exists. `--util 1 --member-cap 1` is the old run.
- **#64 prices.** The sim uses three real ERCOT DAM days, Sep 7, Sep 9, Sep 26, with no replay.
  `data/ercot-dam-2026-09-27.json` holds one row only: HE24 of Sep 26 (timestamp 2026-09-27 00:00).
  So the two new files make one real day, not two. The sim has 72 intervals, so three days fill it.
- **#62 battery and zone.** `grid/earned.py` and `grid/library_node.py` import `CAPACITY_KWH`,
  `RATE_KW` and `RESERVE` from `sim/fleet.py`: 39.2 kWh, 10 kW, 30% reserve kept (27.44 kWh usable a
  cycle). Zone LZ_AEN everywhere; LZ_NORTH (Dallas, Oncor) is the comparison. The grid scripts still
  cycle Sep 7 and Sep 9 for their 7-day week.
- **#65 density.** `python3 -m sim.density` now defaults to 120 nodes, the run the docs quote.
- **#59 territory.** `sim/stages.py` calls `house/territory.lookup()`. Served = `energy_and_backup`,
  `backup_only` (Austin Energy) or `mixed` (competitive TDU in part of the zip). After the territory
  fix, all 49 Austin zips are in `territory.py` ZIP_TABLE, so no lead is unmapped.

| number | old | new | command |
|---|---|---|---|
| Fleet power only, 50 nodes, 3 days | $181.02 | $142.14 | `python3 -m sim --nodes 50 --seed 7` |
| Fleet power plus compute | $2,920.10 (100% util) | $1,182.82 (40% util) | same |
| Fleet compute | $2,739.08 | $1,040.68 | same |
| Compute, members on their own node ($1.20/h) | $1,618.53 (59%) | $646.60 (62%) | same |
| Compute, outside buyers | $1,120.55 | $394.08 | same |
| GPU utilisation achieved | 100% | 39.7% | same |
| Fleet total at 100% util, new prices | n/a | $2,885.71 (members $1,618.53, outside $1,125.04) | same (`at_full_util` in report.json) |
| Fleet total at 40% util, old Sep 7/9/7 prices | n/a | $1,220.19 | `fleet.panel(50, 7)` with the old price_series (not a CLI flag) |
| Reserve breaches | 0 | 0 (asserted every node, every interval) | same |
| Recovery, node / region / scheduler kill | 1 / 1 / 1 | 1 / 1 / 1 | same |
| Territory share (served TDU, owner, has address) | 0.662 | 0.641 | same |
| Territory-only share (served TDU, any tenure) | 1.000 (580 AE + 220 Oncor/PEC, 0 not served) | 0.964 (511 Austin Energy backup_only, 125 energy_and_backup, 135 mixed, 29 PEC not served, 0 unmapped) | same |
| Leads served, 4 weeks | 530 of 800 | 513 of 800 | same |
| Permit permutations | 8 | 13 | same |
| Install routing, miles per install | 8.49 | 8.3 (first-come order 17.89) | same |
| Homes lost a month at the photo step | 108 | 104 | same |
| Compute margin per node per month | $547.82 | $208.14 | same |
| Compute margin never scheduled a month | $59,164 | $21,646 | same |
| Density: GPU hours lost, 1 node per feeder, 20% killed | 24 (120 nodes); 48 (240-node default) | 8 | `python3 -m sim.density` (120 nodes default) |
| Density: GPU hours lost, 2 per feeder | 2, failover 92% | 0, failover 100% | same |
| Density: first capped discharges | 3 per feeder | 3 per feeder | same |
| Density: peak relief kW per feeder | 20 kW from 2 per feeder | 12.7 at 2, 20 from 6 per feeder | same |
| Density: compute per node across sweep | $54.42 to $56.86 ("$54 to $57"; docs said $56 to $57) | $20.63 to $21.04 ("$21") | same |
| One battery, 7 days, Austin | $8.66 (30 kWh, 11 kW, LZ_SOUTH) | $12.58 (39.2 kWh, 10 kW, 30% reserve, LZ_AEN) | `python3 grid/earned.py` |
| One battery, 7 days, LZ_NORTH (Oncor) | $11.30 | $12.93 | same |
| Highest hourly price seen | $107/MWh (LZ_NORTH) | $109/MWh (LZ_AEN, Sep 9 HE20, $108.57) | same |
| Library node a week (4 batteries + 4 GPUs) | $190.39 (battery $34.64) | $205.78 (battery $50.32) | `cd grid && python3 library_node.py` |
| House node a week (1 battery + 1 GPU) | $80.86 (battery $8.66) | $84.71 (battery $12.58) | same |
| Average price for GPU hours | $44.51/MWh (LZ_SOUTH) | $47.60/MWh (LZ_AEN) | same |

Notes:

- Old compute ($2,739.08) and outside ($1,120.55) are $2,920.10 minus $181.02 and minus the member tier.
- The drop from $2,920 to $1,183 is almost all utilisation: at 40% on the old prices the total is $1,220.
  The new Sep 26 day has a smaller spread, so power only falls from $181 to $142.
- The member cap binds only on busy nodes: without it, members earn $656.97, not $646.60.
- Before the territory fix, 22 of the 49 zips were unmapped (54% of leads) and the share was 0.249.
  With every zip in `house/territory.py` ZIP_TABLE, the share is 0.641. The 29 PEC leads are the only
  leads not served. `house/funnel.py` reads the same table.
- Not rerun or not restated here: `out/network.json` was regenerated by `python3 -m sim.network`
  under the new defaults, but its README numbers (63%, 0.5%, $1.18, $0.49) were not rechecked.
  `sim/community.py`, `sim/server.py` and `brain/members.py` also now run at 40% by default.
  `docs/SUBMISSION.md` quotes the new column (0.964, 0.641, 104 homes, $21,646, 8 vs 0 GPU hours).
