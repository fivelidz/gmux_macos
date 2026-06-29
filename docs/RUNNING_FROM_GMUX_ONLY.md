# "Should I shift to running things entirely out of the gmux Tauri app?"

You asked whether to use the gmux Tauri app as your daily driver for all
agent work next session. Honest answer:

## One-time setup: re-point the `gmux` shell command (v3.6.4)

If you've been using gmux for a while, `gmux` from terminal probably runs
the **old** `~/projects/gmux/scripts/gmux` script. That script starts a
separate monitor + Python services that compete with the gmux-system
Tauri stack — which is why you sometimes saw two `monitor.py` processes
racing on the same `/tmp/gmuxtest-*.json` files.

Run this **once** to make `gmux` launch the current gmux-system:

```bash
ln -sf ~/projects/gmux-system/scripts/gmux ~/.local/bin/gmux
hash -r 2>/dev/null   # bash; fish reloads PATH automatically
```

Verify:
```bash
which gmux                 # → ~/.local/bin/gmux
readlink ~/.local/bin/gmux # → ~/projects/gmux-system/scripts/gmux
gmux help                  # → usage from the new entry point
```

The new `gmux` command supports:
- `gmux` — launch Tauri (default)
- `gmux --browser` — browser-only mode
- `gmux --check` — sanity check, no launch
- `gmux --backend-only` — monitor + http server, no UI
- `gmux attach` — tmux attach to the gmux session
- `gmux status` — one-shot pane state dump
- `gmux help` — usage

To revert: `ln -sf ~/projects/gmux/scripts/gmux ~/.local/bin/gmux`

---

## Recommendation — **YES, with one caveat**

**Use gmux Tauri as your primary launcher and monitor.** It's now in a
state where it can replace ad-hoc `tmux new-window + opencode` workflows
for most cases. The caveat: keep one regular terminal (ghostty/kitty/etc.)
open as a fallback for the few rough edges that remain.

---

## What works well enough to rely on (as of v3.6.0)

| Capability | Status | Notes |
|---|---|---|
| **Launch a new agent in any folder** | ✅ solid | Press `N`, type path, agent starts |
| **Pre-fill last-used folder per session** | ✅ solid | Saves you typing |
| **Window names reflect real projects** | ✅ solid | No more "fish" labels |
| **Live monitoring of all agents** | ✅ solid | Pane grid + Agent Monitor flowchart |
| **Real-time tool-call activity** | ✅ solid | act:/files: counters update |
| **Provider auth via UI** | ✅ new this session | Options → Providers tab works |
| **First-launch wizard for unauthed users** | ✅ new | Auto-opens on first run |
| **Approve / reject permissions** | ✅ solid | Click-to-approve, Space-key works |
| **Tmux session-restore (window names persist)** | ✅ solid | Survives reboot |
| **PTY-attached terminal in the main window** | ✅ solid | You can type into agents directly |
| **Voice mode (faster-whisper STT)** | ✅ ok | Works when daemon is up |
| **Gesture mode (hand tracking)** | ⚠ unreliable | MediaPipe model fetches from CDN if not local |
| **Multi-session pane filtering** | ✅ solid | Tabs switch between sessions cleanly |

## What's still rough — don't rely on Tauri-only for these

| Capability | Status | Workaround |
|---|---|---|
| **Memory aggregator** | ❌ not implemented | `/tmp/gmuxtest-memory.json` stays empty — dashboard memory tab will show "no memories yet" |
| **MediaPipe gestures on first run** | ⚠ may need internet | Pre-bundle `models/hand_landmarker.task` if going offline |
| **Tauri build (release binary)** | ⚠ untested in this repo | Dev mode works; release should also but verify before claiming "production-ready" |
| **macOS support** | ❌ untested | See `DEPLOYMENT_TARGETS.md` — likely works but 6 small platform-specific fixes needed |
| **Multi-machine sync** | ❌ not implemented | One auth.json per machine; if you switch laptops you re-auth |
| **PR mode for the chat panel** | ⚠ partial | Markdown renders; complex inline images don't always |

## Concrete daily-driver checklist

For your next test session, run gmux Tauri exclusively and use it for:

1. **Launching every new agent** — instead of `cd ~/projects/X && opencode`,
   press `N` in gmux. You'll instantly see the agent in the grid and the
   Agent Monitor.

2. **Switching context between projects** — the session tabs + window tabs
   let you bounce between agents without losing where each one is.

3. **Approving permissions** — instead of focusing the agent's pane and
   typing `y\n`, click the orange-bordered pane or press Space when it's
   selected.

4. **Viewing real-time tool activity** — open the Agent Monitor (Ctrl+Alt+D
   or Views ▾ → 🧠 Agent Monitor). Watch the flowchart populate.

5. **Adding providers** — Options → Providers → Connect. Should take ~30s
   per OAuth flow.

For things to STILL keep a regular terminal open for:

1. **Running `git` / `pytest` / `npm` directly** when you don't want it
   captured in an agent pane. (Or just `tmux attach -t gmux` from any
   terminal and use the gmux session manually.)

2. **Debugging gmux itself** — `tail /tmp/gmux-monitor.log`, killing
   stuck processes, etc.

3. **System administration** — sudo prompts inside Tauri's PTY work but
   are easier to type into a real terminal.

## What to watch for and report

Test these scenarios and tell us if they break:

- [ ] Launch 5+ agents in different projects in one session. Memory leak?
      Lag in the grid?
- [ ] Leave Tauri open overnight. Does monitor.py still respond next
      morning? Does the dashboard still render?
- [ ] Provider auth: click Connect → tmux window opens → complete the OAuth
      → list refreshes within 60s without any extra action.
- [ ] Switch sessions while agents are mid-task. Do the panes from the
      hidden session keep their state?
- [ ] Run a long-running tool call (Task that delegates to sub-agents).
      Does the Agent Monitor render the parent → child correctly?

## When to fall back

If gmux Tauri crashes, hangs, or fails to start during your test session:

```bash
# Sanity check
~/projects/gmux-system/latest_version_test/launch_tauri.sh --check

# Nuclear restart
pkill -f gmux-system/backend
pkill -f gmuxtest                  # the Tauri binary name
tmux kill-session -t gmux
~/projects/gmux-system/scripts/launch.sh
```

If even that fails: go back to manual `tmux new-window + opencode`, file
the failure in `docs/VM_REPORTS/<date>-issue.md` with the log content,
and we'll fix forward next session.

---

## Bottom line

The friction of running everything through gmux Tauri vs. raw terminal is
now **lower than the value** of having all agents visible, monitored, and
controllable from one window. Run it. If it falls over, the fallback is
30 seconds away and the failure tells us what's still broken.

The biggest behavioural shift: stop typing `cd ~/projects/X && opencode`
in your shell. Press `N`. Type the path. Done.
