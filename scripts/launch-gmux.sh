#!/bin/bash
# gmux Tauri app launcher
# Starts the gmuxtest-specific monitor and voice daemon before Tauri.
# WebKitGTK on KDE Wayland requires GDK_BACKEND=x11 to create a managed window.

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ── OS detection ──────────────────────────────────────────────────────────────
_OS="$(uname -s)"
_IS_MAC=false
[ "$_OS" = "Darwin" ] && _IS_MAC=true
# Cross-platform port check (lsof is available on both Linux and macOS)
_port_in_use() { lsof -i :"$1" >/dev/null 2>&1; }

echo "[gmux] Starting services..."

# ── Monitor ──────────────────────────────────────────────────────────────
# Use precise pgrep so we don't match the production gmux monitor
# (which runs from ~/projects/gmux/src/status/monitor.py)
if pgrep -f "gmuxtest/src-py/status/monitor.py" >/dev/null 2>&1; then
  echo "[gmux] monitor: already running"
else
  echo "[gmux] monitor: starting gmuxtest monitor on :8769..."
  python3.11 src-py/status/monitor.py &>/tmp/gmux-monitor.log &
  echo "[gmux] monitor PID: $!"
fi

# ── Voice daemon (faster-whisper) ────────────────────────────────────────
if _port_in_use 8770; then
  echo "[gmux] voice: already running on :8770"
else
  echo "[gmux] voice: starting faster-whisper daemon on ws://:8770..."
  python3.11 src-py/voice/gmux_voice_daemon.py \
    --model tiny --port 8770 --lang en \
    &>/tmp/gmux-voice.log &
  echo "[gmux] voice PID: $!"
fi

echo ""
echo "[gmux] Services:"
echo "  Monitor HTTP:   http://127.0.0.1:8769/api/state"
echo "  Voice daemon:   ws://127.0.0.1:8770"
echo "  UI (browser):   http://localhost:5550/v2/index.html"
echo ""

# ── WebKitGTK / Wayland fix (Linux-only) ─────────────────────────────────
# Without GDK_BACKEND=x11, the Tauri window opens on Wayland but KWin
# doesn't manage it — it stays invisible or behind other windows.
# On macOS, Tauri uses native WebKit (WKWebView) — these env vars don't apply.
if ! $_IS_MAC; then
  export GDK_BACKEND=x11
  export WEBKIT_DISABLE_COMPOSITING_MODE=1
fi

echo "[gmux] Tauri dev (GDK_BACKEND=x11)..."
npm run tauri dev
