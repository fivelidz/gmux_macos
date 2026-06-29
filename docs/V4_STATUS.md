# v4 status — running log of what's done and what's next

A living checklist. Updated at the end of every session. Read this
before reading anything else if you're picking up the work.

---

## Where we are

**Phase:** Alpha — Agent Monitor now actually opens; layout + agent-type fixes.
**Tag at HEAD:** `v4.0.0-alpha.8`
**Next:** Human verification of Agent Monitor (now actually opens flowchart),
v4 chat round-trip. Then make v4 the default for new agents.

## What's working

- ✅ Repo mirrors `gmux-system` v3.7.2 (all UI, voice, gesture,
  dashboards, backend sidecars, scripts, tests intact)
- ✅ 211/211 Python tests passing (`test_monitor_producers` 117,
  `test_sub_agents` 30, `test_memory_aggregator` 64)
- ✅ Maestro `ProcessManager` lifted into `app/src-tauri/src/core/`
  with attribution headers; env vars renamed to `GMUX_*`
- ✅ 9 new Tauri commands registered alongside the v3 commands:
  - PTY core: `spawn_shell`, `write_stdin`, `resize_pty`,
    `kill_session`, `kill_all_sessions`, `get_backend_info`,
    `pty_ping`
  - Agent layer: `open_agent_v4`, `spawn_sub_agent_v4`
  - State: `get_pane_state_v4` (live session dict from ProcessManager)
- ✅ `cargo check` **zero warnings** (pre-existing `window` warning fixed)
- ✅ Smoke test button + JS function ready to verify the new PTY
  path end-to-end
- ✅ `createAgent()` in the UI has an opt-in v4 PTY path:
  `localStorage.setItem('gmux_v4_pty', '1')` → next "+ new agent"
  uses `open_agent_v4` instead of `open_agent`
- ✅ `open_project`, `spawn_sub_agent`, `login_provider` return
  `v4-redirect` errors when `GMUX_V4_PTY=1` so JS can use v4 siblings
- ✅ `login_provider` spawns auth flow as detached subprocess in v4 mode
- ✅ `find_gmux_script` now searches `gmux_v4/backend/` first (sidecars
  resolve from this repo before gmux-system)
- ✅ `on_window_event` session-save path fixed (was pointing to
  non-existent `gmuxtest/src-py/` and `gmux/src/` paths)
- ✅ Full release build: 17 MB binary + .deb + .rpm (alpha.4, re-verified alpha.5)
- ✅ Standalone PTY smoke test passes (`cargo run --example pty_smoke`)
- ✅ `launch-v4.sh` — self-contained launch script with `--test` / `--kill` /
  `--browser` / `--dev` modes; passes **13/13 headless checks**
- ✅ `launch.sh` monitor detection patched to find `gmux_v4/backend/status/monitor.py`
- ✅ Release binary headless launch verified: WebKit processes spawn, session_restore
  from `gmux_v4/backend/session/` confirmed, `GMUX_V4_PTY=1` skips tmux attach
- ✅ `get_pane_state_v4` JSON shape verified (pane_id, is_v4, child_pid, ram_mb all present)
- ✅ `interrupt_agent` Tauri command — Esc/Cancel for running agents (3-tier
  escalation: HTTP /abort → tmux send-keys Escape → Ctrl-C)
- ✅ **UI ergonomics pass (alpha.6):**
  - Model dropdown shows real Anthropic models: `sonnet` / `opus` / `haiku`
    aliases + explicit `claude-sonnet-4-6` / `claude-opus-4-7` / `claude-haiku-4-5`
  - Two new presets: "Yolo Sonnet 4.6" and "Yolo Opus 4.7" auto-set both
    model AND Yolo Extreme mode
  - Stop button (⎋) in chat panel and pane card headers for running/waiting
    agents — calls `interrupt_agent`
  - Each pane card now shows a model badge (color-coded: accent / opus-red / haiku-green)
  - Chat input restructured: textarea full-width on its own row, action
    buttons (history, mic, stop, send) in a separate row below — no more
    squashing
  - In fullscreen chat mode, textarea grows up to 340px tall (was 120px)
  - "Connect Claude" badge now opens Options AND switches to the Providers
    tab specifically (was opening to default Layout tab)
  - Agent Monitor button: improved toasts explain whether it opened a
    separate Tauri window or fell back to a browser tab
  - New "👁 Active / All" toolbar toggle filters out idle shell panes by
    default — focuses the grid on agents that are actually doing things
- ✅ `docs/V4_PTY_PLAN.md` — plain-English explainer of the migration plan
- ✅ **alpha.7 — v4 ↔ v3 parity for chat + interrupt + state:**
  - `sendChat()` routes through `write_stdin(text+\r)` when pane is v4
  - `stopAgent()` routes through `write_stdin(0x1b)` (Esc) or `0x03` (C-c)
    when pane is v4 — no tmux involved
  - UI polls `get_pane_state_v4` every 2s and merges results into the
    pane map; v4 panes show up alongside tmux panes
  - For each new v4 pane discovered, UI attaches a `pty-output-{id}`
    listener that streams output into `CHAT[pane_id]` — v4 agents show
    up in the chat panel like normal agents (no xterm needed)
  - Model badge `.ph-model` is now a clickable button; opens an inline
    model-picker that sends `/model <name>` to the agent via existing
    `send_to_agent` pipeline
  - Brand badge in topbar shows app version (e.g. `4.0.0-alpha.7`),
    click to copy; backed by new `app_version` Tauri command which
    reads `GMUX_GIT_TAG` injected by `build.rs`
  - Fixed false "backend down — UI on mock" notice — it was firing
    before the first health check completed; now suppressed when
    `lastCheck === 0`
  - Fixed `backend_health` Rust command — was checking the wrong file
    path (`/tmp/gmux-pane-state.json` instead of `gmuxtest-`)
- ✅ `docs/V4_BACKEND_DESIGN.md` — long-form architecture explainer:
  component contracts, migration phases (1–4), design principles, and
  rejected alternatives
- ✅ **alpha.8 — Agent Monitor fix + ergonomics fix:**
  - **Root-cause fix for Agent Monitor "doesn't open"**: vite was only
    bundling `index.html` into `app/dist/`. The `dashboard` and `aquarium`
    HTML files were missing from the packaged build, so the Tauri windows
    that load `dashboard/index.html` opened blank. Added custom vite
    plugin `copyExtraWindows()` that copies `src/dashboard/` and
    `src/aquarium.html` to `dist/` after the main vite write step. Plugin
    runs in `closeBundle` (final) hook with `enforce: 'post'` so it runs
    after any `emptyOutDir` cleanup. Includes a sanity assertion that
    fails loudly if the dashboard didn't end up in dist.
  - **Path-resolution bug discovered & fixed**: `path.resolve('../dist')`
    resolves against `process.cwd()`, which is the project root (not
    `app/`) when invoked via `tauri build`. Fixed by using
    `path.join(__dirname, 'dist')` based on `fileURLToPath(import.meta.url)`.
    First build was writing to `~/projects/gmux_v4/dist` (wrong!) instead
    of `~/projects/gmux_v4/app/dist`. Cleaned the wrong-dir dist.
  - Stop button moved from pane header → into the todo-progress-row
    (next to the % and task count). No longer obscures the agent title.
  - New `agentTypeOf(p)` + `agentTypeBadgeHtml(p)`: detects agent CLI
    type (claude / opencode / qalcode / aider / gemini / gpt / agent)
    from spawned_agent_type → provider → foreground_cmd. Color-coded
    badge appears next to the model badge.
  - Brand version badge is now bright accent-colored + outlined so the
    user can confirm the new build loaded. Click → toast with build time;
    click again within 4s → copies version+build info to clipboard.
  - `app_build_time` Tauri command + `GMUX_BUILD_TIME` env var injected
    by `build.rs` (with inline days-to-ymd math, no chrono dep).
  - `GMUX_FORCE_REBUILD` env var added to `build.rs` so devs can bust
    the cache to refresh the build-time stamp.
  - Layout fixes (responsive):
    * Removed the 2400px max-width cap on ultrawide displays — was
      leaving a dead band on either side
    * Added `overflow-x: auto` to `#topbar` so buttons don't clip on
      narrow windows
    * Brand right-border hidden below 900px to save 14px
    * `#opts-panel` capped at `90vh` so Options modal scrolls instead
      of cutting off Save/Reset on shorter windows
- ✅ Backup procedure: `archive/binaries/gmuxtest-v4.0.0-alpha.7-*` saved,
  source snapshot tar archived in `archive/snapshots/`

## What needs human verification — DO THIS FIRST

The Rust core compiles. The IPC bindings exist. The smoke test JS is
in place. Nobody has actually run `npm run tauri dev` to verify
output streams via `pty-output-{id}` events yet.

### Smoke test procedure

```bash
cd ~/projects/gmux_v4/app
npm install   # if not done already
npm run tauri dev
```

When the window opens:

1. Right-click → "Inspect" to open DevTools (Tauri exposes them in dev mode)
2. Console → run: `localStorage.setItem('gmux_v4_smoke', '1')` then refresh
3. Look for the 🧪 v4 PTY button in the toolbar
4. Click it
5. Watch the console — you should see:

```
🧪 v4 PTY smoke test
1) pty_ping → pong
2) spawn_shell → 1
3) listening on pty-output-1
   [pty-output-1] "\x1b]7;file://...\x1b\\\u001b]2;...\x1b\\$ "      ← shell prompt
4) wrote: echo "hello v4 PTY"
   [pty-output-1] "echo \"hello v4 PTY\"\r\n"                          ← echo of input
   [pty-output-1] "hello v4 PTY\r\n"                                   ← agent output
   [pty-output-1] "$ "                                                  ← next prompt
5) killed session, smoke test complete ✅
```

If you see this, **the PTY core works**. Tag and commit:
```bash
cd ~/projects/gmux_v4
git tag -a v4.0.0-alpha.1 -m "v4.0.0-alpha.1: PTY core smoke-tested end-to-end"
git push --tags
```

If you see something else (e.g. spawn_shell errors, no PTY output),
note the failure in this doc under "Known issues" and stop.

---

## Enabling the v4 path (no DevTools needed)

The Options panel has a new **v4 Lab** tab. Open it, tick "Enable v4
PTY for new agents". Toggling this:

- Routes the next "+ new agent" through `open_agent_v4` (Rust spawns
  a per-agent PTY via portable-pty; no tmux involved).
- The new pane's view mode auto-switches to "Terminal" and mounts
  xterm.js bound to the agent's PTY.
- `Tab` cycles `Tasks → Chat → Hardware → Terminal → Tasks`.

To disable: untick the box. New agents go back through the legacy
tmux path. Existing agents are unaffected.

## Second verification — full PTY path end-to-end

1. Options → v4 Lab → tick **Enable v4 PTY for new agents**
2. Press `N` for New Agent
3. Type a real path (e.g. `~/projects/gmux_v4`), pick an agent type
4. Click Create
5. The pane should switch to Terminal view and show your shell prompt
6. Press Tab — you can cycle back to Tasks / Chat / Hardware views
7. Type into the terminal — it should respond
8. Toast: `🧪 v4 PTY: agent spawned (session #N)`
9. DevTools console:
   - `[gmux] open_agent_v4 ok: session_id = N`
   - `[gmux v4] mounted xterm for pane … session N (cols x rows)`

If you see this, **the per-pane PTY pipeline works end-to-end**.

## What's not done yet

In rough dependency order:

1. ✅ ~~**xterm.js per pane**~~ — landed in alpha.2.
2. ✅ ~~**Rewire `open_project`, `spawn_sub_agent`, `login_provider`**~~ —
   all three return `v4-redirect` errors in v4 mode so JS uses v4 siblings.
   `login_provider` additionally spawns auth as a detached subprocess.
3. ✅ ~~**`get_pane_state_v4` Tauri command**~~ — queries ProcessManager,
   returns same JSON shape as `gmuxtest-pane-state.json`.
4. ✅ ~~**`find_gmux_script` path fix**~~ — gmux_v4/backend/ searched first.
5. ✅ ~~**`on_window_event` script path fix**~~ — gmux_v4 + gmux-system only.
6. **Human GUI smoke test** — still needed (xterm.js renders, PTY streams).
   See "What needs human verification" section above.
7. **Drop `start_pty` tmux dependency** — the legacy single-PTY
   path is still spawned at app start (it tries to attach to a tmux
   session). Once v4 is the default, this can be gated behind a
   `v4_legacy_mode` flag. Currently it skips cleanly when `GMUX_V4_PTY=1`.
8. **monitor.py v4 adaptation** — currently monitor.py still polls `tmux
   list-panes`. Add a Rust IPC path so v4-spawned PTYs feed the dashboard
   state without tmux. `get_pane_state_v4` is the bridge — JS can call it
   and merge the result with the file-backed pane state.
9. **Session restore** — replace tmux-window-name persistence with a
   `~/.config/gmux/sessions.json` snapshot. On startup, re-spawn shells.
10. **Install scripts** — `scripts/install-vm.sh` etc.: tmux moves
    from required to "optional for headless mode".
11. **Cross-platform verification** — already designed in; needs
    real Mac + Windows runs.
12. **Phone bridge** — implement per `docs/BRIDGE_DESIGN.md` (v3 doc
    that carried over; same WS protocol).

## Key files to know about

| File | Role |
|---|---|
| `README.md` | Repo front door |
| `docs/V4_PTY_SWAP.md` | Plan for the swap (read this first if new) |
| `docs/V4_STATUS.md` | This doc — running progress |
| `app/src-tauri/src/core/` | Maestro PTY code (lifted, attributed) |
| `app/src-tauri/src/commands/terminal.rs` | New Tauri commands |
| `app/src-tauri/src/lib.rs` | Legacy v3 commands + new core registered |
| `ui/v3/index.html` | Main UI (massive — 8000+ lines) |
| `app/src/index.html` | Mirror of ui/v3/ that Tauri actually serves |

## Known issues

- `get_pane_state_v4` returns basic state (pane_id, pid, ram_mb, cpu_pct).
  Fields like `current_tool`, `todos`, `session_tokens`, `cost_usd` are not
  yet populated from the Rust side — they come from monitor.py's /tmp files.
  This is expected until the monitor.py v4 adaptation is done.
- CPU% in `get_pane_state_v4` is currently "any activity (1.0) vs idle (0.0)"
  from /proc/PID/stat jiffies — not a real instantaneous percentage. Will
  improve when monitor.py adaptation adds a proper psutil-backed path.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-05-17 | gmux-v4 will be a successor (not sibling) repo | User direction |
| 2026-05-17 | Scope: only swap PTY substrate, keep all v3 UI/features | Path A — incremental, low-risk |
| 2026-05-17 | Lift maestro PTY core under MIT attribution | Cross-platform, battle-tested |
| 2026-05-17 | Keep both old and new code paths during transition | Safe rollout; can A/B compare |
| 2026-05-17 | UI stays vanilla JS (no React) | Lifting v3 UI as-is is fastest |
| 2026-05-17 | v4-redirect errors (not silent no-ops) in tmux commands | Makes routing failures visible and debuggable in JS console |
| 2026-05-17 | find_gmux_script: gmux_v4 first, gmux-system second | Sidecars should use this repo's own backend when running from source |
| 2026-05-17 | get_pane_state_v4 falls back to file-backed state when PM has 0 sessions | Mixed-mode (some tmux, some v4 PTY) deployments work without changes |
