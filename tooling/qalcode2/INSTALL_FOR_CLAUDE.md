# Installing qalcode (QalCode) on macOS — Instructions for a Claude Agent

> **You are a Claude coding agent.** Install **qalcode** (fivelidz's OpenCode
> fork) on this macOS machine, optionally add the **QTK** plugin, and apply the
> bundled settings. Read this whole file first, then work top-to-bottom. Stop and
> ask the human at the ⚠️ points (authentication, anything destructive).

---

## What qalcode is

`qalcode` is fivelidz's public fork of **[OpenCode](https://github.com/sst/opencode)**
— a terminal AI coding agent. It runs **from source via [Bun](https://bun.sh)**
(no global npm install, works on non-AVX CPUs) and adds a full agent roster
(autonomous "yolo" agents, local Ollama agents, planning mode), push-to-talk
voice, a live usage/rate-limit panel, and sensible permission defaults including
a safety layer where the agent **never hard-deletes** — every `rm` is archived
for manual deletion instead.

- **Public repo (use this one):** https://github.com/fivelidz/qalcode-share
- **Optional plugin — QTK (token compressor):** https://github.com/qalarc/QTK
- Upstream it's forked from: https://github.com/sst/opencode

> The repo's own `README.md` documents an Arch/CachyOS `pacman` installer. On
> **macOS** you use the exact same installer with the **`--skip-deps`** flag and
> install Bun yourself first (steps below).

---

## Step 1 — Prerequisites (macOS)

```bash
# Bun — the runtime qalcode needs:
curl -fsSL https://bun.sh/install | bash
# restart shell, or: source ~/.zshrc

# git + ripgrep + fzf (the Linux installer normally pulls these via pacman;
# on macOS install them with brew so --skip-deps has everything it needs):
brew install git ripgrep fzf
```

✅ **Checkpoint:** `bun --version`, `git --version`, `rg --version` all succeed.

---

## Step 2 — Clone and run the installer (with --skip-deps)

```bash
git clone https://github.com/fivelidz/qalcode-share.git ~/qalcode
cd ~/qalcode

# --skip-deps tells the installer NOT to use pacman (it's not on macOS).
# It runs `bun install` and drops a `qalcode` launcher into ~/.local/bin.
bash install.sh --skip-deps
```

Then make sure `~/.local/bin` is on PATH (macOS default shell is zsh):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
which qalcode        # should print ~/.local/bin/qalcode
```

> **Note on the launcher name:** the public installer creates a launcher called
> **`qalcode`** (not `qalcode2`). They are the same tool — `qalcode2` was just
> fivelidz's local alias for a newer checkout. Use `qalcode` on this machine.
> A reference macOS launcher (`qalcode2`) is also bundled in this folder if you
> ever want the multi-mode wrapper, but the installer's `qalcode` is the simplest
> path — prefer it.

✅ **Checkpoint:** `which qalcode` resolves under `~/.local/bin`.

---

## Step 3 — (Optional) install the QTK plugin

QTK silently compresses tool outputs (`git status`, `ls`, `rg`, `pytest`,
`Read`/`Grep`/`Glob`, …) before they reach the model — big token savings, no LLM,
zero workflow change. **Optional.** Skip it on the first pass if you want qalcode
running fast; add it later.

See the companion guide: [`../qtk/INSTALL_FOR_CLAUDE.md`](../qtk/INSTALL_FOR_CLAUDE.md)

If you install QTK, enable it in the settings file (Step 4) by setting the
`"plugin"` array to point at your QTK checkout (the settings file has a commented
example).

---

## Step 4 — Apply the bundled settings

Settings live in `tooling/qalcode2/settings/` in this repo. qalcode reuses
OpenCode's config dir:

```bash
mkdir -p ~/.config/opencode

# Back up anything already there first (do NOT overwrite blindly):
[ -f ~/.config/opencode/opencode.jsonc ] && cp ~/.config/opencode/opencode.jsonc ~/.config/opencode/opencode.jsonc.bak-$(date +%s)
[ -f ~/.config/opencode/config.json ]    && cp ~/.config/opencode/config.json    ~/.config/opencode/config.json.bak-$(date +%s)

cp <gmux_macos>/tooling/qalcode2/settings/opencode.jsonc ~/.config/opencode/opencode.jsonc
cp <gmux_macos>/tooling/qalcode2/settings/config.json    ~/.config/opencode/config.json
```

**About these settings (already sanitised for a fresh machine):**
- `autoupdate: false` — no version check on launch.
- Ollama local-model provider (harmless if Ollama isn't installed).
- Codex MCP server — needs the codex CLI; set `"enabled": false` if you don't
  install it, or ignore the startup warning.
- Two `codex-*` delegate agents (only work with the codex MCP server).
- `"plugin": []` — QTK is **off by default**. To enable it after Step 3, set:
  `"plugin": ["file:///Users/<you>/qtk/packages/qtk-plugin/src/index.ts"]`
  (the file has this example as a comment).
- The author's machine-specific MCP servers (`diary`, `gmux-brain`,
  `bannerlord-modkit`) were removed because they pointed at his local paths.

✅ **Checkpoint:** `~/.config/opencode/opencode.jsonc` exists.

---

## Step 5 — ⚠️ First run + authentication (ask the human)

```bash
cd ~/some-project
qalcode
```

First launch needs Anthropic (Claude) authentication — **interactive login, let
the human do it** (browser OAuth or API key, depending on their account). The
repo's `README.md` / `docs/` cover the exact flow. If auth gets stuck, there's a
`--clean-auth`-style reset documented in the repo.

✅ **Checkpoint:** the human confirms the TUI launches and Claude responds.

---

## Modes / notes

- `qalcode` launches the TUI; **Tab** cycles agent modes (yolo / build / plan / …).
- **Safety layer:** deletions are archived, not `rm`-ed — intended behaviour.
- For deeper docs read the repo's `README.md`, `AGENTS.md`, `docs/`, and
  `STYLE_GUIDE.md`.
