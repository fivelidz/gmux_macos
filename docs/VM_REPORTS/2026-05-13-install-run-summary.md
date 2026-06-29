# VM install / run summary — 2026-05-13

State of the gmux-system install on the **sandbox VM** (`192.168.122.100`,
user `agent`, CachyOS arm64 QEMU).

## TL;DR

✅ Backend monitor running with v3.6.2 code, all 5 producer files writing
✅ Browser UI accessible from host at `http://192.168.122.100:5550/ui/v3/index.html`
✅ wezterm installed and works on the VM (use it instead of ghostty)
⚠ ghostty installed but crashes (the LLVM AVX2 issue we already knew about)
✅ opencode-ai 1.14.48 installed via `bun install -g opencode-ai`
❌ Tauri desktop app NOT running (no display server, expected)

## Detailed status

### Hardware / env
| Property | Value |
|---|---|
| Host | sandbox VM via QEMU virtio |
| Uptime | 1 day, 7 hrs (was running before this session) |
| Display | none (`XDG_SESSION_TYPE=tty`) |
| Shell | fish (this matters for SSH-then-run patterns — must wrap in `bash -lc`) |
| Python | 3.14 (system) |
| tmux | 3.6a |

### Terminals available
| Terminal | Status | Notes |
|---|---|---|
| **wezterm** | ✅ `/usr/bin/wezterm` works | Use this as the daily-driver terminal on the VM |
| **ghostty** | ❌ `/usr/bin/ghostty` present but crashes | LLVM AVX2 abort on virtio GPU. Documented in `VM_PROTOCOL.md` |
| **tmux** | ✅ works | Hosts the `gmux` session that monitor.py tracks |

### Critical install gotcha — opencode package name

The user attempted `bun install -g opencode` originally. That fails with a
404 because **the npm package is called `opencode-ai`, not `opencode`**.

```bash
# WRONG — what the docs implied:
bun install -g opencode    # → 404

# CORRECT:
bun install -g opencode-ai # → installs binary at ~/.bun/bin/opencode
```

After install, the executable IS called `opencode` (not `opencode-ai`),
but the package name on npm is `opencode-ai`. This caused the VM-AI's
earlier install attempts to silently fail.

**Fix applied to `INSTALL_GUIDE.md` + `DEPENDENCIES.md`:** updated all
bun install commands to use `opencode-ai`.

### What runs on the VM right now

```
process               status   port    note
─────────────────────────────────────────────────────────────
monitor.py            ✅ up    8769    state API + SSE
http.server           ✅ up    5550    serves UI HTML
voice daemon          ⏸ off    -       no audio device available
session_restore       ⏸ off    -       not started (optional)
tmux 'gmux' session   ✅ up    -       2 windows, hosts the panes
opencode agents       ⏸ none   -       no agents currently running
```

### Producer files (the dashboard's data)

```
/tmp/gmuxtest-pane-state.json     ~5KB    live (1s)
/tmp/gmuxtest-services.json       14B     live (10s)
/tmp/gmuxtest-window-names.json   41B     persistent
/tmp/gmuxtest-activity.json       2B      empty (no agents yet)
/tmp/gmuxtest-files.json          2B      empty (no agents yet)
```

### Verified from the HOST

```bash
curl http://192.168.122.100:8769/health         # → ok
curl http://192.168.122.100:8769/api/state | jq # → JSON, valid
curl http://192.168.122.100:5550/ui/v3/index.html -o /dev/null -w '%{http_code}'  # → 200
```

You can open `http://192.168.122.100:5550/ui/v3/index.html` in any host
browser and the UI will load. Live data flows when you set
`window.GMUX_API = 'http://192.168.122.100:8769'` in the console (or wait
for v3.7 `?api=` URL param).

### Tauri desktop app — NOT viable on this VM

- No display server → Tauri can't create a window even with `Xvfb`
- Even if Xvfb worked, ghostty's LLVM AVX2 crash would hit WebKitGTK's
  GL backend too
- **This is fine.** The VM's role is backend + browser-UI testing.
  Tauri runs on the host. Browser on the host points at VM's `:8769`.

### What worked end-to-end today

1. rsync deploy host → VM: 2 min, ~3 MB of source files
2. `bun install -g opencode-ai` install: 30 seconds
3. `setsid python3 backend/status/monitor.py & disown`: starts and persists
4. `curl http://127.0.0.1:8769/health` from VM: `ok` immediately
5. UI HTTP server on `:5550 --bind 0.0.0.0` reachable from host LAN

### What still needs to be tested

- Live agent: `tmux new-window -t gmux -n testagent; tmux send-keys ... opencode`
  inside that window, then watch activity flow into the dashboard.
- The new auth wizard in v3.6.0: `opencode auth login anthropic` from a
  VM terminal completes the OAuth flow (would need browser on the host to
  click the URL).
- The new folder drill-in (v3.6.2): browser → connect to VM's data →
  navigate the file tree.

### `setsid` not `nohup` — important VM pattern

```bash
# Doesn't survive SSH disconnect on this VM:
nohup python3 backend/status/monitor.py &

# Does survive:
setsid python3 backend/status/monitor.py </dev/null >/tmp/x.log 2>&1 & disown
```

This is now in `scripts/launch.sh`'s monitor-spawn block and noted in
`VM_PROTOCOL.md`.

### Coordination with the VM-AI

There IS an AI agent running on the VM ("vmai") per
`docs/VM_AGENT_COORDINATION.md`. It hasn't dropped a report at
`docs/VM_REPORTS/` yet this session — pulled but empty other than the
host-side handoff note.

Open questions to the VM-AI (when it returns):
1. Was the original `bun install -g opencode` failure noticed? (Yes — your
   silent install attempt would have 404'd.) Confirm `opencode-ai` works.
2. Have you started any agents in the VM's tmux session yet, or is it
   just the empty `gmux` session from May 12?
3. Are there any system-level changes you needed (sysctl, ulimits, etc.)
   to keep monitor.py stable across reboots? Document in your report.

## Action items for next session

- [ ] Start an opencode agent in the VM tmux to populate activity/files
- [ ] Verify the dashboard's new drill-in works against VM data
- [ ] Add `opencode-ai` correction to INSTALL_GUIDE (done in this commit)
- [ ] Consider writing a `scripts/install-vm.sh` that does the whole
      install end-to-end in one command (see DEPLOY_PORTABLE.md plan)
