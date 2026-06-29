# Tauri app status — is this a real app or a demo?

**Short answer: this is the REAL, working gmux app — not a demo or a stub.**

If it ever *looks* like a demo (blank windows, "nothing happens"), it's almost
always one of the build/run gotchas listed below — not missing functionality.
This note exists so the coding agent doing the macOS port doesn't mistake a
build-step issue for a hollow app.

---

## Evidence it's the real app

The Rust + frontend source is all present and substantial:

| Piece | File | Size |
|-------|------|------|
| Main Tauri app + commands | `app/src-tauri/src/lib.rs` | 2,243 lines (95 KB) |
| Embedded HTTP API (:6310) | `app/src-tauri/src/api.rs` | 409 lines |
| PTY process manager | `app/src-tauri/src/core/process_manager.rs` | 29 KB |
| Terminal backend | `app/src-tauri/src/core/terminal_backend.rs` | 6 KB |
| Usage / pairing / terminal commands | `app/src-tauri/src/commands/*.rs` | ~40 KB |
| Full UI | `app/src/index.html` | 13,660 lines (618 KB) |
| Agent Monitor window | `app/src/dashboard/` | present |
| Aquarium window | `app/src/aquarium.html` | 49 KB |

Real PTY engine, not a mock:
- `ProcessManager` owns one `portable-pty` per agent (`core/process_manager.rs`).
- Tauri commands `open_agent_v4` and `spawn_sub_agent_v4` are implemented and
  registered in the `invoke_handler!` (lib.rs ~line 1683).
- The app emits live `pty-output-*` / `gmux-state` / `files-update` events.

This is gated behind `GMUX_V4_PTY=1` (set automatically by
`scripts/launch-v4.sh`). With that env var, the app skips the legacy tmux path
and uses the direct-PTY engine.

---

## Why it can LOOK like a demo (and the fixes)

### 1. No pre-built `dist/` is committed
`app/src-tauri/tauri.conf.json` has `"frontendDist": "../dist"`, but `dist/` is a
build artifact and is **not** in the repo (correctly — it's git-ignored). If you
try to run a release binary before building the frontend, windows are blank.

**Fix:** always build the frontend first, or use dev mode which serves `src/`
live:
```bash
# Dev mode (serves UI live from src/, hot reload — best for porting):
./scripts/launch-v4.sh --dev

# OR produce a real release:
cd app && npm install && npm run build && npm run tauri build
```

### 2. Multi-window HTML must be copied into dist (already handled)
The app registers three windows — `main` (`index.html`), `aquarium`
(`aquarium.html`), and `dashboard` (`dashboard/index.html`). Vite only bundles
the root entry by default, so through alpha.7 the **packaged** build opened the
Agent Monitor / aquarium windows blank ("Agent Monitor appears to do nothing").

This is **already fixed**: `app/vite.config.js` has a `copyExtraWindows()` plugin
that copies `dashboard/`, `aquarium.html`, and `vendor/` into `dist/` after build,
and prints a sanity check:
```
[gmux-vite] ✓ dist/dashboard/index.html present
```
If you ever see `✗ ... MISSING`, the packaged build's extra windows will be blank
— investigate the plugin, don't assume the app is empty.

### 3. The backend sidecars must be running for live data
The UI shows live agent/folder/file data that comes from the Python backend
(`backend/status/monitor.py` on :8769) and is re-emitted by Rust as Tauri events.
`scripts/launch-v4.sh` starts the monitor automatically. If you launch the Tauri
binary directly **without** the monitor, panes/folders look empty — again, not a
demo, just a missing sidecar. (See also the Agent Monitor "folders only show the
last hour of activity" note in `MACOS_AGENT_SETUP.md`.)

### 4. Version strings say `0.1.0` — ignore them
`app/package.json` and `tauri.conf.json` both say `"version": "0.1.0"` and the
identifier is `dev.gmux.test`. These are leftover Tauri scaffolding values. The
**real product version is v4.0.0-alpha.22** (see top-level `README.md`). Don't
take `0.1.0` as evidence of an early/demo app.

---

## What "working" looks like on macOS

After `./scripts/launch-v4.sh --dev`:
1. A native macOS window (WKWebView) opens showing the gmux UI.
2. You can open an agent pane and get a live terminal (PTY) you can type into.
3. Cmd+Opt+D toggles the Agent Monitor (dashboard) window.
4. The monitor on :8769 is up (`curl http://localhost:8769/health` → `ok`).

If all four happen, the app is fully functional. The remaining porting work is
about the Tauri/Rust **build** on mac hardware (first `cargo build` is slow,
WKWebView vs webkit2gtk, code-signing/Gatekeeper) — see `MACOS_AGENT_SETUP.md`
and `docs/MACOS_PORTING.md`.
