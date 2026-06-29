# Implementation Phases

8 phases from docs to v4.0.0. Each phase ends with a git tag and a
runnable artefact. **Current phase: Phase 0 — Scaffolding starts now.**

Acceptance criteria are atomic checklists.

---

## Phase −1 — Documentation ✅ DONE

Tag: `v0.0.0-docs`. Repo: private at `fivelidz/gmux-v4`.

Established v4 as the **all-in-one successor** (not a sibling). v3
becomes legacy at v4.0.0 ship.

---

## Phase 0 — Scaffold (current)

**Goal:** Tauri 2 + Vite project that builds, opens an empty window,
and round-trips an `invoke('ping')` IPC. Persistence layer skeleton.

### What lands
- `package.json`, `vite.config.js`, `tsconfig.json`, `index.html`,
  `src/main.ts`
- `src-tauri/Cargo.toml`, `tauri.conf.json`, `build.rs`,
  `capabilities/default.json`, placeholder icons
- `src-tauri/src/main.rs` + `lib.rs` with one `ping` Tauri command
- `src-tauri/src/core/persistence/` skeleton — opens SQLite at
  `~/.local/share/gmux/state.db`, runs an empty migration
- `src-tauri/src/core/event_bus.rs` — initial broadcast channels
- A "Spawn shell" smoke button on the page

### Acceptance criteria
- [ ] `npm install` completes
- [ ] `npm run tauri:dev` opens a window on Linux
- [ ] Page shows "ping ok" output from invoke
- [ ] `cargo check` zero warnings for new code
- [ ] SQLite file created at the expected path
- [ ] Tag pushed: `v0.1.0-scaffold`

---

## Phase 1 — PTY core (Linux)

**Goal:** Lift maestro's PTY architecture. One smoke terminal works.

### What lands
- `core/process_manager.rs` (from maestro, env vars renamed)
- `core/terminal_backend.rs` (trait)
- `core/error.rs` (PtyError)
- `core/utf8_decoder.rs` (split-byte handling)
- `commands/terminal.rs` (spawn_shell, write_stdin, resize_pty, kill_session)
- `src/lib/pty.ts` frontend wrappers
- Minimal index.html with one xterm.js Terminal bound to a PTY

### Acceptance criteria
- [ ] "Spawn Shell" button → terminal appears with `$` prompt
- [ ] Type `ls` + Enter → file listing renders
- [ ] `htop` redraws correctly
- [ ] Resize window → terminal reflows
- [ ] Click "Kill" → shell exits
- [ ] `echo "测试 🚀"` → multi-byte renders correctly
- [ ] Unit test for `Utf8Decoder::decode` passes (split sequences)
- [ ] Zero `unwrap()` in non-test code
- [ ] Tag: `v0.2.0-pty-linux`

---

## Phase 2 — Agent layer + state stores

**Goal:** Wrap PTY sessions with the `Agent` abstraction. All state
managers (todos, activity, sub-agents, permissions, files) implemented
and event-bus wired. SQLite persistence works.

### What lands
- `core/agent_manager.rs` — Agent struct + DashMap + state machine
- `core/todo_store.rs` — CRUD + persistence
- `core/activity_log.rs` — circular buffer + queries
- `core/file_touches.rs` — heatmap
- `core/permission_store.rs` — pending permissions
- `core/sub_agent_registry.rs` — parent/child
- `core/event_bus.rs` — broadcast channels per stream
- `core/persistence/` — SQLite schema migrations + autosave loops
- `commands/agent.rs`, `commands/todo.rs`, `commands/activity.rs`,
  `commands/sub_agent.rs`, `commands/permission.rs`
- Minimal UI: a list of agents, a "spawn agent" button, a todo
  checkbox panel

### Acceptance criteria
- [ ] Spawning an agent creates a row in `agents` SQL table
- [ ] Adding a todo persists and reappears after app restart
- [ ] Activity log captures spawn + every PTY input/output burst
- [ ] Sub-agent spawn writes the parent link
- [ ] Permission state populated when a pattern in PTY output matches
- [ ] Killing an agent sets `ended_at`, removes from in-memory DashMap
- [ ] App restart restores agents list (minus the PTYs which can't survive)
- [ ] Unit tests for each manager
- [ ] Tag: `v0.3.0-agent-layer`

---

## Phase 3 — opencode SSE listener + usage tracking

**Goal:** Real-time agent activity through opencode + Anthropic usage.

### What lands
- `core/opencode_sse.rs` — per-agent SSE listener: detects new
  opencode sessions, parses `message.part.updated`, updates
  AgentManager + ActivityLog + TodoStore + PermissionStore
- `commands/usage.rs` (from maestro) — Anthropic /api/oauth/usage
  with 30s cache
- `core/usage_cache.rs` — TTL + 429-aware caching
- Frontend toolbar usage badge with daily/weekly toggle (from maestro's
  Tamagotchi pattern, ported to vanilla JS)
- 30s background polling task
- Auto-detect of opencode sessions from per-pane HTTP probes

### Acceptance criteria
- [ ] Starting a Claude/OpenCode agent triggers an SSE listener
- [ ] Tool calls populate ActivityLog
- [ ] Permission requests show "NeedsInput" state
- [ ] Todos from opencode appear in TodoStore
- [ ] Usage badge shows "Daily X%" after 30s
- [ ] Click toggles to "Weekly X%"
- [ ] Tooltip shows reset time
- [ ] Token expired: badge shows "🔑 Connect Claude"
- [ ] 429: cached for retry-after seconds
- [ ] Tag: `v0.4.0-sse-usage`

---

## Phase 4 — Full v3 UI integration

**Goal:** Lift the entire gmux-v3 UI on top of the v4 backend. The
app looks and feels like v3 but runs on v4's PTY-direct backend.

### Subphases

#### 4a — Lift UI files
- Copy `gmux-system/ui/v3/index.html` → `ui/index.html`
- Copy `gmux-system/app/src/dashboard/` → `ui/dashboard/`
- Lift `models/hand_landmarker.task` → `assets/`
- Configure Vite to serve `ui/index.html` as the root

#### 4b — Per-pane xterm.js
- Replace v3's mock pane content with real xterm.js Terminal per pane
- `spawnShell` on new-agent → mount Terminal in pane container
- `onData/onResize` → IPC to backend
- WebGL/Canvas/DOM fallback cascade

#### 4c — Wire v3's existing JS controllers to v4 commands
- `createAgent()` → invoke `spawn_agent` (not `spawn_shell` directly)
- `approveAgent()` → invoke `approve_permission`
- `getOpenCodeSessions()` etc. → adapt to new event-bus subscriptions
- Voice mode keeps working (Web Speech API path)
- Gesture mode keeps working (MediaPipe, model from `assets/`)

#### 4d — Sub-agent panels in grid
- Right-click → context menu → "Spawn sub-agent"
- Parent pane's grid cell expands; child panes render nested below

#### 4e — Agent Monitor (dashboard) wires to v4 state
- `Ctrl+Alt+D` opens the dashboard window
- All dashboard panels (rail, flowchart, detail panel, activity feed)
  subscribe to v4 events instead of polling JSON files

#### 4f — Todo UI panels per pane
- Each pane's grid cell has a collapsible todo list below the terminal
- Live updates from TodoStore events
- Click checkbox toggles done

#### 4g — Quick-swap, layout cycle, palette, favorites
- All v3 hotkeys work as-is (palette is pure JS over v4 state)

### Acceptance criteria
- [ ] All of v3.7.2's success-criteria boxes from `OBJECTIVES.md` pass
- [ ] No regression vs v3 in any visible feature
- [ ] Performance improved: input/output latency measurably better
- [ ] Tag: `v0.5.0-ui`

---

## Phase 5 — Phone bridge + headless

**Goal:** Phone control works. Headless mode works.

### What lands
- `commands/bridge.rs` — WS server `:8767`, HTTP `:8768`
- Implements the protocol in `~/projects/gmux-system/docs/BRIDGE_DESIGN.md`
- `gmux pair` CLI subcommand: QR + token to `~/.config/gmux/pair-tokens.json`
- `commands/headless.rs` + axum HTTP server on `:5550` (when `--headless`)
- HTTP API on `:8769` for compatibility with v3 phone clients

### Acceptance criteria
- [ ] `gmux pair` shows a QR with valid token
- [ ] Phone scans QR, connects, gets sessions list
- [ ] Phone send_text → appears in correct pane
- [ ] Phone approve_permission → agent unblocks
- [ ] Phone spawn_agent → pane appears locally
- [ ] Network drop → phone reconnects, re-authorises
- [ ] `gmux-v4 --headless` starts without a window
- [ ] Browser at `http://localhost:5550/ui/` loads UI
- [ ] HTTP API at `:8769/api/state` returns valid JSON
- [ ] Tag: `v0.6.0-bridge`

---

## Phase 6 — Cross-platform (macOS + Windows)

**Goal:** Phase 1-5 acceptance criteria all pass on macOS + Windows.

### What changes
- Verify `setsid` / `kill -pgid` path on macOS
- Verify ConPTY + DSR + taskkill on Windows
- macOS: `security` CLI for Keychain
- Windows: keyring crate for Credential Manager
- Cmd vs Ctrl global shortcuts
- xdg-open vs open vs start branching

### Acceptance criteria
- [ ] All Phase 1-5 criteria pass on macOS Apple Silicon
- [ ] All Phase 1-5 criteria pass on macOS Intel
- [ ] All Phase 1-5 criteria pass on Windows 11
- [ ] `cargo build --release` produces native binaries on each
- [ ] `docs/PLATFORM_TESTS.md` documents results
- [ ] Tag: `v0.7.0-cross-platform`

---

## Phase 7 — Polish + release

**Goal:** Production-grade quality. v3 archived. v4 public.

### What lands
- Final perf tuning (16ms PTY batching, rAF in JS)
- Code-signing for macOS (.dmg notarisation)
- Code-signing for Windows
- `.AppImage` + `.deb` + `.rpm` for Linux
- Install scripts per platform
- Auto-updater (Tauri's built-in)
- v3 migration helper: `gmux import-v3`
- v3 repo banner: "Archived. Use gmux-v4."
- Repo flips PRIVATE → PUBLIC

### Acceptance criteria
- [ ] All boxes in OBJECTIVES.md Success Criteria are ticked
- [ ] Input latency < 50ms p95 (measured)
- [ ] Output latency < 50ms p95 (measured)
- [ ] Idle CPU < 5%
- [ ] No memory leak after 100 spawn/kill cycles
- [ ] Code-signed `.dmg` distributable
- [ ] Code-signed `.msi` distributable
- [ ] Linux artefacts all present
- [ ] `gh release create v1.0.0` with all platform binaries
- [ ] v3 README updated with "archived" banner
- [ ] Tag: `v1.0.0`

---

## After v1.0.0

Roadmap (not in v4.0.0 scope):
- Auto-update (Tauri updater)
- Cloud relay for phone bridge
- Git worktree integration
- iOS native (gmux-phone v0.7's job)
- VTE-parser backend (for enhanced state tracking)
- Plugin marketplace
- Web Speech API → faster-whisper bundled

---

## How to skip ahead

Hard dependencies:
- Phase 0 must come first
- Phase 1 must precede 2, 3, 4
- Phase 2 (state stores) is a prereq for Phase 3 (SSE writes into them)
- Phase 4 can start as soon as Phase 2 done (3 in parallel is fine)
- Phase 5 needs Phase 2 (sessions to expose)
- Phase 6 needs everything else

Phases 2/3, 3/4, 5 can run in parallel after Phase 1 is done. Use the
sub-agent pattern: one agent on the Rust side (2/3), one on the UI
side (4), syncing via the docs.
