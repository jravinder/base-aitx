# What one library node earns per week

Issue #47, tasks 3 and 4. Numbers from `grid/library_node.py`, using the battery
math in `grid/earned.py` and the GPU tier rates in `grid/RATES.md`.

A library node is 4 batteries plus 4 GPUs, sited at a public library. A house
node is 1 battery plus 1 GPU, for comparison.

## Weekly table

| node | batteries | battery net | GPU revenue | GPU electricity cost | GPU net | TOTAL/week |
|---|---|---|---|---|---|---|
| Library (4 batt + 4 GPU) | 4 | $50.32 | $159.94 | $4.48 | $155.46 | **$205.78** |
| House (1 batt + 1 GPU) | 1 | $12.58 | $73.25 | $1.12 | $72.13 | **$84.71** |

GPU revenue by tier, library node (40% utilization, 67.2 active hours/week each):

| tier | $/GPU-hour | revenue/week | electricity cost/week | net/week |
|---|---|---|---|---|
| business | 1.09 | $73.25 | $1.12 | $72.13 |
| base | 0.79 | $53.09 | $1.12 | $51.97 |
| partner | 0.34 | $22.85 | $1.12 | $21.73 |
| external | 0.16 | $10.75 | $1.12 | $9.63 |

House node runs one GPU at the business tier only (one customer relationship,
not four), so its GPU row matches the library's business-tier row exactly.

## Assumptions and sources

- **Battery**: 4x Base Core 39.2 kWh, 10 kW, 30% reserve kept (same spec as `sim/fleet.py`), one arbitrage cycle
  a day. Same math and same 2 real ERCOT DAM days as `grid/EARNED.md`
  (2026-09-07, 2026-09-09, cycled to fill 7 days). LZ_AEN (Austin Energy load zone).
  Source: `data/ercot-dam-2026-09-07.json`, `data/ercot-dam-2026-09-09.json`,
  https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD
- **GPU tier rates**: business $1.09/hr (Lambda A6000 on-demand), base $0.79/hr
  (RunPod L40S community), partner $0.34/hr (RunPod RTX 4090 community),
  external $0.16/hr (RunPod RTX A5000 community). All from `grid/RATES.md`,
  checked 2026-09-26.
- **Utilization: 40%**. This is a stated planning assumption, not measured
  fleet data. No utilization telemetry exists in this repo. Real jobs are
  bursty; 40% is a mid-range guess for a single library-sited node serving a
  local customer base, not a modeled or fitted number.
- **GPU electricity draw: 350 W per GPU under load.** Typical draw for a
  consumer/workstation-class card in the RTX 4090/L40S class. Idle hours are
  not charged, only the 40% active hours.
- **Electricity price for GPU hours**: average LZ_AEN ERCOT DAM price across
  the same 7-day cycled window, $0.04760/kWh ($47.60/MWh). This is the
  all-hours average, not the battery's cheap 3-hour charge-window price,
  because GPU jobs run whenever demand arrives, not only during the battery's
  scheduled charge window.
- **Library node GPU mix**: one GPU per tier (business, base, partner,
  external), skipping "member" because that rate is the homeowner's own local
  job price, not something the library resells. This lets one library node
  serve every non-member customer class at once, GPU electricity is a small
  line, about 2.8% of GPU revenue at these rates and this draw.

## The library is the SMB's GPU

`grid/RATES.md` already has one small business worked example: an SMB running
2,000,000 tokens/day of 8B-class inference.

**On a cloud API (Together AI, $0.14/1M tokens):** about $8.40/month.

**On the library node, one hop away, at the external tier ($0.16/GPU-hour):**
about $0.67/month, using the same 4,000 tok/sec assumption from RATES.md.

Both bills are small in absolute dollars at this token volume. The real
difference is not price, it is where the data goes:

- **On the cloud API**: every prompt, every document snippet, every customer
  record the SMB sends leaves the building, crosses the internet, and sits on
  someone else's server, subject to that vendor's retention and training
  policies.
- **On the library node**: the job runs on a GPU physically inside the same
  zip code, often the same few blocks. The SMB's invoices, contracts, and
  customer records never leave the local network hop. Nothing is uploaded to
  a third party to get the answer back.

For a small business handling anything sensitive, an insurance broker,
a bookkeeper, a small medical office, a law office, that data-locality
guarantee is worth more than the token price. The library node is not
competing with the cloud API on price alone. It is offering a local-only
compute option that a hosted API structurally cannot: the SMB's documents
never leave the zip.

## The ceiling

This table only counts energy arbitrage and GPU rental at an assumed 40%
utilization. Two things would change it a lot:

1. **Ancillary services.** Real ERCOT dispatch also earns from regulation,
   responsive reserve, and ECRS, paid for standing ready, not for energy
   moved. `grid/EARNED.md` already flags this for the battery side. None of
   that revenue is in this table.
2. **Real utilization data.** 40% is a guess. If a library node's actual GPU
   demand runs higher (a busy branch, several SMBs sharing one node) or lower
   (a quiet branch, no demand yet), the GPU revenue line scales linearly with
   it and could be off by 2x or more in either direction. The right next step
   is to log actual job arrivals at a pilot node and replace the assumption
   with a measured number.

Treat the $205.78/week library total as a floor built on a stated, sourced
assumption, not a forecast.
