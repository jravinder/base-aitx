# Base Brain: the app knowledge base

Base Brain is the app's second brain. It has two parts: this knowledge base (how the repo connects) and the member Q&A. This file is about the knowledge base. Page: web/knowledge.html ("How it all connects"). Code: store/kb.py.

## What is in it

The knowledge base is a graph in data/fleet.db. It has two tables:

- `kb_nodes(slug, type, title, summary, body, repo_path, updated_at)`
- `kb_edges(src, dst, type, source)`

Every slug starts with `hackathons/2026-09-base-fleet-data/`, the same prefix as the gbrain data pages. A dataset node has the same slug as its gbrain page (for example `.../ercot-load`). Other nodes use `<type>-<name>` (for example `.../zip-78665`, `.../gap-80`, `.../doc-docs-submission`).

Node types:

| type | what | from |
|---|---|---|
| hub | the start node, `.../index` | store/kb.py |
| dataset | 15 datasets (permits, Base rollout, storms, territory, funnel, demographics, deeds, ERCOT prices, load, live feeds, sim numbers, judgments, signals, local AI tests, gaps) | DATASETS in store/kb.py; the body is read from the gbrain page when the CLI is on the machine |
| doc | SUBMISSION, VIDEO, GAPS, DATAFLOW, MIRROR_SCHEMA, STORM_RUSH, DEEDS, STAR_AREAS, PERSONAS, DEMO_RUNBOOK, BACKEND_CHECK, SUBMISSION_FORM, UX_REDESIGN, this file, every ADR, grid/*.md, brain/LOCAL_VS_CLOUD.md, collect/README.md | the first prose lines of each doc, its section names and its text |
| page | every web/*.html | the question in the h1, the data files it reads, the persona tours it is in |
| gap | every GitHub issue titled "Gap:" | web/data/gaps.json, git log for the fix commit |
| persona | every tour | web/data/tours.json |
| zip | every zip in data/funnel.json | who sells power, easy-fit homes, Base permits in 2026, deed turnover, assisted priority |
| signal | the 5 rules | RULES in store/signals.py |
| job | the launchd jobs | collect/install_mac.sh and the job scripts |

Link types. Each link comes from the repo, not from a hand list:

| link | rule |
|---|---|
| page `reads` dataset, dataset `feeds` page | a data file path in the page or its local js |
| doc `describes` dataset or page | the doc names a file of the dataset, or the page file |
| doc `cites_number` dataset | the doc names a file of the dataset on a line that has a number |
| doc `references` doc | a doc path, an ADR number or an upper-case doc name |
| gap `affects` page, dataset or doc | a path, a module name, a page name or a doc name in the issue text |
| gap `fixed_by` commit | the newest commit that names the issue number (kept in the table, not drawn) |
| persona `tours` page | a stop in tours.json |
| zip `appears_in` page | the zip in the page or in a data file the page reads |
| job `refreshes` dataset, job `serves` page | the script calls the dataset producer; the page names the service port |
| signal `watches` dataset, signal `writes` signals | the rule text in store/signals.py |
| hub `spine` | the story page, the two submission docs, the 5 main datasets |

No personal data: the build removes network addresses, key-shaped strings, e-mail addresses and street addresses, and uses no owner names. Nothing says what Base plans or what hardware Base uses.

## How to query it

From Python (the ask server calls this):

```python
from store.kb import kb_search
kb_search("Which page shows ERCOT prices and what job refreshes it?", k=5)
```

It scores nodes by word overlap (title x3, summary x2, body x1, weighted by rarity), then adds the one-hop neighbours of each hit. Each result has slug, type, title, summary, text, path, score, via (the hit it came from) and links.

From the command line:

```sh
python3 store/kb.py --search "open gap about local AI speed"
sqlite3 data/fleet.db "SELECT type, count(*) FROM kb_edges GROUP BY type"
sqlite3 data/fleet.db "SELECT dst, type FROM kb_edges WHERE src LIKE '%zip-78665'"
```

In the browser: web/knowledge.html. Search, filter by type, click a node for its summary and links.

The dataset pages are also in gbrain (the builder's personal brain, read only from this repo). To walk them there: `gbrain graph hackathons/2026-09-base-fleet-data/index --depth 2`. The app does not write to gbrain.

## How it refreshes

`python3 store/kb.py` deletes the kb rows and writes them again in one transaction. A run twice gives the same rows. It also writes web/data/kb_graph.json. collect/daily.sh runs it at the end, at 06:15 each day; a failure does not stop the collector.
