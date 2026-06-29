# Self-Launching Backend — E2E Test Results

**Date:** 2026-05-12  
**Goal:** Verify Tauri app spawns its backend sidecars from a cold start  
**Outcome:** ✅ **WORKS** — no manual setup required

---

## Test procedure

```bash
# 1. Clean slate — kill all backend services
kill <monitor_pid> <voice_pid>
pkill -f "tauri dev" "target/debug/gmuxtest"

# 2. Verify ports free
ss -tlnp | grep -E "8769|8770|1421"   # → empty

# 3. Launch Tauri only
cd ~/projects/gmuxtest
GDK_BACKEND=x11 npm run tauri dev
```

## Observed output

```
[gmux] starting gmux-monitor from /home/fivelidz/projects/gmux-system/backend/status/monitor.py
[gmux] gmux-monitor started — PID 1060595 — log /tmp/gmux-monitor.log
[gmux] gmux-monitor listening on :8769
[gmux] starting gmux-voice from /home/fivelidz/projects/gmux-system/backend/voice/gmux_voice_daemon.py
[gmux] gmux-voice started — PID 1060675 — log /tmp/gmux-voice.log
[gmux] gmux-voice listening on :8770
[gmux] starting gmux-saver from /home/fivelidz/projects/gmux-system/backend/session/session_restore.py
[gmux] gmux-saver started — PID 1060863 — log /tmp/gmux-saver.log
[gmuxtest] Auto-detected session: 'gmux'
[gmuxtest] Attaching PTY to session 'gmux'
[gmuxtest] tmux PID 1061060
```

**All three sidecars came up automatically.** Time from `npm run tauri dev` to first port bound:
- gmux-monitor (:8769) — **~2 seconds**
- gmux-voice (:8770) — **~3 seconds** (faster-whisper model load)
- gmux-saver (no port) — **~1 second**

## Live data verification

```bash
$ curl -s http://127.0.0.1:8769/health
ok

$ curl -s http://127.0.0.1:8769/api/state | jq 'keys | length'
14

$ curl -s http://127.0.0.1:8769/api/state | jq '[.[].session_name] | unique'
["gmux", "goblin", "knowledge", "rfai", "tradez"]
```

WebSocket to voice daemon also accepts connections:
```python
async with websockets.connect('ws://127.0.0.1:8770', open_timeout=2) as ws:
    ✓ voice ws connected
```

---

## What the Rust does (lib.rs)

### Search order for sidecar scripts

```rust
fn find_gmux_script(name: &str) -> Option<PathBuf> {
    let home = std::env::var("HOME").unwrap_or_default();
    [
        // gmux-system (consolidated, install location)  ← preferred
        PathBuf::from(&home).join(format!("projects/gmux-system/backend/status/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux-system/backend/voice/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux-system/backend/session/{name}")),
        // gmuxtest dev sandbox                          ← fallback 1
        PathBuf::from(&home).join(format!("projects/gmuxtest/src-py/status/{name}")),
        PathBuf::from(&home).join(format!("projects/gmuxtest/src-py/voice/{name}")),
        PathBuf::from(&home).join(format!("projects/gmuxtest/src-py/session/{name}")),
        // Production gmux                                ← fallback 2
        PathBuf::from(&home).join(format!("projects/gmux/src/status/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux/src/voice/{name}")),
    ]
    .into_iter()
    .find(|p| p.exists())
}
```

### Robust spawn with health check

```rust
fn start_with_retry(label, script_path, args, port, sidecars) -> bool {
    if let Some(mut child) = spawn_one_sidecar(...) {
        thread::sleep(1500ms);                       // let it boot
        match child.try_wait() {
            Some(status) => {                          // died → log + give up
                eprintln!("{} died (exit {}). Check /tmp/{}.log");
                return false;
            }
            None => {                                  // alive — wait for port bind
                for _ in 0..40 {                       // up to 4 seconds
                    sleep(100ms);
                    if port_in_use(p) { return true; }
                }
            }
        }
    }
}
```

If a sidecar dies on startup (missing deps, bad config), the log file at `/tmp/gmux-monitor.log` or `/tmp/gmux-voice.log` contains the Python traceback.

---

## UI health indicator

A new element in the status bar (`#sb-backend`) appears red **only when monitor :8769 is unreachable**:

```
[ ● tauri live ] [ ⚠ backend down — restart ]
```

Clicking **restart** calls Tauri's `restart_backend` command, which re-runs `spawn_sidecars`. Since `port_in_use` checks each port first, healthy sidecars are not disturbed.

The UI polls health every 8 seconds (and on first load after 2.5s). In browser mode (no Tauri) it does direct `fetch /health` + WebSocket probe.

---

## What's left for "install anywhere"

This test only validates the **dev mode** path (`npm run tauri dev`). To make the app truly installable on a stranger's machine:

| Step | What | Status |
|------|------|--------|
| 1 | Ship sidecars inside Tauri bundle | TODO — currently uses `$HOME/projects/gmux-system/...` paths |
| 2 | Detect script location relative to Tauri binary | TODO — add `tauri::api::path::resource_dir()` lookup |
| 3 | Bundle MediaPipe model (`hand_landmarker.task`) | TODO — 7.5 MB binary, add to `tauri.conf.json` resources |
| 4 | `tauri build` → .deb / .AppImage / .msi | TODO — currently only `cargo run` works |
| 5 | Bundle Python deps (faster-whisper, sounddevice) | TODO — install via shell on first launch or ship a venv |
| 6 | Detect missing tmux / opencode and offer install | TODO — onboarding flow |

These are the proper packaging steps once the dev flow is fully proven. For now the system works end-to-end as long as `gmux-system/` is cloned into `~/projects/`.

---

## Next steps

1. **You test the actual UI** in either browser (`http://localhost:5550/v2/index.html`) or the Tauri window that opened. Verify:
   - 5 session tabs: gmux / goblin / knowledge / rfai / tradez (plus All)
   - 14 agents in the sidebar with real names
   - Status bar shows `● tauri live` (or `● live :8769` in browser) — NOT `● mock`
   - No red `⚠ backend down` indicator
2. Try the **restart backend** button — kill monitor manually (`kill <pid>`), wait for the warning to appear, click restart, watch monitor come back.
3. When ready, packaging — see steps 1–6 above.
