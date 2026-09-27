# Base Brain

Issue #52. Post-onboarding Q&A over one member's own record: house fields, node, and the week of earnings. Same intelligence that knew the house before the photo, now it knows the member after install.

## What it is

- `brain/members.py` joins `house/cohort.json`, sim node state, and `grid/earned.py` into `data/members.json` (40 members, no addresses, no names).
- `brain/answer.py` answers one question for one member. Retrieval is token overlap between the question and record sections (fields, node, day rows, event strings). No embeddings. The question and the top 8 sections go to `gemma4:e4b` through local Ollama with `think: false`. If Ollama is down, a rule-based answerer runs on the same sections.
- `brain/score.py` runs `brain/questions.json` for m001 and writes `brain/pred.jsonl`.
- `web/member.html` shows the record on the left and the question box on the right. Chips replay the scored answers. Free text calls `http://localhost:11434` from the browser and says "needs local Ollama" if that fails. GAP answers render in amber.

Run: `python3 -m brain.score m001`, then `python3 -m http.server 8741` and open `http://localhost:8741/web/member.html`.

## Score

9 of 10 for m001 on 2026-09-26, Ollama up, gemma4:e4b, about 1 s per answer.

| Result | Count |
|---|---|
| correct | 7 |
| GAP correct | 2 of 2 |
| wrong | 1 |

The one miss (q06, GPU hours sold) is a right answer, "168 GPU hours were run this week", that the strict judge rejects because it wants two numbers from the expected text. A GAP question counts only if the answer starts with `GAP`. Both policy questions (next credit date, can I cancel) return `GAP: not in your record. Ask Base support.`

Two fixes that moved the score from 2 to 9: `think: false` (gemma4 spent the whole token budget on hidden reasoning and returned empty strings) and a per-day total in the day rows (the model mis-summed the best day across seven rows without it).

## The rule

Never invent Base policy. The system prompt allows only the record. Fees, contracts, credit dates, and eligibility rules are never in the record, so the brain says GAP and points to Base support. The pre-sale FAQ (`faq/`) had 11 GAPs of 25 for the same reason. Unknown stays unknown, out loud.

## The ceiling

The record is scaffolded: cohort permits plus a 72 hour sim cycled to a week plus two real ERCOT day-ahead days. The real version runs on Base's own telemetry (per interval battery state, dispatch reasons, credits posted) and ticket history (the questions members really ask and the answers support really gave). With those, the GAP class shrinks to true policy questions and the judge becomes real ticket outcomes. We show the shape, not the data.

## Beat 9 sentence for docs/VIDEO.md

Screen: `member.html`, member m001. Click "why did my battery discharge at 5 pm on day 2", then "what did my node earn this week", then "when is my next credit paid".

Voice (about 70 words, 30 seconds):

> The same brain that read the house before the photo now answers the member after install. Why did my battery discharge at five on day two: peak price, one hundred one dollars a megawatt hour, reserve held. What did my node earn: eight ninety four battery, one twenty five GPU, one thirty four total. When is my next credit paid: not in your record, ask Base support. Nine of ten. It never invents policy.
