#!/bin/bash
# gmux-system — master launcher
# Starts: monitor (HTTP :8769) + voice daemon (ws:8770) + Tauri app
#
# Usage:
#   ./scripts/launch.sh           # full system
#   ./scripts/launch.sh --browser # browser UI only (no Tauri)
#   ./scripts/launch.sh --dev     # Tauri dev mode (hot reload)

set -e
SYSTEM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$SYSTEM_DIR/backend"
UI_DIR="$SYSTEM_DIR/ui"
APP_DIR="$SYSTEM_DIR/app"

# ── OS detection ──────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
IS_MAC=false
[ "$OS_TYPE" = "Darwin" ] && IS_MAC=true

# ── Cross-platform port check ─────────────────────────────────────────────────
# lsof is available on both Linux (lsof pkg) and macOS (built-in).
# ss is Linux-only; fall back to lsof on macOS.
port_in_use() {
  lsof -i :"$1" >/dev/null 2>&1
}

echo ""
echo "  ██████╗ ███╗   ███╗██╗   ██╗██╗  ██╗"
echo "  ██╔════╝████╗ ████║██║   ██║╚██╗██╔╝"
echo "  ██║  ███╗██╔████╔██║██║   ██║ ╚███╔╝ "
echo "  ██║   ██║██║╚██╔╝██║██║   ██║ ██╔██╗ "
echo "  ╚██████╔╝██║ ╚═╝ ██║╚██████╔╝██╔╝ ██╗"
echo "   ╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝"
echo ""
echo "  gesture-aware AI terminal multiplexer"
echo ""

BROWSER_ONLY=false
DEV_MODE=false
for arg in "$@"; do
  case $arg in
    --browser) BROWSER_ONLY=true ;;
    --dev)     DEV_MODE=true ;;
  esac
done

# ── Monitor ──────────────────────────────────────────────────────────────
if pgrep -f "gmux_v4/backend/status/monitor.py" >/dev/null 2>&1 || \
   pgrep -f "gmux-system/backend/status/monitor.py" >/dev/null 2>&1 || \
   pgrep -f "gmuxtest/src-py/status/monitor.py" >/dev/null 2>&1; then
  echo "  ✓ monitor    already running"
elif port_in_use 8769; then
  echo "  ✓ monitor    :8769 already bound"
else
  echo "  ↻ monitor    starting on :8769..."
  python3.11 "$BACKEND/status/monitor.py" &>/tmp/gmux-monitor.log &
  echo "              PID $!  log: /tmp/gmux-monitor.log"
fi

# ── Voice daemon ─────────────────────────────────────────────────────────
if port_in_use 8770; then
  echo "  ✓ voice      ws://localhost:8770 already running"
else
  MODEL_PATH="$SYSTEM_DIR/models/hand_landmarker.task"
  echo "  ↻ voice      starting faster-whisper on ws://localhost:8770..."
  python3.11 "$BACKEND/voice/gmux_voice_daemon.py" \
    --model tiny --port 8770 --lang en \
    &>/tmp/gmux-voice.log &
  echo "              PID $!  log: /tmp/gmux-voice.log"
fi

echo ""

if $BROWSER_ONLY; then
  # ── Browser UI ───────────────────────────────────────────────────────
  PORT=5550
  pkill -f "http.server $PORT" 2>/dev/null || true
  sleep 0.3
  python3 -m http.server $PORT --directory "$SYSTEM_DIR" &>/tmp/gmux-http.log &
  HTTP_PID=$!
  sleep 1
  URL="http://localhost:$PORT/ui/v3/index.html"
  echo "  ✓ UI         $URL"
  echo "  ✓ Demo       http://localhost:$PORT/ui/releases/gmux-v3.0-demo.html"
  echo "  ✓ API state  http://localhost:8769/api/state"
  echo ""
  echo "  Opening browser..."
  if $IS_MAC; then
    open "$URL" 2>/dev/null || echo "  Open manually: $URL"
  else
    xdg-open "$URL" 2>/dev/null || echo "  Open manually: $URL"
  fi
  echo ""
  echo "  Ctrl+C to stop"
  wait $HTTP_PID
else
  # ── Tauri app ─────────────────────────────────────────────────────────
  # Linux-only: WebKitGTK on KDE Wayland requires GDK_BACKEND=x11.
  # On macOS, Tauri uses native WebKit — these env vars are irrelevant and
  # would produce GTK warnings if set. Skipped on Darwin.
  if ! $IS_MAC; then
    export GDK_BACKEND=x11
    export WEBKIT_DISABLE_COMPOSITING_MODE=1
    # Suppress GStreamer media pipeline assertion crashes in WebKitWebProcess.
    # Without these, webkit2gtk probes v4l2/camera caps at startup and fires
    # repeated gst_value_collect_int_range assertions that jank or blank the UI.
    export GST_DEBUG="*:0"
    export GST_PLUGIN_FEATURE_RANK="v4l2src:NONE,v4l2sink:NONE,v4l2videoenc:NONE,v4l2videodec:NONE"
  fi
  # Sync UI source before launch — app/src/index.html must match ui/v3/index.html
  if [ "$SYSTEM_DIR/ui/v3/index.html" -nt "$APP_DIR/src/index.html" ]; then
    echo "  ↻ sync       ui/v3/index.html → app/src/index.html"
    cp "$SYSTEM_DIR/ui/v3/index.html" "$APP_DIR/src/index.html"
  fi
  # Sync dashboard (Agent Monitor window) if a newer copy exists in ui/v3/dashboard/.
  # Default source of truth is app/src/dashboard/ (checked in to repo). Override is optional.
  if [ -d "$SYSTEM_DIR/ui/v3/dashboard" ] && \
     [ "$SYSTEM_DIR/ui/v3/dashboard/index.html" -nt "$APP_DIR/src/dashboard/index.html" ]; then
    echo "  ↻ sync       ui/v3/dashboard/ → app/src/dashboard/"
    rm -rf "$APP_DIR/src/dashboard"
    cp -r "$SYSTEM_DIR/ui/v3/dashboard" "$APP_DIR/src/dashboard"
  fi
  if $IS_MAC; then
    echo "  ✓ Tauri      starting (native WebKit, macOS)..."
  else
    echo "  ✓ Tauri      starting (GDK_BACKEND=x11, GST suppressed)..."
  fi
  echo ""
  cd "$APP_DIR"
  if $DEV_MODE; then
    npm run tauri dev
  else
    npm run tauri dev   # TODO: switch to tauri build + run binary for production
  fi
fi
