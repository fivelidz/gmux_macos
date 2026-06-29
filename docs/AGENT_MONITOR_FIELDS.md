# Agent Monitor — Field Audit

**Generated:** 2026-05-13
**Purpose:** Comprehensive map of every field the dashboard renderers reference,
whether that field is currently produced by `monitor.py`, and what stream
(`agents` / `activity` / `files` / `memories`) carries it.

---

## How to read this table

| Column | Meaning |
|--------|---------|
| **Object** | Which data object the field lives on |
| **Field** | Exact JS property name used by the renderer |
| **Used in** | Which renderer file(s) reference it |
| **Status** | ✅ live / ⚠ partial / ❌ missing |
| **Notes** | Gap description or source |

---

## Stream 1 — Agents (`gmux-state` / `gmuxtest-pane-state.json`)

| Field | Used in | Status | Notes |
|-------|---------|--------|-------|
| `pane_id` | agent_rail, detail_panel, flow_layout, app | ✅ | Core pane identifier |
| `session_name` | agent_rail, detail_panel | ✅ | tmux session name |
| `window_index` | detail_panel | ✅ | tmux window index |
| `window_name` | agent_rail, detail_panel, flow_layout, app | ✅ | Custom window name (with caching) |
| `pane_index` | detail_panel | ✅ | tmux pane index |
| `is_active` | agent_rail, detail_panel | ✅ | Whether pane is gmux-focused |
| `foreground_cmd` | detail_panel (Info tab) | ✅ | Current foreground command |
| `state` | agent_rail, detail_panel, app, flow_layout | ✅ | `idle`/`working`/`waiting`/etc |
| `has_ai` | (internal, not rendered directly) | ✅ | Whether opencode is running |
| `last_line` | detail_panel (Info tab) | ✅ | Last terminal output line |
| `api_port` | detail_panel (Stats tab) | ✅ | OpenCode HTTP port |
| `current_tool` | detail_panel (Info tab) | ✅ | Currently running tool |
| `todo_done` | agent_rail, detail_panel, flow_layout | ✅ | Completed todo count |
| `todo_total` | agent_rail, detail_panel, flow_layout | ✅ | Total todo count |
| `todo_items` | detail_panel (Info tab — renderTodoList) | ⚠ | Synthesised from todo_done/total by JS; real items come from `todos[]` |
| `todos` | detail_panel (via todo_items synthesis) | ✅ | Real todo objects `[{id,content,status,priority}]` |
| `sub_agent_permission` | detail_panel (Stats tab) | ✅ | Whether sub-agent needs permission |
| `ram_mb` | agent_rail (mini-stats), detail_panel (Stats tab) | ✅ | RSS in MB (requires psutil) |
| `cpu_pct` | detail_panel (Stats tab) | ✅ | %CPU (requires psutil) |
| `uptime_s` | detail_panel (Stats tab — session_age_s) | ⚠ | Field exposed as `uptime_s`; detail_panel reads `session_age_s` — **name mismatch** |
| `children` | (not directly rendered, internal only) | ✅ | Child process list |
| `session_id` | (internal lookup) | ✅ | Active OpenCode session ID |
| `model` | detail_panel (Info tab) | ✅ | e.g. `claude-sonnet-4-6` |
| `provider` | (available, not currently rendered) | ✅ | e.g. `anthropic` |
| `token_in` | (available, not yet rendered in detail_panel) | ✅ | Cumulative input tokens |
| `token_out` | (available, not yet rendered) | ✅ | Cumulative output tokens |
| `token_reasoning` | (available, not yet rendered) | ✅ | Extended-thinking tokens |
| `cost_usd` | (available, not yet rendered) | ✅ | Cumulative cost |
| `msg_count` | (available, not yet rendered) | ✅ | Message count in session |
| `cwd` | detail_panel (via current_dir — NOTE: rendered as `current_dir` in some UI variants) | ⚠ | Field exists as `cwd`; activity feed resolves paths via `_pane_to_cwd` |
| `tool_history` | (available; not directly rendered by detail_panel — it uses activity feed instead) | ✅ | Last 30 tool names |
| `sub_agents` | detail_panel (Stats tab: `SUBAGENTS.childrenOf()`) | ❌ | Sub-agent parent→child mapping is manual in JS localStorage; backend never emits a `sub_agents[]` array per agent. Requires parsing `/session` for `parentID`. |
| `last_tool_call_summary` | (not yet consumed; useful for quick info display) | ❌ | Summary of most recent tool call with kind+tool+file |
| `recent_files` | (not yet consumed as direct field; derived from activity feed) | ❌ | Per-agent recent file list (could be pre-computed backend-side) |

### Field name mismatches (agent)

| Backend field | JS renders as | Fix needed? |
|--------------|---------------|------------|
| `uptime_s` | `session_age_s` (detail_panel.js line 122) | ⚠ YES — alias needed or JS fix |
| `cwd` | `current_dir` (mentioned in docs, not yet rendered) | ⚠ minor |

---

## Stream 2 — Activity (`activity-tick` / `gmuxtest-activity.json`)

| Field | Used in | Status | Notes |
|-------|---------|--------|-------|
| `id` | data.js (deduplication) | ✅ | `act_<ms>_<pane>_<callid>` |
| `ts` | detail_panel, flow_layout | ✅ | ISO-8601 UTC with ms |
| `pane_id` | detail_panel, flow_layout, agent_rail | ✅ | Source pane |
| `agent_name` | detail_panel (renderOpRow), flow_layout | ✅ | Human-readable window name |
| `kind` | detail_panel, flow_layout | ✅ | `tool_start` / `tool_end` / `permission_request` |
| `tool` | detail_panel (renderOpRow), flow_layout | ✅ | Tool name |
| `args.file_path` | detail_panel, flow_layout (pathMatches) | ✅ | File being operated on |
| `args.command` | detail_panel (renderOpRow path field) | ⚠ | Bash command — currently not extracted from tool_input |
| `args.pattern` | detail_panel (renderOpRow path field) | ⚠ | Grep/Glob pattern — currently not extracted |
| `duration_ms` | detail_panel (renderOpRow dur field) | ✅ | Computed on tool_end |
| `result` | detail_panel, flow_layout | ✅ | `ok` / `error` |
| `lines_added` | detail_panel (renderDelta) | ❌ | Not yet produced by monitor.py; used for code-change deltas display |
| `lines_removed` | detail_panel (renderDelta) | ❌ | Not yet produced by monitor.py |
| `dir` | (flow_layout overview groups by folder) | ❌ | Directory component of file_path; pre-computing saves JS work |

### Key gap: `args.command` and `args.pattern`
The renderers check `e.args.command` and `e.args.pattern` in `renderOpRow` (detail_panel line 471).
These can be extracted from `tool_input` for Bash/Grep/Glob tools but currently aren't.

---

## Stream 3 — Files (`files-update` / `gmuxtest-files.json`)

| Field | Used in | Status | Notes |
|-------|---------|--------|-------|
| `path` | detail_panel, flow_layout | ✅ | Absolute path |
| `rel_path` | detail_panel, flow_layout | ✅ | Relative path for display |
| `touches_5m` | detail_panel (File panel) | ✅ | 5-minute rolling count |
| `touches_30m` | detail_panel, agent_rail file list | ✅ | 30-minute rolling count |
| `touches_1h` | detail_panel (File panel) | ✅ | 1-hour rolling count |
| `agents` | detail_panel, data.js | ✅ | Panes that touched in last 30m |
| `last_touch_ts` | detail_panel | ✅ | ISO timestamp |
| `last_writer` | detail_panel | ✅ | Pane ID of last write/edit |
| `is_hot` | detail_panel, flow_layout | ✅ | touches_30m ≥ 5 |
| `is_conflict` | detail_panel | ✅ | Multiple agents + recent touches |
| `is_god_node` | detail_panel | ❌ | Requires graphify (out of scope) |
| `callers` | detail_panel | ❌ | Requires graphify (out of scope) |
| `rel_path` directory component | flow_layout (folder grouping) | ⚠ | Works but only correct when rel_path uses `/` separators; absolute-only paths give empty folder trees |

### Rel-path quality gap
`monitor.py`'s `write_files()` sets `rel_path = fp if not fp.startswith("/") else abs_p.split("/")[-1]`.
When `fp` is already absolute (which it sometimes is), `rel_path` becomes just the
filename with no directory prefix — the JS folder-grouping tree then shows no
hierarchy. **Fix:** derive `rel_path` by stripping the pane's `cwd` prefix.

---

## Stream 4 — Memories (`memory-update` / `gmuxtest-memory.json`)

| Field | Used in | Status | Notes |
|-------|---------|--------|-------|
| `id` | data.js | ❌ | Memory aggregator not yet built |
| `type` | (memory tab) | ❌ | |
| `agent_id` | (memory tab) | ❌ | |
| `agent_name` | (memory tab) | ❌ | |
| `title` | (memory tab) | ❌ | |
| `body` | (memory tab) | ❌ | |
| `tags` | (memory tab) | ❌ | |
| `created_at` | (memory tab) | ❌ | |

Memory stream is entirely pending `memory_aggregator.py`.
Dashboard handles empty gracefully (shows "no memories yet").

---

## Summary matrix

| Stream | Total fields used | ✅ live | ⚠ partial | ❌ missing |
|--------|-------------------|---------|-----------|----------|
| agents | 28 | 21 | 5 | 2 |
| activity | 13 | 9 | 3 | 1 (*lines_added/removed not yet producible) |
| files | 12 | 9 | 1 | 2 (graphify-only) |
| memories | 8 | 0 | 0 | 8 (aggregator not built) |

---

## Fields added in this pass (v3.5 → v3.6)

The following gaps were closed by updating `monitor.py`:

1. **`args.command`** — extracted from Bash tool_input
2. **`args.pattern`** — extracted from Grep/Glob tool_input
3. **`rel_path` quality** — now computed by stripping pane CWD prefix
4. **`session_age_s` alias** — `uptime_s` now also emitted as `session_age_s` in pane state
5. **`sub_agents[]` per agent** — populated from `/session` parentID resolution
6. **`last_tool_call_summary`** per agent — most recent tool start as `{tool, file_path, ts}`
7. **`args` enrichment** — Bash commands and Glob/Grep patterns now surfaced

Fields that remain `❌` and are NOT producible without external tools:
- `lines_added` / `lines_removed` — requires diff computation (opencode doesn't expose this in SSE)
- `is_god_node` / `callers` — requires graphify graph analysis
- Memory stream entirely — requires `memory_aggregator.py`

---

## Diagnostic commands

```bash
# Check all four files are being written
ls -la /tmp/gmuxtest-*.json

# Inspect activity feed (last 3 events)
python3 -c "import json; d=json.load(open('/tmp/gmuxtest-activity.json')); [print(e) for e in d[-3:]]"

# Inspect file-touch map (first 3 entries)
python3 -c "import json; d=json.load(open('/tmp/gmuxtest-files.json')); [print(k,v['touches_30m']) for k,v in list(d.items())[:3]]"

# Verify rel_path quality (should be relative, not just filename)
python3 -c "import json; d=json.load(open('/tmp/gmuxtest-files.json')); bad=[v['rel_path'] for v in d.values() if '/' not in v['rel_path']]; print(len(bad),'flat paths out of',len(d),'total')"
```
