# gmux-system — Dependencies & Optimization Guide

**Last updated:** 2026-05-12 (v3.3)

This document lists every runtime dependency, why it's needed, and what can be
optimized away or made optional.

---

## TL;DR

| Layer | Required? | What for |
|---|---|---|
| **tmux 3.5+** | YES, hard requirement | The whole multiplexer is built on it |
| **Python 3.11+** | YES, hard requirement | All backend daemons |
| **psutil (Python)** | optional | RAM/CPU/uptime fields; without it those are zero |
| **opencode** (or `bun` running `qalcode2`) | optional but expected | Without an agent there's nothing to monitor |
| **Node.js 18+ / npm / Rust + cargo** | only for Tauri desktop app | Browser UI works without these |
| **WebKitGTK 2.40+** | only for Tauri | Linux Tauri WebView; not needed for browser |
| **A display server** | only for Tauri / camera / voice | Headless mode supports backend + browser only |
| **PulseAudio / PipeWire** | only for voice STT | sounddevice needs ALSA/Pulse |
| **MediaPipe model (`hand_landmarker.task`)** | only for gestures | 7.5 MB binary, fetched once from CDN or bundled |

---

## Full dependency tree

### 1. The backend daemon (`backend/status/monitor.py`)

**Mandatory:**
- Python 3.10+ (uses `dataclasses`, `:=` walrus, modern typing)
- `tmux` 3.0+ in `$PATH`
- Standard library only — `http.server`, `socketserver`, `urllib`, `subprocess`, `json`, `re`, `threading`

**Optional (graceful degradation):**
- `psutil` — for `ram_mb`, `cpu_pct`, `uptime_s`, `children` fields per pane
  - Without it, all four stay at 0, UI shows `—` placeholders
  - Install: `pip install psutil`

**External services it talks to:**
- Each opencode instance's HTTP API (random port per pane, discovered via `ss -tlnp`)
- The opencode SQLite DB at `~/.local/share/opencode/opencode.db` (read via `sqlite3` CLI)

### 2. Voice daemon (`backend/voice/gmux_voice_daemon.py`)

**Mandatory if you want voice STT:**
- `faster-whisper` (`pip install faster-whisper`) — Whisper STT models
- `sounddevice` (`pip install sounddevice`) — mic capture
- `websockets` (`pip install websockets`) — broadcast transcripts to UI
- `numpy` (`pip install numpy`) — audio buffer math
- A working PulseAudio or PipeWire daemon (`pactl info` must succeed)

**Model files:**
- First run downloads ~75 MB Whisper "tiny" model into `~/.cache/huggingface/`
- Larger models work (`--model small` = 460 MB) but slower

**Skip voice entirely?** Just don't launch the daemon. UI auto-detects ws://:8770
is unreachable and silently disables the mic button.

### 3. Session restore (`backend/session/session_restore.py`)

**Mandatory:** Python stdlib only.
**Optional for full feature:** `tmux-resurrect` plugin (already at
`~/.tmux/plugins/tmux-resurrect/` on the main machine). Without it, window
names persist via our own `/tmp/gmux-window-names.json` cache only.

### 4. The Tauri desktop app (`app/`)

**Mandatory for `tauri dev` or `tauri build`:**
- **Rust** 1.75+ (`rustc`, `cargo`) — get via rustup or `pacman -S rust`
- **Node.js 18+** + **npm** — for Vite dev server
- **WebKitGTK 2.40+** + dev headers:
  - Arch/CachyOS: `pacman -S webkit2gtk-4.1`
  - Debian/Ubuntu: `apt install libwebkit2gtk-4.1-dev`
- **libsoup3**, **glib-2.0**, **gtk3** dev headers
- Build deps: `build-essential` / `base-devel`

**At runtime (production build):**
- Just WebKitGTK + glib + gtk runtime
- `GDK_BACKEND=x11` on KDE Wayland (otherwise window stays invisible)

### 5. The browser UI (`ui/v3/index.html`)

**Mandatory:**
- A modern browser (Chromium 120+ / Firefox 120+ / WebKitGTK 2.40+)
- An HTTP server to serve the file (Python's `http.server` is enough)

**Optional features that require browser permissions:**
- **Webcam** for gestures (`getUserMedia({video})`)
- **Mic** for voice (`getUserMedia({audio})`)
- **WebSocket** for live voice transcript (auto if voice daemon up)

**MediaPipe model:** the gesture engine fetches `/hand_landmarker.task` from
the same origin as the HTML, OR falls back to Google's CDN. To avoid the
CDN call, copy `~/.local/share/kalarc/models/hand_landmarker.task` next to
`index.html`.

### 6. The agents (opencode / qalcode2 / claude / aider)

These are **what** the system monitors, not required to install themselves.
But for a useful demo:
- `opencode` from npm: `npm i -g opencode` (or use bun)
- `claude` CLI from Anthropic
- `aider` from pip: `pip install aider-chat`

---

## Optimisation paths

### A — Cut the dependency surface for headless servers

If you're running this on a server / VM with no display, you can skip:
- Tauri (Rust, Node, WebKitGTK)
- Voice (faster-whisper, sounddevice, numpy)
- Gesture model (no camera anyway)

The minimal headless install is **just Python + tmux + opencode**, with
`psutil` as the only optional pip dep. Backend listens on `:8769`, you point
a browser on another machine at `http://<server>:8769/api/state`.

### B — Make voice optional at build-time

Move the voice daemon import block into a try/except guard (already done in
`backend/voice/gmux_voice_daemon.py`). The launcher script `scripts/launch.sh`
already skips spawning voice if the deps are missing — currently it would
just fail with a Python traceback in `/tmp/gmux-voice.log`. Improvement: have
the launcher pre-check `python3 -c "import faster_whisper"` and only attempt
voice if that succeeds.

### C — Tauri release build vs dev build

`npm run tauri dev` runs Vite with HMR + a full WebKitGTK debug build. This
is the laggy mode the user has been seeing. A `tauri build` produces a single
binary at `src-tauri/target/release/<appname>` with:
- No Vite (HTML is bundled)
- Release-mode Rust optimisations
- ~3-5x faster scrolling and event handling on WebKitGTK

Time investment: one-off `cargo install tauri-cli && npm run tauri build`
(~3 min cold).

### D — Reduce monitor polling frequency

Default: `POLL_INTERVAL = 2.0` (tmux poll) and `AGGREGATE_INTERVAL = 10.0`
(opencode message aggregator). On a quiet system you can bump these to 5s
and 30s respectively. Edit at the top of `monitor.py`.

### E — Cache the MediaPipe model

The 7.5 MB `hand_landmarker.task` is fetched on every cold load if you go via
CDN. Bundle it next to `index.html` and the gesture engine prefers the local
copy.

### F — Drop session_restore daemon

If you don't care about agent window names persisting across reboots, skip
launching `session_restore.py --daemon`. Saves ~10 MB RSS and one Python
process.

---

## Install on a fresh CachyOS / Arch machine

```bash
# 1. System packages
sudo pacman -Sy --noconfirm tmux git python python-pip nodejs npm rust webkit2gtk-4.1 base-devel pulseaudio

# 2. Python deps (system-wide)
pip install --break-system-packages psutil websockets numpy sounddevice faster-whisper

# 3. Bun + opencode (for the agents)
curl -fsSL https://bun.sh/install | bash
~/.bun/bin/bun install -g opencode-ai

# 4. Clone the repo
git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system

# 5. Tauri deps (if building desktop app)
cd app && npm install && cd ..

# 6. Run
./scripts/launch.sh           # full system
./scripts/launch.sh --browser # browser-only mode
```

---

## Install on a fresh Debian / Ubuntu machine

```bash
sudo apt update
sudo apt install -y tmux git python3.11 python3-pip nodejs npm \
                    libwebkit2gtk-4.1-dev libsoup-3.0-dev libgtk-3-dev \
                    build-essential pulseaudio

# Rust via rustup
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

# Python deps
pip install --user psutil websockets numpy sounddevice faster-whisper

# Bun + opencode
curl -fsSL https://bun.sh/install | bash
~/.bun/bin/bun install -g opencode-ai

# Clone + run
git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system/app && npm install
cd ..
./scripts/launch.sh
```

---

## What's been verified working on

| Platform | Status | Notes |
|---|---|---|
| CachyOS x86_64 (the main dev machine) | ✅ everything | Daily driver |
| QEMU VM (CachyOS, no display) | ⏳ backend only | See VM_DEPLOYMENT.md |
| Phone (Android Chrome) | ⏳ partial | Browser UI loads, no gestures (no MediaPipe permission) |
| macOS | ❌ untested | Should work for backend + Tauri; voice needs `pulseaudio` replacement |
| Windows | ❌ untested | Tauri has Windows support; voice/tmux need WSL2 |

---

## Optimization wins (delivered v3.0 → v3.3)

- ✅ Replaced full-merge poll with event-driven SSE listeners per pane → 90% less polling overhead
- ✅ Lazy chat fetch (only when chat panel open) → no traffic on agents you're not looking at
- ✅ Markdown renderer is regex-only, no DOMParser → ~5x faster than naive innerHTML+library
- ✅ pane render uses `el.innerHTML = …` not separate node creation → fast on WebKitGTK
- ✅ Session derivation is O(n) over panes, cached in `SESSIONS` array — only re-renders tabs on actual change

## Optimization opportunities (open)

- ⬜ `tauri build` for production binary (vs dev mode) — easiest 3-5x perf win
- ⬜ Coalesce render() calls within a single rAF frame (currently can fire 3× on rapid state)
- ⬜ Virtualise the agent sidebar if >50 panes (currently always renders all)
- ⬜ Move markdown rendering off the render hot-path → render plain text first, decorate after
- ⬜ Cache rendered HTML per (pane_id, state_hash) — skip re-render when nothing changed
