# tooling/ — companion tools for the gmux macOS setup

This folder bundles the **other tools fivelidz uses alongside gmux**, with
install instructions written for a **Claude coding agent** to follow on macOS.

There are three pieces. Recommended install order:

| # | Tool | What it is | Folder |
|---|------|-----------|--------|
| 1 | **Ghostty** | Fast GPU terminal — the host you run everything in | [`ghostty/`](ghostty/INSTALL_FOR_CLAUDE.md) |
| 2 | **qalcode2** | fivelidz's opencode fork (the AI coding agent CLI) + his settings | [`qalcode2/`](qalcode2/INSTALL_FOR_CLAUDE.md) |
| 3 | **gmux** | The terminal multiplexer / agent operations centre (this whole repo) | [`../MACOS_AGENT_SETUP.md`](../MACOS_AGENT_SETUP.md) |

---

## Agent: do this

1. **Install Ghostty** → follow [`ghostty/INSTALL_FOR_CLAUDE.md`](ghostty/INSTALL_FOR_CLAUDE.md).
   (One `brew install --cask ghostty`.) Run the rest inside a Ghostty window.
2. **Install qalcode2 + apply settings** → follow
   [`qalcode2/INSTALL_FOR_CLAUDE.md`](qalcode2/INSTALL_FOR_CLAUDE.md).
   The settings in `qalcode2/settings/` are a *sanitised, portable* copy of
   fivelidz's config — machine-specific MCP servers/plugins are disabled with
   notes on how to re-enable them.
3. **Get gmux running** → follow [`../MACOS_AGENT_SETUP.md`](../MACOS_AGENT_SETUP.md)
   (the main task for this repo).

Each guide has ✅ checkpoints and ⚠️ "stop and ask the human" points
(authentication, anything destructive). Honour them.

---

## Quick links

- Ghostty: https://github.com/ghostty-org/ghostty
- qalcode2 (source): https://github.com/fivelidz/qalcode2
- opencode (upstream qalcode2 is forked from): https://github.com/sst/opencode
- gmux: this repository (macOS porting fork of `fivelidz/gmux-v4`)

---

## What's in here

```
tooling/
├── README.md                       ← you are here
├── ghostty/
│   └── INSTALL_FOR_CLAUDE.md       ← install Ghostty (brew cask / DMG)
└── qalcode2/
    ├── INSTALL_FOR_CLAUDE.md       ← clone, build (bun), install wrapper, apply settings
    ├── qalcode2                    ← macOS-portable launcher (→ ~/.local/bin/qalcode2)
    └── settings/
        ├── opencode.jsonc          ← sanitised global config (→ ~/.config/opencode/)
        └── config.json             ← provider config (Ollama local models)
```
