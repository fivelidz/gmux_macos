# v4 Backend Design — how the PTY-based backend should look

**Status:** alpha.7 draft  ·  **Last updated:** 2026-05-17  ·  **Author:** the AI agent currently doing the work

This is the long-form answer to "what does the v4 backend look like?".
It describes the **target architecture** — where we want to end up
once the v4 PTY layer is the default and tmux is optional. The current
state (alpha.6/7) is a transitional one: both v3 and v4 paths coexist.

If you only have 30 seconds, read the **Glance** section below. If
you're implementing, read the **Component contracts** and
**Migration tactics** sections.

---

## Glance

```
┌────────────────────────────────────────────────────────────────────────┐
│                         gmux Tauri window (Rust)                       │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │  UI process  (WebKit + vanilla JS)                             │   │
│  │   - Pane grid · Chat panel · Dashboard window                  │   │
│  │   - Reads `panes` map (merged from monitor.py + v4 PTY)        │   │
│  │   - Writes via invoke('write_stdin' | 'send_to_agent' | …)     │   │
│  └──────────────────────────┬─────────────────────────────────────┘   │
│                             │ Tauri IPC                                │
│  ┌──────────────────────────┴─────────────────────────────────────┐   │
│  │  Rust core  (one ProcessManager owns all PTYs)                 │   │
│  │   - portable-pty per agent (cross-platform)                    │   │
│  │   - reader thread → mpsc → tokio task → "pty-output-{id}"      │   │
│  │   - registers each PTY with the status server                  │   │
│  │   - exposes ~30 #[tauri::command]s                             │   │
│  └──────────────────────────┬─────────────────────────────────────┘   │
└─────────────────────────────┼──────────────────────────────────────────┘
                              │ child subprocesses
       ┌──────────────────────┼──────────────────────────────┐
       ▼                      ▼                              ▼
 ┌────────────┐    ┌─────────────────────┐    ┌────────────────────────┐
 │ monitor.py │    │  agent CLI #1       │    │  agent CLI #N          │
 │ :8769      │    │  (claude / opencode)│    │                        │
 │            │    │  in its own PTY     │    │  in its own PTY        │
 └─────┬──────┘    └─────────────────────┘    └────────────────────────┘
       │
       │ writes /tmp/gmuxtest-pane-state.json (live, 2s cadence)
       │   + activity.json + memory.json + files.json + services.json
       ▼
   UI poll
```

**One Rust process. Many PTYs.** No tmux involved.

---

## Component contracts

### 1. `ProcessManager` (Rust)

**Owns** every PTY in the app. Maps a monotonic `session_id: u32` to a
PTY session. Each session is:

```rust
struct PtySession {
    writer:        Mutex<Box<dyn Write + Send>>,
    master:        Mutex<Box<dyn MasterPty + Send>>,
    child_pid:     i32,
    pgid:          i32,                              // for SIGTERM
    shutdown:      Arc<Notify>,
    reader_handle: Mutex<Option<JoinHandle<()>>>,
}
```

**Methods that already exist (alpha.6):**

| Method                       | What it does                                          |
|------------------------------|-------------------------------------------------------|
| `spawn_shell(cwd, env)`      | Open a PTY, spawn `$SHELL -l`, return `session_id`    |
| `write_stdin(id, data)`      | Write any bytes (incl. `\r`, `\x1b`, `\x03`) to PTY   |
| `resize_pty(id, rows, cols)` | SIGWINCH propagation                                  |
| `kill_session(id)`           | SIGTERM (3s) → SIGKILL escalation on the process group|
| `get_session_pid(id)`        | Returns child PID for psutil lookups                  |
| `get_all_session_pids()`     | List of `(id, pid)` for monitor / dashboard           |
| `kill_all_sessions()`        | Used on app shutdown                                  |

**Methods to add for full parity:**

| Method                                 | Purpose                                          |
|----------------------------------------|--------------------------------------------------|
| `spawn_agent(cwd, agent_type, model)`  | Spawn shell + send `cd $cwd; <agent_cmd>\r`     |
| `attach_status_server(id, port)`       | Hook a PTY to the per-pane MCP status server     |
| `session_label(id, str)`               | Setter for the pane's display name (cleared on kill) |
| `session_metadata(id) → Map<k,v>`      | Cached `{model, cwd, agent_type, started_at, …}` |
| `subscribe_output(id, channel)`        | Server-side fan-out instead of Tauri-only events |

### 2. Status server (sidecar, Python)

`backend/status/monitor.py` continues to be the source of truth for
pane state. Currently it polls `tmux list-panes`; in v4 it polls
`/api/v4/sessions` from Rust instead, plus its existing per-pane MCP
status endpoint scrape.

**Output contract (unchanged):** writes `/tmp/gmuxtest-pane-state.json`
keyed by `pane_id` with the schema documented in `AGENT_MONITOR_FIELDS.md`.

**New Rust → Python wire:** a small HTTP endpoint added to Rust
(`:8771/sessions`) returning the same JSON shape as
`get_pane_state_v4`. monitor.py reads from this instead of (or in
addition to) tmux. Falls back to tmux when the endpoint is unreachable
(e.g. v3-only install).

### 3. Per-pane MCP status server (existing)

Each agent CLI starts an MCP server on a free port (`api_port`).
monitor.py discovers it via lsof / process inspection. The UI talks
to this server for:

- `/session?directory=...` → list session IDs
- `/session/{id}/messages?directory=...` → chat history
- `/session/{id}/prompt_async?directory=...` → send a user message
- `/session/{id}/permission/{allow|deny}?directory=...` → approve/reject
- `/session/{id}/abort?directory=...` → cancel current generation

**v4 invariant:** this layer is unchanged. v4 PTY shells launch the
agent CLI the same way v3 tmux windows did; the MCP server appears
naturally as a child of the PTY. monitor.py just needs to know the
parent PID is now `ProcessManager.get_session_pid(id)` instead of a
tmux pane PID.

### 4. UI data model

```js
panes[paneId] = {
  // Identity
  pane_id, session_name, window_index, window_name, cwd,
  // State
  state, todos, todo_done, todo_total, current_tool,
  // Resources
  ram_mb, cpu_pct, uptime_s, children,
  // Agent
  model, has_ai, api_port, token_in, token_out, last_message_role,
  // v3-only
  // (nothing — tmux is the default identity)
  // v4-only (when is_v4=true)
  is_v4, v4_session_id, child_pid,
}
```

The **same shape** for both backends — the UI only checks `is_v4` to
decide routing (write_stdin vs HTTP API), never to decide rendering.

### 5. Event flow

```
PTY → reader thread → mpsc(256 slots) → tokio task →
  ├─ batches into 16ms / 64KB chunks
  ├─ emits "pty-output-{id}" to all Tauri listeners
  └─ (planned) writes to a server-side ring buffer for late-joiners

monitor.py → reads Rust /sessions endpoint + scrapes MCP servers →
  writes /tmp/gmuxtest-pane-state.json every 2s →
  Rust file-watcher → emits "gmux-state" to UI

UI receives both:
  - gmux-state → dashboard / pane grid (general state)
  - pty-output-{id} → xterm.js (rendering) + CHAT[pane_id] (history)
```

---

## Migration tactics — getting from alpha.6 to fully v4

### Phase 1 (done in alpha.5/6)
- ✅ `ProcessManager` lifted from maestro under MIT
- ✅ Per-pane PTY commands (spawn/write/resize/kill)
- ✅ `open_agent_v4`, `spawn_sub_agent_v4` (agent layer)
- ✅ `get_pane_state_v4` (returns same JSON shape)
- ✅ `interrupt_agent` (3-tier escalation for v3, write_stdin Esc for v4)
- ✅ UI merges v4 panes into the `panes` map every 2s
- ✅ UI: `sendChat()` routes through `write_stdin` for v4 panes
- ✅ UI: `stopAgent()` routes through `write_stdin(0x1b)` for v4 panes
- ✅ `pty-output-{id}` events fan into both xterm.js AND `CHAT[]`

### Phase 2 (alpha.7-8 — what's next)
- [ ] **Status-server registration**: when `ProcessManager::spawn_agent`
  runs, it should immediately register the new PID with monitor.py so
  the dashboard sees the pane within one poll cycle.
- [ ] **Server-side output buffer**: keep the last 4KB of PTY output
  per session in a ring buffer. UI listeners that join late (e.g. user
  opens chat after agent has been running) get the recent context.
- [ ] **Provider login via v4 PTY**: `login_provider` currently spawns
  `opencode auth login` detached. Better: spawn it in a real PTY, show
  the OAuth URL in the chat panel, let the user click.
- [ ] **Rust HTTP `/sessions` endpoint**: serves the same shape as
  `get_pane_state_v4` over HTTP. monitor.py polls it.
- [ ] **Session metadata persistence**: write `{id, cwd, agent_type,
  model, started_at, last_used}` to `~/.config/gmux/sessions.json` so
  the app can offer "resume last session" on launch.

### Phase 3 (beta)
- [ ] Make v4 PTY the default for new agents (no toggle needed).
- [ ] Drop tmux from install scripts (optional dep for headless mode).
- [ ] macOS verified end-to-end (mostly done; needs human run).
- [ ] Windows ConPTY verified end-to-end.

### Phase 4 (1.0)
- [ ] Remove all v3 tmux code paths from Rust.
- [ ] Remove tmux-related toasts and tooltips from UI.
- [ ] monitor.py drops its tmux poller, only uses Rust `/sessions`.

---

## Design principles (won't break these)

1. **Same JSON contract for v3 and v4.** `get_pane_state_v4` returns
   the same shape as `gmuxtest-pane-state.json`. UI code should never
   need to learn a v4-specific field schema.

2. **One-direction data flow.** Rust owns PTYs; Python (monitor.py)
   owns state aggregation; UI is a viewer that occasionally invokes
   commands. No back-channels.

3. **Tauri events for streaming, IPC commands for actions.** PTY
   output streams via `pty-output-{id}` events. User actions (send
   message, stop, approve) go through `invoke(...)` commands.

4. **Bounded buffers everywhere.** Reader thread → 256-slot mpsc.
   Event batcher → 64KB flush valve. Output ring buffer → 4KB.
   Never an unbounded queue.

5. **Process groups, not PIDs.** When we kill a session, we kill the
   process *group* (negative PGID) so child agent CLIs and the MCP
   server die together. portable-pty calls `setsid()` for us; we save
   the PGID at spawn time.

6. **Graceful first, force second.** Esc → C-c. SIGTERM → wait 3s →
   SIGKILL. HTTP /abort → tmux Esc → C-c. Always escalate, never
   hard-kill first.

7. **No tmux in v4 hot paths.** v4 mode must work with `tmux` absent
   from `$PATH`. Test by `mv $(which tmux) /tmp/tmux.bak` and running
   `./scripts/launch-v4.sh --test`.

8. **Sidecars are children, not peers.** monitor.py and the voice
   daemon are spawned by Rust at startup, parented to the Tauri
   process, and killed when the app exits. No orphan processes.

9. **Cross-platform is a feature, not an aspiration.** Every new
   feature must work on Linux, macOS, AND Windows (or be explicitly
   feature-gated with `#[cfg(...)]` and degrade gracefully).

10. **The UI must work in plain browser mode too.** Tauri provides
    PTY + sidecar lifecycle, but the v3 HTTP path (browser hits
    monitor.py :8769 directly) must remain functional for headless /
    remote scenarios.

---

## Why this shape (not alternatives)

| Alternative considered          | Why rejected                                  |
|---------------------------------|-----------------------------------------------|
| Keep using tmux forever         | Unix-only. macOS users tolerate it; Windows users don't. |
| Use libtmux / write our own mux | Reinventing tmux is a multi-year project. PTY-per-agent gives us 90% of the value at 10% of the work. |
| One PTY shared by all agents (v3 style) | Already broken: agents step on each other's stdin, and you can't run them in parallel. |
| Node.js subprocess management   | We're a Tauri app; Rust is already the host. Adding Node ⇒ more deps, more attack surface. |
| Web-based terminal only (no PTY)| Can't run real CLIs without a backend. Defeats the whole point. |

---

## "What if I disagree with this design?"

Open `docs/DECISIONS.md` and add a counter-proposal with:
1. The principle you'd change
2. What it enables that's blocked today
3. The migration path from current state
4. A list of tests that would need to change

The current shape is a default, not a religion.

---

*End of design doc. For implementation status see V4_STATUS.md.
For user-facing migration notes see V4_PTY_PLAN.md.*
