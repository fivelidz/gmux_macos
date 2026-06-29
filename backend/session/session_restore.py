#!/usr/bin/env python3.11
"""
session_restore.py — restore gmux session from tmux-resurrect save files.

tmux-resurrect already saves/restores window layout and working directories.
gmux adds on top:
  1. Parse the resurrect file to find which windows had qalcode2 running
  2. After resurrect restores the layout, re-launch qalcode2 in those windows
  3. Rename windows to project directory name (not "bun")
  4. Apply gmux status bar overrides
  5. Daemon mode: auto-save window names every 30s so they survive restart

The resurrect file format (line by line):
  pane  SESSION  WINDOW  PANE  FLAGS  ACTIVE  TITLE  DIR  ACTIVE  CMD  FULL_CMD
  window SESSION WINDOW  NAME  ...

We look at FULL_CMD to detect qalcode2 and extract --cwd project path.

Usage:
  python3.11 session_restore.py --check      # show what would be restored
  python3.11 session_restore.py --restore     # re-launch agents after resurrect
  python3.11 session_restore.py --names       # rename windows to project names
  python3.11 session_restore.py --hook        # called by tmux-resurrect post-restore hook
  python3.11 session_restore.py --daemon      # run save-loop + name-restore every 30s
"""

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

RESURRECT_DIR = Path.home() / ".local" / "share" / "tmux" / "resurrect"
GMUX_SESSION = "gmuxtest"

# Persistent name cache: written to disk so names survive gmux restart
NAMES_CACHE_FILE = Path("/tmp/gmuxtest-window-names.json")

# alpha.17 — Durable session manifest for the Tauri restore panel.
# Written every 30s by the daemon + on manual save so the restore UI can
# offer one-click resume after a reboot or panel close.
_XDG_DATA_HOME = Path(
    __import__("os").environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
)
SESSION_MANIFEST_FILE = _XDG_DATA_HOME / "gmuxtest" / "session_manifest.json"

# Process names that tmux auto-rename sets — we always ignore these
_GENERIC_NAMES = {
    "bun",
    "fish",
    "bash",
    "zsh",
    "sh",
    "python3",
    "python3.11",
    "node",
    "nvim",
    "vim",
    "tmux",
}

# Detect qalcode2 in the full command
QALCODE_RE = re.compile(
    r"bun run.*opencode.*src/index\.ts\s+(\S+?)(?:\s+--agent\s+(\S+))?$"
)


@dataclass
class ResurrectedPane:
    session: str
    window_idx: int
    window_name: str  # from 'window' lines in resurrect file
    pane_title: str  # from 'pane' TITLE field (set by shell integration)
    directory: str
    command: str
    full_cmd: str
    is_qalcode: bool
    project_dir: str  # extracted from qalcode2 --cwd arg
    agent: str  # yolo, etc.


def latest_resurrect_file() -> Path | None:
    """Find the most recent resurrect save file."""
    files = sorted(RESURRECT_DIR.glob("tmux_resurrect_*.txt"), reverse=True)
    if not files:
        return None
    # tmux-resurrect also maintains a 'last' symlink
    last = RESURRECT_DIR / "last"
    if last.exists() or last.is_symlink():
        target = last.resolve()
        if target.exists():
            return target
    return files[0]


def parse_resurrect(path: Path) -> list[ResurrectedPane]:
    """Parse a tmux-resurrect save file into ResurrectedPane objects."""
    panes = []
    # First pass: build window name map
    window_names: dict[tuple[str, int], str] = {}

    for line in path.read_text().splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        if parts[0] == "window" and len(parts) >= 4:
            session = parts[1]
            win_idx = int(parts[2]) if parts[2].isdigit() else 0
            win_name = parts[3]
            window_names[(session, win_idx)] = win_name

    for line in path.read_text().splitlines():
        parts = line.split("\t")
        if not parts or parts[0] != "pane":
            continue
        if len(parts) < 10:
            continue

        # pane SESSION WINDOW_IDX PANE_IDX FLAGS ACTIVE TITLE DIR ACTIVE CMD [FULL_CMD]
        try:
            session = parts[1]
            win_idx = int(parts[2])
            pane_title = (
                parts[6] if len(parts) > 6 else ""
            )  # pane title (shell CWD/cmd)
            directory = parts[7]
            command = parts[9]
            full_cmd = parts[10] if len(parts) > 10 else ""
            # Prefer pane title (from resurrect) over stale window_name
            # pane_title is often set by shell integration to show current dir/cmd
            win_name = pane_title or window_names.get((session, win_idx), str(win_idx))
        except (IndexError, ValueError):
            continue

        # Detect qalcode2
        m = QALCODE_RE.search(full_cmd)
        is_qalcode = bool(m)
        project_dir = m.group(1) if m else directory
        agent = m.group(2) if (m and m.group(2)) else "yolo"

        panes.append(
            ResurrectedPane(
                session=session,
                window_idx=win_idx,
                window_name=window_names.get((session, win_idx), str(win_idx)),
                pane_title=pane_title,
                directory=directory,
                command=command,
                full_cmd=full_cmd,
                is_qalcode=is_qalcode,
                project_dir=project_dir,
                agent=agent,
            )
        )

    return panes


def get_good_window_name(pane: ResurrectedPane) -> str:
    """
    Get a clean window name.
    Priority: project dir name > pane title > window_name
    The project dir name is the most human-readable and stable identifier.
    """
    # 1. For qalcode panes, use the project dir (most meaningful)
    if pane.is_qalcode and pane.project_dir:
        path = Path(pane.project_dir)
        if path.name:
            return path.name

    # 2. Use the working directory name
    if pane.directory:
        path = Path(pane.directory)
        if path.name and path.name not in ("~", "/", ""):
            return path.name

    # 3. Fall back to whatever was saved as window_name
    return pane.window_name or str(pane.window_idx)


def rename_windows(panes: list[ResurrectedPane], session: str = GMUX_SESSION):
    """Rename all windows in session to their project directory names."""
    # Deduplicate: one name per window index
    seen: dict[int, ResurrectedPane] = {}
    for p in panes:
        if p.session == session and p.window_idx not in seen:
            seen[p.window_idx] = p

    renamed = 0
    for win_idx, pane in sorted(seen.items()):
        new_name = get_good_window_name(pane)
        result = subprocess.run(
            ["tmux", "rename-window", "-t", f"{session}:{win_idx}", new_name],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            renamed += 1

    return renamed


def relaunch_agents(panes: list[ResurrectedPane], session: str = GMUX_SESSION):
    """
    Re-launch qalcode2 in windows where it was running.
    tmux-resurrect restores the shell + directory but not running processes.
    """
    qc_panes = [p for p in panes if p.session == session and p.is_qalcode]

    # Deduplicate by window (only one qalcode per window)
    done_windows: set[int] = set()
    launched = 0

    for pane in sorted(qc_panes, key=lambda p: p.window_idx):
        if pane.window_idx in done_windows:
            continue
        done_windows.add(pane.window_idx)

        target = f"{session}:{pane.window_idx}"

        # Verify window exists
        result = subprocess.run(
            ["tmux", "list-panes", "-t", target],
            capture_output=True,
            timeout=2,
        )
        if result.returncode != 0:
            continue

        # cd to project dir and launch qalcode2
        qc_cmd = _build_qalcode_cmd(pane)

        # Small stagger to avoid all agents hammering startup simultaneously
        if launched > 0:
            time.sleep(0.3)

        subprocess.run(
            [
                "tmux",
                "send-keys",
                "-t",
                target,
                f"cd {pane.project_dir} && {qc_cmd}",
                "Enter",
            ],
            capture_output=True,
            timeout=2,
        )
        launched += 1
        project_name = Path(pane.project_dir).name
        print(f"  🤖 [{pane.window_idx}:{project_name}] → {qc_cmd[:60]}")

    return launched


def _build_qalcode_cmd(pane: ResurrectedPane) -> str:
    """
    Reconstruct the qalcode2 launch command.
    Uses the full_cmd from resurrect if available, else builds from config.
    """
    # If resurrect has the full bun command, we can use it directly
    if pane.full_cmd and "bun run" in pane.full_cmd:
        return pane.full_cmd

    # Fallback: build from config
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import get as get_config  # type: ignore

        cfg = get_config()
        binary = cfg.qalcode2.binary
        agent = pane.agent or cfg.qalcode2.agent
    except Exception:
        binary = "qalcode2"
        agent = pane.agent or "yolo"

    return f"{binary} --agent {agent}"


def run_hook(session: str = GMUX_SESSION):
    """
    Called by tmux-resurrect's post-restore hook.
    This runs AFTER resurrect has restored the layout.
    """
    save_file = latest_resurrect_file()
    if not save_file:
        print("[gmuxtest-restore] No resurrect save file found.", flush=True)
        return

    print(f"[gmuxtest-restore] Restoring from: {save_file.name}", flush=True)
    panes = parse_resurrect(save_file)

    session_panes = [p for p in panes if p.session == session]
    if not session_panes:
        # Try session "0" if gmux session not found
        session_panes = [p for p in panes if p.session == "0"]
        if session_panes:
            session = "0"

    if not session_panes:
        print(f"[gmuxtest-restore] No panes found for session '{session}'", flush=True)
        return

    qc_count = sum(1 for p in session_panes if p.is_qalcode)
    print(
        f"[gmuxtest-restore] {len(session_panes)} panes, {qc_count} with qalcode2",
        flush=True,
    )

    # Step 1a: Restore names from persistent cache (most reliable - names we saved before restart)
    restored_names = restore_window_names(session)
    print(
        f"[gmuxtest-restore] Restored {restored_names} window names from cache",
        flush=True,
    )

    # Step 1b: Rename windows from resurrect file (project dir names for qalcode panes)
    renamed = rename_windows(session_panes, session)
    print(f"[gmuxtest-restore] Renamed {renamed} windows from resurrect", flush=True)

    # Step 2: Re-launch qalcode2 agents
    if qc_count > 0:
        print(f"[gmuxtest-restore] Re-launching {qc_count} agents...", flush=True)
        launched = relaunch_agents(session_panes, session)
        print(f"[gmuxtest-restore] Launched {launched} agents", flush=True)

    # Step 3: Apply gmux status bar
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from gmux import apply_status_overrides  # type: ignore

        apply_status_overrides(session)
        print(f"[gmuxtest-restore] Status bar applied", flush=True)
    except Exception as e:
        print(f"[gmuxtest-restore] Status bar: {e}", flush=True)


def _read_names_cache() -> dict[str, str]:
    """Read the names cache file safely, handling empty/corrupt files."""
    if not NAMES_CACHE_FILE.exists():
        return {}
    for _ in range(3):  # retry up to 3 times in case of mid-write race
        try:
            text = NAMES_CACHE_FILE.read_text().strip()
            if text:
                return json.loads(text)
        except Exception:
            pass
        import time as _time

        _time.sleep(0.05)
    return {}


def save_window_names(session: str = GMUX_SESSION):
    """
    Snapshot current tmux window names to a JSON file.

    IMPORTANT: also removes entries for windows that no longer exist.
    Without this, closing window 3 "expose" and opening a new window 3
    would immediately stamp "expose" onto the new window.

    Only stores real custom names (not generic process names like "bun").
    """
    try:
        out = subprocess.check_output(
            [
                "tmux",
                "list-windows",
                "-t",
                session,
                "-F",
                "#{window_index}|#{window_name}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return

    # Build the set of window indices that currently exist in this session
    live_indices: set[str] = set()
    live_names: dict[str, str] = {}  # win_idx → current tmux name

    for line in out.strip().splitlines():
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        win_idx, name = parts
        live_indices.add(win_idx)
        live_names[win_idx] = name

    # Load existing cache
    cache = _read_names_cache()

    # ── Prune closed windows ──────────────────────────────────────────────────
    # Remove any cached entry whose window index no longer exists in this session.
    # This is the key fix: prevents old names from being stamped onto new windows.
    keys_to_delete = [
        key
        for key in list(cache.keys())
        if key.startswith(f"{session}:") and key.split(":", 1)[1] not in live_indices
    ]
    for key in keys_to_delete:
        del cache[key]

    # ── Update with current good names ────────────────────────────────────────
    for win_idx, name in live_names.items():
        if name.lower() in _GENERIC_NAMES:
            # Generic process name — keep existing cached entry if we have one
            # (it may be a better name from before auto-rename clobbered it)
            continue
        key = f"{session}:{win_idx}"
        cache[key] = name

    # ── Write atomically ──────────────────────────────────────────────────────
    try:
        content = json.dumps(cache)
        tmp = NAMES_CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(content)
        tmp.rename(NAMES_CACHE_FILE)
    except Exception:
        pass


def restore_window_names(session: str = GMUX_SESSION) -> int:
    """
    Re-apply saved window names to the current session.

    Only renames windows that actually exist — never stamps a name from a
    closed window onto a new window that happened to get the same index.
    Returns number of windows renamed.
    """
    cache = _read_names_cache()
    if not cache:
        return 0

    # Get currently existing window indices for this session
    try:
        out = subprocess.check_output(
            ["tmux", "list-windows", "-t", session, "-F", "#{window_index}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        live_indices = set(out.strip().splitlines())
    except Exception:
        return 0

    renamed = 0
    for key, name in cache.items():
        if not key.startswith(f"{session}:"):
            continue
        win_idx = key.split(":", 1)[1]
        if win_idx not in live_indices:
            continue  # window no longer exists — skip
        result = subprocess.run(
            ["tmux", "rename-window", "-t", f"{session}:{win_idx}", name],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            renamed += 1
    return renamed


def save_session_manifest(session: str = GMUX_SESSION) -> None:
    """alpha.17 — Write a durable session manifest to SESSION_MANIFEST_FILE.

    Reads the live pane-state JSON (if present and fresh), extracts the fields
    the Tauri restore panel needs, and writes them to a durable location under
    ~/.local/share/gmuxtest/ so they survive reboots.

    Called every 30s by run_daemon() and also on demand.
    Failures are silently swallowed (never kill the daemon).
    """
    import os

    try:
        state_file = Path("/tmp/gmuxtest-pane-state.json")
        if not state_file.exists():
            return
        # Only read if the file was updated within the last 30s — stale state
        # is better skipped than written with an outdated snapshot_ts.
        if time.time() - state_file.stat().st_mtime > 30:
            return

        panes_raw: dict = json.loads(state_file.read_text())
        if not isinstance(panes_raw, dict):
            return

        now = time.time()
        manifest: dict = {}

        # Merge with any existing manifest so stale entries survive
        try:
            if SESSION_MANIFEST_FILE.exists():
                existing = json.loads(SESSION_MANIFEST_FILE.read_text())
                if isinstance(existing, dict):
                    manifest = existing
        except Exception:
            pass

        live_pane_ids: set = set()
        for pane_id, p in panes_raw.items():
            if not isinstance(p, dict):
                continue
            state_val = p.get("state", "idle")
            if state_val in ("idle", "shell", "not_started"):
                continue  # Only record panes with an AI session attached

            live_pane_ids.add(pane_id)
            win_name = p.get("window_name", "")
            working_dir = p.get("directory", "") or p.get("cwd", "")
            model = p.get("model", "")
            api_port = p.get("api_port", 0)
            session_id = p.get("session_id", "")
            tmux_session = p.get("tmux_session", session)
            tmux_window = p.get("window_index", 0)
            todo_done = p.get("todo_done", 0)
            todo_total = p.get("todo_total", 0)

            # Last message preview from stored messages
            last_preview = ""
            msgs = p.get("messages") or []
            if msgs and isinstance(msgs, list):
                for msg in reversed(msgs):
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "")
                    if role in ("assistant", "agent"):
                        text = msg.get("text", "") or msg.get("content", "")
                        if isinstance(text, list):
                            text = " ".join(
                                t.get("text", "")
                                for t in text
                                if isinstance(t, dict) and t.get("type") == "text"
                            )
                        last_preview = str(text)[:200]
                        break

            manifest[pane_id] = {
                "pane_id": pane_id,
                "window_name": win_name,
                "working_dir": working_dir,
                "state": state_val,
                "model": model,
                "api_port": api_port,
                "session_id": session_id,
                "tmux_session": tmux_session,
                "tmux_window": tmux_window,
                "last_message_preview": last_preview,
                "todo_done": todo_done,
                "todo_total": todo_total,
                "snapshot_ts": now,
                "stale": False,
            }

        # Mark entries not seen in this pass as stale; prune entries >30 days
        cutoff = now - 30 * 86400
        for pid in list(manifest.keys()):
            if pid not in live_pane_ids:
                manifest[pid]["stale"] = True
                if manifest[pid].get("snapshot_ts", 0) < cutoff:
                    del manifest[pid]

        if not manifest:
            return

        SESSION_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SESSION_MANIFEST_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2))
        tmp.rename(SESSION_MANIFEST_FILE)

    except Exception as e:
        # Non-critical — never kill the daemon
        print(f"[gmuxtest-session] manifest write error: {e}", file=sys.stderr)


def run_daemon(session: str = GMUX_SESSION):
    """
    Daemon loop for the session saver.

    - Every 30s: save current window names (before auto-rename clobbers them)
    - Every 30s: also trigger tmux-resurrect save via Ctrl+A Ctrl+S if possible

    This is started by gmux.py at startup so names are always persisted.
    """
    print(f"[gmuxtest-session] Daemon started for session '{session}'", flush=True)
    while True:
        try:
            save_window_names(session)
        except Exception as e:
            print(f"[gmuxtest-session] save error: {e}", file=sys.stderr)
        # alpha.17 — also write the durable session manifest for restore panel
        try:
            save_session_manifest(session)
        except Exception as e:
            print(f"[gmuxtest-session] manifest error: {e}", file=sys.stderr)
        time.sleep(30)


def show_check():
    """Show what would be restored from the latest save."""
    save_file = latest_resurrect_file()
    if not save_file:
        print("No resurrect save file found.")
        print(f"Save one with: tmux prefix + Ctrl+S")
        return

    import os

    age_s = time.time() - os.path.getmtime(save_file)
    age = f"{int(age_s // 60)}m ago" if age_s > 60 else f"{int(age_s)}s ago"
    print(f"Latest save: {save_file.name}  ({age})")
    print()

    panes = parse_resurrect(save_file)
    sessions: dict[str, list] = {}
    for p in panes:
        sessions.setdefault(p.session, []).append(p)

    for session, spanes in sessions.items():
        seen_wins: set[int] = set()
        print(f"Session: {session}")
        for p in sorted(spanes, key=lambda x: x.window_idx):
            if p.window_idx in seen_wins:
                continue
            seen_wins.add(p.window_idx)
            icon = "🤖" if p.is_qalcode else "  "
            name = get_good_window_name(p)
            print(f"  {icon} [{p.window_idx}] {name:20} {p.project_dir[:50]}")
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Set process name so it shows as gmux-session in htop/system monitor
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).parent.parent))
    try:
        from config import set_process_name  # type: ignore

        set_process_name("gmux-session")
    except Exception:
        pass

    args = sys.argv[1:]

    session = GMUX_SESSION
    for i, a in enumerate(args):
        if a == "--session" and i + 1 < len(args):
            session = args[i + 1]

    if "--daemon" in args:
        run_daemon(session)
    elif "--check" in args or not args:
        show_check()
    elif "--restore" in args or "--hook" in args:
        run_hook(session)
    elif "--names" in args:
        f = latest_resurrect_file()
        if f:
            panes = parse_resurrect(f)
            n = rename_windows(panes)
            print(f"Renamed {n} windows")
        else:
            print("No save file found")
    elif "--save-names" in args:
        save_window_names(session)
        print(f"Saved window names for session '{session}'")
    elif "--restore-names" in args:
        n = restore_window_names(session)
        print(f"Restored {n} window names for session '{session}'")
