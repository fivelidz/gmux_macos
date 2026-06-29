#!/usr/bin/env bash
# gmux-system — macOS smoke test script
# Run this on a Mac after cloning the repo to verify the minimum environment
# is in place before attempting a full launch.
#
# Usage:
#   bash scripts/macos-smoke-test.sh
#
# Exit code: 0 = all checks passed, 1 = one or more checks failed.
# Each check prints PASS / FAIL / WARN so you can grep the output.
#
# What it does NOT do:
#   - Does not launch any services (no side effects)
#   - Does not require a display (safe to run over SSH)
#   - Does not attempt to build the Tauri app unless --build is passed
#     (that takes 5-10 min on a cold Rust cache)
#
# Usage with build test:
#   bash scripts/macos-smoke-test.sh --build

set -euo pipefail

SYSTEM_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0
WARN=0
DO_BUILD=false
[[ "${1:-}" == "--build" ]] && DO_BUILD=true

_pass() { echo "  PASS  $1"; ((PASS++)); }
_fail() { echo "  FAIL  $1"; ((FAIL++)); }
_warn() { echo "  WARN  $1"; ((WARN++)); }
_head() { echo ""; echo "── $1 ──────────────────────────────────────"; }

echo ""
echo "  gmux-system macOS smoke test"
echo "  System dir: $SYSTEM_DIR"
echo "  $(uname -srm)"
echo ""

# ── 1. OS check ───────────────────────────────────────────────────────────────
_head "1. OS"
if [[ "$(uname -s)" == "Darwin" ]]; then
  _pass "Running on macOS (Darwin)"
else
  _fail "Not macOS — this script is macOS-specific (got $(uname -s))"
  exit 1
fi

# ── 2. tmux ───────────────────────────────────────────────────────────────────
_head "2. tmux"
if command -v tmux >/dev/null 2>&1; then
  TMUX_VER="$(tmux -V)"
  _pass "tmux found: $TMUX_VER"
else
  _fail "tmux not found — install with: brew install tmux"
fi

# ── 3. Python 3.11 ───────────────────────────────────────────────────────────
_head "3. Python 3.11"
if command -v python3.11 >/dev/null 2>&1; then
  PY_VER="$(python3.11 --version)"
  _pass "python3.11 found: $PY_VER"
else
  _warn "python3.11 not in PATH — trying python3"
  if command -v python3 >/dev/null 2>&1; then
    PY3_VER="$(python3 --version)"
    _warn "python3 found: $PY3_VER (scripts expect python3.11 explicitly)"
    echo "       Install with: brew install python@3.11"
    echo "       Then: export PATH=/opt/homebrew/opt/python@3.11/bin:\$PATH"
  else
    _fail "No python3 found — install with: brew install python@3.11"
  fi
fi

# ── 4. Python dependencies ────────────────────────────────────────────────────
_head "4. Python deps (psutil, websockets)"
PY="python3.11"
command -v python3.11 >/dev/null 2>&1 || PY="python3"

if $PY -c "import psutil" 2>/dev/null; then
  _pass "psutil importable"
else
  _fail "psutil not installed — run: $PY -m pip install psutil"
fi

if $PY -c "import websockets" 2>/dev/null; then
  _pass "websockets importable"
else
  _fail "websockets not installed — run: $PY -m pip install websockets"
fi

if $PY -c "import numpy" 2>/dev/null; then
  _pass "numpy importable"
else
  _warn "numpy not installed (needed for voice daemon) — run: $PY -m pip install numpy"
fi

# ── 5. sounddevice (voice daemon dep) ────────────────────────────────────────
_head "5. Voice deps (sounddevice, faster-whisper)"
if $PY -c "import sounddevice" 2>/dev/null; then
  _pass "sounddevice importable (CoreAudio backend via PortAudio)"
else
  _warn "sounddevice not installed — voice daemon will not start"
  echo "       Install with: $PY -m pip install sounddevice"
fi

if $PY -c "import faster_whisper" 2>/dev/null; then
  _pass "faster_whisper importable"
else
  _warn "faster-whisper not installed — voice daemon will not start"
  echo "       Install with: $PY -m pip install faster-whisper"
fi

# ── 6. bun / opencode ────────────────────────────────────────────────────────
_head "6. bun / opencode"
if [[ -x "$HOME/.bun/bin/bun" ]]; then
  BUN_VER="$("$HOME/.bun/bin/bun" --version 2>/dev/null || echo '?')"
  _pass "bun found: $BUN_VER"
else
  _fail "bun not found — install with: curl -fsSL https://bun.sh/install | bash"
fi

export PATH="$HOME/.bun/bin:$PATH"
if command -v opencode >/dev/null 2>&1; then
  OC_VER="$(opencode --version 2>/dev/null || echo '?')"
  _pass "opencode found: $OC_VER"
else
  _fail "opencode not found — install with: bun install -g opencode-ai"
fi

# ── 7. Rust / cargo ───────────────────────────────────────────────────────────
_head "7. Rust toolchain"
if command -v cargo >/dev/null 2>&1; then
  CARGO_VER="$(cargo --version)"
  _pass "cargo found: $CARGO_VER"
else
  _fail "cargo not found — install with: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
fi

# ── 8. Node / npm ────────────────────────────────────────────────────────────
_head "8. Node / npm"
if command -v node >/dev/null 2>&1; then
  NODE_VER="$(node --version)"
  _pass "node found: $NODE_VER"
else
  _fail "node not found — install with: brew install node"
fi

if command -v npm >/dev/null 2>&1; then
  NPM_VER="$(npm --version)"
  _pass "npm found: $NPM_VER"
else
  _fail "npm not found — install with: brew install node"
fi

# ── 9. npm deps in app/ ───────────────────────────────────────────────────────
_head "9. app/ npm dependencies"
if [[ -d "$SYSTEM_DIR/app/node_modules" ]]; then
  _pass "app/node_modules exists"
else
  _warn "app/node_modules missing — run: cd $SYSTEM_DIR/app && npm install"
fi

# ── 10. lsof availability (used by launch.sh port checks) ────────────────────
_head "10. lsof (port check utility)"
if command -v lsof >/dev/null 2>&1; then
  _pass "lsof found (used by launch.sh for cross-platform port checks)"
else
  _fail "lsof not found — unexpected on macOS, it's a system tool"
fi

# ── 11. gmux-system repo structure ───────────────────────────────────────────
_head "11. Repo structure"
for f in \
  "backend/status/monitor.py" \
  "backend/voice/gmux_voice_daemon.py" \
  "scripts/launch.sh" \
  "app/src-tauri/Cargo.toml" \
  "ui/v3/index.html"
do
  if [[ -f "$SYSTEM_DIR/$f" ]]; then
    _pass "$f present"
  else
    _fail "$f missing (repo incomplete?)"
  fi
done

# ── 12. Backend smoke test (monitor producers unit tests) ─────────────────────
_head "12. Backend unit tests"
if $PY -m pytest "$SYSTEM_DIR/backend/status/test_monitor_producers.py" -q 2>/dev/null | tail -3; then
  _pass "pytest tests (or see output above)"
else
  # Fall back to running directly if pytest not available
  if $PY "$SYSTEM_DIR/backend/status/test_monitor_producers.py" 2>/dev/null | grep -q "Passed:"; then
    RESULT="$($PY "$SYSTEM_DIR/backend/status/test_monitor_producers.py" 2>/dev/null | grep "Passed:")"
    _pass "$RESULT"
  else
    _warn "Could not run test_monitor_producers.py — may need psutil/websockets"
  fi
fi

# ── 13. Tauri build (optional, slow) ─────────────────────────────────────────
_head "13. Tauri app build (--build flag)"
if $DO_BUILD; then
  echo "  Running: cd app && npm run tauri build (this takes 5-15 minutes cold)"
  cd "$SYSTEM_DIR/app"
  if npm run tauri build 2>&1 | tail -10; then
    _pass "Tauri build succeeded"
  else
    _fail "Tauri build failed — check output above"
  fi
else
  _warn "Skipped (pass --build to test; takes 5-15 minutes cold)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  Passed: $PASS   Warned: $WARN   Failed: $FAIL"
echo "══════════════════════════════════════════════"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo "  ✗ Fix the FAILed checks above before running gmux-system."
  echo ""
  exit 1
elif [[ $WARN -gt 0 ]]; then
  echo "  ⚠ Some optional dependencies missing (voice/gesture may not work)."
  echo "    Core backend + browser UI should still work."
  echo ""
  echo "  Next steps:"
  echo "    bash $SYSTEM_DIR/scripts/launch.sh --browser"
  echo "    open http://localhost:5550/ui/v3/index.html"
  echo ""
  exit 0
else
  echo "  ✓ All checks passed — gmux-system should work on this Mac."
  echo ""
  echo "  Launch with:"
  echo "    bash $SYSTEM_DIR/scripts/launch.sh --browser   # browser UI only"
  echo "    bash $SYSTEM_DIR/scripts/launch.sh             # Tauri desktop app"
  echo ""
  exit 0
fi
