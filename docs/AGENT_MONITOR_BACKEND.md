# Agent Monitor — Backend Wiring Status

What the Agent Monitor (dashboard) needs from the backend, what already works,
and what's still missing. Source of truth for this contract is
`/home/fivelidz/projects/Knowledge_systems/gmux_memory_integration/docs/02_DATA_CONTRACTS.md`.

## TL;DR

The Tauri side is fully wired. The Rust state-poll thread broadcasts four
events every second to **main / dashboard / aquarium** windows. The dashboard
already listens to all of them. As of **v3.7** all four streams have producers,
including the memory stream which is now driven by `memory_aggregator.py`
(invoked from monitor.py's existing aggregate worker every ~10s).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA FLOW (one-second tick)                       │
└─────────────────────────────────────────────────────────────────────────┘

      producers                tmp files                  Rust              dashboard
     ─────────────             ──────────                ──────             ─────────

 monitor.py             →  gmuxtest-pane-state.json   →  gmux-state    →  agents ✅
 monitor.py             →  gmuxtest-services.json     →  gmux-services →  services ✅
 monitor.py (v3.5+)     →  gmuxtest-activity.json     →  activity-tick →  activity ✅
 monitor.py (v3.5+)     →  gmuxtest-files.json        →  files-update  →  files ✅
 monitor.py + aggregator(v3.7+) →  gmuxtest-memory.json →  memory-update → memory ✅
```

## What works today (v3.7)

| Stream | Producer | Schema | Tauri event | Dashboard handler |
|--------|----------|--------|-------------|-------------------|
| pane-state (agents) | `backend/status/monitor.py` ✅ | per 02_DATA_CONTRACTS.md §pane state | `gmux-state` | `data.js` ✅ |
| services | `backend/status/monitor.py` ✅ | flat flags object | `gmux-services` | n/a (main UI only) |
| activity feed | `backend/status/monitor.py` v3.5+ ✅ | array of tool events | `activity-tick` | `data.js` ✅ |
| file-touch map | `backend/status/monitor.py` v3.5+ ✅ | dict keyed by abs path | `files-update` | `data.js` ✅ |
| memory | `backend/status/memory_aggregator.py` v3.7+ ✅ | dict of memory entries | `memory-update` | `data.js` ✅ |

## Fields live as of v3.6 (changes from this pass)

### Agents stream — new fields added to `PaneInfo` and `LiveState`

| Field | Description | Source |
|-------|-------------|--------|
| `session_age_s` | Alias of `uptime_s`. The `detail_panel.js` Stats tab reads `session_age_s`; the backend was emitting `uptime_s` only — now both are present. | psutil process create_time |
| `sub_agents` | List of pane_ids whose OpenCode sessions have `parentID == this.session_id`. Updated by the aggregate worker every ~10s. | `/session` API |
| `last_tool_call_summary` | Dict `{tool, file_path, command, ts}` for the most recent `tool_start` event for this pane. Gives the dashboard a quick summary without scanning the full activity feed. | activity deque |

### Activity stream — args now richer

| Args field | Tools where it's now populated |
|-----------|-------------------------------|
| `args.file_path` | Read, Write, Edit, MultiEdit, Patch, Glob, Grep (where filePath/path is the input) |
| `args.command` | Bash, Terminal, Shell — truncated at 120 chars |
| `args.pattern` | Grep, Glob — from `pattern` / `query` / `glob` keys, truncated at 80 chars |

### Files stream — rel_path quality improved

`rel_path` is now correctly computed by stripping the pane's CWD prefix from
the absolute path, giving e.g. `src/voice/daemon.py` instead of just
`daemon.py`. This is the fix for the empty-folder-tree bug where files appeared
as top-level nodes with no directory hierarchy in the dashboard flowchart.

## ✅ Memory aggregator (v3.7 — IMPLEMENTED)

**File:** `backend/status/memory_aggregator.py` (stdlib only, ~400 LOC).

**What it does:**
1. Walks `~/.local/share/gmux/memory/{episodic,semantic,procedural,shared}/*.json`
2. Parses each memory file; skips malformed JSON and files missing required keys
3. Builds three indexes: `by_agent`, `by_kind`, `by_tag`
4. Writes atomically (tmpfile + `os.rename`) to `/tmp/gmuxtest-memory.json`

**Integration path:** `monitor.py`'s `run_aggregate_worker()` calls
`memory_aggregator.aggregate_once()` every `AGGREGATE_INTERVAL` (10s).
Wrapped in `try/except` so a memory-side failure can never kill the worker.
This avoids running a separate daemon process.

**Run modes:**

```bash
# One-shot (also runs implicitly inside monitor.py)
python3 backend/status/memory_aggregator.py

# Daemon (standalone — polls every 10s)
python3 backend/status/memory_aggregator.py --daemon

# Watch mode (inotify on Linux, polling fallback)
python3 backend/status/memory_aggregator.py --watch
```

**Test fixtures:** `tools/seed_memory.py` writes 8 example memories across
4 kinds and 6 agents so you can verify the dashboard renders before any
real agent has produced anything. Idempotent; supports `--clear` to remove.

**Tests:** `backend/status/test_memory_aggregator.py` — 64 inline assertions
covering missing dir, valid parsing, malformed-JSON skip, grouping correctness,
atomic-write verification, partial-tree handling, and dashboard-field presence.

**Output schema** matches what `app/src/dashboard/js/data.js` expects
(line 151–153 and 502–504): the dashboard does
`parsed.memories || parsed` → `Object.values(...)` → array. Our top-level
`memories` key is a dict keyed by `memory_id`, so the conversion to an array
of memory entries is automatic.

## What's still missing

### 1. `lines_added` / `lines_removed` on activity events

The `detail_panel.js` `renderDelta()` function displays code-change deltas
(`+N lines / −M lines`) on tool_end events. These fields are NOT producible
from the opencode SSE stream — the SSE events don't include diff data.

Options to produce these:
- **A**: Have opencode expose a per-message diff summary (upstream change).
- **B**: Compare file snapshots before/after each Write/Edit via inotify + hash.
- **C**: Parse git diff output after each write completes (fragile, slow).

Currently marked ❌ in the field audit. The mock data layer synthesises these
for the demo view. Real data would require option A or B.

### 2. `is_god_node` / `callers` on file entries

Requires graphify analysis to compute which files are central nodes in the
call/import graph. Out of scope for monitor.py — graphify writes these into
a `graph.json` which a future aggregator would merge into the files map.

## Diagnostic checklist

If the dashboard window opens but stays empty:

```bash
# 1. Are the producer files being written?
ls -la /tmp/gmuxtest-*.json

# 2. Is monitor.py running?
ps aux | grep monitor.py | grep -v grep

# 3. Are the files being updated (timestamp changes every ~2s)?
watch -n 2 "ls -la /tmp/gmuxtest-*.json"

# 4. Check activity feed has real events (not just a stale empty array)
python3 -c "
import json
d = json.load(open('/tmp/gmuxtest-activity.json'))
print(f'{len(d)} events total')
for e in d[-3:]:
    print(' ', e.get('kind'), e.get('tool'), e.get('pane_id'), e.get('ts'))
"

# 5. Check file-touch map has entries with good rel_paths
python3 -c "
import json
d = json.load(open('/tmp/gmuxtest-files.json'))
print(f'{len(d)} file entries')
for k, v in list(d.items())[:3]:
    print(' ', v['rel_path'], f\"touches_30m={v['touches_30m']}\")
" 2>/dev/null || echo "files empty or missing"

# 6. Check pane-state has sub_agents + session_age_s
python3 -c "
import json
d = json.load(open('/tmp/gmuxtest-pane-state.json'))
for pid, p in list(d.items())[:2]:
    print(pid, 'session_age_s:', p.get('session_age_s'), 'sub_agents:', p.get('sub_agents'))
"

# 7. Open devtools inside the dashboard window (right-click → Inspect)
#    and check the floating HUD in the top-right corner:
#       🟢 tauri · state:N mem:N act:N files:N
#    state should be > 0 within a few seconds.
#    act and files should climb once monitor.py is receiving SSE events.

# 8. If state climbs but act/files stay at 0 forever, that's the missing
#    producer — start monitor.py:
#    python3.11 backend/status/monitor.py
```

## Run the test suite

Verify all producer functions work correctly:

```bash
python3.11 backend/status/test_monitor_producers.py
```

All 78 assertions should print OK. Exit code 0 = clean.

## What's already wired correctly

- **Rust `app/src-tauri/src/lib.rs` lines 481–517** — single state-poll thread
  reads all six tmp files every second and emits to all three windows.
- **Rust `open_dashboard` Tauri command** + Ctrl+Alt+D global shortcut.
- **`tauri.conf.json`** registers the `dashboard` window.
- **`app/src/dashboard/index.html`** + js + css.
- **UI toolbar button** 🧠 Agent Monitor in `ui/v3/index.html` next to Graph.
- **launch.sh auto-sync** for `ui/v3/index.html`.

## Capabilities check

`app/src-tauri/capabilities/default.json` currently lists
`"windows": ["main", "aquarium"]`. The `default` capability does NOT cover
the new `dashboard` window. Two options:

a. Add `"dashboard"` to the windows list (simplest).
b. Define a second capability scoped to `["dashboard"]` if dashboard needs
   different permissions later.

Option **(a)** is the right call — the dashboard uses the same `core:default`
permission set as the main window (event.listen is part of core).

## Action items (ordered)

1. ✅ Copy dashboard files + register window + add button
2. Add `"dashboard"` to capabilities/default.json windows list
3. Verify dashboard renders inside Tauri (agent rail at minimum)
4. ✅ Extend monitor.py to write `gmuxtest-activity.json` (v3.5)
5. ✅ Extend monitor.py to derive `gmuxtest-files.json` from the activity deque (v3.5)
6. ✅ Enrich args (command/pattern), fix rel_path, add session_age_s / sub_agents / last_tool_call_summary (v3.6)
7. ✅ Add comprehensive test suite (`test_monitor_producers.py`)
8. ✅ Build `memory_aggregator.py` per the contract (v3.7)
9. (Future) Source `lines_added/removed` for code-change delta display
10. (Future) Memory retention policy + deduplication + search index
11. Update VM_PROTOCOL.md so VM installs spin up monitor with the new outputs
