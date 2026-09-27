#!/bin/bash
# Base Fleet local AI: one-shot setup on your own PC. Everything runs on this machine.
#
#   git clone https://github.com/jravinder/base-aitx.git && cd base-aitx && bash scripts/install-local.sh
#
# In order (each step skipped if already done):
#   1. Ollama (macOS: Homebrew formula; Linux: prints the official install command)
#   2. Ollama server on 127.0.0.1:11434, then the answer model gemma4:e4b (9.6 GB, one time)
#   3. Pages on http://localhost:8741 (python3 -m http.server, repo root)
#   4. Ask server on http://localhost:8742 (python3 -m brain.ask --serve 8742)
#   5. Voice server on http://localhost:8744 when .venv-tts has kokoro (else prints the setup)
#   6. Doctor line, then opens http://localhost:8741/web/models.html#try
# Re-run any time; idempotent. Stop everything: bash scripts/install-local.sh --uninstall
# The model stays in Ollama after --uninstall (remove it with: ollama rm gemma4:e4b).
set -euo pipefail
export HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1

MODEL="gemma4:e4b"; PAGES=8741; ASK=8742; TTS=8744; OLLAMA_URL="http://127.0.0.1:11434"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$HOME/.base-fleet"; UNINSTALL=0; OPEN=1

usage(){
  cat <<'HELP'
Usage: bash scripts/install-local.sh [--no-open] [--uninstall] [--help]
Sets up the Base Fleet home AI on this PC: Ollama + gemma4:e4b, the ask server (8742),
the pages (8741) and, when Kokoro is set up, the voice server (8744).
  --no-open    Do not open the browser at the end
  --uninstall  Stop the servers this script started; keep Ollama and the model
  --help       Show this help without making changes
HELP
}
while [ $# -gt 0 ]; do case "$1" in
  --help|-h) usage; exit 0;;
  --uninstall) UNINSTALL=1;;
  --no-open) OPEN=0;;
  *) echo "unknown flag $1"; usage; exit 2;; esac; shift; done

ok(){ printf "\033[32m✓\033[0m %s\n" "$*"; }; step(){ printf "\n\033[1m── %s\033[0m\n" "$*"; }; warn(){ printf "\033[33m△\033[0m %s\n" "$*"; }
up(){ curl -sf -m 2 "$1" >/dev/null 2>&1; }
listening(){ curl -s -m 2 -o /dev/null "$1" 2>/dev/null; }   # any HTTP reply counts
# stop NAME: kill the process recorded in ~/.base-fleet/NAME.pid, if it is still ours.
stop(){
  local f="$RUN/$1.pid" pid
  [ -f "$f" ] || return 0
  pid="$(cat "$f")"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; ok "stopped $1 (pid $pid)"; fi
  rm -f "$f"
}
# start NAME URL CMD...: run CMD from the repo root in the background unless URL already answers.
start(){
  local name="$1" url="$2"; shift 2
  if listening "$url"; then ok "$name already running ($url)"; return 0; fi
  stop "$name"
  ( cd "$REPO" || exit 1; nohup "$@" >>"$RUN/logs/$name.log" 2>&1 </dev/null & echo $! >"$RUN/$name.pid" )
  for _ in $(seq 1 20); do listening "$url" && { ok "$name on $url"; return 0; }; sleep 0.5; done
  warn "$name did not answer on $url; see $RUN/logs/$name.log"; return 1
}

if [ "$UNINSTALL" -eq 1 ]; then
  step "Stop Base Fleet servers"
  for n in tts ask pages ollama; do stop "$n"; done
  ok "servers stopped. Ollama and $MODEL stay installed (ollama rm $MODEL to remove the model)."
  exit 0
fi

OS="$(uname)"
[ -f "$REPO/brain/ask.py" ] || { echo "Run this from a base-fleet checkout (brain/ask.py not found under $REPO)"; exit 2; }
command -v python3 >/dev/null || { echo "python3 is needed (macOS: xcode-select --install; Linux: your package manager)"; exit 2; }
command -v curl >/dev/null || { echo "curl is needed"; exit 2; }
mkdir -p "$RUN/logs"

if [ "$OS" = "Darwin" ]; then MEM=$(( $(sysctl -n hw.memsize) / 1073741824 ))
else MEM=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1048576 )); fi
step "Base Fleet local AI — $OS, ${MEM} GB memory, repo $REPO"
[ "$MEM" -ge 16 ] || warn "under 16 GB: $MODEL answers will be slow; the page's in-browser model still works"

step "1/5 Ollama"
if ! command -v ollama >/dev/null; then
  if [ "$OS" = "Darwin" ]; then
    if ! command -v brew >/dev/null; then
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; else eval "$(/usr/local/bin/brew shellenv)"; fi
    fi
    brew install -q ollama
  else
    echo "Install Ollama with its official script (it asks for sudo), then re-run this installer:"
    echo "  curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
  fi
fi
ok "ollama $(ollama --version 2>/dev/null | awk '{print $NF}')"

step "2/5 Model $MODEL"
if up "$OLLAMA_URL/api/tags"; then ok "ollama server already running ($OLLAMA_URL)"
else
  ( OLLAMA_HOST=127.0.0.1:11434 nohup ollama serve >>"$RUN/logs/ollama.log" 2>&1 </dev/null & echo $! >"$RUN/ollama.pid" )
  for _ in $(seq 1 30); do up "$OLLAMA_URL/api/tags" && break; sleep 0.5; done
  up "$OLLAMA_URL/api/tags" || { warn "ollama serve did not start; see $RUN/logs/ollama.log"; exit 1; }
  ok "ollama serve on $OLLAMA_URL"
fi
if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then ok "$MODEL already pulled"
else echo "Downloading $MODEL (9.6 GB, one time)"; ollama pull "$MODEL"; ok "$MODEL"; fi

step "3/5 Pages"
if listening "http://127.0.0.1:$PAGES/" && ! up "http://127.0.0.1:$PAGES/web/models.html"; then
  warn "port $PAGES serves another folder; for this checkout run: python3 -m http.server 8751 (from $REPO)"
else
  start pages "http://127.0.0.1:$PAGES/web/models.html" python3 -m http.server "$PAGES" --bind 127.0.0.1 || true
fi

step "4/5 Ask server"
start ask "http://127.0.0.1:$ASK/health" python3 -m brain.ask --serve "$ASK"

step "5/5 Voice server (optional)"
VPY="$REPO/.venv-tts/bin/python"
if listening "http://127.0.0.1:$TTS/"; then
  ok "voice already running (http://localhost:$TTS)"
elif [ -x "$VPY" ] && "$VPY" -c "import kokoro, soundfile" >/dev/null 2>&1 && command -v ffmpeg >/dev/null; then
  # Kokoro loads on the first POST /tts; any reply on / means the server is listening.
  start tts "http://127.0.0.1:$TTS/" "$VPY" -m brain.tts --serve "$TTS" || true
else
  ok "voice skipped; pages use the browser voice. To add Kokoro-82M (Python 3.12 + ffmpeg):"
  echo "   cd \"$REPO\" && uv venv -p 3.12 .venv-tts && uv pip install -p .venv-tts kokoro soundfile"
  echo "   .venv-tts/bin/python -m spacy download en_core_web_sm; brew install ffmpeg (Linux: apt install ffmpeg)"
  echo "   then re-run: bash scripts/install-local.sh"
fi

step "Doctor"
yes_no(){ up "$1" && echo up || echo down; }
HEALTH="$(curl -sf -m 3 "http://127.0.0.1:$ASK/health" || echo '{}')"
printf 'ollama=%s  model=%s  ask=%s (%s)  pages=%s  voice=%s\n' \
  "$(yes_no "$OLLAMA_URL/api/tags")" "$MODEL" "$(yes_no "http://127.0.0.1:$ASK/health")" \
  "$(printf '%s' "$HEALTH" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("model","?"))' 2>/dev/null || echo '?')" \
  "$(yes_no "http://127.0.0.1:$PAGES/web/models.html")" \
  "$(listening "http://127.0.0.1:$TTS/" && echo up || echo off)"

URL="http://localhost:$PAGES/web/models.html#try"
if [ "$OPEN" -eq 1 ]; then
  if [ "$OS" = "Darwin" ]; then open "$URL" 2>/dev/null || true; elif command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1 || true; fi
fi
cat <<MSG

Base Fleet local AI is running on this PC.
  Open:  $URL   (shows "Connected to your PC")
  Logs:  $RUN/logs/
  Stop:  bash scripts/install-local.sh --uninstall
Servers listen on 127.0.0.1 only. Re-run this script after a restart to start them again.
MSG
