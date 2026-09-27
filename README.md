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
