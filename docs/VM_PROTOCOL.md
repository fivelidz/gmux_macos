# gmux-system — VM Deploy & Test Protocol

**Standard procedure for deploying and testing gmux-system on the sandbox VM.**  
Version 1.0 — 2026-05-13

---

## VM Spec

| Property | Value |
|----------|-------|
| Hostname | `sandbox` (configured in `~/.ssh/config`) |
| IP | 192.168.122.100 |
| User | `agent` |
| OS | CachyOS Linux, kernel 7.0.2-1-cachyos |
| Shell | fish (use `bash -c "..."` for one-liners) |
| Auth | Passwordless SSH key — `ssh sandbox 'echo ok'` must work before starting |
| Display | NONE — `XDG_SESSION_TYPE=tty`, headless |

---

## What Works on VM vs Host

| Feature | VM | Host |
|---------|----|----|
| `monitor.py` backend :8769 | ✅ | ✅ |
| `http.server` UI :5550 | ✅ | ✅ |
| tmux pane tracking | ✅ | ✅ |
| Live data in browser | ✅ (loopback) / ⚠️ (remote needs `GMUX_API`) | ✅ |
| Tauri desktop app | ❌ no cargo/display | ✅ |
| Ghostty terminal | ❌ LLVM AVX2 crash on QEMU virtio GPU | ✅ |
| Voice (sounddevice) | ❌ no audio | ✅ |
| Gestures (MediaPipe) | ❌ no camera | ✅ |
| opencode CLI | ❌ not on npm | ✅ (via bun from private repo) |

---

## Step 0 — Pre-flight

```bash
# From HOST — verify SSH works
ssh sandbox 'echo SSH_OK'

# Verify VM has required tools
ssh sandbox bash -c "python3 --version && tmux -V && echo TOOLS_OK"

# Check if anything is already running (avoid port conflicts)
ssh sandbox bash -c "ss -tlnp 2>/dev/null | grep -E '8769|5550' || echo PORTS_FREE"
```

---

## Step 1 — Deploy Code

```bash
# Always rsync — never git clone (VM has no GitHub SSH key)
rsync -av \
  --exclude .git \
  --exclude node_modules \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'app/src-tauri/target' \
  --exclude 'models/hand_landmarker.task' \
  ~/projects/gmux-system/ sandbox:~/projects/gmux-system/

# Verify
ssh sandbox bash -c "ls ~/projects/gmux-system/backend/status/monitor.py && echo DEPLOY_OK"
```

**When to re-deploy:**
- After any change to `backend/` or `ui/`
- Before every test session
- The rsync is idempotent — safe to run any time

---

## Step 2 — Install Python Dependencies

Only needed once per VM (or after a Python upgrade):

```bash
ssh sandbox bash -c "pip install --break-system-packages --user psutil websockets requests numpy 2>&1 | tail -5"

# Verify
ssh sandbox bash -c "python3 -c 'import psutil, websockets, requests, numpy; print(\"DEPS_OK\")'"
```

**Do NOT install:** `sounddevice`, `mediapipe`, `cv2` — they require audio/camera hardware.

**Note:** `python3.11` on this VM is a symlink to Python 3.14 — this is fine.

---

## Step 3 — Start tmux Session

```bash
ssh sandbox bash -c "
  tmux kill-server 2>/dev/null || true
  sleep 0.5
  tmux new-session -d -s gmux -n shell
  echo TMUX_OK
"
```

To add simulated agent windows (for pane-tracking tests):
```bash
ssh sandbox bash -c "
  tmux new-window -t gmux -n agent1
  tmux send-keys -t gmux:agent1 'echo agent1_ready' Enter
  tmux new-window -t gmux -n agent2
  tmux send-keys -t gmux:agent2 'sleep 9999' Enter
"
```

---

## Step 4 — Start monitor.py

```bash
# Kill any existing monitor
ssh sandbox bash -c "pkill -f 'monitor.py' 2>/dev/null || true; sleep 1"

# Start fresh
ssh sandbox bash -c "
  cd ~/projects/gmux-system
  nohup python3 backend/status/monitor.py > /tmp/gmux-monitor.log 2>&1 &
  sleep 3
  tail -5 /tmp/gmux-monitor.log
"
```

Expected output:
```
[monitor] HTTP state server on :8769  — /api/state  /api/stream  /health
[gmuxtest-status] Event-driven monitor → /tmp/gmuxtest-pane-state.json
[gmuxtest-status] SSE listeners + 2.0s tmux poll
[gmuxtest-status] Aggregate worker started (10.0s cycle)
```

---

## Step 5 — Start UI HTTP Server

```bash
ssh sandbox bash -c "
  pkill -f 'http.server 5550' 2>/dev/null || true
  cd ~/projects/gmux-system
  nohup python3 -m http.server 5550 > /tmp/gmux-ui.log 2>&1 &
  sleep 1
  echo UI_SERVER_OK
"
```

---

## Step 6 — Verify from VM (loopback)

```bash
# Health check
ssh sandbox bash -c "curl -s http://127.0.0.1:8769/health"
# Expected: ok

# State check
ssh sandbox bash -c "curl -s http://127.0.0.1:8769/api/state | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d),\"panes\",[p[\"window_name\"]+\":\"+p[\"state\"] for p in d.values()])'"

# UI check
ssh sandbox bash -c "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5550/ui/v3/index.html"
# Expected: 200
```

---

## Step 7 — Verify from Host

```bash
# Health from host machine
curl -s --max-time 3 http://192.168.122.100:8769/health
# Expected: ok

# State from host
curl -s --max-time 3 http://192.168.122.100:8769/api/state | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d),'panes')"

# UI from host
curl -s -o /dev/null -w "%{http_code}\n" --max-time 3 \
  http://192.168.122.100:5550/ui/v3/index.html
# Expected: 200
```

Open in host browser: `http://192.168.122.100:5550/ui/v3/index.html`

---

## Step 8 — Connect Browser to VM Backend

The UI defaults to `http://127.0.0.1:8769` which on the host browser means the
**host's own** loopback — so it will use the host's monitor.py (or fallback to mocks).

To point the browser at the **VM's** backend:

**Option A — Browser console (quick):**
```js
window.GMUX_API = 'http://192.168.122.100:8769';
location.reload();
```

**Option B — URL parameter (if implemented):**
```
http://192.168.122.100:5550/ui/v3/index.html?api=http://192.168.122.100:8769
```
*(Not yet implemented — tracked in HANDOVER.md future plans)*

**Option C — Remote shim page:**
```bash
# Create once on VM
ssh sandbox bash -c "cat > ~/projects/gmux-system/ui/v3/remote.html << 'EOF'
<script>window.GMUX_API='http://192.168.122.100:8769';</script>
<script>location.replace('/ui/v3/index.html');</script>
EOF"
# Then open: http://192.168.122.100:5550/ui/v3/remote.html
```

---

## Step 9 — Test Checklist

After setup, verify each row before marking the session complete:

| Check | Command / Action | Expected |
|-------|-----------------|----------|
| SSH | `ssh sandbox 'echo ok'` | `ok` |
| Monitor running | `curl 192.168.122.100:8769/health` | `ok` |
| Panes tracked | `/api/state` returns ≥1 pane | JSON with pane list |
| UI accessible | HTTP 200 on `:5550/ui/v3/index.html` | 200 |
| UI pane grid | Open in browser | Grid renders |
| Live data | Set `window.GMUX_API`, reload | Real pane names visible |
| SSE stream | `/api/stream` held open | Keeps connection, sends updates |
| New pane appears | `tmux new-window -t gmux -n test` | Appears in grid within 4s |
| Monitor log clean | `cat /tmp/gmux-monitor.log` | No Python errors |
| Activity feed (v3.5) | `cat /tmp/gmuxtest-activity.json \| head -c 80` | `[]` initially, fills as agents run tools |
| Files map (v3.5) | `cat /tmp/gmuxtest-files.json \| head -c 80` | `{}` initially, fills as file edits occur |

---

## v3.5 — Agent Monitor (dashboard) verification

The dashboard window only renders inside Tauri (which the VM cannot run).
What the VM CAN do is verify the **producers** that feed the dashboard:

```bash
# All five producer files must exist after ~5s of monitor uptime
ssh sandbox bash -c "ls -la /tmp/gmuxtest-*.json"
# Expected:
#   gmuxtest-pane-state.json   (agents)
#   gmuxtest-services.json      (services flags)
#   gmuxtest-window-names.json  (name cache)
#   gmuxtest-activity.json      (tool events, may be [])
#   gmuxtest-files.json         (file touches, may be {})

# Force some activity to populate the feed (only works if opencode is running
# in one of the tmux panes — which it usually isn't on a headless VM).
# For a synthetic test, the dashboard's "mock" mode in serve.sh works fine
# without any of these producers — see app/src/dashboard/serve.sh.
```

On the host, after rsyncing the latest code, the dashboard window opens via:
- The 👁 Views ▾ dropdown in the toolbar → 🧠 Agent Monitor, OR
- Ctrl+Alt+D global shortcut

It listens to four Tauri events emitted by the Rust state-poll thread:
`gmux-state`, `memory-update`, `activity-tick`, `files-update`. The HUD in
the dashboard's top-right corner shows live tick counters per stream.

---

## Teardown

```bash
# Stop all gmux processes on VM
ssh sandbox bash -c "
  pkill -f 'monitor.py' 2>/dev/null
  pkill -f 'http.server 5550' 2>/dev/null
  tmux kill-server 2>/dev/null
  echo TEARDOWN_OK
"
```

---

## Known VM Limitations (do not attempt)

| Thing | Why it fails | Error |
|-------|-------------|-------|
| Tauri / Ghostty | No GPU, no display server | Ghostty: LLVM AVX2 abort; Tauri: no cargo |
| `opencode` CLI | Not on npm registry | 404 on bun/npm install |
| Voice daemon | No audio input (`sounddevice` uninstallable) | ModuleNotFoundError |
| Gestures | No `/dev/video*`, no MediaPipe | ModuleNotFoundError |
| `git clone` from GitHub | No SSH key on VM | Host key verification failed |

---

## Troubleshooting

**Monitor won't start:**
```bash
ssh sandbox bash -c "python3 -c 'import psutil, websockets' && echo DEPS_OK || echo DEPS_MISSING"
# If DEPS_MISSING: run pip install step again
```

**Port 8769 in use:**
```bash
ssh sandbox bash -c "ss -tlnp | grep 8769"
ssh sandbox bash -c "fuser -k 8769/tcp 2>/dev/null || pkill -f monitor.py"
```

**No panes in /api/state:**
```bash
# Check tmux is running
ssh sandbox bash -c "tmux list-sessions"
# If no sessions: create one (Step 3)
```

**UI loads but shows mocks only:**
- Set `window.GMUX_API` in browser console (Step 8)
- Check host firewall isn't blocking 8769 from host to VM

**VM IP changed:**
- Update `~/.ssh/config` on host: `HostName 192.168.122.XXX`
- All curl/rsync commands auto-pick up the new IP via the `sandbox` alias
