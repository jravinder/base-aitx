#!/usr/bin/env bash
# Daily: Austin permits by zip and the Base market view. Stdlib Python only.
set -u
cd "$(dirname "$0")/.." || exit 1
OUT="${COLLECT_OUT:-$(cd "$(dirname "$0")/.." && pwd)/data/live}"; mkdir -p "$OUT/daily"
D=$(date -u +%F)
for m in house.permits_by_zip house.market; do
  if python3 -m "$m" > "$OUT/daily/$m-$D.log" 2>&1; then echo "$D ok $m" >> "$OUT/collect.log"; else echo "$D FAIL $m" >> "$OUT/collect.log"; fi
done
# Energy permit mirror: only rows issued since the newest issue_date on file.
if python3 -m house.mirror --incremental > "$OUT/daily/house.mirror-$D.log" 2>&1; then echo "$D ok house.mirror" >> "$OUT/collect.log"; else echo "$D FAIL house.mirror" >> "$OUT/collect.log"; fi
# Store and signals after the mirror; never fail the collector.
(python3 store/build.py --incremental >/dev/null 2>&1 && python3 store/signals.py >/dev/null 2>&1) || true
cp data/permits_by_zip.json "$OUT/daily/permits_by_zip-$D.json"
cp data/market.json "$OUT/daily/market-$D.json"
# Rebuild the admin dashboard data; never fail the collector.
(cd "$(dirname "$0")/.." && python3 admin/build.py >/dev/null 2>&1) || true
# Rebuild the "Questions people ask" answers from the fresh data; never fail the collector.
(cd "$(dirname "$0")/.." && python3 store/data_qa.py >/dev/null 2>&1) || true
# Rebuild Base Brain (kb_nodes, kb_edges, web/data/kb_graph.json); never fail the collector.
(cd "$(dirname "$0")/.." && python3 store/kb.py >/dev/null 2>&1) || true
# Rebuild the Base Brain FAQs (member and Base team); run after store/kb.py so the faq nodes stay. Never fail the collector.
(cd "$(dirname "$0")/.." && python3 store/faq.py >/dev/null 2>&1) || true
# Learning loop from member questions (store/learn.py): questions table, proposals, web/data/learning.json; never fail the collector.
(cd "$(dirname "$0")/.." && python3 store/learn.py >/dev/null 2>&1) || true
