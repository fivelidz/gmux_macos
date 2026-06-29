#!/bin/bash
# gmux browser UI launcher — no Tauri required
exec "$(dirname "$0")/launch.sh" --browser "$@"
