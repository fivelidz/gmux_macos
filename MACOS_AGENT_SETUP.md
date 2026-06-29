# gmux on macOS — Setup Guide for a Coding Agent

> **You are a coding agent.** Your job is to get **gmux** running on this macOS
> machine. This document is your brief. Read it fully before acting, then work
> through the phases in order. Report back at each ✅ checkpoint.
>
> **Before you start:** read [`docs/TAURI_APP_STATUS.md`](docs/TAURI_APP_STATUS.md).
> This IS the real, full gmux app (not a demo). That note explains the build
> steps and the reasons it can *look* empty (no committed `dist/`, missing
> backend sidecar, leftover `0.1.0` version strings) so you don't chase ghosts.

---

## 0. What gmux is (context)

gmux (v4.0.0-alpha.22, "the agent operations centre") is a **cross-platform
Tauri 2 desktop app that is itself a terminal multiplexer** — it owns terminals
directly via a Rust PTY engine (`portable-pty`), no tmux substrate required.
It is built to run and supervise multiple AI coding agents at once and visualise
what each one is doing.

Architecture (three layers):
1. **Rust core** (`app/src-tauri/src/lib.rs`) — owns one PTY per agent, emits
   live output events. Native **WKWebView** on macOS (NOT webkit2gtk).
2. **Frontend UI** (`ui/v3/index.html`, mirrored to `app/src/index.html`) —
   Vite + xterm.js. Also extra windows: `aquarium`, `dashboard` (Agent Monitor).
3. **Python backend sidecars** (`backend/`) — `status/monitor.py` (HTTP :8769),
   `voice/gmux_voice_daemon.py` (ws :8770, optional), session restore, MCP server.

The app also exposes an embedded HTTP API on `http://127.0.0.1:6310`.

**This repo was developed and verified on Linux. It is ~95% mac-ported already**
(all known platform-specific paths are guarded with `cfg!(target_os)` / `uname`
checks — see `docs/MACOS_PORTING.md` for the full list of patches). It has
**never been run on real Mac hardware**. Your task is to close that last 5%.

---

## 1. Ground rules for you, the agent

- **Work in phases.** Do not jump to the Tauri build before the browser UI runs.
- **Do not delete files.** If you must replace something, copy the original to an
  `archive/` folder first.
- **Prefer `cfg!(target_os = "macos")` (Rust) and `uname`/`$IS_MAC` (bash)**
  guards over hard-coding mac-only behaviour, so the code stays cross-platform.
- **Keep Linux working.** Any change you make must not break the Linux path. The
  existing guards already do this — follow the same pattern.
- **Log every issue you hit** into `docs/VM_REPORTS/macos-phase{N}.md` with the
  exact error and the fix you applied. This is how the change gets back upstream.
- **Commit in small, described steps** (`fix(macos): ...`).
- If a step needs the human (e.g. an Apple Developer ID for notarisation, or a
  microphone-permission prompt), **stop and ask** rather than guessing.

---

## 2. Prerequisites (install these first)

> **⚡ Shortcut:** there is now a one-command bootstrap that does the survey +
> install + Phase 1 for you, with all the macOS traps already handled:
> ```bash
> bash scripts/macos-bootstrap.sh --terminal   # (--check to survey only, --app to build the desktop app)
> ```
> See [`docs/MACOS_RUNBOOK.md`](docs/MACOS_RUNBOOK.md) for the smooth path and the
> table of known traps. The manual steps below still work if you prefer them.

> **gmux is standalone.** It does NOT need Ghostty, qalcode2, or any tool from
> the `tooling/` folder. Everything gmux needs is below + this repo's own
> `backend/`. (The `tooling/` extras are unrelated companion apps — skip them
> unless explicitly asked.)

```bash
# Homebrew (if not present): https://brew.sh
# Then — the only system deps gmux needs:
brew install python@3.11 node git
# tmux is NOT required for v4 (PTY engine replaces it) but harmless to have:
brew install tmux

# Python deps for gmux's OWN backend (this repo's backend/ folder).
# Core need is psutil — the monitor runs without it but RAM/CPU show 0.
pip3.11 install --user -r backend/requirements.txt

# Rust toolchain (needed for Phase 2 — the Tauri app):
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
```

> Voice is optional and off by default. To enable it later, uncomment the voice
> lines in `backend/requirements.txt` and re-run the pip command.

✅ **Checkpoint 0:** `python3.11 --version`, `node --version`, `cargo --version`
all succeed, and `python3.11 -c "import psutil"` works.

---

## 3. Phase 1 — Backend + browser UI (target ~1–2 h)

This proves the Python backend and UI work on macOS *before* touching Rust.

```bash
cd <repo-root>          # the directory containing this file

# Launch the backend monitor + browser UI (no Tauri):
./scripts/launch-v4.sh --browser
```

What should happen:
- `monitor.py` binds **:8769** (uses `lsof` on macOS — Patch 7).
- A static UI is served (Python `http.server`). Open the printed URL.
- The Agent Monitor dashboard fetches `/api/state`, `/api/files`,
  `/api/activity`, `/api/memory` from :8769.

Verify the backend endpoints directly:
```bash
curl -s http://localhost:8769/health        # -> ok
curl -s http://localhost:8769/api/state     # -> JSON of panes
curl -s http://localhost:8769/api/files     # -> JSON folder/file feed
```

> **Known macOS-relevant detail:** `monitor.py` discovers listening ports. On
> Linux it uses `ss`; on macOS it falls back to `lsof` (`_list_listening_ports`,
> Patch 7). If port discovery fails, check that fallback is being taken
> (`uname -s` should be `Darwin`).

> **Agent Monitor "empty / no folders" note:** the folder tree is built from the
> *last hour* of agent tool activity. If no AI agents are actively touching files,
> the view is legitimately empty — that is **not** a bug, and (as of the demo-
> substitution fix) the app correctly shows an empty "waiting for data" canvas
> instead of fabricating fake sample agents. Start an agent and have it Read/Edit
> a file to see folders populate. See `docs/TAURI_APP_STATUS.md` §3a.

✅ **Checkpoint 1:** `curl http://localhost:8769/api/state` returns JSON and the
browser UI loads without console errors. Record results in
`docs/VM_REPORTS/macos-phase1.md`.

To stop everything: `./scripts/launch-v4.sh --kill`

---

## 4. Phase 2 — Tauri desktop app (target ~3–4 h)

```bash
cd <repo-root>/app
npm install

# Dev mode (hot reload). First cargo build is SLOW (5–15 min, many crates):
cd <repo-root>
./scripts/launch-v4.sh --dev
```

Expected:
- A native macOS window opens (WKWebView). No GTK/GStreamer involved — those
  env vars are skipped on macOS (Patch 1).
- The global shortcut for the dashboard window is **Cmd+Opt+D** on macOS
  (Ctrl+Alt+D on Linux) — Patch 5.
- PTY-backed terminals work via `portable-pty` (cross-platform).

Likely things you may need to fix on real hardware (none confirmed yet):
- **Microphone / Accessibility permissions:** macOS will prompt the first time
  the app uses audio or global shortcuts. Grant in System Settings → Privacy.
- **Code-signing for the dev build:** dev mode usually runs unsigned fine; if
  macOS Gatekeeper blocks it, right-click → Open, or `xattr -dr
  com.apple.quarantine` on the built `.app`.
- **`portable-pty` / xterm sizing:** confirm terminal resize works.

Release build (only after dev mode works):
```bash
cd <repo-root>/app
npm run tauri build
# Output: app/src-tauri/target/release/bundle/macos/gmuxtest.app
#         (and a .dmg under .../bundle/dmg/)
```

✅ **Checkpoint 2:** dev-mode window opens, you can open an agent pane and type
in its terminal. Record in `docs/VM_REPORTS/macos-phase2.md`.

---

## 5. Phase 3 — Voice, and packaging (optional, ~1 day)

- **Voice daemon** (`backend/voice/gmux_voice_daemon.py`): uses
  `faster-whisper` + `sounddevice`. On macOS, `sounddevice` → PortAudio →
  CoreAudio works with no extra config (Patch 8). The launcher auto-skips voice
  if these libs are missing, so it's safe to defer.
- **`cam_broker_active()`** returns `False` on macOS (it used `systemctl`, which
  doesn't exist on macOS — Patch 7). Porting the camera broker to `launchd` is a
  TODO; the UI handles `cam: false` gracefully. Leave this unless asked.
- **DMG distribution to non-developers** requires an **Apple Developer ID +
  notarisation** (paperwork + `xcrun notarytool`). This needs the human's Apple
  account — **stop and ask** before attempting.

---

## 6. Reference docs in this repo

- `docs/MACOS_PORTING.md` — the authoritative list of all 9 mac patches already
  applied, with file/line references. **Read this.**
- `README.md` — feature overview, alpha.22 capabilities.
- `docs/GMUX_API.md` — the embedded HTTP API on :6310.
- `agent-monitor/README.md` + `agent-monitor/docs/BACKEND_CONTRACT.md` — how the
  Agent Monitor dashboard consumes data (folder tree, file feeds).
- `scripts/launch-v4.sh` — the single entry point; read its `--help`/header for
  all modes (`--dev`, `--browser`, `--kill`, `--test`).
- `scripts/macos-smoke-test.sh` — environment sanity checks for macOS.

---

## 7. What "done" looks like

1. ✅ Backend + browser UI run on macOS (Phase 1).
2. ✅ Tauri dev-mode app opens a native window with working PTY terminals (Phase 2).
3. ✅ A release `.app` builds (`npm run tauri build`).
4. 📝 `docs/VM_REPORTS/macos-phase{1,2,3}.md` written with every issue + fix.
5. 📝 Any code changes use `cfg!(target_os)` / `$IS_MAC` guards and **keep Linux
   working**, committed in small described steps.

When all of the above are green, gmux runs on macOS. Hand back a summary of
what you changed and anything that still needs the human (permissions,
Apple Developer ID, hardware-specific quirks).
