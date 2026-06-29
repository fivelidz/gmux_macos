#!/usr/bin/env bash
# Serve the gmux agent flowchart dashboard (v2).
# Open the URL in a browser, then drag to your second monitor + press F.
set -euo pipefail

PORT="${1:-${PORT:-1900}}"
OPEN_FLAG=""
[[ "${1:-}" == "--open" ]] && { OPEN_FLAG="--open"; PORT="${PORT:-1900}"; }
[[ "${2:-}" == "--open" ]] && OPEN_FLAG="--open"

cd "$(dirname "$0")/.."
echo "→ gmux dashboard v2 (single-agent flowchart)"
echo "  url:  http://localhost:${PORT}/dashboard/"
echo "  ctrl-c to stop"
[[ -n "$OPEN_FLAG" ]] && (sleep 1 && (xdg-open "http://localhost:${PORT}/dashboard/" 2>/dev/null || open "http://localhost:${PORT}/dashboard/" 2>/dev/null)) &
exec python3 -m http.server "$PORT" --bind 127.0.0.1
