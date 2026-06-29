# Handover — Memory aggregator landed in v3.7, ready to port forward

**From:** Previous agent (Claude Sonnet 4.6) finishing the memory aggregator
implementation in `~/projects/gmux-system/` before context ran out.
**To:** Next agent picking up gmux_v4 work.
**Date:** 2026-05-17
**Status:** ✅ v3.7 memory aggregator implemented + tested + integrated.
   v4 needs to absorb the same files, then continue with whatever
   `V4_STATUS.md` lists.

---

## What you need to know before doing anything else

1. **gmux-system v3.7.2 is stable.** 211 tests pass. The memory aggregator
   is the last stream that was missing from the dashboard's 5-stream
   contract — it now exists and is integrated.
2. **gmux_v4 already mirrors v3.7.2** (per its own README and `V4_STATUS.md`),
   so the new memory aggregator files **may or may not already be here**.
   Step 1 below tells you how to check and sync.
3. **Run the 3 test suites first.** If 211/211 pass, you're at parity with
   v3 and free to continue v4-specific work.
4. **Don't re-implement anything.** Every file already exists in v3.

---

## Step 1 — Verify v4 is at parity with v3.7

```bash
cd ~/projects/gmux_v4

# Run the three Python test suites
python3.11 backend/status/test_monitor_producers.py   | tail -3
python3.11 backend/status/test_sub_agents.py          | tail -3
python3.11 backend/status/test_memory_aggregator.py   | tail -3
```

**Expected:** `117 passed` + `30 passed` + `64 passed` = **211 total, 0 failed.**

If `test_memory_aggregator.py` does not exist or fails, sync the files from
v3:

```bash
# Copy the 3 new files from v3 → v4
cp ~/projects/gmux-system/backend/status/memory_aggregator.py       backend/status/
cp ~/projects/gmux-system/backend/status/test_memory_aggregator.py  backend/status/
cp ~/projects/gmux-system/tools/seed_memory.py                      tools/

# Patch monitor.py to call aggregate_once() inside run_aggregate_worker()
# — find the auth_expiry block in run_aggregate_worker and append the
#   memory-aggregator try/except block right after it. The exact patch is
#   in /home/fivelidz/projects/gmux-system/backend/status/monitor.py
#   around lines 2260–2275. Look for the comment:
#       "# v3.7 — refresh /tmp/gmuxtest-memory.json from raw memory files."

# Re-run tests to confirm
python3.11 backend/status/test_memory_aggregator.py | tail -3
```

---

## Step 2 — End-to-end smoke test (proves the wiring)

```bash
# Clear any leftover seeds from previous sessions
python3.11 tools/seed_memory.py --clear

# Run on empty dirs — should produce empty structure, not crash
python3.11 backend/status/memory_aggregator.py
# → "Parsed 0 memories, skipped 0. Total: 0."
# → /tmp/gmuxtest-memory.json exists with total_count=0

# Seed 8 fake memories across all 4 kinds and 6 agents
python3.11 tools/seed_memory.py
# → "Wrote 8 seed memories under /home/fivelidz/.local/share/gmux/memory"

# Re-aggregate — should pick up all 8
python3.11 backend/status/memory_aggregator.py
# → "Parsed 8 memories ... agents: ['pane-1', 'pane-4', 'graphify', ...]"

# Verify on-disk shape
python3.11 -c "
import json
d = json.load(open('/tmp/gmuxtest-memory.json'))
print('Schema:', d['_schema_version'])
print('Total:', d['total_count'])
print('Agents:', list(d['by_agent'].keys()))
print('Kinds:', {k: len(v) for k, v in d['by_kind'].items()})
print('Tags:', len(d['by_tag']))
"
```

**Expected output:**
```
Schema: 1.0
Total: 8
Agents: ['pane-1', 'pane-4', 'graphify', 'pane-6', 'human', 'monitor']
Kinds: {'episodic': 2, 'semantic': 2, 'procedural': 2, 'shared': 2}
Tags: 24
```

---

## Step 3 — Run the v4-specific tests too

The v4 PTY core has its own smoke test (lifted from maestro). This proves
the substrate swap works independently of the v3 backend.

```bash
cd ~/projects/gmux_v4/app/src-tauri

# Compile + run the standalone PTY smoke test (no Tauri, no UI)
cargo run --example pty_smoke --release
```

**Expected:**
```
── gmux-v4 PTY smoke test (no Tauri) ────────────────────────────
✅ PTY opened
✅ shell spawned (pid …)
   → prompt + early output: N bytes
✅ wrote 'echo "hello v4"\r' (16 bytes)
✅ captured 'hello v4' in N bytes of output
✅ shell exited cleanly with ExitStatus { code: 0, signal: None }
──────────────────────────────────────────────────────
✅ ALL CHECKS PASSED
```

If this passes, both the v3 backend AND the v4 PTY substrate are
working. That's the baseline.

---

## Step 4 — What's left in v4 (read V4_STATUS.md)

The full backlog lives in `~/projects/gmux_v4/docs/V4_STATUS.md`. Highlights:

### Done (alpha.4 reached)
- ✅ Maestro PTY core lifted into `app/src-tauri/src/core/`
- ✅ 7 new Tauri commands: `spawn_shell`, `write_stdin`, `resize_pty`, `kill_session`, `kill_all_sessions`, `get_backend_info`, `pty_ping`
- ✅ `open_agent_v4`, `spawn_sub_agent_v4` Tauri commands
- ✅ xterm.js per pane wired
- ✅ Options → v4 Lab tab (toggle `localStorage.gmux_v4_pty`)
- ✅ `cargo check` clean (1 pre-existing warning)
- ✅ Full release builds: 17MB binary + 5.8MB .deb + 5.8MB .rpm
- ✅ Headless launch works; sidecars start; `GMUX_V4_PTY=1` skips legacy tmux

### Needs HUMAN GUI verification (next agent cannot do this headless)
See `docs/TEST_REPORT_alpha4.md` "What's NOT tested" section:
- Tauri window opens at 1400×900 with full v3 UI
- Options → v4 Lab tab visible
- Press `N` → spawn shell → Terminal view mounts xterm.js
- Typing in xterm sends keystrokes
- Agent output streams back
- `Ctrl+P` palette, `L` layout cycle, voice mode, gesture mode all work
- `Ctrl+Alt+D` opens dashboard window
- Closing app cleans up all child PTYs

### Headless work the next agent CAN do
1. **Rewire remaining commands to v4 path** — `open_project`,
   `spawn_sub_agent`, `login_provider` still use the legacy tmux flow.
   They need v4 sibling commands or a feature-flag branch.
2. **Drop `start_pty` tmux attach** — currently still spawned at app start.
   Gate behind `v4_legacy_mode` flag.
3. **monitor.py adaptation** — add Rust `get_pane_state_v4` Tauri command
   returning the same JSON shape as `/tmp/gmuxtest-pane-state.json`.
   Update monitor.py to consume PTY events when v4 mode is on.
4. **Session restore swap** — replace tmux-window-name persistence with
   `~/.config/gmux/sessions.json` snapshot. Re-spawn shells on startup.
5. **Install scripts** — `scripts/install-vm.sh`: tmux moves from
   required to optional (headless-only).
6. **AppImage fix** — `linuxdeploy` offline mode (network fetch failed
   during alpha.4 build).
7. **Code-signing pipeline** — deferred to ship phase.

---

## How the v3 memory aggregator integrates with v4's PTY model

The aggregator is **substrate-agnostic**. It only reads memory files from
`~/.local/share/gmux/memory/**/*.json` and writes
`/tmp/gmuxtest-memory.json`. It doesn't care whether the agents that
created those memories were running under tmux (v3) or under a Rust-owned
PTY (v4). The dashboard consumes the same `memory-update` Tauri event in
both versions.

**For v4 specifically:**
- Keep `memory_aggregator.aggregate_once()` calls inside monitor.py for as
  long as monitor.py exists as a sidecar.
- When `get_pane_state_v4` lands in Rust, **also** add a Rust path to call
  `memory_aggregator.py --once` (subprocess) on the same 10s cadence —
  this way you can eventually drop the Python sidecar.
- Alternative: rewrite `aggregate_once()` in Rust. ~300 lines, no
  third-party crates needed (uses `serde_json` + `walkdir`). This is a
  reasonable beta-2 task once the PTY model is stable.

---

## Key files reference

### In v3 (parent — `~/projects/gmux-system/`)

| File | Why it matters for v4 |
|------|----------------------|
| `backend/status/memory_aggregator.py` | Source of truth. Copy verbatim into v4. |
| `backend/status/test_memory_aggregator.py` | Copy verbatim. |
| `tools/seed_memory.py` | Copy verbatim. |
| `backend/status/monitor.py` | v4's monitor.py is a fork. The aggregator integration is a ~10-line patch at the bottom of `run_aggregate_worker()`. |
| `LAST_WORKING_STATE.md` | Full system snapshot. Read first if you've never seen this codebase. |
| `docs/AGENT_MONITOR_BACKEND.md` | Updated with the memory stream marked ✅. |

### In v4 (this repo — `~/projects/gmux_v4/`)

| File | Why it matters |
|------|----------------|
| `docs/V4_STATUS.md` | Living checklist. Update after every session. |
| `docs/V4_PTY_SWAP.md` | Plan for the substrate swap. |
| `docs/TEST_REPORT_alpha4.md` | What's tested in alpha.4. |
| `app/src-tauri/src/core/` | Lifted maestro PTY code (with attribution). |
| `app/src-tauri/src/commands/terminal.rs` | New v4 Tauri commands. |
| `app/src-tauri/src/lib.rs` | Legacy v3 commands + new core registered. |
| `app/src-tauri/examples/pty_smoke.rs` | Standalone PTY smoke test. |
| `ui/v3/index.html` | Main UI (8000+ lines — same as v3). |
| `app/src/index.html` | Mirror of ui/v3 that Tauri serves. |

---

## What the previous agent (me) actually shipped

If you want to see the diff that was made before context ran out:

```bash
cd ~/projects/gmux-system

# Files created
ls -la backend/status/memory_aggregator.py       # 414 lines
ls -la backend/status/test_memory_aggregator.py  # 297 lines
ls -la tools/seed_memory.py                      # 174 lines

# Files modified
git diff --staged backend/status/monitor.py | head -25
# → adds ~8 lines inside run_aggregate_worker():
#     try:
#         from memory_aggregator import aggregate_once as _memory_aggregate_once
#         _memory_aggregate_once()
#     except Exception as e:
#         print(f"[gmuxtest-status] memory aggregator: {e}", file=sys.stderr)

git diff --staged docs/AGENT_MONITOR_BACKEND.md
# → marks memory stream ✅, documents integration path
```

---

## If something is broken

1. **`test_memory_aggregator.py` fails** — likely the file wasn't copied
   from v3. Run the sync command in Step 1.
2. **monitor.py import error** — the `from memory_aggregator import ...`
   line is inside the worker thread loop. If the file isn't present, the
   `try/except` catches it and logs to stderr; the worker keeps running.
   Symptom: `[gmuxtest-status] memory aggregator: No module named ...`
   in `/tmp/gmux-monitor.log`. Fix: copy the file.
3. **Aggregator runs but `/tmp/gmuxtest-memory.json` is missing** — check
   `/tmp/` is writable. Run `python3.11 backend/status/memory_aggregator.py -v`
   to see verbose output.
4. **Dashboard memory tab is empty even after seeding** — the dashboard
   reads via Tauri event `memory-update`. Confirm the Rust side emits it:
   grep `memory-update` in `app/src-tauri/src/lib.rs`. If the line exists
   and the file is being written, the event will fire on the next 1s tick.

---

## Quick-start for the next agent (TL;DR)

```bash
cd ~/projects/gmux_v4

# 1. Confirm parity with v3
python3.11 backend/status/test_monitor_producers.py | tail -3   # 117 passed
python3.11 backend/status/test_sub_agents.py        | tail -3   #  30 passed
python3.11 backend/status/test_memory_aggregator.py | tail -3   #  64 passed

# 2. Confirm v4 PTY core
cd app/src-tauri && cargo run --example pty_smoke --release | tail -10

# 3. Read what's next
cd ~/projects/gmux_v4
cat docs/V4_STATUS.md      # what's done, what's next
cat docs/TEST_REPORT_alpha4.md  # what's tested, what needs human eyes

# 4. Update todos as you work — DON'T let V4_STATUS.md go stale
```

If steps 1–2 all green, **the system is at parity with v3.7.2 plus the
v4 PTY core works standalone**. You're free to continue the substrate
swap, monitor.py adaptation, or anything else V4_STATUS.md prioritises.
