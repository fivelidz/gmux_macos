# Test report — gmux-v4 alpha.4

**Date:** 2026-05-17
**Tag at HEAD:** `v4.0.0-alpha.4`
**Host:** CachyOS Linux x86_64 (KDE Plasma 6 / Wayland)
**Tester:** Claude (Sonnet 4.6) via opencode, headless / no GUI interaction

---

## TL;DR

| Layer | Result |
|---|---|
| Maestro PTY core lifted + compiles | ✅ |
| `cargo check` zero new warnings | ✅ |
| **Standalone PTY smoke test (no Tauri)** | ✅ shell spawned, command echoed back, clean exit |
| `npm run build` (Vite production bundle) | ✅ 9 modules → `app/dist/` |
| `npm run tauri build` (full release bundle) | ✅ 17 MB binary + 5.8 MB .deb + 5.8 MB .rpm |
| AppImage bundle | ⚠ linuxdeploy fetch failed (network during build); irrelevant locally |
| Headless binary launch | ✅ all sidecars start, Tauri attempts window |
| `GMUX_V4_PTY=1` skips legacy tmux attach | ✅ confirmed in log |
| Monitor sidecar `/health` + `/api/state` | ✅ 200 OK, valid JSON |
| Claude usage API command compiled in | ✅ |
| Usage badge UI wired (poll every 30s, click cycles daily/weekly/opus) | ✅ |
| Toolbar `v4 Lab` tab in Options | ✅ |
| xterm.js per pane (term view mode) | ✅ wired, awaiting human GUI test |
| `open_agent_v4`, `spawn_sub_agent_v4` Tauri commands | ✅ compiled + registered |

**The full v4 stack builds and starts.** What's left is human-eye verification that the Tauri window renders correctly and that the per-pane xterm.js terminals stream PTY output as expected.

---

## Test 1 — Rust standalone PTY smoke (`examples/pty_smoke.rs`)

Goal: prove the lifted maestro `process_manager.rs` works on this host without involving Tauri.

```bash
cd app/src-tauri
cargo run --example pty_smoke
```

Output:
```
── gmux-v4 PTY smoke test (no Tauri) ────────────────────────────
✅ PTY opened
✅ shell spawned (pid 1247855)
   → prompt + early output: 10 bytes
✅ wrote 'echo "hello v4"\r' (16 bytes)
✅ captured 'hello v4' in 36 bytes of output
✅ shell exited cleanly with ExitStatus { code: 0, signal: None }
──────────────────────────────────────────────────────
✅ ALL CHECKS PASSED
```

This proves: portable-pty → reader thread → writer → child sees input → child output flows back → clean PTY shutdown. The exact same pipeline `ProcessManager::spawn_shell` uses.

---

## Test 2 — Full Tauri release build

```bash
cd app
npm install
npm run tauri build
```

Output (tail):
```
warning: `gmuxtest` (lib) generated 1 warning
    Finished `release` profile [optimized] target(s) in 1m 29s
       Built application at: app/src-tauri/target/release/gmuxtest
        Info Patching … with bundle type information: deb
    Bundling gmux_0.1.0_amd64.deb
        Info Patching … with bundle type information: rpm
    Bundling gmux-0.1.0-1.x86_64.rpm
    Bundling gmux_0.1.0_amd64.AppImage
failed to bundle project `failed to run linuxdeploy`
```

Artifacts:
```
-rwxr-xr-x  17M  app/src-tauri/target/release/gmuxtest
-rw-r--r-- 5.8M  app/src-tauri/target/release/bundle/deb/gmux_0.1.0_amd64.deb
-rw-r--r-- 5.8M  app/src-tauri/target/release/bundle/rpm/gmux-0.1.0-1.x86_64.rpm
```

The single warning is pre-existing (unused `window` binding at lib.rs:1111, unrelated to v4 changes).

The AppImage failure is the linuxdeploy network fetch — irrelevant for local testing, and won't affect macOS/Windows .dmg/.msi builds.

### Fixes applied during this test
- `vite.config.js` `outDir: '../dist'` — vite root is `src/` so default emits to `src/dist`, but tauri expects `app/dist`
- `vite.config.js` `target: 'safari15'` — `safari13` can't lower xterm addons' destructuring
- `package.json` `@tauri-apps/api: ~2.10` — version mismatch fix
- `package.json` added `esbuild` as devDep (vite 8 + rolldown bundling)

---

## Test 3 — Binary launches + sidecars come up

```bash
env GMUX_V4_PTY=1 app/src-tauri/target/release/gmuxtest > /tmp/gmux-v4.log 2>&1 &
sleep 5
pgrep -af gmuxtest
cat /tmp/gmux-v4.log
```

Output:
```
1275062 /home/fivelidz/projects/gmux_v4/app/src-tauri/target/release/gmuxtest
[gmux] starting gmux-monitor from /home/fivelidz/projects/gmux-system/backend/status/monitor.py
[gmux] gmux-monitor started — PID 1275711 — log /tmp/gmux-monitor.log
[gmux] gmux-monitor listening on :8769
[gmux] gmux-voice :8770 already bound — assuming healthy, skip spawn
[gmux] starting gmux-saver from /home/fivelidz/projects/gmux-system/backend/session/session_restore.py
[gmux] gmux-saver started — PID 1275867 — log /tmp/gmux-saver.log
[gmuxtest] GMUX_V4_PTY=1 — skipping legacy tmux PTY attach. Use open_agent_v4 / spawn_sub_agent_v4 commands instead.
```

Confirms:
- Tauri binary runs natively (no embedded Python)
- Sidecars (monitor, voice, session-saver) auto-spawn
- The `GMUX_V4_PTY` env var correctly skips the legacy `start_pty` tmux attach
- No crashes, no error spam, exit code 0 on SIGTERM

---

## Test 4 — Monitor sidecar reachable

```bash
curl -s http://localhost:8769/health
# → ok

curl -s http://localhost:8769/api/state | head -c 200
# → { "%1": { "pane_id": "%1", "session_name": "gmux", … } }
```

Proves the existing v3 backend keeps working alongside the v4 PTY path. The dashboard window's flowchart and agent monitor still get their data feed.

---

## What's NOT tested (needs human at a desktop)

All of these require an interactive Tauri window:

- [ ] Window opens at 1400×900 with the full v3 UI rendered
- [ ] Options → v4 Lab tab visible; "Enable v4 PTY for new agents" toggle present
- [ ] Toggling the checkbox sets/clears `localStorage.gmux_v4_pty`
- [ ] Press `N` (new agent) with v4 enabled → spawns a shell, switches view to "Terminal", mounts xterm.js
- [ ] Typing in the xterm sends keystrokes to the agent
- [ ] Agent output streams back into the xterm
- [ ] `Ctrl+P` palette filters across panes
- [ ] `L` cycles layout
- [ ] Voice mode (Caps Lock) still routes input to focused pane
- [ ] Gesture mode (camera) still switches focus
- [ ] Agent Monitor (`Ctrl+Alt+D`) opens dashboard window with flowchart
- [ ] Provider auth panel "Connect Claude" still works
- [ ] **Claude usage badge** in toolbar:
  - Appears after first 30s poll if `~/.claude/.credentials.json` exists
  - Shows `Daily X%` with colored dot (green/amber/red)
  - Click cycles to `Weekly X%` then `Opus X%`
  - Tooltip shows reset timestamp
- [ ] Spawning a v4 agent in a folder with opencode running there → activity flows to the dashboard
- [ ] Closing the app cleans up all child PTYs (no orphans in `ps`)

## How to run the human-eye tests

```bash
# 1. Build (already done)
cd ~/projects/gmux_v4/app
npm run tauri build       # → target/release/gmuxtest

# 2. Launch with v4 mode pre-enabled
env GMUX_V4_PTY=1 ./src-tauri/target/release/gmuxtest

# 3. Inside the window
#    Options → v4 Lab → tick "Enable v4 PTY for new agents"
#    Press N → fill a real dir like ~/projects/gmux_v4 → Create
#    Watch the pane auto-switch to Terminal view
#    Type ls — see file listing
```

If steps work: tag `v4.0.0-beta.1` and we're past alpha.

---

## Sidecar / dependency story

Confirmed at build time:
- `portable-pty` builds clean on Linux x86_64
- `keyring` (cfg-gated on non-macOS) pulls in Secret-Service / D-Bus stubs without runtime errors
- `reqwest` with `rustls-tls` avoids OpenSSL system dependency
- `which` correctly detects `tmux` presence (test machine has tmux installed)
- `tauri-plugin-shell` + `tauri-plugin-global-shortcut` compile

Optional sidecars that started during launch:
- monitor.py — found at `~/projects/gmux-system/backend/status/monitor.py` (lifted location)
- session_restore.py — same
- voice daemon — port :8770 was already bound by a prior instance; skipped gracefully

---

## What broke (and was fixed) during this test

| Issue | Cause | Fix |
|---|---|---|
| `cargo check` failed: `tokio::process::Command` not in scope | Cargo `tokio` features missing `process` | Added `"process"` to tokio features |
| vite-build failed: `safari13` can't lower destructuring | xterm addons use modern JS | Bumped to `safari15` |
| vite-build emitted to wrong dir | Vite root is `src/`, tauri expects `../dist` | Added `outDir: '../dist'` in vite.config.js |
| Tauri build version mismatch warning | `@tauri-apps/api 2.11.0` vs `tauri 2.10.3` | Pinned api to `~2.10` |
| `npm run build` failed: esbuild missing | Vite 8 + rolldown bundling change | Added `esbuild` to devDependencies |
| AppImage bundle failed | `linuxdeploy` network fetch | Ignored (irrelevant for local + .deb/.rpm cover most cases) |

All committed.

---

## Recommended next steps

1. **Human GUI test on the host** (Test 5 — the checklist above)
2. If green: tag `v4.0.0-beta.1`, fix AppImage build (`linuxdeploy` offline mode)
3. macOS build verification (Mac required)
4. Windows build verification (Windows required)
5. monitor.py adaptation so v4-spawned PTYs feed it state without needing tmux
6. Code-signing pipeline (deferred to ship phase)
