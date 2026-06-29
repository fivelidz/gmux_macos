# TODO — concrete task list

The granular list of things to do, ordered by phase. Each task is sized
to "one focused work session" or smaller.

**Last refreshed:** see `AGENT_HANDOFF.md` for the most recent timestamp.

Tasks are marked:
- `[ ]` — not started
- `[~]` — in progress (note who/when in inline comment)
- `[x]` — done
- `[!]` — blocked (note reason in inline comment)
- `[?]` — needs research before doing

When you pick up a task, change `[ ]` to `[~] @your-handle 2026-MM-DD`.
When you finish, change to `[x]` and add a brief note.

---

## Phase −1 — Documentation ✅ DONE

- [x] README.md
- [x] docs/OBJECTIVES.md (rewritten to reflect successor scope)
- [x] docs/ARCHITECTURE.md (rewritten with state-store-centric design)
- [x] docs/AGENT_LIFECYCLE.md (new — core spec for agent handling)
- [x] docs/PHASES.md (8 phases, ending at v1.0.0)
- [x] docs/TODO.md (this file)
- [x] docs/CONTRIBUTING.md
- [x] docs/AGENT_HANDOFF.md
- [x] docs/FROM_V3.md
- [x] docs/FROM_MAESTRO.md
- [x] LICENSE (MIT)
- [x] .gitignore
- [x] git init + first commit
- [x] Push to GitHub as PRIVATE repo `fivelidz/gmux-v4`
- [x] Tag: `v0.0.0-docs`

---

## Phase 0 — Scaffold

### Root config
- [ ] `package.json` with deps (`@tauri-apps/cli ^2`, `@tauri-apps/api ^2`,
      `@xterm/xterm`, `@xterm/addon-fit`, `@xterm/addon-webgl`,
      `@xterm/addon-canvas`, `@xterm/addon-unicode11`,
      `@xterm/addon-web-links`, `vite ^5`)
- [ ] `vite.config.js` on port 5180
- [ ] `tsconfig.json` (minimal, ESM)

### Rust scaffold
- [ ] `src-tauri/Cargo.toml` with maestro-equivalent deps
  - `tauri = "2"` with `devtools` feature
  - `tauri-plugin-opener = "2"`, `tauri-plugin-global-shortcut = "2"`
  - `portable-pty = "0.8"`
  - `tokio = { version = "1", features = ["rt-multi-thread", "macros", "sync", "time", "process"] }`
  - `dashmap = "5"`, `serde`, `serde_json`, `thiserror`, `log`, `env_logger`
  - `reqwest` (rustls-tls), `keyring = "3"`, `directories = "5"`, `uuid`
  - `[target.'cfg(unix)'.dependencies] libc = "0.2"`
- [ ] `src-tauri/build.rs` calling `tauri_build::build()`
- [ ] `src-tauri/tauri.conf.json` — main window 1400×900, dev URL `http://127.0.0.1:5180`
- [ ] `src-tauri/capabilities/default.json` — allow `core:default`,
      `opener:default`, `global-shortcut:default`
- [ ] `src-tauri/icons/` placeholder icons (use Tauri's default for now)
- [ ] `src-tauri/src/main.rs` calling `gmux_v4_lib::run()`
- [ ] `src-tauri/src/lib.rs` minimal `run()` with one `ping` command

### Frontend scaffold
- [ ] `index.html` minimal with `<script type="module" src="/src/main.ts">`
- [ ] `src/main.ts` calls `invoke('ping')`, logs result

### Smoke test
- [ ] `npm install` completes
- [ ] `npm run tauri:dev` opens a window showing "ping ok"
- [ ] `cargo check` on src-tauri produces ZERO warnings
- [ ] Commit + tag `v0.1.0-scaffold`

---

## Phase 1 — PTY core (Linux)

### Lift maestro files
Source paths (read-only on this machine):
`/home/fivelidz/projects/github_repos/maestro/src-tauri/src/`

- [ ] Copy `core/process_manager.rs` → `src-tauri/src/core/process_manager.rs`
  - Find/replace: `MAESTRO_SESSION_ID` → `GMUX_SESSION_ID`
  - Find/replace: `MAESTRO_PROJECT_HASH` → `GMUX_PROJECT_HASH`
  - Find/replace: `CLAUDECODE` env_remove — keep as-is (still useful)
  - Keep windows DSR handling intact
  - Keep `Utf8Decoder` inside this file, OR split into `core/utf8_decoder.rs`
- [ ] Copy `core/terminal_backend.rs` → `src-tauri/src/core/terminal_backend.rs`
  - Update `use super::PtyError` if module path differs
- [ ] Copy `core/session_manager.rs` → `src-tauri/src/core/session_manager.rs`
  - Adjust `AiMode` enum:
    - Add `Aider`, `QalCode`
    - Rename `Plain` → `Terminal` (matches v3 vocabulary)
- [ ] Copy `core/error.rs` → `src-tauri/src/core/error.rs`
  (define `PtyError` enum with `spawn_failed`, `write_failed`, `resize_failed`,
  `session_not_found`, `id_overflow`)
- [ ] Create `src-tauri/src/core/mod.rs`:
  ```rust
  pub mod error;
  pub mod process_manager;
  pub mod session_manager;
  pub mod terminal_backend;
  pub mod utf8_decoder;
  pub use error::PtyError;
  pub use process_manager::ProcessManager;
  pub use session_manager::SessionManager;
  pub use terminal_backend::{BackendType, BackendCapabilities};
  ```

### Tauri commands
- [ ] Copy `commands/terminal.rs` → `src-tauri/src/commands/terminal.rs`
  - Keep: `spawn_shell`, `write_stdin`, `resize_pty`, `kill_session`,
    `kill_all_sessions`, `get_backend_info`, `check_cli_available`,
    `save_pasted_image`
  - Drop: `get_session_process_tree`, `get_all_process_trees`,
    `kill_process` (we don't need their git-worktree-aware versions)
- [ ] Create `src-tauri/src/commands/mod.rs` exporting `pub mod terminal;`

### Wire to lib.rs
- [ ] `src-tauri/src/lib.rs` registers `ProcessManager`, `SessionManager`
- [ ] `invoke_handler!` lists every terminal command

### Frontend bindings
- [ ] `src/lib/pty.ts` with:
  ```ts
  export async function spawnShell(cwd?: string, env?: Record<string,string>): Promise<number>
  export async function writeStdin(sessionId: number, data: string): Promise<void>
  export async function resizePty(sessionId: number, rows: number, cols: number): Promise<void>
  export async function killSession(sessionId: number): Promise<void>
  export function onPtyOutput(sessionId: number, cb: (data: string) => void): Promise<UnlistenFn>
  ```

### Smoke test page
- [ ] Replace minimal `index.html` with a stripped layout:
  - "Spawn Shell" button
  - One full-window xterm.js Terminal div
  - Bind it to a fresh PTY session on click
- [ ] Verify the 7 acceptance criteria from PHASES.md § Phase 1

### Tests
- [ ] `src-tauri/src/core/utf8_decoder.rs` — write a unit test for split
      multi-byte (matches maestro's existing tests if present)
- [ ] Commit + tag `v0.2.0-pty-linux`

---

## Phase 2 — Agent layer + state stores

This is the big one. Subdivide.

### 2a — Agent abstraction (struct + DashMap + state machine)
- [ ] `core/agent_manager.rs` — define `Agent` struct per AGENT_LIFECYCLE.md
- [ ] `AgentState` enum: Starting / Working / Idle / NeedsInput / Done / Error / RateLimited
- [ ] `AgentManager` struct holding `DashMap<u32, Agent>` + atomic id counter
- [ ] `AgentManager::spawn(SpawnConfig) -> u32` wraps `ProcessManager::spawn_shell`
- [ ] `AgentManager::update(id, |&mut Agent| ...)` helper
- [ ] `AgentManager::set_state(id, new_state)` emits AgentUpdate
- [ ] `AgentManager::kill(id)` chains to ProcessManager + sets state Done

### 2b — Event bus
- [ ] `core/event_bus.rs` — `EventBus` struct
- [ ] `tokio::broadcast::Sender` per stream:
      `agent_updates`, `activity`, `todos`, `permissions`, `usage`, `subagent_tree`
- [ ] Subscription helpers: `bus.agents().subscribe() -> Receiver`
- [ ] Register `EventBus::new()` in Tauri managed state
- [ ] Tauri commands forward broadcast messages to webview via `app_handle.emit()`

### 2c — Todo store
- [ ] `core/todo_store.rs` — `Todo` struct + `TodoStore` (DashMap<u32, Vec<Todo>>)
- [ ] `TodoStore::add`, `set_done`, `delete`, `reorder`, `list_for_agent`
- [ ] Every mutation emits `TodoUpdate` on the event bus
- [ ] `commands/todo.rs` Tauri command surface

### 2d — Activity log
- [ ] `core/activity_log.rs` — `ActivityEvent` + `ActivityLog`
- [ ] Internal: `Mutex<VecDeque<ActivityEvent>>` capped at 500
- [ ] Methods: `push`, `last(n)`, `by_agent(id)`, `by_kind(k)`, `between(t1,t2)`
- [ ] `commands/activity.rs` exposes queries to UI

### 2e — File touch map
- [ ] `core/file_touches.rs` — `FileTouches` per path; `FileTouchMap`
- [ ] Methods: `touch(path, agent_id, kind)`, `list_hot(n)`, `conflicts()`
- [ ] Emits `FileTouchUpdate` events

### 2f — Sub-agent registry
- [ ] `core/sub_agent_registry.rs` — `SubAgentLink` + DashMap
- [ ] `register_child(parent_id, child_id, prompt)`
- [ ] `children_of(parent_id) -> Vec<u32>`, `parent_of(child_id) -> Option<u32>`
- [ ] Emits `SubAgentTreeUpdate` events

### 2g — Permission store
- [ ] `core/permission_store.rs` — `Permission` + DashMap<agent_id, Permission>
- [ ] `register(agent_id, permission)`, `clear(agent_id)`
- [ ] `commands/permission.rs`: approve, reject, list_pending, set_auto_approve

### 2h — Persistence layer
- [ ] `core/persistence/db.rs` — rusqlite + r2d2 connection pool
- [ ] `core/persistence/migrations/` — SQL files versioned `001_init.sql` etc.
- [ ] First migration creates all tables per AGENT_LIFECYCLE.md schema
- [ ] `core/persistence/autosave.rs` — debounced writers subscribing to event bus
- [ ] On startup: load surviving state into memory

### 2i — Tauri commands for agents
- [ ] `commands/agent.rs` — `spawn_agent`, `kill_agent`, `rename_agent`,
      `mark_agent_done`, `list_agents`, `get_agent`
- [ ] `commands/sub_agent.rs` — `spawn_sub_agent`, `list_sub_agents`,
      `kill_sub_agent_tree`

### 2j — Smoke UI for the agent layer
- [ ] Page lists active agents (live-updating via event subscription)
- [ ] "Spawn agent" button → creates one via `spawn_agent`
- [ ] Click an agent → shows todos + recent activity for that agent
- [ ] Add/remove todos via UI
- [ ] Kill agent → row disappears

### Acceptance criteria (Phase 2)
- [ ] All sub-tasks above complete
- [ ] Unit tests for each manager (TodoStore, ActivityLog, etc.)
- [ ] App restart restores agents (without PTYs), todos, activity, sub-agent links
- [ ] No `unwrap()` in non-test code
- [ ] `cargo check` zero warnings
- [ ] Tag: `v0.3.0-agent-layer`

---

## Phase 3 — opencode SSE listener + usage tracking

### opencode SSE
- [ ] `core/opencode_sse.rs` — `OpencodeSseListener` per agent
- [ ] On agent spawn (if agent_type uses opencode): start listener as tokio task
- [ ] Detects opencode HTTP port from agent's spawned port (poll-then-watch)
- [ ] Subscribes to `/event` endpoint via SSE
- [ ] Parses `message.part.updated` → updates AgentManager + ActivityLog +
      TodoStore + PermissionStore + FileTouchMap
- [ ] Reconnects on disconnect with exponential backoff

### Anthropic usage API
- [ ] Copy `commands/usage.rs` from
      `~/projects/github_repos/maestro/src-tauri/src/commands/usage.rs`
- [ ] Adapt to use our event bus (emit `UsageUpdate` events)
- [ ] `core/usage_cache.rs` — 30s TTL cache; 429 → cache for retry-after
- [ ] Background tokio task: poll every 30s
- [ ] Surfaces in toolbar via UI subscription to `usage-update` event

### Acceptance criteria
- [ ] Spawning Claude agent triggers SSE listener
- [ ] Tool calls populate ActivityLog (visible in smoke UI)
- [ ] Permission requests put agent in NeedsInput state
- [ ] Todos from opencode appear in TodoStore
- [ ] Usage badge shows "Daily X%" after 30s
- [ ] Click toggles to "Weekly X%"
- [ ] Token expired: badge shows "🔑 Connect Claude"
- [ ] Tag: `v0.4.0-sse-usage`

---

## Phase 4 — Full v3 UI integration

### 4a — Lift UI files
- [ ] Copy `~/projects/gmux-system/ui/v3/index.html` → `ui/index.html`
- [ ] Copy `~/projects/gmux-system/app/src/dashboard/` → `ui/dashboard/`
- [ ] Copy `~/projects/gmux-system/models/hand_landmarker.task` → `assets/`
- [ ] Configure Vite to serve `ui/index.html` as root
- [ ] Verify the UI loads in the Tauri window

### 4b — Per-pane xterm.js
- [ ] Replace v3's mock pane content with real Terminal per pane
- [ ] Pane object holds `term: Terminal` reference
- [ ] On spawn: `spawnAgent(...)` then bind xterm to returned session_id
- [ ] On kill: `killAgent(...)` + `term.dispose()`
- [ ] Use the WebGL→Canvas→DOM cascade from maestro's TerminalView pattern
- [ ] rAF batching for incoming output

### 4c — Resize sync
- [ ] ResizeObserver per pane container
- [ ] `term.fit()` after layout change
- [ ] `resizePty(session_id, rows, cols)` to backend

### 4d — Wire v3 controllers to v4 commands
- [ ] `createAgent()` → invoke `spawn_agent` (NOT `spawn_shell` directly)
- [ ] `approveAgent()` → invoke `approve_permission`
- [ ] `rejectAgent()` → invoke `reject_permission`
- [ ] `killPane()` → invoke `kill_agent`
- [ ] Provider auth panel calls (`list_providers`, `login_provider`) still work
- [ ] Voice mode dispatches text via `write_stdin(session_id, text + '\n')`
- [ ] Gesture mode switches focus (pure JS, no backend)

### 4e — Sub-agent panels
- [ ] Right-click pane → context menu → "Spawn sub-agent"
- [ ] `invoke('spawn_sub_agent', { parent_id, name, cwd, agent_type })`
- [ ] Child panes render nested under parent in grid (indent + tree line)
- [ ] `subagent-tree-changed` event → re-render hierarchy

### 4f — Agent Monitor wiring
- [ ] `Ctrl+Alt+D` opens dashboard window
- [ ] Dashboard JS subscribes to `agent-update`, `activity-event`,
      `todo-update`, `subagent-tree-changed`, `file-touch-update` events
- [ ] No more reads of `/tmp/gmuxtest-*.json` — pure event-driven

### 4g — Todo panels per pane
- [ ] Each pane has a collapsible todo list strip below the terminal
- [ ] Subscribes to `todo-update-{agent_id}` events
- [ ] Click checkbox → `set_todo_done(agent_id, todo_id, !done)`

### 4h — Quick-swap palette, layout, favorites
- [ ] `Ctrl+P` palette over `panes` array (vanilla JS, no backend)
- [ ] `L` cycles layout
- [ ] `Ctrl+1..9` jumps direct
- [ ] Favorites in localStorage

### Acceptance criteria
- [ ] All v3.7.2 success criteria pass on v4
- [ ] No regression in any visible feature
- [ ] Sub-50ms input latency measured
- [ ] Tag: `v0.5.0-ui`

---

## Phase 5 — Phone bridge + headless

### Bridge
- [ ] `commands/bridge.rs` — `start_bridge`, `stop_bridge`, `list_phones`
- [ ] tokio task spawns WS server on `:8767` + HTTP on `:8768`
- [ ] Per-connection task handles auth handshake + message routing
- [ ] Token verification against `~/.config/gmux/pair-tokens.json`
- [ ] Subscribes to event bus, forwards `status` messages every 2s
- [ ] Phone commands (`send_text`, `permission_response`, etc.) route to v4 functions

### Pairing
- [ ] `gmux pair` CLI: generates token, writes to disk, prints QR
- [ ] Use `qrcode` crate for QR generation (pure Rust)
- [ ] Optional: HTML pairing page at `http://localhost:5550/pair`

### Headless mode
- [ ] `commands/headless.rs` — `--headless` flag in main.rs
- [ ] If --headless: skip Tauri window creation, start axum HTTP server on :5550
- [ ] Server routes: `/`, `/ui/`, `/api/state`, `/api/agents`, etc.
- [ ] All same Tauri commands callable via REST

### Acceptance criteria
- [ ] `gmux pair` shows valid QR
- [ ] Phone scans, connects, sees sessions
- [ ] Phone send_text → appears in pane
- [ ] `gmux-v4 --headless` starts without window
- [ ] Browser at `:5550` loads UI
- [ ] Tag: `v0.6.0-bridge`

---

## Phase 6 — Cross-platform

- [ ] Phase 1-5 regression test on Linux
- [ ] macOS Apple Silicon: all criteria pass
  - [ ] Keychain via `security` CLI works
  - [ ] Cmd+Opt+D global shortcut works
  - [ ] LANG fallback when launched from Finder
- [ ] macOS Intel: same
- [ ] Windows 11: all criteria pass
  - [ ] ConPTY path works
  - [ ] Credential Manager via keyring crate
  - [ ] taskkill /T /F for shutdown
- [ ] `docs/PLATFORM_TESTS.md` documents results
- [ ] Tag: `v0.7.0-cross-platform`

---

## Phase 7 — Polish + release

### Perf
- [ ] Measure input latency p95 (must be < 50ms)
- [ ] Measure output latency p95 (must be < 50ms)
- [ ] Memory leak test: 100 spawn/kill cycles
- [ ] Idle CPU test (must be < 5%)

### Image paste + drag-drop
- [ ] `save_pasted_image` Tauri command
- [ ] Clipboard paste interceptor in xterm.js mount
- [ ] Drag-drop via Tauri's `onDragDropEvent`

### Code-signing
- [ ] macOS: Apple Developer ID + notarisation pipeline
- [ ] Windows: signtool integration
- [ ] Linux: optional GPG signature

### Install scripts
- [ ] `scripts/install-macos.sh` — Homebrew + dmg install
- [ ] `scripts/install-windows.ps1` — winget + msi run
- [ ] `scripts/install-linux.sh` — distro-detect + appropriate pkg manager
- [ ] All scripts tested on fresh VMs

### v3 migration
- [ ] `gmux import-v3` reads v3 state and seeds v4 SQLite
- [ ] Documentation written for migration path
- [ ] v3 README updated with archived banner at v4 ship

### Release
- [ ] All boxes in OBJECTIVES.md Success Criteria ticked
- [ ] `gh release create v1.0.0` with platform binaries
- [ ] Repo flipped PRIVATE → PUBLIC
- [ ] Tag: `v1.0.0`

---

## Always-on chores

- [ ] Update `docs/AGENT_HANDOFF.md` at end of every session
- [ ] Update `docs/CHANGELOG.md` with each feature (create at Phase 0)
- [ ] Append session prompts to `docs/PROMPT_HISTORY.md`
- [ ] Tag every meaningful state
- [ ] Archive HTML before any big UI lift in `archive/ui/`

---

## "Where to look first" cheat sheet

| Task topic | Look in |
|---|---|
| PTY spawn / read / write | `~/projects/github_repos/maestro/src-tauri/src/core/process_manager.rs` |
| Tauri command structure | `~/projects/github_repos/maestro/src-tauri/src/commands/terminal.rs` |
| Anthropic usage API | `~/projects/github_repos/maestro/src-tauri/src/commands/usage.rs` |
| xterm.js mount + wiring | `~/projects/github_repos/maestro/src/components/terminal/TerminalView.tsx` |
| **Agent lifecycle spec** | `docs/AGENT_LIFECYCLE.md` (THIS REPO) |
| The gmux v3 UI | `~/projects/gmux-system/ui/v3/index.html` (8000+ lines) |
| The gmux v3 dashboard | `~/projects/gmux-system/app/src/dashboard/` |
| The phone protocol | `~/projects/gmux-system/docs/BRIDGE_DESIGN.md` |
| The v3 backend reference (DO NOT REUSE — design for in-process replacement) | `~/projects/gmux-system/backend/status/monitor.py` |
| The v3 voice daemon (optional sidecar) | `~/projects/gmux-system/backend/voice/gmux_voice_daemon.py` |
| Cross-platform notes | `~/projects/gmux-system/docs/MACOS_PORTING.md` |
| The maestro deep-dive | `~/projects/gmux-system/docs/maestro_study/` (3 docs) |
