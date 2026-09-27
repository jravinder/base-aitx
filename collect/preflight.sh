#!/usr/bin/env bash
# Demo preflight: one green or red line per check. Exit code = number of red lines (0 = all green).
# Usage: bash collect/preflight.sh        (about 10 s warm, up to 30 s if gemma4 is cold)
set -u
LIVE="$HOME/base-fleet-live"
LOG="$LIVE/data/live/collect.log"
# The web root is the directory the 8741 server runs in. Fall back to the live clone.
PID=$(lsof -nP -tiTCP:8741 -sTCP:LISTEN 2>/dev/null | head -1)
WEBROOT=$( [ -n "$PID" ] && lsof -a -p "$PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1 )
[ -d "${WEBROOT:-}/web" ] || WEBROOT="$LIVE"
Q="What was the peak ERCOT load in 2025?"   # brain/templates.py load.peak_year, local file, no internet
FAILS=0
if [ -t 1 ]; then G=$'\e[32m'; R=$'\e[31m'; N=$'\e[0m'; else G=""; R=""; N=""; fi
ok()  { printf '%sOK  %s%s\n' "$G" "$1" "$N"; }
bad() { printf '%sRED %s%s\n' "$R" "$1" "$N"; FAILS=$((FAILS+1)); }
chk() { if eval "$2"; then ok "$1"; else bad "$1${3:+  -> fix: $3}"; fi; }
age_min() { echo $(( ( $(date +%s) - $(stat -f %m "$1" 2>/dev/null || echo 0) ) / 60 )); }
now=$(date +%s)

# 1. launchd collectors
for f in "$HOME"/Library/LaunchAgents/com.basefleet.*.plist; do
  j=$(basename "$f" .plist | sed 's/^com.basefleet.//')
  chk "launchd com.basefleet.$j loaded" "launchctl list | grep -q 'com.basefleet.$j\$'" "bash $LIVE/collect/install_mac.sh"
done

# 2. collector freshness (log stamps are UTC)
H=$(grep -E '^[0-9]{8}T[0-9]{4}Z ok ' "$LOG" 2>/dev/null | tail -1 | cut -c1-13)
if [ -n "$H" ]; then
  HM=$(( (now - $(TZ=UTC date -j -f %Y%m%dT%H%M "$H" +%s)) / 60 ))
  chk "hourly ERCOT pull ${HM} min ago ($H)" "[ $HM -lt 90 ]" "bash $LIVE/collect/ercot_feeds.sh"
else bad "hourly ERCOT pull: no ok line in $LOG"; fi
D=$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} ok ' "$LOG" 2>/dev/null | tail -1 | cut -c1-10)
chk "daily pull today (last $D)" "[ '$D' = '$(date +%F)' ] || [ '$D' = '$(date -u +%F)' ]" "bash $LIVE/collect/daily.sh"

# 3. data on the served web root
DB="$WEBROOT/data/fleet.db"
P=$(sqlite3 "$DB" 'select count(*) from permits' 2>/dev/null || echo 0)
chk "fleet.db permits rows $P (> 30000) in $WEBROOT" "[ ${P:-0} -gt 30000 ]" "cp $LIVE/data/fleet.db $WEBROOT/data/"
for f in signals grid_today; do
  A=$(age_min "$WEBROOT/web/data/$f.json")
  chk "web/data/$f.json updated $A min ago (< 120)" "[ $A -lt 120 ]" "cp $LIVE/web/data/{grid_today,signals,admin}.json $WEBROOT/web/data/"
done

# 4. ports
for p in 8741 8742 8732 11434; do
  chk "port $p answers" "curl -s -o /dev/null -m 3 http://127.0.0.1:$p/" "see docs/DEMO_RUNBOOK.md start order"
done

# 5. ask server: template question under 2 s, streamed trace
T0=$(python3 -c 'import time;print(time.time())')
OUT=$(curl -s -N -m 5 -X POST 'http://127.0.0.1:8742/ask?stream=1' -H 'Content-Type: application/json' -d "{\"q\":\"$Q\"}")
MS=$(python3 -c "import time;print(int((time.time()-$T0)*1000))")
STEPS=$(printf '%s\n' "$OUT" | grep -c '"ev": "step"')
chk "ask answers template in ${MS} ms (< 2000), trace $STEPS steps" "[ $MS -lt 2000 ] && [ $STEPS -ge 3 ] && printf '%s' \"\$OUT\" | grep -q '\"ev\": \"done\"'" "python3 -m brain.ask --serve 8742"

# 6. sim server
NODES=$(curl -s -m 3 http://127.0.0.1:8732/state | python3 -c 'import json,sys;print(len(json.load(sys.stdin).get("nodes",[])))' 2>/dev/null || echo 0)
chk "sim /state returns $NODES nodes" "[ ${NODES:-0} -gt 0 ]" "python3 -m sim.server --tick 0.5"

# 7. Ollama gemma4:e4b listed and answers 5 tokens (keep_alive 30m warms it for the demo)
chk "ollama lists gemma4:e4b" "curl -s -m 3 http://127.0.0.1:11434/api/tags | grep -q '\"gemma4:e4b\"'" "ollama pull gemma4:e4b"
T0=$(python3 -c 'import time;print(time.time())')
GEN=$(curl -s -m 40 http://127.0.0.1:11434/api/generate -d '{"model":"gemma4:e4b","prompt":"Say hi","stream":false,"think":false,"keep_alive":"30m","options":{"num_predict":5}}' | python3 -c 'import json,sys;print(json.load(sys.stdin).get("response","").strip()[:30])' 2>/dev/null)
MS=$(python3 -c "import time;print(int((time.time()-$T0)*1000))")
chk "gemma4:e4b answers 5 tokens in ${MS} ms: \"$GEN\"" "[ -n \"\$GEN\" ]" "brew services restart ollama"

# 8. internet sources
code() { curl -s -o /dev/null -w '%{http_code}' -m 8 "$1"; }
C=$(code https://www.ercot.com/api/1/services/read/dashboards/fuel-mix.json)
chk "ERCOT dashboard API reachable ($C)" "[ '$C' = 200 ]" "Wi-Fi; pages use last cached pull"
C=$(code 'https://data.austintexas.gov/resource/3syk-w9eu.json?$limit=1')
chk "Austin Socrata reachable ($C)" "[ '$C' = 200 ]" "Wi-Fi; permit questions fall back to fleet.db / recorded answers"

# 9. latest Vercel production deployment is login-protected (302)
VURL=$(cd "$(dirname "$0")/.." && timeout 20 vercel ls --prod 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.vercel\.app' | head -1)
[ -z "$VURL" ] && VURL=$(cd "$(dirname "$0")/.." && timeout 20 vercel ls 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.vercel\.app' | head -1)
C=$([ -n "$VURL" ] && code "$VURL" || echo none)
chk "Vercel ${VURL:-?} answers $C (302 to login)" "[ '$C' = 302 ]" "vercel login; or demo from localhost"

# 10. disk
FREE=$(df -g / | awk 'NR==2{print $4}')
chk "disk free ${FREE} GB (> 5)" "[ ${FREE:-0} -gt 5 ]" "empty ~/Library/Caches or old data/live/ercot files"

echo "web root: $WEBROOT   demo URL: http://localhost:8741/web/story.html"
[ $FAILS -eq 0 ] && printf '%sALL GREEN%s\n' "$G" "$N" || printf '%s%d RED%s\n' "$R" "$FAILS" "$N"
exit $FAILS
