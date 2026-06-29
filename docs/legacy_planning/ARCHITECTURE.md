# Architecture

How gmux-v4 — the **all-in-one successor to gmux-system v3** — is
structured. One repo, one binary, one in-process state store, minimal
external moving parts.

For the detailed agent-handling design (state machine, todos, activity,
persistence), see [`AGENT_LIFECYCLE.md`](AGENT_LIFECYCLE.md).

---

## System diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                         gmux-v4 Tauri process                          │
│                          (one binary, one PID)                         │
│                                                                        │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │            Webviews (managed by Tauri, all in-process)       │     │
│   │                                                              │     │
│   │  ┌──────────────────────────────────────────────────────┐    │     │
│   │  │ "main" window  — pane grid + gesture + voice         │    │     │
│   │  │   ui/index.html (lifted from gmux-v3, adapted)       │    │     │
│   │  └──────────────────────────────────────────────────────┘    │     │
│   │  ┌──────────────────────────────────────────────────────┐    │     │
│   │  │ "dashboard" window  — Agent Monitor (Ctrl+Alt+D)     │    │     │
│   │  │   ui/dashboard/index.html (lifted from gmux-v3)      │    │     │
│   │  └──────────────────────────────────────────────────────┘    │     │
│   └──────────────────────────────────────────────────────────────┘     │
│                              │                                         │
│                Tauri IPC (invoke + emit/listen)                        │
│                              │                                         │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │                 Rust core (src-tauri/src/)                   │     │
│   │                                                              │     │
│   │   Managed state (DashMaps, all hot-path lock-free):          │     │
│   │   ┌──────────────────────────────────────────────────────┐   │     │
│   │   │ ProcessManager      DashMap<u32, PtySession>         │   │     │
│   │   │ AgentManager        DashMap<u32, Agent>              │   │     │
│   │   │ TodoStore           DashMap<u32, Vec<Todo>>          │   │     │
│   │   │ ActivityLog         VecDeque<ActivityEvent> + mutex  │   │     │
│   │   │ FileTouchMap        DashMap<PathBuf, FileTouches>    │   │     │
│   │   │ SubAgentRegistry    DashMap<u32, SubAgentLink>       │   │     │
│   │   │ PermissionStore     DashMap<u32, Permission>         │   │     │
│   │   │ UsageCache          ProviderUsage with 30s TTL       │   │     │
│   │   │ EventBus            tokio::broadcast per stream      │   │     │
│   │   └──────────────────────────────────────────────────────┘   │     │
│   │                                                              │     │
│   │   Background tasks (tokio):                                  │     │
│   │   - per-session PTY reader threads + emit batcher (16ms)     │     │
│   │   - per-agent opencode SSE listener (when applicable)        │     │
│   │   - 30s usage poller → emit usage-update                     │     │
│   │   - 5s state snapshot to SQLite (debounced)                  │     │
│   │   - phone bridge: WS server :8767 + HTTP :8768               │     │
│   │   - headless mode: HTTP UI on :5550 (when --headless)        │     │
│   │                                                              │     │
│   │   Persistence layer:                                         │     │
│   │   - SQLite at ~/.local/share/gmux/state.db                   │     │
│   │   - rusqlite + r2d2 connection pool                          │     │
│   │   - autosave on event-bus subscription                       │     │
│   └──────────────────────────────────────────────────────────────┘     │
│                                                                        │
│   No tmux. No monitor.py. No /tmp/*.json files except optional         │
│   compatibility output for old gmux-phone clients.                     │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ (optional, opt-in)
                                  ▼
                        ┌──────────────────────┐
                        │  voice_daemon.py     │
                        │  (lifted from v3)    │
                        │  WS :8770            │
                        └──────────────────────┘

                                  │
                                  │ (optional, when phone is paired)
                                  ▼
                        ┌──────────────────────┐
                        │   gmux-phone PWA     │
                        │   ws://host:8767     │
                        └──────────────────────┘
```

---

## Why this is "minimal-fuss"

Compared to v3's architecture, v4 eliminates:

| v3 thing | v4 replacement |
|---|---|
| `monitor.py` polling `/tmp/gmuxtest-*.json` every 2s | Event-driven in-process state, < 50ms |
| Two processes racing on the same JSON | One process, lock-free DashMap |
| `tmux send-keys` for everything | Direct PTY writes via `ProcessManager` |
| opencode SSE in Python, then re-emit via Tauri | opencode SSE in Rust, emit directly to webview |
| `monitor.py` + `voice_daemon.py` + Rust + tmux server | One Rust process + optional voice sidecar |
| `setsid` / `nohup` to keep monitor alive across SSH | Tauri owns its own lifecycle |
| State file race conditions on writes | SQLite WAL handles concurrent reads/writes |
| Tracking todos in markdown | First-class `Todo` struct, persisted |

---

## Layer responsibilities

### Frontend (HTML/JS in webview)

- **Rendering** — pane grid with xterm.js per pane, modals, toolbars
- **Input** — keyboard, mouse, voice, gesture
- **Subscription** — `listen('agent-update-{id}', cb)` etc.
- **No state** — all source-of-truth lives in Rust; UI is a view

The v3 UI HTML is **lifted essentially unchanged**. Only the IPC
function names are remapped (see `FROM_V3.md`).

### Tauri / IPC layer

- Routes `invoke('cmd', args)` to Rust command handlers
- Broadcasts `emit('event', payload)` from background tasks to webviews
- Manages windows (main + dashboard + future expansion)
- Registers global shortcuts (`Ctrl+Alt+D` for dashboard, etc.)
- Loads plugins (opener, global-shortcut)

### Rust core

The heart of v4. Responsibilities:

1. **PTY ownership** — every shell is a `portable_pty` instance owned
   by `ProcessManager`. No FD ever leaves Rust.
2. **Agent abstraction** — `AgentManager` wraps PTY sessions with
   semantic state (todos, activity, permissions). Agents are what
   the UI mostly cares about; PTYs are an implementation detail.
3. **Event broadcasting** — every state change fires a tokio broadcast
   event. The webview + the bridge + the persistence layer are all
   subscribers.
4. **Background polling** — when an opencode session is detected, a
   tokio task subscribes to its SSE stream and updates state.
5. **Usage tracking** — 30s poll of `api.anthropic.com/api/oauth/usage`
   with TTL cache.
6. **Persistence** — SQLite-backed state survives app restart.
7. **Phone bridge** — WS server in the same process implementing the
   v3 contract.
8. **Headless mode** — when `--headless` is passed, the Tauri window
   is skipped; only the HTTP/WS servers come up.

### Optional sidecars

These are **not started by v4** but are auto-detected and used if running:

- **Voice daemon** (`backend/voice_daemon.py`, lifted from v3): WS
  on `:8770`. v4 connects if available, falls back to Web Speech API.
- **Anything else from v3** running in `~/projects/gmux-system/backend/`
  for users mid-migration.

These are optional installs. The voice sidecar is documented but not
shipped in the v4 installer initially (it's a separate `pip install`
step the user does once).

---

## Module map (Rust)

```
src-tauri/src/
├── main.rs                        ← gmux_v4_lib::run()
├── lib.rs                         ← Tauri builder, managed state, invoke_handler
│
├── core/
│   ├── mod.rs
│   ├── error.rs                   ← PtyError, AgentError, BridgeError enums
│   ├── event_bus.rs               ← broadcast channels per stream
│   ├── process_manager.rs         ← PTY spawn/read/write/kill (lifted from maestro)
│   ├── utf8_decoder.rs            ← Stateful split-byte handling (maestro)
│   ├── agent_manager.rs           ← Agent struct + DashMap + state machine
│   ├── todo_store.rs              ← Todo CRUD + persistence
│   ├── activity_log.rs            ← Circular buffer + queries
│   ├── file_touches.rs            ← Per-file touch heatmap
│   ├── permission_store.rs        ← Pending permissions registry
│   ├── sub_agent_registry.rs      ← Parent/child links
│   ├── usage_cache.rs             ← Provider usage with TTL
│   ├── opencode_sse.rs            ← per-agent SSE listener
│   └── persistence/
│       ├── mod.rs
│       ├── db.rs                  ← rusqlite pool + migrations
│       ├── migrations/            ← versioned schema
│       └── autosave.rs            ← debounced writers
│
├── commands/
│   ├── mod.rs
│   ├── terminal.rs                ← spawn_shell, write_stdin, resize, kill_session
│   ├── agent.rs                   ← spawn_agent, kill_agent, rename, list_agents
│   ├── sub_agent.rs               ← spawn_sub_agent, kill_sub_agent_tree
│   ├── todo.rs                    ← add_todo, set_todo_done, list_todos
│   ├── activity.rs                ← get_activity, get_agent_activity
│   ├── permission.rs              ← approve, reject, set_auto_approve
│   ├── usage.rs                   ← get_claude_usage (lifted from maestro)
│   ├── auth.rs                    ← list_providers, login_provider, logout_provider
│   ├── windows.rs                 ← open_dashboard, focus_main
│   ├── bridge.rs                  ← phone WS server commands
│   └── headless.rs                ← --headless mode HTTP/WS
│
└── ui_hosting/
    ├── mod.rs
    └── http_server.rs             ← serves ui/ over HTTP when --headless
```

---

## Critical data flows

### Spawning an agent

```
User: clicks "+ new agent" → opens modal → submits
  │
  ▼
JS: invoke('spawn_agent', {
       name: "claude in my-app",
       agent_type: "Claude",
       cwd: "~/projects/my-app",
       model: "claude-sonnet-4.5",
       parent_id: null
     })
  │
  ▼
Rust commands::agent::spawn_agent()
  → AgentManager.spawn(config)
    → ProcessManager.spawn_shell(cwd, env)  → session_id (PTY live)
    → Build Agent { id, state: Starting, ... }
    → agents.insert(id, agent)
    → tokio::spawn(opencode_sse::listen(id))     // background SSE if Claude/OpenCode
    → tokio::spawn(pty_watcher::analyse(id))     // background pattern matching
    → EventBus.agent_updates.send(AgentUpdate::Created(id))
    → If parent_id: SubAgentRegistry.insert + emit subagent-tree-changed
    → persistence::autosave.queue(id)
    → Return Ok(id)
  │
  ▼
JS: receives Ok(id)
JS: renders new pane in grid, mounts xterm.js, calls
    spawnShell internally to bind xterm.js to session
JS: types the agent launch command into PTY (e.g. "claude --model ...\n")
  │
  ▼
PTY: agent boots; output flows
  - ProcessManager reader → 16ms batching → emit pty-output-{session_id}
  - opencode_sse picks up tool_start events → ActivityLog.push + AgentManager.set_state
  - All subscribers (UI, dashboard, bridge, persistence) get events
```

Latency: spawn_agent → first Render: < 100ms.
Latency: PTY byte → screen: < 50ms p95.

### Activity flow (e.g. agent reads a file)

```
Agent (Claude) calls Read("auth.py")
  │
  ▼
opencode emits message.part.updated with tool="Read", status="running"
  │
  ▼
Rust opencode_sse listener catches event
  → ActivityLog.push(ActivityEvent { kind: ToolStart { tool: "Read", args }, ... })
  → AgentManager.update(id, |a| a.current_tool = Some("Read"); a.state = Working)
  → FileTouchMap.touch(path, agent_id, kind: Read)
  → EventBus.activity.send(ev)
  → EventBus.agent_updates.send(AgentUpdate::StateChanged(id, Working))
  │
  ▼
ALL subscribers fire simultaneously:
  → main window's xterm pane updates its status dot (yellow)
  → dashboard window adds a green edge agent→file in flowchart
  → phone WS pushes status update
  → persistence writes ActivityEvent to SQLite (batched 1s)
```

No polling. No JSON files. Sub-50ms end-to-end.

### Todo update (agent ticks one off)

```
Agent: emits todo_update SSE event with done: true
  │
  ▼
opencode_sse listener catches it
  → TodoStore.set_done(agent_id, todo_id, true)
  → EventBus.todo_updates.send(TodoUpdate { agent_id, todo_id, done: true })
  → persistence::autosave.queue_todo(agent_id, todo_id)
  │
  ▼
JS receives event, UI checkbox ticks
Phone receives same event, ticks its checkbox too
SQLite write happens in background, never blocks the event path
```

### Persistence — app restart

```
gmux-v4 binary starts
  │
  ▼
Rust core::persistence::db::init()
  → Open ~/.local/share/gmux/state.db (create if missing)
  → Run pending migrations in order
  → SELECT agents WHERE ended_at IS NULL
    → For each: try to re-attach (most will fail; PTY died with old process)
    → If can't re-attach: UPDATE agents SET ended_at = now WHERE id = ?
    → Load todos, activity (last 500), sub-agent links into memory
  → SELECT * FROM usage_history WHERE hour_bucket = current_hour
    → Seed usage_cache
  │
  ▼
Tauri window opens; UI does invoke('list_agents')
  → Returns the surviving agents (mostly empty for fresh start; full for warm restart)
  │
  ▼
UI renders the grid with carried-over state. Todos still visible.
Recent activity still showing.
```

Even though PTYs don't survive app restart (a v4.0 limitation), all
the **work** survives — todos ticked, files touched, activity history.
Users can pick up exactly where they left off.

---

## Headless mode

When started with `--headless`:

```bash
gmux-v4 --headless
```

- No Tauri window created
- HTTP UI server starts on `:5550` serving `ui/`
- WS phone bridge starts on `:8767`
- HTTP API starts on `:8769` (subset of the Tauri commands as REST endpoints)
- Process stays alive until SIGTERM

Use case: server install. Browser/phone connects from anywhere on the
network. Replaces v3's `monitor.py + python -m http.server` combo with
a single binary.

---

## Cross-platform concerns

| Concern | Linux | macOS | Windows |
|---|---|---|---|
| PTY | POSIX (portable-pty) | POSIX (portable-pty) | ConPTY (portable-pty) |
| Shell | `$SHELL` -l | `$SHELL` -l | `%COMSPEC%` |
| Process group | kill(-pgid, SIGTERM) | kill(-pgid, SIGTERM) | taskkill /T /F |
| Locale | LANG fallback | LANG fallback | ConPTY-internal |
| Credential store | Secret Service (D-Bus) | Keychain (`security` CLI) | Credential Manager |
| Browser-open | `xdg-open` via tauri-plugin-opener | `open` | `start` |
| Global shortcut Mod | Ctrl | Cmd (cfg!) | Ctrl |
| Audio backend (voice) | PulseAudio | CoreAudio | WASAPI |
| Default install location | `~/.local/share/gmux/` | `~/Library/Application Support/gmux/` | `%APPDATA%\gmux\` |
| SQLite path | `~/.local/share/gmux/state.db` | `~/Library/Application Support/gmux/state.db` | `%APPDATA%\gmux\state.db` |

All cross-platform path handling goes through `directories` crate.

---

## What we explicitly do NOT do

| Don't | Why |
|---|---|
| Have a separate Python backend | One process owns the state |
| Sync state through `/tmp/*.json` files | Event bus does it in-process |
| Poll for state changes | Subscribe to event bus |
| Use tmux | portable-pty is enough and cross-platform |
| Embed an MCP server | We use opencode's SSE + our activity log |
| Have a web framework on the frontend | The v3 vanilla-JS UI is sufficient |
| Persist PTY processes across app restart | Out of scope; agents are short-lived |
| Add a plugin system | YAGNI for v4.0 |

---

## Threading model

```
main thread:
  - Tauri runtime
  - WebView event loop

tokio multi-thread runtime:
  - command handlers (lightweight, mostly await DashMap ops)
  - per-session PTY reader (one std::thread per PTY for blocking read)
  - per-session PTY emitter task (one tokio task batches reader output)
  - per-agent opencode SSE listener (one tokio task)
  - usage poller (one tokio task, every 30s)
  - persistence autosave loop (one tokio task, every 5s)
  - phone bridge accept loop + per-connection task
  - headless HTTP server (axum or hyper, when --headless)
```

DashMap is lock-free for reads and shard-locked for writes — perfect
for the high-fan-out read pattern (every webview subscriber + bridge +
persistence reads on every event).

---

## See also

- [`AGENT_LIFECYCLE.md`](AGENT_LIFECYCLE.md) — agent state machine, todos, activity in detail
- [`FROM_V3.md`](FROM_V3.md) — what to lift from gmux-system v3
- [`FROM_MAESTRO.md`](FROM_MAESTRO.md) — what to lift from maestro
- [`PHASES.md`](PHASES.md) — implementation phases with acceptance criteria
- [`TODO.md`](TODO.md) — granular tasks
