# v4 PTY swap — implementation plan

The **only** change from v3 to v4 is: replace the single-PTY-into-tmux
substrate with per-agent-PTY directly owned by the Rust backend.
Everything else (UI, voice, gesture, dashboard, sub-agents, provider
auth, phone bridge spec, memory aggregator) stays exactly as it is in
v3.7.2.

## Before / after

### v3 (today)

```
                              ┌─ Tauri Rust process ─┐
                              │                      │
                              │  ONE PTY:            │
ui/v3/index.html pane grid    │  tmux new-session    │ → tmux server
(summary cards rendered       │  -A -s gmux          │   │
 from monitor.py state)       │                      │   ├── window: claude
                              │  pty_writer.write(   │   ├── window: opencode
                              │    "\x01c"           │   ├── window: aider
                              │    "cd /x && opencode\r"  └── ...
                              │  )                   │
                              └──────────────────────┘
                                       ▲
                                       │ polls /tmp/gmuxtest-*.json every 2s
                                       │
                              ┌──────────────────────┐
                              │  monitor.py          │
                              │  - tmux list-panes   │
                              │  - opencode SSE      │
                              │  - writes JSON files │
                              └──────────────────────┘
```

### v4 (target)

```
                              ┌─ Tauri Rust process ──────────────────┐
                              │                                       │
                              │  ProcessManager:                      │
ui/v3/index.html pane grid    │   DashMap<u32, PtySession> {          │
(one xterm.js per pane,       │     1: PTY running 'claude'           │
 bound to one PTY each)       │     2: PTY running 'opencode'         │
                              │     3: PTY running 'aider'            │
                              │     ...                               │
                              │   }                                   │
                              │                                       │
                              │  emit("pty-output-{id}", data)        │
                              │                                       │
                              └───────────────────────────────────────┘
                                       │
                                       │ events flow directly to webview
                                       │ no monitor.py polling needed
                                       │ monitor.py becomes optional
                                       │ headless-mode sidecar only
                                       ▼
                                  (xterm.js renders)
```

## What changes, by file

### Rust — `app/src-tauri/`

1. `src/core/` — new module directory containing:
   - `process_manager.rs` — lifted from maestro, 600 LOC
   - `utf8_decoder.rs` — split-byte handling (from maestro)
   - `terminal_backend.rs` — backend trait (from maestro)
   - `error.rs` — `PtyError` types
   - `mod.rs` — exports
2. `src/commands/` — new module:
   - `terminal.rs` — `spawn_shell`, `write_stdin`, `resize_pty`,
     `kill_session`, `kill_all_sessions`, `get_backend_info`
3. `src/lib.rs` — register `ProcessManager` as managed state, expose
   the new commands, **keep** existing commands working during transition

### Frontend — `ui/v3/index.html`

The single biggest patch. In the pane-grid render path (`updatePaneEl`,
`createPaneEl`):
- Replace the summary-card HTML/CSS with a `<div class="pane-term"
  data-session-id="N"></div>` container
- On pane create: call `spawnShell(cwd)` (new Tauri command), receive
  `session_id`, mount an `xterm.js` Terminal into the container, listen
  on `pty-output-{session_id}` events, push input via `writeStdin`
- On pane delete: `killSession(session_id)` + `term.dispose()`
- Resize observer per pane → `resizePty(session_id, rows, cols)`

### Backwards-compat layer (v3 commands)

We keep `open_agent`, `open_project`, `spawn_sub_agent`, `login_provider`
working **during transition**:

- Old behaviour: writes prefix+c to the single tmux PTY
- New behaviour: calls `ProcessManager.spawn_shell()` then sends the agent
  launch command (`cd <dir> && opencode\n`) via `write_stdin`

A `cfg!(feature = "tmux-mode")` or runtime flag picks the path. Default
is the new path; users with existing tmux sessions can opt into the old
path until they're confident in the new model.

### monitor.py

Stays installed. Two adjustments:
1. Subscribes to a new `pty-state-update` Tauri event (instead of running
   `tmux list-panes` polling)
2. Stops writing pane-state.json once Rust emits the same data; it still
   writes activity.json + files.json + memory.json (those are derived
   data, useful for the phone bridge + headless mode)

When users run v4 in **desktop mode**, monitor.py is unnecessary.
When users run v4 with `--headless`, monitor.py provides the HTTP API
on `:8769` for phone/browser remote access.

## What v3 features keep working unchanged

| Feature | How it works in v4 |
|---|---|
| Voice mode (Web Speech + faster-whisper) | Unchanged. Voice JS dispatches text via `writeStdin(focused_session_id, text)` |
| Gesture engine (MediaPipe hand tracking) | Unchanged. Gestures switch which pane has focus; no backend change |
| Agent palette (Ctrl+P) | Unchanged. Pure JS over the `panes` array (just now panes have a `session_id` field) |
| Layout cycle (L key) | Unchanged |
| Per-session last-dir memory | Unchanged (localStorage) |
| Provider auth panel | Unchanged. Connect Claude / OpenAI still works the same way |
| First-launch auth wizard | Unchanged |
| Sub-agent spawning | Same UX: right-click → "spawn sub-agent". Now creates a new PTY via `spawn_shell` and writes the parent-link to `/tmp/gmuxtest-sub-agents.json` so monitor.py can still observe it |
| Agent Monitor (Ctrl+Alt+D) | Unchanged — still opens the dashboard window. Dashboard subscribes to `pty-state-update` instead of polling JSON |
| Memory aggregator + Memory tab | Unchanged |
| Folder click-to-drill-in | Unchanged |
| Full-path display | Unchanged |
| Rate-limit detection + countdown | Unchanged. Pattern matching now applies to per-PTY output buffers in Rust, but the result still surfaces as the same UI badge |
| Markdown chat fullscreen | Unchanged |
| Theme switching | Unchanged |
| Window naming / fish-name fix | Gets *simpler* — we set the agent name directly when spawning, no more `prefix+,` rename gymnastics or `automatic-rename off` workaround |
| Session restore | Gets adapted: instead of restoring tmux window names, we restore agent metadata from SQLite (or a JSON snapshot file) on app startup |
| Phone bridge | Designed in v3 docs/BRIDGE_DESIGN.md, builds in v4 against the new ProcessManager session list (instead of monitor.py tmux state). Same WS protocol |

## Migration timeline

### Step 1 — copy v3 into v4 ✅ DONE
`rsync` of `gmux-system/` into `gmux_v4/`. Repo now mirrors v3.

### Step 2 — lift maestro PTY core
- Create `app/src-tauri/src/core/{process_manager.rs, terminal_backend.rs, error.rs, utf8_decoder.rs}` from
  `~/projects/github_repos/maestro/src-tauri/src/core/`
- Rename env vars (`MAESTRO_SESSION_ID` → `GMUX_SESSION_ID`)
- Add `core` module to `lib.rs`

### Step 3 — add new Tauri commands
- Create `app/src-tauri/src/commands/terminal.rs` with the maestro
  `spawn_shell` / `write_stdin` / `resize_pty` / `kill_session` /
  `kill_all_sessions` / `get_backend_info`
- Register in `invoke_handler!`
- Add `src/lib/pty.ts` (small TS wrapper) — actually since v3 is pure JS,
  we'll put these as inline functions in `ui/v3/index.html`

### Step 4 — smoke-test single PTY
- Verify the existing v3 build still works (the new code is additive,
  no existing code touched)
- Add a hidden devtools-only button "Spawn test shell" that calls
  `spawn_shell()` and dumps `pty-output-*` events to console
- Confirm a shell prompt appears via PTY events

### Step 5 — mount xterm.js per pane (in UI)
- In `ui/v3/index.html`, find the pane-rendering path (search for
  `updatePaneEl` / `renderPanes`)
- For each pane that has `session_id` set, create an xterm.js
  Terminal inside the pane container
- Listen on `pty-output-{session_id}` → `term.write(data)`
- Bind `term.onData(data => writeStdin(session_id, data))`
- Bind `term.onResize` → `resizePty(session_id, rows, cols)`

### Step 6 — rewire open_agent / open_project / spawn_sub_agent
- Change behaviour from "write keystrokes into tmux PTY" to:
  1. Call `spawn_shell(cwd=dir, env={"GMUX_SESSION_ID": new_id})` → session_id
  2. Build the agent command (e.g. `opencode` or `claude --model X`)
  3. Call `write_stdin(session_id, format!("{}\n", agent_cmd))`
  4. Update the `panes` JS object with `session_id`
  5. UI mounts xterm.js for that session_id
- The new `spawn_sub_agent` records the parent-child link in
  `/tmp/gmuxtest-sub-agents.json` (same as v3)

### Step 7 — adapt monitor.py
- Add a Rust command `get_pty_state_json` that returns the same shape
  as `/tmp/gmuxtest-pane-state.json`
- monitor.py: if Tauri is up and the command is callable, use it
  instead of `tmux list-panes` polling
- The activity / files / memory producers stay as-is (they listen to
  opencode SSE, not tmux)

### Step 8 — preserve v3 features
- Session restore: instead of restoring tmux window names, save
  `panes` JSON (just the metadata, not the PTYs) to a config file on
  app close, reload on startup. Spawn fresh PTYs for any that should
  auto-resume.
- Fish-name fix: not needed any more (we don't pass through tmux's
  automatic-rename)
- Automatic-rename lock: not needed any more
- Sub-agent JSON: works unchanged

### Step 9 — make tmux optional
- `scripts/launch.sh`: drop the `tmux new-session -A` step
- `scripts/install-vm.sh`: tmux moves from mandatory to optional (only
  required for headless mode)
- Update `DEPENDENCIES.md`, `INSTALL_GUIDE.md`

### Step 10 — test, tag, push
- Run `python3.11 backend/status/test_monitor_producers.py` — must pass
- Smoke test in Tauri: spawn 3 agents in different folders, voice talk
  to one of them, switch between them with Ctrl+P
- Tag `v4.0.0-alpha.1`
- Push to GitHub

### Step 11 — cross-platform (post alpha-1)
- Verify on a Mac (lifted maestro code already handles this)
- Verify on Windows (same)
- Tag `v4.0.0-alpha.2` once each platform works

### Step 12 — Release
- Code-sign macOS / Windows builds
- AppImage / .deb for Linux
- v3 README banner: "Archived — use v4"
- Tag `v4.0.0`

## What's explicitly out of scope for this swap

- All-new state management (todos in SQLite, etc.) — that was the old
  plan; reverting it
- Rewriting the UI to React — staying with v3 vanilla JS
- Plugin marketplace — same
- Auto-updater — same; can add post-ship

These can be future enhancements; they're not blocking v4 ship.

## Risk register

| Risk | Mitigation |
|---|---|
| The pane-rendering code in `index.html` is tangled and slow to refactor | Keep summary-card view as fallback; new xterm-mode is opt-in via a feature flag toggle in localStorage during alpha. Compare both side-by-side. |
| Voice/gesture relied on monitor.py-derived focus state | Voice/gesture only need to know which pane has focus — that's a pure JS variable. No backend coupling. |
| Rate-limit detection regex was applied to monitor.py's pane state | Move the regex to the Rust side: it now runs on each PTY's output buffer. Trigger remains the same; surface is the same. |
| Sub-agent JSON gets out of sync between Rust and monitor.py | Rust becomes the writer; monitor.py becomes a reader. Single source of truth. |
| macOS/Windows PTY behaviour differs from Linux | portable-pty handles this transparently. Plus maestro is already tested on all three. |
| Existing v3 tests need updating | Most test plain Python logic that doesn't touch tmux. Only failure mode is `test_monitor_producers.py` — adjust to read state from a mock or the new Rust API. |

## Definition of done — v4.0.0-alpha.1

- [ ] `cargo check` clean on a fresh `cargo build` (no warnings on new code)
- [ ] `npm run tauri dev` opens the Tauri window
- [ ] User can press `N`, create an agent in a folder, see the agent's
      real terminal in the pane grid (xterm.js)
- [ ] Typing in the pane is received by the agent (via `write_stdin`)
- [ ] Output from the agent is rendered in the pane (via `pty-output` events)
- [ ] Layout cycling, palette, voice, gesture, dashboard, provider auth
      all still work
- [ ] No tmux process spawned by Tauri (it's optional, only used for
      headless mode if user enables it)
- [ ] `python3.11 backend/status/test_monitor_producers.py` passes
- [ ] Commit + tag `v4.0.0-alpha.1`

## Definition of done — v4.0.0 (ship)

- [ ] Cross-platform tested on macOS + Windows
- [ ] Sub-50ms latency measured
- [ ] Phone bridge implemented per `docs/BRIDGE_DESIGN.md`
- [ ] Auto-updater wired
- [ ] Code-signed binaries produced
- [ ] Install scripts tested on fresh VMs
- [ ] gmux-system v3 repo banner: "Archived — use v4"
- [ ] Tag `v4.0.0`
