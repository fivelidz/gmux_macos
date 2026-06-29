#!/usr/bin/env bash
# macos-keepalive.sh — keep a remote Mac reachable over Tailscale/SSH.
#
# The #1 reason a remote Mac "disappears" is SLEEP: lid closed or idle timeout
# drops WiFi + Tailscale, and SSH stops answering. This configures the Mac to
# stay reachable and verifies the persistence pieces.
#
# Usage (run ON the Mac, needs sudo):
#   bash scripts/macos-keepalive.sh            # apply keepalive + verify
#   bash scripts/macos-keepalive.sh --status   # just report current state
#   bash scripts/macos-keepalive.sh --revert    # restore default sleep behaviour
#
# What "apply" does:
#   • pmset: never sleep on AC, don't sleep on idle, keep network alive on sleep
#   • verifies Remote Login (sshd) is on and persistent
#   • verifies Tailscale is a login item (auto-reconnect after reboot)
#   • symlinks the tailscale CLI if missing

set -uo pipefail
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
ok(){ printf "  ${G}✓${N} %s\n" "$1"; }; warn(){ printf "  ${Y}!${N} %s\n" "$1"; }; err(){ printf "  ${R}✗${N} %s\n" "$1"; }

[ "$(uname -s)" = "Darwin" ] || { err "macOS only"; exit 1; }
MODE="${1:-apply}"

ts_cli() { command -v tailscale >/dev/null 2>&1 && echo tailscale \
  || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale; }

status() {
  echo "── Keepalive status ──"
  pmset -g | grep -E "sleep|disablesleep|womp|tcpkeepalive" | sed 's/^/  /'
  echo
  if sudo -n systemsetup -getremotelogin 2>/dev/null | grep -qi on; then ok "Remote Login (sshd): ON"; else warn "Remote Login: OFF or needs sudo"; fi
  if osascript -e 'tell application "System Events" to get the name of every login item' 2>/dev/null | grep -qi tailscale; then
    ok "Tailscale is a login item (auto-starts on boot)"; else warn "Tailscale NOT a login item — won't auto-reconnect after reboot"; fi
  "$(ts_cli)" status >/dev/null 2>&1 && ok "Tailscale CLI works ($("$(ts_cli)" ip -4 2>/dev/null | head -1))" || warn "Tailscale CLI not reachable"
}

case "$MODE" in
  --status) status; exit 0 ;;
  --revert)
    echo "Reverting to default sleep behaviour…"
    sudo pmset -a disablesleep 0 2>/dev/null || true
    sudo pmset -c sleep 10 2>/dev/null || true
    ok "Reverted (display may sleep, system may sleep on idle)"; exit 0 ;;
esac

echo "Applying keepalive (needs sudo)…"
# -c = on charger/AC. Keep the machine and its network up.
sudo pmset -c sleep 0 2>/dev/null        && ok "AC: system sleep disabled"   || warn "could not set sleep 0"
sudo pmset -a disablesleep 1 2>/dev/null && ok "sleep fully disabled (incl. lid-close on AC)" || warn "could not disablesleep"
sudo pmset -a womp 1 2>/dev/null         && ok "wake-on-network enabled"      || true
sudo pmset -a tcpkeepalive 1 2>/dev/null && ok "TCP keepalive on during sleep" || true
sudo pmset -a powernap 1 2>/dev/null     || true

# Tailscale CLI symlink (standalone app hides it in the bundle)
if ! command -v tailscale >/dev/null 2>&1 && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]; then
  sudo ln -sf /Applications/Tailscale.app/Contents/MacOS/Tailscale /usr/local/bin/tailscale && ok "linked tailscale CLI"
fi

# Tailscale login item (auto-reconnect after reboot)
if ! osascript -e 'tell application "System Events" to get the name of every login item' 2>/dev/null | grep -qi tailscale; then
  osascript -e 'tell application "System Events" to make login item at end with properties {path:"/Applications/Tailscale.app", hidden:true}' >/dev/null 2>&1 \
    && ok "added Tailscale as a login item" || warn "could not add login item"
fi

echo; status
echo
echo "  Note: lid-closed-on-battery may still sleep (Apple safety). For a truly"
echo "  always-on remote Mac, keep it plugged into AC power."
