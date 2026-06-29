# gmux-system — macOS Porting Guide

**Version:** v3.7 porting prep  
**Status:** Patches applied (Linux verified); macOS untested — awaiting hardware  
**Last updated:** 2026-05-13  

---

## TL;DR

gmux-system is ~95% macOS-compatible today. All known platform-specific code
paths have been patched with `OS_TYPE`/`cfg!(target_os)` guards. The patches
were written and verified on Linux; they need one round of testing on real Mac
hardware to confirm.

**Estimated effort once a Mac is available:**
- Phase 1 (browser UI only): ~2 hours
- Phase 2 (Tauri desktop app): ~4 hours
- Phase 3 (voice + gestures + DMG packaging): ~1 day

---

## What was patched (v3.7 porting prep)

### Patch 1 — `scripts/launch.sh` — OS detection + cross-platform port check

**File:** `scripts/launch.sh` (lines 13–23)

**Problem:** `ss -tlnp` is Linux-only (iproute2 package); macOS ships `lsof` instead.
`GDK_BACKEND=x11` and `GST_*` env vars are GTK/GStreamer — useless on macOS and
may generate GTK framework warnings if accidentally exported.
`xdg-open` does not exist on macOS; the equivalent is `open`.

**Change:**
```bash
# Added at top of file:
OS_TYPE="$(uname -s)"
IS_MAC=false
[ "$OS_TYPE" = "Darwin" ] && IS_MAC=true

port_in_use() {
  lsof -i :"$1" >/dev/null 2>&1
}
```

All `ss -tlnp | grep :PORT` calls replaced with `port_in_use PORT`.

GDK/GST exports wrapped:
```bash
if ! $IS_MAC; then
  export GDK_BACKEND=x11
  export WEBKIT_DISABLE_COMPOSITING_MODE=1
  export GST_DEBUG="*:0"
  export GST_PLUGIN_FEATURE_RANK="..."
fi
```

Browser open call:
```bash
if $IS_MAC; then
  open "$URL" 2>/dev/null || echo "  Open manually: $URL"
else
  xdg-open "$URL" 2>/dev/null || echo "  Open manually: $URL"
fi
```

**Linux impact:** None — `lsof` is available on Linux (lsof package, usually
pre-installed). The `if ! $IS_MAC` guards are `false` on Linux.

---

### Patch 2 — `scripts/install-vm.sh` — Homebrew package manager + setsid

**File:** `scripts/install-vm.sh`

**Problem 1:** `pacman`/`apt`/`dnf` branch missing for macOS Homebrew.

**Change:** Added `brew` branch:
```bash
elif command -v brew >/dev/null 2>&1; then
  PM=brew
```

And a corresponding install case:
```bash
brew)
  # webkit2gtk NOT needed on macOS — Tauri uses native WKWebView.
  brew install --quiet tmux python@3.11 curl rsync openssh 2>&1 | tail -3 || true
  ;;
```

**Problem 2:** `setsid` is a Linux `util-linux` tool; macOS does not include it.

**Change:** macOS uses `nohup` for equivalent process detachment:
```bash
if $_IS_MAC; then
  nohup python3 backend/status/monitor.py ... &
else
  setsid python3 backend/status/monitor.py ... &
fi
```

**Problem 3:** Port checks used `ss -tlnp`. Replaced with `lsof -i :PORT` helper.

**Problem 4:** IP discovery used `ip -4 addr show` (Linux iproute2). Added macOS
`ifconfig` fallback:
```bash
if command -v ip >/dev/null 2>&1; then
  _get_local_ip() { ip -4 addr show ...; }
else
  _get_local_ip() { ifconfig | grep inet ...; }
fi
```

---

### Patch 3 — `scripts/gmux` — `ss` in `--backend-only`

**File:** `scripts/gmux` (line 43)

**Change:** `ss -tlnp | grep :5550` replaced with `_port_in_use 5550` (lsof-based helper).

---

### Patch 4 — `scripts/launch-gmux.sh` — `ss` and `GDK_BACKEND`

**File:** `scripts/launch-gmux.sh`

- `ss -tlnp | grep :8770` replaced with `_port_in_use 8770`
- `GDK_BACKEND=x11` / `WEBKIT_DISABLE_COMPOSITING_MODE=1` wrapped in `if ! $_IS_MAC`

---

### Patch 5 — `app/src-tauri/src/lib.rs` — Cmd vs Ctrl global shortcut

**File:** `app/src-tauri/src/lib.rs` (function `setup_shortcuts`)

**Problem:** `Ctrl+Alt+D` is the Linux global shortcut for the dashboard window.
On macOS, users expect `Cmd+Opt+D` — `Ctrl` shortcuts feel wrong on Mac.

**Change:** (lib.rs:1207–1216)
```rust
let dash_modifiers = if cfg!(target_os = "macos") {
    Modifiers::META | Modifiers::ALT
} else {
    Modifiers::CONTROL | Modifiers::ALT
};
let dash_key = Shortcut::new(Some(dash_modifiers), Code::KeyD);
```

`cfg!(target_os = "macos")` is evaluated at compile time — zero runtime overhead.
On Linux the compiled binary is identical to before this change.

**macOS key:** Cmd+Opt+D  
**Linux key:** Ctrl+Alt+D (unchanged)

---

### Patch 6 — `app/src-tauri/src/lib.rs` — cross-platform URL opener

**File:** `app/src-tauri/src/lib.rs` (new helper function `open_url_in_browser`)

**Problem:** Any future code that calls `xdg-open` for OAuth flows or external
links will fail on macOS (no `xdg-open`).

**Change:** Added `open_url_in_browser(url)` helper (lib.rs:183–207):
```rust
fn open_url_in_browser(url: &str) {
    let opener = if cfg!(target_os = "macos") {
        "open"
    } else {
        "xdg-open"
    };
    let _ = std::process::Command::new(opener).arg(url).spawn();
}
```

All future OAuth URL-open code should call `open_url_in_browser(&url)` instead
of hard-coding `xdg-open`.

---

### Patch 7 — `backend/status/monitor.py` — cross-platform port discovery

**File:** `backend/status/monitor.py`

**Problem 1:** `get_bun_port()` used `ss -tlnp` to find which port a bun process
is listening on. `ss` is Linux-only.

**Change:** Added `_list_listening_ports()` that prefers `ss` on Linux and falls
back to `lsof -i -P -n -sTCP:LISTEN` on macOS. Added `_find_port_for_pid_lsof()`
to parse lsof output format (different from ss format). The existing ss parsing
path is preserved unchanged.

**Problem 2:** `cam_broker_active()` called `systemctl --user is-active` which
does not exist on macOS (macOS uses `launchd`/`launchctl`).

**Change:** Returns `False` immediately on macOS with a TODO comment:
```python
if _IS_MACOS:
    # systemctl does not exist on macOS.
    # TODO(macos): port to launchctl when cam-broker is ported to macOS.
    return False
```

The UI handles `cam: false` gracefully — the camera toggle stays unchecked.

---

### Patch 8 — `backend/voice/gmux_voice_daemon.py` — PulseAudio preflight

**File:** `backend/voice/gmux_voice_daemon.py`

**Problem:** The voice daemon *currently* has no explicit `pactl` call, but any
future preflight that checks PulseAudio would break on macOS (which uses
CoreAudio). Added a defensive wrapper now to prevent future regressions.

**Change:** Added `_check_audio_backend()` function that:
- On macOS: logs a debug message and returns immediately (CoreAudio is always present)
- On Linux: runs `pactl info` as an advisory check, warns but NEVER exits if it fails
- Called from `main()` after arg parsing, before loading the Whisper model

`sounddevice` → PortAudio → CoreAudio works transparently on macOS without any
additional configuration.

---

### Patch 9 — `app/src-tauri/Cargo.toml` — platform audit comments

**File:** `app/src-tauri/Cargo.toml`

Added comments clarifying platform support for each dependency:
- `tauri`: macOS uses native WKWebView, NOT webkit2gtk (Linux-only)
- `tauri-plugin-global-shortcut`: cross-platform; key mapping handled in lib.rs
- `portable-pty`: cross-platform (macOS requires `brew install tmux`)

---

## Three-phase rollout plan

Copied from `DEPLOYMENT_TARGETS.md` and updated with patch cross-references.

### Phase 1 — Browser UI (target: ~2 hours on a fresh Mac)

```bash
# Prerequisites
brew install tmux python@3.11 node git
pip3.11 install --user psutil websockets

# Get the code
git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system

# Verify environment (Patch 1+2 in smoke test)
bash scripts/macos-smoke-test.sh

# Launch backend + browser UI
bash scripts/launch.sh --browser
open http://localhost:5550/ui/v3/index.html
```

Expected result: monitor.py starts, browser UI opens, live pane state shows
tmux sessions. No Tauri required.

Document issues in `docs/VM_REPORTS/macos-phase1.md`.

### Phase 2 — Tauri desktop app (target: ~4 hours)

```bash
# Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

# App dependencies
cd ~/projects/gmux-system/app
npm install

# Dev mode (hot reload)
bash ../scripts/launch.sh --dev

# If dev mode works, try release build:
npm run tauri build
# Binary appears at: app/src-tauri/target/release/bundle/macos/gmuxtest.app
```

Expected issues:
- First-time `cargo build` is slow (5–15 min, many crates)
- `portable-pty` requires `tmux` in PATH — confirmed by `brew install tmux` above
- Global shortcut Cmd+Opt+D should work via Patch 5

Document issues in `docs/VM_REPORTS/macos-tauri.md`.

### Phase 3 — Voice + gestures + DMG packaging (target: ~1 day)

```bash
# Voice daemon deps
pip3.11 install --user sounddevice faster-whisper

# Test voice daemon
python3.11 backend/voice/gmux_voice_daemon.py --list-devices
python3.11 backend/voice/gmux_voice_daemon.py --model tiny --port 8770

# Gesture engine (MediaPipe)
pip3.11 install --user mediapipe

# DMG packaging — requires Apple Developer ID certificate ($99/yr)
# npm run tauri build produces a .app; DMG requires notarization for distribution.
# Internal use: unsigned .app works fine for local testing.
```

---

## What's still untested (as of 2026-05-13)

| Component | Patch applied | Tested on Mac |
|---|---|---|
| `ss` → `lsof` for port checks | ✅ (Patches 1,2,3,4,7) | ❌ |
| `xdg-open` → `open` for browser | ✅ (Patches 1,6) | ❌ |
| `GDK_BACKEND=x11` gating | ✅ (Patches 1,4) | ❌ |
| `setsid` → `nohup` on macOS | ✅ (Patch 2) | ❌ |
| `brew` package manager branch | ✅ (Patch 2) | ❌ |
| Tauri Cmd+Opt+D shortcut | ✅ (Patch 5) | ❌ |
| `open_url_in_browser` helper | ✅ (Patch 6) | ❌ |
| `cam_broker_active` macOS guard | ✅ (Patch 7) | ❌ |
| PulseAudio preflight skip | ✅ (Patch 8) | ❌ |
| `sounddevice` → CoreAudio | code unchanged | ❌ |
| `faster-whisper` on Apple Silicon | code unchanged | ❌ |
| `portable-pty` PTY on macOS | code unchanged | ❌ |
| Tauri `WKWebView` rendering | code unchanged | ❌ |
| `ip addr` → `ifconfig` fallback | ✅ (Patch 2) | ❌ |

---

## How to verify each fix on a Mac

### Verify Patch 1 (port_in_use / lsof)
```bash
# Start monitor
python3.11 backend/status/monitor.py &
sleep 2
# Confirm port_in_use works (launch.sh internal helper)
lsof -i :8769 >/dev/null 2>&1 && echo "PORT 8769 OPEN" || echo "FAIL"
```

### Verify Patch 2 (brew branch)
```bash
# On macOS with no pacman/apt/dnf installed:
bash scripts/install-vm.sh
# Should print: "  ✓ package manager:    brew"
```

### Verify Patch 5 (Cmd+Opt+D shortcut)
Launch the Tauri app and press Cmd+Option+D — the dashboard window should toggle.

### Verify Patch 7 (lsof-based port discovery in monitor.py)
```bash
# Start opencode in a tmux pane, then:
python3.11 backend/status/monitor.py --once
# Each bun pane should show a non-zero api_port value
```

### Verify Patch 8 (voice daemon on macOS)
```bash
python3.11 backend/voice/gmux_voice_daemon.py --model tiny --port 8770
# Should NOT print "pactl" errors
# Should print: "[audio] macOS CoreAudio backend ..."
# Should print: "[mic] started"
```

---

## Known remaining macOS limitations (not yet patched)

1. **`cam_broker_active` always returns False** — the camera gesture service
   (`gmux-cam-broker.service`) is a Linux systemd unit. To add macOS support,
   port the service to a `launchd` plist at
   `~/Library/LaunchAgents/com.gmux.cam-broker.plist`.
   Tracking: `TODO(macos)` comment in `monitor.py`.

2. **Python interpreter path** — scripts use `python3.11` explicitly. On
   Apple Silicon with Homebrew, it lives at
   `/opt/homebrew/bin/python3.11`. This is on PATH after
   `brew install python@3.11`. No code change needed if PATH is set correctly.

3. **DMG code signing** — `npm run tauri build` produces an unsigned `.app`.
   To distribute outside of your own machine, you need an Apple Developer ID
   certificate ($99/yr). For internal / team use, unsigned apps work with
   `xattr -d com.apple.quarantine gmuxtest.app`.

4. **`sqlite3` CLI** — `get_opencode_sessions()` in `lib.rs` calls `sqlite3`.
   macOS ships `sqlite3` in Xcode CLI tools. Run `xcode-select --install` if
   the command is missing.

5. **Voice daemon on Apple Silicon** — `faster-whisper` uses CTranslate2 which
   has arm64 wheels. The `--compute=int8` default should work; `float16` may
   be faster on M-series chips. Untested.

---

## Smoke test

A `scripts/macos-smoke-test.sh` script is provided. Run it on a fresh Mac:

```bash
bash scripts/macos-smoke-test.sh
```

It checks: macOS, tmux, python3.11, psutil+websockets+numpy, sounddevice,
faster-whisper, bun, opencode, cargo, node/npm, app/node_modules, lsof,
repo structure, and the backend unit tests.

Pass `--build` to also attempt a Tauri build (slow, ~15 min cold):

```bash
bash scripts/macos-smoke-test.sh --build
```

---

## Quick reference: Linux vs macOS equivalents

| Need | Linux | macOS |
|---|---|---|
| List listening ports | `ss -tlnp` | `lsof -i -P -n -sTCP:LISTEN` |
| Open URL in browser | `xdg-open URL` | `open URL` |
| Detach process (SSH-safe) | `setsid cmd &` | `nohup cmd &` |
| System package manager | pacman/apt/dnf | brew |
| GUI toolkit (Tauri) | libwebkit2gtk-4.1 | native WKWebView (built in) |
| Audio daemon | PulseAudio/PipeWire (`pactl`) | CoreAudio (no daemon) |
| Service manager | systemd (`systemctl --user`) | launchd (`launchctl`) |
| Network interfaces | `ip -4 addr show` | `ifconfig` |
| Global keyboard shortcut | Ctrl+Alt+Key | Cmd+Option+Key |
