#!/usr/bin/env bash
# macos-perf-cleanup.sh — free RAM and reduce load on a low-memory Mac.
#
# Built for an 8 GB / dual-core 2015 MacBook Pro that swaps heavily. Safe and
# reversible. It kills only STALE dev leftovers (old tauri/vite/duplicate http
# servers), purges inactive memory, and reports the big consumers so you know
# what to close.
#
# Usage:
#   bash scripts/macos-perf-cleanup.sh            # clean + report
#   bash scripts/macos-perf-cleanup.sh --report   # report only, kill nothing
#   bash scripts/macos-perf-cleanup.sh --aggressive  # also offer to quit Chrome

set -uo pipefail
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
ok(){ printf "  ${G}✓${N} %s\n" "$1"; }; warn(){ printf "  ${Y}!${N} %s\n" "$1"; }

MODE="${1:-clean}"

report() {
  echo "── Memory & load ──"
  sysctl vm.swapusage 2>/dev/null | sed 's/^/  /'
  top -l 1 -n 0 2>/dev/null | grep -E "PhysMem|Load Avg" | sed 's/^/  /'
  echo "── Top RAM consumers (MB) ──"
  ps aux 2>/dev/null | sort -nrk 4 | head -10 | awk '{printf "  %6.0f MB  %4s%% cpu  %s\n", $6/1024, $3, $11}'
}

if [ "$MODE" = "--report" ]; then report; exit 0; fi

echo "Cleaning stale dev leftovers…"
# Old gmux/tauri dev sessions that linger for hours
for pat in "tauri dev" "node_modules/.bin/vite" "launch-v4.sh --dev"; do
  pids=$(pgrep -f "$pat" 2>/dev/null)
  [ -n "$pids" ] && kill $pids 2>/dev/null && ok "killed stale: $pat"
done
# Duplicate python http servers on :5550 (keep at most one)
http_pids=$(pgrep -f "http.server 5550" 2>/dev/null | tail -n +2)
[ -n "$http_pids" ] && kill $http_pids 2>/dev/null && ok "killed duplicate http servers"

# Purge inactive memory (compresses/frees standby pages)
if sudo -n purge 2>/dev/null; then ok "purged inactive memory"; else warn "purge needs sudo (skipped)"; fi

# Lighten the GPU/compositor on old Intel Macs
defaults write com.apple.dock launchanim -bool false 2>/dev/null && ok "dock launch animation off"
defaults write com.apple.dock expose-animation-duration -float 0.1 2>/dev/null || true

echo
report
echo
echo "  Biggest wins are usually things only YOU can close:"
echo "   • Chrome with many tabs (each tab ~80–300 MB) — close unused tabs/windows"
echo "   • iTerm with many panes/unlimited scrollback — close old tabs"
echo "  On 8 GB RAM, keeping Chrome + iTerm + an AI agent open at once will swap."
if [ "$MODE" = "--aggressive" ]; then
  echo
  warn "Aggressive mode: to quit Chrome now, run:  osascript -e 'quit app \"Google Chrome\"'"
fi
