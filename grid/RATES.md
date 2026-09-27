# GPU and token rates, sourced

Issue #12. Replaces the STUB rates in `sim/fleet.py` TIERS.

## Source table

| Source | GPU / model | $/hour or $/1M tok | Date checked | URL |
|---|---|---|---|---|
| RunPod | RTX 4090 (24 GB), community cloud | $0.34/hr | 2026-09-26 | https://www.runpod.io/pricing |
| RunPod | RTX A5000 (24 GB), community cloud | $0.16/hr | 2026-09-26 | https://www.runpod.io/pricing |
| RunPod | L40S (48 GB), community cloud | $0.79/hr | 2026-09-26 | https://www.runpod.io/pricing |
| Lambda | RTX A6000 (48 GB), on-demand | $1.09/hr | 2026-09-26 | https://lambda.ai/service/gpu-cloud |
| Lambda | A100 40GB, on-demand | $1.99/hr | 2026-09-26 | https://lambda.ai/service/gpu-cloud |
| Together AI | Llama 3.1 8B Instruct Lite | $0.14 / 1M tokens (in + out) | 2026-09-26 | https://www.together.ai/pricing |

Vast.ai and Akash publish live, bid-driven marketplace rates with no static page to cite. Their pricing pages (https://vast.ai/pricing, https://akash.network/pricing/gpus) confirm the pricing model is real-time and bid-based but did not return a fixed number on a page fetch. RunPod's community cloud rate is used as the stand-in for that class of spot/marketplace pricing, since RunPod publishes the same kind of low-cost spot GPU rate on a static page.

## Mapping to the five tiers

| Tier | Old (STUB) | New | Reasoning |
|---|---|---|---|
| member | 1.20 | 1.20 (unchanged) | This is the homeowner's own local job rate (`LOCAL_JOB_RATE`), not a market rate. It stays fixed. |
| business | 1.00 | 1.09 | Local businesses want low latency and uptime, so price at Lambda's on-demand A6000 rate, a reliable dedicated cloud tier. |
| base | 0.90 | 0.79 | Base's own forecast/telemetry jobs can tolerate spot risk, so price at RunPod community L40S, a mid-tier spot rate. |
| partner | 0.80 | 0.34 | Grid partner batch work is price-sensitive and delay-tolerant, so price at RunPod community RTX 4090, a cheap consumer-class spot rate. |
| external | 0.55 | 0.16 | Public marketplace batch is the bottom of the stack, so price at RunPod community RTX A5000, the cheapest sourced rate. |

Rates stay monotonically decreasing member > business > base > partner > external, matching the original tier design.

## Worked example: SMB local inference bill

SMB running 2,000,000 tokens/day of 8B-class inference.

**On Together AI (managed API):**
- Rate: $0.14 per 1M tokens (in + out combined)
- Cost: 2M tokens x $0.14/1M = $0.28/day, about $8.40/month

**On the fleet, at the external tier rate ($0.16/GPU-hour):**
- Assume an 8B model does about 4,000 tokens/sec on a 24 GB consumer GPU, batched
- 2,000,000 tokens / 4,000 tok/sec = 500 sec = 0.139 GPU-hours/day
- Cost: 0.139 hr x $0.16/hr = $0.02/day, about $0.67/month

At this volume both bills are small in absolute dollars, but the fleet is about 12.5x cheaper per day than the managed API, because the SMB is paying for raw GPU-hours instead of a per-token markup. The gap widens as token volume grows, since GPU-hour pricing does not carry the same per-token margin a hosted API charges.

## Simulation check

Rerun on 2026-09-26 with the current defaults (40% GPU use, member cap 25%, ERCOT DAM Sep 7, Sep 9, Sep 26):

```
python3 -m sim --nodes 50 --seed 7
```

Result:
- Fleet power-only margin: $142.14
- Fleet with compute: $1,182.82 (compute $1,040.68: members $646.60, outside buyers $394.08; 39.7% GPU use achieved)
- At 100% GPU use: $2,885.71. The first run after the rate change ($181.02 and $2,920.10) used 100% GPU use and older prices. See grid/NUMBERS.md.
- Jobs lost under kills: 0
- Recovery (intervals): node:0 = 1, region:east = 1, scheduler:None = 1
- Reserve breaches: 0

Simulation runs clean with the sourced rates, no errors.
