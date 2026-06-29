# Contributing

This guide is for any contributor — human or AI agent — picking up
work on gmux-v4.

---

## Before you start

1. **Read** in order: `README.md` → `docs/OBJECTIVES.md` →
   `docs/ARCHITECTURE.md` → `docs/PHASES.md` → `docs/TODO.md` →
   `docs/AGENT_HANDOFF.md` (always read last — it's the latest state).
2. **Reference repos** (read-only on this machine):
   - `/home/fivelidz/projects/gmux-system/` — v3 (UI, voice, docs)
   - `/home/fivelidz/projects/github_repos/maestro/` — PTY core
   - `/home/fivelidz/projects/gmux-phone/` — phone client spec
3. **Test environment:** Linux x86_64 / CachyOS is the daily-driver.
   macOS and Windows tests come in Phase 2.

---

## Workflow

### Picking up a task

1. Open `docs/TODO.md`
2. Find an unchecked `[ ]` task in the current phase (see
   `docs/AGENT_HANDOFF.md` for which phase is active)
3. Change to `[~] @your-handle YYYY-MM-DD` so others know it's claimed
4. Do the work
5. Change to `[x]` with a 1-line note about what you did
6. Update `docs/AGENT_HANDOFF.md` with your session summary

### Branching

- **Default branch:** `main`
- **Phase work:** create `phase-N/short-description` branches if PR'ing
- **Trivial fixes:** push direct to `main` if the test suite passes
- We use **rebase merges** to keep history flat; no merge commits

### Commits

Format:
```
<scope>: <short imperative>

<body, optional, explaining WHY>
```

Examples:
- `pty: lift maestro process_manager.rs verbatim`
- `usage: implement get_claude_usage with 30s cache`
- `ui: integrate pane grid with xterm.js per session`
- `docs: clarify Phase 4d acceptance criteria`
- `bridge: implement WS auth handshake`

Bullet lists in the body are fine for multi-point changes.

### Tagging

Every phase completion gets a tag (see `docs/PHASES.md`). Format:
`v0.X.0-<phase-name>` for pre-1.0, `vX.Y.Z` for stable.

### Tests

- **Rust:** `cargo test` (unit + integration tests under `src-tauri/src/`)
- **JS:** none for now; the UI is mostly DOM-mutating glue lifted from v3
- **End-to-end:** manual; document in the relevant test report under
  `docs/test-reports/` if you want it tracked

Every PR or direct push **must** keep `cargo test` and `cargo check`
green. No exceptions.

---

## Working with AI agents

This project assumes the bulk of work will be done by AI agents
(Claude / OpenCode / Codex / etc.) supervised by a human.

### Best practices when delegating

**Do:**
- Reference specific files in the reference repos with **absolute paths**
- Cite a specific section of a doc (e.g. "see PHASES.md § Phase 4b")
- Specify "no new pip deps" / "no new crates" if you want to constrain scope
- Run tests yourself after the agent claims completion
- Tag a known-good state before letting an agent loose

**Don't:**
- Let an agent decide architecture from scratch — point at this docs folder
- Skip running `cargo check` / `cargo test` after a Rust change
- Merge an agent's changes without reading the diff
- Leave the agent in autonomous mode for >1 hour without checking in

### Multi-agent coordination

If multiple agents are working in parallel:

- **One agent per phase** at any time (e.g. one on Phase 3, one on Phase 4)
- **Phase 4 is the exception:** subdivisions (4a-4h) can be parallel
- Use the `[~] @handle date` marker in TODO.md to avoid double-work
- Sub-agents working under a parent agent: parent owns the coordination

---

## Code style

### Rust

- 2-space indent (matches portable-pty's style)
- `rustfmt` default settings on save
- `clippy` clean: zero warnings allowed
- No `unwrap()` on non-test paths — use `?` or `match`
- Error types: define in `core/error.rs`, use `thiserror`
- Async: `tokio` runtime; blocking work in `spawn_blocking`

### TypeScript

- 2-space indent
- `prettier` defaults
- No-strict mode is fine for now (the UI lift is JS-heavy)
- Avoid pulling in React / Solid / Svelte — keep the DOM imperative
- ESM imports; `type:"module"` in `package.json`

### Naming

- Tauri commands: `snake_case` Rust → exposed to JS as `snake_case`
- IPC event names: `kebab-case` (e.g. `pty-output-7`, `usage-update`)
- Files: `snake_case.rs` for Rust, `kebab-case.ts` for TS, `index.html`
  for HTML entries
- Branch names: `kebab-case`

---

## Cross-platform

Always test (or note "untested on") for the target platform:

| Platform | Status checklist |
|---|---|
| Linux x86_64 | Primary; everything must work here |
| macOS Apple Silicon | Phase 2+; uses `cfg!(target_os = "macos")` branches |
| macOS Intel | Same as ASi; usually trivial |
| Windows 11 | Phase 2+; uses `cfg!(windows)` branches |

When in doubt, write a `cfg!` branch rather than committing platform-specific code.

---

## Doc updates

If your change affects:
- A feature or architecture → update `docs/ARCHITECTURE.md`
- A phase scope or acceptance → update `docs/PHASES.md`
- A specific task → check it off in `docs/TODO.md`
- The current state of the repo → **always** update `docs/AGENT_HANDOFF.md`

Docs are first-class. A working feature with stale docs is half-shipped.

---

## Reporting issues

For now, this is a private repo; issues go in `docs/issues/`
as plain markdown files: `docs/issues/2026-05-17-pty-resize-glitch.md`

Once public (post-v1.0.0), we move to GitHub Issues.

---

## Licence

By contributing, you agree your work is licensed under MIT (see
`LICENSE`). If you lifted code from a different-licensed source,
note the attribution inline and in `LICENSE`.

---

## Communication

- Use commit messages and PR bodies as the primary record
- Use `docs/AGENT_HANDOFF.md` for handoffs between sessions / agents
- Use inline `// NOTE:` and `// TODO:` comments in source for in-flight reasoning
- Don't rely on chat history — it doesn't survive context windows
