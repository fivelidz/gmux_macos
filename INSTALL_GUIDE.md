# gmux-system — Install Guide

End-to-end install for a fresh machine. Companion to `DEPENDENCIES.md`
(which lists every dep + why) and `DEPLOYMENT_TARGETS.md` (which OS).

If you only want the 5-minute version: scroll to **One-shot install
recipes** at the bottom.

---

## The full stack — what runs where

```
┌─────────────────────────────────────────────────────────────────────┐
│                        gmux-system stack                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Tauri desktop app  (or browser)                              │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  ui/v3/index.html   (main UI — tabs, panes, chat)       │  │  │
│  │  │  app/src/dashboard/ (Agent Monitor — flowchart)         │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘    │
│             │                                                        │
│             │ Tauri IPC (open_agent, list_providers, etc.)            │
│             ▼                                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  app/src-tauri/src/lib.rs    (Rust shell — PTY, windows)      │  │
│  │  - portable-pty: attaches to tmux session 'gmux'              │  │
│  │  - spawns sidecars: monitor, voice, session-restore           │  │
│  │  - registers 3 windows: main, aquarium, dashboard             │  │
│  │  - state-poll thread: reads /tmp/gmuxtest-*.json every 1s     │  │
│  │    and broadcasts as Tauri events to the windows              │  │
│  └───────────────────────────────────────────────────────────────┘  │
│             │                       │                                │
│             ▼                       ▼                                │
│  ┌──────────────────────┐  ┌──────────────────────┐                  │
│  │  tmux server          │  │  /tmp/gmuxtest-*.json │                  │
│  │  session = 'gmux'     │  │  - pane-state         │                  │
│  │  one window per       │  │  - services           │                  │
│  │  agent + opencode     │  │  - activity (NEW)     │                  │
│  │                       │  │  - files (NEW)        │                  │
│  └──────────────────────┘  │  - memory (TODO)      │                  │
│             ▲              └──────────────────────┘                  │
│             │                       ▲                                │
│             │ pane events           │ produced by                    │
│             ▼                       │                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  backend/status/monitor.py   (Python, :8769)                │    │
│  │  - polls tmux every 2s for pane structure                    │    │
│  │  - subscribes to each opencode SSE feed                      │    │
│  │  - tracks tool calls, file touches, sub-agents               │    │
│  │  - writes the JSON files above, atomically                   │    │
│  │  - serves HTTP /api/state, /api/stream, /health              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│             ▲                                                        │
│             │ HTTP (SSE) — random ports per agent                    │
│             ▼                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  bun + opencode    (one bun process per agent pane)          │   │
│  │  - each agent is `bun /home/.../opencode-bin/opencode`       │   │
│  │  - listens on random port 30000-65000                        │   │
│  │  - reads ~/.local/share/opencode/auth.json for credentials   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│             │                                                        │
│             ▼                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Cloud providers   (Anthropic, OpenAI, Google, ...)          │   │
│  │  - OAuth refresh tokens in auth.json                         │   │
│  │  - or API keys in env vars (ANTHROPIC_API_KEY etc.)          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Optional sidecars                                            │   │
│  │  - backend/voice/gmux_voice_daemon.py   ws://localhost:8770   │   │
│  │  - backend/session/session_restore.py   (window-name persist) │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component summary

| Layer | What it does | Required? |
|---|---|---|
| **tmux server** | Hosts the `gmux` session; every agent = one window | Always |
| **bun + opencode** | The actual AI agent | Always (1+ per useful demo) |
| **monitor.py** | Backend daemon. Tracks tmux + opencode SSE. Writes JSON state. | Always |
| **Tauri app** | Desktop UI shell. PTY-attaches to tmux, displays dashboard. | Optional (browser is the alternative) |
| **Browser UI** | Same HTML as Tauri but served over HTTP. No PTY. | Optional |
| **voice daemon** | faster-whisper STT, broadcasts transcripts. | Optional |
| **session_restore** | Persists window names across tmux restarts. | Optional |
| **MediaPipe model** | Hand-tracking for the gesture UI. | Optional |

### Network ports

| Port | Bound by | Purpose |
|---|---|---|
| 8769 | monitor.py | HTTP state API + SSE stream |
| 8770 | voice daemon | WebSocket for live transcripts |
| 5550 | http.server | Browser UI (only in `--browser` mode) |
| 30000-65000 | opencode | Per-agent random port |
| 11434 | Ollama (optional) | Local LLM HTTP |

---

## Install flow — step by step

Below is the procedure for getting another computer running gmux-system
end-to-end. CachyOS / Arch is the reference distro; Debian and macOS
deltas follow.

### Stage 0 — Pre-flight

You need:
- A user account (not root) you'll run gmux as
- Network access for first install
- ~3 GB free disk (Tauri build artifacts are 2 GB; the rest is dependencies)

```bash
# Verify clean prerequisites
uname -a                       # Confirm Linux
echo $HOME                     # Confirm you're not root
df -h $HOME | head             # ≥ 3 GB free
```

### Stage 1 — System packages (5 min)

**CachyOS / Arch:**
```bash
sudo pacman -Syu --noconfirm
sudo pacman -S --noconfirm \
  tmux git python python-pip nodejs npm rust \
  webkit2gtk-4.1 base-devel pulseaudio \
  curl rsync openssh
```

**Debian / Ubuntu 22.04+:**
```bash
sudo apt update
sudo apt install -y \
  tmux git python3.11 python3-pip nodejs npm \
  libwebkit2gtk-4.1-dev libsoup-3.0-dev libgtk-3-dev \
  build-essential pulseaudio curl rsync openssh-client

# Rust via rustup (Ubuntu's apt version is too old for Tauri 2)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env
```

**macOS:**
```bash
# Homebrew first if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install tmux git python@3.11 node rust openssh
# WebKit is built-in; no webkit2gtk dependency on macOS
```

Verify:
```bash
python3.11 --version           # ≥ 3.11
tmux -V                        # ≥ 3.0
node --version                 # ≥ 18
cargo --version                # ≥ 1.75
```

### Stage 2 — Python dependencies (2 min)

```bash
# Mandatory: psutil (process metrics), websockets (voice broadcast)
pip3.11 install --user psutil websockets requests numpy

# Optional: voice STT (faster-whisper)
pip3.11 install --user faster-whisper sounddevice

# On Arch with newer pip:
pip3.11 install --user --break-system-packages psutil websockets requests numpy
```

### Stage 3 — bun + opencode (2 min)

```bash
# bun (the JS runtime opencode targets)
curl -fsSL https://bun.sh/install | bash
# bun lands at ~/.bun/bin/bun

# opencode (the AI agent CLI)
~/.bun/bin/bun install -g opencode-ai

# Add to PATH (fish: ~/.config/fish/config.fish ; bash: ~/.bashrc)
# echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.bashrc

# Verify
~/.bun/bin/opencode --version
```

### Stage 4 — Clone the repo (1 min)

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/fivelidz/gmux-system.git
cd gmux-system
```

### Stage 5 — Tauri build deps (5 min — only if you want the desktop app)

```bash
cd ~/projects/gmux-system/app
npm install
# Pulls @tauri-apps/api, @xterm/xterm, vite, tauri-cli
# First run also resolves the Cargo registry under app/src-tauri/target/
# Expect ~120 MB node_modules + 1.5 GB target/ on first cargo check
```

### Stage 6 — Configure a provider (3 min — once per machine)

You can do this **either** via the gmux UI (Step 8 below — "Connect a
provider" button), **or** from a terminal first if you'd rather have
auth ready before launch:

```bash
opencode auth login anthropic   # or openai / google / etc.
# Opens browser → OAuth flow → paste the callback URL back into terminal
# Stores credentials in ~/.local/share/opencode/auth.json
```

Or use an API key from env:
```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc   # bash
echo 'set -gx ANTHROPIC_API_KEY sk-ant-...' >> ~/.config/fish/config.fish  # fish
```

### Stage 7 — Smoke test the backend (1 min)

```bash
cd ~/projects/gmux-system
python3.11 backend/status/monitor.py &
sleep 3
curl http://127.0.0.1:8769/health           # expect: ok
curl http://127.0.0.1:8769/api/state | head # expect: JSON
ls /tmp/gmuxtest-*.json                     # expect: 5 files
pkill -f backend/status/monitor.py          # cleanup
```

If anything fails, check `/tmp/gmux-monitor.log`.

### Stage 8 — First launch

```bash
cd ~/projects/gmux-system
./scripts/launch.sh
```

What happens:
1. Spawns monitor.py on :8769 (if not already running)
2. Spawns voice daemon on :8770 (if deps available — silently skipped otherwise)
3. Sets `GDK_BACKEND=x11` (KDE/Wayland compatibility) + GStreamer crash workarounds
4. Auto-syncs `ui/v3/index.html` → `app/src/index.html` if newer
5. Auto-syncs `ui/v3/dashboard/` → `app/src/dashboard/` if newer
6. Runs `npm run tauri dev` from `app/`
7. Tauri compiles Rust (first time = ~3 min), opens the desktop window

If the **First-launch auth wizard** runs and no provider is configured,
the Options → Providers tab auto-opens with a "Connect a provider" callout.

### Stage 9 — Verify everything

Inside the Tauri window:
- Press `N` → New Agent modal opens
- Pick "QalCode 2", enter `~/projects/gmux-system` as working dir
- Click Create
- A new tmux window opens with opencode running in that directory
- The new pane appears in the grid within ~2s
- Press Ctrl+Alt+D → Agent Monitor window opens; HUD shows tick counters

### Stage 10 — Optional: faster builds

```bash
# Production Tauri build (faster than dev mode, smaller binary)
cd ~/projects/gmux-system/app
npm run tauri build

# Produces:
#   app/src-tauri/target/release/gmuxtest  (Linux binary)
#   app/src-tauri/target/release/bundle/   (AppImage, .deb, etc.)
```

The release binary uses ~180 MB RSS vs ~280 MB in dev mode (per
DEPENDENCIES.md performance table).

---

## One-shot install recipes

### CachyOS / Arch — copy-paste

```bash
sudo pacman -Syu --noconfirm
sudo pacman -S --noconfirm tmux git python python-pip nodejs npm rust \
  webkit2gtk-4.1 base-devel pulseaudio curl rsync openssh

pip install --break-system-packages --user psutil websockets requests numpy

curl -fsSL https://bun.sh/install | bash
~/.bun/bin/bun install -g opencode-ai

mkdir -p ~/projects
git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system/app && npm install
cd ~/projects/gmux-system && ./scripts/launch.sh
```

### Debian / Ubuntu — copy-paste

```bash
sudo apt update && sudo apt install -y \
  tmux git python3.11 python3-pip nodejs npm \
  libwebkit2gtk-4.1-dev libsoup-3.0-dev libgtk-3-dev \
  build-essential pulseaudio curl rsync openssh-client

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

pip3.11 install --user psutil websockets requests numpy

curl -fsSL https://bun.sh/install | bash
~/.bun/bin/bun install -g opencode-ai

mkdir -p ~/projects
git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system/app && npm install
cd ~/projects/gmux-system && ./scripts/launch.sh
```

### Backend-only / headless (VM, cloud, container)

If you only need the monitor + browser UI:

```bash
# Minimal deps
sudo apt install -y tmux python3.11 python3-pip git
pip3.11 install --user psutil websockets

# Clone + run backend
git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system
cd ~/projects/gmux-system

# Start monitor (use setsid so it survives SSH disconnect on a VM)
setsid python3.11 backend/status/monitor.py </dev/null >/tmp/gmux-monitor.log 2>&1 &
disown

# Start UI HTTP server bound to all interfaces (so the host can reach it)
setsid python3 -m http.server 5550 --bind 0.0.0.0 \
  </dev/null >/tmp/gmux-ui.log 2>&1 &
disown
```

From any browser on the LAN:
- `http://<vm-ip>:5550/ui/v3/index.html`
- `http://<vm-ip>:8769/api/state` (raw data)

---

## Common install issues

### "no python3.11" on macOS
Homebrew installs as `python3.11`. Add Homebrew to PATH:
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
```

### "webkit2gtk-4.1 not found" on Ubuntu < 22.04
Ubuntu 20.04 ships 4.0; Tauri 2 needs 4.1. Either upgrade Ubuntu or:
```bash
sudo add-apt-repository ppa:webkit-team/ppa -y && sudo apt update
sudo apt install -y libwebkit2gtk-4.1-dev
```

### Tauri window opens but is invisible (KDE Wayland)
`scripts/launch.sh` sets `GDK_BACKEND=x11` to fix this. If you're
launching `npm run tauri dev` directly, export it yourself.

### "bun: command not found" after install
The installer drops `bun` at `~/.bun/bin/`. Either source the line it
adds to your shell rc, or just `export PATH="$HOME/.bun/bin:$PATH"`.

### Opencode fails with "no provider configured"
You haven't run `opencode auth login` or set an `*_API_KEY` env var.
Open the Tauri app → Options → Providers → Connect.

### Cargo first-build takes forever
First `npm run tauri dev` compiles ~400 crates. ~3 minutes on a modern
CPU. Subsequent builds are incremental (<1 min). The artifacts go in
`app/src-tauri/target/` (~1.5 GB).

### Voice daemon won't start
`faster-whisper` needs `libsoundfile` + CUDA-optional / CPU-fallback.
On a headless VM with no audio, just skip it — `launch.sh` will start
gmux without voice and the mic button will be inactive.

### Monitor dies silently on a VM
nohup gets severed when SSH closes on some VMs. Use `setsid` instead
(see the "Backend-only" recipe above).

---

## Updating

```bash
cd ~/projects/gmux-system
git pull
cd app && npm install     # only if package.json changed
cd .. && ./scripts/launch.sh
```

The launcher auto-syncs UI files and detects when Rust needs to rebuild.

---

## Uninstalling

```bash
# Stop everything
pkill -f gmux-system/backend
pkill -f gmux-system/app
tmux kill-session -t gmux 2>/dev/null

# Remove the repo + build artifacts
rm -rf ~/projects/gmux-system

# Remove auth (optional — kills credentials for all opencode users on this account!)
# rm ~/.local/share/opencode/auth.json

# Remove tmp state
rm -f /tmp/gmuxtest-*.json /tmp/gmux-*.log
```

We don't install anything system-wide, so there's nothing else to clean up.
