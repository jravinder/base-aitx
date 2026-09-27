# Base Fleet: two entries, one story

Base Power x AITX Talent Hackathon, Sep 25 to 27, 2026. Submission Sunday 11:00 AM CT. Each entry: a video up to 5 minutes and this repo.

Docs map: [README.md](../README.md). Story spine: [GOAL.md](./GOAL.md). Video script: [VIDEO.md](./VIDEO.md). Start page: `/web/start.html` (the hosted site opens it at `/home`).

## The story in one breath

End to end, lead to grid. Base can meet member demand; utility asks and permits set the pace. We make Base's reach work for the member twice. First, the Home track takes a member from address to installation without a phone call. Then, once the battery is in, the Compute track gives the member their own private AI next door, on Base's stations.

Our design choice runs through both: AI never decides alone where the physical world is at stake. The photo confirms what the records say, a person ticks each uncertain field, and policy questions go to the Base team.

Base is building the stations; a member AI service is our proposal. Both entries run from this repo.

Every number below names its file. Tags: **Measured** (we ran it, or counted it in public data), **Simulation** (our sim or model, with its dials named).

## How this maps to the judging criteria

| Criterion | One number | Tag | Page |
|---|---|---|---|
| Technical execution | 0.4 s on the template path vs 23 s on the agent path; the model runs only where it earns its time (`brain/insights.json`) | Measured | `/web/knowledge.html` |
| Track fit | 0 reserve breaches at a 30% floor while the control tower runs jobs and survives node, region and scheduler kills (`grid/NUMBERS.md`) | Simulation | `/web/tower.html` |
| Value and impact | 264 of 316 Base backup permits issued in Austin in 2026 are still open (`data/market.json`) | Measured | `/web/market.html` |
| Innovation | Local answers in 2.2 s on a laptop and 3.0 s on an edge box, with the data staying on the member's side (`brain/LOCAL_VS_CLOUD.md`) | Measured | `/web/copilot.html` |

---

## A. Home track: from address to installation (Base Ready · Track 2 Orchestration, primary)

Spine beats 1 to 8. Tracks: Orchestration (primary), Most Commercializable.

### Problem

The path from a lead to an installed battery sets Base's pace. Of 316 Base backup permits issued in Austin in 2026, 264 are still open (Measured: `data/market.json`, Socrata `3syk-w9eu`, 2026-09-26; 16.5% final, median 14 days from applied to issued). Public records already hold most of what a member is asked to type.

### What the member sees, beat by beat

| Beat | Page | What it does |
|---|---|---|
| 1 | `/web/start.html` | Pick your track: your home, or local AI. |
| 2 | `/web/onboarding.html#home` | Type your address; public permits show most of the home first. |
| 3 | `/web/onboarding.html#home` | Answer only what records miss; every answer earns a credit. |
| 4 | `/web/onboarding.html#home`, `/web/voice.html` | One guided photo that confirms; a voice guide with a caregiver view. |
| 5 | `/web/status.html` | Where the application stands and the one thing Base needs next. |
| 6 | `/web/rewards.html` | Credits and invites in one tracker. Base confirms credit at installation. |
| 7 | `/web/brain.html` | Questions answered with sources, any time. |
| 8 | `/web/knowledge.html` | Base Brain: the knowledge behind every answer. |

### What we built behind it

- `house/permits.py`: City of Austin issued construction permits (Socrata `3syk-w9eu`), classified by type, into a 40-house cohort in zip 78745 with timelines, confidence and a fit bucket (`house/cohort.json`).
- `house/territory.py`: zip to utility and Base's plan there, checked against the Power to Choose API.
- `house/clearance.py`, `house/appraisal.py`: rule checks and year built before the truck rolls.
- `panel/`: one prompt, one JSON schema, cloud and local models on 21 hand-labelled photos (`panel/BASELINE.md`).
- `brain/ask.py`: Ask the data. A template path for fixed-shape questions, agents (planner, analyst, critic, reporter) on local gemma4 for free text. Every answer carries a replayable Socrata link.
- `brain/tts.py`: a local voice (Kokoro-82M) for the voice guide; the browser voice reads the steps without it.
- `store/build.py`, `store/signals.py`: one SQLite store (`data/fleet.db`) and 5 signal rules.
- Evidence pages: `/web/explorer.html` (every Austin energy permit since 2015), `/web/market.html` (Base permits by month and zip), `/web/star.html` (where the next easy-fit homes are).

### The numbers

- Open permits: 264 of 316 (Measured, `data/market.json`).
- Rollout: Base permits Jul 19, Aug 138, Sep 157 (partial month), 314 since July (Measured, `data/market.json`).
- Permit mirror: 34,334 Austin energy permits since 2015 (Measured, `web/data/explorer_zip.json`).
- Cohort: 40 houses in 78745; 22 easy, 18 needs love (Measured on public records, `house/cohort.json`).
- Ask the data: 73 questions, 73 pass the critic; template path median 0.37 s with a live permit query, agent path median 23.16 s on gemma4:e4b (Measured, `brain/insights.json`).
- Photo baseline: Gemini reads photo type on 18 of 21 at 12.7 s median; gemma4:e4b on 16 of 21 at 129 s (Measured, `panel/BASELINE.md`). The photo confirms the record; a person confirms breaker size.
- Market: ERCOT counts 8 million premises in competitive choice areas (public source, https://www.ercot.com/about, read 2026-09-26).

### Next steps (the ceiling)

- Base's own permit state per utility and municipality shows exactly where each application waits.
- A breaker read tuned on about 200 labelled panel photos, as a second check next to the person who ticks.
- Base's eligibility rules and real drop rates in the fit score.
- Travis County bulk appraisal and utility feeder maps for territory and clearance.

### Run

```
python3 -m http.server 8741                           # from the repo root
open http://localhost:8741/web/start.html             # beats 1 to 8
python3 -m brain.ask --serve 8742                     # Ask the data and Help answers (Ollama with gemma4:e4b)
python3 -m brain.tts --serve 8744                     # optional local voice
python3 house/permits.py --cohort && python3 house/market.py   # rebuild cohort and market from Austin open data
```

---

## B. Compute track: your own AI next door (Base Super Local AI · Track 3 Most Commercializable, primary)

Spine beats 9 to 13. Tracks: Most Commercializable (primary, `/web/pitch.html`), Orchestration (second), Open Grid Data (evidence).

### Problem

Frontier AI takes the member's data, bills per question and needs the internet. Base is building compute stations on its battery fleet. The member AI service on those stations is our proposal: private answers, one hop away, with the member's backup reserve always protected.

### What the member and Base see, beat by beat

| Beat | Page | What it does |
|---|---|---|
| 9 | `/web/pitch.html#how-it-works` | Frontier AI takes your data; your own AI next door keeps it. |
| 10 | `/web/copilot.html`, `/web/energy.html` | Your home AI answers about your power, your week, your records. |
| 11 | `/web/overview.html`, `/web/placement.html`, `/web/block.html` | Stations serve the homes around them; the library example. |
| 12 | `/web/jobs.html`, `/web/tower.html` | The control tower: jobs by priority, reserve always protected. |
| 13 | `/web/pitch.html` | Base has the stations, the members and the crews. This is the software that makes them private AI for every member. |

### What we built behind it

- `brain/answer.py`, `brain/members.py`, `brain/score.py`: the member's AI answers from the member's own record and sends policy questions to the Base team. Backends: laptop, edge box on the home network, cloud.
- `sim/fleet.py`: stations, a greedy scheduler with 24 h lookahead, five buyer tiers, job placement by data locality, same-feeder failover, three kills, a reserve assertion every interval.
- `sim/density.py`: the same network at 1 to 20 stations per feeder.
- `sim/server.py`: the control tower (`GET /state`, `POST /jobs`, `POST /kill`).
- `grid/year.py`, `grid/library_node.py`: one battery against 627 days of ERCOT day-ahead prices; library station against house station.
- `docs/adr/0016-gpu-placement-community-hub.md`: compute at the library or community hub, on a standard Windows-class PC, with or without a GPU.

### The numbers

- Local answers, member m001, 10 questions, 2 runs each (Measured, `brain/LOCAL_VS_CLOUD.md`): laptop 14 of 16 correct plus 4 of 4 policy questions sent to Base, median 2.2 s, first token 0.62 s. Edge box over the home network: 12 of 16 plus 4 of 4, median 3.0 s, first token 1.45 s.
- Reserve: 0 breaches at a 30% floor of 39.2 kWh, asserted every interval on every station (Simulation, `grid/NUMBERS.md`, seed 7, 50 stations, 3 real ERCOT days).
- Failover: 2 or more stations per feeder lose 0 GPU hours at 100% failover; 1 per feeder loses 8 (Simulation, `grid/NUMBERS.md`, 120 stations, 20% killed).
- Library station: $205.78 a week against $84.71 for a house station, at 40% GPU use (Simulation on real ERCOT prices, `grid/LIBRARY_NODE.md`).
- Fleet, 50 stations, 3 days: power only $142.14; with compute $1,040.68 at 40% GPU use (Simulation, `grid/NUMBERS.md`).
- One battery, a year of prices: $603.45 in 2025 in LZ_AEN, energy only (Measured prices, `grid/YEAR.md`).

The 40% GPU use and the 25 kW feeder cap are dials we set.

### Next steps (the ceiling)

- Measure answer speed and power draw on the target Windows-class PC (#80, #85; the fleet sim uses 0.4 kW, the hub model 350 W).
- Run the member AI with the internet unplugged and the grid off, on battery power.
- Log job arrivals at one pilot hub for 30 days to replace the 40% dial.
- A min-cost scheduler on real telemetry, with checkpoints.

### Run

```
python3 -m http.server 8741                                    # from the repo root, then /web/pitch.html
python3 -m brain.answer --backend laptop m001 "what did my node earn this week"
python3 -m sim --nodes 50 --seed 7 && python3 -m sim.density   # out/report.md, out/density.json
python3 -m sim.server --nodes 50 --tick 2                      # control tower on http://localhost:8732/tower.html
cd grid && python3 earned.py && python3 library_node.py && python3 year.py && cd ..
```

### Collectors, store, and signals

```
bash collect/install_mac.sh                                    # launchd: ERCOT hourly, permits and market daily, ACS monthly
python3 store/build.py --incremental && python3 store/signals.py   # data/fleet.db, web/data/signals.json
```

See `collect/README.md`.

---

## Built this weekend, kept off the spine

On the pages, cut from the video for time: storm history in permits (`docs/STORM_RUSH.md`), assisted-onboarding priority per zip (`data/funnel.json`), clearance wall sketch (`/web/wall.html`), the 40-house block (`/web/house.html`), the ERCOT grid page (`/web/grid.html`), install routing, permit path counts, and photo candidate scrapers.
