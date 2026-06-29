# Installing qalcode2 on macOS — Instructions for a Claude Agent

> **You are a Claude coding agent.** Your job is to install **qalcode2** on this
> macOS machine and apply the bundled settings. Read this whole file first, then
> work top-to-bottom. Stop and ask the human at the two ⚠️ points (auth, and any
> destructive step).

---

## What qalcode2 is

`qalcode2` is fivelidz's personal fork of **[opencode](https://github.com/sst/opencode)**
— a terminal-based AI coding agent. It runs on **[Bun](https://bun.sh)** (not Node)
and adds custom agent "modes" (`yolo`, `yolo-opus`, `yolo-extreme`, `build`,
`plan`, `coder`), voice integration, and a safety layer where the agent **never
hard-deletes files** (every `rm` is archived to `~/.qalcode-archive` for manual
deletion instead).

- **Source repo:** https://github.com/fivelidz/qalcode2
- It is launched by a small bash wrapper (`qalcode2`) that calls
  `bun run … src/index.ts` with the chosen agent mode.

---

## Step 1 — Prerequisites

```bash
# Bun (the runtime qalcode2 needs):
curl -fsSL https://bun.sh/install | bash
# restart your shell or: source ~/.zshrc

# git, if not present:
brew install git

# (Optional) codex CLI — only if you want the codex-edit / codex-review agents:
#   the bundled settings reference an OpenAI Codex MCP server.
#   Install per https://github.com/openai/codex and run `codex login`.
#   If you skip this, set "enabled": false on the "codex" block in opencode.jsonc
#   (or just ignore the startup warning).

# (Optional) Ollama — only if you want local models:
#   https://ollama.com  → then `ollama pull qwen2.5-coder:7b`
```

✅ **Checkpoint:** `bun --version` succeeds.

---

## Step 2 — Clone and build qalcode2

```bash
mkdir -p ~/projects
git clone https://github.com/fivelidz/qalcode2 ~/projects/qalcode2
cd ~/projects/qalcode2
bun install        # installs all workspace deps (may take a few minutes)
```

The runnable entrypoint is `~/projects/qalcode2/packages/opencode/src/index.ts`.

✅ **Checkpoint:** `bun install` finishes with no fatal errors.

---

## Step 3 — Install the launcher wrapper

A macOS-portable launcher is bundled next to this file: **`qalcode2`** (in this
same `tooling/qalcode2/` folder).

```bash
mkdir -p ~/.local/bin
cp <gmux_macos>/tooling/qalcode2/qalcode2 ~/.local/bin/qalcode2
chmod +x ~/.local/bin/qalcode2

# Make sure ~/.local/bin is on PATH (zsh):
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

The wrapper expects the source at `~/projects/qalcode2/packages/opencode`. If you
cloned elsewhere, either edit the `QALCODE2_SRC=` line at the top of the wrapper
or export `QALCODE2_SRC` in your shell.

✅ **Checkpoint:** `which qalcode2` resolves to `~/.local/bin/qalcode2`.

---

## Step 4 — Apply the bundled settings

The settings live in `tooling/qalcode2/settings/` in this repo. They go in the
opencode config dir (qalcode2 reuses opencode's config location):

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
- Codex MCP server **enabled** — needs the codex CLI (Step 1). If you don't have
  it, set `"enabled": false` on the `codex` block, or ignore the warning.
- Two `codex-*` delegate agents (only work with the codex MCP server).
- The original machine-specific MCP servers (`diary`, `gmux-brain`,
  `bannerlord-modkit`) and the QTK plugin were **removed/disabled** because they
  pointed at the original author's local paths. Notes in the file explain how to
  re-enable each if you ever set them up.

✅ **Checkpoint:** `~/.config/opencode/opencode.jsonc` exists.

---

## Step 5 — ⚠️ First run + authentication (ask the human)

```bash
cd ~/some-project
qalcode2 --help          # confirm the wrapper works
qalcode2                 # launches the TUI in yolo (Sonnet) mode
```

On first launch qalcode2 needs to authenticate to Anthropic (Claude). **This is
an interactive login — stop and let the human do it.** It typically opens a
browser OAuth flow, or you paste an API key, depending on their account.
See `AUTHENTICATION-SETUP.md` / `CLAUDE-AUTHENTICATION.md` in the qalcode2 repo
for the exact flow.

If auth ever gets stuck: `qalcode2 --clean-auth` then relaunch.

✅ **Checkpoint:** the human confirms the TUI launches and Claude responds.

---

## Notes / gotchas

- **macOS, not Linux:** the original wrapper had a Linux voice daemon path; the
  bundled wrapper leaves voice disabled by default (`VOICE_DAEMON` empty). Voice
  is optional and Linux-developed — skip it unless asked.
- **Safety layer:** this fork archives deletions instead of `rm`-ing them
  (`~/.qalcode-archive`). That's intended behaviour, not a bug.
- **Modes:** `qalcode2 --yolo` (default, autonomous), `--build` (asks before
  changes), `--plan` (read-only). Tab cycles modes inside the TUI.
- For deeper config/build docs, read the qalcode2 repo's own `README.md`,
  `BUILD-AND-DEPLOY.md`, and `TROUBLESHOOTING.md`.
