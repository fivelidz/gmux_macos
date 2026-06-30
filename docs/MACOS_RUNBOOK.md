# gmux on macOS — Runbook (the smooth path)

One page. Everything we learned from a real install, turned into a fast,
repeatable procedure. For the full narrative see
[`VM_REPORTS/macos-install-log.md`](VM_REPORTS/macos-install-log.md).

---

## TL;DR — one command

```bash
git clone https://github.com/fivelidz/gmux_macos.git ~/projects/gmux_macos
cd ~/projects/gmux_macos
bash scripts/macos-bootstrap.sh --terminal      # backend + browser UI + gmux CLI + tmux
# add --app to also build the desktop app (slow), or --check to survey only
```

The bootstrap is **idempotent** and **brew-free-capable**. It surveys what's
present, installs only the gaps, and avoids every trap below.

---

## The traps (and why the scripts now avoid them)

| # | Trap | Symptom | Fix (now automatic) |
|---|------|---------|---------------------|
| 1 | **Linux `package-lock.json` committed** | `@esbuild/darwin-x64 could not be found` during `npm run tauri build` | lockfile is now git-ignored; npm regenerates per-OS. If you still hit it: `rm -rf app/node_modules app/package-lock.json && npm i` |
| 2 | **Hardcoded `python3.11`** | `python3.11: command not found` (Mac has 3.14) | scripts now auto-pick `python3.11→…→python3` |
| 3 | **`setsid` is Linux-only** | `setsid: command not found` | `gmux` falls back to `nohup` on macOS |
| 4 | **`timeout` not on macOS** | `timeout: command not found` | use `gtimeout` (coreutils) or none; scripts avoid it |
| 5 | **`~/.zshrc` vs `~/.zprofile`** | tool works in Terminal but not via SSH/scripts | launchers self-prepend `~/.bun/bin` & `~/.cargo/bin` |
| 6 | **Broken Homebrew blocks everything** | `brew --version` errors | NOT a blocker — install `rg` via `cargo install`, python via system; brew only needed to *acquire* missing deps |
| 7 | **Mac goes offline (sleep)** | Tailscale "offline, last seen Nm ago"; SSH times out | run `scripts/macos-keepalive.sh` on the Mac |
| 8 | **Demo agents won't clear** | UI shows sample agents on a fresh deploy | fixed in code: mock seed clears once backend connects (commit 95412eb) |
| 9 | **APFS corruption masquerading as a brew bug** | `git checkout`/`touch` fail to create *specific* files in a writable dir | run `sudo diskutil verifyVolume /`; if it fails → Recovery-Mode First Aid. **If brew dir is corrupt:** archive it (`sudo mv /usr/local/Homebrew /usr/local/Homebrew.broken`), `git clone https://github.com/Homebrew/brew /usr/local/Homebrew`, relink `/usr/local/bin/brew`. Cellar packages survive. |
| 10 | **Heredocs over nested SSH quoting** | mangled config files | `scp` a file instead of heredoc-over-ssh |
| 11 | **Ghostty requires macOS 13+** | `dyld: Library not loaded: AppIntents.framework` — Ghostty won't launch on Monterey (12) | Ghostty ≥1.x needs Ventura. On macOS 12 use **WezTerm** (recommended) or Terminal.app. Check `LSMinimumSystemVersion` in the app's Info.plist. |
| 12 | **brew on macOS 12 is "Tier 3"** | source-builds (cmake, tmux) are slow (15-20 min) and easy to mistake for hung; spawning a 2nd `brew install` hits a lock | run ONE install, detached, and leave it. `ps aux \| grep clang` confirms it's compiling. **tmux without cmake:** build from source — `./configure --disable-utf8proc && make` against existing libevent/ncurses (avoids the slow cmake build entirely). |
| 13 | **iTerm2 memory leak under TUI agents** | iTerm `phys_footprint` balloons to tens of GB running an animated TUI (qalcode/opencode); whole Mac beachballs from swap exhaustion | Quit iTerm, clear `~/Library/Saved Application State/com.googlecode.iterm2.savedState` (it restores the bloated session), `sudo purge`. **Use WezTerm instead** with `max_fps=30`, `scrollback_lines=10000`, no transparency/blur. |
| 14 | **8 GB Mac swaps hard with Chrome + iTerm + agent** | load 8–14 on 2 cores, 20+ GB swap, beachball | `scripts/macos-perf-cleanup.sh` (kills stale dev procs, purges); close Chrome tabs; remove Zoom/uTorrent from login items & uninstall if unused. |
| 15 | **`~/Documents` & `~/Desktop` are TCC-protected** | SSH/automation gets "Operation not permitted" listing them; AI tools hit permission walls if projects live there | Keep the projects folder at a **top-level, non-TCC path like `~/Code`** (SSH-accessible + shows in Finder). Symlink `~/projects → ~/Code` for back-compat. Redirect screenshots off Desktop: `defaults write com.apple.screencapture location ~/Pictures/Screenshots`. |

---

## What gmux actually needs (minimum)

- **Phase 1 (backend + browser UI):** `python3` (3.10+) + `psutil`. That's it.
- **Terminal-multiplexer mode:** `+ tmux`.
- **qalcode (AI coder):** `+ bun + ripgrep` (rg via cargo if no brew).
- **Phase 2 (desktop .app):** `+ node + npm + rust/cargo` + Xcode CLT.

> Node, Rust, Python, and psutil are frequently *already present* on a dev Mac.
> Survey first (`--check`), install only gaps.

---

## Two ways to run gmux on macOS

### A) Terminal-multiplexer mode (lightweight, no GUI) — recommended first
```bash
gmux --backend-only     # monitor :8769 + UI server :5550, headless
gmux attach             # enter the tmux 'gmux' session (the multiplexer)
gmux status             # list panes from the monitor
```
Run `qalcode` inside tmux panes; `gmux status` sees them. No WebView, no signing,
no Gatekeeper — robust.

### B) Desktop app (Tauri WKWebView)
```bash
cd app && npm install && npm run tauri build
# → app/src-tauri/target/release/bundle/macos/*.app
# global shortcut: Cmd+Opt+D toggles the dashboard window
```

---

## Remote support checklist (driving a Mac from elsewhere)

On the Mac, once:
- System Settings → General → Sharing → **Remote Login ON** (persistent sshd)
- Standalone Tailscale.app (NOT App Store — it lacks `tailscale ssh`)
- `bash scripts/macos-keepalive.sh`  ← prevents sleep, ensures auto-reconnect
- Admin console: **disable key expiry** for the node (web only)

From the operator:
- add your SSH pubkey to the Mac's `~/.ssh/authorized_keys`
- `ssh <user>@<tailscale-ip>` (use the `100.x` IP if MagicDNS/resolved is flaky)

---

## Quick diagnostics

```bash
# Mac unreachable?  -> it's asleep/offline. Wake it. Then:
tailscale status | grep macbook

# Backend up?
curl -s localhost:8769/health           # -> ok
curl -s localhost:8769/api/state         # -> {} is correct when idle

# qalcode missing a dep?
qalcode --help ; which rg bun

# Filesystem suspicious?
sudo diskutil verifyVolume /
```
