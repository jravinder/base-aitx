# Base Power member FAQ — public-corpus coverage

Corpus: `faq/corpus/` (home, how-it-works, pricing, help-center-index). BrainBox ran the 25 questions and wrote `faq/pred.jsonl`.

| # | Question | Status |
|---|---|---|
| 1 | Photo requirements for eligibility review | GAP |
| 2 | How long the eligibility review takes | GAP |
| 3 | What disqualifies a home | GAP |
| 4 | Max panel amps allowed | GAP |
| 5 | Gas meter effect on install | GAP |
| 6 | Does Base handle HOA approval | GAP |
| 7 | Renter vs. owner eligibility | GAP |
| 8 | Service areas / territory | Answered |
| 9 | Battery size in kWh | Answered |
| 10 | How many batteries per home | Answered |
| 11 | What happens during a grid outage | Answered |
| 12 | How long the battery lasts in an outage | Answered |
| 13 | What Base costs | Answered |
| 14 | Contract or commitment length | GAP |
| 15 | Monthly membership fee | Answered |
| 16 | Do I have to switch energy provider | Answered |
| 17 | What happens if I move | GAP (see note) |
| 18 | Where the battery is installed | Answered |
| 19 | Solar panel compatibility | GAP |
| 20 | Battery safety (weather, fire, flood) | Answered |
| 21 | Installation timeline and visits | Answered |
| 22 | Do I own the battery | GAP |
| 23 | Max home power draw for battery to engage | Answered |
| 24 | Can I add a second battery later | GAP |
| 25 | Portable generator compatibility | GAP |

**The model returned GAP on 11 of 25 and answered 14. The table marks 13 as not covered by Base public pages: rows 6 (HOA) and 19 (solar) got a model answer the pages do not support.**

Note on #17: the corpus does answer "what happens if I move" ("the battery agreement runs with the home... if not, we'll remove the system"), but BrainBox's own generated answer for this question came back GAP because retrieval did not surface the right chunk in the top 4 results — a retrieval miss, not a true corpus gap. `faq/questions.json` records the correct corpus quote; `faq/pred.jsonl` records what the model actually said.

## The gap, in one paragraph

The public pages sell the pitch and the mechanics of the battery (size, outage behavior, install steps, one sample price) but say nothing about how membership is actually granted. Every question a real prospect asks before signing up — what photos to submit, how long review takes, what disqualifies a house, panel amp limits, gas meter rules, HOA process, renter eligibility, contract terms, ownership of the hardware, and adding a second battery — lives behind the Help Center's 62 "Backup battery service" articles and the logged-in member chat, neither of which a public crawl can reach. A member FAQ bot built only from these public pages can answer "what is this and what does it cost," but not "can I actually get one," which is the question that decides whether someone signs up.

## Files
- `faq/corpus/home.md`, `how-it-works.md`, `pricing.md`, `help-center.md` — source text with URLs
- `faq/questions.json` — 25 questions with corpus quotes or GAP
- `faq/pred.jsonl` — BrainBox (gbrain search + gemma4:e4b) answers to all 25
