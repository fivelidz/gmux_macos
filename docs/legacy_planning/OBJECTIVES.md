# Objectives

What gmux-v4 is for, what it is not, and how we know we're done.

---

## North star

**gmux-v4 is the all-in-one successor to gmux-system v3.** One repo,
one binary, one daily-driver app for running, watching, and controlling
multiple AI coding agents with minimal backend friction.

When v4.0.0 ships:
- v3 is **archived as legacy**, not "sibling product"
- v4 owns: desktop + headless + browser + phone control
- Backend is **stateful, in-process, and minimal-fuss** — no tmux,
  no `/tmp/*.json` JSON shuffling, no opencode-SSE polling shell games,
  no race-conditions between separate processes
- All agent state (status, todos, activity, history, sub-agents,
  permissions, usage) lives in **one Rust state store** with a single
  source of truth, broadcasting events to whoever is listening
  (local UI, dashboard window, phone)

---

## What "minimal-fuss agent handling" means

The core complaint about v3 backend: too many independent moving parts
syncing through `/tmp` files. v4 collapses this into one Rust process
that owns:

```
┌────────────────────────────────────────────────────────────────┐
│                   gmux-v4 process (Tauri app)                  │
│                                                                │
│  Core state (one DashMap per concept):                          │
│   - sessions:   DashMap<u32, Session>          ← PTY + metadata │
│   - agents:     DashMap<u32, AgentState>       ← per-pane state │
│   - todos:      DashMap<u32, Vec<Todo>>        ← per-pane todos │
│   - activity:   VecDeque<ActivityEvent> (500)  ← rolling log    │
│   - usage:      ProviderUsage cache            ← Anthropic etc. │
│   - files:      DashMap<PathBuf, FileTouches>  ← edit heatmap   │
│   - subagents:  DashMap<u32, ParentLink>       ← parent/child   │
│   - perms:      DashMap<u32, PendingPerm>      ← pending approvals│
│                                                                │
│  Event bus:                                                    │
│   - one tokio broadcast channel per stream                     │
│   - main window + dashboard + phone bridge all subscribe       │
│   - changes to state → events → all subscribers in < 1ms       │
│                                                                │
│  Persistence (optional, opt-in):                               │
│   - SQLite at ~/.local/share/gmux/state.db                     │
│   - autosave todos, activity, sessions across app restarts     │
│   - lazy load — UI never blocked                               │
│                                                                │
│  External integrations:                                        │
│   - PTY: portable-pty (Unix/Windows)                           │
│   - Anthropic usage API: reqwest + 30s cache                   │
│   - Phone bridge: tokio WS server on :8767 (same process)      │
│   - Voice: optional Python sidecar (lifted from v3 unchanged)  │
└────────────────────────────────────────────────────────────────┘
```

No more:
- monitor.py + Rust + Python juggling files in `/tmp`
- Race conditions between two monitor.py instances
- "Did we read the latest activity.json or a stale one?"
- "Why is the Tauri app showing different state than the dashboard?"

Everything lives in one process. Events are zero-latency. The dashboard
window is just another Tauri window — same state.

---

## What carries over from v3 (must work day-one)

The entire v3 UI/UX gets lifted to v4. Specifically:

- All gestures (MediaPipe hand tracking)
- All voice (Web Speech + faster-whisper sidecar)
- Pane grid with layout cycling (`L` key)
- Agent quick-swap palette (`Ctrl+P`)
- Favorites with `Ctrl+Shift+F`
- Direct jumps (`Ctrl+1..9`)
- Per-session last-dir memory
- New-agent modal with provider + model + yolo flags
- Provider auth panel (Connect Claude, OpenAI, etc.)
- First-launch auth wizard
- Sub-agent spawning (right-click → spawn child)
- Agent Monitor (Ctrl+Alt+D) — flowchart + activity feed + detail panel
- Memory aggregator + Memory panel
- Folder click-to-drill-in with breadcrumb
- Full-path display
- Rate-limit detection + countdown badge
- Markdown chat fullscreen view
- Theme switching (dark/light + accent colour)

If you used it in v3.7.2, it works in v4.0.0.

---

## What's new in v4 (above v3)

### N1 — Cross-platform from day one
Builds and runs natively on Linux, macOS, and Windows. No tmux
dependency. Single Rust binary plus webview.

### N2 — Sub-50ms input latency
Maestro's 16ms tokio batching pattern + WebGL xterm.js rendering.
Input keystroke → PTY: <50ms p95. PTY byte → screen: <50ms p95.

### N3 — Claude usage display (the real one)
Polls `https://api.anthropic.com/api/oauth/usage` every 30s. Shows
daily (5-hour window), weekly (7-day), and weekly Opus quotas as a
toolbar badge with click-to-toggle.

### N4 — Per-agent todo tracking, first-class
Every agent has a `todos: Vec<Todo>` in state. Updated by:
- The agent itself via opencode's `/todo` endpoint (if available)
- The user clicking checkboxes in the UI
- Sub-agent spawn → inherits parent's relevant todos
- Persisted to SQLite so they survive app restart

Surfaced in:
- A panel beside each pane in grid view
- The Agent Monitor's per-agent detail panel
- The phone app

### N5 — Activity markers / event log
Every PTY operation, every tool call, every permission request,
every file edit is captured as an `ActivityEvent` with timestamp.
Rolling 500-event buffer plus optional persistence. Used by:
- Agent Monitor flowchart (edges between agent → file)
- Per-agent activity tab in detail panel
- Rate-limit detection (regex on recent terminal output)
- Phone status updates

### N6 — UTF-8 correctness everywhere
Emoji, CJK, nerd-font icons never garbled. Inherits maestro's
`Utf8Decoder` with split-byte handling across 4 KB chunks.

### N7 — One install command
`curl … | bash` or download `.dmg` / `.msi` / `.AppImage`. No
"first install Python, then bun, then tmux, then npm, then…"
sequence. Tauri binary bundles everything except the optional
voice sidecar.

### N8 — Phone bridge built-in
WS server on `:8767` runs in the same Tauri process. No separate
`bridge.py` needed. Implements v3's frozen contract so the existing
gmux-phone APK works unchanged.

### N9 — Headless mode without sacrificing v3 features
`gmux-v4 --headless` runs without opening a Tauri window. Exposes
HTTP API at `:8769` + browser UI at `:5550`. Phone connects the
same way it does in v3.

---

## Out of scope for v4.0.0

| What | Why |
|---|---|
| Git worktree integration (maestro's killer feature) | Big surface; defer to v4.1 |
| Plugin marketplace | Not core to gmux's identity |
| GitHub PR / Issue views | Out of scope; users have a browser |
| Auto-update | Add post-v4.0.0 |
| iOS native app | gmux-phone v0.7's job |
| Cloud relay for phone | LAN + Tailscale ships; relay is v4.1 |
| MCP server bundling | We use opencode's SSE + our own activity log |

---

## Success criteria for v4.0.0

### Functional
- [ ] Spawn an agent in any folder; agent boots
- [ ] Approve a permission with one click
- [ ] Send text to an agent via voice
- [ ] Switch focus between agents via `Ctrl+1..9`
- [ ] Quick-swap palette opens with `Ctrl+P`
- [ ] Layout cycles with `L`, button label updates
- [ ] Agent Monitor opens (`Ctrl+Alt+D`) and shows live activity
- [ ] Sub-agent panel spawns under parent
- [ ] Provider auth: connect Claude via Settings → Providers
- [ ] Claude daily/weekly usage badge updates every 30s
- [ ] Rate-limit detected → status badge appears
- [ ] **Todos per agent visible in grid and dashboard, persist across app restart**
- [ ] **Activity log records every tool call, persists, queryable from UI**
- [ ] Memory tab in dashboard shows aggregated memories
- [ ] Phone (gmux-phone PWA) pairs via QR; sees sessions; sends text
- [ ] **Headless mode (`--headless`) starts without a window**

### Platform
- [ ] Builds + runs on Linux x86_64 (CachyOS / Debian 12 / Ubuntu 24)
- [ ] Builds + runs on macOS Apple Silicon (14+) and Intel
- [ ] Builds + runs on Windows 11
- [ ] All Tauri global shortcuts work on each platform

### Quality
- [ ] Idle CPU < 5%
- [ ] No RAM growth over 1 hour of normal use
- [ ] Input latency: keystroke to PTY <50ms p95 (measured)
- [ ] Output latency: PTY byte to render <50ms p95 (measured)
- [ ] Unit tests cover: PTY manager, session manager, usage parser,
      todo store, activity log, sub-agent registry
- [ ] No memory leaks after 100 spawn/kill cycles
- [ ] UTF-8 multi-byte never garbled

### State management
- [ ] **All state lives in DashMaps inside the Tauri process**
- [ ] **Persistence to SQLite is autosave-on-change**
- [ ] **Restarting the app restores: sessions list, todos, recent activity**
- [ ] **Event bus has one channel per stream; no polling**

### Distribution
- [ ] Code-signed `.dmg` for macOS (universal binary)
- [ ] Signed `.msi` for Windows
- [ ] `.AppImage` + `.deb` + `.pkg.tar.zst` for Linux
- [ ] One-shot install script per platform
- [ ] Artifacts < 200 MB each

### Docs
- [ ] Every doc in `docs/` is current
- [ ] Inline code comments on every non-trivial function
- [ ] Architecture diagram in README is accurate
- [ ] At least one "from-zero" install writeup

---

## Migration from v3

When v4.0.0 ships:

1. v3 repo gets a final tag `v3.7.2-final-archive`
2. v3 README banner: "🏁 This project is archived. Use [gmux-v4](https://github.com/fivelidz/gmux-v4)."
3. v4 ships an import helper: `gmux import-v3` reads
   `~/.local/share/opencode/auth.json` and any v3 session state from
   `/tmp/gmuxtest-*.json` and seeds v4's SQLite store with it.
4. The v3 `gmux` shell command is replaced by v4's binary.
5. Users on the headless / remote / phone-only flow are NOT left
   behind — v4 supports the same WS protocol on `:8767` and the
   same browser UI on `:5550` via the built-in headless mode.

There is no scenario where a v3 user can't get equivalent or better
behaviour in v4.

---

## What the user sees on day one (v4.0.0)

A developer downloads `gmux-v4.dmg` on their MacBook, drags to
Applications, opens it. Window appears with one terminal showing
their shell prompt. They press `N`, type `~/projects/my-app`, choose
Claude. Second pane appears, already in their project, with `claude`
running. The first pane is still there.

They press `Ctrl+P`, type "my-app", hit Enter — focus jumps. They
say "go check the auth file" — voice STT writes that into the
terminal. Claude reads the file, status dot goes yellow. The Agent
Monitor (which they opened with `Ctrl+Alt+D`) shows a green edge:
`my-app-claude → auth.py`. Claude generates 3 todos:

> ☐ Read auth.py
> ☐ Refactor login_user()
> ☐ Add unit tests

All three appear in the pane's todo panel **and** in the Agent
Monitor. As Claude completes them, the checkboxes tick automatically.

They press `L` to cycle layout to 2×2. They close their laptop. Open
it again hours later. The app is still there, the panes are still
there, todos still ticked, activity log still showing recent edits.

Their friend opens gmux-phone on the train, scans the QR shown by
`gmux pair`, controls the same agents from the phone over Tailscale.
The phone sees the same todos.

That's v4.0.0.
