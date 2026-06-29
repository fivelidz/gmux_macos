#!/usr/bin/env python3.11
"""
gmux status monitor — event-driven, talks to QalCode2's HTTP/SSE API directly.

ARCHITECTURE:
  One SSE listener thread per QalCode2 instance.
  Each instance has its own local HTTP server (random port per bun process).
  We subscribe to the SSE stream and update state in real-time.
  A separate tmux poll thread handles process lifecycle (new/dead panes).

STATE MACHINE (8 states):
  ─────────────────────────────────────────────────────────────────
  not_started  ─  GREY        bun process found but zero sessions exist yet
  waiting      ●  RED         AI loaded, between turns, ready for input
  working      ◉  GREEN       AI actively running tools or streaming response
  permission   !  ORANGE      AI needs you to approve a tool call
  done         ◆  BLUE        AI just completed a task (brief flash)
  error        ✗  RED         Hard error — session.error event or retry exhausted
  idle         ○  DIM         No QalCode2 running in this pane (plain shell)
  rate_limited ⏱  ORANGE-RED  API rate-limit detected (429/quota/too-many-reqs)
  ─────────────────────────────────────────────────────────────────

API sources (per QalCode2 bun instance):
  GET  /session/status      → [] (waiting) | [{"type":"busy"}] | [{"type":"retry"}]
  GET  /session             → list sessions (count=0 → not_started)
  GET  /session/:id/todo    → todo progress for rich status display
  SSE  /event               → real-time events:
         session.status       → { type: "idle"|"busy"|"retry" }
         permission.updated   → permission needed
         permission.replied   → permission answered
         session.error        → hard error
         message.part.updated → { tool, status: "running"|"completed"|"error" }

QalCode2 integration:
  We ALSO expose a gmux status endpoint via POST /gmux/status so QalCode2 can
  PUSH state to us (removing the need to poll at all).
  See: src/status/gmux_receiver.py
"""

import http.server
import json
import os
import platform
import re
import socketserver
import subprocess
import sys
import time
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Optional

# ── Platform detection ────────────────────────────────────────────────────────
_IS_MACOS = platform.system() == "Darwin"

# psutil is REQUIRED for the live RAM/CPU/uptime/children metrics added in v3.1.
# It is a standard package on Arch/CachyOS and is also available via pip.
# Without it, the process-level fields stay at zero and the UI falls back to "—".
#
# Static analysers see psutil as Optional after the try/except, which is
# correct, but every USE of psutil is guarded by `if not _HAS_PSUTIL: return`.
# The `# type: ignore` markers on the import line suppress the noise.
try:
    import psutil  # type: ignore[import-not-found]

    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    _HAS_PSUTIL = False

STATE_FILE = Path("/tmp/gmuxtest-pane-state.json")
INDICATOR_FILE = Path("/tmp/gmuxtest-services.json")
# Shared with session_restore.py — persistent window names that survive restart
NAMES_CACHE_FILE = Path("/tmp/gmuxtest-window-names.json")
# alpha.17 — Session manifest: durable snapshot of pane state written to
# ~/.local/share/gmuxtest/ so the Tauri restore panel can show saved sessions
# and offer one-click resume after a reboot or panel close.
_XDG_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
SESSION_MANIFEST_FILE = _XDG_DATA_HOME / "gmuxtest" / "session_manifest.json"
# v3.7 — gmux-spawned sub-agents (separate pane, killable independently).
# Written by the Rust spawn_sub_agent command; keyed by window_name.
# Shape: { "<win_name>": { "parent_pane_id": "...", "spawned_at": <ms>,
#                          "agent_type": "...", "model": "..." } }
SUB_AGENTS_FILE = Path("/tmp/gmuxtest-sub-agents.json")
# v3.5 — Activity feed (tool_start/tool_end events) and derived file-touch map.
# Consumed by the Agent Monitor (dashboard) per
# Knowledge_systems/gmux_memory_integration/docs/02_DATA_CONTRACTS.md.
ACTIVITY_FILE = Path("/tmp/gmuxtest-activity.json")
FILES_FILE = Path("/tmp/gmuxtest-files.json")
ACTIVITY_MAX = 500  # circular buffer cap, same as the JS data layer uses
POLL_INTERVAL = 2.0  # tmux process check interval (SSE handles real-time)
API_TIMEOUT = 1.5
# Sample window over which CPU% is averaged. The first call to psutil.cpu_percent()
# returns 0 because it has no baseline — we cache and re-query each poll.
_CPU_SAMPLE_INTERVAL = None  # None = non-blocking, returns since last call

# ── State definitions ─────────────────────────────────────────────────────────


class PaneState(str, Enum):
    NOT_STARTED = "not_started"  # ─  GREY    bun up, no sessions yet
    WAITING = "waiting"  # ●  RED     idle between turns
    WORKING = "working"  # ◉  GREEN   running tools/streaming
    PERMISSION = "permission"  # !  ORANGE  needs tool approval
    DONE = "done"  # ◆  BLUE    just completed
    ERROR = "error"  # ✗  RED     hard error
    IDLE = "idle"  # ○  DIM     no AI in pane
    RATE_LIMITED = "rate_limited"  # ⏱  ORANGE-RED   API rate-limit / 429 received


# ── Per-pane live state (updated by SSE threads) ──────────────────────────────


@dataclass
class LiveState:
    state: PaneState = PaneState.IDLE
    api_port: int = 0
    current_tool: str = ""  # e.g. "bash", "write", "glob"
    session_id: str = ""  # active session ID
    todo_done: int = 0
    todo_total: int = 0
    has_sessions: bool = False
    last_update: float = 0.0
    sub_agent_permission: bool = (
        False  # True when a sub-agent (Task tool child) needs permission
    )
    # ── v3.1: Real todos {"id","content","status","priority"} from /session/:id/todo ─
    todos: list = field(default_factory=list)
    # Tool call history (last 30) — populated from message.part.updated SSE events
    tool_history: list = field(default_factory=list)
    last_message_fetch: float = 0.0
    # ── v3.1: OpenCode message aggregation (refreshed periodically, not via SSE) ──
    # Populated by refresh_session_aggregate() — totals across all assistant
    # messages in the active session. Used by the UI to show real token counts,
    # model name and cost without the UI having to hit the OpenCode API itself.
    model_id: str = ""  # e.g. "claude-sonnet-4-6"
    provider_id: str = ""  # e.g. "anthropic"
    token_in: int = 0  # cumulative input tokens (inc. cache reads)
    token_out: int = 0  # cumulative output tokens
    token_reasoning: int = 0  # extended-thinking tokens
    token_cache_read: int = 0  # cache hits (cheap)
    token_cache_write: int = 0  # cache writes
    cost_usd: float = 0.0  # sum of step-finish.cost (0 in QalCode 1.1.x)
    msg_count: int = 0  # number of messages in the session
    last_aggregate: float = 0.0  # epoch of last successful aggregation
    # ── v3.6 additions ────────────────────────────────────────────────────────
    # sub_agents: pane_ids whose sessions have parentID == this agent's session.
    sub_agents: list = field(default_factory=list)
    # last_tool_call_summary: compact summary of the most recent tool start.
    last_tool_call_summary: dict = field(default_factory=dict)
    # ── v3.7: rate-limit detection ────────────────────────────────────────────
    # Set when an API 429 / rate-limit signal is detected (Signal A or C).
    rate_limit_msg: str = ""  # human-readable rate-limit message
    rate_limit_until: Optional[float] = None  # epoch seconds (from Retry-After header)
    # Set by the aggregate worker (Signal B) when the OAuth token is near expiry.
    auth_expiring: bool = False  # token expires within 60 seconds
    auth_expired: bool = False  # token has already expired


# pane_id → LiveState
_live: dict[str, LiveState] = {}
_live_lock = threading.Lock()

# pane_id → SSE listener thread (to avoid duplicates)
_sse_threads: dict[str, threading.Thread] = {}

# ── v3.5: Activity feed (per Knowledge_systems data contract) ─────────────────
# Circular buffer of tool events, oldest dropped when over ACTIVITY_MAX.
# Each entry: {id, ts, pane_id, agent_name, kind, tool, args, duration_ms, result}
from collections import deque  # noqa: E402  (must come after stdlib imports)

_activity: deque = deque(maxlen=ACTIVITY_MAX)
_activity_lock = threading.Lock()
# Map pane_id → window_name for activity correlation (updated each tmux poll).
_pane_to_name: dict[str, str] = {}
# Map pane_id → cwd (project root) for file-touch absolute-path resolution.
_pane_to_cwd: dict[str, str] = {}
# Track per-tool start times so we can compute duration_ms on tool_end.
# Keyed by (pane_id, tool_call_id) where tool_call_id is part.id from opencode.
_tool_starts: dict[tuple[str, str], float] = {}

# Generic process names that tmux auto-rename uses — never store these as window names
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
}

# Cache of "last good" window names: (session, win_idx) → name
_window_name_cache: dict[tuple[str, int], str] = {}

# ── v3.7: gmux-spawned sub-agent registry ─────────────────────────────────────
# Loaded from /tmp/gmuxtest-sub-agents.json at startup and refreshed on every
# tmux poll cycle. Keyed by window_name (as set by spawn_sub_agent in Rust).
# On each poll cycle we resolve window_name → pane_id and build a pane_id-keyed
# dict (_spawned_sub_agents_by_pane) for O(1) lookup during write_state.
#
# This dict is intentionally separate from the opencode-internal sub-sessions
# that get_child_session_ids() handles — those are intra-session Task-tool
# sub-agents that live inside a single bun process. These are *independent panes*
# that the user can see, switch to, kill, etc.
_spawned_sub_agents_raw: dict[str, dict] = {}  # win_name → entry
_spawned_sub_agents_by_pane: dict[str, dict] = {}  # pane_id → entry


def _load_spawned_sub_agents() -> None:
    """Read /tmp/gmuxtest-sub-agents.json and refresh module-level dicts.

    Called once at startup and then on every tmux poll cycle. Resolves
    window_name keys to pane_ids using the current _pane_to_name mapping
    (which is populated during poll_tmux).

    Thread-safe: called from the main poll thread only; the _live_lock is
    NOT needed here because _spawned_sub_agents_by_pane is only read in
    write_state which is also called from the main poll thread.
    """
    global _spawned_sub_agents_raw, _spawned_sub_agents_by_pane
    if not SUB_AGENTS_FILE.exists():
        return
    try:
        text = SUB_AGENTS_FILE.read_text().strip()
        if not text:
            return
        raw: dict = json.loads(text)
    except Exception as e:
        print(f"[monitor] _load_spawned_sub_agents: {e}", file=sys.stderr)
        return

    _spawned_sub_agents_raw = raw

    # Resolve window_name → pane_id using the reverse of _pane_to_name.
    # Build a reverse map: name → pane_id (last-write-wins for duplicate names).
    name_to_pane: dict[str, str] = {v: k for k, v in _pane_to_name.items()}

    by_pane: dict[str, dict] = {}
    for win_name, entry in raw.items():
        pane_id = name_to_pane.get(win_name)
        if pane_id:
            by_pane[pane_id] = entry
    _spawned_sub_agents_by_pane = by_pane


def _load_names_cache():
    """Pre-populate in-memory cache from persistent file at startup."""
    data = _read_names_cache()
    for key, name in data.items():
        parts = key.split(":", 1)
        if len(parts) == 2:
            session, win_idx_s = parts
            if win_idx_s.isdigit():
                _window_name_cache[(session, int(win_idx_s))] = name


def _read_names_cache() -> dict[str, str]:
    """Read the names cache file safely, retrying on empty/corrupt."""
    if not NAMES_CACHE_FILE.exists():
        return {}
    for _ in range(3):
        try:
            text = NAMES_CACHE_FILE.read_text().strip()
            if text:
                return json.loads(text)
        except Exception:
            pass
        time.sleep(0.05)
    return {}


def _persist_window_name(session: str, win_idx: str, name: str):
    """
    Write a good window name to the persistent cache file.

    Only writes if the window actually exists right now — prevents phantom
    entries from closed windows being applied to new windows at the same index.
    """
    try:
        # Verify the window still exists before caching its name
        result = subprocess.run(
            [
                "tmux",
                "display-message",
                "-t",
                f"{session}:{win_idx}",
                "-p",
                "#{window_index}",
            ],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode != 0:
            return  # window gone — don't cache a stale name

        data = _read_names_cache()
        data[f"{session}:{win_idx}"] = name
        tmp = NAMES_CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.rename(NAMES_CACHE_FILE)
    except Exception:
        pass


# ── Pane info (from tmux) ─────────────────────────────────────────────────────


@dataclass
class PaneInfo:
    pane_id: str
    session_name: str
    window_index: int
    window_name: str
    pane_index: int
    is_active: bool
    foreground_cmd: str
    state: PaneState
    has_ai: bool
    last_line: str
    api_port: int = 0
    current_tool: str = ""
    todo_done: int = 0
    todo_total: int = 0
    pane_left: int = 0
    pane_top: int = 0
    pane_width: int = 80
    pane_height: int = 24
    sub_agent_permission: bool = False  # True when a Task-tool sub-agent needs approval
    # ── Extended fields (v3.1, populated by separate threads) ─────────────────
    # Real todo items: [{"id","content","status","priority"}] from /session/:id/todo
    todos: list = field(default_factory=list)
    # Working directory (used by UI to call OpenCode API)
    cwd: str = ""
    # Last 30 tool names called (most recent last)
    tool_history: list = field(default_factory=list)
    # Live process metrics (from psutil; zero when unavailable)
    ram_mb: int = 0  # RSS of the agent's bun process + children, MB
    cpu_pct: float = 0.0  # %CPU since last poll (parent only)
    uptime_s: int = 0  # seconds the bun process has been alive
    children: list = field(default_factory=list)  # [{"name","ram_mb"}]
    # OpenCode session aggregates (refreshed by aggregate thread)
    session_id: str = ""  # active OpenCode session id
    model: str = ""  # model name from latest assistant message
    provider: str = ""  # provider id, e.g. "anthropic"
    token_in: int = 0
    token_out: int = 0
    token_reasoning: int = 0
    cost_usd: float = 0.0
    msg_count: int = 0
    # ── v3.6: dashboard-facing extra fields ───────────────────────────────────
    # session_age_s aliases uptime_s so detail_panel.js can read it directly.
    session_age_s: int = 0
    # sub_agents: list of pane_ids that are child sessions of this agent.
    # Populated by get_sub_agents() during the aggregate refresh pass.
    sub_agents: list = field(default_factory=list)
    # last_tool_call_summary: compact summary of the most recent tool op.
    # Useful for quick info display without scanning the full activity feed.
    # Shape: {"tool": str, "file_path": str, "ts": str} | {}
    last_tool_call_summary: dict = field(default_factory=dict)
    # ── v3.7: rate-limit detection fields (surfaced to UI) ────────────────────
    rate_limit_msg: str = ""  # human-readable rate-limit message (or "")
    rate_limit_until: Optional[float] = None  # epoch seconds resume time (or null)
    auth_expiring: bool = False  # OAuth token expires within 60 seconds
    auth_expired: bool = False  # OAuth token has already expired
    # ── v3.8: agent_type (derived from foreground_cmd + provider + model) ─────
    # Populated during write_state so the phone bridge adapter can read it
    # directly without re-deriving. Values: 'opencode'|'claude'|'qalcode'|
    # 'aider'|'qwen'|'shell'.
    agent_type: str = ""


# ── Port discovery ────────────────────────────────────────────────────────────


def _list_listening_ports() -> str:
    """Return a string describing listening TCP ports in a cross-platform way.

    On Linux:  prefers `ss -tlnp` (fast, shows pid= tags).
    On macOS:  uses `lsof -i -P -n -sTCP:LISTEN` (BSD, no `ss`).
    Falls back to the other tool if the preferred one is unavailable.

    The returned string is formatted so callers can search for
    `pid=<N>` (Linux) or `<pid>` patterns (macOS lsof).
    """
    # Try ss first (Linux-native, fastest, includes pid= tags)
    if not _IS_MACOS:
        try:
            return subprocess.check_output(
                ["ss", "-tlnp"], text=True, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

    # macOS (or Linux fallback when ss missing): use lsof
    # lsof -i -P -n -sTCP:LISTEN  →  one listening socket per line,
    # columns: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
    try:
        return subprocess.check_output(
            ["lsof", "-i", "-P", "-n", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return ""


def _find_port_for_pid_lsof(bpid: str, lsof_out: str) -> int:
    """Parse `lsof -i -P -n` output to find a localhost port for a given PID.

    lsof output format (relevant columns):
      COMMAND   PID   USER   FD   TYPE  DEVICE  SIZE/OFF  NODE  NAME
      bun      1234   user   7u   IPv4  ...                TCP  127.0.0.1:PORT (LISTEN)

    We match lines where the second whitespace-delimited field equals bpid
    and extract the port from the NAME column (last field, format host:port).
    """
    for line in lsof_out.splitlines():
        parts = line.split()
        if len(parts) < 9:
            continue
        if parts[1] != bpid:
            continue
        name = parts[-1]  # e.g. "127.0.0.1:PORT" or "*:PORT"
        # Only accept localhost binds
        if not name.startswith("127.0.0.1:"):
            continue
        try:
            return int(name.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue
    return 0


def get_bun_port(shell_pid: int) -> int:
    """Find the QalCode2 HTTP port from the shell's bun child process.

    Strategy:
      1. Use pgrep to find bun child PIDs under shell_pid (one or two levels deep).
      2. Query listening ports via ss (Linux) or lsof (macOS / fallback).
      3. Match the bun PID against the port list to find its bound port.
    """
    bun_pids: list[str] = []
    try:
        bun_pids = (
            subprocess.check_output(
                ["pgrep", "-P", str(shell_pid), "bun"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            .strip()
            .split()
        )
    except subprocess.CalledProcessError:
        pass

    if not bun_pids:
        # One level deeper (fish → sh → bun)
        try:
            for cpid in (
                subprocess.check_output(
                    ["pgrep", "-P", str(shell_pid)],
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
                .strip()
                .split()
            ):
                try:
                    bun_pids += (
                        subprocess.check_output(
                            ["pgrep", "-P", cpid, "bun"],
                            text=True,
                            stderr=subprocess.DEVNULL,
                        )
                        .strip()
                        .split()
                    )
                except subprocess.CalledProcessError:
                    pass
        except subprocess.CalledProcessError:
            pass

    if not bun_pids:
        return 0

    # Get the port listing once (shared across all bun_pids to avoid N calls)
    port_listing = _list_listening_ports()

    for bpid in bun_pids[:2]:
        try:
            if not _IS_MACOS:
                # ss output: includes "pid=<N>" in the last column
                for line in port_listing.splitlines():
                    if f"pid={bpid}" in line:
                        m = re.search(r"127\.0\.0\.1:(\d+)", line)
                        if m:
                            return int(m.group(1))
            else:
                # lsof output: PID is the second column
                port = _find_port_for_pid_lsof(bpid, port_listing)
                if port:
                    return port
        except Exception:
            pass
    return 0


# Cache: pane_id → (port, discovery_time)
_port_cache: dict[str, tuple[int, float]] = {}


def get_port_cached(pane_id: str, shell_pid: int) -> int:
    now = time.time()
    if pane_id in _port_cache:
        port, ts = _port_cache[pane_id]
        if now - ts < 30.0:
            return port
    port = get_bun_port(shell_pid)
    _port_cache[pane_id] = (port, now)
    return port


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def api_get(port: int, path: str, directory: str = "") -> Optional[object]:
    """HTTP GET to qalcode2/opencode API.

    opencode ≥1.4 requires ?directory= on all endpoints that are instance-scoped
    (everything under the Instance.provide middleware, which is everything except
    /global/event and /doc).
    """
    try:
        sep = "&" if "?" in path else "?"
        url = (
            f"http://127.0.0.1:{port}{path}{sep}directory={directory}"
            if directory
            else f"http://127.0.0.1:{port}{path}"
        )
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=API_TIMEOUT) as r:
            return json.loads(r.read())
    except Exception:
        return None


# Cache: pane_id → project directory (resolved from tmux pane_current_path)
_pane_dir_cache: dict[str, tuple[str, float]] = {}


def get_pane_directory(pane_id: str) -> str:
    """Get the current working directory of a tmux pane (cached 30s)."""
    now = time.time()
    if pane_id in _pane_dir_cache:
        d, ts = _pane_dir_cache[pane_id]
        if now - ts < 30.0:
            return d
    try:
        out = subprocess.check_output(
            ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_current_path}"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
        d = out.strip()
        _pane_dir_cache[pane_id] = (d, now)
        return d
    except Exception:
        return ""


def get_session_status(port: int, directory: str = "") -> PaneState:
    """Poll /session/status. Returns PaneState.

    opencode ≥1.4 returns a RECORD: {sessionID: {type: "idle"|"busy"|"retry"}}
    Older qalcode2 returned a LIST: [] | [{type:"busy"}]
    We handle both formats.
    """
    result = api_get(port, "/session/status", directory)
    if result is None:
        return PaneState.IDLE  # server unreachable

    # New format: dict mapping sessionID → status object
    if isinstance(result, dict):
        if not result:
            return PaneState.WAITING  # no sessions running = waiting
        for status_obj in result.values():
            t = (
                status_obj.get("type", "idle")
                if isinstance(status_obj, dict)
                else "idle"
            )
            if t == "busy":
                return PaneState.WORKING
            if t == "retry":
                return PaneState.ERROR
        return PaneState.WAITING

    # Old format: list
    if not isinstance(result, list) or len(result) == 0:
        return PaneState.WAITING  # empty = all sessions idle

    for item in result:
        t = item.get("type", "")
        if t == "busy":
            return PaneState.WORKING
        if t == "retry":
            return PaneState.ERROR

    return PaneState.WAITING


def count_sessions(port: int, directory: str = "") -> int:
    """Return number of sessions in this QalCode2 instance."""
    result = api_get(port, "/session", directory)
    if isinstance(result, list):
        return len(result)
    return -1  # unknown


def get_active_session_id(port: int, directory: str = "") -> str:
    """Get the most recently used TOP-LEVEL session ID (skips sub-sessions).

    GET /session returns all sessions sorted by most-recently-updated, which
    includes child sub-sessions spawned by the task tool.  Sub-sessions never
    have todos (todowrite is disabled on sub-agents), so we must skip them and
    find the most-recently-updated session that has no parentID.
    """
    result = api_get(port, "/session", directory)
    if not isinstance(result, list):
        return ""
    for session in result:
        if not session.get("parentID"):
            return session.get("id", "")
    return ""


def get_todo_progress(
    port: int, session_id: str, directory: str = ""
) -> tuple[int, int]:
    """Return (done, total) todo counts for the active session."""
    if not session_id:
        return 0, 0
    result = api_get(port, f"/session/{session_id}/todo", directory)
    if not isinstance(result, list):
        return 0, 0
    total = len(result)
    done = sum(1 for t in result if t.get("status") == "completed")
    return done, total


def get_session_todos(port: int, session_id: str, directory: str = "") -> list:
    """v3.1: Return the full todo list (with text, status, priority).

    Used by the HTTP proxy endpoint /api/pane/:pid/todos so the UI doesn't
    need to know about OpenCode ports/directories.
    """
    if not session_id:
        return []
    result = api_get(port, f"/session/{session_id}/todo", directory)
    return result if isinstance(result, list) else []


def get_session_messages(
    port: int, session_id: str, directory: str = "", limit: int = 50
) -> list:
    """v3.1: Return the most recent N messages with their parts.

    The full list can be hundreds of messages, so we trim. The UI uses this
    to populate the chat panel with real conversation history.
    """
    if not session_id:
        return []
    result = api_get(port, f"/session/{session_id}/message", directory)
    if not isinstance(result, list):
        return []
    return result[-limit:] if limit > 0 else result


# ─── v3.1: OpenCode session aggregation ───────────────────────────────────────
# Sums tokens/cost across all assistant messages in the active session and
# captures the latest model. Called from a periodic background thread (every
# ~10s per pane) — we do NOT do this on the hot path because it pulls the full
# message list, which can be 100+ messages on long-running sessions.


def aggregate_session_stats(port: int, session_id: str, directory: str = "") -> dict:
    """Pull /session/:id/message and aggregate token/cost totals.

    Returns dict with: model, provider, token_in, token_out, token_reasoning,
    token_cache_read, token_cache_write, cost_usd, msg_count.
    Returns empty dict on failure (caller keeps previous values).
    """
    if not session_id:
        return {}
    result = api_get(port, f"/session/{session_id}/message", directory)
    if not isinstance(result, list):
        return {}

    # Build totals with explicit per-field accumulators (typed-friendly)
    token_in = 0
    token_out = 0
    token_reasoning = 0
    token_cache_read = 0
    token_cache_write = 0
    cost_usd = 0.0
    model_name = ""
    provider_name = ""

    # Walk every message: assistant messages carry tokens in `info.tokens`
    # and the model in `info.modelID`. We sum across all assistant turns.
    latest_model_time = 0
    for msg in result:
        info = msg.get("info") or {}
        if info.get("role") == "assistant":
            tokens = info.get("tokens") or {}
            cache = tokens.get("cache") or {}
            token_in += int(tokens.get("input", 0) or 0)
            token_out += int(tokens.get("output", 0) or 0)
            token_reasoning += int(tokens.get("reasoning", 0) or 0)
            token_cache_read += int(cache.get("read", 0) or 0)
            token_cache_write += int(cache.get("write", 0) or 0)
            cost_usd += float(info.get("cost", 0) or 0)

            # Pick the most-recently-completed assistant message's model
            ts = (info.get("time") or {}).get("completed") or 0
            if ts > latest_model_time and info.get("modelID"):
                latest_model_time = ts
                model_name = info["modelID"]
                provider_name = info.get("providerID", "")

    # Roll cache.read into token_in so the UI shows a single "input" figure
    # matching user intuition. cache_read stays available separately.
    token_in += token_cache_read

    return {
        "token_in": token_in,
        "token_out": token_out,
        "token_reasoning": token_reasoning,
        "token_cache_read": token_cache_read,
        "token_cache_write": token_cache_write,
        "cost_usd": cost_usd,
        "msg_count": len(result),
        "model": model_name,
        "provider": provider_name,
    }


def refresh_session_aggregate(pane_id: str) -> None:
    """Refresh the aggregate fields for ONE pane (called from worker thread).

    Looks up the pane's port + active session_id, hits the OpenCode message
    endpoint, and writes the aggregated totals back into _live[pane_id].
    Safe to call repeatedly; cheap when there are no new messages.
    """
    with _live_lock:
        ls = _live.get(pane_id)
        if not ls or not ls.api_port:
            return
        port = ls.api_port
        sid = ls.session_id

    directory = get_pane_directory(pane_id)

    # If we don't have a session_id yet, try to discover one
    if not sid:
        sid = get_active_session_id(port, directory)
        if not sid:
            return
        with _live_lock:
            if pane_id in _live:
                _live[pane_id].session_id = sid

    stats = aggregate_session_stats(port, sid, directory)
    if stats:
        with _live_lock:
            ls = _live.get(pane_id)
            if ls:
                ls.model_id = stats.get("model", "") or ls.model_id
                ls.provider_id = stats.get("provider", "") or ls.provider_id
                ls.token_in = stats["token_in"]
                ls.token_out = stats["token_out"]
                ls.token_reasoning = stats["token_reasoning"]
                ls.token_cache_read = stats["token_cache_read"]
                ls.token_cache_write = stats["token_cache_write"]
                ls.cost_usd = stats["cost_usd"]
                ls.msg_count = stats["msg_count"]
                ls.last_aggregate = time.time()

    # Also fetch real todos for this session (separate endpoint)
    todos_data = api_get(port, f"/session/{sid}/todo", directory)
    if isinstance(todos_data, list):
        with _live_lock:
            ls = _live.get(pane_id)
            if ls:
                # Keep last 15 entries — UI doesn't need huge histories
                ls.todos = todos_data[:15]

    # v3.6 — Populate sub_agents: child session IDs that have this pane's
    # session as their parentID. This lets the dashboard render a real
    # parent→child hierarchy rather than requiring manual localStorage grouping.
    child_sids = get_child_session_ids(port, sid, directory)
    # Map child session IDs → pane_ids by looking through _live for matching session_ids
    child_pane_ids: list = []
    with _live_lock:
        for pid, ls_other in _live.items():
            if pid == pane_id:
                continue
            if ls_other.session_id in child_sids:
                child_pane_ids.append(pid)
        ls_self = _live.get(pane_id)
        if ls_self:
            ls_self.sub_agents = child_pane_ids

    # v3.6 — Populate last_tool_call_summary from the activity deque.
    summary = _get_last_tool_summary_for_pane(pane_id)
    with _live_lock:
        ls_self = _live.get(pane_id)
        if ls_self:
            ls_self.last_tool_call_summary = summary


# ─── v3.1: process-level metrics via psutil ───────────────────────────────────
# We resolve the bun process (the agent itself) starting from the tmux pane's
# shell PID. RAM is the RSS of bun + all descendants summed. CPU is the
# parent only (kernel exposes cumulative-since-last-call %).


# Cache psutil.Process objects keyed by pid so cpu_percent() can use the
# "since last call" mode. Cleaned up when the process dies.
_proc_cache: dict = {}


def _find_bun_pid(shell_pid: int) -> int:
    """Walk the process tree from a tmux shell PID down to its bun child.

    The chain is typically:  shell → (optional sh) → bun
    Returns 0 if no bun is found within 2 levels.
    """
    if not _HAS_PSUTIL or shell_pid <= 0:
        return 0
    try:
        shell = psutil.Process(shell_pid)
        # Check direct children first (most common)
        for child in shell.children(recursive=False):
            try:
                if "bun" in child.name().lower():
                    return child.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        # One level deeper (fish → sh → bun pattern)
        for child in shell.children(recursive=False):
            try:
                for grand in child.children(recursive=False):
                    if "bun" in grand.name().lower():
                        return grand.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return 0


def get_process_metrics(shell_pid: int) -> dict:
    """Get RAM, CPU, uptime and child process list for the agent at this pane.

    Returns dict with keys: ram_mb, cpu_pct, uptime_s, children.
    Values are zero/empty when psutil unavailable or the process can't
    be inspected (permission, dead, etc.).
    """
    empty = dict(ram_mb=0, cpu_pct=0.0, uptime_s=0, children=[])
    if not _HAS_PSUTIL or shell_pid <= 0:
        return empty

    bun_pid = _find_bun_pid(shell_pid)
    if not bun_pid:
        return empty

    try:
        proc = _proc_cache.get(bun_pid)
        if proc is None or not proc.is_running():
            proc = psutil.Process(bun_pid)
            _proc_cache[bun_pid] = proc
            # First call seeds the CPU baseline — value is unreliable
            proc.cpu_percent(interval=None)

        # ── RAM: parent + all descendants summed ────────────────────────
        # The agent often spawns sub-processes (ripgrep, tsc, esbuild) that
        # count toward its true memory footprint.
        total_rss = proc.memory_info().rss
        kids_list: list = []
        try:
            for kid in proc.children(recursive=True):
                try:
                    rss = kid.memory_info().rss
                    total_rss += rss
                    kids_list.append(
                        {
                            "name": kid.name(),
                            "ram_mb": rss // (1024 * 1024),
                            "pid": kid.pid,
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Sort children by RAM desc, top 8 only (UI shows ~5)
        kids_list.sort(key=lambda k: k["ram_mb"], reverse=True)
        kids_list = kids_list[:8]

        # ── CPU: %CPU since last call (parent only) ─────────────────────
        # psutil returns 0..(100*ncpu). Cap at 100 for the UI bar.
        cpu = proc.cpu_percent(interval=None)

        # ── Uptime: now - create_time ───────────────────────────────────
        uptime = int(time.time() - proc.create_time())

        return dict(
            ram_mb=total_rss // (1024 * 1024),
            cpu_pct=round(min(100.0, cpu), 1),
            uptime_s=uptime,
            children=kids_list,
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # Process died between find and inspect — drop the cache entry
        _proc_cache.pop(bun_pid, None)
        return empty


# ── v3.7: Rate-limit detection helpers ───────────────────────────────────────
# Compiled regex for terminal output / SSE error text matching
_RATE_LIMIT_RE = re.compile(
    r"rate.?limit|429|too many requests|quota exceeded|resource_exhausted",
    re.IGNORECASE,
)
# Path to OpenCode's auth.json (stores OAuth tokens with expiry timestamps)
_AUTH_JSON_PATH = Path.home() / ".local" / "share" / "opencode" / "auth.json"


def _extract_retry_after(msg_text: str) -> Optional[float]:
    """Parse a Retry-After / resume-time value from API error text.

    Returns epoch seconds if found, else a best-guess fallback so the
    auto-resume loop always has *something* to wait for.

    Handles:
      1. "Retry-After: 30"  → now + 30s
      2. "retry_after: 1748000000"  → raw epoch (> 1e9)
      3. "Please try again in Xh Ym Zs" (Anthropic 429 body)
      4. "Usage limit reached … resets at HH:MM AM/PM UTC" (claude.ai 5h cap)
      5. Fallback: if any rate-limit text is present but no timer found,
         return now + 310s (5 min 10s) as a safe retry window.
         The 5-minute padding is intentional: hammering immediately after
         a window clears triggers a second 429 on some Anthropic accounts.
    """
    # ── Pattern 1 & 2: standard Retry-After header value ──────────────
    m = re.search(r"[Rr]etry[-_][Aa]fter[:\s]+([0-9]+)", msg_text)
    if m:
        val = int(m.group(1))
        if val > 1_000_000_000:
            return float(val)
        return time.time() + float(val)

    # ── Pattern 3: "Please try again in Xh Ym Zs" ─────────────────────
    # e.g. "Please try again in 5h 0m 0s"  or "2m 30s"
    m = re.search(
        r"try again in\s+(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?",
        msg_text,
        re.IGNORECASE,
    )
    if m:
        h = int(m.group(1) or 0)
        mn = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        total = h * 3600 + mn * 60 + s
        if total > 0:
            return time.time() + total + 30  # 30s grace on top

    # ── Pattern 4: "resets at HH:MM AM/PM UTC" (claude.ai 5h cap) ─────
    # e.g. "Your usage limit resets at 11:30 PM UTC"
    m = re.search(
        r"resets?\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)?\s*(UTC)?", msg_text, re.IGNORECASE
    )
    if m:
        import datetime

        h, mn = int(m.group(1)), int(m.group(2))
        ampm = (m.group(3) or "").upper()
        if ampm == "PM" and h != 12:
            h += 12
        elif ampm == "AM" and h == 12:
            h = 0
        now_utc = datetime.datetime.utcnow()
        reset = now_utc.replace(hour=h, minute=mn, second=0, microsecond=0)
        if reset <= now_utc:
            reset += datetime.timedelta(days=1)  # tomorrow
        return reset.timestamp() + 30  # 30s grace

    # ── Fallback: no timer found — return now + 5 min 10s ─────────────
    # Safe conservative default. The auto-resume loop will log that it
    # used the fallback so the user knows the real window is unknown.
    return time.time() + 310.0


def _check_auth_expiry() -> dict:
    """Read ~/.local/share/opencode/auth.json and return auth expiry flags.

    Returns a dict:
      {
        "<provider_id>": {
            "auth_expiring": bool,   # expires within 60s
            "auth_expired":  bool,   # already expired
        },
        ...
      }
    Returns {} if the file does not exist or cannot be read.

    The auth.json format used by opencode is:
      {
        "<provider_id>": {
          "access_token": "...",
          "expires": <epoch_ms>,   // or "expiresAt", "expires_at"
          ...
        },
        ...
      }
    We try the common key spellings and treat missing as "no expiry info".
    """
    if not _AUTH_JSON_PATH.exists():
        return {}
    try:
        text = _AUTH_JSON_PATH.read_text()
        data = json.loads(text)
    except Exception:
        return {}

    now_ms = time.time() * 1000  # convert to ms for comparison
    result: dict = {}
    for provider_id, entry in data.items():
        if not isinstance(entry, dict):
            continue
        # Try common key names for the expiry timestamp
        expires_ms: Optional[float] = None
        for key in ("expires", "expiresAt", "expires_at", "expiry"):
            v = entry.get(key)
            if v is not None:
                try:
                    v_f = float(v)
                    # Distinguish ms (> 1e12) from seconds (> 1e9)
                    if v_f > 1_000_000_000_000:
                        expires_ms = v_f
                    elif v_f > 1_000_000_000:
                        expires_ms = v_f * 1000
                    break
                except (TypeError, ValueError):
                    pass
        if expires_ms is None:
            continue
        remaining_ms = expires_ms - now_ms
        result[provider_id] = {
            "auth_expiring": 0 < remaining_ms < 60_000,
            "auth_expired": remaining_ms <= 0,
        }
    return result


# Module-level auth expiry cache: refreshed every aggregate cycle.
# Shape: provider_id → {"auth_expiring": bool, "auth_expired": bool}
_auth_expiry_cache: dict = {}
_auth_expiry_lock = threading.Lock()


def _refresh_auth_expiry_cache() -> None:
    """Update the module-level auth expiry cache from auth.json.
    Called from the aggregate worker every AGGREGATE_INTERVAL seconds.
    """
    global _auth_expiry_cache
    new_cache = _check_auth_expiry()
    with _auth_expiry_lock:
        _auth_expiry_cache = new_cache


# ── SSE listener ──────────────────────────────────────────────────────────────


def sse_listener(pane_id: str, port: int):
    """
    Subscribe to QalCode2's SSE event stream.
    Updates _live[pane_id] in real-time.
    Runs forever in a daemon thread.

    opencode ≥1.4 requires ?directory= query param so the server routes the
    SSE stream to the right Instance (each bun process serves one project dir).
    We look up the project directory from the pane info each time we reconnect.
    """

    # Resolve the project directory for this pane (needed for opencode ≥1.4)
    def _get_project_dir() -> str:
        try:
            fmt = "#{pane_id}|#{pane_current_path}"
            out = subprocess.check_output(
                ["tmux", "list-panes", "-a", "-F", fmt],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            for line in out.strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 2 and parts[0] == pane_id:
                    return parts[1].strip()
        except Exception:
            pass
        return ""

    base_url = f"http://127.0.0.1:{port}/event"
    project_dir = _get_project_dir()
    url = f"{base_url}?directory={project_dir}" if project_dir else base_url

    while True:
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                buf = b""
                while True:
                    chunk = resp.read(512)
                    if not chunk:
                        break
                    buf += chunk

                    # Process complete SSE events (separated by \n\n)
                    while b"\n\n" in buf:
                        event_bytes, buf = buf.split(b"\n\n", 1)
                        for line in event_bytes.decode(
                            "utf-8", errors="replace"
                        ).splitlines():
                            if line.startswith("data: "):
                                try:
                                    msg = json.loads(line[6:])
                                    _handle_sse_event(pane_id, port, msg)
                                except json.JSONDecodeError:
                                    pass

        except Exception:
            pass

        # Lost connection — wait, then reconnect (port may change if bun restarted)
        time.sleep(5)

        # Re-check if port is still valid for this pane
        with _live_lock:
            ls = _live.get(pane_id)
        if ls and ls.api_port != port:
            return  # port changed, new thread will handle it

        # Refresh directory in case pane changed CWD (re-build URL on reconnect)
        project_dir = _get_project_dir()
        url = f"{base_url}?directory={project_dir}" if project_dir else base_url


# ── v3.5: Activity feed helpers ───────────────────────────────────────────────
# Append tool_start / tool_end events into the shared _activity deque so the
# Agent Monitor dashboard's flowchart can render real edges. The deque is
# dumped to /tmp/gmuxtest-activity.json by the aggregate worker every cycle.


def _extract_file_path(tool_name: str, tool_input: dict) -> str:
    """Pull the most relevant file path from opencode tool args.

    Tool input shapes vary across providers — we check the common keys.
    Returns "" if nothing path-like is present (e.g. Bash without a file).
    """
    if not isinstance(tool_input, dict):
        return ""
    # Opencode-style keys (camelCase) plus snake_case fallbacks
    for key in ("filePath", "file_path", "path", "filepath"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            return v
    # Bash with `cd path && ...` — best-effort: ignore, too noisy
    return ""


# Tool names whose primary argument is a shell command (not a file path)
_BASH_TOOLS: frozenset[str] = frozenset({"Bash", "bash", "Terminal", "Shell"})
# Tool names that operate on patterns (Grep, Glob)
_PATTERN_TOOLS: frozenset[str] = frozenset({"Grep", "grep", "Glob", "glob"})


def _extract_tool_args(tool_name: str, tool_input: dict, pane_id: str = "") -> dict:
    """Build the sparse `args` dict for an activity event.

    Returns at most these keys:
      file_path      — ABSOLUTE path (v3.6.1) — resolved against the pane's cwd
                       if opencode gave a relative path. The dashboard relies on
                       this being absolute so it can show the full path back to
                       /home and group by parent folder correctly.
      file_path_rel  — relative version (project-rooted) for compact UI display.
                       Only set when the original input was already absolute and
                       fits under the pane cwd; otherwise omitted.
      command        — for Bash / Terminal tools (truncated)
      pattern        — for Grep / Glob tools (truncated)

    Unknown tools get an empty dict rather than a raw dump (keeps events small).
    """
    if not isinstance(tool_input, dict):
        return {}
    args: dict = {}

    # File path (camelCase and snake_case keys used by different providers)
    raw_fp = ""
    for key in ("filePath", "file_path", "path", "filepath"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            raw_fp = v
            break
    if raw_fp:
        # v3.6.1 — always emit the absolute path. _abs_path() handles both
        # "already absolute" and "relative, join with pane cwd" cases.
        abs_fp = _abs_path(pane_id, raw_fp) if pane_id else raw_fp
        args["file_path"] = abs_fp
        # Compute a project-relative form for compact display if possible.
        cwd = _pane_to_cwd.get(pane_id, "") if pane_id else ""
        if cwd and abs_fp.startswith(cwd.rstrip("/") + "/"):
            args["file_path_rel"] = abs_fp[len(cwd.rstrip("/")) + 1 :]

    # Bash command — truncate at 120 chars to avoid massive event payloads
    if tool_name in _BASH_TOOLS:
        for key in ("command", "cmd", "script"):
            v = tool_input.get(key)
            if isinstance(v, str) and v:
                args["command"] = v[:120]
                break

    # Grep / Glob pattern
    if tool_name in _PATTERN_TOOLS:
        for key in ("pattern", "query", "glob", "regex"):
            v = tool_input.get(key)
            if isinstance(v, str) and v:
                args["pattern"] = v[:80]
                break

    return args


def _record_activity_start(
    pane_id: str, tool_name: str, tool_call_id: str, tool_input: dict
) -> None:
    """Add a tool_start event to the activity deque."""
    now = time.time()
    args = _extract_tool_args(tool_name, tool_input, pane_id)
    ev = {
        "id": f"act_{int(now * 1000)}_{pane_id.replace('%', 'p')}_{tool_call_id[:8]}",
        "ts": _iso_now(now),
        "pane_id": pane_id,
        "agent_name": _pane_to_name.get(pane_id, ""),
        "kind": "tool_start",
        "tool": tool_name,
        "args": args,
        "duration_ms": None,
        "result": None,
    }
    with _activity_lock:
        _activity.append(ev)
        _tool_starts[(pane_id, tool_call_id)] = now


def _record_activity_end(
    pane_id: str,
    tool_name: str,
    tool_call_id: str,
    tool_input: dict,
    result: str = "ok",
) -> None:
    """Add a tool_end event with duration_ms relative to the matching start."""
    now = time.time()
    args = _extract_tool_args(tool_name, tool_input, pane_id)
    duration_ms = None
    with _activity_lock:
        started_at = _tool_starts.pop((pane_id, tool_call_id), None)
        if started_at is not None:
            duration_ms = int((now - started_at) * 1000)
        ev = {
            "id": f"act_{int(now * 1000)}_{pane_id.replace('%', 'p')}_{tool_call_id[:8]}_end",
            "ts": _iso_now(now),
            "pane_id": pane_id,
            "agent_name": _pane_to_name.get(pane_id, ""),
            "kind": "tool_end",
            "tool": tool_name,
            "args": args,
            "duration_ms": duration_ms,
            "result": result,
        }
        _activity.append(ev)


def _iso_now(t: float | None = None) -> str:
    """ISO-8601 UTC with millisecond precision and Z suffix."""
    if t is None:
        t = time.time()
    # Build as YYYY-MM-DDTHH:MM:SS.mmmZ
    ms = int((t - int(t)) * 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{ms:03d}Z"


def _abs_path(pane_id: str, rel_or_abs: str) -> str:
    """Resolve a file path: if absolute return as-is, else join with pane cwd."""
    if not rel_or_abs:
        return ""
    if rel_or_abs.startswith("/"):
        return rel_or_abs
    cwd = _pane_to_cwd.get(pane_id, "")
    if not cwd:
        return rel_or_abs
    return f"{cwd.rstrip('/')}/{rel_or_abs.lstrip('./')}"


def write_activity() -> None:
    """Dump the current activity deque to /tmp/gmuxtest-activity.json.

    Format: JSON array, newest-last (the JS layer re-sorts by ts DESC).
    Atomic write via tmpfile + rename.
    """
    with _activity_lock:
        snapshot = list(_activity)
    try:
        tmp = ACTIVITY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot))
        tmp.rename(ACTIVITY_FILE)
    except Exception as e:
        print(f"[gmuxtest-status] write_activity failed: {e}", file=sys.stderr)


def write_files() -> None:
    """Derive a file-touch map from the recent activity deque.

    Per Knowledge_systems data contract — one entry per absolute file path:
      touches_5m / touches_30m / touches_1h — rolling-window counts
      agents[] — unique pane_ids that touched in last 30m
      last_touch_ts / last_writer
      is_hot — touches_30m >= 5
      is_conflict — len(agents) >= 2 && touches_5m >= 2
      is_god_node / callers — populated by graphify later (0 for now)
    """
    with _activity_lock:
        events = list(_activity)
    now = time.time()
    five_min = now - 300
    thirty_min = now - 1800
    one_hour = now - 3600

    # Build per-path stats
    files: dict[str, dict] = {}
    write_tools = {"Write", "Edit", "MultiEdit", "Patch"}

    for ev in events:
        fp = ev.get("args", {}).get("file_path") or ""
        if not fp:
            continue
        pane_id = ev.get("pane_id", "")
        abs_p = _abs_path(pane_id, fp)
        if not abs_p:
            continue
        # Parse ts back to epoch (best-effort: split on '.' to drop ms)
        ts_str = ev.get("ts", "")
        try:
            base = ts_str.replace("Z", "").split(".")[0]
            ev_epoch = time.mktime(time.strptime(base, "%Y-%m-%dT%H:%M:%S"))
            # mktime treats as local; ts is UTC. Adjust:
            ev_epoch -= time.timezone
        except Exception:
            ev_epoch = now

        if ev_epoch < one_hour:
            continue  # too old to count

        # Derive a proper relative path by stripping the pane's CWD prefix.
        # Prefer: strip CWD from absolute path → relative keeps directory structure.
        # Fallback: if fp was already relative, use it as-is.
        # Worst case: just the filename (better than nothing).
        cwd = _pane_to_cwd.get(pane_id, "")
        if not fp.startswith("/"):
            # Already relative — use directly
            rel_p = fp
        elif cwd and abs_p.startswith(cwd.rstrip("/") + "/"):
            rel_p = abs_p[len(cwd.rstrip("/")) + 1 :]
        else:
            rel_p = abs_p.split("/")[-1]

        entry = files.setdefault(
            abs_p,
            {
                "path": abs_p,
                "rel_path": rel_p,
                "touches_5m": 0,
                "touches_30m": 0,
                "touches_1h": 0,
                "agents": [],
                "last_touch_ts": ts_str,
                "last_writer": "",
                "is_hot": False,
                "is_conflict": False,
                "is_god_node": False,
                "callers": 0,
            },
        )
        # only count tool_start so we don't double-count start+end
        if ev.get("kind") == "tool_start":
            if ev_epoch >= one_hour:
                entry["touches_1h"] += 1
            if ev_epoch >= thirty_min:
                entry["touches_30m"] += 1
                if pane_id and pane_id not in entry["agents"]:
                    entry["agents"].append(pane_id)
            if ev_epoch >= five_min:
                entry["touches_5m"] += 1
            entry["last_touch_ts"] = ts_str
            if ev.get("tool") in write_tools:
                entry["last_writer"] = pane_id

    # Derive flags
    for entry in files.values():
        entry["is_hot"] = entry["touches_30m"] >= 5
        entry["is_conflict"] = len(entry["agents"]) >= 2 and entry["touches_5m"] >= 2

    try:
        tmp = FILES_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(files))
        tmp.rename(FILES_FILE)
    except Exception as e:
        print(f"[gmuxtest-status] write_files failed: {e}", file=sys.stderr)


def _is_sub_agent_session(port: int, session_id: str, directory: str = "") -> bool:
    """Return True if session_id has a parentID — i.e. is a Task-tool sub-agent."""
    if not session_id:
        return False
    result = api_get(port, f"/session/{session_id}", directory)
    if isinstance(result, dict):
        return bool(result.get("parentID"))
    return False


def get_child_session_ids(
    port: int, parent_session_id: str, directory: str = ""
) -> list:
    """Return the list of session IDs whose parentID matches parent_session_id.

    These are the Task-tool sub-sessions spawned from the given parent session.
    Used to populate the `sub_agents[]` list on the parent pane record so the
    dashboard can display a real sub-agent hierarchy without requiring manual
    grouping in localStorage.
    """
    if not parent_session_id:
        return []
    result = api_get(port, "/session", directory)
    if not isinstance(result, list):
        return []
    return [
        s.get("id", "")
        for s in result
        if s.get("parentID") == parent_session_id and s.get("id")
    ]


def _get_last_tool_summary_for_pane(pane_id: str) -> dict:
    """Return a compact summary of the most recent tool_start event for pane_id.

    Scans the shared activity deque (most recently appended = last in deque).
    Returns {} if no events found for this pane.
    """
    with _activity_lock:
        events = list(_activity)
    # Deque is ordered oldest-first; walk in reverse to find the most recent
    for ev in reversed(events):
        if ev.get("pane_id") != pane_id:
            continue
        if ev.get("kind") == "tool_start":
            args = ev.get("args", {})
            return {
                "tool": ev.get("tool", ""),
                "file_path": args.get("file_path", ""),
                "command": args.get("command", ""),
                "ts": ev.get("ts", ""),
            }
    return {}


def _handle_sse_event(pane_id: str, port: int, msg: dict):
    """Process one SSE event and update live state."""
    ev_type = msg.get("type", "")
    props = msg.get("properties", {})

    # For permission.updated we need to check parentID via HTTP — do it outside
    # the lock so we don't hold the mutex during a network call.
    _resolve_sub: tuple[str, int, str] | None = None  # (pane_id, port, session_id)

    with _live_lock:
        if pane_id not in _live:
            _live[pane_id] = LiveState()
        ls = _live[pane_id]
        ls.api_port = port
        ls.last_update = time.time()

        # ── session.status ────────────────────────────────────────────────────
        if ev_type == "session.status":
            status = props.get("status", {})
            t = status.get("type", "idle")
            if t == "busy":
                if ls.state != PaneState.PERMISSION:
                    ls.state = PaneState.WORKING
            elif t == "retry":
                ls.state = PaneState.ERROR
            elif t == "idle":
                if ls.state not in (PaneState.PERMISSION,):
                    ls.state = PaneState.WAITING
                ls.current_tool = ""

        # ── session.idle (deprecated but still fires) ─────────────────────────
        elif ev_type == "session.idle":
            if ls.state not in (PaneState.PERMISSION,):
                ls.state = PaneState.WAITING
            ls.current_tool = ""

        # ── session.error ─────────────────────────────────────────────────────
        elif ev_type == "session.error":
            # v3.7 — Signal A: check for rate-limit text in the error payload.
            # opencode SSE events embed the error message in properties under
            # various keys depending on the provider SDK version.
            error_text = (
                props.get("message")
                or props.get("error")
                or props.get("text")
                or str(props)
            )
            if _RATE_LIMIT_RE.search(error_text):
                ls.state = PaneState.RATE_LIMITED
                ls.rate_limit_msg = str(error_text)[:200]
                ls.rate_limit_until = _extract_retry_after(error_text)
            else:
                ls.state = PaneState.ERROR
            ls.current_tool = ""

        # ── permission.updated ────────────────────────────────────────────────
        elif ev_type == "permission.updated":
            ls.state = PaneState.PERMISSION
            # Queue a parentID check — resolved AFTER the lock (HTTP call)
            perm_session_id = props.get("sessionID", "")
            if perm_session_id:
                _resolve_sub = (pane_id, port, perm_session_id)

        # ── permission.replied ────────────────────────────────────────────────
        elif ev_type == "permission.replied":
            ls.state = PaneState.WORKING
            ls.sub_agent_permission = False

        # ── message.part.updated (tool running/completed) ─────────────────────
        elif ev_type == "message.part.updated":
            part = props.get("part", {})
            if part.get("type") == "tool":
                tool_name = part.get("tool", "")
                tool_state = part.get("state", {})
                status = tool_state.get("status", "")
                session_id = part.get("sessionID", "")
                # v3.5 — capture call id + args for activity feed
                tool_call_id = part.get("id", "") or part.get("callID", "") or ""
                tool_input = tool_state.get("input", {}) or {}

                if session_id:
                    ls.session_id = session_id

                if status == "running":
                    ls.state = PaneState.WORKING
                    ls.current_tool = tool_name
                    # v3.1 FIX: also append to tool_history so the UI's tool
                    # timeline ribbon shows recent activity. We append at
                    # "running" (rather than "completed") so the UI sees the
                    # tool the moment it starts, not 200ms later.  Keep
                    # only the last 30 — same cap as the UI.
                    if tool_name:
                        ls.tool_history.append(tool_name)
                        if len(ls.tool_history) > 30:
                            ls.tool_history = ls.tool_history[-30:]
                    # v3.5 — record tool_start in the activity deque so the
                    # Agent Monitor's flowchart can render real edges.
                    if tool_name:
                        _record_activity_start(
                            pane_id, tool_name, tool_call_id, tool_input
                        )
                elif status in ("completed", "error"):
                    if ls.state == PaneState.WORKING:
                        ls.current_tool = ""
                    if status == "error":
                        ls.state = PaneState.ERROR
                    # v3.5 — record tool_end with duration + result
                    if tool_name:
                        _record_activity_end(
                            pane_id,
                            tool_name,
                            tool_call_id,
                            tool_input,
                            result="error" if status == "error" else "ok",
                        )

        # ── todo.updated ──────────────────────────────────────────────────────
        elif ev_type == "todo.updated":
            todos = props.get("todos", [])
            if todos:
                ls.todo_total = len(todos)
                ls.todo_done = sum(1 for t in todos if t.get("status") == "completed")

    # ── Resolve sub-agent permission (outside lock, HTTP safe) ───────────────
    if _resolve_sub:
        _pid, _port, _sid = _resolve_sub
        is_sub = _is_sub_agent_session(_port, _sid)
        with _live_lock:
            if _pid in _live:
                _live[_pid].sub_agent_permission = is_sub


def ensure_sse_listener(pane_id: str, port: int):
    """Start an SSE listener thread if not already running for this pane+port."""
    key = f"{pane_id}:{port}"
    if key in _sse_threads and _sse_threads[key].is_alive():
        return
    t = threading.Thread(
        target=sse_listener,
        args=(pane_id, port),
        daemon=True,
        name=f"sse-{pane_id[-6:]}",
    )
    t.start()
    _sse_threads[key] = t


# ── Initial state poll (before SSE catches up) ────────────────────────────────


def poll_initial_state(pane_id: str, port: int):
    """Query REST API once to get current state (SSE only gives deltas)."""
    directory = get_pane_directory(pane_id)
    session_count = count_sessions(port, directory)
    with _live_lock:
        if pane_id not in _live:
            _live[pane_id] = LiveState()
        ls = _live[pane_id]
        ls.api_port = port

        if session_count == 0:
            ls.state = PaneState.NOT_STARTED
            ls.has_sessions = False
            return
        elif session_count > 0:
            ls.has_sessions = True

        # Don't override permission state from a REST poll
        if ls.state == PaneState.PERMISSION:
            return

    # Poll status (outside lock to avoid holding during HTTP)
    state = get_session_status(port, directory)
    with _live_lock:
        ls = _live.get(pane_id)
        if ls and ls.state != PaneState.PERMISSION:
            ls.state = state

    # Get todo progress for the active session
    sid = get_active_session_id(port, directory)
    if sid:
        done, total = get_todo_progress(port, sid, directory)
        with _live_lock:
            ls = _live.get(pane_id)
            if ls:
                ls.session_id = sid
                ls.todo_done = done
                ls.todo_total = total


# ── Tmux pane polling ─────────────────────────────────────────────────────────


def _infer_agent_type(
    cmd: str, model: str = "", provider: str = "", win_name: str = ""
) -> str:
    """Derive agent_type from the foreground command, model and provider strings.

    Called during write_state so the pane dict has an explicit 'agent_type'
    field — the phone bridge adapter (and any future consumer) can read it
    without re-deriving. Mirrors the logic in
    gmux_phone_bridge_system/bridge/adapter.py::_detect_agent_type().

    Return values: 'opencode' | 'claude' | 'qalcode' | 'aider' | 'qwen' | 'shell'
    """
    c = cmd.lower().strip() if cmd else ""
    m = model.lower() if model else ""
    p = provider.lower() if provider else ""
    w = win_name.lower() if win_name else ""

    if c in ("bun", "node"):
        if "qalcode" in w or "qalcode" in m:
            return "qalcode"
        return "opencode"
    if "opencode" in c:
        return "opencode"
    if "qalcode" in c:
        return "qalcode"
    if "claude" in c:
        return "claude"
    if "aider" in c:
        return "aider"
    if "qwen" in c or "qwen" in m:
        return "qwen"
    # Provider-based inference (foreground cmd is a shell like fish/bash)
    if p in ("anthropic",) and m:
        return "opencode"
    if p in ("google",) or "gemini" in m:
        return "opencode"
    if p in ("openai",) or "gpt" in m:
        return "opencode"
    return "shell"


def is_qalcode(cmd: str) -> bool:
    return any(
        p in cmd.lower()
        for p in {
            "bun",
            "qalcode2",
            "qalcode",
            "opencode",
            "node",
            "python3.11",
            "claude",
        }
    )


def get_last_line(pane_id: str) -> str:
    try:
        out = subprocess.check_output(
            ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", "-2"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[-1][:80] if lines else ""
    except Exception:
        return ""


def poll_tmux() -> list[PaneInfo]:
    """Get tmux pane list and match to live state."""
    fmt = (
        "#{pane_id}|#{session_name}|#{window_index}|#{window_name}|#{pane_index}"
        "|#{pane_active}|#{pane_current_command}|#{pane_pid}"
        "|#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}"
    )
    try:
        out = subprocess.check_output(
            ["tmux", "list-panes", "-a", "-F", fmt],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return []

    panes = []
    seen_pane_ids: set[str] = set()

    for line in out.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 12:
            continue
        (
            pane_id,
            session_name,
            win_idx,
            win_name,
            pane_idx,
            active,
            cmd,
            pane_pid_str,
            p_left,
            p_top,
            p_width,
            p_height,
        ) = parts[:12]

        # Use the best available window name: prefer real name over generic process name.
        # Resolution order:
        #   1. tmux-reported real name (not in _GENERIC_NAMES) → use + cache
        #   2. Cached real name from a previous poll → use cached
        #   3. basename of the pane's CWD (e.g. "gmux-system") → use as friendly
        #      synthetic name. Better than showing "fish" / "bun" / "bash".
        #   4. Fallback: keep whatever tmux gave us (still might be "fish")
        win_key = (session_name, int(win_idx) if win_idx.isdigit() else 0)
        if win_name and win_name.lower() not in _GENERIC_NAMES:
            # Real custom name — cache it in memory
            if _window_name_cache.get(win_key) != win_name:
                _window_name_cache[win_key] = win_name
                # Also persist to disk so names survive monitor restart
                _persist_window_name(session_name, win_idx, win_name)
        elif win_key in _window_name_cache:
            # tmux has clobbered the name with a process name — use cached real name
            win_name = _window_name_cache[win_key]
        else:
            # No cache entry and the tmux name is generic ("fish", "bun" etc).
            # Derive a friendly name from the pane's current working directory.
            # This makes agents launched via prefix+c (which start as "fish")
            # immediately readable in the UI as e.g. "gmux-system" or "research".
            cwd = get_pane_directory(pane_id)
            if cwd:
                derived = cwd.rstrip("/").rsplit("/", 1)[-1]
                # Don't use ambiguous one-char names or "home" — better to show
                # the generic process name than mislead the user.
                if derived and derived not in ("", "/", "home") and len(derived) > 1:
                    win_name = derived
            # else: keep tmux's name (still might be "fish")

        seen_pane_ids.add(pane_id)
        has_ai = is_qalcode(cmd)
        port = 0

        if has_ai:
            try:
                shell_pid = int(pane_pid_str)
                port = get_port_cached(pane_id, shell_pid)
            except ValueError:
                pass

            if port:
                # Start SSE listener if new
                ensure_sse_listener(pane_id, port)

                # If we have no live state yet, poll REST API once
                with _live_lock:
                    has_state = pane_id in _live and _live[pane_id].last_update > 0
                if not has_state:
                    poll_initial_state(pane_id, port)

        # Fetch current live state (SSE-driven fields + v3.1/v3.6 aggregates)
        with _live_lock:
            ls = _live.get(pane_id)
            if ls and has_ai:
                state = ls.state
                current_tool = ls.current_tool
                todo_done = ls.todo_done
                todo_total = ls.todo_total
                port = ls.api_port or port
                sub_agent_permission = ls.sub_agent_permission
                # v3.1 aggregates from OpenCode message history
                session_id_v = ls.session_id
                model_v = ls.model_id
                provider_v = ls.provider_id
                token_in_v = ls.token_in
                token_out_v = ls.token_out
                token_reasoning_v = ls.token_reasoning
                cost_usd_v = ls.cost_usd
                msg_count_v = ls.msg_count
                # v3.6 — sub-agents + last tool summary
                sub_agents_v = list(ls.sub_agents)
                last_tool_summary_v = dict(ls.last_tool_call_summary)
                # v3.7 — rate-limit fields
                rate_limit_msg_v = ls.rate_limit_msg
                rate_limit_until_v = ls.rate_limit_until
                auth_expiring_v = ls.auth_expiring
                auth_expired_v = ls.auth_expired
            elif has_ai and not port:
                state = PaneState.IDLE  # bun found but no port yet
                current_tool = ""
                todo_done = 0
                todo_total = 0
                sub_agent_permission = False
                session_id_v = ""
                model_v = ""
                provider_v = ""
                token_in_v = 0
                token_out_v = 0
                token_reasoning_v = 0
                cost_usd_v = 0.0
                msg_count_v = 0
                sub_agents_v = []
                last_tool_summary_v = {}
                rate_limit_msg_v = ""
                rate_limit_until_v = None
                auth_expiring_v = False
                auth_expired_v = False
            else:
                state = PaneState.IDLE
                current_tool = ""
                todo_done = 0
                todo_total = 0
                sub_agent_permission = False
                session_id_v = ""
                model_v = ""
                provider_v = ""
                token_in_v = 0
                token_out_v = 0
                token_reasoning_v = 0
                cost_usd_v = 0.0
                msg_count_v = 0
                sub_agents_v = []
                last_tool_summary_v = {}
                rate_limit_msg_v = ""
                rate_limit_until_v = None
                auth_expiring_v = False
                auth_expired_v = False

        # ── v3.7 Signal B: auth expiry check ──────────────────────────────
        # Read from the module-level cache (updated by aggregate worker).
        # We apply it only for has_ai panes with a known provider.
        if has_ai and model_v:
            with _auth_expiry_lock:
                cache = dict(_auth_expiry_cache)
            # Match by provider_id if known; otherwise check if ANY provider expired.
            if provider_v and provider_v in cache:
                auth_expiring_v = cache[provider_v]["auth_expiring"]
                auth_expired_v = cache[provider_v]["auth_expired"]
            elif not provider_v and cache:
                # No known provider yet — flag if any token is expiring/expired
                auth_expiring_v = any(v["auth_expiring"] for v in cache.values())
                auth_expired_v = any(v["auth_expired"] for v in cache.values())

        last_line = get_last_line(pane_id)

        # ── v3.7 Signal C: terminal output rate-limit check ───────────────
        # If the SSE stream hasn't fired a session.error yet (e.g. opencode
        # crashed before emitting the event), fall back to scanning the last
        # terminal line for rate-limit keywords.
        if has_ai and _RATE_LIMIT_RE.search(last_line):
            with _live_lock:
                ls_rl = _live.get(pane_id)
                if ls_rl and ls_rl.state not in (
                    PaneState.RATE_LIMITED,
                    PaneState.WORKING,
                    PaneState.PERMISSION,
                ):
                    ls_rl.state = PaneState.RATE_LIMITED
                    if not ls_rl.rate_limit_msg:
                        ls_rl.rate_limit_msg = last_line[:200]
                    # alpha.17-dev4 — Always populate rate_limit_until so the
                    # frontend auto-resume loop has a concrete target to wait
                    # for. _extract_retry_after now returns a fallback (now+310s)
                    # even when no Retry-After header is present in the text.
                    if not ls_rl.rate_limit_until:
                        ls_rl.rate_limit_until = _extract_retry_after(last_line)

        # ── v3.1: process metrics (RAM / CPU / uptime / children) ─────────
        # Only meaningful when there's an AI process running in this pane.
        # Returns zeros when psutil missing or no bun process found.
        if has_ai:
            try:
                shell_pid_int = int(pane_pid_str)
            except ValueError:
                shell_pid_int = 0
            pm = get_process_metrics(shell_pid_int)
        else:
            pm = {"ram_mb": 0, "cpu_pct": 0.0, "uptime_s": 0, "children": []}

        # v3.5 — populate maps used by the activity feed so SSE handlers can
        # resolve pane_id → window_name and pane_id → cwd without re-querying tmux.
        _pane_to_name[pane_id] = win_name
        _pane_to_cwd[pane_id] = get_pane_directory(pane_id)

        panes.append(
            PaneInfo(
                pane_id=pane_id,
                session_name=session_name,
                window_index=int(win_idx) if win_idx.isdigit() else 0,
                window_name=win_name,
                pane_index=int(pane_idx) if pane_idx.isdigit() else 0,
                is_active=active == "1",
                foreground_cmd=cmd,
                state=state,
                has_ai=has_ai,
                last_line=last_line,
                api_port=port,
                current_tool=current_tool,
                todo_done=todo_done,
                todo_total=todo_total,
                pane_left=int(p_left) if p_left.isdigit() else 0,
                pane_top=int(p_top) if p_top.isdigit() else 0,
                pane_width=int(p_width) if p_width.isdigit() else 80,
                pane_height=int(p_height) if p_height.isdigit() else 24,
                sub_agent_permission=sub_agent_permission,
                # v3.1: live process metrics
                ram_mb=pm["ram_mb"],
                cpu_pct=pm["cpu_pct"],
                uptime_s=pm["uptime_s"],
                children=pm["children"],
                # v3.1: OpenCode session aggregates
                session_id=session_id_v,
                model=model_v,
                provider=provider_v,
                token_in=token_in_v,
                token_out=token_out_v,
                token_reasoning=token_reasoning_v,
                cost_usd=cost_usd_v,
                msg_count=msg_count_v,
                # v3.1: real todos + working directory
                todos=ls.todos if ls else [],
                cwd=get_pane_directory(pane_id) if has_ai else "",
                tool_history=list(ls.tool_history) if ls else [],
                # v3.6: session_age_s aliases uptime_s; sub_agents + summary
                session_age_s=pm["uptime_s"],
                sub_agents=sub_agents_v,
                last_tool_call_summary=last_tool_summary_v,
                # v3.7: rate-limit detection fields
                rate_limit_msg=rate_limit_msg_v,
                rate_limit_until=rate_limit_until_v,
                auth_expiring=auth_expiring_v,
                auth_expired=auth_expired_v,
                # v3.8: derived agent_type so consumers don't need to re-derive it
                agent_type=_infer_agent_type(cmd, model_v, provider_v, win_name),
            )
        )

    # Clean up dead panes from live state
    with _live_lock:
        for dead_id in set(_live.keys()) - seen_pane_ids:
            del _live[dead_id]

    return panes


def write_state(panes: list[PaneInfo]):
    data = {}
    for p in panes:
        d = asdict(p)
        d["state"] = p.state.value
        # v3.7 — ensure rate_limit_until serialises as null (not a dataclass default).
        # asdict() already handles Optional[float] → None correctly, but be explicit.
        if d.get("rate_limit_until") is None:
            d["rate_limit_until"] = None  # explicit null in JSON

        # v3.7 — merge gmux-spawned sub-agent parent pointer if present.
        # These are *independent pane* sub-agents (different from the intra-
        # session Task-tool sub-agents tracked in d["sub_agents"]).
        # Both can coexist: d["sub_agents"] continues to hold the list of
        # pane_ids whose opencode sessions have parentID == this session;
        # d["parent_pane_id"] / d["is_child_pane"] are set when THIS pane was
        # explicitly spawned via spawn_sub_agent from a parent pane.
        sa_entry = _spawned_sub_agents_by_pane.get(p.pane_id)
        if sa_entry:
            d["parent_pane_id"] = sa_entry.get("parent_pane_id", "")
            d["is_child_pane"] = True
            d["spawned_agent_type"] = sa_entry.get("agent_type", "")
            d["spawned_model"] = sa_entry.get("model", "")
            d["spawned_at_ms"] = sa_entry.get("spawned_at", 0)
        else:
            d.setdefault("parent_pane_id", "")
            d.setdefault("is_child_pane", False)

        data[p.pane_id] = d
    json_str = json.dumps(data, indent=2)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json_str)
    tmp.rename(STATE_FILE)
    # Push to any connected HTTP SSE clients
    _update_http_state(json_str)
    # alpha.17 — also write the durable session manifest for the restore panel
    _write_session_manifest(panes)


def _write_session_manifest(panes: list) -> None:
    """alpha.17 — Write a durable session manifest to
    ~/.local/share/gmuxtest/session_manifest.json.

    Called every time write_pane_state() writes the live state file, so the
    manifest is kept within 2 seconds of being current. Writing only happens
    when there is at least one non-idle pane so we don't snapshot useless
    empty sessions.

    The manifest is what the Tauri restore panel reads:
      - list_saved_sessions  →  reads this file
      - restore_session      →  reads a single entry and respawns/resumes it

    Schema (each entry keyed by pane_id):
    {
      "pane_id": "%1",
      "window_name": "my_project",
      "working_dir": "/home/user/projects/my_project",
      "state": "waiting",
      "model": "claude-sonnet-4-5",
      "api_port": 9001,
      "session_id": "abc123",
      "tmux_session": "gmux",
      "tmux_window": 3,
      "last_message_preview": "I've finished the refactor...",
      "todo_done": 8,
      "todo_total": 10,
      "snapshot_ts": 1716000010.0
    }
    """
    try:
        now = time.time()
        manifest: dict = {}

        # Load any existing manifest so we can MERGE — entries that are no
        # longer live keep their last-known data with a stale flag.
        try:
            if SESSION_MANIFEST_FILE.exists():
                existing = json.loads(SESSION_MANIFEST_FILE.read_text())
                if isinstance(existing, dict):
                    manifest = existing
        except Exception:
            pass

        for p in panes:
            pane_id = (
                getattr(p, "pane_id", None) or p.get("pane_id")
                if isinstance(p, dict)
                else None
            )
            if not pane_id:
                continue
            # Only meaningful if the pane has an AI session attached
            state_val = str(getattr(p, "state", "idle"))
            if state_val in ("idle", "shell"):
                continue

            # Safely get attrs whether p is a PaneInfo dataclass or a dict
            def _g(attr: str, default: object = ""):
                return (
                    getattr(p, attr, default)
                    if hasattr(p, attr)
                    else (p.get(attr, default) if isinstance(p, dict) else default)
                )

            win_name = str(_g("window_name") or "")
            tmux_session = str(_g("tmux_session") or "gmux")
            tmux_window = int(_g("window_index") or 0)  # type: ignore[arg-type]
            working_dir = str(_g("directory") or _g("cwd") or "")
            model = str(_g("model") or "")
            api_port = int(_g("api_port") or 0)  # type: ignore[arg-type]
            session_id = str(_g("session_id") or "")
            todo_done = int(_g("todo_done") or 0)  # type: ignore[arg-type]
            todo_total = int(_g("todo_total") or 0)  # type: ignore[arg-type]

            # Last message preview — from the messages list if present
            last_preview = ""
            msgs_raw = _g("messages") or []
            msgs: list = list(msgs_raw)  # type: ignore[arg-type]
            if msgs:
                # Walk backwards for last assistant message
                for msg in reversed(msgs):
                    role = msg.get("role", "") if isinstance(msg, dict) else ""
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

        # Mark entries not seen in this pass as stale (they may be restorable
        # but are no longer live). Keep stale entries up to 30 days.
        cutoff = now - 30 * 86400
        for pid, entry in list(manifest.items()):
            if pid not in {getattr(p, "pane_id", None) for p in panes}:
                entry["stale"] = True
                if entry.get("snapshot_ts", 0) < cutoff:
                    del manifest[pid]

        if not manifest:
            return

        SESSION_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SESSION_MANIFEST_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2))
        tmp.rename(SESSION_MANIFEST_FILE)
    except Exception as e:
        # Manifest write failures are non-critical — never kill the monitor
        print(f"[gmuxtest-status] manifest write failed: {e}", file=sys.stderr)


# ── Daemon ────────────────────────────────────────────────────────────────────


def cam_broker_active() -> bool:
    """Fast check — reads active state from systemctl (Linux) or returns False
    on macOS where systemctl is not available. macOS uses launchd, but the
    cam-broker service is not yet ported to launchctl, so we default to False
    and let the UI handle the "cam unavailable" state gracefully.
    """
    if _IS_MACOS:
        # systemctl does not exist on macOS. The gmux-cam-broker service is a
        # Linux systemd unit — it has no macOS equivalent yet.
        # TODO(macos): port to launchctl when cam-broker is ported to macOS.
        return False
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "gmux-cam-broker.service"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def write_services(cam: bool):
    """Write service flags to gmux-services.json so pane_status.py never has to call systemctl."""
    try:
        # Preserve existing gesture/voice flags, just update cam
        existing = {}
        if INDICATOR_FILE.exists():
            try:
                existing = json.loads(INDICATOR_FILE.read_text())
            except Exception:
                pass
        existing["cam"] = cam
        tmp = INDICATOR_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(existing))
        tmp.rename(INDICATOR_FILE)
    except Exception:
        pass


# ── HTTP state server (port 8769) — for web UI + phone PWA ──────────────────
# (8768 is used by gmux-voice; gmuxtest uses 8769)

_http_clients: list = []
_http_state_json: str = "{}"
_http_lock = threading.Lock()


def _update_http_state(json_str: str) -> None:
    """Call this whenever state changes to push SSE to all connected clients."""
    global _http_state_json
    _http_state_json = json_str
    msg = f"data: {json_str}\n\n".encode()
    dead = []
    with _http_lock:
        clients = list(_http_clients)
    for wfile in clients:
        try:
            wfile.write(msg)
            wfile.flush()
        except Exception:
            dead.append(wfile)
    if dead:
        with _http_lock:
            for w in dead:
                if w in _http_clients:
                    _http_clients.remove(w)


class _StateHTTPHandler(http.server.BaseHTTPRequestHandler):
    """v3.1 HTTP routes:

      /api/state                   — full pane-state JSON snapshot
      /api/stream                  — SSE feed of pane-state changes (1Hz)
      /api/pane/<pane_id>/todos    — proxy: full todo list for pane's session
      /api/pane/<pane_id>/messages — proxy: chat history (last 50 by default)
      /health                      — liveness probe (200 ok)

    The /api/pane/* routes are proxies that translate from pane_id → port +
    directory + session_id (which only the backend knows) so the UI doesn't
    need to know about OpenCode internals.

    URL-encode pane_id values containing % (e.g. "%1" → "%251").
    """

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _resolve_pane(self, pane_id: str):
        """Return (port, session_id, directory) for the given pane_id.
        Returns (0, "", "") if pane is unknown or has no agent.
        """
        with _live_lock:
            ls = _live.get(pane_id)
            if not ls or not ls.api_port:
                return 0, "", ""
            port = ls.api_port
            sid = ls.session_id

        directory = get_pane_directory(pane_id)
        # If we don't have a cached session_id yet, fetch one on-demand
        if not sid:
            sid = get_active_session_id(port, directory)
            if sid:
                with _live_lock:
                    if pane_id in _live:
                        _live[pane_id].session_id = sid
        return port, sid, directory

    def do_GET(self) -> None:
        from urllib.parse import urlparse, unquote

        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/state":
            data = _http_state_json.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif path == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            # Send current snapshot immediately so the client has data right away
            try:
                self.wfile.write(f"data: {_http_state_json}\n\n".encode())
                self.wfile.flush()
            except Exception:
                return
            with _http_lock:
                _http_clients.append(self.wfile)
            try:
                while True:
                    time.sleep(15)
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                with _http_lock:
                    if self.wfile in _http_clients:
                        _http_clients.remove(self.wfile)

        # ── agent-monitor feeds: files / activity / memory ──────────────
        # The flowchart dashboard (agent-monitor) builds its agent→folder→file
        # tree from these. They are produced as /tmp/gmuxtest-*.json by the
        # aggregate worker; here we simply serve the latest snapshot over HTTP
        # so browser/standalone mode works (Tauri mode uses events instead).
        elif path in ("/api/files", "/api/activity", "/api/memory"):
            feed_paths = {
                "/api/files": FILES_FILE,
                "/api/activity": ACTIVITY_FILE,
                "/api/memory": Path("/tmp/gmuxtest-memory.json"),
            }
            fpath = feed_paths[path]
            try:
                raw = fpath.read_text()
                data = raw.encode()
            except FileNotFoundError:
                # Empty default so the UI renders "no data" gracefully
                data = b"{}" if path == "/api/files" else b"[]"
            except Exception:
                data = b"{}" if path == "/api/files" else b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # ── v3.1: pane-scoped OpenCode proxies ──────────────────────────
        # Path: /api/pane/<urlencoded-pane-id>/todos
        # Path: /api/pane/<urlencoded-pane-id>/messages[?limit=N]
        elif path.startswith("/api/pane/"):
            parts = path[len("/api/pane/") :].split("/", 1)
            if len(parts) != 2:
                self._send_json({"error": "bad path"}, 400)
                return

            pane_id = unquote(parts[0])
            sub = parts[1]
            port, sid, directory = self._resolve_pane(pane_id)

            if not port or not sid:
                # Return an empty result so the UI can render "no data" gracefully
                # rather than treating this as a hard error.
                self._send_json({"pane_id": pane_id, "ok": False, "data": []})
                return

            if sub == "todos":
                todos = get_session_todos(port, sid, directory)
                self._send_json(
                    {
                        "pane_id": pane_id,
                        "session_id": sid,
                        "ok": True,
                        "data": todos,
                    }
                )

            elif sub.startswith("messages"):
                # parse ?limit=N (default 50, max 500)
                qs = parsed.query or ""
                limit = 50
                for kv in qs.split("&"):
                    if kv.startswith("limit="):
                        try:
                            limit = max(1, min(500, int(kv[6:])))
                        except ValueError:
                            pass
                msgs = get_session_messages(port, sid, directory, limit=limit)
                self._send_json(
                    {
                        "pane_id": pane_id,
                        "session_id": sid,
                        "ok": True,
                        "limit": limit,
                        "data": msgs,
                    }
                )

            else:
                self._send_json({"error": "unknown sub-route", "path": sub}, 404)

        elif path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:  # type: ignore[override]
        pass  # suppress per-request access logs


def start_http_server(port: int = 8769) -> None:
    """Start the HTTP state server in a background daemon thread.

    Uses ThreadingTCPServer so SSE long-poll connections don't block /api/state
    or /health requests — each connection gets its own thread.
    """
    try:
        # allow_reuse_address must be set BEFORE __init__ calls bind()
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        server = socketserver.ThreadingTCPServer(("0.0.0.0", port), _StateHTTPHandler)
        server.daemon_threads = True  # don't let handler threads block process exit
        t = threading.Thread(target=server.serve_forever, daemon=True, name="gmux-http")
        t.start()
        print(
            f"[monitor] HTTP state server on :{port}  — /api/state  /api/stream  /health",
            flush=True,
        )
    except OSError as e:
        print(f"[monitor] HTTP server failed to bind on :{port}: {e}", flush=True)


# ── Daemon ────────────────────────────────────────────────────────────────────


# ─── v3.1: session aggregate worker ──────────────────────────────────────────
# Periodically refreshes OpenCode token/cost/model aggregates for every known
# pane. We do this on a thread (not the main poll loop) because each refresh
# pulls the full message list, which can be slow on long sessions and would
# block the tmux poll.

AGGREGATE_INTERVAL = 10.0  # seconds between full refreshes per pane


def run_aggregate_worker() -> None:
    """Background worker that refreshes OpenCode session stats for all panes.

    Loops forever; each iteration:
      1. Snapshot the set of known pane_ids
      2. For each pane with an API port, refresh aggregate stats
      3. Sleep AGGREGATE_INTERVAL seconds
    """
    print(
        f"[gmuxtest-status] Aggregate worker started ({AGGREGATE_INTERVAL}s cycle)",
        flush=True,
    )
    while True:
        try:
            with _live_lock:
                pane_ids = [pid for pid, ls in _live.items() if ls.api_port]
            for pid in pane_ids:
                try:
                    refresh_session_aggregate(pid)
                except Exception as e:
                    # Per-pane failures should not kill the worker
                    print(
                        f"[gmuxtest-status] aggregate {pid}: {e}",
                        file=sys.stderr,
                    )
            # v3.7 — refresh auth expiry cache once per aggregate cycle.
            # This reads auth.json from disk (fast, ~1KB file) and updates
            # the module-level cache that poll_tmux() reads per-pane.
            try:
                _refresh_auth_expiry_cache()
            except Exception as e:
                print(f"[gmuxtest-status] auth expiry check: {e}", file=sys.stderr)
            # v3.7 — refresh /tmp/gmuxtest-memory.json from raw memory files.
            # Lazy-imported to keep the dependency optional and avoid slowing
            # cold startup. Failures are logged but never kill the worker.
            try:
                from memory_aggregator import aggregate_once as _memory_aggregate_once  # type: ignore

                _memory_aggregate_once()
            except Exception as e:
                print(f"[gmuxtest-status] memory aggregator: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[gmuxtest-status] aggregate worker: {e}", file=sys.stderr)
        time.sleep(AGGREGATE_INTERVAL)


def start_aggregate_worker() -> None:
    t = threading.Thread(
        target=run_aggregate_worker, daemon=True, name="gmux-aggregate"
    )
    t.start()


def run_daemon():
    print(f"[gmuxtest-status] Event-driven monitor → {STATE_FILE}", flush=True)
    print(f"[gmuxtest-status] SSE listeners + {POLL_INTERVAL}s tmux poll", flush=True)
    if not _HAS_PSUTIL:
        print(
            "[gmuxtest-status] WARNING: psutil not installed — "
            "RAM/CPU/uptime fields will be zero. Install with: pip install psutil",
            flush=True,
        )
    # Pre-load saved window names from disk so we restore them immediately
    _load_names_cache()
    # v3.7 — pre-load gmux-spawned sub-agent registry (best-effort at startup;
    # _pane_to_name may be empty here, but the registry will be resolved on
    # the first poll cycle once window names are discovered).
    _load_spawned_sub_agents()
    # v3.1: start the OpenCode aggregation worker in parallel
    start_aggregate_worker()
    cam_check_counter = 0
    while True:
        try:
            panes = poll_tmux()
            # v3.7 — refresh spawned sub-agent registry after tmux poll so that
            # _pane_to_name is populated when _load_spawned_sub_agents resolves
            # window_name → pane_id. This is the correct ordering: poll first,
            # then load the registry, then write state (which merges both).
            _load_spawned_sub_agents()
            if panes:
                write_state(panes)
            # v3.5 — emit the activity feed + derived file-touch map every cycle.
            # Cheap (read-only on the deque, ~500 entries max), so we do it every
            # tick rather than gating on a longer interval.
            write_activity()
            write_files()
            # Update camera status every 5 cycles (~10s) — no need for per-second systemctl
            cam_check_counter += 1
            if cam_check_counter >= 5:
                cam_check_counter = 0
                write_services(cam_broker_active())
        except Exception as e:
            print(f"[gmuxtest-status] Error: {e}", file=sys.stderr)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    # Set process name so it shows as gmux-monitor in htop/system monitor
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).parent.parent))
    try:
        from config import set_process_name  # type: ignore

        set_process_name("gmux-monitor")
    except Exception:
        pass

    if "--once" in sys.argv:
        panes = poll_tmux()
        if panes:
            write_state(panes)
        icons = {
            "not_started": "─",
            "waiting": "🔴",
            "working": "🟢",
            "permission": "🟠",
            "done": "🔵",
            "error": "❌",
            "idle": "🟡",
        }
        for p in sorted(panes, key=lambda x: x.window_index):
            icon = icons.get(p.state.value, "?")
            port_s = f":{p.api_port}" if p.api_port else " no-api"
            tool_s = f" [{p.current_tool}]" if p.current_tool else ""
            todo_s = f" {p.todo_done}/{p.todo_total}✓" if p.todo_total else ""
            print(
                f"  {icon} [{p.window_index}:{p.window_name}] → {p.state.value}{tool_s}{todo_s}  (port{port_s})"
            )
    else:
        start_http_server()  # binds port 8768 in a daemon thread before main loop
        run_daemon()
