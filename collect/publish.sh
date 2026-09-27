#!/usr/bin/env bash
# Publish: pull code into the live clone, rebuild the generated data, deploy to Vercel (production).
# Runs from the clone (~/base-fleet-live), by hand or as com.basefleet.publish (every 3 hours at :20).
# Vercel Authentication stays on: the deployment answers 302 to the Vercel login.
set -eu
cd "$(dirname "$0")/.."
echo "== publish $(date -u +%FT%TZ) in $(pwd)"
# The builders rewrite tracked JSON. Discard those changes so the pull cannot conflict.
git checkout -- web/data/ data/*.json
git pull --ff-only
# The checkout reverts the daily permits and market files. Put back the newest collected copies.
for f in permits_by_zip market; do
  last=$(ls -1 data/live/daily/$f-*.json 2>/dev/null | tail -1 || true)
  [ -n "$last" ] && cp "$last" "data/$f.json"
done
python3 store/build.py --incremental
python3 store/signals.py
python3 grid/today.py
python3 admin/build.py
python3 store/data_qa.py
python3 -c "import json;print('grid_today as_of', json.load(open('web/data/grid_today.json')).get('as_of'))"
vercel deploy --prod --yes
echo "== publish done $(date -u +%FT%TZ)"
