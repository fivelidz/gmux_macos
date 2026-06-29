# tooling/ — companion tools for the gmux macOS setup

This folder bundles **optional companion tools** fivelidz uses alongside gmux,
with install instructions for a **Claude coding agent** on macOS. All referenced
repos are **public**.

> ## ⚠️ Read this first — these are NOT dependencies of gmux
>
> **The gmux Tauri app is standalone.** It does NOT need Ghostty, qalcode2, or
> QTK to build or run. gmux ships its own Python backend (`backend/`) and its own
> Tauri/Rust app — that's all it needs.
>
> - **If your only goal is to get the gmux app working → ignore this whole
>   folder and go straight to [`../MACOS_AGENT_SETUP.md`](../MACOS_AGENT_SETUP.md).**
> - The tools below are just nice extras fivelidz runs in his own workflow:
>   - **Ghostty** — a terminal emulator (any terminal works; gmux doesn't require it)
>   - **qalcode2** — a separate AI coding-agent CLI (unrelated to the gmux app)
>   - **QTK** — a plugin for qalcode2 (not for gmux)
>
> Install them only if fivelidz specifically asked for them. They can be set up
> before, after, or completely independently of gmux.

---

## The two are independent

| | What it is | Needs the others? | Guide |
|---|---|---|---|
| **gmux app** | The terminal multiplexer / agent ops centre (this repo) | **No** — standalone | [`../MACOS_AGENT_SETUP.md`](../MACOS_AGENT_SETUP.md) |
| Ghostty | Fast GPU terminal emulator | No | [`ghostty/`](ghostty/INSTALL_FOR_CLAUDE.md) |
| qalcode2 | fivelidz's OpenCode fork (AI coding CLI) + his settings | No | [`qalcode2/`](qalcode2/INSTALL_FOR_CLAUDE.md) |
| QTK *(optional)* | Token-compression plugin **for qalcode2** | qalcode2 only | [`qtk/`](qtk/INSTALL_FOR_CLAUDE.md) |

Public repos: gmux (this repo) · Ghostty `github.com/ghostty-org/ghostty` ·
qalcode `github.com/fivelidz/qalcode-share` · QTK `github.com/qalarc/QTK`.

---

## Agent: do this

**Primary task — the gmux app (no companion tools required):**
→ [`../MACOS_AGENT_SETUP.md`](../MACOS_AGENT_SETUP.md)

**Only if fivelidz asked for the companion tools** (order doesn't matter; they're
independent of gmux):
- **Ghostty** → [`ghostty/INSTALL_FOR_CLAUDE.md`](ghostty/INSTALL_FOR_CLAUDE.md)
  (one `brew install --cask ghostty`).
- **qalcode2 + settings** → [`qalcode2/INSTALL_FOR_CLAUDE.md`](qalcode2/INSTALL_FOR_CLAUDE.md)
  (public `qalcode-share` installer with `--skip-deps`).
- **QTK plugin for qalcode2** *(optional)* → [`qtk/INSTALL_FOR_CLAUDE.md`](qtk/INSTALL_FOR_CLAUDE.md).

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
