# Base Brain: learning from member questions

Generated 2026-09-27T01:18:07Z by `store/learn.py`. Do not edit by hand.

## How the loop works

1. Log. The ask server (`/ask` and `/ask?stream=1`), Base Brain (`brain/answer.py`) and typed questions on `web/member.html` (through `POST /learn/log` when a local server runs) append one line per question to `data/live/questions.jsonl`: time, page, question, member id, path, template id, answered, critic pass, seconds, and the first 200 characters of the answer. The logger removes emails, phone numbers, street addresses, IP addresses and "my name is" names. The server does not log the caller IP address.
2. Learn. `collect/daily.sh` runs `python3 store/learn.py` each night. It loads the log into table `questions` in `data/fleet.db`, groups the last 30 days of questions by normalised text and token overlap, and ranks the groups: unanswered or gap first, then critic fails, then slow agent answers (more than 10 s).
3. Propose. Each group gets one proposal: a new template (intent, parameters, data source, draft SoQL or local filter), a new cached answer (only when a template produces it now and the critic passes; never from an agent answer), or "Base policy question: route to Base support" (credits, cancelling, payments, contracts, eligibility).
4. Approve. A person approves or rejects each proposal on the admin page. The buttons call `POST /learn/approve` and `POST /learn/reject` on the ask server, which accepts localhost only and records who and when in `data/live/learn_decisions.jsonl`. An approved cached answer goes into `brain/insights.json` and into the app knowledge base as a `learned_answer` node. Nothing goes live without approval.
5. Knowledge base. The ask planner has a `kb` source: questions about our data or methods (not a live number) get an answer from `store/kb.py` `kb_search`, cited as "Base Brain knowledge base: <slug>". Base Brain answers a member from the member record first, then from the knowledge base. Each run of this script writes the weekly summary as a `member_questions` node. No personal data goes into the knowledge base, and Base policy is never written as fact.
6. Signal. `learning.json` field `signal` has `unanswered_7d` and `unanswered_prev_7d` for an `unanswered_spike` rule.

## This week

100 questions, 88 answered, median 0.0 s. All time logged: 100.

| Path | Asked | Answered |
|---|---:|---:|
| cache | 73 | 73 |
| template | 4 | 3 |
| kb | 4 | 4 |
| agent | 10 | 8 |
| gap | 3 | 0 |
| base_support | 6 | 0 |

Signal unanswered_spike: 12 unanswered this week, 0 the week before.

## Top unanswered

- Can I cancel my Base contract early? (asked 2)
- When will my first bill credit be paid out? (asked 2)
- Does Base work with my solar panels? (asked 1)
- I rent my house, can I still get a battery? (asked 1)
- Does my HOA need to approve the battery? (asked 1)
- What was the highest power price in Austin last week? (asked 1)
- What is the weather forecast for Austin this weekend? (asked 1)
- Which zips have the most backup generators? (asked 1)
- will my battery keep my AC on in an outage (asked 1)
- what is my neighbor earning (asked 1)

## What members ask that only Base can answer

- Can I cancel my Base contract early? (asked 2)
- When will my first bill credit be paid out? (asked 2)
- Does Base work with my solar panels? (asked 1)
- I rent my house, can I still get a battery? (asked 1)
- Does my HOA need to approve the battery? (asked 1)

## Proposals

| # | Kind | Question | Proposal | Asked | Status |
|---:|---|---|---|---:|---|
| 1 | new_template | Which zips have the most backup generators? | New template permits.zip_top_backup | 1 | proposed |
| 2 | base_support | Can I cancel my Base contract early? | Base policy question: route to Base support | 2 | proposed |
| 3 | base_support | When will my first bill credit be paid out? | Base policy question: route to Base support | 2 | proposed |
| 4 | new_template | What was the highest power price in Austin last week? | New template dam.top_power_price | 1 | proposed |
| 5 | new_template | What is the weather forecast for Austin this weekend? | New template load.weather_forecast_austin | 1 | proposed |
| 6 | base_support | Does Base work with my solar panels? | Base policy question: route to Base support | 1 | proposed |
| 7 | base_support | I rent my house, can I still get a battery? | Base policy question: route to Base support | 1 | proposed |
| 8 | base_support | Does my HOA need to approve the battery? | Base policy question: route to Base support | 1 | proposed |
| 9 | new_template | will my battery keep my AC on in an outage | New template zips.battery_keep_ac | 1 | proposed |
| 10 | new_template | what is my neighbor earning | New template none.neighbor_earn | 1 | proposed |
| 11 | new_template | How many Base batteries were installed in 78745 this year? | New template zips.base_battery_install | 1 | proposed |
| 12 | new_template | Will there be a power outage in my neighborhood tomorrow? | New template none.power_outage_neighborhood | 1 | proposed |
| 13 | new_template | How many homes in 78745 have solar and a battery? | New template zips.home_solar_battery | 1 | proposed |
| 14 | new_template | What is my neighbor's battery earning? | New template zips.neighbor_s_battery | 1 | proposed |
| 15 | new_template | How much money do Base members save on average? | New template none.money_base_member | 1 | proposed |
| 16 | cached_answer | How many Base permits in 78745 this year? | Cache the answer from template permits.base.count | 1 | proposed |
| 17 | cached_answer | How long does a Base install take from permit to final? | Cache the answer from template permits.base.status | 1 | rejected |
| 18 | new_template | Is the grid in an emergency right now? | New template load.grid_emergency | 1 | proposed |

Draft queries for new templates are in `web/data/learning.json` (`proposals[].draft`).
