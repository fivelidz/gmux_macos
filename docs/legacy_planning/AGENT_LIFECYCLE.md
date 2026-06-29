# Agent Lifecycle & State Management

How v4 handles an AI agent from spawn to death with minimal friction.
Every concern (PTY, status, todos, activity, sub-agents, permissions,
usage) is owned by one Rust process and broadcast via tokio channels.

This is the **single most important doc** for understanding v4's backend.

---

## The agent abstraction

In v3, an "agent" was a fuzzy concept spread across tmux + monitor.py +
opencode SSE + JSON files. In v4 it's a concrete Rust struct:

```rust
pub struct Agent {
    pub id: u32,                          // monotonic, never reused
    pub name: String,                     // user-given, renameable
    pub agent_type: AgentType,            // Claude | OpenCode | Aider | Gemini | Shell
    pub cwd: PathBuf,                     // working directory
    pub model: Option<String>,            // "claude-sonnet-4.5" etc.

    // PTY ownership
    pub session_id: u32,                  // index into ProcessManager
    pub spawned_at: SystemTime,
    pub pid: Option<i32>,                 // child shell PID; updated post-spawn
    pub parent_id: Option<u32>,           // for sub-agents

    // Status — single field, single source of truth
    pub state: AgentState,                // Starting|Working|Idle|NeedsInput|Done|Error|RateLimited
    pub state_changed_at: SystemTime,     // when did we enter current state?
    pub last_line: String,                // last line of terminal output (for grid card preview)

    // Tracked work
    pub todos: Vec<Todo>,                 // current todo list, ordered
    pub current_tool: Option<String>,     // tool the agent is running right now
    pub recent_files: VecDeque<PathBuf>,  // last 20 files this agent touched

    // Counters (cheap to read, updated on events)
    pub tokens_in: u64,
    pub tokens_out: u64,
    pub cost_usd: f64,
    pub tool_calls: u64,
    pub error_count: u32,

    // Permission state (when state == NeedsInput)
    pub pending_permission: Option<Permission>,

    // Rate-limit info
    pub rate_limit_until: Option<SystemTime>,
    pub rate_limit_msg: Option<String>,

    // Sub-agent linkage
    pub sub_agent_ids: Vec<u32>,          // children spawned from this agent
}
```

All agents live in `DashMap<u32, Agent>` registered as Tauri managed state.
Every change to an Agent fires a `agent-update-{id}` event.

---

## AgentState — the state machine

```
       ┌──────────┐
       │ Starting │ ← spawn_agent() just called, PTY opening
       └────┬─────┘
            ▼
       ┌──────────┐
       │  Working │ ← tool is actively running (received tool_start)
       └────┬─────┘
            │
            ├────────────────────┐
            ▼                    ▼
       ┌──────────┐         ┌──────────┐
       │   Idle   │         │NeedsInput│ ← permission_request received
       └────┬─────┘         └────┬─────┘
            │                    │
            │  user types or     │  user clicks approve/reject
            │  agent restarts    │
            ▼                    ▼
       (back to Working)    (back to Working or Idle)


       ┌──────────┐
       │  Error   │ ← agent crashed or non-recoverable
       └──────────┘

       ┌────────────┐
       │RateLimited │ ← 429 detected; auto-exits when rate_limit_until passes
       └──────┬─────┘
              │
              ▼
       (back to Working)

       ┌──────────┐
       │   Done   │ ← user explicitly marked done OR PTY exited cleanly
       └──────────┘
```

Transitions are driven by three sources:

1. **PTY events** — output appears → if recently silent, go Working
2. **opencode SSE** — `tool_start` → Working; `permission_request` → NeedsInput
3. **User actions** — manual rename, kill, mark-done

The state machine is **permissive** — invalid transitions are allowed but
logged. We never panic on an unexpected transition.

---

## Lifecycle phases

### Phase 1: Spawn

```
User clicks "+ new agent" → fills modal → invoke('spawn_agent', ...)
  │
  ▼
core::agent_manager::spawn_agent(SpawnConfig {
    name, agent_type, cwd, model, parent_id: None
})
  │
  ▼
Steps in order, all in one fn:
  1. process_manager.spawn_shell(cwd, env) → session_id (PTY exists)
  2. Build Agent { id: next_id(), state: Starting, … }
  3. agents.insert(id, agent)
  4. emit("agent-update-{id}", &agent)  // UI receives the new agent
  5. Background tokio task: watch_pty_output_for_status(id, session_id)
  6. Background tokio task: poll_opencode_session(id)  if agent_type uses opencode
  7. If parent_id.is_some(): write SubAgentLink, emit("subagent-tree-changed")
  8. If autosave: persist_to_db(&agent)
  9. Return Ok(id)
```

The UI receives the `agent-update` event and renders the new pane immediately.
Time from click to interactive PTY: **< 100ms** target.

### Phase 2: Activity

Every byte from the PTY triggers two things:

1. **Frontend rendering** — emit `pty-output-{session_id}` event, xterm.js writes it
2. **Backend analysis** — the `watch_pty_output_for_status` task:
   - Appends to `agent.last_line` buffer (rolling)
   - Pattern-matches for rate-limit signals
   - Updates `state` if heuristics fire
   - Records `ActivityEvent { ts, agent_id, kind, … }` in the activity log

If the agent has an opencode session, a **separate** background task polls
`/event` SSE for that session:

- `message.part.updated` with `tool_start` → push `ActivityEvent::ToolStart`,
  set `agent.current_tool`, set state Working
- `tool_end` → push `ActivityEvent::ToolEnd`, clear `current_tool`, set state Idle
- `permission_request` → set state NeedsInput, populate `pending_permission`,
  emit `permission-pending-{id}` event
- `todo_update` → replace `agent.todos`, emit `todos-update-{id}` event

### Phase 3: User interaction

| Action | API call | What happens |
|---|---|---|
| Type into pane | `write_stdin(session_id, "...")` | Bytes flow to PTY |
| Approve permission | `approve_permission(agent_id)` | POST opencode `/permission/allow` OR `write_stdin("y\n")` fallback |
| Reject permission | `reject_permission(agent_id)` | Same but `/deny` |
| Rename agent | `rename_agent(agent_id, "...")` | Updates `agent.name`, emit, persist |
| Mark todo done | `set_todo(agent_id, todo_id, done: bool)` | Updates `agent.todos[i].done`, emit, persist |
| Kill agent | `kill_agent(agent_id)` | Calls `process_manager.kill_session()`, sets state Done, persist |

### Phase 4: Sub-agent spawn

```
User right-clicks pane → "Spawn sub-agent" → invoke('spawn_sub_agent', { parent_id, name, … })
  │
  ▼
Same as spawn_agent BUT:
  - parent_id is set
  - parent.sub_agent_ids.push(new_id)
  - SubAgentLink { id, parent_id, spawned_at } written to disk
  - emit("subagent-tree-changed", {parent_id, child_id})
```

The Agent Monitor receives the event, redraws the flowchart with the new edge.

### Phase 5: Termination

```
User clicks kill (or app shutdown, or PTY EOF)
  │
  ▼
core::agent_manager::kill_agent(id)
  Steps:
  1. process_manager.kill_session(session_id)  → SIGTERM, then SIGKILL
  2. If parent_id.is_some():
       parent.sub_agent_ids.retain(|x| x != id)
  3. For child in agent.sub_agent_ids:
       kill_agent(child)  // recursive
  4. agent.state = Done
  5. emit("agent-update-{id}")
  6. persist_to_db (still keep in db but mark as ended)
  7. agents.remove(id) is OPTIONAL — keep in memory for grace period
     so UI can show "exited 3s ago" before disappearing
```

---

## Todos

### Storage

```rust
pub struct Todo {
    pub id: u32,                  // unique per agent
    pub text: String,
    pub done: bool,
    pub created_at: SystemTime,
    pub updated_at: SystemTime,
    pub source: TodoSource,       // Agent | User | Inherited
    pub priority: TodoPriority,   // Low | Med | High
    pub blocked_by: Option<u32>,  // another todo's id (rare)
}
```

### Lifecycle

- **Created** by the agent itself (via opencode `/session/:id/todo` poll),
  by the user (UI), or inherited from a parent during sub-agent spawn
- **Updated** when the agent emits a `todo_update` SSE event OR the user
  ticks the checkbox
- **Deleted** on agent done OR explicit user action

### Persistence

Todos are autosaved to `~/.local/share/gmux/state.db` (SQLite) so they
survive app restarts. On launch, the agent_manager re-loads them as part
of restoring sessions.

### Surface in UI

- **Per-pane sidebar:** small checklist below the pane title
- **Dashboard:** per-agent detail panel has a Todos tab
- **Phone:** todos exposed in the per-agent screen

### Hotkeys

- `T` (when an agent is focused) → quick-add todo from a small text input
- Click a checkbox in the pane to toggle done
- `Cmd/Ctrl+T` → opens a global todo overview

---

## Activity log

Rolling 500-event circular buffer in memory + optional persistence.

```rust
pub enum ActivityKind {
    Spawn { agent_type: AgentType },
    ToolStart { tool: String, args: ToolArgs },
    ToolEnd { tool: String, result: Result, duration_ms: u32 },
    FileTouch { path: PathBuf, kind: TouchKind },   // Read | Write | Edit
    PermissionRequest { detail: String },
    PermissionApproved { method: ApproveMethod },   // Click | Hotkey | Phone
    PermissionRejected,
    RateLimited { until: SystemTime, reason: String },
    Error { msg: String },
    UserInput { bytes: u32 },                       // counts only, not text
    OutputBurst { bytes: u32, lines: u32 },         // periodic summary
    Killed,
}

pub struct ActivityEvent {
    pub id: u64,
    pub ts: SystemTime,
    pub agent_id: u32,
    pub kind: ActivityKind,
}
```

### Subscription pattern

```rust
let mut rx = activity_log.subscribe();   // tokio broadcast Receiver
while let Ok(ev) = rx.recv().await {
    // emit to webview, push to phone, etc.
}
```

The webview receives a `activity-event` Tauri event for each new entry.
The dashboard's flowchart updates its edges. The phone gets the event too.

### Queries

The activity log supports filtering:

- By agent: `log.by_agent(agent_id) -> Vec<ActivityEvent>`
- By kind: `log.by_kind(ActivityKind::FileTouch) -> Vec<...>`
- Time-range: `log.between(start, end) -> Vec<...>`
- Last N: `log.last(20) -> Vec<...>`

Tauri commands `get_activity`, `get_agent_activity`, etc. expose these.

---

## Permissions

When an agent emits a permission request:

```rust
pub struct Permission {
    pub agent_id: u32,
    pub request_id: String,                  // opencode's id
    pub tool: String,                        // "Write", "Bash", etc.
    pub args: ToolArgs,
    pub requested_at: SystemTime,
    pub auto_approve_within_s: Option<u32>,  // if set, auto-allows after timeout
}
```

Stored in `DashMap<u32, Permission>` keyed by `agent_id`. Only one pending
permission per agent at a time. Multiple agents can have pending permissions
concurrently.

User actions:
- `approve_permission(agent_id)` → POST `/permission/allow` or write `y\n`
- `reject_permission(agent_id)` → POST `/permission/deny` or write `n\n`
- `auto_approve_all_for(agent_id, duration)` → adds an auto-approval window
  so a long-running agent can chew through edits without per-edit clicks

When approved/rejected:
1. Send the API call to opencode (with fallback)
2. Remove the entry from `perms`
3. Set `agent.state = Working` (or whatever next state opencode emits)
4. Record an `ActivityEvent::PermissionApproved` / `Rejected`

---

## Rate-limit handling

Three detection signals (carry over from v3.7.0):

### Signal A — opencode error event
`session.error` SSE with text matching `/rate.?limit|429|too many requests|quota/i` →
set `state = RateLimited`, parse `retry-after` if present.

### Signal B — auth.json expiry
Polled separately; if `expires_at - now() < 60s`, set `agent.auth_expiring = true`
on every agent using that provider.

### Signal C — terminal output regex
The PTY watch task checks the last 30 lines for rate-limit phrases as a
fallback when SSE doesn't fire.

When `state = RateLimited` is set:
- Badge appears in the pane (orange clock icon + countdown)
- Activity log records the event
- A tokio task watches `rate_limit_until` and auto-recovers state at expiry
- The Anthropic usage cache is invalidated so the toolbar badge re-fetches

---

## Sub-agent registry

```rust
pub struct SubAgentLink {
    pub child_id: u32,
    pub parent_id: u32,
    pub spawned_at: SystemTime,
    pub agent_type: AgentType,
    pub initial_prompt: Option<String>,   // what the parent asked the child to do
}
```

`DashMap<u32, SubAgentLink>` keyed by child_id. Plus `parent.sub_agent_ids`
on the parent's Agent struct (denormalized for fast lookup).

Persisted to disk so sub-agent relationships survive app restart.

---

## Sessions vs Agents

**Session** = PTY (managed by `ProcessManager`, identified by `u32` index
into a DashMap). One PTY = one shell process + its descendants.

**Agent** = higher-level concept (managed by `AgentManager`). An agent
owns one Session but also has state, todos, activity, parent/child links.

In v3 these were conflated and lived across two processes (Rust + Python).
In v4 they're cleanly separated and both live in Rust. The frontend
mostly sees Agents and rarely cares about Session IDs.

---

## Persistence — SQLite schema

```sql
-- on app startup, run any pending migrations from migrations/ folder

CREATE TABLE agents (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    cwd TEXT NOT NULL,
    model TEXT,
    parent_id INTEGER REFERENCES agents(id),
    state TEXT NOT NULL,
    spawned_at INTEGER NOT NULL,         -- unix ms
    ended_at INTEGER,                    -- unix ms; NULL if alive
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    tool_calls INTEGER DEFAULT 0,
    last_line TEXT
);

CREATE TABLE todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL,
    blocked_by INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,                 -- json blob, type-tagged
    detail TEXT                         -- json blob, kind-specific
);
CREATE INDEX activity_by_agent ON activity_log(agent_id, ts);

CREATE TABLE file_touches (
    agent_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    touched_at INTEGER NOT NULL,
    kind TEXT NOT NULL,                 -- read | write | edit
    PRIMARY KEY (agent_id, file_path, touched_at)
);
CREATE INDEX touches_by_file ON file_touches(file_path);

CREATE TABLE sub_agent_links (
    child_id INTEGER PRIMARY KEY REFERENCES agents(id),
    parent_id INTEGER NOT NULL REFERENCES agents(id),
    spawned_at INTEGER NOT NULL,
    initial_prompt TEXT
);

CREATE TABLE usage_history (
    provider TEXT NOT NULL,
    hour_bucket INTEGER NOT NULL,        -- unix hour (epoch_s / 3600)
    rpm_limit INTEGER, rpm_used INTEGER,
    tpm_in_limit INTEGER, tpm_in_used INTEGER,
    tpm_out_limit INTEGER, tpm_out_used INTEGER,
    PRIMARY KEY (provider, hour_bucket)
);

CREATE TABLE app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL                  -- json blob; flexible kv store
);
```

### Autosave policy
- **Agents:** debounced 500ms write on any field change
- **Todos:** immediate write on toggle / add / delete
- **Activity:** batched every 1s (insert N events at once)
- **File touches:** batched every 5s
- **Usage history:** written when the usage poller has a fresh sample

Concurrent reads while writing are fine — SQLite handles this with WAL.

### On startup
- Open `state.db`, run pending migrations
- For each agent with `ended_at IS NULL`: try to re-attach
  - If the recorded PID is still alive AND we can re-open its PTY → restore
  - Else mark as `ended_at = now()` (we can't recover the PTY across restart;
    this is documented as a v4.0 limitation)
- Load todos, activity (last 500), sub-agent links into memory
- Pull usage_history for the current hour to seed the toolbar

---

## The event bus

Single tokio `broadcast` channel per stream:

```rust
pub struct EventBus {
    agent_updates:   broadcast::Sender<AgentUpdate>,
    activity:        broadcast::Sender<ActivityEvent>,
    todo_updates:    broadcast::Sender<TodoUpdate>,
    permissions:     broadcast::Sender<PermissionEvent>,
    usage_updates:   broadcast::Sender<UsageData>,
    subagent_tree:   broadcast::Sender<SubAgentTreeUpdate>,
}
```

Subscribers:
- **Main window** — listens to all, mutates its DOM
- **Dashboard window** — same, but renders differently (flowchart)
- **Phone bridge** — listens to all, forwards selected updates as WS messages
- **Persistence layer** — listens to all, debounces, writes to SQLite

Adding a new subscriber is just `bus.activity.subscribe()`. No locking,
no shared mutable state, no JSON files.

---

## Tauri commands surface (full list)

```rust
// PTY (low-level — most callers should use the agent commands)
spawn_shell, write_stdin, resize_pty, kill_session, kill_all_sessions,
get_backend_info, check_cli_available

// Agent management (the main API)
spawn_agent, kill_agent, rename_agent, mark_agent_done, list_agents,
get_agent

// Sub-agent
spawn_sub_agent, list_sub_agents, kill_sub_agent_tree

// Todos
add_todo, set_todo_done, delete_todo, list_todos, reorder_todos

// Permissions
approve_permission, reject_permission, list_pending_permissions,
set_auto_approve

// Activity
get_activity, get_agent_activity, get_file_activity

// Files (heatmap)
list_hot_files, get_file_touches

// Usage
get_claude_usage, get_provider_usage, refresh_usage_cache

// Providers / auth (lifted from v3)
check_auth, list_providers, login_provider, logout_provider, list_models

// Windows
open_dashboard, close_dashboard, focus_main

// Headless / phone
start_bridge, stop_bridge, pair_phone, revoke_phone_token, list_phones

// Persistence
backup_state, restore_state, export_session
```

Every command takes `State<EventBus>` + relevant managers via Tauri's
managed state. Most are async to allow background tokio work.

---

## What this design buys us

| Problem in v3 | Solution in v4 |
|---|---|
| Two monitor.py processes racing on JSON files | Single Rust state store, atomic DashMap ops |
| State scattered across `/tmp/gmuxtest-*.json` | One SQLite DB, one in-memory store |
| Agent status delayed 2-5s by polling | Event-driven, <50ms |
| Tmux + opencode + Python interaction bugs | One process owns the PTY + the SSE + the state |
| "Why is the dashboard showing different state than the main UI?" | Same in-process store; both windows subscribe |
| Cross-platform PTY hell | portable-pty handles Linux/Mac/Win uniformly |
| `nohup` vs `setsid` confusion on different VMs | No external Python daemon to keep alive |
| Tracking todos manually in a markdown file | First-class struct, persisted, queryable |
| Activity tracking via tail-parsing terminal text | Event-driven with typed enums |

---

## Open questions

1. **Persistent sessions across app restart**
   PTYs die when the Tauri process exits. We can't keep them alive
   across restarts without something like tmux underneath. Trade-off:
   either accept this (v4.0.0 decision), or add an optional tmux
   backend later (post-v4.0).

2. **SQLite vs append-only log file**
   SQLite has more overhead but easier querying. An append-only
   line-delimited JSON file is simpler but slower for queries. Going
   with SQLite given Rust's `rusqlite` is mature and zero-config.

3. **Should activity events emit to UI per-event or batched?**
   Per-event keeps the UI live; batched (every 100ms) saves IPC.
   Compromise: 16ms batching (same pattern as PTY output).

4. **How long do we keep ended agents in memory?**
   60-second grace period after kill, then evict. Still in SQLite
   for history queries.

5. **Should the activity log have a maximum disk size?**
   Yes — rotate / cap at 100,000 events on disk (about 100MB worst case).
   Older events are archived or dropped.
