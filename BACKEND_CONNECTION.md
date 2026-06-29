# gmux-system — Backend Connection Guide

**Last updated:** 2026-05-12 (v3.2)

This document explains exactly how the UI connects to the backend, what data
flows where, and how to diagnose connection failures.

---

## Architecture at a glance

```
                                                    ┌──────────────────┐
                                                    │ tmux session     │
                                                    │ "gmux"           │
   ┌───────────────────────────┐  reads via tmux    │  ├ window 1: bun │
   │ backend/status/monitor.py │ ────────────────►  │  ├ window 2: bun │
   │ Python daemon             │                    │  └ window N: ... │
   │ (1 process)               │  one SSE stream    └──────────────────┘
   │                           │  per opencode pane          │
   │                           │ ◄───────────────────────────┤
   │                           │                  ┌──────────▼─────────────┐
   │                           │                  │ Each opencode/bun pane │
   │                           │                  │ exposes a random HTTP  │
   │                           │                  │ port:                  │
   │                           │                  │   GET  /session        │
   │                           │                  │   GET  /session/:id/.. │
   │ writes every 2s ──┐       │                  │   GET  /event (SSE)    │
   │                   ▼       │                  │   POST /session/:id/   │
   │ /tmp/gmux-pane-state.json │                  │        prompt_async    │
   │                           │                  └────────────────────────┘
   │ serves HTTP on :8769      │
   │   /health                 │
   │   /api/state  (JSON)      │
   │   /api/stream (SSE)       │
   └──────┬──────────────┬─────┘
          │              │
   read   │              │ subscribe SSE
   /tmp   │              │
          ▼              ▼
   ┌─────────────┐  ┌──────────────────────────┐
   │ Tauri Rust  │  │ Browser / Phone PWA      │
   │ lib.rs      │  │ ui/v3/index.html         │
   │             │  │                          │
   │ poll 1Hz    │  │ initDataSource():        │
   │ emit JS     │  │  1. Tauri events         │
   │ event       │  │  2. HTTP :8769/api/stream│
   │ "gmux-state"│  │  3. HTTP polling fallback│
   └──────┬──────┘  │  4. Mock evolution       │
          │         └────────────┬─────────────┘
          ▼                      ▼
   ┌────────────────────────────────────────────┐
   │ ui/v3/index.html — gesture UI              │
   │ Renders agent grid, chat, todos, hardware  │
   └────────────────────────────────────────────┘
```

---

## Three connection modes

The UI's `initDataSource()` (line ~1810) tries these in order. The first that
succeeds wins. The status-bar indicator (`#sb-src`) tells you which mode is live.

### Mode 1 — Tauri events (when running inside Tauri)
- Tauri's Rust backend polls `/tmp/gmux-pane-state.json` every 1 second
- Emits a `gmux-state` Tauri event to the frontend
- UI listens via `window.__TAURI__.event.listen('gmux-state', ...)`
- **Indicator:** `● tauri live` (accent colour)
- **Detection:** `window.__TAURI_INTERNALS__` is set

### Mode 2 — HTTP + SSE (browser, monitor reachable)
- UI does `EventSource('http://127.0.0.1:8769/api/stream')`
- monitor.py pushes pane state JSON on every state change
- **Indicator:** `● live :8769` (accent colour)
- **Detection:** `GET /api/state` returns 200 within 1.5s

### Mode 3 — HTTP polling (SSE failed)
- UI polls `GET /api/state` every 2 seconds
- Used when EventSource open fails (rare; usually firewall or proxy)
- **Indicator:** `● live (poll)` (accent colour)

### Mode 4 — Mock fallback (no backend reachable)
- UI runs `startMockEvolution()` — fake data drift in `panes` object
- **Indicator:** `● mock` (muted grey)
- Why: lets the UI render even when working offline

---

## What the backend exposes

### `monitor.py` HTTP endpoints (port 8769)

| Method | Path | Returns | Used by |
|---|---|---|---|
| GET | `/health` | `ok` | UI startup probe |
| GET | `/api/state` | full pane state JSON object | initial load + polling fallback |
| GET | `/api/stream` | SSE stream — same JSON pushed on every change | UI live mode |
| GET | `/api/pane/<pid>/todos` | todos for one pane | future use |

CORS headers are set so the browser can fetch from any origin (typically
`http://localhost:5550`).

### Pane state JSON schema (per pane)

Every pane object has these keys (v3.2 — 27 fields):

```json
{
  "pane_id":            "%17",
  "session_name":       "gmux",
  "window_index":       3,
  "window_name":        "museall_image_visualiser",
  "pane_index":         1,
  "is_active":          true,
  "foreground_cmd":     "bun",
  "state":              "working",
  "has_ai":             true,
  "last_line":          "Edited foo.ts (+3 -1)",
  "api_port":           40167,
  "current_tool":       "edit",
  "todo_done":          7,
  "todo_total":         10,
  "todos":              [{"id": "1", "content": "...", "status": "completed"}, ...],
  "pane_left":          0,
  "pane_top":           0,
  "pane_width":         258,
  "pane_height":        62,
  "sub_agent_permission": false,
  "cwd":                "/home/fivelidz/projects/...",
  "tool_history":       ["edit", "bash", "grep"],
  "ram_mb":             381,
  "cpu_pct":            10.9,
  "uptime_s":           43920,
  "children":           [{"name": "node", "ram_mb": 124, "pid": 12345}],
  "session_id":         "ses_1ea889f01ffeQgD9...",
  "model":              "claude-sonnet-4-6",
  "provider":           "anthropic",
  "token_in":           6885306,
  "token_out":          39047,
  "token_reasoning":    0,
  "cost_usd":           0.0,
  "msg_count":          122
}
```

### How those fields get populated

| Field | Source | When |
|---|---|---|
| `pane_id`, `session_name`, `window_*`, `pane_*` | `tmux list-panes` | every 2s poll |
| `is_active`, `foreground_cmd` | tmux | every 2s |
| `state`, `current_tool` | opencode SSE `/event` stream | real-time |
| `todo_done`, `todo_total`, `todos` | opencode `/session/:id/todo` (REST) | every 8s aggregator |
| `model`, `token_*`, `cost_usd`, `msg_count` | opencode `/session/:id/message` (REST) | every 8s aggregator |
| `cwd`, `session_id` | tmux pane_current_path + opencode session list | every 2s |
| `ram_mb`, `cpu_pct`, `uptime_s`, `children` | psutil (Python lib) on bun PID tree | every 2s |
| `last_line` | `tmux capture-pane -p -t <pane>` last non-empty line | every 2s |
| `sub_agent_permission` | opencode `/session/:id` parentID check | when permission.updated fires |

### Tauri commands (UI → Rust)

Available via `window.__TAURI__.core.invoke('cmd_name', {...args})`:

| Command | Purpose |
|---|---|
| `pty_write(data)` | write bytes to the embedded tmux PTY |
| `pty_resize(cols, rows)` | resize PTY |
| `get_home_dir()` | returns `$HOME` |
| `get_pane_state()` | one-shot read of `/tmp/gmux-pane-state.json` |
| `get_services()` | one-shot read of `/tmp/gmux-services.json` |
| `open_aquarium()` / `hide_aquarium()` | toggle the (currently disabled) aquarium window |
| `open_project(path)` | new tmux window: `cd <path> && opencode` |
| `check_auth()` | does `~/.local/share/opencode/auth.json` exist? |
| `send_to_agent(port, session_id, dir, msg)` | POST a chat message to opencode |
| `open_agent(name, dir, type, model)` | spawn a new tmux window with chosen agent CLI |
| `approve_agent(port, sid, dir, win_idx)` | POST `/permission/allow` to opencode |
| `reject_agent(port, sid, dir, win_idx)` | POST `/permission/deny` to opencode |
| `restart_backend()` | re-spawn monitor + voice sidecars if dead |
| `backend_health()` | returns `{monitor, voice, state_fresh}` JSON |
| `get_opencode_sessions()` | sqlite3 dump of recent opencode sessions |

---

## Sidecar processes (auto-started by Tauri)

When Tauri starts, `spawn_sidecars()` looks up scripts in this order:
1. `~/projects/gmux-system/backend/{status,voice,session}/<name>.py`  ← preferred
2. `~/projects/gmuxtest/src-py/{status,voice,session}/<name>.py`        ← fallback
3. `~/projects/gmux/src/{status,voice}/<name>.py`                       ← legacy

Three sidecars:

| Script | Port | Purpose |
|---|---|---|
| `monitor.py` | 8769 (HTTP) | the daemon described above |
| `gmux_voice_daemon.py` | 8770 (WS) | faster-whisper STT, pushes transcripts to UI |
| `session_restore.py --daemon` | none | persists tmux window names to `/tmp/gmux-window-names.json` so they survive restart |

If a port is already bound, the sidecar is skipped (don't fight existing
instances). Each sidecar writes its stdout+stderr to `/tmp/<label>.log` for
debugging.

---

## Troubleshooting checklist

### "UI shows mock data even though backend should be running"

```bash
# 1. Is monitor listening?
ss -tlnp | grep 8769
# If no output: monitor is dead. Start it:
python3.11 ~/projects/gmux-system/backend/status/monitor.py &

# 2. Is /api/state returning data?
curl -s http://127.0.0.1:8769/api/state | python3 -m json.tool | head -30

# 3. Is the UI being served?
curl -I http://localhost:5550/v2/index.html   # 200 OK?

# 4. Does the UI hit the API? (open browser devtools Network tab)
# - look for /api/stream or /api/state requests
# - if blocked: check CORS — should already be wildcard "*"
```

### "Hardware tab is blank or pane fails to render"

In browser devtools console, look for `ReferenceError`. Most common past
cause: a variable name typo in the template literal in `updatePaneEl()`.
Recent fix (v3.2): `children.length` → `childrenSource.length`.

### "Tauri shows real data but is sluggish"

The Tauri WebView (WebKitGTK on Linux) has more rendering overhead than
Chromium/Brave. Mitigations:
- Test in browser instead: `./scripts/launch.sh --browser`
- Run a Tauri **production** build: `cd ~/projects/gmuxtest && npm run tauri build`
  then run the binary from `src-tauri/target/release/`
- Disable HMR by setting `GMUX_PROD=1` (currently not implemented; future work)

### "Todos appear on the wrong agent"

This can be legitimate: if two tmux panes attach to the same opencode session
(e.g. window 2 and window 8 both ran `qc` in the same directory), they share
state. Check `session_id` in `/api/state` — if two panes have identical
`session_id`, they're meant to share todos.

### "Voice daemon won't start"

```bash
# Check log
tail -30 /tmp/gmux-voice.log

# Common cause: missing Python deps
pip install faster-whisper sounddevice websockets numpy

# Or PulseAudio not running:
pulseaudio --check -v
```

---

## Connection lifecycle (when you start the app)

```
t = 0.0   User runs ./scripts/launch.sh
t = 0.1   launch.sh starts monitor.py if :8769 not bound
t = 1.0   monitor.py: imports done, HTTP server bound
t = 1.5   launch.sh starts gmux_voice_daemon.py if :8770 not bound
t = 1.5   monitor.py first poll_tmux() — discovers panes
t = 2.0   monitor.py first SSE subscribers attached to opencode instances
t = 3.5   monitor.py first aggregator pass — fills model/tokens for all panes
t = 4.0   launch.sh starts Tauri (npm run tauri dev) or browser server
t = 4.5   Tauri/browser loads index.html
t = 5.0   UI's initDataSource() tries Tauri → HTTP → mock
t = 5.5   First state event lands → render() draws real data
```

If anything fails between t=1.0 and t=3.5, the UI falls through to mock mode
and the status bar shows `● mock`. Click the red "restart" button (or just
restart the launcher) and watch `/tmp/gmux-monitor.log` for errors.
