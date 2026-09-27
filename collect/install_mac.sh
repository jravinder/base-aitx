#!/usr/bin/env bash
# Install the collectors as launchd jobs on this Mac. Idempotent.
#   ercot_feeds.sh  hourly at :07
#   daily.sh        06:15 local
#   monthly.sh      2nd of the month, 06:30 local
#   publish.sh      every 3 hours at :20 (rebuild and vercel deploy --prod)
# Servers (KeepAlive, RunAtLoad): pages 8741, ask 8742, sim 8732
# Output: data/live/ (gitignored). Logs: data/live/collect.log and ~/Library/Logs/base-fleet-*.log
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LA="$HOME/Library/LaunchAgents"
# vercel lives under nvm, so put its directory on the job PATH.
VB="$(dirname "$(command -v vercel 2>/dev/null || echo /usr/local/bin/vercel)")"
PATHS="/opt/homebrew/bin:/usr/local/bin:$VB:/usr/bin:/bin:/usr/sbin:/sbin"
mk() { # label script calendar-xml
  local plist="$LA/com.basefleet.$1.plist"
  cat > "$plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.basefleet.$1</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$REPO/collect/$2</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$PATHS</string></dict>
  <key>StartCalendarInterval</key>$3
  <key>StandardOutPath</key><string>$HOME/Library/Logs/base-fleet-$1.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/base-fleet-$1.log</string>
</dict></plist>
PL
  launchctl bootout "gui/$(id -u)/com.basefleet.$1" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
}
mk ercot ercot_feeds.sh '<dict><key>Minute</key><integer>7</integer></dict>'
mk daily daily.sh '<dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>15</integer></dict>'
mk monthly monthly.sh '<dict><key>Day</key><integer>2</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>'
mk publish publish.sh "$(for h in 0 3 6 9 12 15 18 21; do printf '<dict><key>Hour</key><integer>%s</integer><key>Minute</key><integer>20</integer></dict>' $h; done | sed 's/^/<array>/; s/$/<\/array>/')"

svc() { # label port python-args...
  local label=$1 port=$2; shift 2
  local plist="$LA/com.basefleet.$label.plist" args=""
  for a in "$@"; do args="$args<string>$a</string>"; done
  cat > "$plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.basefleet.$label</string>
  <key>ProgramArguments</key><array><string>/opt/homebrew/bin/python3</string>$args</array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$PATHS</string><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/base-fleet-$label.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/base-fleet-$label.log</string>
</dict></plist>
PL
  launchctl bootout "gui/$(id -u)/com.basefleet.$label" 2>/dev/null || true
  # Stop only the process that listens on this port (for example a hand-started server).
  lsof -ti "tcp:$port" -sTCP:LISTEN | xargs kill 2>/dev/null || true
  sleep 1
  launchctl bootstrap "gui/$(id -u)" "$plist"
}
svc pages 8741 -m http.server 8741
svc ask 8742 -m brain.ask --serve 8742
svc sim 8732 -m sim.server --tick 0.5 --port 8732
launchctl list | grep com.basefleet
