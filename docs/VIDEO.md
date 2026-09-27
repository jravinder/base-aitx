# Base Fleet video: end to end, lead to grid

One Loom, 4:40, in spine order (docs/GOAL.md). Home track beats 1 to 8, then Compute beats 9 to 13.
Serve from the repo root (`python3 -m http.server 8741`) and open each path below on
`http://localhost:8741`. On the hosted site, `/home` opens `start.html`.

Words: say "member" and "network". Every number on screen has its tag (Measured or Simulation).
Timings are recording targets.

| Beat | Time | Path to show | Length |
|---|---|---|---|
| 1 | 0:00 to 0:20 | /web/start.html | 20 s |
| 2 | 0:20 to 0:45 | /web/onboarding.html#home | 25 s |
| 3 | 0:45 to 1:05 | /web/onboarding.html#home | 20 s |
| 4 | 1:05 to 1:35 | /web/onboarding.html#home (photo step), /web/voice.html | 30 s |
| 5 | 1:35 to 1:52 | /web/status.html | 17 s |
| 6 | 1:52 to 2:05 | /web/rewards.html | 13 s |
| 7 | 2:05 to 2:20 | /web/brain.html | 15 s |
| 8 | 2:20 to 2:35 | /web/knowledge.html | 15 s |
| 9 | 2:35 to 2:55 | /web/pitch.html#how-it-works | 20 s |
| 10 | 2:55 to 3:25 | /web/copilot.html, /web/energy.html | 30 s |
| 11 | 3:25 to 3:50 | /web/overview.html, /web/placement.html, /web/block.html | 25 s |
| 12 | 3:50 to 4:15 | /web/jobs.html, /web/tower.html | 25 s |
| 13 | 4:15 to 4:40 | /web/pitch.html | 25 s |

## Home track

**Beat 1, 0:00 to 0:20. Pick your track.** `/web/start.html`

"End to end, lead to grid. Base can meet member demand; utility asks and permits set the pace.
So we built two things on one app: the path from your address to an installed battery, and,
once the battery is in, your own private AI next door. Pick your home, or local AI."

**Beat 2, 0:20 to 0:45. Your address.** `/web/onboarding.html#home`

"Type an address. Public permits already know most of the home: service upgrades, solar,
earlier batteries, with dates. The member sees their house from the record first."

Show the record card and its source link.

**Beat 3, 0:45 to 1:05. Only what records miss.** same page

"The member answers only what the records miss, one question at a time. Every answer earns
points, and the tracker at the top shows how close they are."

Click one answer; show the reward chip and the tracker move.

**Beat 4, 1:05 to 1:35. One photo, guided; voice for anyone.** photo step, then `/web/voice.html`

"One photo, guided step by step. Here is our design choice: AI never decides alone where the
physical world is at stake. The photo confirms what the records say, a person ticks each
uncertain field, and policy questions go to the Base team. For anyone who prefers to listen,
the voice guide reads each step aloud, with big buttons and a caregiver view."

**Beat 5, 1:35 to 1:52. Where it stands.** `/web/status.html`

"The member sees where the application stands and the one thing Base needs next."

**Beat 6, 1:52 to 2:05. Points and invites.** `/web/rewards.html`

"Points and invites live in one tracker. Base confirms credit at installation."

**Beat 7, 2:05 to 2:20. Questions answered.** `/web/brain.html`

"Questions get answers with their sources, any time. The Base team answers policy questions directly."

Ask one question; point at the source link.

**Beat 8, 2:20 to 2:35. The knowledge behind it.** `/web/knowledge.html`

"This is Base Brain, the knowledge behind every answer. Measured: a fixed-shape question takes
0.4 seconds on the template path; a free-text question through the agents takes 23 seconds.
We use the model only where it earns its time."

## Compute track

**Beat 9, 2:35 to 2:55. Your own AI next door.** `/web/pitch.html#how-it-works`

"Frontier AI takes your data, bills per question and needs the internet. Your own AI, on the
station next door, answers without sending your data away."

**Beat 10, 2:55 to 3:25. Useful on day one.** `/web/copilot.html`, then `/web/energy.html`

"Your home AI answers about your power, your week and your records: outage hours, what the
battery did this week, your permits. Measured: local answers in 2.2 seconds on a laptop and
3.0 seconds on an edge box."

Ask one question in copilot; then show the energy week.

**Beat 11, 3:25 to 3:50. Stations serve the homes around them.** `/web/overview.html`, `/web/placement.html`, `/web/block.html`

"Each station serves the member homes around it. A library holds more batteries and GPUs than
one house. When a station drops, a neighbour on the same feeder takes the work: with two or
more stations per feeder, the network loses no GPU hours in our simulation."

**Beat 12, 3:50 to 4:15. The control tower.** `/web/jobs.html`, then `/web/tower.html`

"The control tower runs jobs by priority and always protects the member's backup reserve.
Break a station here; the job moves, and the reserve holds at its 30 percent floor. Zero
breaches in the simulation."

Press one kill button; show the job move.
Both paths, the recorded replay on the page and the local simulator, run in simulation; no real GPU jobs run yet.

**Beat 13, 4:15 to 4:40. Close.** `/web/pitch.html`

"Base is building the stations; a member AI service is our proposal. Base has the stations,
the members and the crews. This is the software that makes them private AI for every member."

## Numbers said out loud, and where they come from

| Line | Tag | Source |
|---|---|---|
| Template path 0.4 s (0.37 s median, live permit query) vs agent 23 s (23.16 s median) | Measured | `brain/insights.json` |
| Local answers 2.2 s laptop, 3.0 s edge box (gemma4:e4b) | Measured | `brain/LOCAL_VS_CLOUD.md` |
| 0 GPU hours lost with 2+ stations per feeder | Simulation | `grid/NUMBERS.md`, `python3 -m sim.density` |
| 0 reserve breaches at a 30% floor | Simulation | `grid/NUMBERS.md`, `python3 -m sim` |

## Before recording

- Start the ask server (`python3 -m brain.ask --serve 8742`) for beats 7, 8 and 10.
- Start the control tower (`python3 -m sim.server --nodes 50 --tick 2`) for beat 12, or use the recorded replay on the page.
- Optional voice: `python3 -m brain.tts --serve 8744`; the browser voice reads the steps without it.
- Walk the spine once in the browser before you record.
