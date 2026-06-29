# What to lift from maestro

The maestro repo at `/home/fivelidz/projects/github_repos/maestro/`
(commit `a10500d`, MIT licensed) is the architectural reference for
v4's PTY core. This doc itemises what we lift, what we adapt, and
how to attribute it.

---

## Licensing & attribution

Maestro is **MIT licensed.** We can freely use its code with proper
attribution. Every file lifted gets a header comment:

```rust
// Originally from https://github.com/its-maestro-baby/maestro
// commit a10500d, MIT licensed by Maestro contributors.
// Adapted for gmux-v4 by fivelidz; changes noted inline.
```

The `LICENSE` file at the v4 repo root reflects this with a
"Third-party Code" section.

---

## Lift verbatim (or near-verbatim)

These files have **zero gmux-specific assumptions** in maestro. They
work for any Tauri PTY app.

### Core PTY infrastructure

| Maestro path | v4 destination | Status |
|---|---|---|
| `src-tauri/src/core/process_manager.rs` | `src-tauri/src/core/process_manager.rs` | Lift; change env var names from `MAESTRO_*` to `GMUX_*` |
| `src-tauri/src/core/terminal_backend.rs` | `src-tauri/src/core/terminal_backend.rs` | Lift; update `use super::PtyError` import |
| `src-tauri/src/core/error.rs` (PtyError) | `src-tauri/src/core/error.rs` | Lift |
| `src-tauri/src/core/utf8_decoder.rs` (or the inline Utf8Decoder) | `src-tauri/src/core/utf8_decoder.rs` | Lift; export `Utf8Decoder` publicly |
| `src-tauri/src/core/session_manager.rs` | `src-tauri/src/core/session_manager.rs` | Lift; extend `AiMode` enum |
| `src-tauri/src/core/windows_process.rs` | `src-tauri/src/core/windows_process.rs` | Lift; ConPTY helpers + `TokioCommandExt` for `hide_console_window` |

### Tauri commands

| Maestro path | v4 destination | Status |
|---|---|---|
| `src-tauri/src/commands/terminal.rs` | `src-tauri/src/commands/terminal.rs` | Lift core 5: spawn_shell, write_stdin, resize_pty, kill_session, kill_all_sessions. **Drop** worktree-aware variants (`get_session_process_tree`, etc.) |
| `src-tauri/src/commands/usage.rs` | `src-tauri/src/commands/usage.rs` | Lift verbatim — the Anthropic OAuth API call is exactly what we need |
| `src-tauri/src/commands/fonts.rs` | (skip; v3 doesn't need custom font detection) | — |

### Frontend infrastructure

| Maestro path | v4 destination | Status |
|---|---|---|
| `src/lib/terminal.ts` | `src/lib/pty.ts` | Lift core 5 wrappers; rename functions to plain `spawnShell`/`writeStdin`/etc. (already are) |
| TS interfaces (`AiMode`, `BackendType`, etc.) | Inline in `src/lib/pty.ts` | Lift |

---

## Lift with adaptation

These files have maestro-specific stuff we strip out:

### `src/components/terminal/TerminalView.tsx` (762 LOC React)

Maestro's xterm.js mount + IPC wiring + render batching. We don't
use React, so this gets **adapted into vanilla JS** inside our
`ui/index.html` (lifted from v3) or as a small helper module.

Key patterns to lift:
- Render batching with `writeBuffer` + `requestAnimationFrame` + 50ms fallback timer
- Backpressure: flush when buffer hits 100 chunks (~400KB)
- WebGL → Canvas → DOM cascade for renderer
- Linux scrollback cap (2000 lines vs 10000 elsewhere)
- Composition event handler for CJK input on WebKit
- WebLinksAddon for clickable URLs
- Unicode11Addon + `term.unicode.activeVersion = "11"`
- Image paste interception (clipboard image → save_pasted_image IPC)
- Drag-drop image (Tauri webview event, not DOM drop)
- Custom keys: Shift+Enter, Cmd+C with selection, Cmd+Arrow on Mac

These patterns become 50-100 lines of vanilla JS that we paste into
the lifted v3 UI in Phase 4b.

### `src/components/tamagotchi/Tamagotchi.tsx` + UsageProgressBar

A React widget showing daily/weekly usage with a toggle button.
**Adapt to a vanilla JS toolbar widget** in our `ui/index.html`.

Key patterns:
- 30s polling on mount
- `showWeekly` boolean state
- Click label → toggle state
- Refresh button
- Tooltip with reset time
- Error state when `needsAuth: true`

### `src-tauri/src/lib.rs` (Tauri builder, managed state, invoke_handler)

We don't lift this file directly because gmux's lib.rs has different
state (no GitHub store, no MarketplaceManager, no WorktreeManager).
We **mimic the structure** — same Tauri builder pattern, same
managed-state registration approach, same plugin registration order.

```rust
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_opener::init())
    .plugin(tauri_plugin_global_shortcut::Builder::new().build())
    .manage(ProcessManager::new())
    .manage(SessionManager::new())
    .manage(UsageCache::default())
    // ... (more state here)
    .invoke_handler(tauri::generate_handler![
      ping,
      // commands::terminal::*
      // commands::usage::*
      // commands::sub_agent::*
    ])
    .setup(|app| {
      // global shortcuts, sidecar spawn, etc.
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
```

---

## Don't lift

| Maestro feature | Why we skip it |
|---|---|
| `commands/git.rs`, `github.rs`, `worktree.rs` | We're not a git visualisation tool |
| `core/worktree_manager.rs` | Worktrees are out of scope for v4 |
| `core/marketplace_manager.rs`, `plugin_manager.rs` | No plugin system in v4 |
| `core/mcp_manager.rs`, `mcp_config_writer.rs` | We use SSE polling instead of MCP callbacks |
| `core/status_server.rs` | Same — our agents send status via SSE |
| `maestro-mcp-server/` (separate crate) | — |
| `commands/marketplace.rs`, `mcp.rs`, `plugin.rs` | — |
| `src/components/git/*` | — |
| `src/components/marketplace/*` | — |
| `src/stores/useGitHubStore.ts` (etc.) | We use vanilla JS, not Zustand |
| `core/font_detector.rs` | We use system defaults |
| `core/transcript_parser.rs`, `transcript_watcher.rs` | Maestro-specific Claude transcript parsing |
| `core/event_bus.rs`, `claude_event.rs` | We use Tauri's own event system |
| `core/cli_path.rs` augmented PATH search | We use a simpler approach |

---

## Order of lifting per phase

| Phase | Lift these |
|---|---|
| 0 | Nothing — we set up the scaffold ourselves |
| 1 | `core/process_manager.rs`, `core/terminal_backend.rs`, `core/session_manager.rs`, `core/error.rs`, `core/utf8_decoder.rs`, `commands/terminal.rs`, `src/lib/terminal.ts` |
| 2 | `core/windows_process.rs` (Windows ConPTY helpers) |
| 3 | `commands/usage.rs`, the Tamagotchi widget pattern |
| 4 | TerminalView.tsx render-batching + WebGL cascade patterns (adapted into v3 UI) |
| 5 | Nothing maestro-specific (bridge is v3-protocol) |
| 6 | Image paste, drag-drop, Cmd+Arrow keys |

---

## Concrete diff workflow for lifting

When you lift a maestro file, follow these steps:

1. **Read the maestro source.**
   ```bash
   cat ~/projects/github_repos/maestro/src-tauri/src/core/process_manager.rs | less
   ```
2. **Copy to v4 destination.**
   ```bash
   cp ~/projects/github_repos/maestro/src-tauri/src/core/process_manager.rs \
      ~/projects/gmux_v4/src-tauri/src/core/process_manager.rs
   ```
3. **Add the attribution header** (see top of this doc).
4. **Apply the documented changes** (e.g. env var rename).
5. **`cargo check`** — verify it compiles. Fix imports/paths as needed.
6. **Update `docs/CHANGELOG.md`** with what you lifted and what you changed.
7. **Commit** with a message like:
   ```
   pty: lift maestro process_manager.rs verbatim
   
   Changes:
   - rename MAESTRO_SESSION_ID → GMUX_SESSION_ID
   - rename MAESTRO_PROJECT_HASH → GMUX_PROJECT_HASH
   - all PTY internals (Utf8Decoder, batching, signal handling) unchanged
   
   Original: maestro commit a10500d, MIT-licensed.
   ```

---

## Open questions about lifting

| Question | Status |
|---|---|
| Use `vt100` crate for VTE backend later? | Decide at Phase 6 — needed if we want enhanced state tracking |
| Lift `core/event_bus.rs` for custom event types? | No — Tauri events are sufficient |
| Lift `core/process_tree.rs` for kill-by-tree? | Phase 2 if Windows needs it; otherwise skip |
| Adopt maestro's session-status enum verbatim? | Mostly — but extend with `rate_limited`, `permission` (we have those in v3, they're needed) |

---

## A note about gratitude

Maestro is exceptionally clean code. The PTY pipeline is textbook,
the cross-platform handling is thorough, the comments explain
**why** not **what**. Lifting from it accelerates v4 by months.

Per its MIT license, we owe attribution and that's it — but the
project owner is a friend of fivelidz, so we'll also reach out
personally to credit them. See `LICENSE` for the attribution
markup and `README.md` for the public credit.
