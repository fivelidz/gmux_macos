# gmux-system — Deployment Targets

**Last updated:** 2026-05-12 (v3.4)

Concise per-OS deployment matrix. Use this to plan rollouts.

---

## Compatibility matrix

| Target | Backend (`monitor.py`) | Browser UI | Voice STT | Tauri desktop | Gestures (camera) | Notes |
|---|---|---|---|---|---|---|
| **CachyOS / Arch x86_64** (dev machine) | ✅ | ✅ | ✅ | ✅ | ✅ | Primary dev target; all features verified |
| **Debian / Ubuntu x86_64** | ✅ | ✅ | ✅ | ✅ (build needed) | ✅ | Webkitgtk-4.1 from apt; rustup for cargo |
| **Fedora / RHEL** | ✅ | ✅ | ✅ | ⚠ untested | ✅ | webkit2gtk available as `webkit2gtk4.1-devel` |
| **QEMU/KVM VM (headless CachyOS)** | ✅ | ✅ (via host browser + `?api=`) | ❌ no audio device | ❌ no display | ❌ no webcam | Used for backend integration testing |
| **Lima/multipass VM** | ✅ | ✅ | depends | ❌ no display | ❌ | Same as QEMU |
| **WSL2 on Windows 11** | ✅ (Linux side) | ✅ (Linux side) | ⚠ tricky | ❌ | ❌ | tmux works; browser opens via WSLview |
| **Native Windows** | ❌ no tmux | ❌ | ❌ | ⚠ would need WinPTY port | ❌ | Not currently a target — use WSL2 |
| **macOS (Apple Silicon)** | ✅ tmux via brew | ✅ | ⚠ sounddevice needs CoreAudio | ⚠ Tauri supports it | ✅ | Untested but should work |
| **Phone — Android Chrome** | n/a | ✅ (read-only useful) | ✅ via Web Speech API | n/a | ⚠ MediaPipe permission flow | Point at desktop's `:5550` via local network |
| **Phone — iOS Safari** | n/a | ✅ (read-only useful) | ⚠ Safari Web Speech limited | n/a | ⚠ same | Same — point at desktop |
| **Docker container** | ✅ minimal install | ⚠ needs host networking | ❌ no audio | ❌ no display | ❌ | See `extras/docker/` (not built yet) |
| **Cloud VM with display** | ✅ | ✅ | ⚠ no mic | ⚠ via X11 forwarding | ❌ no webcam | Backend role |

---

## Recommended deployment patterns

### Pattern A — Local dev box (everything on one machine)
- Monitor + voice + UI all on the same host
- Tauri desktop app
- Full feature set
- This is the everyday setup

### Pattern B — Server backend, browser frontend
- Backend on a Linux server (could be a headless VM, LXC, or remote box)
- Open browser on a laptop pointing at the server's IP
- Setup:
  ```
  # On server
  python3.11 backend/status/monitor.py &     # binds 0.0.0.0:8769
  python3 -m http.server 5550 --bind 0.0.0.0 # binds 0.0.0.0:5550

  # On client
  open http://<server-ip>:5550/ui/v3/index.html?api=http://<server-ip>:8769
  ```
- Verified on the QEMU sandbox VM (192.168.122.100) — see VM_DEPLOYMENT_LOG.md.

### Pattern C — Phone remote, desktop backend
- Backend + Tauri on the dev machine
- Phone browses to `http://<desktop-ip>:5550/ui/v3/index.html?api=http://<desktop-ip>:8769` over the local network
- Useful for monitoring agents while away from the keyboard
- HTTPS still needed for camera+mic on mobile (use Caddy or Tailscale serve)

### Pattern D — Docker (planned, not yet built)
- Single container for backend + voice
- Mount `/var/run/tmux*` from host so monitor can see tmux sockets
- Host networking for ports 8769 / 8770
- Browser UI served by host or another container
- Sketch in `extras/docker/` (TODO)

---

## Install recipes

### CachyOS / Arch
```bash
sudo pacman -Sy --noconfirm tmux git python python-pip nodejs npm rust webkit2gtk-4.1 base-devel
pip install --break-system-packages psutil websockets numpy
# Optional for voice:
pip install --break-system-packages sounddevice faster-whisper

curl -fsSL https://bun.sh/install | bash
~/.bun/bin/bun install -g opencode

git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system/app && npm install
./scripts/launch.sh
```

### Debian / Ubuntu 22.04+
```bash
sudo apt update
sudo apt install -y tmux git python3.11 python3-pip nodejs npm \
                    libwebkit2gtk-4.1-dev libsoup-3.0-dev libgtk-3-dev \
                    build-essential
pip install --user psutil websockets numpy
# Voice:
pip install --user sounddevice faster-whisper

# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

curl -fsSL https://bun.sh/install | bash
~/.bun/bin/bun install -g opencode

git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system/app && npm install
./scripts/launch.sh
```

### Headless VM (any Linux, no display)
```bash
# Skip Tauri, voice, gestures — backend + browser-from-host only
sudo pacman -S tmux git python python-pip   # or apt equivalent
pip install --break-system-packages psutil websockets

git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system

# Start with bind 0.0.0.0 so host can reach it
python3 backend/status/monitor.py &
python3 -m http.server 5550 --bind 0.0.0.0 &

# From your host machine browser:
# http://<vm-ip>:5550/ui/v3/index.html?api=http://<vm-ip>:8769
```

### WSL2 on Windows
```bash
# Inside Ubuntu/Debian WSL distro
sudo apt install -y tmux git python3.11 python3-pip
pip install --user psutil websockets numpy

git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
~/projects/gmux-system/scripts/launch.sh --browser

# In Windows browser
# WSL2 forwards localhost automatically, so:
# http://localhost:5550/ui/v3/index.html
```

---

## Per-target gotchas

### KDE / Wayland compositors
- **Tauri windows invisible without `GDK_BACKEND=x11`** — the launch script sets this automatically. If you launch Tauri manually without it, the window opens but stays under the active window.

### Wayland + camera (gestures)
- `getUserMedia` works fine
- MediaPipe requires a hardware GPU or software fallback; Tauri's WebKitGTK has had issues on some Wayland sessions — use the browser UI if Tauri gestures are broken.

### Headless VMs / containers
- **Ghostty crashes** with LLVM/AVX2 JIT abort on virtio GPU — use plain tmux or wezterm-headless
- **No `sounddevice` / no audio** — skip voice daemon; UI auto-detects and disables the mic button
- **No `webcam` device** — gesture engine fails silently; toggle stays unchecked

### Phone access
- **HTTPS required** for camera/mic on mobile browsers (any modern phone)
- For dev, use Tailscale's `ts cert` to get a real cert for your `*.tailnet.ts.net` hostname
- Without HTTPS the UI still loads — just no gesture/voice. Read-only monitor mode works fine.

### Firewall on VMs
- Default QEMU NAT lets the host reach VM ports but not vice versa — that's why we bind monitor + UI to `0.0.0.0` rather than `127.0.0.1`
- If using libvirt bridged networking, the VM gets a LAN IP and is reachable from anywhere on the LAN

---

## Performance expectations

| Setup | First-paint | Cold-start backend | Memory (RSS, idle) |
|---|---|---|---|
| Local browser only | <1s | 2s | ~60 MB Python + ~120 MB browser tab |
| Local Tauri (dev mode) | ~3s | 2s | ~60 MB Python + ~280 MB Tauri |
| Local Tauri (release build) | ~1.5s | 2s | ~60 MB Python + ~180 MB Tauri |
| Phone over LAN | <2s | n/a (server-side) | n/a |
| Headless VM (host browser) | <1s | 2s | ~50 MB Python (no GUI) |

Tauri dev mode is the slow option — see `DEPENDENCIES.md` section D for the release-build path.

---

## Tested as of 2026-05-12

| Target | Status | Tested commit |
|---|---|---|
| CachyOS local | ✅ all features | `8a5db96` |
| QEMU CachyOS VM | ✅ backend + remote browser | `8a5db96` (sub-agent deployed) |
| Phone Chrome | ⏳ untested | — |
| Debian VM | ⏳ untested | — |
| Tauri release build | ⏳ untested | — |
| Docker | ❌ not built | — |

---

## Next deployment targets to test

1. **Debian VM** — spin up a fresh Debian QEMU image, run install recipe end-to-end
2. **Tauri release build on the main host** — `cd app && npm run tauri build`, run the produced binary, measure perf delta vs dev mode
3. **Phone PWA** — set up Tailscale serve, test on actual Android device
4. **Docker container** — write Dockerfile, test from a fresh Arch image
5. **macOS** — see detailed assessment below

---

## macOS deployment — detailed assessment (v3.5)

### Theoretical compatibility

| Component | macOS support | Confidence |
|---|---|---|
| `monitor.py` (Python stdlib + tmux) | ✅ should work as-is | high |
| `psutil` | ✅ pip wheel available for arm64 + x86_64 | high |
| `tmux` | ✅ `brew install tmux` | high |
| `bun` / `opencode` | ✅ official macOS support | high |
| Tauri 2 desktop app | ✅ native WebKit, no `webkit2gtk` needed | high |
| `portable-pty` (Rust crate) | ✅ macOS supported | high |
| `tauri-plugin-global-shortcut` | ⚠ needs key-code re-check (Cmd vs Ctrl/Alt) | medium |
| `faster-whisper` + `sounddevice` (voice) | ⚠ CoreAudio backend, untested but should work | medium |
| MediaPipe gesture engine | ✅ AVFoundation camera, universal binary | medium |
| `xdg-open` calls in code | ❌ does not exist on macOS — must use `open` | low (easy fix) |
| Hard-coded `python3.11` paths | ⚠ Homebrew installs at `/opt/homebrew/bin/python3.11` (arm64) | low (PATH covers it) |

### Known code-level fixes needed before macOS works

These have been identified by reading the codebase; none have been tested on a Mac yet.

1. **`scripts/launch.sh`** uses `pgrep -f` and `ss -tlnp`:
   - macOS `pgrep` is BSD — `-f` works but pattern-matching is case-sensitive
   - macOS does NOT have `ss` — must fall back to `lsof -i -P -n | grep LISTEN`
   - Suggested change: detect with `uname -s` and switch command per OS

2. **`backend/voice/gmux_voice_daemon.py`** assumes PulseAudio:
   - `pactl info` won't exist; `sounddevice` will still work because it goes
     through PortAudio → CoreAudio directly
   - Remove any explicit pactl preflight checks

3. **`app/src-tauri/src/lib.rs` global shortcut** registers `Ctrl+Alt+D`:
   - On macOS users expect `Cmd+Opt+D`. Tauri's `Modifiers::META` is Cmd on macOS.
   - Suggested: register both, or branch on `cfg!(target_os = "macos")`

4. **OAuth-flow URL surfacing** (when v3.6 provider auth lands):
   - Must use `open <url>` not `xdg-open <url>`
   - Helper: `std::process::Command::new(if cfg!(target_os = "macos") { "open" } else { "xdg-open" })`

5. **`scripts/launch.sh`** sets `GDK_BACKEND=x11`:
   - Harmless on macOS but irrelevant — wrap in `if [ "$(uname -s)" = "Linux" ]`

6. **MediaPipe model path resolution** is fine — uses HOME via env, works cross-platform.

### What macOS users get for free (without any code changes)

- Backend monitor on `:8769`
- Browser UI from `python3 -m http.server` or any static server
- Live data flow through `/tmp/gmuxtest-*.json` (macOS `/tmp` is writable user-readable, fine)
- tmux pane tracking
- opencode/bun agents (they already support macOS)

### What requires the v3.6 polish pass

- Tauri desktop app build + DMG packaging (`npm run tauri build` should produce a .app and DMG already)
- Voice daemon — likely works but untested
- Gesture engine — likely works but untested
- Global shortcuts — needs the Cmd-vs-Ctrl branch
- Launch script cross-OS support

### Recommended path forward

**Phase 1 (do first, takes a few hours on a Mac):**
1. `git clone gmux-system` on a Mac
2. `brew install tmux node rust python@3.11`
3. `pip3.11 install --user psutil websockets`
4. `bash scripts/launch.sh --browser` — should produce a working browser UI
5. Document any issues in `docs/VM_REPORTS/macos-phase1.md`

**Phase 2 (Tauri):**
1. `cd app && npm install && npm run tauri dev`
2. Expect 1-2 errors related to missing tooling; iterate
3. Once dev mode runs, try `npm run tauri build` for the production .app
4. Document in `docs/VM_REPORTS/macos-tauri.md`

**Phase 3 (full feature):**
1. Test voice + gestures
2. Fix the Cmd-vs-Ctrl shortcut issue
3. Fix `xdg-open` → `open` for provider auth
4. Produce a code-signed DMG (requires Apple Developer cert — separate cost discussion)

### What this means for the user asking "have we made an assessment?"

**Yes — and here it is.** Summary:
- No fundamental blocker. macOS should be ~95% compatible.
- The 5% that breaks is small-scale platform differences (pgrep, ss, xdg-open, Cmd vs Ctrl) that are 1-line fixes each.
- We have not actually run it on a Mac yet, so any of the above could surprise us.
- DMG distribution to non-developers needs a Developer ID and notarisation — that's a paperwork problem, not a code problem.
- Estimated effort to get gmux-system working on macOS once a Mac is available: **one focused day** for Phase 1+2, another day for Phase 3.
