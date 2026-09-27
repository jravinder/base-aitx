# Base Power × AITX hackathon entry

Built at the Base Power × AITX Talent Hackathon, Sep 25 to 27, 2026. Two entries share this repo. Start at the [landing page](https://base-aitx.vercel.app/web/start.html).

Demo videos: [Base Ready](https://www.loom.com/share/5cce9ad808a84c73a7346e334cf5e019) · [Base Super Local AI](https://www.loom.com/share/37a225004ab248bc874401470ef2653d).

## What we built for Track 2, Orchestration: Base Ready

Goal: take a member from a home address to an installed battery without a phone call.

- **Records-first onboarding.** The member types an address. City of Austin permits, ERCOT and Census data fill most fields, and three guided steps ask only what the records miss. [Onboarding](https://base-aitx.vercel.app/web/onboarding.html#home)
- **Points for each step.** 10 per answer, 20 for the photo, 30 for finishing, 50 per neighbour who joins. The member can redeem points for bill credit (our proposal). [Rewards](https://base-aitx.vercel.app/web/rewards.html)
- **Photo check with a person in the loop.** Gemini reads one guided photo, a quality check blocks blurry shots, and a person reviews anything uncertain. [Onboarding, photo step](https://base-aitx.vercel.app/web/onboarding.html#home)
- **Voice guide.** One question at a time, with pre-rendered Kokoro audio. [Voice guide](https://base-aitx.vercel.app/web/voice.html)
- **Application status.** The member sees where the application stands. [Status](https://base-aitx.vercel.app/web/status.html)
- **Help at any hour.** Base Brain answers from 88 curated FAQs and 168 linked sources. [Help](https://base-aitx.vercel.app/web/brain.html) · [The knowledge behind it](https://base-aitx.vercel.app/web/knowledge.html)
- **Views for Base.** Where ready homes concentrate, the permits behind them, and ERCOT price and load insights. [Market](https://base-aitx.vercel.app/web/market.html) · [ERCOT grid](https://base-aitx.vercel.app/web/grid.html)

## What we built for Track 3, Most Commercializable: Base Super Local AI

Goal: a private AI assistant for each member, on a small computer beside the battery. The member's data stays in the home.

- **The pitch, with a live ask box.** [Pitch](https://base-aitx.vercel.app/web/pitch.html)
- **Try it.** Run the local AI in the browser, or install it on a home PC with one command. [Try it](https://base-aitx.vercel.app/web/models.html)
- **Three plans: Use, Host, Sell.** A member uses the AI, hosts a GPU for shared earnings, or Base sells spare GPU time to local businesses. [Plans](https://base-aitx.vercel.app/web/plans.html)
- **Energy and credits.** The backup reserve always comes first. [Energy](https://base-aitx.vercel.app/web/energy.html)
- **Control tower.** Runs jobs by priority and moves them when a node fails, without touching the reserve (simulation). [Control tower](https://base-aitx.vercel.app/web/tower.html)

## Quick start

Needs Python 3.11+ (standard library only). Node 20+ only for the tests.

```sh
git clone https://github.com/jravinder/base-aitx && cd base-aitx
python3 -m http.server 8741                  # serve the static site from the repo root
open http://localhost:8741/web/start.html    # pages run on the checked-in JSON; no keys needed
```

Optional pieces:

```sh
cp .env.example .env && set -a && source .env && set +a   # add GEMINI_API_KEY
python3 -m brain.ask --serve 8742    # Help / Base Brain answers and photo reading on localhost
bash scripts/install-local.sh        # Super Local AI on your own PC, with Ollama
python3 -m sim --nodes 50 --seed 7   # rerun the fleet simulation -> out/report.json, out/report.md
python3 -m sim.server --port 8732    # live control tower: http://localhost:8732/tower.html
python3 grid/insights.py             # rerun the ERCOT analysis
```

## Reproduce the demo

1. Serve the site (Quick start). The demo path: `/web/start.html` → Base Ready → onboarding: confirm one of the 40 Austin homes, answer what records miss, upload a photo (samples in `demo/photos/`), then Rewards and Status. Base Super Local AI: `/web/compute-home.html` → Try it (a model runs in your browser with WebGPU, or on your PC after `scripts/install-local.sh`), Plans, Energy, Control tower.
2. Photo reading and the Gemini voice need `GEMINI_API_KEY`. On localhost, run `brain.ask` (above); on Vercel, set the key in the project and `api/read-photo.js` and `api/tts.js` use it server-side. Without a key, the photo step falls back to a person-review note and the voice guide to recorded clips and the browser voice.
3. Environment variables: see [.env.example](.env.example). Keys stay server-side; nothing is sent from the browser to Gemini directly.
4. Tests: `npm i -D playwright && npx playwright install chromium`, then `node tests/<name>.cjs`; Python tests: `python3 -m pytest tests/`.

## Tech stack and architecture

- **Pages:** static HTML, Tailwind (CDN) and vanilla JS in `web/`, one shared shell (`web/shell.js`), styles from a Stitch design.
- **Data:** stdlib Python collectors (`collect/`, `grid/`, `house/`) write JSON and one SQLite store (`store/build.py` → `data/fleet.db`). Pages read small JSON files, so they work without a server.
- **Answers:** `brain/ask.py` answers in a fixed order: recorded answer, route policy questions to Base, Base Brain knowledge base (`store/kb.py`), template, then a local model (Ollama, `gemma4:e4b`).
- **Photo and voice:** Gemini 3.8 Flash reads the photo (`api/read-photo.js`); voice is recorded Kokoro clips (`web/audio`), then Gemini TTS (`api/tts.js`), then the browser voice.
- **Super Local AI:** in the browser, WebLLM (MLC) runs a small open model on WebGPU with no install (`web/models.js`); on a home PC, `scripts/install-local.sh` sets up Ollama with `gemma4:e4b` (9.6 GB, one time), and the same answer server runs against it.
- **Control tower and simulation:** `sim/` models the fleet (nodes, jobs, backup reserve floor, earnings, failover); `sim/server.py` runs it live for the control tower; `grid/library_node.py` models a neighbourhood station.
- **Hosting:** Vercel (static files + two serverless functions). GA4 for page views.

**Base Ready**

```mermaid
flowchart LR
  P[City of Austin permits] & C[Census, CAD, Power to Choose] & E[ERCOT] --> COL[Collectors<br/>collect/ grid/ house/]
  COL --> DB[(data/fleet.db + JSON)]
  DB --> ON[Onboarding, Status, Rewards<br/>web/]
  ON -->|photo| RP[api/read-photo.js] --> G[Gemini 3.8 Flash]
  ON -->|voice| TTS[api/tts.js] --> G
  ON -->|questions| ASK[brain/ask.py] --> KB[Base Brain<br/>store/kb.py]
  ON -->|uncertain field or photo| H[Person reviews]
```

**Base Super Local AI**

```mermaid
flowchart LR
  M[Member question or business job] --> BR[Browser: WebLLM on WebGPU]
  M --> PC[Home PC beside the battery<br/>Ollama gemma4:e4b]
  M --> ST[Base station on the feeder]
  PC & ST --> T[Control tower<br/>sim/server.py]
  T -->|backup reserve first| BAT[Battery]
  T --> EN[Energy and earnings<br/>web/energy.html]
```

## Datasets and provenance

Every number on a page names its source file and a tag: **Measured** (we ran it or counted it in public data), **Simulation** (our model, with its dials named), **Our design** (a choice, not a measurement). The full list with URLs is in [web/data/sources.json](web/data/sources.json) and on each page's Data sources strip.

| Data | Source | Kind |
|---|---|---|
| Building and electrical permits (the 40 demo homes, market counts) | City of Austin Open Data, Socrata `3syk-w9eu` | Public |
| Prices, load, fuel mix | ERCOT dashboards and DAM/RTM archive (report 13060), load history | Public |
| Households, income | U.S. Census ACS 5-year (Census Reporter), TIGERweb ZCTAs | Public |
| Year built, appraisal | Travis and Williamson appraisal districts | Public |
| Retail plans | Power to Choose (PUCT) | Public |
| Weather alerts | National Weather Service | Public |
| Substations, libraries, rec centres, schools | OpenStreetMap, Austin Public Library, City of Austin, TEA | Public |
| FAQ corpus | Base Power public site and help centre, copied by hand | Public |
| GPU and token prices | RunPod, Lambda, Together AI pricing pages (2026-09-26) | Public |
| Local vs cloud answers, permit judgments, data QA | Our runs (`brain/LOCAL_VS_CLOUD.md`, `store/`) | Measured |
| Fleet, earnings, onboarding funnel, easy-fit funnel | Our simulations (`sim/`, `grid/`) | Simulation (synthetic) |
| Demo photos | Openly licensed images, see `demo/photos/ATTRIBUTION.md` | Public |

The 40 demo homes are real Austin addresses from public permit records; there are no owner names. Answers, points and photos a visitor adds stay in that browser.

## Known limitations

- The demo covers 40 preset Austin homes, not any address.
- Target PC speed is not yet measured on the Windows-class PC beside the battery (#80).
- One PC's power draw is unresolved: 0.4 kW in the fleet sim vs 350 W in the hub model (#85).
- 40% GPU use is a dial we set, not a measured demand number; earnings and savings are Simulation.
- There is no hyperscaler price in the comparison yet; the measured public rate is RunPod.
- Amps read from outside-the-panel photos are rarely readable; a person confirms breaker size.
- The hand-off to a person is shown, not staffed: a photo for review is saved in the browser only.
- Points and bill credit are our proposal, not a Base program. Base's real lead-to-install drop rate is unknown.

## Next steps

- Any Austin address: look up permits live from Socrata instead of the preset 40.
- Measure speed and power on the target PC (#80, #85) and run the member AI with the internet unplugged on battery.
- Add a hyperscaler GPU price to the comparison.
- Real reviewer queue for photos, during Base hours.
- Log 30 days of job arrivals at one pilot hub to replace the 40% GPU dial.

## Demo photos

See [demo/photos/ATTRIBUTION.md](demo/photos/ATTRIBUTION.md) for sourcing and licenses.

## Docs

- [docs/BUILT.md](docs/BUILT.md) — what we built, row by row
- [docs/SUBMISSION.md](docs/SUBMISSION.md) — the submission writeup
- [docs/GRID_INSIGHTS.md](docs/GRID_INSIGHTS.md) — ERCOT findings
- [docs/COMPUTE_PLANS.md](docs/COMPUTE_PLANS.md) — compute plans and rate card
- [docs/DATAFLOW.md](docs/DATAFLOW.md) — data flow
- [docs/GAPS.md](docs/GAPS.md) — open gaps
- [docs/KNOWLEDGE_BASE.md](docs/KNOWLEDGE_BASE.md) — Base Brain knowledge base
- [docs/LEARNING.md](docs/LEARNING.md) — what we learned
- [docs/VIDEO.md](docs/VIDEO.md) — video script
- [docs/adr/](docs/adr/) — architecture decision records
