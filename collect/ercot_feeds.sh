#!/usr/bin/env bash
# Pull ERCOT public dashboard feeds (no login, no browser). Run hourly.
# Output: $OUT/ercot/<feed>/<UTC stamp>.json.gz . Skips when free disk < 300 MB.
set -u
OUT="${COLLECT_OUT:-$(cd "$(dirname "$0")/.." && pwd)/data/live}"
mkdir -p "$OUT"
FREE_MB=$(df -Pm "$HOME" | awk 'NR==2{print $4}')
[ "$FREE_MB" -lt 300 ] && { echo "$(date -u +%FT%TZ) skip: ${FREE_MB} MB free" >> "$OUT/collect.log"; exit 0; }
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
STAMP=$(date -u +%Y%m%dT%H%MZ)
HOURLY="system-wide-prices supply-demand fuel-mix"
DAILY="daily-prc"
FEEDS="$HOURLY"; [ "$(date -u +%H)" = "12" ] && FEEDS="$FEEDS $DAILY"
for f in $FEEDS; do
  mkdir -p "$OUT/ercot/$f"
  if curl -sf -A "$UA" -H "Accept: application/json" -H "Referer: https://www.ercot.com/gridmktinfo/dashboards" \
       "https://www.ercot.com/api/1/services/read/dashboards/$f.json" | gzip > "$OUT/ercot/$f/$STAMP.json.gz.tmp" \
     && [ -s "$OUT/ercot/$f/$STAMP.json.gz.tmp" ]; then
    mv "$OUT/ercot/$f/$STAMP.json.gz.tmp" "$OUT/ercot/$f/$STAMP.json.gz"; echo "$STAMP ok $f" >> "$OUT/collect.log"
  else
    rm -f "$OUT/ercot/$f/$STAMP.json.gz.tmp"; echo "$STAMP FAIL $f" >> "$OUT/collect.log"
  fi
done
# NWS active alerts, Travis and Williamson counties (keyless; NWS asks for a User-Agent).
mkdir -p "$OUT/nws"
if curl -sf -m 30 -A "base-fleet signals (github.com/jravinder/base-aitx)" -H "Accept: application/geo+json" \
     "https://api.weather.gov/alerts/active?zone=TXC453,TXC491" | gzip > "$OUT/nws/$STAMP.json.gz.tmp" \
   && [ -s "$OUT/nws/$STAMP.json.gz.tmp" ]; then
  mv "$OUT/nws/$STAMP.json.gz.tmp" "$OUT/nws/$STAMP.json.gz"; echo "$STAMP ok nws-alerts" >> "$OUT/collect.log"
else
  rm -f "$OUT/nws/$STAMP.json.gz.tmp"; echo "$STAMP FAIL nws-alerts" >> "$OUT/collect.log"
fi
# Store and signals (data/fleet.db, web/data/signals.json); never fail the collector.
(cd "$(dirname "$0")/.." && python3 store/build.py --incremental >/dev/null 2>&1 && python3 store/signals.py >/dev/null 2>&1) || true
# Rebuild the grid page and admin dashboard data; never fail the collector.
(cd "$(dirname "$0")/.." && python3 grid/today.py >/dev/null 2>&1) || true
(cd "$(dirname "$0")/.." && python3 admin/build.py >/dev/null 2>&1) || true
