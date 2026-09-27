# Community nodes

Issue #47, task 1. Numbers from `python3 -m sim.community` (240 member nodes, seed 7, 49 feeders from the Austin zip map, 48 nodes killed at hour 22). Output in `data/community.json`.

A community node is one shared unit on a feeder: 4x the battery (156.8 kWh), 4x the rated power (40 kW), and 4 GPU slots that run 4 jobs at once. `--community N` in `sim.network` places N of them on the N feeders with the most member nodes. With the flag at 0 the house fleet runs exactly as before (verified by diff of `out/network.json` and the density sweep).

Three arms, same member fleet, same price series, same queue, same kill. The extra nodes own no jobs.

| arm | extra nodes | GPU hours lost | failover / requeued | margin $ | upload $ | jobs by fit node / feeder / far | discharges capped |
|---|---|---|---|---|---|---|---|
| baseline | 0 | 2 | 46 / 2 | 13865.35 | 349.80 | 3196 / 2242 / 314 | 1248 |
| houses (4 per feeder, 5 feeders) | 20 | 2 | 46 / 2 | 14482.04 | 440.20 | 2887 / 2366 / 509 | 1452 |
| community (1 per feeder, 5 feeders) | 5 | 2 | 46 / 2 | 14482.04 | 440.20 | 2887 / 2366 / 509 | 1299 |

Upload cost per job: node 0.00, feeder 0.10, far 0.40 (`UPLOAD_COST`, a stub).

## Reading

In this model a community node is the same thing as 4 house nodes on the same feeder: same margin, same jobs placed, same upload paid. The only column that moves is discharges capped, and that is accounting, not physics. The feeder export cap (25 kW) binds either way, so 4 houses log 4 capped hours where one community node logs 1. The added capacity does buy 88 more jobs done and $617 more margin over 3 days, but it pays $90 more in upload because the extras pull feeder and far work, and it costs $9.51 in power margin because the new packs charge at full rate on feeders that are already export capped and cannot sell all of it back. GPU hours lost do not move at all. The 2 hours lost in every arm come from feeder 78617-f0, a 2 node feeder where both nodes died in the same kill and no neighbor was left to take the job. Placing capacity on the densest feeders puts it where failover already works. The dense feeders had 46 successful failovers before any extra node arrived.

## Ceiling

A placement optimiser would not rank feeders by member count. It would rank them by expected hours at risk (small feeders, where one kill empties the feeder) times queue value on that feeder, subject to the feeder export cap and the upload cost of pulling work in. On this seed that puts the first community node on 78617-f0, not on a 12 node feeder. Checked: 1 community node there takes GPU hours lost from 2 to 1 (the handover slot takes one job per kill hour; the second still requeues) where 5 nodes on the dense feeders took it nowhere. The right form is a min cost assignment over feeders with a risk term, solved once per topology; the densest first rule here is the floor.
