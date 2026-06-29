# Installing Ghostty on macOS — Instructions for a Claude Agent

> **You are a Claude coding agent.** Install **Ghostty**, a fast GPU-accelerated
> terminal, on this macOS machine. This is a quick task. Read, then do.

---

## What Ghostty is

**Ghostty** is a fast, native, GPU-accelerated terminal emulator written by
Mitchell Hashimoto. It's a great host terminal to run `qalcode2` and `gmux` in.

- **GitHub:** https://github.com/ghostty-org/ghostty
- **Website / downloads:** https://ghostty.org
- **Docs:** https://ghostty.org/docs

> Note: gmux is itself a terminal multiplexer, so you don't *need* Ghostty to run
> gmux — but Ghostty is the recommended host terminal for the overall setup, and
> the human asked for it to be installed.

---

## Step 1 — Install (pick ONE)

### Option A — Homebrew (recommended, simplest)
```bash
brew install --cask ghostty
```
This installs `Ghostty.app` into `/Applications`.

### Option B — Official DMG
1. Download the macOS build from https://ghostty.org/download
2. Open the `.dmg`, drag **Ghostty** to `/Applications`.
3. First launch: right-click → **Open** (to clear Gatekeeper) if prompted.

### Option C — Build from source (only if asked)
Ghostty is written in Zig. Building from source requires the Zig toolchain and is
NOT necessary for normal use — prefer A or B. If you must, follow the build docs
at https://github.com/ghostty-org/ghostty (read `BUILD.md` / the README; the Zig
version must match what the repo pins).

✅ **Checkpoint:** `Ghostty.app` is in `/Applications` and launches.

---

## Step 2 — (Optional) basic config

Ghostty reads its config from `~/.config/ghostty/config` (or
`~/Library/Application Support/com.mitchellh.ghostty/config`). A minimal example:

```ini
# ~/.config/ghostty/config
theme = catppuccin-mocha
font-family = "JetBrains Mono"
font-size = 13
background-opacity = 0.96
```

Reload config inside Ghostty with **Cmd+Shift+,** (or restart the app).
Full config reference: https://ghostty.org/docs/config

✅ **Checkpoint:** Ghostty opens, you can run `echo hello` in it.

---

## Step 3 — Use it for the rest of the setup

Once Ghostty is installed, run the **qalcode2** and **gmux** setup steps inside a
Ghostty window:
- qalcode2 install → `../qalcode2/INSTALL_FOR_CLAUDE.md`
- gmux (this whole repo) → `../../MACOS_AGENT_SETUP.md`

That's it — Ghostty is just the host terminal.
