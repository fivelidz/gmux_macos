# What to lift from gmux-system v3

The v3 repo at `/home/fivelidz/projects/gmux-system/` (tag `v3.7.2`)
contains ~3 years of UI / voice / gesture / monitor work. v4 keeps
nearly all of it, replacing only the tmux substrate with PTY-direct.

This doc is the **inventory**: what we lift verbatim, what we lift
with adaptation, what we leave behind.

---

## Lift verbatim — drop straight in, no changes

These files are copy-and-they-just-work. They have no tmux-specific
assumptions or are written against APIs we keep stable.

| v3 path | v4 destination | Phase |
|---|---|---|
| `ui/v3/index.html` (~8000 lines) | `ui/index.html` | 4a |
| `app/src/dashboard/index.html` | `ui/dashboard/index.html` | 4a |
| `app/src/dashboard/css/dashboard.css` | `ui/dashboard/css/dashboard.css` | 4a |
| `app/src/dashboard/js/*.js` (8 files) | `ui/dashboard/js/` | 4a |
| `models/hand_landmarker.task` | `assets/hand_landmarker.task` | 4f |
| `extras/avatar_system/` (archive) | `extras/avatar_system/` | — |

The dashboard JS files (data.js, agent_rail.js, flow_layout.js,
flow_render.js, detail_panel.js, subagents.js, flow_pulses.js,
util.js, version.js) all work against Tauri events that we'll emit
from the new Rust backend.

---

## Lift with adaptation — copy then modify

These files have v3-specific assumptions (tmux, monitor.py polling,
opencode SSE) that need rewiring for v4's PTY-direct model.

### Backend

| v3 path | v4 destination | What changes |
|---|---|---|
| `backend/status/monitor.py` | `backend/monitor.py` (sidecar, optional) | Keep file-for-file; runs only in headless mode. v4 reads its output if it's running. |
| `backend/voice/gmux_voice_daemon.py` | `backend/voice_daemon.py` (sidecar) | No changes needed; v4 connects to its WS like v3 does |
| `backend/session/session_restore.py` | Drop (PTYs don't persist) | — |
| `backend/status/memory_aggregator.py` | `backend/memory_aggregator.py` | Same — runs as sidecar |
| `backend/status/test_*.py` | `tests/` (port to Rust where possible) | Rewrite as Rust integration tests |

### Scripts

| v3 path | v4 destination | What changes |
|---|---|---|
| `scripts/launch.sh` | `scripts/launch.sh` | Big rewrite — no tmux check, points at Tauri binary |
| `scripts/install-vm.sh` | `scripts/install-vm.sh` | Adapt for v4's deps (Rust + Node instead of Python + tmux) |
| `scripts/deploy.sh` | `scripts/deploy.sh` | Mostly same; rsync the new file layout |
| `scripts/gmux` shell entry | `scripts/gmux` | Adapt subcommands to v4's command names |
| `scripts/macos-smoke-test.sh` | `scripts/macos-smoke-test.sh` | Update checks for v4 binary |

### Rust (v3's `app/src-tauri/src/lib.rs`)

The v3 lib.rs (~1200 LOC) has handlers we adapt:

| v3 Rust function | Adapt to | Why |
|---|---|---|
| `open_agent` | Becomes `spawn_shell` + `write_stdin` chain in JS | PTY-direct doesn't need tmux send-keys |
| `open_project` | Same | — |
| `approve_agent` | `permission_response` (calls opencode API or writes `y\n`) | — |
| `reject_agent` | Same with `n\n` | — |
| `send_to_agent` | Becomes `write_stdin` | — |
| `get_opencode_sessions` | Adapt to read from `SessionManager` | Source of truth changed |
| `check_auth` | Lift as-is | Reads `~/.local/share/opencode/auth.json` — no change |
| `list_providers` | Lift as-is | Reads auth.json + env vars |
| `login_provider` | Adapt: spawn an opencode-auth PTY instead of typing into tmux | — |
| `logout_provider` | Lift as-is | — |
| `list_models` | Lift as-is | Calls `opencode models` |
| `open_dashboard` | Lift as-is | Tauri window show/hide |
| `open_aquarium` | Lift as-is | Same |
| `restart_backend` | Drop | We don't have a separate backend to restart |
| `backend_health` | Adapt to check PTY count instead | — |
| `spawn_sub_agent` | Adapt to use `ProcessManager::spawn_shell` + parent record | — |

### Frontend JS modules

These live inside `ui/v3/index.html` as inline `<script>` blocks
in v3 (no module system). We lift the whole HTML, but the relevant
patterns to know are:

| v3 module / pattern | Phase to address |
|---|---|
| `_loadPersistedState()` / `_saveState()` localStorage | 4a (works as-is) |
| `panes` object + `paneOrder` array | 4b (rebind to PTY sessions) |
| `applyRealState(data)` for state JSON ingestion | 5 (now `usage-update`/`gmux-state` from Rust) |
| `pushToolEvent` / `pushTokenRate` activity tracking | 5 (Rust emits via monitor adapter) |
| Voice mode (Web Speech + voice daemon WS) | 4f (no changes) |
| Gesture engine (MediaPipe) | 4f (no changes) |
| Agent palette (Ctrl+P) | 4e (no changes; pure JS) |
| Layout cycle (L) | 4e (no changes) |
| Views dropdown | 4a (no changes) |
| New-agent modal | 4d (Tauri command name changes) |
| Provider auth modal | 3 (works as-is once `list_providers` is wired) |
| First-launch wizard | 3 (works as-is) |

---

## Lift the docs

Most of v3's docs are still valid. They go into v4's `docs/` either
as-is or as references.

| v3 doc | v4 disposition |
|---|---|
| `docs/AGENT_MONITOR_BACKEND.md` | Reference; the v4 backend changes but the contract is similar |
| `docs/AGENT_MONITOR_FIELDS.md` | Lift verbatim — field list is unchanged |
| `docs/BRIDGE_DESIGN.md` | Lift verbatim — phone protocol unchanged |
| `docs/USAGE_TRACKING.md` | Reference; v4 implements the maestro pattern instead |
| `docs/VM_PROTOCOL.md` | Adapt to v4's deploy flow |
| `docs/SUB_AGENT_SYSTEM.md` | Lift verbatim — same model |
| `docs/MACOS_PORTING.md` | Lift verbatim — same fixes still apply |
| `docs/EFFICIENT_DEPLOY.md` | Adapt to v4 binary distribution |
| `docs/FRESH_VM_TEST_PLAN.md` | Lift verbatim — same test rig |
| `docs/VM_AGENT_COORDINATION.md` | Lift verbatim |
| `docs/PROVIDER_AUTH_PLAN.md` | Status update — many items already shipped in v3.6 |
| `docs/maestro_study/` (3 docs) | Lift verbatim — they're the basis for v4 |
| `docs/INTEGRATION.md` | Rewrite for v4 architecture |
| `docs/NEXT_ACTIONS.md` | Drop — replaced by `TODO.md` |
| `docs/PROMPT_HISTORY.md` | Lift verbatim, append new entries |
| `HANDOVER.md` | Lift to `docs/HANDOVER_v3.md` (historical) |
| `DEPENDENCIES.md` | Rewrite for v4 |
| `INSTALL_GUIDE.md` | Rewrite for v4 |
| `DEPLOYMENT_TARGETS.md` | Lift verbatim, update macOS column to ✅ when Phase 2 lands |
| `RUNNING_FROM_GMUX_ONLY.md` | Drop — replaced by v4 README |
| `VERSION_CONTROL.md` | Lift verbatim — same tagging policy |
| `TESTING_GUIDE.md` | Adapt to v4 |
| `TESTING_CHECKLIST.md` | Adapt to v4 |
| `BACKEND_CONNECTION.md` | Rewrite for v4 |
| `DECISIONS.md` | Lift verbatim, append v4 decisions |
| `LICENSE` | Keep v3's terms; add MIT for v4-original code |

---

## Leave behind

These files are v3-specific or replaced by maestro's patterns. **Do
not lift**:

| v3 file/dir | Why we leave it |
|---|---|
| `app/src-tauri/` entirely | v4 has its own `src-tauri/` from scratch |
| `app/package.json` | v4 has its own |
| `app/src/index.html` (a copy of ui/v3) | We lift the ui/v3 original |
| `app/src/dashboard/serve.sh` | Dev script for v3 dashboard preview; v4 has its own dev flow |
| `app/aquarium.html` (and aquarium related files) | The aquarium was a v3 experimental feature; revisit post-v1.0 |
| `archive/` | Historical snapshots; not relevant to v4 |
| `latest_version_test/` | v3 test launcher; v4 has its own |
| `state-review/` | Historical state-review notes; not for v4 |
| `tools/seed_memory.py` | We re-create if memory tab matters |
| `ui/archive/` | Historical UI snapshots |
| `ui/releases/` | Historical |
| `ui/gesture-engine.js` etc (standalone copies) | The inline versions in `ui/v3/index.html` are canonical |

---

## How to lift safely

When you lift a v3 file:

1. **Always copy, never move.** The v3 repo stays canonical and
   reachable as a reference.
2. **Run `diff` against the source** after any adaptation, so future
   readers can see what was changed and why.
3. **Annotate the top of the file** with a comment:
   ```rust
   // Originally lifted from gmux-system v3.7.2 / app/src-tauri/src/lib.rs
   // Adapted to use ProcessManager instead of tmux send-keys.
   // Changes: removed monitor.py state polling; commands now async.
   ```
4. **If you change non-trivially**, write a one-paragraph note in
   `docs/CHANGELOG.md` (create in Phase 0).

---

## Order of lifting per phase

| Phase | Lift these |
|---|---|
| 0 | Nothing yet — pure scaffold |
| 1 | Nothing from v3 (this is maestro PTY core only) |
| 2 | Nothing |
| 3 | Provider auth code from v3's `lib.rs` |
| 4a | `ui/v3/index.html`, `app/src/dashboard/` |
| 4b–4h | (UI lift drives everything; adapt the Rust handlers from v3's lib.rs as you need them) |
| 5 | `docs/BRIDGE_DESIGN.md` becomes the implementation guide for bridge.rs |
| 6 | Scripts (`launch.sh`, `install-vm.sh`, `deploy.sh`) |

---

## What v3 did better than the new plan

Be honest about it. v3 had some wins worth preserving:

- **Headless mode.** A bare server (no Tauri) can serve the UI over
  HTTP for browser access. v4 doesn't have this; v3 stays available.
- **Cross-machine view.** The phone connects to v3's bridge to see
  panes on a remote machine. v4 is single-machine. Bridge from v4
  to other machines is post-v1.0.
- **Resilience to app crash.** tmux sessions outlive the Tauri app
  in v3. PTY-only in v4 means restarting the app loses everything.
- **Real activity feed across machines.** monitor.py polls every
  active machine; v4's activity feed is local.

For these cases, **users keep using v3.** v4 doesn't replace v3 —
they're sibling products.
