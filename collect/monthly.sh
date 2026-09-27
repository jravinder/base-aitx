#!/usr/bin/env bash
# Monthly: ACS demographics per zip (Census Reporter, keyless).
set -u
cd "$(dirname "$0")/.." || exit 1
OUT="${COLLECT_OUT:-$(cd "$(dirname "$0")/.." && pwd)/data/live}"; mkdir -p "$OUT/monthly"
M=$(date -u +%Y-%m)
python3 house/demographics.py > "$OUT/monthly/demographics-$M.log" 2>&1 && cp data/demographics.json "$OUT/monthly/demographics-$M.json" && echo "$M ok demographics" >> "$OUT/collect.log" || echo "$M FAIL demographics" >> "$OUT/collect.log"
