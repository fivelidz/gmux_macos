# Maestro deep-dive — findings

Source: https://github.com/its-maestro-baby/maestro
Local clone: `/home/fivelidz/projects/github_repos/maestro/` (depth 1)
Commit studied: `a10500d` (May 2026)

## TL;DR

Maestro is a **Tauri 2 + xterm.js + portable-pty** terminal multiplexer.
**No tmux, no monitor.py, no opencode HTTP polling** — every terminal is a
direct PTY owned by Rust, with raw bytes streamed over Tauri events to
xterm.js. Cross-platform Linux/macOS/Windows out of the box.

This is **fundamentally a different architecture** from gmux-system:

| Concept | gmux-system | maestro |
|---|---|---|
| Terminal substrate | tmux + Rust PTY to tmux client | Rust spawns PTY directly per session |
| State capture | Parse opencode SSE + tmux panes | Each PTY is its own session; no state polling |
| Cross-machine | monitor.py HTTP API on `:8769` | None — single-machine app |
| Multi-window | tmux windows in one session | DashMap of independent PTYs |
| Session model | tmux session = project, tmux window = agent | Maestro session = one PTY with metadata |
| OS support | Linux only (Tauri + tmux deps) | Linux + macOS + Windows |
| Backend coupling | Tight to opencode/tmux | Decoupled — agent is just `claude` / `gemini` / `codex` CLI invoked in a normal shell |

The Rust PTY core is so clean and self-contained that we can lift it
wholesale into gmux-system to get instant macOS + Windows support, **without
giving up our voice/gesture/UI work**.

---

## Critical files studied

### Rust backend
| File | LOC | Purpose |
|---|---|---|
| `src-tauri/src/core/process_manager.rs` | 686 | PTY spawn / read / write / resize / kill — the heart |
| `src-tauri/src/core/terminal_backend.rs` | 181 | Trait abstraction for swappable PTY/VTE backends |
| `src-tauri/src/core/session_manager.rs` | 187 | DashMap of session metadata (mode, status, branch) |
| `src-tauri/src/commands/terminal.rs` | 333 | Tauri command handlers for terminal operations |
| `src-tauri/src/commands/usage.rs` | 340 | **Claude usage API** — calls `api.anthropic.com/api/oauth/usage` |
| `src-tauri/src/commands/session.rs` | 176 | Session create / assign branch / status |

### Frontend
| File | LOC | Purpose |
|---|---|---|
| `src/lib/terminal.ts` | 307 | Thin wrappers around Tauri invoke + listen for PTY ops |
| `src/components/terminal/TerminalView.tsx` | 762 | xterm.js mount + PTY event subscription + render batching |
| `src/components/tamagotchi/Tamagotchi.tsx` | 130 | Usage widget with daily/weekly toggle |
| `src/stores/useUsageStore.ts` | — | Zustand store, polls `get_claude_usage` every 30s |

---

## The PTY pipeline — what makes it fast and correct

`process_manager.rs::spawn_shell()` does these things every time a session opens:

1. **`portable_pty::native_pty_system().openpty(80x24)`** — cross-platform PTY pair (Unix: pty/tty; Windows: ConPTY).
2. **CommandBuilder** — finds shell:
   - Unix: `$SHELL` or `/bin/sh`, with `-l` for login
   - Windows: `%COMSPEC%` or `cmd.exe`
3. **Sets correct env**:
   - `TERM=xterm-256color` (Unix only — ConPTY handles emulation itself on Windows)
   - `LANG=en_US.UTF-8` if not set (fixes Tauri-from-Finder/Dock missing locale)
   - `MAESTRO_SESSION_ID=<id>` so spawned child processes (incl. MCP server) know their parent
   - Strips `CLAUDECODE` env var if present (prevents nested-session confusion)
4. **`portable_pty` calls `setsid()` on Unix** so the child is a session leader; PGID==PID; allows killing the whole process group.
5. **`master.process_group_leader()`** captures PGID directly rather than assuming.
6. **Dedicated OS thread** named `pty-reader-<id>` reads from the master PTY in 4096-byte chunks. Critical because PTY reads are blocking syscalls — running them inside tokio would freeze the runtime.
7. **`Utf8Decoder` (stateful)** — handles split multi-byte sequences. Emoji and CJK characters that get cut in half by 4 KB chunk boundaries are buffered and prepended to the next chunk. No more garbled output.
8. **mpsc channel (256-slot)** funnels chunks from the reader thread into a tokio task. ~1 MB of buffered chunks before backpressure kicks in.
9. **Tokio task batches writes**:
   - Accumulates into a `String` buffer
   - Flushes every **16 ms** (60 fps alignment) OR when the buffer exceeds **64 KB**
   - Emits as Tauri event `pty-output-{id}` carrying the batched string
10. **Windows DSR handling** — if it sees `ESC [ 6 n` (cursor-position request), responds with `ESC [ 1 ; 1 R` directly on the PTY to keep some Windows tools from hanging.

### Why this is so much better than what most projects do
Most Tauri-terminal projects emit one event per PTY read, which means
~500 events per second during a `cargo build`. That kills the frontend.
Maestro's 16ms batching reduces this to **60 events per second max**, with
each event carrying potentially dozens of KB of output. Same data, way less
IPC overhead.

### Shutdown
- `kill_session()` removes from DashMap atomically (concurrent calls return `NotFound`)
- Unix: `kill(-pgid, SIGTERM)`, wait 3s, escalate to `kill(-pgid, SIGKILL)`
- Windows: `taskkill /PID <pid> /T /F`
- Drops writer + master → reader thread hits EOF and exits
- Notify `shutdown` → tokio emitter task drains buffer and exits
- `tokio::task::spawn_blocking` to `.join()` the reader thread without blocking the async runtime

---

## Frontend xterm.js wiring — what's clever

### Render batching on the JS side too
The frontend ALSO batches:
- Incoming PTY chunks pushed into `writeBuffer: string[]`
- `requestAnimationFrame` schedules a flush
- Fallback: `setTimeout(flushBuffer, 50ms)` for backgrounded tabs (rAF stops firing)
- Backpressure: if buffer hits 100 chunks (~400KB), flush immediately

### WebGL renderer with cascade fallback
1. Try `@xterm/addon-webgl` (GPU rendering)
2. On context loss → `@xterm/addon-canvas`
3. If even Canvas fails → DOM (slow but always works)

### Linux-specific tweak
`scrollback: isLinux ? 2000 : 10000` — WebKitGTK's DOM renderer is so slow
that 10k scrollback lines cause severe lag. Cap it.

### Multi-byte input fix (Tauri / WKWebView bug)
xterm.js's `CompositionHelper` has a known bug on WebKit where the hidden
textarea accumulates text across CJK compositions. They capture
`compositionend` data and use it to override what xterm.js sends via
`onData`. This is the "测试 vs 这是" bug — easy to miss, hard to debug.

### Image paste + drag-drop
- Clipboard paste: intercept paste event, detect image MIME, save to temp
  file via `save_pasted_image` IPC, write the path into the terminal.
- Drag-drop: Tauri intercepts at webview level so `drop` events never fire
  in JS. Use `getCurrentWebviewWindow().onDragDropEvent()` instead.

### Custom keys (cross-platform)
- Shift+Enter → sends `ESC [ 1 3 ; 2 u` (Kitty keyboard protocol) for
  newline-in-buffer instead of submit
- Cmd/Ctrl+C with selection → copy to clipboard, don't send SIGINT
- Cmd+ArrowLeft/Right → send `^A` / `^E` (Mac webview swallows these)

---

## Usage tracking — the critical reverse-engineered API

### The undocumented Anthropic endpoint
```
GET https://api.anthropic.com/api/oauth/usage
  Authorization: Bearer <access_token>
  anthropic-beta: oauth-2025-04-20
  User-Agent: claude-code/2.0.32

Response:
{
  "five_hour":      { "utilization": 0.34, "resets_at": "2026-05-16T14:00:00Z" },
  "seven_day":      { "utilization": 0.12, "resets_at": "2026-05-23T00:00:00Z" },
  "seven_day_opus": { "utilization": 0.41, "resets_at": "2026-05-23T00:00:00Z" }
}
```

`utilization` is either `0..1` (multiply by 100) or `0..100`. They handle
both. This is exactly what claude.ai/settings/usage shows.

### Where the OAuth token lives
- **macOS:** Keychain → `security find-generic-password -s "Claude Code-credentials" -a <user> -w` → returns JSON `{ claudeAiOauth: { accessToken, expiresAt } }`
- **Windows:** Credential Manager via `keyring` crate
- **Linux:** Secret Service (D-Bus) via `keyring` crate
- **Fallback (all OSes):** `~/.claude/.credentials.json` file in same format

### Critical implementation details
- **Cache the result for 30 seconds.** Multiple components calling on mount otherwise hammer the API.
- **On 429**, cache the failure for the `Retry-After` duration so we don't keep getting rate-limited by the rate-limit checker itself.
- **Static `CREDENTIAL_STORE_FAILED` flag** — first failure to talk to keychain disables it for the rest of the process lifetime, so we don't spam permission prompts on every poll.
- **Token expiry check with 60-second buffer** — if `expires_at - now < 60s`, treat as expired so we don't fail mid-request.

### The UI pattern (Tamagotchi widget)
```jsx
const [showWeekly, setShowWeekly] = useState(false);
const currentPercent = showWeekly ? weeklyPercent : sessionPercent;
const currentLabel   = showWeekly ? "Weekly" : "Daily";

<button onClick={() => setShowWeekly(!showWeekly)}>
  <Dot color={currentColor} />
  {currentLabel}: {Math.round(currentPercent)}%
</button>
```

One button toggles between the two views. Progress bar fills based on
`currentPercent`. Refresh button next to it manually re-polls. Tooltip
shows the reset time.

---

## Other architectural notes

### State management
Frontend uses **Zustand** stores per concern:
- `useSessionStore` — list of sessions, current focus, status
- `useUsageStore` — claude usage data, polling timer
- `useTerminalSettingsStore` — font, line height, zoom
- `useGitStore`, `useGitHubStore` — git operations + GitHub auth

Backend uses **Tauri managed state** — `Arc<>`-cloneable structs registered
once in `lib.rs::run()`.

### Worktrees (architecturally interesting but not relevant to us yet)
Maestro's killer feature is **per-session git worktrees** — each agent
gets its own isolated checkout of the same repo on a different branch.
The `worktree_manager.rs` and `git.rs` modules handle this. We can skip
copying this for now; it's a separate concern.

### MCP server
Maestro runs its own MCP server at `maestro-mcp-server/` that Claude
sessions can use to report status back to the app. Not needed for our
gmux integration but interesting pattern.

### Status server pattern
The app embeds an HTTP server (`status_server.rs`) so spawned CLI
processes can phone home with status updates. Sessions identify
themselves via `MAESTRO_SESSION_ID` env var. We do something similar
with monitor.py's :8769 — but ours is per-machine, theirs is per-app.

---

## What we should and shouldn't copy

### ✅ Copy wholesale
- `process_manager.rs` — the PTY core. Bring this in as `backend/pty_manager.rs` (or pull into Rust if we keep the python backend separate; but I think we move it into the Tauri Rust layer)
- `Utf8Decoder` — solves a real correctness issue
- The 16ms batching pattern (Rust side) + rAF batching (JS side)
- `usage.rs` — exactly what we need for the rate-limit display. Word-for-word.
- The Tamagotchi widget UI pattern (daily/weekly toggle) — fits our existing rate-limit work perfectly
- Cross-platform port detection / OS branches (we already started this in v3.7)

### ✅ Adapt
- `terminal_backend.rs` trait — gives us a clean place for the gmux-specific behaviour (tmux passthrough mode, multi-session aggregation)
- `session_manager.rs` — useful pattern for tracking session lifecycle. Our current state lives in `/tmp/gmuxtest-pane-state.json` from monitor.py polling tmux; we should keep that for compatibility but add a DashMap-backed registry for Tauri-spawned sessions.
- WebGL/Canvas/DOM cascade for xterm.js — we already use xterm in `app/src/` but not with this cascade. Add it.

### ❌ Don't copy
- The whole worktree system — separate concern, big surface area
- The MCP server pattern — we already have monitor.py serving similar role
- The git visualization — separate feature
- Their session-status state machine — ours is more permissive on purpose

### 🤔 Maybe later
- Status server (their HTTP-status-callback pattern) — could replace our `/tmp/*.json` polling if we wanted purer event-driven, but the JSON files are also useful for external tools (phone bridge, sub-agents). Skip for now.
- Pasted-image handler — nice UX but optional

---

## What gmux gains by adopting their PTY core

1. **macOS support** — `portable-pty` works on macOS natively. No more "Tauri opens but PTY won't attach to tmux" issue.
2. **Windows support** — ConPTY just works. The `cfg!(target_os)` we already set up handles the differences.
3. **Faster rendering** — 16ms batching + WebGL + UTF-8 fix means smoother UI even during heavy output.
4. **Independent PTYs** — each agent is its own PTY, not a tmux pane. This means killing one agent doesn't take down others; no risk of tmux server crash propagating.
5. **No tmux dependency at all** — installation simplifies significantly. (We could keep tmux as an OPTION for users who want it, but default to direct PTY.)

## What gmux LOSES if we go all-PTY

1. **Cross-machine view** — monitor.py's `/api/state` on :8769 exposes all panes to remote clients (the phone). If we drop tmux, we'd need to write our own session-list endpoint.
2. **Attach to existing tmux** — power users like to `tmux attach -t gmux` from their own terminal. Without tmux, that's gone.
3. **Persistence across app restart** — tmux sessions outlive the gmux app. PTY-only would lose sessions when Tauri quits.

## The middle path (most attractive)

Run BOTH:
- **Direct PTY** as the default for new agents (gives us macOS/Windows + speed)
- **tmux backend** as an option for users who want persistence (Linux only)
- A `TerminalBackend` trait (exactly the one maestro defined) lets us pick at session creation time
- monitor.py keeps doing its tmux-watching job AND learns to read the Tauri-spawned PTY session list
- The phone bridge talks to a unified session list that merges both

This is what `docs/maestro_study/02_MIGRATION_PLAN.md` will lay out.
