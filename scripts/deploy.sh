#!/usr/bin/env bash
# gmux-system — host-side deploy script.
# Pushes the host's local working tree to a target machine and runs the
# install/launch sequence there. Use this when you have local changes
# that aren't on GitHub yet.
#
# Usage:
#   ./scripts/deploy.sh <target-host>
#   ./scripts/deploy.sh sandbox
#   ./scripts/deploy.sh root@192.168.1.20
#
# The target must:
#  - Be reachable via ssh (key-auth recommended)
#  - Have bash + curl (everything else installs itself)
#
# What this does:
#  1. rsync this repo's working tree to target:~/projects/gmux-system
#     (excludes .git, node_modules, target/, models/, VM_REPORTS/)
#  2. SSH to target and run install-vm.sh which:
#     - Installs system + Python + bun + opencode-ai
#     - Creates tmux 'gmux' session
#     - Starts monitor.py + UI HTTP server
#  3. Prints the URLs to access from your host browser

set -euo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "usage: $0 <target-host>"
  echo "  e.g. $0 sandbox"
  echo "       $0 root@192.168.1.20"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "  gmux-system deploy → $TARGET"
echo ""

# 1. rsync working tree
echo "  ↻ rsync source files (this may take 10-30s on a slow link)"
rsync -a --delete \
  --exclude .git \
  --exclude node_modules \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'app/src-tauri/target' \
  --exclude 'models/' \
  --exclude 'docs/VM_REPORTS' \
  --exclude 'archive/' \
  "$REPO_DIR/" "$TARGET:~/projects/gmux-system/"

# 2. Pull any VM-AI reports back so we have them locally
echo "  ↻ pull VM reports (if any)"
rsync -a \
  "$TARGET:~/projects/gmux-system/docs/VM_REPORTS/" \
  "$REPO_DIR/docs/VM_REPORTS/" 2>/dev/null || true

# 3. Run install-vm.sh on target
echo "  ↻ run install-vm.sh on $TARGET"
ssh "$TARGET" "bash ~/projects/gmux-system/scripts/install-vm.sh" \
  || { echo "  ✗ install-vm.sh failed on $TARGET"; exit 1; }

echo ""
echo "  ── done ──"
echo ""
echo "  From this machine, verify with:"
echo "    curl --max-time 3 http://$TARGET:8769/health"
echo "    open http://$TARGET:5550/ui/v3/index.html"
echo ""
