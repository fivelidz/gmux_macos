#!/bin/bash
# gmux-v4 — dedicated launch script
#
# Starts: monitor (HTTP :8769) + voice daemon (ws:8770) + gmux-v4 Tauri app
# Always uses gmux_v4's own backend, never falls back to gmux-system.
#
# Usage:
#   ./scripts/launch-v4.sh             # full system (Tauri window)
#   ./scripts/launch-v4.sh --dev       # Tauri dev mode (hot reload, slower)
#   ./scripts/launch-v4.sh --browser   # browser UI only (no Tauri)
#   ./scripts/launch-v4.sh --kill      # stop all gmux-v4 processes
#   ./scripts/launch-v4.sh --test      # headless smoke test, no UI

set -e
V4_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$V4_DIR/backend"
APP_DIR="$V4_DIR/app"
BINARY="$APP_DIR/src-tauri/target/release/gmuxtest"

# ── Colours ───────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'; N='\033[0m'

# ── OS detection ──────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
IS_MAC=false; [ "$OS_TYPE" = "Darwin" ] && IS_MAC=true

port_in_use() { lsof -i :"$1" >/dev/null 2>&1; }

# ── Mode flags ────────────────────────────────────────────────────────────────
DEV_MODE=false; BROWSER_ONLY=false; KILL_MODE=false; TEST_MODE=false
for arg in "$@"; do
  case $arg in
    --dev)     DEV_MODE=true ;;
    --browser) BROWSER_ONLY=true ;;
    --kill)    KILL_MODE=true ;;
    --test)    TEST_MODE=true ;;
  esac
done

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${B}██████╗ ███╗   ███╗██╗   ██╗██╗  ██╗${N}  ${Y}v4${N}"
echo -e "  ${B}██╔════╝████╗ ████║██║   ██║╚██╗██╔╝${N}"
echo -e "  ${B}██║  ███╗██╔████╔██║██║   ██║ ╚███╔╝ ${N}"
echo -e "  ${B}██║   ██║██║╚██╔╝██║██║   ██║ ██╔██╗ ${N}"
echo -e "  ${B}╚██████╔╝██║ ╚═╝ ██║╚██████╔╝██╔╝ ██╗${N}"
echo -e "  ${B} ╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝${N}"
echo -e "  ${Y}gesture-aware AI terminal multiplexer${N}"
echo -e "  ${G}★ v4 — portable PTY, no tmux required${N}"
echo ""

# ── Kill mode ─────────────────────────────────────────────────────────────────
if $KILL_MODE; then
  echo "Stopping gmux-v4 processes..."
  pkill -f "gmux_v4/backend/status/monitor.py"   2>/dev/null && echo "  ✓ monitor stopped"    || true
  pkill -f "gmux_v4/backend/voice/gmux_voice"    2>/dev/null && echo "  ✓ voice stopped"      || true
  pkill -f "gmux_v4/backend/session/session_restore" 2>/dev/null && echo "  ✓ session-restore stopped" || true
  pkill -f "target/release/gmuxtest"             2>/dev/null && echo "  ✓ Tauri binary stopped" || true
  echo "Done."
  exit 0
fi

# ── Python interpreter ────────────────────────────────────────────────────────
PY=""
for candidate in python3.11 python3.12 python3.10 python3; do
  if command -v "$candidate" &>/dev/null; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
  echo -e "${R}ERROR: Python 3.10+ required but not found on PATH${N}"
  exit 1
fi

# ── Monitor ──────────────────────────────────────────────────────────────────
if pgrep -f "gmux_v4/backend/status/monitor.py" >/dev/null 2>&1; then
  echo -e "  ${G}✓${N} monitor    already running (gmux_v4)"
elif port_in_use 8769; then
  echo -e "  ${Y}~${N} monitor    :8769 bound by another process (ok for dev)"
else
  echo -e "  ↻ monitor    starting on :8769..."
  $PY "$BACKEND/status/monitor.py" &>/tmp/gmux-v4-monitor.log &
  MON_PID=$!
  # Wait up to 5s for it to bind
  for i in $(seq 1 10); do
    sleep 0.5
    if port_in_use 8769; then
      echo -e "  ${G}✓${N} monitor    :8769 up  (PID $MON_PID  log: /tmp/gmux-v4-monitor.log)"
      break
    fi
    if [ $i -eq 10 ]; then
      echo -e "  ${R}✗${N} monitor    failed to bind :8769 — check /tmp/gmux-v4-monitor.log"
    fi
  done
fi

# ── Voice daemon ─────────────────────────────────────────────────────────────
if port_in_use 8770; then
  echo -e "  ${G}✓${N} voice      ws://localhost:8770 already running"
else
  # Voice is optional — requires faster-whisper + sounddevice
  if $PY -c "import faster_whisper, sounddevice" 2>/dev/null; then
    echo "  ↻ voice      starting faster-whisper on ws://localhost:8770..."
    $PY "$BACKEND/voice/gmux_voice_daemon.py" \
      --model tiny --port 8770 --lang en \
      &>/tmp/gmux-v4-voice.log &
    echo -e "  ${G}✓${N} voice      starting (PID $!  log: /tmp/gmux-v4-voice.log)"
  else
    echo -e "  ${Y}-${N} voice      skipped (faster-whisper / sounddevice not installed)"
  fi
fi

echo ""

# ── Headless smoke test ───────────────────────────────────────────────────────
if $TEST_MODE; then
  echo -e "${B}═══ Headless smoke test ═══${N}"
  PASS=0; FAIL=0

  check() {
    local label="$1"; local result="$2"; local expected="$3"
    if echo "$result" | grep -q "$expected"; then
      echo -e "  ${G}✓${N} $label"
      PASS=$((PASS+1))
    else
      echo -e "  ${R}✗${N} $label  (got: ${result:0:80})"
      FAIL=$((FAIL+1))
    fi
  }

  # 1. Monitor health
  sleep 1
  check "monitor /health" "$(curl -s --max-time 3 http://localhost:8769/health 2>/dev/null)" "ok"

  # 2. Pane count > 0
  STATE=$(curl -s --max-time 3 http://localhost:8769/api/state 2>/dev/null)
  PANE_COUNT=$(echo "$STATE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d))" 2>/dev/null || echo 0)
  if [ "$PANE_COUNT" -gt 0 ] 2>/dev/null; then
    echo -e "  ${G}✓${N} pane state  ($PANE_COUNT panes)"
    PASS=$((PASS+1))
  else
    echo -e "  ${R}✗${N} pane state  (0 panes — monitor may not see tmux yet)"
    FAIL=$((FAIL+1))
  fi

  # 3. All 5 tmp files exist
  for f in pane-state services activity files memory; do
    check "/tmp/gmuxtest-$f.json" "$(ls /tmp/gmuxtest-$f.json 2>/dev/null && echo ok)" "ok"
  done

  # 4. Python tests
  echo ""
  echo -e "  ${B}Python test suites:${N}"
  for suite in test_monitor_producers test_sub_agents test_memory_aggregator; do
    OUT=$($PY "$BACKEND/status/$suite.py" 2>&1 | tail -2)
    if echo "$OUT" | grep -qE "Failed: 0|passed, 0 failed"; then
      PASSED=$(echo "$OUT" | grep -oE "[0-9]+ passed|Passed: [0-9]+" | grep -oE "[0-9]+" | head -1)
      echo -e "  ${G}✓${N} $suite  (${PASSED} passed)"
      PASS=$((PASS+1))
    else
      echo -e "  ${R}✗${N} $suite"
      echo "    $OUT"
      FAIL=$((FAIL+1))
    fi
  done

  # 5. PTY standalone smoke
  echo ""
  echo -e "  ${B}PTY core:${N}"
  PTY_OUT=$(cd "$V4_DIR/app/src-tauri" && cargo run --example pty_smoke 2>&1 | tail -3)
  check "pty_smoke" "$PTY_OUT" "ALL CHECKS PASSED"

  # 6. Memory aggregator end-to-end
  echo ""
  echo -e "  ${B}Memory aggregator:${N}"
  $PY "$BACKEND/status/memory_aggregator.py" 2>/dev/null
  MEM_TOTAL=$(python3 -c "import json; d=json.load(open('/tmp/gmuxtest-memory.json')); print(d['total_count'])" 2>/dev/null || echo -1)
  if [ "$MEM_TOTAL" -ge 0 ] 2>/dev/null; then
    echo -e "  ${G}✓${N} memory aggregator  ($MEM_TOTAL memories in /tmp/gmuxtest-memory.json)"
    PASS=$((PASS+1))
  else
    echo -e "  ${R}✗${N} memory aggregator  (could not read output)"
    FAIL=$((FAIL+1))
  fi

  # 7. Release binary exists and is executable
  echo ""
  echo -e "  ${B}Release binary:${N}"
  if [ -x "$BINARY" ]; then
    SIZE=$(du -h "$BINARY" | cut -f1)
    echo -e "  ${G}✓${N} binary  ($SIZE  $BINARY)"
    PASS=$((PASS+1))
  else
    echo -e "  ${Y}~${N} binary not built yet — run: cd $APP_DIR && npm run tauri build"
    # Not a failure — dev mode uses npm run tauri dev
  fi

  echo ""
  echo -e "${B}═══ Results: ${G}${PASS} passed${N}  ${R}${FAIL} failed${N}  ${B}═══${N}"
  echo ""
  [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

# ── Browser UI ────────────────────────────────────────────────────────────────
if $BROWSER_ONLY; then
  PORT=5550
  pkill -f "http.server $PORT" 2>/dev/null || true
  sleep 0.2
  python3 -m http.server $PORT --directory "$V4_DIR" &>/tmp/gmux-v4-http.log &
  HTTP_PID=$!
  sleep 1
  URL="http://localhost:$PORT/ui/v3/index.html"
  echo -e "  ${G}✓${N} browser UI  $URL"
  echo -e "  ${G}✓${N} dashboard   $URL  (open Ctrl+Alt+D inside)"
  echo -e "  ${G}✓${N} API state   http://localhost:8769/api/state"
  echo ""
  if $IS_MAC; then open "$URL" 2>/dev/null; else xdg-open "$URL" 2>/dev/null || true; fi
  echo "Ctrl+C to stop"
  wait $HTTP_PID
  exit 0
fi

# ── Tauri app ─────────────────────────────────────────────────────────────────
# Sync ui/v3/index.html → app/src/index.html if source is newer
if [ "$V4_DIR/ui/v3/index.html" -nt "$APP_DIR/src/index.html" ] 2>/dev/null; then
  echo "  ↻ sync       ui/v3/index.html → app/src/index.html"
  cp "$V4_DIR/ui/v3/index.html" "$APP_DIR/src/index.html"
fi

if ! $IS_MAC; then
  # Linux: WebKitGTK needs X11 backend and GStreamer suppression
  export GDK_BACKEND=x11
  export WEBKIT_DISABLE_COMPOSITING_MODE=1
  export GST_DEBUG="*:0"
  export GST_PLUGIN_FEATURE_RANK="v4l2src:NONE,v4l2sink:NONE,v4l2videoenc:NONE,v4l2videodec:NONE"
fi

# Always enable v4 PTY mode (this is gmux-v4, not gmux-system)
export GMUX_V4_PTY=1

cd "$APP_DIR"

if [ -x "$BINARY" ] && ! $DEV_MODE; then
  echo -e "  ${G}✓${N} Tauri       launching release binary (GMUX_V4_PTY=1)..."
  echo ""
  exec "$BINARY"
else
  echo -e "  ${Y}~${N} Tauri       launching dev mode (hot reload)..."
  if $DEV_MODE; then echo "               (--dev flag set)"; fi
  if [ ! -x "$BINARY" ]; then echo "               (release binary not built yet)"; fi
  echo ""
  exec npm run tauri dev
fi
