# Base Fleet

Base Power x AITX Talent Hackathon, Sep 25 to 27, 2026. All code written during the event.

End to end, lead to grid. Base can meet member demand; utility asks and permits set the pace. One app, two tracks:

1. **Home track** (spine beats 1 to 8): from address to installation without a phone call. Public permits show most of the home first, the member answers only what records miss, one guided photo confirms, and every answer earns a credit.
2. **Compute track** (spine beats 9 to 13): once the battery is in, the member's own private AI next door, on Base's stations. Base is building the stations; a member AI service is our proposal.
3. **Design choice:** AI never decides alone where the physical world is at stake. The photo confirms, a person ticks, and policy questions go to the Base team.
4. **Evidence is public data:** Austin permits, ERCOT prices and load, Census ACS, Power to Choose, NWS alerts. 264 of 316 Base backup permits in Austin in 2026 are still open (`data/market.json`).

Story spine: [docs/GOAL.md](docs/GOAL.md). Submission: [docs/SUBMISSION.md](docs/SUBMISSION.md). Video script: [docs/VIDEO.md](docs/VIDEO.md). Docs index: [docs/README.md](docs/README.md).

## What we built

Eleven rows, each with what, why, how, proof and status: 7 built, 4 partly built. Page: [web/built.html](web/built.html) (http://localhost:8741/web/built.html). Same content as markdown: [docs/BUILT.md](docs/BUILT.md).

## Quick start (judge path, under 60s)

Needs **Python 3** only. No `pip install` for the static demo. Serve from the **repo root** (pages fetch `../data`, `../house`, `../brain` — do **not** use `--directory web`).

```sh
git clone https://github.com/jravinder/base-aitx.git && cd base-aitx
python3 -m http.server 8741
```

Open the vertical demo:

**http://localhost:8741/web/story.html**

Or jump the Home admin evidence walk:

**http://localhost:8741/web/market.html?track=home&persona=operations**

### Vertical: Lead → Photo → Permit → Install → Grid

| Stage | Open | What a judge should see |
|---|---|---|
| Lead | [onboarding.html#home](http://localhost:8741/web/onboarding.html?track=home&persona=lead#home) | Sample address; public permits fill most fields |
| Photo | [voice.html](http://localhost:8741/web/voice.html?track=home&persona=lead) / journey photo | One guided panel photo (browser draft only) |
| Permit | [market.html](http://localhost:8741/web/market.html?track=home&persona=operations) | Austin Base Auxiliary Power: pace, open vs final |
| Install | [recovery.html](http://localhost:8741/web/recovery.html?track=home&persona=operations) | Austin install pipeline (issued → active → final) + honest #57 gap outside Austin |
| Grid | [grid.html](http://localhost:8741/web/grid.html?track=compute&persona=fleet) | ERCOT day-ahead + modeled battery; not live member telemetry |

Setup detail: [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md). Role entries: [docs/DEMO_PATH_QUICK.md](docs/DEMO_PATH_QUICK.md).

### Optional (not required for the vertical)

```sh
python3 -m brain.ask --serve 8742    # Help / Base Brain / Ask the data (needs Ollama on 11434 with gemma4:e4b)
python3 -m brain.tts --serve 8744    # local voice (Kokoro-82M; Python 3.12 + ffmpeg)
python3 -m sim.server --nodes 50 --tick 2   # live control tower → http://localhost:8732/tower.html
```

Without those, Help uses indexed FAQs, voice uses the browser speech API, and the tower plays a recorded replay on port 8741. Optional servers listen on 127.0.0.1 only.

### Run the local AI on your PC (one command)

```sh
bash scripts/install-local.sh              # macOS; Linux best effort
bash scripts/install-local.sh --uninstall  # stop the servers it started
```

Idempotent, no sudo (Homebrew may ask when it installs itself). It installs Ollama, pulls `gemma4:e4b` (9.6 GB, one time), starts the pages on 8741, the ask server on 8742 and, when `.venv-tts` has Kokoro, the voice server on 8744, prints a doctor line, then opens http://localhost:8741/web/models.html#try, which shows "Connected to your PC". Logs and pid files: `~/.base-fleet/`.

No install: `models.html#try` also loads Qwen2.5-0.5B (282 MB, WebLLM on WebGPU) in the browser and answers from `web/data/faq.json` and `web/data/kb_graph.json`.

## Pages

All pages are in `web/`. The hosted site opens `start.html` at `/home`. Spine pages, in order:

| Beat | Page | What it shows |
|---|---|---|
| 1 | `start.html` | Pick your track: your home, or local AI. |
| 2 to 4 | `onboarding.html#home`, `voice.html` | Address, the gaps records miss, one guided photo, a voice guide. |
| 5 | `status.html` | Where the application stands and the one thing Base needs. |
| 6 | `rewards.html` | Credits and invites in one tracker. |
| 7 | `brain.html` | Help: questions answered with sources. |
| 8 | `knowledge.html` | Base Brain: the knowledge behind every answer. |
| 9, 13 | `pitch.html` | Your own AI next door; the close. |
| 10 | `copilot.html`, `energy.html` | Your home AI: your power, your week, your records. |
| 11 | `overview.html`, `placement.html`, `block.html` | Stations serve the homes around them. |
| 12 | `jobs.html`, `tower.html` | Control tower: jobs by priority, reserve always protected. |

Evidence and admin pages:

| Page | What it shows |
|---|---|
| `story.html` | The whole story on one page, one card per beat, and 8 persona tours. |
| `demo.html` | Walkthrough: one address, six steps, from lead in to the photo gate. |
| `house.html` | The block: 40 houses, a confirm on one house teaches its neighbours. |
| `wall.html` | Clearance: a 2.5D meter wall rule check before the truck rolls. |
| `explorer.html` | Permit explorer: 34,334 Austin energy permits since 2015, with Play and storm markers. |
| `market.html` | Market: Base permits by month, status, and zip against other contractors. |
| `star.html` | Next areas: estimated easy-fit homes per zip on a map. |
| `grid.html` | Grid: one battery against every ERCOT day-ahead hour since 2025, plus a live ERCOT dashboard. |
| `ask.html` | Ask the data: permit questions answered by local agents, each with a replayable Socrata URL. |
| `onboarding.html#network` | Your network: a browser-only sim of one job and a node recovery. |
| `index.html` | Fleet: the sim report, kills, tiers, and the feeder density chart. |
| `member.html` | Ask your own record; the Base team answers policy questions directly. |
| `admin.html` | Admin: data feeds, pages, tracks, signals, and agents; what is live, stale, or failing. |

## More commands

```
python3 -m sim --nodes 50 --seed 7              # fleet sim, writes out/report.json and out/report.md
python3 -m sim.density                          # density sweep, 120 nodes, writes out/density.json
python3 -m brain.answer --backend laptop m001 "what did my node earn this week"
```

Python 3 standard library for the sim, store, and signals. The Base Brain and Ask the data need Ollama. More commands per entry: `docs/SUBMISSION.md`, Run.

## Data sources

| Source | Used for | Access |
|---|---|---|
| City of Austin issued construction permits, Socrata `3syk-w9eu` | Cohort, market, permit mirror, explorer, storms, ask | data.austintexas.gov, no key |
| ERCOT report 13060 (historical DAM load zone prices) | A year of prices, `grid/YEAR.md` | ercot.com, no login |
| ERCOT native load history | Peak hours, `grid/LOAD.md` | ercot.com/gridinfo/load/load_hist, no login |
| ERCOT dashboards (system-wide prices, supply-demand, fuel mix, daily PRC) | Live grid page, sim days, signals | ercot.com dashboards JSON, no login |
| Census ACS 5-year via Census Reporter | Households, tenure, year built, age 65+, disability | censusreporter.org API, no key |
| Power to Choose API | Utility (TDU) and competitive plans per zip | powertochoose.org, no key |
| Census TIGERweb ZCTA layer | Zip polygons, `data/zcta.geojson` | no key |
| NWS active alerts | Storm alert signal, Travis and Williamson counties | api.weather.gov, no key |
| OpenStreetMap | Substations, basemap tiles | no key |
| Base public pages, GPU cloud price pages | FAQ corpus, tier rates (`grid/RATES.md`) | public web |

## Where data lives

- Flat files in the repo: `data/*.json` and `data/*.csv` (market, funnel, storms, demographics, territory, ERCOT prices and load), `data/mirror/energy_permits.csv.gz` (permit mirror), `web/data/*.json` (page files), `house/cohort.json`, `out/` (sim output).
- One SQLite store: `data/fleet.db`, built by `store/build.py` from the flat files and the collector snapshots. `store/signals.py` reads it and writes `web/data/signals.json`.
- Collectors run on the Mac through launchd (`collect/`, install with `bash collect/install_mac.sh`): ERCOT and NWS hourly at :07, permits and market daily at 06:15, ACS monthly on the 2nd. Snapshots go to `data/live/` (gitignored). Each run ends with `store/build.py --incremental` and `store/signals.py`. See `collect/README.md`.
- No owner names and no addresses in browser files. Contractors other than Base are anonymous (`docs/MIRROR_SCHEMA.md`).

## Demo photos

Openly licensed meter and panel photos for trying the Onboarding photo step (quality check, reading, retake), plus three deliberately bad copies for the retake tips. Sources and licences: [demo/photos/ATTRIBUTION.md](demo/photos/ATTRIBUTION.md). For the demo only; no page uses them.
