# Architecture diff — gmux-system vs maestro

Side-by-side comparison of how each system handles the same problems.

## How a new agent gets spawned

### gmux-system today (v3.7.0)

```
User press 'N' → createAgent(name, dir, type, model)
  │
  ▼
Tauri JS: window.__TAURI__.core.invoke('open_agent', ...)
  │
  ▼
Rust open_agent() in app/src-tauri/src/lib.rs:
  1. write "\x01c" to the EXISTING tmux PTY  ← spawns new tmux window
  2. sleep 300ms
  3. write "cd <dir> && opencode\r" to same PTY ← runs in new window
  4. sleep 200ms
  5. write "\x01,<name>\r" to rename
  6. write ":set-window-option automatic-rename off\r" lock
  │
  ▼
tmux server creates a window; bun/opencode/etc starts
  │
  ▼
monitor.py polls tmux every 2s → detects new window → writes pane-state.json
  │
  ▼
Rust state-poll thread reads pane-state.json → emits 'gmux-state' event
  │
  ▼
JS UI receives event → renders new pane in grid
```

**End-to-end latency:** ~3 seconds (tmux poll cycle). New pane appears in
the UI 2-4 seconds after Create button click.

### maestro

```
User clicks "+ new session" → createSession(...)
  │
  ▼
Tauri JS: invoke('spawn_shell', { cwd, env })
  │
  ▼
Rust spawn_shell() in process_manager.rs:
  1. native_pty_system().openpty(80x24) ← fresh PTY pair
  2. CommandBuilder spawns user's $SHELL
  3. Dedicated reader thread starts on the PTY
  4. Tokio batching task starts
  │
  ▼
Returns session_id (u32, monotonic)
  │
  ▼
JS: TerminalView mounts xterm.js, listens to `pty-output-{id}` event
  │
  ▼
Reader thread emits batched chunks every 16ms
  │
  ▼
xterm.js renders WebGL accelerated
```

**End-to-end latency:** <100ms. The terminal is interactive
immediately. There is no polling — output flows through events the
moment it appears.

---

## How output is captured

### gmux-system

- monitor.py polls tmux every 2s via `tmux capture-pane -p`
- Writes `last_line` to `/tmp/gmuxtest-pane-state.json`
- Rust re-emits as 'gmux-state' event
- UI shows the last line per pane card
- For full terminal output, we attach to a single PTY (`pty_writer`) per
  window and the user has to switch into that view to see scrollback

**Trade-off:** lightweight, polling-friendly, low Rust complexity. But:
- 2-second lag on state
- No live terminal-in-pane in the grid (the main UI shows summary cards)
- Output history is whatever tmux's own scrollback retains

### maestro

- Per-session PTY reader thread captures EVERY byte
- 16ms batching tokio task
- xterm.js receives raw bytes and renders them
- xterm.js's own buffer + WebGL handles scrollback

**Trade-off:** every keystroke and every output byte goes through IPC.
Higher memory (one Terminal instance per session). But:
- Live terminal in every grid cell
- Sub-50ms input latency
- True scrollback in xterm.js (configurable per OS)

---

## How sessions are tracked

### gmux-system

- The **tmux server** is the source of truth
- monitor.py polls it
- Writes flat JSON files in `/tmp/gmuxtest-*.json`
- Anything that wants session info reads these JSONs

### maestro

- **DashMap<u32, SessionConfig>** in Rust managed state (`SessionManager`)
- **DashMap<u32, PtySession>** in `ProcessManager`
- Frontend has a Zustand `useSessionStore` that mirrors backend
- Backend is the authoritative source

---

## How status is determined

### gmux-system

- monitor.py parses opencode SSE for `running` / `completed` / permission events
- Sets `PaneState` enum: working / waiting / permission / error / idle / done / rate_limited
- Writes to pane-state.json
- UI colour-codes pane dot

### maestro

- Three sources merge into the session status:
  1. **MCP callback** — Claude sessions can phone home with status updates via `MAESTRO_SESSION_ID` and the local status server
  2. **Activity heuristic** — JS in `TerminalView` watches for sustained PTY output; sets "Working" after 500ms of activity, "Idle" after 5s of silence
  3. **Manual override** — user can mark a session done
- 10-second MCP grace period: if MCP told us something recently, don't override with heuristic

Their MCP-callback approach is **more accurate** for Claude specifically;
ours is more flexible (works for any agent).

---

## How both handle "the agent is waiting for permission"

### gmux-system

- opencode emits a `permission_request` SSE event
- monitor.py sets `state = "permission"` + populates `pending_permission` blob
- UI shows orange border + permission card
- User clicks Approve → POST to opencode `/permission/allow`

### maestro

- Claude CLI prints something distinctive to stdout that the agent's MCP
  hook intercepts
- Hook calls `update_session_status` on the local status server with
  `NeedsInput`
- UI shows distinct border (red)
- User just types `y` into the terminal — no special UI action

Both work. Ours is more decoupled (no hooks needed); theirs is more
visually obvious.

---

## How both handle rate limiting

### gmux-system today

- v3.7.0 added detection via SSE 429, auth.json expiry, terminal regex
- Sets `state = "rate_limited"`, populates `rate_limit_until`,
  `rate_limit_msg`, `auth_expiring`, `auth_expired`
- UI shows badge + countdown

### maestro

- Polls `api.anthropic.com/api/oauth/usage` every 30s
- Caches result, shows daily/weekly progress bar in sidebar widget
- Click to toggle between 5-hour-session and 7-day-weekly view
- Doesn't detect mid-stream 429s (relies on the polled view)

**The two are complementary, not redundant.** We should keep our 429
detection AND add their `/api/oauth/usage` poll.

---

## How both handle the "Tauri Cmd vs Ctrl on macOS" issue

### gmux-system (v3.7.0)
- `cfg!(target_os = "macos")` branch in global-shortcut registration
- Cmd+Opt+D on macOS, Ctrl+Alt+D on Linux/Windows

### maestro
- Frontend uses `event.metaKey || event.ctrlKey` (accepts either)
- Per-key custom handler in xterm.js `attachCustomKeyEventHandler`
- Sends raw escape sequences for things webview swallows (Cmd+Arrow)

Their approach is more thorough for in-terminal keys; ours is more
opinionated.

---

## Platform support today

| Platform | gmux-system | maestro |
|---|---|---|
| Linux x86_64 | ✅ (daily driver) | ✅ |
| Linux arm64 | ⏳ untested | ✅ |
| macOS Apple Silicon | ❌ (Tauri runs, but tmux/PTY untested) | ✅ |
| macOS Intel | ❌ | ✅ |
| Windows 11 | ❌ (no tmux) | ✅ (ConPTY) |
| Headless VM | ✅ (backend only) | ❌ (needs display) |
| Browser mode | ✅ (point browser at :5550) | ❌ |
| Phone bridge | ⏳ designed, not built | ❌ |

**gmux's superpower** is the headless / browser / phone modes — we beat
maestro there. **Maestro's superpower** is direct OS coverage. The merger
would give us both.

---

## Code quality observations

### gmux-system
- monitor.py: 1500+ LOC Python, complex
- Rust app/src-tauri/src/lib.rs: ~1200 LOC, somewhat monolithic
- UI: index.html is a 8000+ line single file (deliberate, gesture+voice tightly coupled)
- 211 tests across 3 suites

### maestro
- Rust split across `commands/` (~12 files) and `core/` (~22 files)
- Each file 100-700 LOC, single responsibility
- 70% cohesion in major clusters per their docs
- 92% parse coverage (their own tooling number)
- Zero circular dependencies

We can learn from their modularisation. Our `lib.rs` is getting large.

---

## What this all means for the path forward

See `02_MIGRATION_PLAN.md` for the concrete proposal.

Two basic strategies:

**Path A** (small): cherry-pick maestro patterns into our existing
architecture. Bring the PTY core, the usage API, the rendering tricks.
Keep tmux as the orchestrator. Less risk, fewer benefits.

**Path B** (large): build `gmux-system-v2` (a new branch / sibling repo)
that uses maestro's PTY-first architecture, keeps our UI/voice/gesture
work, and treats tmux as an optional backend. More work, biggest payoff,
but the v1 stays running as a fallback for users on Linux who want the
remote backend.

I recommend **Path B**, done incrementally as a side-by-side build, with
the entire v3.7.0 system staying untouched and tagged so we never lose
what we have.
