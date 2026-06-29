# Agent Monitor — Backend Contract

How the dashboard reads data from the gmux backend.

---

## Data sources (file-based, always)

All written by `~/projects/gmux_v4/backend/status/monitor.py` to `/tmp/`.
The monitor.py process must be running for the dashboard to have any data.

### 1. `/tmp/gmuxtest-pane-state.json` — agent state

Updated every 2 seconds. Top-level shape:

```json
{
  "%5": {
    "pane_id":      "%5",
    "session_name": "gmux",
    "window_index": 3,
    "window_name":  "yuki",
    "cwd":          "/home/user/projects/yuki",
    "state":        "working",         // working|waiting|permission|sub_permission|idle|done|error|rate_limited|not_started
    "has_ai":       true,
    "foreground_cmd": "claude",        // claude|opencode|bun|fish|...
    "model":        "claude-sonnet-4-6",
    "provider":     "anthropic",
    "api_port":     34813,
    "ram_mb":       3010,
    "cpu_pct":      12.5,
    "uptime_s":     8725,
    "session_id":   "ses_xxx",
    "current_tool": "read_file",       // empty string when idle
    "tool_history": [
      {"tool":"read_file","path":"src/main.rs","ts":"2026-05-17T22:30:00Z"},
      {"tool":"edit_file","path":"src/main.rs","ts":"2026-05-17T22:30:14Z"}
    ],
    "todos": [
      {"content":"Implement foo","status":"completed"},
      {"content":"Test bar","status":"in-progress"}
    ],
    "todo_done":    1,
    "todo_total":   2,
    "token_in":     266651,
    "token_out":    484836,
    "last_line":    "Reading file: src/main.rs",
    "msg_count":    844,
    "session_age_s": 8725
  }
}
```

### 2. `/tmp/gmuxtest-files.json` — files touched

Updated every ~10 seconds. Top-level shape:

```json
{
  "/home/user/projects/yuki/src/main.rs": {
    "path":     "/home/user/projects/yuki/src/main.rs",
    "kind":     "rs",                    // file extension
    "touched_by": ["%5", "%3"],          // pane_ids
    "operations": [
      {"agent":"%5","tool":"read","ts":"..."},
      {"agent":"%5","tool":"edit","ts":"..."},
      {"agent":"%3","tool":"read","ts":"..."}
    ],
    "first_seen": "2026-05-17T22:25:00Z",
    "last_seen":  "2026-05-17T22:30:14Z",
    "hot_score":  0.85    // 0-1; high = touched by multiple agents recently
  }
}
```

### 3. `/tmp/gmuxtest-activity.json` — event timeline

Updated event-driven. Top-level shape:

```json
{
  "events": [
    {
      "ts":    "2026-05-17T22:30:14.123Z",
      "agent": "%5",
      "agent_name": "yuki",
      "tool":  "edit_file",
      "path":  "/home/user/projects/yuki/src/main.rs",
      "ok":    true
    },
    ...
  ],
  "version": 4
}
```

Newest events first. The array can hold up to 500 events; older ones
fall off.

### 4. `/tmp/gmuxtest-memory.json` — agent memory

Updated every 30 seconds. Used by V2 features (memory recall view):

```json
{
  "_schema_version": 1,
  "total_count": 8,
  "by_agent": {
    "%5": [{"kind":"episodic","text":"...","ts":"..."}],
    ...
  },
  "by_kind": {"episodic":2,"semantic":2,"procedural":2,"shared":2}
}
```

---

## Reading the data — three paths

### Path A: In a browser (workshop dev mode)

Use HTTP fetch to `monitor.py` directly:

```js
const r = await fetch('http://127.0.0.1:8769/api/state');
const panes = await r.json();
```

Available endpoints (all on :8769):
- `GET /health` → `"ok"`
- `GET /api/state` → same as `/tmp/gmuxtest-pane-state.json`
- `GET /api/stream` → SSE stream of state updates
- `GET /api/files` → same as `/tmp/gmuxtest-files.json`
- `GET /api/activity` → same as `/tmp/gmuxtest-activity.json`
- `GET /api/memory` → same as `/tmp/gmuxtest-memory.json`

### Path B: Embedded in Tauri (production)

Use Tauri events. The Rust process emits these to the `dashboard`
window every 1 second:

```js
const { listen } = window.__TAURI__.event;
await listen('gmux-state', e => {
  const panes = JSON.parse(e.payload);
  // update UI
});
await listen('files-update', e => {
  const files = JSON.parse(e.payload);
});
await listen('activity-tick', e => {
  const {events} = JSON.parse(e.payload);
});
await listen('memory-update', e => {
  const mem = JSON.parse(e.payload);
});
```

Detect mode:
```js
const isTauri = !!(window.__TAURI__ || window.__TAURI_INTERNALS__);
```

The existing `data.js` in this workshop already has the dual-path
detection; you can probably keep it.

### Path C: Mock data (for working without backend)

Sample data is in `reference/sample-data/` (TODO: add). Useful when
the backend is down or you don't want to spin it up.

---

## Filtering: "only running agents"

The spec says only show actively running agents. Definition:

```js
function isActive(pane) {
  // Active means: AI attached AND state indicates work or readiness
  if (!pane.has_ai) return false;
  const liveStates = ['working','waiting','permission','sub_permission','rate_limited','done'];
  return liveStates.includes(pane.state);
  // Note: 'idle' is excluded (plain shells), 'not_started' excluded.
  // 'done' is included so completed work stays visible for a moment.
}
```

For a hot-only view (only those currently doing something), restrict
to `working` + `permission` + `sub_permission` only.

---

## Backend availability checks

```js
async function checkBackend() {
  try {
    const r = await fetch('http://127.0.0.1:8769/health',
                          {signal: AbortSignal.timeout(1200)});
    return r.ok;
  } catch { return false; }
}
```

If down, show a friendly "monitor.py not running" placeholder with a
copy-paste command to start it:

```
python3.11 ~/projects/gmux_v4/backend/status/monitor.py
```

---

## Writing back to the backend (optional)

The dashboard is mostly read-only, but if you want clickable
interactions (e.g. select an agent → focus the corresponding tmux
pane in the main window), use Tauri invoke from inside the dashboard:

```js
const { invoke } = window.__TAURI__.core;
await invoke('select_pane', {paneId: '%5'});
// (the command would need to be implemented in lib.rs first)
```

For V1 keep it read-only. Interactive features are V2+.
