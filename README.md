# gmux_macos

> **🍎 This is the macOS porting fork of gmux (v4.0.0-alpha.22).**
> The code is ~95% mac-ready (developed on Linux, never run on Mac hardware).
> **If you are a coding agent tasked with getting this working on macOS, start
> here → [`MACOS_AGENT_SETUP.md`](MACOS_AGENT_SETUP.md).**
> Full patch list and rationale: [`docs/MACOS_PORTING.md`](docs/MACOS_PORTING.md).
> **Is this a real app or a demo?** → [`docs/TAURI_APP_STATUS.md`](docs/TAURI_APP_STATUS.md)
> (it's the real app — that note explains the build steps so it doesn't *look* like a demo).
>
> **Optional companion tools** (Ghostty, qalcode2, QTK) live in
> [`tooling/`](tooling/README.md). They are **NOT required** to build or run the
> gmux app — gmux is standalone with its own Python backend. Install them only if
> asked.

---

**gmux IS the terminal multiplexer.** No tmux underneath. Cross-platform
Tauri 2 desktop app that owns the PTYs directly, with the full v3 UI,
voice, gesture, agent monitor, sub-agents, todos, phone bridge, and
provider auth on top.

This repo is the **direct continuation** of
[gmux-system](https://github.com/fivelidz/gmux-system) (v3.7.2) with
the tmux substrate replaced by direct PTY ownership in Rust (lifted
from [maestro](https://github.com/its-maestro-baby/maestro)). Every
v3 feature continues to work; cross-platform support and sub-50ms
input latency are added.

---

## ✨ alpha.22 — the agent operations centre

> **Most tools run one agent. gmux runs a _fleet_ in one cockpit — and adds
> the layer nobody else has: fleet coordination.**

The v4 PTY engine now drives a full multi-agent orchestration layer. See
`docs/ALPHA22_FEATURES_AND_MARKETING.md` for the marketing write-up and
`docs/ALPHA22_SUMMARY_AND_TESTING.md` for the manual test checklist.

### Frictionless creation
- **Press `N`** → the chat panel becomes the creation surface. Agent / model /
  permission / folder are **preselected** from your last-used defaults. Type a
  prompt, hit **Enter** — that's the whole flow. No "Create" button.
- **`Shift+N`** opens the full dialog (presets, parent, naming) for power users.
- Permission mode (safe / yolo / yolo-extreme) is wired end-to-end into the
  agent launch, and **sub-agents inherit their parent's permission mode**.

### Looping / supervisor agents ♻️
- Tick **"Looping / supervisor agent"** at creation → a distinct dashed-teal
  pane with a `♻️ super` badge.
- When a worker stalls, the supervisor either **re-prompts it to continue** or
  **POSTs a notify webhook** (→ phone / Slack / your API). Loop caps + cooldowns.

### Smart concurrency governor ⚖️
- Watches fleet-wide rate-limit hits and runs an **AIMD budget** (TCP-style):
  halve concurrency on a 429, +1 per clean 60s.
- **Staggers (re)starts and nudges** with jitter so loops don't all fire at
  once and re-trip the per-minute limit.
- A **green / amber / red lamp** in the topbar: _"safe to add an agent?"_
- Design brief: `docs/RATE_LIMIT_DETECTION_DESIGN.md`.

### Scheduled sessions & task timers ⏰
- Launch an agent at a set time — e.g. **warm up the 5-hour Claude window
  before you sit down.** Optional prompt; once / daily / weekdays.

### Audible attention alerts 🚂
- Synthesised alert (no sound files) when an agent needs you — finished,
  awaiting permission, errored, or rate-limited. Toggle + picker; **default
  train whistle**, plus chime / ding / bell / beep with a Test button.

### Embedded HTTP API for apps & agents 🔌
gmux now exposes a small HTTP API on **`http://127.0.0.1:6310`** (starts with the
app) so **other apps and agents can query gmux and control its agents** — seeing
the live v4 PTY agents directly, no tmux required. Full reference:
`docs/GMUX_API.md`.
- **Read** (open on localhost): `GET /api/health`, `/api/state`, `/api/agents`,
  `/api/agent/:id`, `/api/usage`.
- **Control** (Bearer token): `POST /api/agent/spawn`, `/api/agent/:id/send`,
  `/api/agent/:id/key`, `/api/agent/:id/kill`.
- **Auth** reuses the same token store as phone pairing
  (`~/.config/gmux/auth_tokens.json`).
```bash
curl http://127.0.0.1:6310/api/agents          # list live agents + state
curl http://127.0.0.1:6310/api/usage           # Claude 5h/7d/sonnet usage
curl -X POST http://127.0.0.1:6310/api/agent/spawn \
  -H "Authorization: Bearer $TOK" \
  -d '{"directory":"~/projects/x","prompt":"audit the codebase"}'
```

### Usage / auth fix (alpha.22)
- Fixed Claude OAuth auto-refresh: Anthropic moved the token endpoint from
  `console.anthropic.com` → `platform.claude.com`. The old URL 404'd, silently
  breaking refresh so the 5-hour / Sonnet usage bars went blank and the UI kept
  asking for `claude /login` despite valid credentials on disk. Now refreshes
  correctly and the usage bars populate again.

---

## Status

**v4.0.0-alpha.22 — PTY engine live, orchestration layer shipped.**

The PTY substrate swap is done: gmux owns one portable-pty per agent (no tmux),
agents launch by writing the CLI command into the PTY, and a full multi-agent
orchestration layer (above) runs on top.

| Stream | Status |
|---|---|
| v4 PTY engine (portable-pty, no tmux) | ✅ Live (`open_agent_v4`, `spawn_sub_agent_v4`) |
| Per-pane xterm.js terminal | ✅ Wired (`pty-output-{id}` events) |
| Frictionless composer creation (`N`) | ✅ alpha.22 |
| Permission modes + sub-agent inheritance | ✅ alpha.22 |
| Looping / supervisor agents | ✅ alpha.22 |
| Smart concurrency governor (rate-limit AIMD) | ✅ alpha.22 |
| Scheduled sessions & task timers | ✅ alpha.22 |
| Audible attention alerts | ✅ alpha.22 |
| Claude OAuth usage + auto-refresh | ✅ Fixed alpha.22 (endpoint migration) |
| Embedded HTTP API (`:6310`) for apps/agents | ✅ alpha.22 (`docs/GMUX_API.md`) |
| Voice daemon | ✅ Present (sidecar) |
| Gesture engine | ✅ Present |
| Agent Monitor dashboard | ✅ Present |
| Memory aggregator | ✅ Present |
| Session restore | ✅ Present |
| Provider auth UI | ✅ Present |
| Phone bridge | 🔧 In progress (`gmux_phone_bridge_system/`) |
| `gmux-ptyd` (terminals survive app restart) | 🔧 Designed (`docs/GMUX_PTYD_DESIGN.md`), unbuilt |
| Cross-platform (macOS/Windows) | 🔧 Falls out of portable-pty; Linux is primary |

---

## How v4 differs from v3

```
v3                                v4
─────                             ─────
one PTY → tmux client             one PTY per agent (Rust-owned)
prefix+c, prefix+, gymnastics     direct portable-pty spawn
monitor.py polls tmux every 2s    Rust emits PTY events live
summary cards in pane grid        real xterm.js in pane grid
Linux only (tmux dependency)      Linux + macOS + Windows
2-5s state-update latency         <50ms event-driven latency
```

Everything else is the same as v3.7.2. You'll recognise the UI, the
hotkeys, the voice/gesture, the dashboard, the agent flowchart, the
provider auth flow.

---

## Reading order

If you're picking this up cold:

1. **`docs/V4_PTY_SWAP.md`** — the actual implementation plan for the
   substrate swap (the only thing that changed from v3)
2. **`README.md`** — this file
3. **`HANDOVER.md`** — full v3 system documentation (unchanged)
4. **`docs/maestro_study/`** — the architectural reference for the
   PTY model we're adopting (3 docs from the v3 repo)
5. **`docs/legacy_planning/`** — earlier v4 planning docs; superseded
   by the current narrow-scope plan but kept for reference
6. **`docs/AGENT_LIFECYCLE.md`** (in `docs/legacy_planning/`) — still
   a useful spec for how agent state, todos, and activity persist;
   the parts that aren't covered by the v3 backend get added in
   later v4 phases

---

## What stays from gmux-system v3

The repo root looks identical to v3 because we copied it verbatim:
- `app/` — Tauri shell + Vite + xterm.js dependencies
- `ui/v3/index.html` — the full 8000-line UI (gesture, voice, palette, etc.)
- `app/src/dashboard/` — Agent Monitor flowchart
- `backend/status/monitor.py` — gets adapted to read PTY state from
  Rust (instead of polling tmux), but kept as the optional headless mode
- `backend/voice/gmux_voice_daemon.py` — unchanged sidecar
- `models/hand_landmarker.task` — MediaPipe gesture model
- `scripts/` — install + launch scripts (get adapted to drop tmux from
  hard deps, keep it as optional sidecar for v3-compat headless mode)
- All v3 tests (`backend/status/test_*.py`) continue to pass

---

## What changes from gmux-system v3

The PTY substrate. Specifically:

- `app/src-tauri/src/lib.rs` — replace `start_pty()` (which spawns one
  PTY into `tmux new-session -A`) with calls to a new `ProcessManager`
  that spawns one PTY per agent directly
- All the v3 commands that wrote `prefix+c` etc. into the tmux client
  (`open_agent`, `open_project`, `spawn_sub_agent`, `login_provider`)
  get rewired to call `ProcessManager.spawn_shell()` instead
- `ui/v3/index.html` pane grid: each pane mounts its own `xterm.js`
  Terminal bound to that pane's PTY, replacing the summary-card
  rendering
- `monitor.py` keeps running but its tmux-polling code path becomes
  dormant; instead it subscribes to Rust PTY events

The PTY infrastructure (`ProcessManager`, `Utf8Decoder`, `TerminalBackend`
trait) is lifted from maestro under its MIT license, with attribution
in `LICENSE` and inline comments.

---

## Why this approach

Three reasons:

1. **The v3 UI and features are mature.** Eight months of polish (voice,
   gesture, agent monitor, sub-agents, palette, layout cycle, provider
   auth, dashboard, memory aggregator, fish-name fix, session restore).
   Rewriting it would be foolish.

2. **tmux is the only Linux-only piece.** Everything else in v3 already
   works on macOS and Windows in principle — we're held back by one
   layer. Replace it, get full cross-platform.

3. **The change is well-bounded.** ~600 lines of new Rust (lifted from
   maestro), ~50 lines of new JS in the pane grid (mount xterm.js per
   pane), the rest is rewiring existing handlers.

---

## Repo / branch / tag policy

- **One repo**, `gmux-v4`. v3 (`gmux-system`) gets archived once v4
  reaches feature parity + cross-platform tested.
- **`main` branch.** Long-lived feature branches discouraged.
- **Tags:** `v4.0.0-alpha.N` for in-progress, `v4.0.0` for ship.
- **No rewriting history on `main`.**

---

## License

MIT — see [`LICENSE`](LICENSE). v3 code carried over retains AGPL-3.0
OR proprietary dual licensing as in the v3 repo (see `LICENSE-AGPL`).
PTY infrastructure lifted from maestro is MIT-attributed inline and
in `LICENSE`.

---

## Pointers

- Reference repos (read-only on this machine):
  - `~/projects/gmux-system/` — v3.7.2 (will be archived once v4 ships)
  - `~/projects/github_repos/maestro/` — PTY architecture reference
  - `~/projects/gmux-phone/` — frozen Android client (v0.6.1)
