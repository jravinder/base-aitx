# Collectors

Run on the Mac through launchd. Install or reinstall: `bash collect/install_mac.sh`.

| Job | Script | When | Output |
|---|---|---|---|
| com.basefleet.ercot | ercot_feeds.sh | hourly at :07 | data/live/ercot/<feed>/<UTC>.json.gz: system-wide-prices, supply-demand, fuel-mix; daily-prc at 12 UTC; data/live/nws/<UTC>.json.gz (NWS alerts, Travis and Williamson); then store/build.py --incremental and store/signals.py |
| com.basefleet.daily | daily.sh | 06:15 | data/permits_by_zip.json, data/market.json, and dated copies in data/live/daily/; then store/build.py --incremental and store/signals.py |
| com.basefleet.monthly | monthly.sh | 2nd, 06:30 | data/demographics.json and a dated copy in data/live/monthly/ |
| com.basefleet.publish | publish.sh | every 3 hours at :20 | discards generated web/data/*.json and data/*.json, git pull, puts back the newest daily permits and market copies, reruns store/build.py, store/signals.py, grid/today.py, admin/build.py, store/data_qa.py, then `vercel deploy --prod --yes`. Vercel Authentication stays on. Manual run: `bash ~/base-fleet-live/collect/publish.sh` |

## Local servers

The installer also loads three servers as launchd agents with RunAtLoad and KeepAlive. They start at login and restart if they stop. Before each load, the installer stops only the process that listens on that port.

| Job | Port | Command | Check |
|---|---|---|---|
| com.basefleet.pages | 8741 | python3 -m http.server 8741 (clone root) | `curl localhost:8741/` |
| com.basefleet.ask | 8742 | python3 -m brain.ask --serve 8742 (127.0.0.1 only) | `curl localhost:8742/health` |
| com.basefleet.sim | 8732 | python3 -m sim.server --tick 0.5 --port 8732 | `curl localhost:8732/state` |

Logs: ~/Library/Logs/base-fleet-<job>.log. The ask server needs Ollama on 11434 with gemma4:e4b. Restart one server: `launchctl kickstart -k gui/$(id -u)/com.basefleet.<job>`.

No login and no browser. ERCOT answers plain requests on `system-wide-prices.json` (hyphen); `systemWidePrices.json` redirects to a bot wall. Status lines go to data/live/collect.log. data/live/ is gitignored.

Stop: `launchctl bootout gui/$(id -u)/com.basefleet.<job>`.

## Where the jobs run (macOS privacy)

launchd jobs cannot read files under ~/Documents ("Operation not permitted"), so the jobs run from a clone outside it: ~/base-fleet-live. Install with `bash ~/base-fleet-live/collect/install_mac.sh`. Collected data lands in ~/base-fleet-live/data/. Before a commit or deploy, copy it into this repo:

    rsync -a ~/base-fleet-live/data/live/ data/live/ && cp ~/base-fleet-live/data/fleet.db data/ && cp ~/base-fleet-live/web/data/{grid_today,signals,admin}.json web/data/

Pull code changes into the clone with `git -C ~/base-fleet-live pull`.
