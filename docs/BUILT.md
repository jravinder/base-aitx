# What we built

Page: [web/built.html](../web/built.html), two tabs: `#lead` (default, Base Ready / Track 2) and `#track3` (Base Super Local AI / Track 3; `#track2` alias). Screenshots: `docs/shots/built.jpg`, `docs/shots/built-phone.jpg`.

Open data tells us about a home before the lead arrives. City of Austin permits, ERCOT prices and load, and Census ACS feed one readiness read per home. The member gets a form that is mostly filled in, guided steps with rewards, a photo check, and help by voice or chat. The Base team gets market intelligence and a conversion view. One knowledge base answers both sides. Each row names its source file and tags its proof: Measured, Simulation, or Our design.

- Member side: open data → readiness → autofill → guided steps → photo check → help (voice, chat) → knowledge base
- Base side: open data → market intelligence → conversion → knowledge base

# Part 1. Base Ready · Track 2 (Orchestration): lead flow onboarding

Status: 7 built, 3 partly built.

## Member side

| # | What | Why | How | Proof | Page | Status |
|---|---|---|---|---|---|---|
| 1 | **Readiness per home.** Each home gets a fit bucket, easy fit or needs work, with the permit that decided it. | Base sees which homes fit before anyone visits. | City of Austin permits (Socrata 3syk-w9eu). Rule on service upgrades, amps, solar, battery and build year. `house/permits.py fit()` → `house/cohort.json` | 22 of 40 homes easy fit, `house/cohort.json` (Measured) | [house.html](../web/house.html) | Built |
| 2 | **Address autofill.** The lead types an address. The page fills what records know and asks only the rest. | Each question the member skips is one less place to stop. | Address combobox over the public-record homes; each field carries its permit number and a confidence. `web/onboarding.js`, `house/cohort.json` | 161 of 200 fields filled from records (40 homes, 5 fields each), `house/cohort.json` (Measured) | [onboarding.html](../web/onboarding.html#home) | Built |
| 3 | **Guided steps with rewards.** Five milestones in one shared tracker. Each answer and the photo earn proposed points. | A clear next step and a reward keep a lead moving to installation. | One tracker component on journey, status and rewards, saved on this device. ADR 0016 points table: 10 pts per answer, 20 for the photo, 30 to finish, 50 per neighbour. `web/milestones.js` | Up to 100 pts per home, plus 50 pts per neighbour invite, `web/milestones.js` (Our design) | [journey](../web/onboarding.html#home), [status](../web/status.html), [rewards](../web/rewards.html) | Built |
| 4 | **Photo check.** The photo is classified on the spot and the member gets a retake tip right away. | The photo step is where leads stall. A tip in seconds replaces a wait for a human review. | Guided shot list saved on this device (`web/photo-checklist.js`). gemma4:e4b through local Ollama returns photo type and pass, with a fixed safe retake tip (`web/voice.js`, prompt from `panel/read.py`). Reads on 5 reference photos (`web/extraction-gallery.js`). | Photo type 16 of 21 local, 18 of 21 in the cloud model, `panel/BASELINE.md` (Measured) | [voice.html](../web/voice.html), [journey gallery](../web/onboarding.html#home) | Partly built. Next: read breaker amps (`docs/GAPS.md`). The live check runs when local Ollama is up. |
| 5 | **Voice guide.** One question at a time, spoken, with a caregiver view. | Some members need more help to finish, for example older members or members with a disability. | Browser speech synthesis and recognition; questions come from the home's public record; optional Kokoro-82M voice. `web/voice.js`, `brain/tts.py` | 5 yes/no questions and 1 photo, `web/voice.js buildSteps()` (Our design) | [voice.html](../web/voice.html) | Built |
| 6 | **Chat, any hour.** Help answers from the knowledge base at any hour. Account, contract and bill questions go to the Base Help Center. | Members ask at night and on weekends. Base team time goes to account work. | Indexed FAQs with sources, plus the ask server with gemma4:e4b on the local machine. `web/brain.html`, `web/data/faq.json`, `brain/ask.py` | 10 of 88 FAQs go to the Base team, `web/data/faq.json`; local answers 18 of 20 correct, `brain/LOCAL_VS_CLOUD.md` (Measured) | [brain.html](../web/brain.html) | Partly built. Next: hand off to a person during Base hours. |
| 7 | **Knowledge base.** One second brain behind every answer, each answer with its source. | Every answer stays the same across chat, voice and the Base team view. | Docs, FAQs and data files built into graph tables in `data/fleet.db` by `store/kb.py`, exported to `web/data/kb_graph.json` | 169 nodes, 1,075 links, `web/data/kb_graph.json` (Measured) | [knowledge.html](../web/knowledge.html) | Built |

## Base side

| # | What | Why | How | Proof | Page | Status |
|---|---|---|---|---|---|---|
| 8 | **Market intelligence.** Where Base installs, where ready homes concentrate, and grid prices by hour. | Go to market with zip-level targets before spend. | Permits by month, status and zip (`house/market.py` → `data/market.json`). Easy-fit estimate per zip from ACS and permits (`house/funnel.py` → `data/funnel.json`). ERCOT day-ahead prices (`data/ercot_dam_hourly_2025_2026.csv`). | 264 of 316 Base permits open, Austin 2026, `data/market.json` (Measured) | [market](../web/market.html), [explorer](../web/explorer.html), [grid](../web/grid.html) | Built |
| 9 | **Conversion view.** Leads through each stage to installation, with the dials that move them. | Shows where leads stall and what a guided photo step is worth. | Stage model with dials: photo drop 35% by default, 15% with guided collection. Both are assumptions. `sim/stages.py` → `web/data/report.json` | 318 of 513 served leads finish the photo, `web/data/report.json` (Simulation) | [index.html](../web/index.html) | Partly built. Next: Base's real drop rate. |
| 10 | **Same knowledge base for Base.** The Base team asks the same brain, with its own FAQ set. | Team and member answers stay in step. | Base team tab on Help for the Base admin role. `web/brain.html`, FAQ audience field in `web/data/faq.json` | 41 Base team FAQs, 47 member FAQs, `web/data/faq.json` (Measured) | [brain, team](../web/brain.html?track=home&persona=operations), [knowledge](../web/knowledge.html) | Built |

# Part 2. Base Super Local AI · Track 3 (Most Commercializable): local AI on the battery fleet

> Base is a power company, not a battery company, and is building a world-class product for its members. Build something that could actually ship as a product on top of what Base does. Show off your taste.
>
> Track 3 prompt

Our answer: a control tower for private AI next door. The PC beside the battery and a station on the feeder run open models for the member, with the backup reserve held first and the fleet holding up when a station goes offline, price spikes, or the scheduler drops. Spare GPU time sells to local businesses. A Base Fleet proposal.

Status: 4 built, 3 partly built, 3 open gaps.

| # | What | Why | How | Proof | Page | Status |
|---|---|---|---|---|---|---|
| 11 | **Why local AI.** Ask a question and the station on your street answers. Take a station offline or spike the grid price and ask again. | A battery home has steady power and a network for a small computer. Base is building the stations; a member AI service is a Base Fleet proposal. | Pitch page with a live ask box and a fleet toggle for station offline, price spike and battery at reserve. `web/pitch.js` | 0 GPU-hours lost with 2+ nodes per feeder; 50 nodes, 3 days: $142 power alone, $1,041 with compute, `grid/RATES.md` (Simulation) | [pitch.html](../web/pitch.html) | Built |
| 12 | **How it thinks, and Try it.** Each question runs through route, model, check and answer, step by step, with sources. | A member trusts an answer they can watch being made. | gemma4:e4b through Ollama on the home PC, or Qwen2.5-0.5B in the browser with WebLLM. `web/models.js`, `brain/ask.py`, `scripts/install-local.sh` | 18 of 20 correct, median 2.2 s, M2 laptop; Jetson 16 of 20, 3.0 s, `brain/LOCAL_VS_CLOUD.md` (Measured) | [models.html](../web/models.html), [Try it](../web/models.html#try) | Partly built. Next: target PC speed (#80). |
| 13 | **Your own AI.** A chat that runs on the PC beside the battery, with backup hours, today's grid prices and the Base Help Center one tap away. | The member's questions and home data stay with the member. | Home-first answers with sources, a backup-hours calculator from the battery settings, ERCOT prices. `web/copilot.js` | Median answer 2.2 s laptop, 3.0 s Jetson, `brain/LOCAL_VS_CLOUD.md` (Measured) | [copilot.html](../web/copilot.html) | Partly built. Next: run on the target PC (#80); internet-off test. |
| 14 | **Energy and credits.** What the battery and PC did this week, hour by hour, with the backup reserve locked. | The member sees what the hardware earned and that backup came first. | Seven days replayed on real ERCOT day-ahead prices; reserve setting tool; proposed points. `web/energy.js`, `data/members.json` | Library station $205.78 a week, one home $84.71 (4 batteries + 4 GPUs vs 1 + 1, 40% GPU use), `grid/LIBRARY_NODE.md` (Simulation) | [energy.html](../web/energy.html) | Built |
| 15 | **Three offers: Use, Host, Sell.** Members buy GPU time like energy, host a GPU for a share, and Base sells spare station time to local businesses. | Open models are close to the frontier; people lack the GPU. Base has the homes, installers and care to supply it. | Offer table, rate card, open-model catalog by machine, comparison with cloud APIs, the data rule. `docs/COMPUTE_PLANS.md` | 5 tiers pinned to public GPU prices, $0.16 to $1.09 per GPU-hour, checked 2026-09-26, `grid/RATES.md` (Measured; offers are Our design) | [plans.html](../web/plans.html) | Partly built. Next: set the Host revenue share. |
| 16 | **Stations.** A station could sit at the Menchaca Road Branch library, with homes on the same feeder covering each other. | A station holds more batteries and GPUs than one home and serves the homes around it. | City of Austin permits in a 1.5 km ring; station layout of 4 batteries and 4 GPU PCs; feeder topology. `grid/library_node.py`, `web/data/block.json` | 537 energy permits, 185 solar homes, 27 battery homes within 1.5 km of the library (Measured) | [overview](../web/overview.html), [placement](../web/placement.html), [block](../web/block.html) | Built |
| 17 | **Job rules and the control tower.** Backup reserve first, work stays on the feeder, grid price sets the pace. | Compute runs only on power the home can spare. | Fleet simulation on ERCOT day-ahead prices with node, region and scheduler interruptions. `sim/fleet.py`, `sim/server.py` | 0 reserve crossings, 0 jobs lost under kills; lowest-rate job pauses at $400/MWh, `grid/RATES.md` (Simulation) | [jobs.html](../web/jobs.html), [tower.html](../web/tower.html) | Built. Live controls with `python3 -m sim.server`. |
| 18 | **Open gaps.** Three measurements before the numbers are claims. | Speed, power and demand set what a member pays and earns. | #80 target PC speed; #85 one PC power draw (0.4 kW in the sim, 350 W in the hub model); demand, 40% GPU use as a dial (`sim/fleet.py UTIL`). `docs/COMPUTE_FLOW.md` | 3 open | [plans gaps](../web/plans.html#gaps) | Next |

## Open before we claim it

- **#80**: measure answer speed on the target Windows-class PC with the same questions (`docs/COMPUTE_FLOW.md`).
- **#85**: pick one PC power draw, 0.4 kW in the fleet sim or 350 W in the hub model, then run both again (`docs/COMPUTE_FLOW.md`).
- **Repo**: make the repo public so every source link opens for a judge (`docs/SUBMISSION_FORM.md`).

## Run it

From the repo root:

```sh
python3 -m http.server 8741          # pages; open http://localhost:8741/web/built.html
python3 -m brain.ask --serve 8742    # Help and Ask the data (Ollama with gemma4:e4b)
bash scripts/install-local.sh        # local AI on your PC, one command
```
