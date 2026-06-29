# Prompt History

Running log of user prompts per session. Newest at top. Manual append-only —
agents must add entries here at the end of each working session.

Format:
```
## YYYY-MM-DD HH:MM — short topic
- prompt 1
- prompt 2
- outcome / files touched
```

---

## 2026-05-13 02:00 — Agent Monitor button missing, dropdown declutter, backend wiring

**User prompts in order:**

1. "continue the tests."
2. "I can't see the agent monitor built before /home/fivelidz/projects/Knowledge_systems/gmux_memory_integration that displays it, in a similar vein to the aquarium designs. Where did those buttons go? they should be next to gesture and open those new windows. look at the claude logs from the gmuxtest UI creation folder."
3. "we don't want 'aquarium'. I just want the agent monitor for now. We are on a much much newer version of the tauri system now but for some reason this has not remained linked properly. keep investigating the backend and go about passing it to the VM for better install"
4. "there should also be a note of previous prompts..."
5. "do not change things outside of your own folder"
6. "I don't see the agent monitor button? where is it? it is not next to the gesture buttons"
7. "nevermind agent monitor has been found. These buttons perhaps need a drop down, graph as well so they are not so cluttered. These are mostly unfinished elements as of now. knowing and seeing how agent monitor is meant to work, can you make sure the backend is properly linked up to it. see what is needed for it."

**Outcomes:**

- Copied `dashboard/` from Knowledge_systems into `app/src/dashboard/`
- Registered `dashboard` window in `app/src-tauri/tauri.conf.json`
- Added `"dashboard"` to `app/src-tauri/capabilities/default.json` windows list
- Added 🧠 Agent Monitor toolbar button → consolidated under 👁 Views ▾ dropdown
  alongside 🗂 Folder Graph and 🧠 Memory Panel (to declutter unfinished features)
- Updated `scripts/launch.sh` auto-sync to also mirror `ui/v3/dashboard/` if present
- Wrote `docs/AGENT_MONITOR_BACKEND.md` — full backend wiring status, what's
  connected, what's missing (activity/files/memory producers in monitor.py)
- Confirmed Rust state-poll thread already broadcasts `gmux-state`,
  `memory-update`, `activity-tick`, `files-update` to all 3 windows — the
  dashboard listens correctly. Only the producers are incomplete.

**Files touched (all inside /home/fivelidz/projects/gmux-system/):**

- `app/src/dashboard/` (new, copy of Knowledge_systems source)
- `app/src/index.html` (mirror of ui/v3/index.html)
- `app/src-tauri/tauri.conf.json` (dashboard window)
- `app/src-tauri/capabilities/default.json` (allow dashboard)
- `ui/v3/index.html` (Views dropdown + CSS + JS handlers)
- `scripts/launch.sh` (dashboard auto-sync block)
- `docs/PROMPT_HISTORY.md` (this file)
- `docs/AGENT_MONITOR_BACKEND.md` (new)

**Commit: 42f2c1a** v3.5: Agent Monitor wired + Views dropdown + backend wiring doc

---

## 2026-05-13 02:30 — Live activity feed + dep audit + VM prep

**User prompts:**

8. "great save this version. Can we configure things so that this agent monitor without using dummy data fully conveys what the agents are doing? like what folders they are accessing and what they are actually doing? Continue the system. Continue the process of testing installation on the other virtual machine environment which has issues with running ghostty. Have we ensured that we have contained all of our dependencies within this project well?"

**Outcomes:**

- Extended `backend/status/monitor.py` to produce the two missing data streams
  the Agent Monitor needs:
  - `/tmp/gmuxtest-activity.json` — tool_start/tool_end events with file_path,
    duration_ms, result. Captured from opencode's SSE `message.part.updated`.
  - `/tmp/gmuxtest-files.json` — derived per-file touch counters
    (touches_5m / touches_30m / touches_1h), unique agents list, is_hot,
    is_conflict, last_writer.
  - New helpers: `_record_activity_start`, `_record_activity_end`,
    `_extract_file_path`, `_abs_path`, `write_activity`, `write_files`.
  - Module-level: `_activity` deque (cap 500), `_pane_to_name`,
    `_pane_to_cwd`, `_tool_starts`.
  - Hooked into the tmux poll loop so files are rewritten every cycle.
  - Unit-tested locally — events get written, file map populates with
    correct touch counts.

- Dependency audit (read-only):
  - `DEPENDENCIES.md` already comprehensive, including install steps for
    CachyOS / Debian, optional vs mandatory, and skip-paths for headless.
  - Only one hardcoded `/home/fivelidz` path in source: dashboard's mock
    file-path builder in `data.js` line 191 — used only when serving the
    dashboard in plain-browser mock mode. Irrelevant on VM (live data flows).
  - Cargo.lock + package-lock.json both committed — reproducible builds.
  - Tauri sidecar resolver checks `gmux-system` → `gmuxtest` → `gmux` paths,
    works on a VM where only `gmux-system` exists.

- Updated `docs/VM_PROTOCOL.md`:
  - Added v3.5 producer-file checks to the test checklist.
  - Added dedicated section explaining how to verify the Agent Monitor
    pipeline on a VM (producers vs the dashboard window itself).

**Files touched:**

- `backend/status/monitor.py` (activity + files producers)
- `docs/VM_PROTOCOL.md` (v3.5 verification section)
- `docs/PROMPT_HISTORY.md` (this entry)

**Commit: 4860c5e** v3.5: live activity + files producers in monitor.py + VM checks

---

## 2026-05-13 03:00 — Agent launch wiring + qalcode2 audit + macOS plan + sub-agent

**User prompts:**

9. "One thing I think lost is when creating agents it should be specified
   what folder they will be in on launch. We need to also at some point
   test the session creation and agent creation system. The tauri app
   essentially also needs all of the options of qalcode2. Connect provider
   with the OAuth is probably necessary and that is basically just passed
   onto the backend. The AI in the VM is also working on getting this to
   work. Make a note of all things and continue. I want you to establish
   good version control as well. Have we made an assessment on deploying
   to things like macOS?"
10. "make a sub agent which will handle the agent display monitor backend
    connections for what it wants to display then continue with other tasks"

**Outcomes:**

- **Working-directory wiring** for agent creation:
  - Updated `createAgent()` in `ui/v3/index.html` to actually invoke the
    Rust `open_agent` Tauri command instead of just mock-inserting a pane.
  - Expands `~` to `$HOME` via `get_home_dir` Tauri command.
  - Empty directory defaults to `$HOME` with a clear toast.
  - Modal label changed from "(optional)" to "(where the agent starts —
    defaults to $HOME)".
  - Browser fallback still mocks (no tmux access).

- **TESTING_CHECKLIST.md v3.5 sections added:**
  - Agent + Session creation tests (modal, live launch, empty-dir default,
    browser fallback, session creation)
  - Agent Monitor (dashboard) end-to-end checklist (producer files,
    dashboard window, live tool activity)
  - Provider auth checklist (current state + v3.6 plan)

- **docs/PROVIDER_AUTH_PLAN.md (new)** — comprehensive plan for v3.6:
  - Audits qalcode2 auth subcommands (login/list/logout/models)
  - Proposes 4 new Tauri commands: list_providers, login_provider,
    logout_provider, list_models
  - Settings → Providers panel mockup
  - First-launch wizard for unauthed users
  - Agent-creation interlock
  - Per-provider OAuth flow details (Anthropic / OpenAI / Google / Ollama)

- **docs/VM_AGENT_COORDINATION.md (new)** — protocol for the VM-side AI:
  - Host is canonical for code; VM is a deploy target
  - VM-AI writes to `docs/VM_REPORTS/<date>.md` outbox
  - `vmai-*` process-name convention
  - Allowed/forbidden file-touch zones on the VM
  - `/tmp/vmai-busy.txt` sentinel for "I'm working" coordination
  - Conflict resolution rules

- **DEPLOYMENT_TARGETS.md macOS section (extensive)** — full assessment:
  - Theoretical compatibility table (which components work as-is)
  - 6 specific code-level fixes identified before macOS will work
  - 3-phase rollout plan (browser → Tauri → full feature)
  - Bottom line: ~95% compatible, no fundamental blocker, ~1 focused day
    of work needed once a Mac is available.

- **VERSION_CONTROL.md v3.5+ section** — established tagging strategy:
  - `vMAJOR.MINOR.PATCH` convention with bump rules
  - Pre-tag checklist (test passes, archive snapshot, PROMPT_HISTORY entry)
  - Rollback procedure
  - Snapshot policy (every "save this" → tag + archive HTML)
  - Two-machine sync rules (no git on VM)

- **Sub-agent dispatched** to deeply wire Agent Monitor backend:
  - Read flow_render.js / agent_rail.js / detail_panel.js / subagents.js
    to catalogue every field the renderers use.
  - Created `docs/AGENT_MONITOR_FIELDS.md` — comprehensive field audit.
  - Closed gaps in `monitor.py`: `session_age_s` alias, `sub_agents[]`
    list, `last_tool_call_summary`, `args.command` + `args.pattern`
    extraction, improved `rel_path` resolution.
  - Created `backend/status/test_monitor_producers.py` — 78 assertions, all pass.
  - Updated `docs/AGENT_MONITOR_BACKEND.md` to reflect v3.6 state.

**Files touched:**

- `ui/v3/index.html` + `app/src/index.html` (createAgent wired to Tauri)
- `TESTING_CHECKLIST.md` (v3.5 sections appended)
- `docs/PROVIDER_AUTH_PLAN.md` (new)
- `docs/VM_AGENT_COORDINATION.md` (new)
- `docs/VM_REPORTS/.gitkeep` (new outbox dir)
- `DEPLOYMENT_TARGETS.md` (macOS section)
- `VERSION_CONTROL.md` (tagging/snapshot policy)
- `backend/status/monitor.py` (sub-agent additions)
- `backend/status/test_monitor_producers.py` (new, sub-agent)
- `docs/AGENT_MONITOR_FIELDS.md` (new, sub-agent)
- `docs/AGENT_MONITOR_BACKEND.md` (sub-agent update)
- `docs/PROMPT_HISTORY.md` (this entry)

**Commit: d7b9679** | **Tag: v3.5.0**

---

## 2026-05-13 06:55 — Per-session last-dir memory (v3.5.1)

**User prompt:**

11. "agent launch should work off folder last agent was opened in for
    that session tab as the default suggestion"

**Outcome:**

Added per-session-tab memory for the new-agent "Working directory" field.
When you open "New Agent" the field is pre-filled with the last directory
used in the currently-active session tab.

- `_getLastDirForSession(sessionName)` + `_rememberDirForSession(name, dir)`
  helpers in `ui/v3/index.html`.
- Storage: `localStorage.gmux_last_dir_by_session` (flat dict
  `{sessionName: absPath}`) plus `gmux_last_dir` global fallback.
- 'all' pseudo-session uses the global last-dir; createAgent attributes
  the new directory to the first real session.
- Pre-filled value gets a subtle visual tint (.nam-suggested) that
  fades on focus/input so the user knows it was auto-suggested but
  not still being "claimed" as suggested after they edit it.
- Modal label updated: "(remembers last folder used in this session)"

**Files:**
- `ui/v3/index.html` + `app/src/index.html` (synced)
- `archive/ui/index.v3.5.1-per-session-dir-memory.20260513-0654.html`
- `docs/PROMPT_HISTORY.md` (this entry)

**Commit: 86f647f** | **Tag: v3.5.1**

---

## 2026-05-13 07:00 — Self-launch test, fish-name fix, crisp graphics, full auth UI

**User prompts:**

12. "can you tell me the whole stack and how the install process of
    getting this working with proper backend on another computer will
    work? Should I basically just shift over to running things entirely
    out of the gmux tauri app next session to test? It labels a few
    agents blank as just fish which i trhinbk is a problem here?"
13. "We need to also configure the system of authentication via qalcode2
    right? did you do that? There is much still to test"
14. "give me a testing list"
15. "make an md of this test list and show me the tauri launch shortcut
    when done in folder. make the folder called latest version test"
16. "before i test keep going with all tasks you have. The graphics in
    the monitor look really bad but at least it seems to be working
    somewhat showing activation. The graphics look bad as all the lines
    and borders look fuzzy."
17. "proceed with all these todos."

**Outcomes (in commit order):**

- **v3.5.2** — fish-name fix:
  - `backend/status/monitor.py` derives window name from `basename(cwd)`
    when tmux reports a generic name (fish/bun/bash). Verified 9/13
    panes were "fish" → 0/13 after fix.
  - `app/src-tauri/src/lib.rs` `open_agent`/`open_project` now also send
    `prefix+: set-window-option automatic-rename off` after the rename
    so tmux doesn't overwrite the name when the foreground process
    changes.

- **`latest_version_test/`** folder created with:
  - `TEST_LIST.md` — comprehensive testing checklist for v3.5.2
  - `launch_tauri.sh` — convenience launcher (`./launch_tauri.sh` /
    `--browser` / `--check`). Kills stale monitor.py first.

- **v3.5.3** — dashboard crisp graphics:
  - Glow filter `stdDeviation` reduced 2.5→1.0, 4.0→1.8 (tight halo
    instead of fog).
  - Stroke widths switched from fractional (3.5/2.5/1.5) to integer
    (3/2/2) to avoid sub-pixel anti-aliasing.
  - `Math.round()` on pan offset and node positions.
  - Added `shape-rendering: geometricPrecision`,
    `text-rendering: optimizeLegibility`, `vector-effect:
    non-scaling-stroke`, `stroke-linecap/linejoin: round`.

- **v3.6.0-a** — provider auth (full stack):
  - **Rust:** `list_providers` (parses auth.json + env vars + Ollama
    TCP check, **never returns secret tokens**), `login_provider`
    (whitelist-validated, spawns `opencode auth login <id>` in new
    tmux window), `logout_provider` (CLI then auth.json fallback),
    `list_models` (parses `opencode models` output).
  - **UI:** new "Providers" tab in Options panel. Renders authed
    providers with Disconnect button + unauthed providers as Connect
    buttons. Toast + polling for auth completion. Browser fallback
    notice. `cargo check` passes clean.
  - **First-launch wizard:** on Tauri boot, if `check_auth() == false`
    and the wizard hasn't been dismissed, auto-opens Options →
    Providers tab with a toast callout. One-shot per machine
    (localStorage flag).

- **`INSTALL_GUIDE.md`** (new) — end-to-end install for a new computer:
  - Full-stack ASCII diagram (Tauri → Rust → tmux → bun/opencode →
    cloud providers)
  - Component summary + network ports table
  - Stage-by-stage flow (system pkgs → Python deps → bun/opencode →
    repo → Tauri deps → provider auth → smoke test → first launch →
    verify → optional faster build)
  - One-shot recipes for CachyOS / Debian / headless-VM
  - Common install issues + fixes
  - Update + uninstall procedures

- **`docs/RUNNING_FROM_GMUX_ONLY.md`** (new) — recommendation answer:
  - Bottom line: **YES, use gmux Tauri as primary launcher next session**,
    keep one terminal as fallback.
  - Capability table: what's solid vs rough
  - Daily-driver checklist (what to use gmux for, what to keep
    terminal for)
  - "What to watch for and report" testing scenarios
  - Nuclear-restart procedure if Tauri crashes

**Files touched:**
- `backend/status/monitor.py`
- `app/src-tauri/src/lib.rs` (+auth commands, fish-name fix)
- `app/src/dashboard/css/dashboard.css`
- `app/src/dashboard/index.html`
- `app/src/dashboard/js/flow_layout.js`
- `app/src/dashboard/js/flow_render.js`
- `ui/v3/index.html` + `app/src/index.html` (synced)
- `latest_version_test/TEST_LIST.md` (new)
- `latest_version_test/launch_tauri.sh` (new, executable)
- `INSTALL_GUIDE.md` (new)
- `docs/RUNNING_FROM_GMUX_ONLY.md` (new)
- `docs/PROMPT_HISTORY.md` (this entry)

**Commits & tags:**
- `0a4c45a` → tag `v3.5.2` (fish-name fix)
- `b1a6e21` → tag `v3.5.3` (crisp graphics)
- `c84543b` → (auth Tauri + Settings panel)
- next commit will roll up auth wizard + install guide + recommendation
  doc + this entry → tag `v3.6.0`

**Diagnosis:**
- `app/src-tauri/src/lib.rs` has `open_dashboard` command and Ctrl+Alt+D global shortcut already wired.
- `app/src-tauri/tauri.conf.json` does NOT register a `dashboard` window — only `main` and `aquarium`.
- `app/src/dashboard/` directory does NOT exist — the dashboard HTML/CSS/JS lives only in
  `/home/fivelidz/projects/Knowledge_systems/gmux_memory_integration/dashboard/` and the
  gmuxtest source tree.
- `ui/v3/index.html` toolbar has buttons for Gesture / Voice / Graph / Memory (soon) / Options
  but no Agent Monitor button.

**Plan (scoped to /home/fivelidz/projects/gmux-system/ only):**
1. Bring a copy of the dashboard files into `app/src/dashboard/` from
   `Knowledge_systems/gmux_memory_integration/dashboard/` (read-only source).
2. Register `dashboard` window in `app/src-tauri/tauri.conf.json` (label, title, url, size, visible:false).
3. Add 🧠 Agent Monitor button to `ui/v3/index.html` toolbar (next to 🗂 Graph), wired to
   `window.__TAURI__.core.invoke('open_dashboard')` with graceful fallback if not running under Tauri.
4. Update `scripts/launch.sh` auto-sync to also mirror `ui/v3/dashboard/` (if present) into
   `app/src/dashboard/`, OR keep dashboard as part of app/src checked-in source.
5. Update `docs/VM_PROTOCOL.md` to note the new window in deployment checklist.
6. Test locally, then prepare VM install.

**Scope reminder:** changes ONLY inside `/home/fivelidz/projects/gmux-system/`. No edits to
gmuxtest, Knowledge_systems, or other projects.

---

## 2026-05-12 — Previous session (Tauri GStreamer fix, archives, docs)

Summary from HANDOVER.md (recorded by previous agent):
- Diagnosed WebKitWebProcess GStreamer assertion crash; fixed by setting
  `GST_DEBUG="*:0"` and `GST_PLUGIN_FEATURE_RANK="v4l2src:NONE,..."` in launch.sh.
- Tauri now launches: gmux 1400×900 window, sidecars on :8769 / :8770,
  session-restore daemon, PTY attached to tmux `gmux`.
- launch.sh auto-syncs `ui/v3/index.html` → `app/src/index.html` when v3 is newer.
- Commits: a3ae37f (archive), 25b4fa6 (HANDOVER + VM_PROTOCOL).
- Wrote: HANDOVER.md, docs/VM_PROTOCOL.md, archive/MANIFEST.md.

Files touched: scripts/launch.sh, HANDOVER.md, docs/VM_PROTOCOL.md, archive/MANIFEST.md.

---

## 2026-05-13 22:50 — v3.7.0 mega-release (token-intensive parallel session)

**User prompts:**

18. "vm is running again. Use a sub agent to communicate to it and run tests
    in the vm to test all back end. Ensure the whole AI stack is working
    together well. A system for agents to make sub agents within the
    session would be good and that is how sub agents should be controlled
    different to what we have here with qalcode"
19. "make a note also, gmux should be able to show when rate limiting has
    happened. We should also make a system to easily swap between agents?
    dropdown menu with more choices? favourite agents? hotkey or something
    to swap agents when selected? In the agent panel display as well there
    should be a button or hotkey to change layout, rather than having to
    always go to options. continue with all elements with sub agents also.
    I will be heading out. do your most token intensive tasks"

**Outcome — v3.7.0:** Five sub-agents dispatched in parallel + two host
features built simultaneously. All passing, all committed, all deployed
to VM. 211 tests passing across 3 suites.

**Sub-agent results:**
1. **VM-Testing** — 9/9 tests PASS on the sandbox VM. Report:
   `docs/VM_REPORTS/2026-05-13-vm-tests.md`. Found pre-existing yuki/yolo
   agents running in `/home/agent/vm_projects/autonomous/` (unrelated).
   opencode first-run takes 10-15s (SQLite migration).

2. **Sub-Agent Spawning** — new Rust `spawn_sub_agent` command, monitor
   loads parent-pointer JSON, UI Parent dropdown in new-agent modal,
   Shift+N hotkey pre-selects parent, dashboard renders cross-pane
   hierarchy. 30 new tests. `docs/SUB_AGENT_SYSTEM.md` explains the two
   sub-agent systems coexisting.

3. **Rate-Limit Detection** — 3 detection signals (SSE 429,
   auth.json expiry, terminal regex), `PaneState.RATE_LIMITED` enum, UI
   badges + countdown, status-bar global indicator. Tests bumped from
   79 → 117.

4. **macOS Porting Prep** — every Linux assumption guarded with
   `cfg!(target_os='macos')` / `IS_MAC`. Cmd+Opt+D on macOS, `open` vs
   `xdg-open`, `lsof` fallback for `ss`, brew package manager support,
   webkit2gtk skip note. `scripts/macos-smoke-test.sh` + full porting
   guide `docs/MACOS_PORTING.md`.

5. **Memory Aggregator** — `backend/status/memory_aggregator.py` walks
   `~/.local/share/gmux/memory/{episodic,semantic,procedural,shared}/`,
   emits `/tmp/gmuxtest-memory.json` per data contract. 3 modes
   (one-shot/daemon/watch). monitor.py integration so no separate
   daemon needed. `tools/seed_memory.py` for testing. 64 tests.

**Host features added myself (in parallel):**

- **Agent quick-swap palette** (`Ctrl+P` / `Ctrl+K`):
  - Fuzzy search over window_name + cwd + session
  - Favorites pinned to top with ⭐ icon
  - Arrow-key navigation, Enter to select, Esc to close
  - Stored in `localStorage.gmux_favorite_agents`
- **Direct jumps**: `Ctrl+1..9` jumps to Nth agent in current view
- **Toggle favorite**: `Ctrl+Shift+F` on the selected agent
- **Layout cycle button** + `L` hotkey:
  - Cycles auto → 1 → 2 → 3 → 2×2 → 3×2 → 4×2 → auto
  - Toolbar button next to Voice (label updates live)
  - Toast confirms each change

**Bugs the sub-agents introduced + I fixed:**

- `_make_pane` PaneInfo got duplicated `rate_limit_msg` keyword
  conflict — fixed by moving defaults into a `**{...}` merge dict.
- `memory_aggregator.py` had `global MEMORY_ROOT` declared AFTER first
  use of name in the function — moved to top of `main()`.

**Test totals:**

```
test_monitor_producers.py — 117 passed
test_sub_agents.py         —  30 passed
test_memory_aggregator.py  —  64 passed
                          ━━━━━━━━━━━━━━━━━━
                          211 passed, 0 failed
cargo check                — clean
```

**VM state:** v3.7.0 deployed via `./scripts/deploy.sh sandbox`. Browser
UI reachable at `http://192.168.122.100:5550/ui/v3/index.html`. All
producer files writing on the VM.

**Files touched (massive — see commit b1a6e21+):**

New:
- `backend/status/memory_aggregator.py`
- `backend/status/test_memory_aggregator.py`
- `backend/status/test_sub_agents.py`
- `docs/MACOS_PORTING.md`
- `docs/SUB_AGENT_SYSTEM.md`
- `docs/VM_REPORTS/2026-05-13-vm-tests.md`
- `scripts/macos-smoke-test.sh`
- `tools/seed_memory.py`
- `archive/ui/index.v3.7-quick-swap-layout-cycle.20260513-2256.html`

Modified:
- `app/src-tauri/Cargo.toml`
- `app/src-tauri/src/lib.rs`
- `app/src/dashboard/css/dashboard.css`
- `app/src/dashboard/js/agent_rail.js`
- `app/src/dashboard/js/subagents.js`
- `app/src/index.html` + `ui/v3/index.html` (synced)
- `backend/status/monitor.py`
- `backend/status/test_monitor_producers.py`
- `backend/voice/gmux_voice_daemon.py`
- `docs/AGENT_MONITOR_BACKEND.md`
- `scripts/gmux`, `scripts/install-vm.sh`, `scripts/launch-gmux.sh`, `scripts/launch.sh`

**Tag: v3.7.0**

---

## 2026-05-16 — phone bridge + usage tracking + fresh-VM rig design (v3.7.1, docs only)

**User prompt:**

20. "I have been putting together the ui for a gmux android app. I want
    you to figure out how this can connect well on the backend. Tomorrow
    we will start doing more solid tests on interactivity and testing
    the whole stack. I also want a system where we can best test the
    whole system installation to a fresh service. We can do this with vms.
    As an extra feature. When using claude you can see usage for the hour
    and current session here https://claude.ai/settings/usage . It would
    be good to display this for claude agents. I should do the same for
    other systems too."

**What I did — docs only, no code changes so tomorrow starts clean:**

1. **Discovered the gmux-phone repo** at `~/projects/gmux-phone/` (PWA, v0.6.1,
   APK-ready). Read its frozen contract at `docs/BACKEND_CONTRACT.md`. The
   phone speaks WS `:8767` + HTTP `:8768`. Bridge is the host-side missing
   piece.

2. **`docs/BRIDGE_DESIGN.md`** — full implementation plan for
   `backend/bridge.py`. Includes:
   - File layout (`backend/bridge/{auth, tmux_ops, adapter, bridge, pair}.py`)
   - Token system with `~/.config/gmux/pair-tokens.json`
   - Pairing flow with QR code
   - Phone schema → monitor.py JSON translation
   - Command-handling (spawn_agent, send_text, permission_response, kill)
   - SSE relay design
   - Auth scopes for multi-phone future
   - Versioning negotiation
   - Transport matrix (LAN / Tailscale / cloud relay)
   - 9-step implementation order, ~2-3 days estimated

3. **`docs/USAGE_TRACKING.md`** — design for the Claude/OpenAI/etc.
   quota display. Researched Anthropic's docs at
   `docs.anthropic.com/en/api/rate-limits`:
   - `anthropic-ratelimit-{requests,input-tokens,output-tokens}-{limit,remaining,reset}`
     headers in every response — exact source-of-truth
   - Aggregate per-hour ourselves from header deltas (Console UI doesn't
     have a public REST endpoint)
   - Three implementation paths: opencode plugin (future), opencode HTTP
     API metadata field (preferred), mitm proxy (fallback)
   - Schema for `/tmp/gmuxtest-usage.json`
   - UI surfaces: status bar widget, dashboard tab, new-agent modal hint
   - Per-provider quirks (OpenAI, Google, DeepSeek, Ollama)

4. **`docs/FRESH_VM_TEST_PLAN.md`** — clean-room test rig. Includes:
   - Three rigs: sandbox (mutated), fresh-snapshot QEMU (clean each run),
     cloud disposable (future CI)
   - `scripts/vm-fresh-boot.sh` snippet — QEMU snapshot revert + boot headless
   - `scripts/test-fresh-install.sh` — full deploy-and-verify cycle
   - 9-check pass criteria
   - Mandatory / smoke / stress test tiers
   - Failure-mode capture (tar bundle of logs + JSON)
   - Future GitHub Actions matrix yaml

5. **`docs/NEXT_ACTIONS.md`** — appended new section with the three streams
   ready to pick up tomorrow, plus a checklist of manual tests still to do
   from `latest_version_test/TEST_LIST.md`.

**Commit + tag:** v3.7.1 (docs-only).

**State of the repo:**
- v3.7.0 code unchanged
- 211 tests still passing
- VM still has v3.7.0 deployed; `./scripts/deploy.sh sandbox` ready
- 5 new docs + history entry
- Tomorrow has 3 well-spec'd streams to choose from

---

## 2026-05-17 — Maestro study (v3.7.2, docs only)

**User prompts:**

21. "https://github.com/its-maestro-baby/maestro?ref=producthunt — I want
    you to download into our studied github repos this one. It is made
    by a friend of mine. I want you to analyse how it does the display
    for usage tracking, 5 hours and click to change to the weekly
    usage. Most critically though I want you to see how it links the
    tauri to the terminal backend properly so we can apply the same
    principles to gmux. We are happy with the UI, the voice is doing
    well. Now we just have to ensure the backend links work and will
    work on all/most systems well. See how it works as a terminal
    emulator essentially."

22. "All very relevant to understand also as perhaps many elements that
    we have running through qalcode2 can just be handled by the gmux
    tauri system. Potentially make a new gmux-system if it will work
    best with the backend whilst keeping all the UI and voice systems
    we have worked on. Figure out what to do and write notes in a new
    folder"

**What I did:**

1. Cloned maestro repo to `~/projects/github_repos/maestro/` (depth 1
   shallow clone, commit `a10500d`).
2. Read every critical file:
   - `src-tauri/src/core/process_manager.rs` (686 LOC PTY manager)
   - `src-tauri/src/core/terminal_backend.rs` (181 LOC trait abstraction)
   - `src-tauri/src/core/session_manager.rs` (187 LOC DashMap session registry)
   - `src-tauri/src/commands/terminal.rs` (333 LOC Tauri command surface)
   - `src-tauri/src/commands/usage.rs` (340 LOC — the Anthropic usage API)
   - `src/lib/terminal.ts` (307 LOC frontend wrapper)
   - `src/components/terminal/TerminalView.tsx` (762 LOC xterm.js mount)
   - `src/components/tamagotchi/Tamagotchi.tsx` (130 LOC usage widget)
3. Wrote three deep-dive docs under `docs/maestro_study/`:

   - **`00_FINDINGS.md`** — every architectural pattern discovered, every
     correctness fix (UTF-8 split-byte, Windows DSR, WebKit composition
     bug, render batching), and the **undocumented**
     `https://api.anthropic.com/api/oauth/usage` endpoint with full
     headers and response schema. The endpoint Anthropic doesn't
     publicly document — what claude.ai/settings/usage uses internally.

   - **`01_ARCHITECTURE_DIFF.md`** — side-by-side comparison of
     gmux-system vs maestro for: spawning agents, capturing output,
     tracking sessions, status detection, permission handling, rate
     limiting, OS support, code quality. Honest assessment of where
     each system wins.

   - **`02_MIGRATION_PLAN.md`** — recommended path forward:
     **Option 3: sibling `app-v2/` folder inside gmux-system** that
     uses maestro's PTY-first core, lifts our existing UI/voice/
     gesture/dashboard verbatim via Vite alias, and coexists with v3
     (which keeps the headless + remote + phone story). 7-phase
     plan, ~1 week of focused work, with tags at every phase.

**Key findings (TL;DR):**

- Maestro is **Tauri 2 + portable-pty + xterm.js**. Each session is a
  fresh PTY spawned by Rust. **No tmux dependency** — works on macOS
  and Windows out of the box.
- Their render pipeline is genuinely brilliant: 16ms tokio batching
  in Rust + rAF flush + WebGL/Canvas/DOM cascade in JS. Result is
  sub-50ms input latency with smooth output rendering even during
  `cargo build`.
- The `usage.rs` Anthropic OAuth API call is **drop-in** for our
  rate-limit display work. 50 LOC of Rust + a 30-line widget.
  Resolves the entire `claude.ai/settings/usage` mystery from
  `docs/USAGE_TRACKING.md`.
- Their PTY core has correctness fixes we don't have:
  - UTF-8 split-byte decoder (emoji + CJK across read boundaries)
  - Windows DSR cursor-position response
  - WebKit composition bug workaround for CJK input
  - macOS-from-Finder LANG injection
- The gap we lose by adopting their PTY-first: no headless mode, no
  cross-machine view, no phone access. Mitigation: keep monitor.py +
  the phone bridge running alongside. v3 stays the headless specialist;
  v4 becomes the desktop power-user specialist.

**Recommendation:** Build `app-v2/` as a sibling Tauri shell inside
`gmux-system`. Reuse `ui/v3/`, `backend/`, `models/`, `scripts/`, and
`docs/` directly. Lift maestro's PTY core wholesale. Get macOS +
Windows + faster Linux for free. Keep v3 alive as the headless +
remote specialist. Detailed 7-phase plan in `02_MIGRATION_PLAN.md`.

**Commit + tag:** v3.7.2 (docs-only — no code changes).

---

## 2026-05-17 17:00 — gmux-v4 repo created (split from gmux-system)

**User prompt:**

23. "Start of by making a lot of good md documents specifying the
    objectives and the to do list so other agents can easily take
    over. make a new private repo for v4"

**What I did:**

Created a brand-new private GitHub repo at
`https://github.com/fivelidz/gmux-v4` (commit `e8c2...`, tag
`v0.0.0-docs`). The repo is intentionally docs-only at this stage —
no source code. The goal was to lay a solid foundation so any
agent (or new contributor) can pick up implementation work cold.

**10 docs written** (~2150 lines total) in
`/home/fivelidz/projects/gmux_v4/`:

| File | Purpose |
|---|---|
| `README.md` | Front door, reading order |
| `LICENSE` | MIT with third-party attribution (maestro, v3) |
| `.gitignore` | Standard Node/Rust/Tauri ignores |
| `docs/OBJECTIVES.md` | Goals, non-goals, success criteria |
| `docs/ARCHITECTURE.md` | System + module map + data flow |
| `docs/PHASES.md` | 7 phases with acceptance criteria |
| `docs/TODO.md` | Granular task list per phase |
| `docs/CONTRIBUTING.md` | How to pick up work, including AI-agent guidance |
| `docs/AGENT_HANDOFF.md` | Current state (always last-read, always-updated) |
| `docs/FROM_V3.md` | What to lift from gmux-system v3 |
| `docs/FROM_MAESTRO.md` | What to lift from maestro |

**Architectural decision recorded:** gmux-v4 is a **sibling product**,
not a successor that retires v3. v3 stays alive for headless / remote /
phone use cases. v4 specialises in cross-platform desktop with sub-50ms
input latency, lifting maestro's PTY-direct architecture.

**Tag:** `v0.0.0-docs` (in the new repo)

**Status:** v3.7.2 unchanged in this repo. v4 is in a separate folder
+ separate repo at `~/projects/gmux_v4/`.

**Next session (any agent) should:**
1. `cd ~/projects/gmux_v4`
2. Read the docs in order specified in the README
3. Begin Phase 0 (scaffold) per `docs/TODO.md`
