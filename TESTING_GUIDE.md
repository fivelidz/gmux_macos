# gmux-system — Testing Guide

**Last updated:** 2026-05-12 (v3.2)

Best approach for testing the system after edits.

---

## TL;DR — fastest test loop

1. Edit `~/projects/gmuxtest/UI_creation_independent/v2/index.html`
2. Sync (one command — see VERSION_CONTROL.md)
3. Browser: hard-reload `http://localhost:5550/v2/index.html` (Ctrl+Shift+R)
4. Tauri: it auto-reloads via HMR — wait ~1s

**Why browser first:** Vite/WebKitGTK reload in Tauri can be slow.
The browser reload is instant and gives proper DevTools.

---

## The "quick sanity check" — 30 seconds

```bash
echo "=== Backend health ==="
curl -s http://127.0.0.1:8769/health
echo ""
echo "=== Pane count ==="
curl -s http://127.0.0.1:8769/api/state | python3 -c "import json,sys; print(len(json.load(sys.stdin)),'panes')"
echo "=== Sessions ==="
curl -s http://127.0.0.1:8769/api/state | python3 -c "import json,sys; print(sorted(set(p.get('session_name','') for p in json.load(sys.stdin).values())))"
echo "=== One pane with real data ==="
curl -s http://127.0.0.1:8769/api/state | python3 -c "
import json,sys
d = json.load(sys.stdin)
for p in d.values():
  if p.get('model') and p.get('token_in',0) > 0:
    print(f'{p[\"window_name\"]:30s}  model:{p[\"model\"]:25s}  ram:{p[\"ram_mb\"]}MB  cpu:{p[\"cpu_pct\"]}%  tokens:{p[\"token_in\"]:,}  todos:{len(p.get(\"todos\",[]))}')
    break
"
```

If this prints real data — the backend is fine. Any UI issue is in the frontend.

---

## Test approach by what you changed

### UI-only changes (CSS, JS, HTML in v2/index.html)

**Use the browser.** Faster, better tooling, no Tauri compile.

```bash
# Start backend if not running
ss -tlnp | grep 8769 || python3.11 ~/projects/gmux-system/backend/status/monitor.py &

# Start HTTP server for the UI
pkill -f "http.server 5550" 2>/dev/null
cd ~/projects/gmuxtest/UI_creation_independent
nohup python3 -m http.server 5550 > /tmp/gmux-ui-server.log 2>&1 &

# Open in browser
xdg-open http://localhost:5550/v2/index.html
```

Then **F12 → Console** to see JS errors and **Network** tab to see if `/api/stream` is connected.

### Rust changes (lib.rs)

You need Tauri to test these. The good news is `cargo check` is fast (~3s).

```bash
# Verify it compiles
cd ~/projects/gmuxtest
cargo check --manifest-path src-tauri/Cargo.toml

# Restart Tauri (it doesn't hot-reload Rust)
pkill -f "tauri dev"; pkill -f "target/debug/gmuxtest"
sleep 2
GDK_BACKEND=x11 npm run tauri dev > /tmp/gmux-tauri.log 2>&1 &
sleep 8
tail -30 /tmp/gmux-tauri.log
```

### Python backend changes (monitor.py, voice daemon)

```bash
# Kill old + restart
pkill -f "gmux-system/backend/status/monitor.py"
sleep 1
python3.11 ~/projects/gmux-system/backend/status/monitor.py > /tmp/gmux-monitor.log 2>&1 &
sleep 4
# Verify
curl -s http://127.0.0.1:8769/api/state | python3 -c "import json,sys; print(len(json.load(sys.stdin)),'panes')"
```

---

## "Lazy session" test (when you've been away)

The system gets sluggish if it's been idle for many hours — usually because:
- The aggregator queue is full of stale SSE listeners on dead opencode panes
- The browser tab has accumulated rAF backpressure

**The clean-restart routine:**

```bash
# 1. Kill everything backend-side
pkill -f "gmux-system/backend"
pkill -f "gmux-monitor"
pkill -f "gmux_voice_daemon"
sleep 2

# 2. Start fresh
nohup python3.11 ~/projects/gmux-system/backend/status/monitor.py > /tmp/gmux-monitor.log 2>&1 &
nohup python3.11 ~/projects/gmux-system/backend/voice/gmux_voice_daemon.py --port 8770 > /tmp/gmux-voice.log 2>&1 &
sleep 4

# 3. Hard-reload the UI (Ctrl+Shift+R in browser; F5 in Tauri)
```

---

## Visual checks after changes

Open the UI and confirm:

| Check | Expected |
|---|---|
| Status bar bottom-right | `● tauri live` or `● live :8769` (NOT mock) |
| Session tabs across the top | Multiple sessions visible (gmux, knowledge, etc.) |
| Agent sidebar (left) | All panes from `tmux list-windows -a` are listed |
| Click an agent | Chat panel opens on right with real chat history |
| Hardware tab on a pane | Shows RAM, CPU, tokens, model — no `—` placeholders for active agents |
| Todo tab on a pane | Real task list (not "Test C2 fix..." mock text) |
| Tab cycle (Tab key) | Smooth swap todos → chat → hardware |
| Click `⛶` chat-fullscreen | Sidebar + session tabs STAY visible |
| In fullscreen, on wide monitor | Todo side panel visible on the right |
| Markdown in chat | Code blocks render with monospace + dark bg, lists indent |
| Scrollbar | 10px wide, purple accent |

---

## Common failure patterns

### "UI loads but is blank / pane bodies are empty"
→ JS exception. Open DevTools console. Most common is a `ReferenceError`
from a typo in `updatePaneEl()`. Fix and reload.

### "Status bar shows ● mock"
→ Backend not reachable. Run the sanity check above. If `curl` works but
the UI says mock, **clear localStorage** (DevTools → Application → Local
Storage → Clear) and reload — sometimes a stale `gmux.dataSource` override
hangs around.

### "Tauri is laggy compared to browser"
This is real and documented. WebKitGTK is heavier than Chromium. Three
options:
1. Develop in browser, use Tauri only for final desktop integration
2. Run `npm run tauri build` to produce a release build (much faster)
3. Reduce render frequency: in DevTools console, type
   `_renderThrottleMs = 100` (default 0) to space out renders

### "Todos showing on the wrong agent"
Not necessarily a bug — if two tmux panes both run opencode in the same
directory, they share a session. Verify with:
```bash
curl -s http://127.0.0.1:8769/api/state | python3 -c "
import json,sys
d = json.load(sys.stdin)
for p in d.values():
  print(p['window_name'], '→ session:', p.get('session_id','none'))
" | sort -k4
```
If two rows have the same `session_id` value, the todos showing twice is correct.

### "Voice doesn't transcribe"
```bash
# 1. Is daemon running?
ss -tlnp | grep 8770

# 2. Test directly
python3.11 -c "
import asyncio, websockets
async def t():
  async with websockets.connect('ws://127.0.0.1:8770') as ws:
    print('Connected. Say something now...')
    for _ in range(5):
      msg = await asyncio.wait_for(ws.recv(), timeout=10)
      print('→', msg)
asyncio.run(t())
"
# You should see partial/final messages as you speak.

# 3. If hang: PulseAudio may not be reachable from your shell
pactl info | head -3
```

---

## How to test gestures

Gestures need a webcam + MediaPipe. In a browser:
1. Click the gesture toggle (top right, or press `g`)
2. Allow camera permission
3. Make sure you have decent lighting
4. Hold your hand up — you should see landmarks drawn over the video PiP
5. Try a single pinch (thumb + index together) — UI cursor should appear
6. Try a swipe — should navigate windows

Headless test? You can simulate the gesture event:
```js
// In DevTools console
document.dispatchEvent(new CustomEvent('gesture-event', {
  detail: { type: 'swipe', direction: 'right', confidence: 0.9 }
}));
```

---

## How to test "everything" (full smoke test)

```bash
# 1. Reset state
pkill -f "gmux-system/backend"
pkill -f "gmux-monitor"
pkill -f "gmux_voice_daemon"
pkill -f "tauri dev"
sleep 3

# 2. Start everything via the launcher
cd ~/projects/gmux-system && ./scripts/launch.sh &
LAUNCH_PID=$!
sleep 12

# 3. Run all checks
echo "─── Services ───"
ss -tlnp | grep -E "8769|8770|1421|5550"
echo "─── API state ───"
curl -s http://127.0.0.1:8769/api/state | python3 -c "
import json,sys
d=json.load(sys.stdin)
real = sum(1 for p in d.values() if p.get('model'))
print(f'{len(d)} panes, {real} with real data, sessions: {sorted(set(p[\"session_name\"] for p in d.values()))}')"
echo "─── Voice WS ───"
python3.11 -c "
import asyncio,websockets
async def t():
  async with websockets.connect('ws://127.0.0.1:8770',open_timeout=2) as ws: print('OK')
asyncio.run(t())
"
```

---

## Debugging the UI inside Tauri

Tauri devtools are accessible:
- Right-click in the window → "Inspect Element" (usually disabled in release)
- For dev mode, you can also navigate to `http://localhost:1421/` in a regular
  browser — Vite serves the same UI there with full DevTools

The Tauri JS console is **also** logged to `/tmp/gmux-tauri.log` if you
launched via `nohup ... > /tmp/gmux-tauri.log 2>&1`.
