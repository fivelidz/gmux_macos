#!/usr/bin/env bash
# gmux — macOS bootstrap. ONE script to take a fresh Mac to a working setup.
#
# Distils everything learned installing gmux on real Mac hardware (see
# docs/VM_REPORTS/macos-install-log.md). It is SAFE and IDEMPOTENT — re-running
# only does the missing pieces. It never deletes anything and never needs a
# broken Homebrew.
#
# Usage:
#   bash scripts/macos-bootstrap.sh             # survey + Phase 1 (backend + browser)
#   bash scripts/macos-bootstrap.sh --terminal  # also set up tmux + gmux CLI + qalcode wiring
#   bash scripts/macos-bootstrap.sh --check      # survey only, install nothing
#   bash scripts/macos-bootstrap.sh --app        # also build the Tauri .app (slow)
#
# What it does, in order:
#   1. Survey the toolchain (python, node, rust, psutil, tmux, git…).
#   2. Install only the GAPS — preferring brew, but with brew-free fallbacks
#      (rustup for cargo, `cargo install` for ripgrep, python3 for python@3.11).
#   3. Fix the committed-Linux-lockfile trap before any npm build.
#   4. Launch Phase 1 (monitor :8769 + browser UI) and verify endpoints.
#   5. (--terminal) wire up the `gmux` CLI + tmux multiplexer mode.
#   6. (--app) build the Tauri desktop app.

set -uo pipefail

REPO_DIR="$(cd "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")/.." && pwd)"
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'; N='\033[0m'
ok()   { printf "  ${G}✓${N} %s\n" "$1"; }
warn() { printf "  ${Y}!${N} %s\n" "$1"; }
err()  { printf "  ${R}✗${N} %s\n" "$1"; }
step() { printf "\n${B}== %s ==${N}\n" "$1"; }

MODE_CHECK=false; MODE_TERMINAL=false; MODE_APP=false
for a in "$@"; do case "$a" in
  --check) MODE_CHECK=true ;;
  --terminal) MODE_TERMINAL=true ;;
  --app) MODE_APP=true ;;
esac; done

[ "$(uname -s)" = "Darwin" ] || { err "This script is for macOS (Darwin). Use launch-v4.sh on Linux."; exit 1; }

# ── helpers ──────────────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }

# Pick the best python3. The monitor is stdlib + psutil only, so we PREFER an
# interpreter that already has psutil importable (avoids the macOS PEP-668
# "externally-managed" pip wall on the system python). Falls back to any python3.
pick_python() {
  local c
  # First pass: an interpreter that already has psutil
  for c in python3.11 python3.12 python3.13 python3.14 python3.10 python3; do
    if have "$c" && "$c" -c "import psutil" >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  # Second pass: any python3 (psutil may be installable, or metrics show 0)
  for c in python3.11 python3.12 python3.13 python3.14 python3.10 python3; do
    if have "$c"; then echo "$c"; return 0; fi
  done
  return 1
}

# Ensure a dir is on PATH inside this script's session
add_path() { case ":$PATH:" in *":$1:"*) ;; *) export PATH="$1:$PATH";; esac; }
add_path "$HOME/.cargo/bin"
add_path "$HOME/.bun/bin"
add_path "$HOME/.local/bin"
add_path "/usr/local/bin"

# ── 1. SURVEY ─────────────────────────────────────────────────────────────────
step "Survey"
ARCH="$(uname -m)"; ok "arch: $ARCH ($([ "$ARCH" = arm64 ] && echo 'Apple Silicon' || echo 'Intel'))"
ok "macOS: $(sw_vers -productVersion 2>/dev/null)"

PY="$(pick_python || true)"
[ -n "$PY" ] && ok "python: $PY ($($PY --version 2>&1))" || err "no python3 found"

if [ -n "$PY" ] && $PY -c "import psutil" 2>/dev/null; then
  ok "psutil: present ($($PY -c 'import psutil;print(psutil.__version__)'))"
  HAVE_PSUTIL=true
else
  warn "psutil: MISSING (RAM/CPU metrics will show 0 until installed)"; HAVE_PSUTIL=false
fi

have node  && ok "node: $(node --version)"   || warn "node: missing (only needed for the Tauri app)"
have npm   && ok "npm: $(npm --version)"      || warn "npm: missing (only needed for the Tauri app)"
have cargo && ok "cargo: $(cargo --version)"  || warn "cargo: missing (only needed for the Tauri app)"
have git   && ok "git: $(git --version)"      || err  "git: missing (required)"
have tmux  && ok "tmux: $(tmux -V)"           || warn "tmux: missing (needed for terminal-multiplexer mode)"
have rg    && ok "ripgrep: $(rg --version | head -1)" || warn "ripgrep: missing (qalcode search needs it)"
have bun   && ok "bun: $(bun --version)"      || warn "bun: missing (only needed for qalcode)"
if have brew; then
  if brew --version >/dev/null 2>&1; then ok "brew: $(brew --version | head -1)"
  else warn "brew: present but BROKEN — see docs/VM_REPORTS/FOR_ASHLEYS_CLAUDE.md (likely APFS corruption; this script does NOT need brew)"; fi
else warn "brew: not installed (this script works without it)"; fi

$MODE_CHECK && { step "Check-only mode — done."; exit 0; }

# ── 2. INSTALL GAPS (brew-free where possible) ─────────────────────────────────
step "Filling gaps"

# psutil — install with pip into the chosen python's user site.
# macOS Homebrew pythons are PEP-668 "externally managed"; --user is blocked.
# Try --user first, then --break-system-packages (safe for a leaf dep like psutil).
if ! $HAVE_PSUTIL && [ -n "$PY" ]; then
  warn "installing psutil via $PY -m pip"
  if $PY -m pip install --user psutil >/tmp/gmux-pip.log 2>&1; then ok "psutil installed (--user)"
  elif $PY -m pip install --user --break-system-packages psutil >>/tmp/gmux-pip.log 2>&1; then ok "psutil installed (--break-system-packages)"
  else warn "psutil install failed (see /tmp/gmux-pip.log) — metrics will show 0. Tip: brew install python@3.11 and re-run."; fi
fi

# ripgrep — prefer brew, else cargo install (brew-free)
if ! have rg; then
  if have brew && brew --version >/dev/null 2>&1; then
    brew install ripgrep && ok "ripgrep via brew"
  elif have cargo; then
    warn "ripgrep missing & brew unavailable — building via cargo (a few min)…"
    cargo install ripgrep >/tmp/gmux-rg.log 2>&1 && ok "ripgrep via cargo (~/.cargo/bin/rg)" \
      || warn "cargo install ripgrep failed (see /tmp/gmux-rg.log)"
  else
    warn "ripgrep missing and no brew/cargo to install it"
  fi
fi

# ── 3. (only if building the app) fix the platform-lockfile trap ───────────────
fix_npm_platform_lock() {
  local app="$REPO_DIR/app"
  [ -d "$app" ] || return 0
  cd "$app" || return 0
  # If node_modules exists but the platform binary is missing, the committed
  # Linux lockfile poisoned the install. Reinstall clean on this OS.
  if [ -d node_modules ] && [ ! -d "node_modules/@rolldown/binding-darwin-$( [ "$ARCH" = arm64 ] && echo arm64 || echo x64)" ] \
     && [ ! -d "node_modules/@rolldown/binding-darwin-x64" ] && [ ! -d "node_modules/@rolldown/binding-darwin-arm64" ]; then
    warn "node_modules looks cross-platform — reinstalling clean for macOS"
    [ -f package-lock.json ] && cp package-lock.json /tmp/package-lock.foreign.json
    rm -rf node_modules package-lock.json
  fi
  # Fix a possible root-owned npm cache from an earlier sudo npm
  if [ -d "$HOME/.npm" ] && [ "$(stat -f '%Su' "$HOME/.npm" 2>/dev/null)" != "$(whoami)" ]; then
    warn "fixing ~/.npm ownership"; sudo chown -R "$(whoami):staff" "$HOME/.npm" 2>/dev/null || true
  fi
  cd "$REPO_DIR"
}

# ── 4. PHASE 1 — backend + browser UI ──────────────────────────────────────────
step "Phase 1 — backend + browser UI"
cd "$REPO_DIR"
chmod +x scripts/*.sh 2>/dev/null || true
if [ -x scripts/launch-v4.sh ]; then
  ./scripts/launch-v4.sh --browser || warn "launch-v4.sh returned non-zero (often fine if a server was already up)"
else
  err "scripts/launch-v4.sh not found"
fi
sleep 3
if curl -s --max-time 4 http://localhost:8769/health 2>/dev/null | grep -q ok; then
  ok "monitor healthy on :8769"
  printf "      state:    "; curl -s --max-time 3 http://localhost:8769/api/state | head -c 120; echo
else
  warn "monitor not answering on :8769 yet — check /tmp/gmux-v4-*.log"
fi

# ── 5. TERMINAL MODE — tmux + gmux CLI ─────────────────────────────────────────
if $MODE_TERMINAL; then
  step "Terminal-multiplexer mode"
  if ! have tmux; then
    if have brew && brew --version >/dev/null 2>&1; then brew install tmux && ok "tmux via brew"
    else warn "tmux missing and brew unavailable — install tmux to use 'gmux attach'. (No pure brew-free build provided; tmux from source is heavy.)"; fi
  fi
  # Symlink the gmux CLI so `gmux` works from anywhere
  mkdir -p "$HOME/.local/bin"
  ln -sf "$REPO_DIR/scripts/gmux" "$HOME/.local/bin/gmux"
  ok "gmux CLI linked → ~/.local/bin/gmux  (try: gmux status / gmux attach / gmux --backend-only)"
  if ! grep -q '.local/bin' "$HOME/.zshrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"; ok "added ~/.local/bin to ~/.zshrc PATH"
  fi
fi

# ── 6. APP — Tauri build ───────────────────────────────────────────────────────
if $MODE_APP; then
  step "Phase 2 — Tauri desktop app (slow)"
  if ! have node || ! have cargo; then
    err "node and cargo are required for the app. Install node (brew or nodejs.org) and rustup (https://rustup.rs)."
  else
    fix_npm_platform_lock
    cd "$REPO_DIR/app"
    npm install || warn "npm install had warnings"
    npm run tauri build && ok "app built → app/src-tauri/target/release/bundle/macos/*.app" \
      || err "tauri build failed — see output above"
    cd "$REPO_DIR"
  fi
fi

step "Done"
echo "  Next:"
echo "    • Browser UI:  http://localhost:5550/ui/v3/index.html"
echo "    • qalcode:     run 'qalcode' in a project folder (first run = Claude login)"
$MODE_TERMINAL && echo "    • Multiplexer: gmux attach   (enter tmux session) · gmux status (see panes)"
echo "    • Full notes:  docs/VM_REPORTS/macos-install-log.md"
