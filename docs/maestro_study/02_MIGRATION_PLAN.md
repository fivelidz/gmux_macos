# Migration plan — gmux-system v3 → v4 (PTY-first)

How to evolve gmux-system to incorporate maestro's PTY-first
architecture while preserving everything we've built (voice, gesture,
phone bridge, monitor.py headless mode, agent monitor flowchart, dashboards).

## Core decision — sibling repo, not in-place rewrite

**Build `gmux-system-v2` as a new repo** (or new branch — see "Repo
strategy" below), not as a refactor of `gmux-system`. Rationale:

1. v3.7.0 is **deployed and working**. Users (you) rely on it daily.
   Tearing it down to ship v4 would mean days of broken tooling.
2. The two architectures coexist cleanly. A `monitor.py` watching tmux on
   a remote VM doesn't conflict with a Tauri-PTY local install.
3. v3 stays as the "headless + remote + phone" specialist. v4 becomes
   the "macOS + Windows + lightning-fast local" specialist. Both can
   eventually share the phone bridge spec (`docs/BRIDGE_DESIGN.md`).
4. Reverting if v4 hits a wall is trivial: just keep using v3.

## Repo strategy

**Option 1 — Sibling repo `gmux-system-v2/`** (recommended)
- Fresh `Cargo.toml`, fresh `package.json`
- Copy in our UI HTML, dashboard, voice daemon, install scripts as a starting point
- Pull maestro patterns directly via `cargo new` shape
- Share docs and design specs across both via symlinks or git submodules
- When v2 reaches feature-parity for daily-driver use, we tag v3 as "final" and switch

**Option 2 — Branch `v4-pty-first/` on gmux-system**
- All work in a long-lived branch
- Easier to share docs and configs
- Harder to keep main green for ongoing v3 fixes
- Merge conflicts get gnarly when both diverge

**Option 3 — Sub-folder `app-v2/` inside gmux-system**
- New Tauri project as a sibling to `app/`
- Shares `backend/`, `docs/`, `scripts/`, `models/`
- Lower repo churn
- Trade-off: package.json/cargo.toml clashes at root if not careful

**Recommendation: Option 3** — keeps everything in one repo, lets us
share the headless backend (monitor.py + phone bridge + voice daemon),
share UI HTML files, share docs. The new `app-v2/` is just an
alternative Tauri shell that hands off to the same `ui/v3/index.html`.

Folder structure:
```
gmux-system/
├── app/             ← existing v3 Tauri app (tmux-backed)
├── app-v2/          ← NEW: PTY-first Tauri app
│   ├── src-tauri/
│   │   ├── src/
│   │   │   ├── core/
│   │   │   │   ├── process_manager.rs   ← lifted from maestro, adapted
│   │   │   │   ├── terminal_backend.rs  ← trait, swappable backends
│   │   │   │   ├── session_manager.rs   ← lifted
│   │   │   │   └── usage_tracker.rs     ← from maestro's usage.rs
│   │   │   ├── commands/
│   │   │   │   ├── terminal.rs          ← spawn_shell/write_stdin/etc.
│   │   │   │   ├── usage.rs             ← get_claude_usage
│   │   │   │   └── ...
│   │   │   └── lib.rs
│   │   └── Cargo.toml
│   ├── src/                ← reuses ui/v3/ files via vite alias
│   └── package.json
├── backend/         ← shared: monitor.py, voice, session_restore
├── ui/v3/           ← shared: HTML, dashboard, gesture, voice — UNCHANGED
├── scripts/
│   ├── launch.sh             ← unchanged, launches v3
│   ├── launch-v2.sh          ← NEW, launches v2
│   └── ...
└── docs/
```

`scripts/gmux` adds a `--v2` flag:
```bash
gmux              # v3 (default, what works today)
gmux --v2         # v2 (PTY-first, in development)
```

Once v2 is solid we flip the default. Until then, v3 stays canonical.

---

## Phased implementation

### Phase 0 — Foundation (1 day)
- [ ] Create `app-v2/` skeleton with `cargo init` and `npm init`
- [ ] Reuse `ui/v3/index.html` via Vite alias — no code duplication
- [ ] Cargo deps: `tauri = "2"`, `portable-pty`, `tokio`, `dashmap`, `keyring`, `reqwest`, `serde`, `directories`
- [ ] Wire up an empty Tauri app that opens our existing index.html
- [ ] `scripts/launch-v2.sh` launches it
- [ ] CI confirmation: still builds on Linux

### Phase 1 — PTY core (2 days)
- [ ] Copy `process_manager.rs` from maestro verbatim, adapt module paths
- [ ] Copy `terminal_backend.rs` trait
- [ ] Copy commands/terminal.rs (`spawn_shell`, `write_stdin`, `resize_pty`, `kill_session`)
- [ ] Add Tauri-managed `ProcessManager::new()` in lib.rs
- [ ] Frontend: add `lib/pty.ts` that mirrors maestro's `lib/terminal.ts` —
      `spawnShell`, `writeStdin`, `resizePty`, `killSession`, `onPtyOutput`
- [ ] Wire one xterm.js Terminal instance to one PTY session for smoke
      test. (We'll integrate with the actual UI gridhol in Phase 4.)

### Phase 2 — Cross-platform port (2 days)
- [ ] Test on macOS — open a session, type, resize, kill. Validate
      shell finds bash/zsh, env vars work, locale is UTF-8.
- [ ] Test on Windows (VM or borrowed machine) — same checks.
      Validate ConPTY DSR handling.
- [ ] Document the platform tests in `docs/maestro_study/03_PLATFORM_TESTS.md`.
- [ ] Add macOS-specific build option to install-vm.sh (already done in v3.7).

### Phase 3 — Usage tracking (1 day)
- [ ] Copy `commands/usage.rs` from maestro verbatim
- [ ] Add `keyring` crate to Cargo.toml (for Windows Credential Manager + Linux Secret Service)
- [ ] Frontend: create `lib/usageStore.ts` (Zustand) with 30s poll
- [ ] Add the daily/weekly toggle widget to our status bar (right side
      of `ui/v3/index.html` toolbar)
- [ ] Wire `usage-update` Tauri event for live updates without poll
      (poll happens in Rust, broadcasts to all windows)

### Phase 4 — Multi-session UI (3 days)
- [ ] Adapt our pane grid to render real xterm.js terminals instead of
      summary cards. Each grid cell mounts a `<TerminalView>`-like
      component listening to its session's PTY events.
- [ ] Keep the current "summary card" view as an opt-in mode for users
      who liked seeing all panes' last lines at a glance.
- [ ] Voice mode keeps working — it inputs to whichever session is
      focused via `writeStdin(sessionId, text + '\r')`.
- [ ] Gesture mode keeps working — it switches focus between sessions,
      not between tmux windows.
- [ ] Approve / reject permission now works by sending characters to the
      PTY (`y\n` / `n\n`) or by calling an MCP hook if we add one later.

### Phase 5 — Bridge integration (1 day)
- [ ] Update `docs/BRIDGE_DESIGN.md` to account for PTY-first sessions
- [ ] The phone bridge talks to a unified session list:
      ```rust
      fn get_all_sessions() -> Vec<Session> {
          let pty_sessions = process_manager.list();
          let tmux_sessions = monitor_py_state_json();  // if monitor.py is running
          merge_dedupe(pty_sessions, tmux_sessions)
      }
      ```
- [ ] Phone can spawn agents via the bridge → bridge calls
      `process_manager.spawn_shell()` directly. No tmux required for phone control.

### Phase 6 — Polish (2 days)
- [ ] Render batching cascade (WebGL → Canvas → DOM)
- [ ] UTF-8 split-byte fix (free with the lifted `Utf8Decoder`)
- [ ] Pasted-image handler
- [ ] Cross-platform keyboard shortcuts (Cmd vs Ctrl, Cmd+Arrow Mac fix)
- [ ] Drag-drop file support

### Phase 7 — Decision point
At this point we have:
- v3 still running daily, untouched
- v2 working on Linux + macOS + Windows
- All UI / voice / gesture features ported
- Usage tracking working
- Phone bridge spec ready to implement against either

Three options:
- **Replace**: declare v2 the default; v3 stays as a tagged release for
  archival. `gmux` command launches v2 by default; `gmux --legacy`
  launches v3.
- **Coexist**: keep both. v2 for desktop power-users; v3 for headless
  servers + remote-via-phone use case. `gmux --v2` and `gmux --legacy`
  both work.
- **Merge**: keep v3's headless mode (monitor.py + browser UI) but make
  the desktop default v2. Single command, smart enough to pick.

Pick at Phase 7 based on how it actually feels.

---

## Detailed file-by-file map

Files we copy with minimal changes:

| Maestro source | Our destination | Changes |
|---|---|---|
| `src-tauri/src/core/process_manager.rs` | `app-v2/src-tauri/src/core/process_manager.rs` | Remove maestro-specific env vars (`MAESTRO_SESSION_ID`, `MAESTRO_PROJECT_HASH`); add our own `GMUX_SESSION_ID` |
| `src-tauri/src/core/terminal_backend.rs` | `app-v2/src-tauri/src/core/terminal_backend.rs` | None needed |
| `src-tauri/src/core/session_manager.rs` | `app-v2/src-tauri/src/core/session_manager.rs` | Add `AiMode::Aider`, `AiMode::QalCode` to enum; rename `AiMode::Plain` to `AiMode::Terminal` |
| `src-tauri/src/commands/terminal.rs` | `app-v2/src-tauri/src/commands/terminal.rs` | Drop `save_pasted_image` if not used; keep everything else |
| `src-tauri/src/commands/usage.rs` | `app-v2/src-tauri/src/commands/usage.rs` | None — works as-is. Optionally add OpenAI / Google equivalents later |
| `src/lib/terminal.ts` | `app-v2/src/lib/pty.ts` | Rename functions to `gmux*`; drop maestro-specific functions |

Files we adapt heavily:

| Maestro source | Our destination | Adaptation needed |
|---|---|---|
| `src/components/terminal/TerminalView.tsx` | inline into `ui/v3/index.html` | Pull the xterm.js setup logic into a `<script>` block that mounts per-pane terminals; reuse our existing pane grid CSS |
| `src/components/tamagotchi/Tamagotchi.tsx` | inline into `ui/v3/index.html` | Become a status-bar widget instead of sidebar; daily/weekly toggle pattern stays |

Files we don't touch:

- `src-tauri/src/commands/git.rs`, `github.rs`, `worktree.rs` — skip
- `src-tauri/src/core/worktree_manager.rs` — skip
- `src-tauri/src/core/marketplace_manager.rs`, `plugin_manager.rs` — skip
- `maestro-mcp-server/` — skip
- `src/components/git/`, `marketplace/`, `quickactions/`, `settings/` — we have our own equivalents

---

## What stays from v3 — preserved unchanged

These are **all keepers** and get reused by v2 via shared paths:

| Thing | Lives in | Used by v2 |
|---|---|---|
| Full UI (gesture, voice, theming, pane grid, modals, dashboard, agent monitor) | `ui/v3/index.html`, `app/src/dashboard/` | Yes, via Vite alias |
| MediaPipe gesture engine + hand_landmarker.task | `models/`, `ui/v3/` JS | Yes — works in any webview |
| Voice daemon (faster-whisper, websockets) | `backend/voice/gmux_voice_daemon.py` | Yes — same daemon serves both apps |
| Session restore (window-name persistence) | `backend/session/session_restore.py` | Optional in v2 (only relevant if user enables tmux backend) |
| monitor.py (headless mode, browser mode, phone source-of-truth) | `backend/status/monitor.py` | Yes — runs alongside v2 when user wants remote/phone access |
| Memory aggregator | `backend/status/memory_aggregator.py` | Yes — reads from disk regardless of which app is running |
| Sub-agent JSON parent-pointer system | `/tmp/gmuxtest-sub-agents.json` + monitor.py | Yes — v2's spawn_sub_agent writes to same file |
| Phone bridge spec | `docs/BRIDGE_DESIGN.md` | Implementation reads from PTY-session list OR tmux state |
| Install scripts | `scripts/install-vm.sh`, `deploy.sh` | Yes, get an extra branch for installing v2 deps (Rust + Node + portable-pty system libs if any) |
| All 211 tests | `backend/status/test_*.py` | Yes |
| Provider auth UI + first-launch wizard | `ui/v3/index.html` | Yes (it talks to opencode `auth.json` directly, no backend coupling) |
| Agent quick-swap, layout cycle, etc. | `ui/v3/index.html` | Yes |

---

## What changes in user experience

| Thing | v3 today | v2 plan |
|---|---|---|
| Where shells live | tmux server | Tauri's own PTY pool |
| Cross-machine view | Yes (via monitor.py + browser) | No (single machine) — or yes if user ALSO runs monitor.py + v3 backend |
| Restart-app survival | Yes (tmux survives) | No (PTYs die with Tauri unless we explicitly persist) |
| `tmux attach -t gmux` works | Yes | No (no tmux) |
| macOS support | No | Yes |
| Windows support | No | Yes |
| Speed of typing | Subjective | Significantly faster (direct PTY, batched render) |
| Output history per pane | Last line in grid, full only in attached tmux | Full xterm.js scrollback per pane in the grid itself |
| Permission approve | Click → API POST | Type `y\n` or click → API POST (either works) |
| First-launch experience | Run launch.sh, expects tmux installed, opencode auth set | Run launch-v2.sh, no tmux needed, opencode CLI is enough |

For the user who does headless + phone + remote: **keep using v3**.
For the user on a Mac who just wants the desktop app: **use v2**.

---

## Cargo deps to add (new in app-v2)

```toml
[dependencies]
tauri = { version = "2", features = ["devtools"] }
tauri-plugin-global-shortcut = "2"
tauri-plugin-shell = "2"
tauri-plugin-opener = "2"
portable-pty = "0.8"
tokio = { version = "1", features = ["full"] }
dashmap = "5"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
keyring = "3"
reqwest = { version = "0.12", default-features = false, features = ["json", "rustls-tls"] }
directories = "5"
thiserror = "1"
log = "0.4"
env_logger = "0.11"
libc = "0.2"
uuid = { version = "1", features = ["v4"] }
```

Everything except `tauri*` and `serde*` is also what maestro uses.

## Cargo features for OS branches

```toml
[features]
default = []
vte-backend = ["dep:vt100"]   # optional terminal VT parser for enhanced state
```

We can ship the simpler xterm-passthrough backend first and add VTE later if needed.

---

## How to start tomorrow

If you want to begin the migration:

```bash
# 1. Create the skeleton
cd ~/projects/gmux-system
mkdir -p app-v2
cd app-v2
npm create tauri-app@latest .   # answer: TypeScript, vanilla, npm
# strip the generated index.html — we'll alias to ../ui/v3/index.html

# 2. Add maestro PTY core
mkdir -p src-tauri/src/core src-tauri/src/commands
cp ../../github_repos/maestro/src-tauri/src/core/process_manager.rs src-tauri/src/core/
cp ../../github_repos/maestro/src-tauri/src/core/terminal_backend.rs src-tauri/src/core/
cp ../../github_repos/maestro/src-tauri/src/core/session_manager.rs src-tauri/src/core/
cp ../../github_repos/maestro/src-tauri/src/commands/terminal.rs src-tauri/src/commands/
cp ../../github_repos/maestro/src-tauri/src/commands/usage.rs src-tauri/src/commands/

# 3. Adapt module paths (sed s/maestro/gmux/g maybe), update Cargo.toml,
#    write a minimal lib.rs that registers the managers and exposes commands

# 4. Build and smoke test
cargo check
npm run tauri dev
```

A morning of work brings the first PTY session up. The rest is grind.

---

## What I'd tag at each phase

| Phase complete | Tag |
|---|---|
| Phase 0 — skeleton runs | `v4.0.0-alpha.0` |
| Phase 1 — PTY core works on Linux | `v4.0.0-alpha.1` |
| Phase 2 — macOS + Windows confirmed | `v4.0.0-beta.0` |
| Phase 3 — usage tracking live | `v4.0.0-beta.1` |
| Phase 4 — multi-session UI integrated | `v4.0.0-beta.2` |
| Phase 5 — phone bridge against v2 | `v4.0.0-rc.0` |
| Phase 6 — polish complete | `v4.0.0` |

Throughout: `v3.7.x` continues to exist, get bug-fix tags as needed,
remains the recommended install for headless/remote use.

---

## Risks and how to mitigate

### Risk 1 — losing the headless / phone story
**Mitigation:** monitor.py + bridge.py keep running regardless of which
Tauri app is in use. The phone connects to the bridge; the bridge reads
from either ProcessManager (Tauri-PTY sessions) or tmux state (legacy).

### Risk 2 — losing tmux power-user features
**Mitigation:** Add an opt-in "tmux backend" mode in v2 that wraps tmux
sessions instead of spawning raw PTYs. The `TerminalBackend` trait
already supports this kind of polymorphism in maestro's design.

### Risk 3 — voice / gesture might break in xterm.js context
**Mitigation:** Voice/gesture works at the JS level today, sending input
to whatever pane has focus. With PTY direct, focus is still just a state
in JS — only the destination of `writeStdin` changes. Low risk.

### Risk 4 — fragmenting development effort
**Mitigation:** Establish a clear rule: bug fixes go in v3; new features
go in v4. As v4 matures, gradually backport critical fixes to v3 only.
Avoid feature-parity treadmill.

### Risk 5 — never finishing v2 because v3 keeps growing
**Mitigation:** Time-box v2 development. Aim Phase 0–3 in one week. If
Phase 4 stalls, freeze and revisit. Worst case we have a powerful local
desktop app at Phase 3 even without full multi-session UI integration.

---

## What this study has taught me about gmux

We have **more architectural surface** than maestro:
- Their app is a single-machine multi-PTY orchestrator with great
  cross-OS support.
- Ours is that PLUS a headless backend, browser frontend, phone bridge,
  voice STT, gesture engine, memory aggregator, agent monitor, sub-agent
  spawning. We've built a lot.

The trade-off has been platform reach. Maestro runs on every OS;
gmux-system runs on Linux. Their PTY core makes cross-OS work feel
trivial — it's all in `portable-pty` + `cfg!()`.

If we adopt their PTY core into a v2 build, we get OS reach for free,
keep everything else, and end up with the strongest tool in this space.
Maestro lacks the headless / browser / voice / gesture story. v3 has it.
v4 inherits it.

This is a really good study. Thanks to your friend for shipping clean
code.
