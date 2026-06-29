# gmux v4 — alpha.17 roadmap

**Date:** 2026-05-19
**Author:** autonomous agent session following user direction

This doc captures the two new roadmap items the user called out, plus the
known near-term backlog. Alpha.17 will focus on **session restore** as the
main deliverable. SSH/cloud is alpha.18+.

---

## Feature 1 — Session restore (alpha.17)

### User request
> *"It would also be good to have some kind of restore function for claude
> code AI. A system where the agent panels can be remembered and restarted
> easily if the computer is closed or the panel is closed. this can work by
> firing off the /resume commands or something to bring back the relevant
> chats."*

### Problem
When gmux is closed (or the computer sleeps/reboots), all the agent panes
in the tmux session survive **as tmux windows** but:
- the Tauri UI loses its layout state (which session was selected, which
  pane was focused)
- claude-code processes may still be running (tmux kept them alive) OR
  they may have exited after the user's last message
- There is no one-click way to bring back the gmux view and resume
  conversations that were in flight

### Design

#### Step 1 — Manifest (backend, no UI change)
`monitor.py`'s aggregate worker already writes `/tmp/gmuxtest-pane-state.json`
every 10s. We add a **session manifest** at a durable location (not `/tmp`):

```
~/.local/share/gmuxtest/session_manifest.json
```

Contents per pane:
```json
{
  "pane_id": "%1",
  "window_name": "my_project",
  "working_dir": "/home/user/projects/my_project",
  "state": "waiting",
  "model": "claude-sonnet-4-5",
  "api_port": 9001,
  "session_id": "abc123",
  "tmux_session": "gmux",
  "tmux_window": 3,
  "last_message_ts": 1716000000,
  "last_message_preview": "I've finished the refactor. Run the tests...",
  "todo_done": 8,
  "todo_total": 10,
  "snapshot_ts": 1716000010
}
```

Written every 30s while the app is running.

#### Step 2 — Restore Tauri command (Rust)
A new `restore_session(pane_id)` command in `lib.rs`:
1. Reads `session_manifest.json` for the entry
2. If the tmux window still exists — focuses it (no respawn needed)
3. If the tmux window is gone — calls `open_agent_v4(name, dir, model)`
4. After the agent is spawned + ready, sends `/resume` via `send_to_agent`

The `/resume` slash command (claude-code built-in, also works in qalcode)
causes claude-code to summarise its last session from its internal history
and pick up where it left off.

#### Step 3 — Restore UI (in Options panel + a dedicated restore shelf)
In the Options overlay, add a new tab **"Restore"** showing:
- list of remembered pane entries from `session_manifest.json`
- each row shows: agent name, working dir, last message preview, last
  active timestamp, todo progress (8/10)
- status indicator: 🟢 still alive / 🟡 tmux window exists but idle /
  🔴 tmux window gone (needs respawn)
- one **Resume** button per row → calls `restore_session(pane_id)`

Also add a **"Restore last session"** button to the topbar's Options group
that is only visible after a fresh launch (disappeared from current layout
= needs restore).

#### Step 4 — Auto-snapshot on close / sleep
The Rust `on_window_event` hook already fires on `CloseRequested`. Add a
final manifest snapshot there so the data is up-to-date at the moment of
closure.

### Implementation scope
- `backend/status/monitor.py` — 30s manifest writer (≈ 30 lines)
- `app/src-tauri/src/lib.rs` — `restore_session` + `list_saved_sessions`
  commands (≈ 80 lines)
- `app/src/index.html` — Restore tab in Options (≈ 200 lines CSS+JS)
- `app/src-tauri/capabilities/default.json` — no new permissions needed
  (already have `fs` access from the `core:default` set)

---

## Feature 2 — SSH + Cloud computer support (alpha.18+)

### User request
> *"A system for the tauri browser to also ssh into another computer or use
> a cloud service with a cloud computer is on the roadmap too."*

### Design concept

The gmux backend (`monitor.py` + HTTP server on :8769) is already host-
agnostic — it reads from tmux and writes JSON. The frontend speaks to it
via `http://127.0.0.1:8769`. Making gmux work against a REMOTE host is
a matter of:

1. **SSH tunnel**: `ssh -L 8769:127.0.0.1:8769 <remote>` — the Tauri app
   connects to `http://127.0.0.1:8769` as normal but the traffic is tunnelled
   to the remote box. Monitor.py must be running on the remote.

2. **Cloud service**: same tunnel, or a tiny HTTPS reverse-proxy on the
   remote (Caddy / nginx / Tailscale serve).

3. **UI additions** needed:
   - "Connect to remote" field in Settings → Providers (or new "Remote" tab)
   - Host selector (`localhost` | `myserver.ssh` | `<IP>`) stored in
     `localStorage`
   - Status indicator: tunnel alive? (ping /health at the configured host)
   - `GMUX_API` env variable already supported in the JS health probe
     (`const apiBase = window.GMUX_API || 'http://127.0.0.1:8769'`) —
     just need a UI to set it and a tunnel manager in the Rust layer

4. **Rust layer** for SSH tunnel management:
   - `spawn_ssh_tunnel(host, port, key_path)` Tauri command that runs
     `ssh -N -L 8769:127.0.0.1:8769 <host>` as a managed subprocess
   - `close_ssh_tunnel()` kills it
   - Tunnel PID tracked in SharedState, health-checked every 30s

5. **Cloud-computer integration** (e.g. EC2, Hetzner, Fly.io):
   - Same tunnel pattern
   - Or: gmux monitor.py deployed as a systemd service, exposed via
     Tailscale (zero-config, encrypted, device-level auth)
   - Or: WebSocket relay layer (for NAT traversal without SSH keys)

### Prerequisites for alpha.18
- Alpha.17 (session restore) shipped and tested
- SSH host can run tmux + claude-code + monitor.py (same as local)
- Tailscale recommended for cloud (handles NAT + certs automatically)

---

## Other queued items (alpha.17/18 backlog)

| Item | Origin | Priority |
| --- | --- | --- |
| In-app OAuth flow for Claude token | User: "opencode oauth system" | high |
| maestro tamagotchi creature in sidebar | Referenced in HANDOVER | low |
| Agent Monitor verification | Needs user click | medium |
| Pane session persistent labels | Sidebar agent names survive restarts | high — covered by session restore |
| Voice → agent routing (multi-agent PTT) | BRIDGE_DESIGN.md | medium |
| Phone PWA (responsive, HTTPS) | NEXT_ACTIONS.md stream 3 | medium |

---

## Immediate next (alpha.17-dev — what to build now)

1. `backend/status/monitor.py` — manifest writer
2. `lib.rs` — `list_saved_sessions` + `restore_session` commands
3. `index.html` — Restore tab in Options

Starting with #1 (backend), then #2 (Rust), then #3 (UI).
