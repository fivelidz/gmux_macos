# v4 PTY migration — what's happening, in plain English

**Last updated:** 2026-05-17 (alpha.5)

This doc exists because the v4 PTY swap is genuinely confusing if you
just look at the code. It runs *two backends side-by-side* while we
migrate, and there's no single "v4 mode is on" switch in the UI yet.
This explains the plan, the current state, and the test path.

---

## TL;DR

| Question | Answer (today) |
|---|---|
| Does v4 PTY replace tmux completely? | **Eventually yes**, but right now both run side-by-side. |
| What does the user gain? | macOS + Windows support (tmux is Unix-only), faster spawn, no tmux dependency. |
| Why is it not the default yet? | The xterm.js per-pane renderer needs human-eyes verification first. |
| How do I turn v4 PTY on? | **Options → v4 Lab → tick the box.** That's it. New agents will use the new path. |
| What if I never tick the box? | Everything works exactly like v3 (tmux backend). No regression. |
| Are existing tmux panes affected? | **No.** Only the next "+ new agent" you create uses v4 if enabled. |

---

## Why "two backends side-by-side"?

A clean cutover would mean:
1. Rip out tmux.
2. Rewrite every agent-spawn / approve / interrupt path through the new PTY layer.
3. Test all of it on one platform.
4. Ship.

That's how you write bugs that brick the whole product. So instead:
1. Add the new PTY layer **alongside** the tmux one.
2. Add `_v4` sibling commands for every legacy command.
3. Gate the user-facing switch in **Options → v4 Lab**.
4. Each new agent picks the backend based on that flag.
5. Once verified, flip the default to v4 and start removing tmux.

Result: you can switch back to v3 by unticking a box. No data lost.

---

## The two backends, mapped

| Concern | v3 path (tmux) | v4 path (portable-pty) |
|---|---|---|
| Spawning a shell | `open_agent` writes `\x01c` (tmux prefix+c) into the single attached PTY, then types `cd <dir> && opencode\r`. Tmux opens a new window. | `open_agent_v4` calls `ProcessManager::spawn_shell(cwd)`. A fresh PTY is opened directly. No tmux involved. |
| Sending input | `pty_write` writes to the one tmux-attached PTY. | `write_stdin(session_id, data)` writes to the specific session. |
| Pane state | `monitor.py` polls `tmux list-panes` every 2s, writes JSON to `/tmp/gmuxtest-pane-state.json`. | `get_pane_state_v4` calls `ProcessManager::get_all_session_pids()` and returns the same JSON shape. |
| Approve / reject permission | `approve_agent` POSTs to OpenCode HTTP API, falls back to `tmux send-keys y` at window N. | Same `approve_agent` works for v3 panes. For v4 panes, the HTTP API path still works (no tmux needed). |
| Interrupt / cancel | NEW: `interrupt_agent` POSTs `/abort`, falls back to `tmux send-keys Escape`, then Ctrl-C. | Same `interrupt_agent` — when `pane_id` is a v4 session, we'll route through `write_stdin(0x1B)` (TODO). |
| Sub-agent spawn | `spawn_sub_agent` (tmux prefix+c + window rename) | `spawn_sub_agent_v4` (fresh PTY, no rename needed) |
| Provider auth (`opencode auth login`) | `login_provider` writes `\x01c` + `opencode auth login <id>\r` to tmux. | `login_provider` in v4 mode spawns `opencode auth login` as a detached subprocess (no PTY at all — it manages its own browser flow). |
| Process tracking | psutil walks `tmux` process tree. | `ProcessManager::get_session_pid` returns the direct PID; psutil walks its children. |

**Critical invariant:** the user-facing JSON contract
(`/tmp/gmuxtest-pane-state.json` etc.) doesn't change. `get_pane_state_v4`
returns the same shape so the dashboard / agent monitor doesn't need
two different parsers.

---

## What we shipped in alpha.5

- ✅ `ProcessManager` (cross-platform PTY layer, lifted from maestro under MIT)
- ✅ `spawn_shell`, `write_stdin`, `resize_pty`, `kill_session`,
  `kill_all_sessions`, `get_backend_info`, `pty_ping` (raw PTY commands)
- ✅ `open_agent_v4`, `spawn_sub_agent_v4` (agent-spawning siblings)
- ✅ `get_pane_state_v4` (returns same JSON shape for the dashboard)
- ✅ `interrupt_agent` (Esc/Cancel, works for both v3 and v4 paths)
- ✅ `is_v4_mode()` helper: detects `GMUX_V4_PTY=1` env var or absent tmux
- ✅ `open_project` / `spawn_sub_agent` / `login_provider` redirect to v4
  siblings when v4 mode is on
- ✅ xterm.js per-pane wired (Tasks/Chat/Hardware/**Terminal** view modes)
- ✅ `launch-v4.sh --test` runs 13 headless checks (all green)
- ✅ Standalone PTY smoke test (`cargo run --example pty_smoke`) passes
- ✅ Release binary builds: 17 MB exec + .deb + .rpm + .AppImage

## What's NOT done yet

In rough dependency order:

1. **Human-eyes verification** of the xterm.js per-pane rendering.
   The infrastructure exists; we need someone to open the window, tick
   the box in Options → v4 Lab, press N, and watch a real shell prompt
   stream into the xterm. (Cannot be done headlessly.)
2. **`interrupt_agent` v4 route**: currently the function takes a
   `pane_id` parameter that's reserved for sending `0x1B` (Esc) directly
   via `write_stdin` for v4 panes. We use the tmux path for now since v4
   panes don't exist in production yet.
3. **monitor.py adaptation**: monitor.py still polls `tmux list-panes`.
   Once v4 panes start existing, the dashboard needs both: tmux panes
   (from monitor.py's file) AND v4 panes (from `get_pane_state_v4`).
   The agreed approach: merge the two on the JS side, since both return
   the same JSON shape.
4. **Session persistence**: today's session-restore uses tmux-resurrect.
   v4 will use `~/.config/gmux/sessions.json` — a snapshot of `{id, cwd,
   agent_type, model}` tuples. On startup, we re-spawn the shells; the
   user re-issues commands. (We don't try to replay terminal output.)
5. **Make v4 the default**: tick the box automatically once 1–4 are
   green for one full week of dogfooding.
6. **Remove the tmux dependency from the install script**. tmux becomes
   "optional, used for headless mode only".

---

## How to test (the simplest possible path)

```bash
# 1. Build (once)
cd ~/projects/gmux_v4
./scripts/launch-v4.sh --test         # confirms 13/13 headless checks pass

# 2. Launch the app
./scripts/launch-v4.sh                # opens the Tauri window

# 3. Inside the window:
#    Options ⚙ → "v4 Lab" tab → tick "Enable v4 PTY for new agents"
#    Press N (new agent), pick a directory, click Create
#    The new pane should auto-switch to "Terminal" view and show a real
#    shell prompt. Type 'ls' and you should see file output stream back.
#
# 4. Cycle the view mode with Tab — Tasks / Chat / Hardware / Terminal
#    should all be reachable for that pane.
#
# 5. Try the new Stop button in the chat panel for a working agent.
#    It sends Esc via the tmux path today; v4 path is a one-line change
#    once we want to flip it on.

# 6. If something looks wrong, disable v4 by unticking the box in Options.
#    New agents go back to tmux. No restart needed. No data lost.
```

---

## What if the user never reads this doc?

That's fine. The app works exactly like v3 by default. The new code
sits dormant until **Options → v4 Lab** is ticked. The visible UI
changes (Stop button, model badges, "Active/All" toggle, better
chat-input layout, the right "Connect Providers" link) are independent
of the v4 PTY swap — they work on the v3 backend today.

---

## Why portable-pty (not tmux's library, not pty.c)?

- **Cross-platform** — Windows ConPTY, macOS, Linux all work from one API
- **Used in maestro** in production — battle-tested at scale
- **MIT-licensed**, lifted with attribution at the top of every file
- **Async-safe** — the reader thread feeds a bounded mpsc channel that
  a tokio task drains into Tauri events, so PTY output never blocks the
  UI thread
- **Correct UTF-8 handling** — multi-byte sequences (emoji, CJK, Nerd
  Font icons) that straddle 4 KB read chunks are buffered properly,
  no `U+FFFD` corruption

See `app/src-tauri/src/core/process_manager.rs` for the lifted code
with the maestro attribution header.

---

## Glossary of "v4" things

| Term | What it means |
|---|---|
| **v4 PTY** | The new per-pane PTY managed by Rust (`ProcessManager`) instead of by tmux. |
| **v4 mode** | When `GMUX_V4_PTY=1` is set OR `localStorage.gmux_v4_pty='1'` OR Options → v4 Lab is ticked. |
| **v4 Lab** | The Options panel tab where you toggle v4 mode. |
| **v4 session** | A PTY owned by `ProcessManager`. Has an integer session_id (1, 2, 3…). Different from a tmux session. |
| **xterm.js per pane** | The view mode where each pane card embeds a real terminal emulator. Currently only renders for v4 sessions (no v3 fallback — they live in tmux windows). |

If you're a new agent on this codebase: read this doc first, then
`V4_STATUS.md` for the running checklist of what's done.
