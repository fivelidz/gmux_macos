#!/usr/bin/env python3.11
"""
pane_status.py — AI state indicators for the gmux status bar.

Called by tmux in three ways:

  pane_status.py right <session>
      → status-right: compact attention alerts ONLY (no names, just icon+number)
        e.g.  !3  ●6  ✋  (permission on 3, waiting on 6, gesture live)
        Names already visible in the tab bar — no duplication.

  pane_status.py <session> <window_index>
      → window-status-format: one coloured tab  e.g.  6:● ai diary

  pane_status.py <session> <window_index> active
      → window-status-current-format: the active/focused tab (brighter)

STATE LEGEND (shown in each tab AND in status-right as icon only):
  !  ORANGE  — AI asking for permission  (approve/y-n/confirm)
  ●  RED     — AI waiting for input      (prompt visible)
  ◉  GREEN   — AI actively working       (tools running, spinner)
  ◆  BLUE    — AI finished, unseen
  ○  DIM     — No AI running
  ✗  RED     — Error
"""

import json
import subprocess
import sys
from pathlib import Path

STATE_FILE = Path("/tmp/gmuxtest-pane-state.json")
INDICATOR_FILE = Path("/tmp/gmuxtest-services.json")
RESET = "#[default]"

# ── Tmux colour strings ──────────────────────────────────────────────────────

STYLES = {
    "permission": "#[fg=colour214,bold]",  # orange  — main agent needs approval
    "sub_permission": "#[fg=colour214,bold]",  # orange  — sub-agent needs approval (same colour, different icon)
    "waiting": "#[fg=colour196,bold]",  # red     — ready for input
    "working": "#[fg=colour114,bold]",  # green   — running
    "done": "#[fg=colour75]",  # blue    — finished
    "error": "#[fg=colour196,bold,blink]",  # red blink — broken
    "not_started": "#[fg=colour244]",  # grey    — not launched yet
    "idle": "#[fg=colour240]",  # dark grey — no AI
}

ACTIVE_STYLES = {
    "permission": "#[fg=colour214,bold]",
    "sub_permission": "#[fg=colour214,bold]",
    "waiting": "#[fg=colour196,bold]",
    "working": "#[fg=colour156,bold]",
    "done": "#[fg=colour117,bold]",
    "error": "#[fg=colour196,bold]",
    "not_started": "#[fg=colour246,bold]",
    "idle": "#[fg=colour252,bold]",
}

ICONS = {
    "permission": "!",  # orange  — main agent needs your decision NOW
    "sub_permission": "^!",  # orange  — a sub-agent (Task tool) needs your decision
    "waiting": "●",  # red     — prompt showing, send it something
    "working": "◉",  # green   — running tools / streaming
    "done": "◆",  # blue    — just finished
    "error": "✗",  # red     — broke
    "not_started": "─",  # grey    — window exists, qalcode not started
    "idle": "○",  # dim     — plain shell, no AI
}

PRIORITY = {
    "error": 0,
    "permission": 1,
    "sub_permission": 1,  # same urgency as main permission
    "waiting": 2,
    "working": 3,
    "done": 4,
    "not_started": 5,
    "idle": 6,
}


# ── Data loading ─────────────────────────────────────────────────────────────


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def load_services() -> dict:
    try:
        return json.loads(INDICATOR_FILE.read_text())
    except Exception:
        return {}


def cam_broker_active() -> bool:
    """Read camera status from services JSON — written by monitor.py every 10s.
    Never spawns systemctl; zero subprocess cost at status-bar refresh time."""
    svc = load_services()
    # Fall back to True if key absent (monitor not yet written first value)
    return svc.get("cam", False)


# ── AI Diary integration ──────────────────────────────────────────────────────
# Shows today's diary task progress in the gmux status bar, e.g. 📋 3/7.
# Reads a cache file written by diary_status_cache.py (refreshed periodically),
# so the status bar NEVER makes a blocking HTTP call. Zero cost if the diary
# isn't running — the segment just disappears.

DIARY_CACHE = Path("/tmp/gmux-diary-status.json")


def diary_segment() -> str:
    """Return a tmux-formatted diary progress segment, or '' if unavailable.

    Cache shape: {"done": int, "total": int, "ts": float, "overdue": int}
    Colour: green when all done, amber when partial, red when 0 done + tasks
    exist, dim grey when nothing scheduled.
    """
    try:
        import time

        data = json.loads(DIARY_CACHE.read_text())
    except Exception:
        return ""
    # Stale-guard: if the cache is older than 5 min, don't show (diary likely down)
    try:
        if time.time() - float(data.get("ts", 0)) > 300:
            return ""
    except Exception:
        return ""
    done = int(data.get("done", 0))
    total = int(data.get("total", 0))
    overdue = int(data.get("overdue", 0))
    if total == 0 and overdue == 0:
        return ""
    # Build "📋 done/total" with an overdue flag if any
    if total > 0 and done >= total:
        colour = "#[fg=colour114]"  # green — all done
    elif done > 0:
        colour = "#[fg=colour214]"  # amber — partial
    else:
        colour = "#[fg=colour196]"  # red — nothing done yet
    label = f"📋{done}/{total}"
    if overdue > 0:
        label += f"#[fg=colour196]!{overdue}#[default]"
    return f"{colour}{label}{RESET}"


def update_service(name: str, active: bool):
    svc = load_services()
    svc[name] = active
    try:
        INDICATOR_FILE.write_text(json.dumps(svc))
    except Exception:
        pass


def effective_state(info: dict) -> str:
    """
    Return the display state key for a pane, accounting for sub-agent permission.
    When state=permission AND sub_agent_permission=True, use "sub_permission"
    so the tab shows ^! instead of !.
    """
    state = info.get("state", "idle")
    if state == "permission" and info.get("sub_agent_permission", False):
        return "sub_permission"
    return state


def best_state_for_window(data: dict, session: str, win_idx: str) -> dict | None:
    """Find the highest-priority pane state for a given window in a session."""
    best = None
    best_pri = 99

    for info in data.values():
        win_match = str(info.get("window_index", "")) == win_idx
        if not win_match:
            continue

        ses_match = (info.get("session_name", "") == session) if session else True
        if not ses_match:
            continue

        state = info.get("state", "idle")
        pri = PRIORITY.get(state, 9)
        if pri < best_pri:
            best_pri = pri
            best = info

    # Fallback: no session match → try without session filter
    if best is None and session:
        return best_state_for_window(data, "", win_idx)

    return best


def windows_by_priority(data: dict, session: str) -> list[tuple[int, dict]]:
    """Return list of (window_index, info) sorted by window index, one per window."""
    best: dict[int, dict] = {}
    for info in data.values():
        if session and info.get("session_name", "") != session:
            continue
        wi = info.get("window_index", 0)
        state = effective_state(info)
        pri = PRIORITY.get(state, 9)
        if wi not in best or pri < PRIORITY.get(effective_state(best[wi]), 9):
            best[wi] = info
    return sorted(best.items())


# ── Format functions ─────────────────────────────────────────────────────────


def get_tmux_window_name(session: str, win_idx: str) -> str:
    """Ask tmux directly for the window name — used as fallback when no state entry."""
    try:
        target = f"{session}:{win_idx}" if session else win_idx
        out = subprocess.check_output(
            ["tmux", "display-message", "-t", target, "-p", "#{window_name}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
        return out.strip()
    except Exception:
        return win_idx


def format_tab(session: str, win_idx: str, active: bool) -> str:
    """
    One tab in the window tab bar.

    Inactive:  6:● ai diary
    Active:    6:◉ gmux        (brighter, bg highlight)

    Always shows number so you can type: tmux select-window -t 6
    """
    data = load_state()
    info = best_state_for_window(data, session, win_idx)

    if not info:
        # Window in tmux but not yet in state — show real window name
        name = get_tmux_window_name(session, win_idx)
        max_name = 10
        if len(name) > max_name:
            name = name[: max_name - 1] + "…"
        if active:
            return f"#[fg=colour252,bg=#1e293b,bold] {win_idx}:○ {name} {RESET}"
        return f"#[fg=colour240] {win_idx}:○ {name}{RESET} "

    state = effective_state(info)  # "sub_permission" when sub-agent asks
    name = info.get("window_name", win_idx)
    icon = ICONS.get(state, "○")

    # Truncate name to keep tabs readable at reasonable widths
    max_name = 10
    if len(name) > max_name:
        name = name[: max_name - 1] + "…"

    # Extra context shown for active states
    tool = info.get("current_tool", "")
    tdone = info.get("todo_done", 0)
    ttot = info.get("todo_total", 0)

    # Tool suffix: show what's running, e.g. ":bash"
    tool_sfx = f":{tool}" if tool and state == "working" else ""

    # Todo suffix: e.g. " 3/5" (only show if there are todos)
    todo_sfx = f" {tdone}/{ttot}" if ttot > 0 else ""

    if active:
        style = ACTIVE_STYLES.get(state, "#[fg=colour252,bold]")
        return (
            f"#[bg=#1e293b]"
            f"{style} {win_idx}:{icon}{tool_sfx} "
            f"#[fg=colour252,bold]{name}{todo_sfx} "
            f"{RESET}"
        )
    else:
        style = STYLES.get(state, "#[fg=colour240]")
        return f" {style}{win_idx}:{icon}{tool_sfx} {name}{todo_sfx}{RESET} "


def format_status_right(session: str = "") -> str:
    """
    Compact status-right — icons and numbers ONLY, no names.
    Names are already visible in the tab bar — repeating them causes the
    double-display bug the user reported.

    Output examples:
      !3 ●6           — permission on win 3, waiting on win 6
      ●6 ✋ 🎤        — waiting + gesture live + voice live
      ◉×9             — 9 working, all fine (quiet indicator)
      (nothing)       — everything idle/done, no attention needed
    """
    data = load_state()

    # Service indicators (gesture / voice / camera)
    svc = load_services()
    parts = []

    # AI Diary today-progress segment (📋 done/total). Empty if diary down/idle.
    diary = diary_segment()
    if diary:
        parts.append(diary)

    # Camera indicator: 📷 green=on, dim strikethrough=off
    # Uses systemctl check — cached by the 1s status interval so not expensive
    if cam_broker_active():
        parts.append("#[fg=colour114]📷#[default]")
    else:
        parts.append("#[fg=colour240,dim]📷#[default]")

    if svc.get("gesture"):
        parts.append("#[fg=colour114]✋#[default]")
    if svc.get("voice"):
        parts.append("#[fg=colour75]🎤#[default]")

    if not data:
        return " ".join(parts) if parts else ""

    wins = windows_by_priority(data, session)

    # Attention items: permission / waiting / error only
    for wi, info in wins:
        state = effective_state(info)  # resolves sub_permission
        if state in ("permission", "sub_permission", "waiting", "error"):
            style = STYLES.get(state, "")
            icon = ICONS.get(state, "?")
            parts.append(f"{style}{icon}{wi}{RESET}")

    # Quiet working count — show only when nothing else needs attention
    attention_count = sum(
        1 for _, info in wins if info.get("state") in ("permission", "waiting", "error")
    )
    working_count = sum(1 for _, info in wins if info.get("state") == "working")
    if attention_count == 0 and working_count > 0:
        parts.append(f"#[fg=colour114,dim]◉×{working_count}{RESET}")

    return "  ".join(parts)


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    argv = sys.argv[1:]

    # ── status-right: pane_status.py right [session] ──────────────────────
    if not argv or argv[0] == "right":
        session = argv[1] if len(argv) > 1 else ""
        print(format_status_right(session), end="")
        return

    # ── service toggle: pane_status.py set <name> <0|1> ──────────────────
    if argv[0] == "set" and len(argv) >= 3:
        update_service(argv[1], argv[2] == "1")
        return

    # ── debug indicator: pane_status.py indicator ─────────────────────────
    if argv[0] == "indicator":
        svc = load_services()
        parts = []
        if svc.get("gesture"):
            parts.append("✋ gesture LIVE")
        if svc.get("voice"):
            parts.append("🎤 voice LIVE")
        if not parts:
            parts.append("no services running")
        print(" │ ".join(parts))
        return

    # ── window tab: pane_status.py <session> <window_index> [active] ─────
    # Detect old vs new calling convention:
    #   Old: pane_status.py 6              (just window index)
    #   Old: pane_status.py 6 active
    #   New: pane_status.py 0 6            (session, window)
    #   New: pane_status.py 0 6 active
    if len(argv) >= 2 and not argv[1] in ("active",):
        # New: first arg is session name, second is window index
        session = argv[0]
        win_idx = argv[1]
        is_active = len(argv) > 2 and argv[2] == "active"
    else:
        # Old/fallback: first arg is window index
        session = ""
        win_idx = argv[0]
        is_active = len(argv) > 1 and argv[1] == "active"

    print(format_tab(session, win_idx, is_active), end="")


if __name__ == "__main__":
    main()
