# Base Ready · Base Super Local AI

Built at the Base Power x AITX Talent Hackathon, Sep 25 to 27, 2026.

## Two areas

### Base Ready (Track 2, Orchestration)

Base Ready takes a member from a home address to an installed battery without a phone call. Public records fill in most of the form so the member answers only what records miss.

What a member sees: records-first onboarding that fills in most fields from public data; three guided steps that earn points as they go; a photo check read by Gemini, with a person confirming anything uncertain; a voice guide with a caregiver view; and Help or Base Brain answering questions any hour.

What Base sees: market intelligence on where ready homes concentrate, the permits behind each one, ERCOT price and load insights, and an install-readiness read per home.

### Base Super Local AI (Track 3, Most Commercializable)

A private AI next door: a PC beside the battery, or a station on the feeder, running open models for the member. Try it in the browser, or install it on your own PC with one command. Three plans: Use, Host, Sell. A control tower keeps the backup reserve first, ahead of any compute job.

## Try it

Live site: [base-aitx.vercel.app](https://base-aitx.vercel.app) (behind Vercel login until public). Start at `/web/start.html`.

| Page | What it shows |
|---|---|
| `/web/start.html` | Pick your track: your home, or local AI |
| `/web/onboarding.html#home` | Records-first onboarding, guided steps, points |
| `/web/voice.html` | Voice guide, one question at a time |
| `/web/status.html` | Where the application stands |
| `/web/rewards.html` | Points and neighbour invites |
| `/web/brain.html` | Help and Base Brain, any hour |
| `/web/knowledge.html` | Base Brain: the knowledge behind every answer |
| `/web/market.html` | Market intelligence, permits by month and zip |
| `/web/grid.html` | ERCOT grid insights |
| `/web/pitch.html` | Base Super Local AI, live ask box |
| `/web/models.html` | Try it: local AI in the browser or on your PC |
| `/web/plans.html` | Compute plans: Use, Host, Sell |
| `/web/energy.html` | Energy and credits, backup reserve first |
| `/web/tower.html` | Control tower: jobs, reserve, failover |

## Run it locally

```sh
python3 -m http.server 8741          # from the repo root
open http://localhost:8741/web/start.html

python3 -m brain.ask --serve 8742    # Help / Base Brain answers, and photo reading
                                       # needs GEMINI_API_KEY in the environment for photo reading

bash scripts/install-local.sh        # local AI on your PC, with Ollama
```

Optional: a local Kokoro voice server for the voice guide, `brain/tts.py`.

## How it's built

Static pages with JSON data built by collectors, served by `brain/ask.py`. Base Brain is a knowledge graph in `store/kb.py`. `sim/` runs the fleet simulation for the control tower. `grid/insights.py` runs the ERCOT analysis. `api/read-photo.js` reads photos on Vercel with a server-side key. Voice clips are Kokoro audio in `web/audio`.

## Data sources

Every number names its source file. See `web/data/sources.json` and the Data sources page for the full list: City of Austin permits, ERCOT day-ahead prices and load, Census ACS, Power to Choose.

Tags on every claim: **Measured** (we ran it, or counted it in public data), **Simulation** (our sim or model, with its dials named), **Our design** (a choice we made, not a measurement).

## Honest limits

- Target PC speed is not yet measured on the Windows-class PC beside the battery (#80).
- One PC's power draw is unresolved: 0.4 kW in the fleet sim vs 350 W in the hub model (#85).
- 40% GPU use is a dial we set, not a measured demand number.
- Amps read from outside-the-panel photos are rarely readable; a person confirms breaker size.
- Base's real lead-to-install drop rate is unknown; our conversion view uses assumed dials.

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
