#!/usr/bin/env bash
# gmux-system — one-shot VM install
# Runs on the TARGET VM (not the host) — installs everything needed
# for the backend + browser UI in a single command.
#
# Usage (on the VM):
#   curl -fsSL https://raw.githubusercontent.com/fivelidz/gmux-system/main/scripts/install-vm.sh | bash
#
# Or, after rsync from host:
#   ssh sandbox 'bash ~/projects/gmux-system/scripts/install-vm.sh'
#
# This script is idempotent — safe to run multiple times.

set -euo pipefail

echo ""
echo "  gmux-system VM install — backend + browser UI"
echo ""

REPO_DIR="${GMUX_REPO_DIR:-$HOME/projects/gmux-system}"
NEED_RUN=true   # whether to launch monitor after install

# ── OS detection ──────────────────────────────────────────────────────────────
_OS="$(uname -s)"
_IS_MAC=false
[ "$_OS" = "Darwin" ] && _IS_MAC=true

# ── Detect package manager ──────────────────────────────────────────
if command -v pacman >/dev/null 2>&1; then
  PM=pacman
elif command -v apt-get >/dev/null 2>&1; then
  PM=apt
elif command -v dnf >/dev/null 2>&1; then
  PM=dnf
elif command -v brew >/dev/null 2>&1; then
  PM=brew
else
  echo "  ✗ unsupported package manager — install python3 + tmux manually"
  exit 1
fi
echo "  ✓ package manager:    $PM"

# ── 1. System packages (idempotent — skips already-installed) ───────
# v4 — tmux is no longer mandatory. The Tauri app owns its PTYs directly.
# We install tmux when available so legacy single-PTY mode + headless
# monitor.py still work, but failure to install tmux is non-fatal.
echo "  ↻ installing system packages"
case "$PM" in
  pacman)
    # tmux first (best-effort), then mandatory deps
    sudo pacman -Sy --noconfirm --needed tmux 2>&1 | grep -v 'is up to date' || true
    sudo pacman -Sy --noconfirm --needed \
      git python python-pip curl rsync openssh \
      2>&1 | grep -v 'is up to date' || true
    ;;
  apt)
    sudo apt-get update -qq
    sudo apt-get install -y -qq tmux 2>&1 | tail -1 || true
    sudo apt-get install -y -qq \
      git python3.11 python3-pip curl rsync openssh-client \
      2>&1 | tail -3
    ;;
  dnf)
    sudo dnf install -y -q tmux 2>&1 | tail -1 || true
    sudo dnf install -y -q \
      git python3.11 python3-pip curl rsync openssh-clients
    ;;
  brew)
    # macOS via Homebrew.
    # Note: webkit2gtk is NOT needed on macOS — Tauri uses the system WebKit
    # (WKWebView) which is built into macOS. tmux is best-effort (v4 doesn't
    # depend on it but legacy headless mode + monitor.py do).
    brew install --quiet tmux 2>&1 | tail -1 || true
    brew install --quiet python@3.11 curl rsync openssh 2>&1 | tail -3 || true
    ;;
esac

# ── 2. Python deps (mandatory subset only — voice/gesture deferred) ─
echo "  ↻ installing python deps"
PIP="python3 -m pip"
if ! $PIP install --user --quiet psutil websockets requests 2>&1 | tail -1; then
  # On newer pip, PEP-668 forces --break-system-packages
  $PIP install --user --break-system-packages --quiet psutil websockets requests
fi
echo "  ✓ python deps installed"

# ── 3. Bun + opencode (if missing) ──────────────────────────────────
if [ ! -x "$HOME/.bun/bin/bun" ]; then
  echo "  ↻ installing bun"
  curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1
fi
export PATH="$HOME/.bun/bin:$PATH"

if [ ! -x "$HOME/.bun/bin/opencode" ]; then
  echo "  ↻ installing opencode-ai (note: package is opencode-ai, binary is opencode)"
  bun install -g opencode-ai 2>&1 | tail -3
fi
echo "  ✓ opencode $(opencode --version 2>/dev/null || echo '?')"

# ── 4. Fetch or update the repo (if not already rsync'd) ────────────
if [ ! -d "$REPO_DIR" ]; then
  echo "  ↻ cloning gmux-system to $REPO_DIR"
  mkdir -p "$(dirname "$REPO_DIR")"
  git clone --depth 1 https://github.com/fivelidz/gmux-system.git "$REPO_DIR"
elif [ -d "$REPO_DIR/.git" ]; then
  echo "  ↻ pulling latest in $REPO_DIR"
  git -C "$REPO_DIR" pull --ff-only 2>&1 | tail -2
fi

# ── 5. tmux session (legacy only — v4 PTY path doesn't need it) ─────
# In v4 the Tauri app owns each agent's PTY directly via portable-pty,
# so a global tmux session is no longer required. We still create one
# here for compatibility with the v3 single-PTY path and headless
# monitor.py mode. If tmux is missing entirely, skip silently — v4
# users on macOS / Windows often won't have it.
if command -v tmux >/dev/null 2>&1; then
  if ! tmux has-session -t gmux 2>/dev/null; then
    echo "  ↻ creating tmux session 'gmux' (legacy compat)"
    tmux new-session -d -s gmux -n shell
  fi
  echo "  ✓ tmux gmux session ready"
else
  echo "  - tmux not installed (optional in v4; PTYs run inside the Tauri app)"
fi

# ── 6. Kill any stale monitor + start fresh ─────────────────────────
pkill -f "$REPO_DIR/backend/status/monitor.py" 2>/dev/null || true
sleep 1
if [ "$NEED_RUN" = true ]; then
  echo "  ↻ starting monitor.py (detached so it survives SSH disconnect)"
  cd "$REPO_DIR"
  if $_IS_MAC; then
    # macOS: setsid is not available (it's a Linux util-linux tool).
    # Use nohup + subshell redirect instead — equivalent for our purposes.
    nohup python3 backend/status/monitor.py </dev/null >/tmp/gmux-monitor.log 2>&1 &
    disown
  else
    setsid python3 backend/status/monitor.py </dev/null >/tmp/gmux-monitor.log 2>&1 &
    disown
  fi
  sleep 3
fi

# ── Port check helper (cross-platform: lsof works on Linux + macOS) ─
_port_in_use() { lsof -i :"$1" >/dev/null 2>&1; }

# ── IP address helper (cross-platform) ──────────────────────────────
if command -v ip >/dev/null 2>&1; then
  # Linux: use `ip addr`
  _get_local_ip() {
    ip -4 addr show 2>/dev/null | grep -v '127.0.0.1' | grep -oE 'inet [0-9.]+' | head -1 | awk '{print $2}'
  }
else
  # macOS: use `ifconfig`
  _get_local_ip() {
    ifconfig 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | head -1
  }
fi

# ── 7. Start UI HTTP server (bound to all interfaces) ───────────────
if ! _port_in_use 5550; then
  echo "  ↻ starting UI HTTP server on :5550 (all interfaces)"
  cd "$REPO_DIR"
  if $_IS_MAC; then
    nohup python3 -m http.server 5550 --bind 0.0.0.0 \
      </dev/null >/tmp/gmux-ui.log 2>&1 &
  else
    setsid python3 -m http.server 5550 --bind 0.0.0.0 \
      </dev/null >/tmp/gmux-ui.log 2>&1 &
  fi
  disown
  sleep 1
fi

# ── 8. Sanity check ─────────────────────────────────────────────────
echo ""
echo "  ── sanity check ──"
echo -n "  health:    " && curl -s --max-time 2 http://127.0.0.1:8769/health || echo "FAIL"
echo ""
echo -n "  producers: " && ls /tmp/gmuxtest-*.json 2>/dev/null | wc -l && echo " files"
echo -n "  ui port:   " && (_port_in_use 5550 && echo ":5550 bound" || echo "not bound")
echo -n "  api port:  " && (_port_in_use 8769 && echo ":8769 bound" || echo "not bound")
echo ""

# ── 9. URLs ─────────────────────────────────────────────────────────
IP="$(_get_local_ip)"
[ -z "$IP" ] && IP="<this-vm-ip>"
echo "  ── access ──"
echo "  Browser UI:  http://$IP:5550/ui/v3/index.html"
echo "  API state:   http://$IP:8769/api/state"
echo "  Health:      http://$IP:8769/health"
echo ""
echo "  Auth one provider before launching agents:"
echo "    opencode auth login anthropic"
echo ""
echo "  Done."
