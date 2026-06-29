# tooling/ — companion tools for the gmux macOS setup

This folder bundles the **other tools fivelidz uses alongside gmux**, with
install instructions written for a **Claude coding agent** to follow on macOS.
All referenced repos are **public**.

Recommended install order:

| # | Tool | What it is | Guide | Public repo |
|---|------|-----------|-------|-------------|
| 1 | **Ghostty** | Fast GPU terminal — the host you run everything in | [`ghostty/`](ghostty/INSTALL_FOR_CLAUDE.md) | github.com/ghostty-org/ghostty |
| 2 | **qalcode** | fivelidz's OpenCode fork (the AI coding agent CLI) + his settings | [`qalcode2/`](qalcode2/INSTALL_FOR_CLAUDE.md) | github.com/fivelidz/qalcode-share |
| 3 | **QTK** *(optional)* | OpenCode plugin that compresses tool output to save tokens | [`qtk/`](qtk/INSTALL_FOR_CLAUDE.md) | github.com/qalarc/QTK |
| 4 | **gmux** | The terminal multiplexer / agent operations centre (this whole repo) | [`../MACOS_AGENT_SETUP.md`](../MACOS_AGENT_SETUP.md) | this repo |

---

## Agent: do this

1. **Install Ghostty** → [`ghostty/INSTALL_FOR_CLAUDE.md`](ghostty/INSTALL_FOR_CLAUDE.md)
   (one `brew install --cask ghostty`). Run the rest inside a Ghostty window.
2. **Install qalcode + apply settings** → [`qalcode2/INSTALL_FOR_CLAUDE.md`](qalcode2/INSTALL_FOR_CLAUDE.md).
   Uses the public `qalcode-share` installer with `--skip-deps` for macOS. The
   settings in `qalcode2/settings/` are a *sanitised, portable* copy of
   fivelidz's config (machine-specific MCP servers removed, with notes).
3. **(Optional) Install QTK plugin** → [`qtk/INSTALL_FOR_CLAUDE.md`](qtk/INSTALL_FOR_CLAUDE.md)
   (`bun add @qalarc/qtk-plugin`, then flip the `plugin` line in the config).
4. **Get gmux running** → [`../MACOS_AGENT_SETUP.md`](../MACOS_AGENT_SETUP.md)
   (the main task for this repo).

Each guide has ✅ checkpoints and ⚠️ "stop and ask the human" points
(authentication, anything destructive). Honour them.

---

## Public links

- Ghostty: https://github.com/ghostty-org/ghostty
- qalcode (public): https://github.com/fivelidz/qalcode-share
- QTK plugin (public): https://github.com/qalarc/QTK  ·  npm `@qalarc/qtk-plugin`
- OpenCode (upstream qalcode is forked from): https://github.com/sst/opencode
- gmux: this repository (macOS porting fork of `fivelidz/gmux-v4`)

---

## What's in here

```
tooling/
├── README.md                       ← you are here
├── ghostty/
│   └── INSTALL_FOR_CLAUDE.md       ← install Ghostty (brew cask / DMG)
├── qalcode2/
│   ├── INSTALL_FOR_CLAUDE.md       ← clone qalcode-share, install.sh --skip-deps, apply settings
│   ├── qalcode2                    ← reference macOS launcher wrapper (optional)
│   └── settings/
│       ├── opencode.jsonc          ← sanitised global config (→ ~/.config/opencode/)
│       └── config.json             ← provider config (Ollama local models)
└── qtk/
    └── INSTALL_FOR_CLAUDE.md       ← optional token-compression plugin (@qalarc/qtk-plugin)
```
