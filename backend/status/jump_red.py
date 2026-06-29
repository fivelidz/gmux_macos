#!/usr/bin/env python3.11
"""
jump_red.py — Jump to the next pane in WAITING (RED) state.

Called by tmux keybinding (prefix + N).
Reads /tmp/gmuxtest-pane-state.json, finds the next waiting window
relative to the current window, and selects it.
"""

import json
import subprocess
from pathlib import Path

STATE_FILE = Path("/tmp/gmuxtest-pane-state.json")


def main():
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        subprocess.run(["tmux", "display-message", "gmux: no state data"])
        return

    # Get current window index
    try:
        cur = int(
            subprocess.check_output(
                ["tmux", "display-message", "-p", "#{window_index}"],
                text=True,
                timeout=1,
            ).strip()
        )
    except Exception:
        cur = 0

    # Find waiting panes sorted by window index
    waiting = sorted(
        [v for v in data.values() if v.get("state") == "waiting"],
        key=lambda x: x.get("window_index", 0),
    )

    if not waiting:
        subprocess.run(["tmux", "display-message", "gmux: no RED panes ✓"])
        return

    # Find first after current, wrap around
    target = None
    for w in waiting:
        if w.get("window_index", 0) > cur:
            target = str(w["window_index"])
            break
    if not target:
        target = str(waiting[0]["window_index"])

    name = waiting[0].get("window_name", target)
    subprocess.run(["tmux", "select-window", "-t", target])
    subprocess.run(
        ["tmux", "display-message", f"gmux: 🔴 [{target}:{name}] needs input"]
    )


if __name__ == "__main__":
    main()
