# gmux Sub-Agent System — v3.7

**Date:** 2026-05-13
**Status:** Implemented

---

## Overview

gmux v3.7 introduces **first-class sub-agent panes**: a parent agent can
spawn a child agent that appears as a separate, visible tmux window — with
its own pane card in the UI, its own kill button, and a parent→child
relationship rendered in the dashboard flowchart.

This is distinct from the **opencode-internal Task-tool sub-agents** that
have always existed (since v3.5). Both systems are designed to coexist.

---

## The Two Sub-Agent Systems

### 1. opencode-internal Task sub-agents (intra-session, invisible)

When an opencode/claude session uses the `Task` tool to spawn a sub-agent,
opencode creates a child session **inside the same bun process**. These
child sessions:

- Live inside the same tmux pane as the parent
- Are invisible to the user (no separate pane)
- Cannot be killed independently (killing the pane kills everything)
- Show up in the API: `GET /session` returns sessions with a `parentID` field
- Are tracked by monitor.py via `get_child_session_ids()` and merged into
  the parent pane's `sub_agents[]` array in the state JSON

This system continues to work unchanged in v3.7.

### 2. gmux-spawned sub-agents (separate pane, first-class — v3.7 new)

When the user selects a parent agent and spawns a sub-agent via the UI
(or via the `spawn_sub_agent` Rust command), gmux creates a **new tmux
window** in the same session. These panes:

- Are fully visible as separate pane cards in the main UI
- Can be focused, switched to, killed independently via tmux
- Have their name formatted as `<parent_name>+<sub_name>`
- Carry a `parent_pane_id` field in the state JSON
- Have `is_child_pane: true` set in the state JSON
- Are rendered as sub-nodes in the dashboard flowchart

---

## How Parent-Pointer Records Work

### Step 1: spawn_sub_agent (Rust, lib.rs)

When the UI calls `invoke('spawn_sub_agent', {...})`:

1. Sends `prefix+c` to open a new tmux window in the current session
2. Runs `cd <directory> && <agent-cmd>` in the new window
3. Renames the window to `<parent_name>+<name>`
4. Locks `automatic-rename off` so tmux doesn't clobber the name
5. Writes a parent-pointer record to `/tmp/gmuxtest-sub-agents.json`:

```json
{
  "parent+sub-name": {
    "parent_pane_id": "%42",
    "spawned_at": 1747123456789,
    "agent_type": "claude",
    "model": "claude-sonnet-4-5"
  }
}
```

The key is the window_name (not pane_id) because pane_id is not known
until monitor.py assigns it on the next tmux poll.

### Step 2: monitor.py merges on each poll cycle

On each tmux poll:

1. `poll_tmux()` runs and populates `_pane_to_name` (pane_id → window_name)
2. `_load_spawned_sub_agents()` reads `/tmp/gmuxtest-sub-agents.json` and
   resolves window_name keys → pane_ids using the reverse of `_pane_to_name`
3. `write_state()` merges the parent-pointer into each matching pane's dict:
   ```json
   {
     "parent_pane_id": "%42",
     "is_child_pane": true,
     "spawned_agent_type": "claude",
     "spawned_model": "claude-sonnet-4-5",
     "spawned_at_ms": 1747123456789
   }
   ```
4. The pane's existing `sub_agents[]` (opencode Task sub-agents) is unaffected

### Step 3: Dashboard renders the hierarchy

The dashboard's `SUBAGENTS.childrenOf(pane)` (subagents.js) now merges:
- Backend-driven: scans `DATA.agents` for panes with `is_child_pane: true`
  and `parent_pane_id === pane`
- localStorage: manual user groupings (pre-v3.7 compat, unchanged)

`app.js` calls `SUBAGENTS.childrenOf(watched)` and passes the result to
`LAYOUT.buildSingleAgent(watched, subPanes)`, which renders each sub-pane
as a `subagent` node connected to the parent agent node.

---

## UI — How to Spawn a Sub-Agent

### Method 1: New Agent modal

1. Press `n` to open the New Agent modal
2. Configure name, directory, agent type, model as usual
3. Select a parent from the **Parent agent** dropdown (lists all panes with
   `has_ai: true`)
4. Click Create — the sub-agent window opens and the dashboard picks it up
   within ~2s

### Method 2: Shift+N hotkey

Press `Shift+N` while a pane is selected — opens the New Agent modal with
that pane pre-selected as the parent. Useful for quickly spawning a sub-agent
under the currently-focused agent without touching the mouse.

---

## Migration Notes

- **Existing opencode Task sub-agents** continue to work unchanged. Their
  `sub_agents[]` array on the parent pane is populated by the existing
  `get_child_session_ids()` logic in monitor.py and displayed in the dashboard.
- **Existing localStorage groupings** (manual user-set parent→child from
  pre-v3.7) continue to work as before. The `SUBAGENTS` module merges both.
- The new `parent_pane_id` / `is_child_pane` fields are `setdefault`'d to
  `""` / `false` for all panes where they don't apply, so no downstream JSON
  consumers break.

---

## Data Contracts

### New fields on agent pane state dict (monitor.py → gmuxtest-pane-state.json)

| Field | Type | Description |
|-------|------|-------------|
| `parent_pane_id` | `str` | Parent pane_id if this is a gmux-spawned sub-agent; `""` otherwise |
| `is_child_pane` | `bool` | `true` when this pane was spawned via spawn_sub_agent |
| `spawned_agent_type` | `str` | Agent type passed at spawn time ("claude", "opencode", etc.) |
| `spawned_model` | `str` | Model passed at spawn time |
| `spawned_at_ms` | `int` | Epoch milliseconds when the pane was spawned |

### Intermediate file: /tmp/gmuxtest-sub-agents.json

Written by the Rust `spawn_sub_agent` command. Keyed by window_name.
Consumed by `_load_spawned_sub_agents()` in monitor.py on every poll cycle.

### Rust command: spawn_sub_agent

Tauri command registered in `app/src-tauri/src/lib.rs`.

```
invoke('spawn_sub_agent', {
  parentPaneId: string,   // pane_id of the parent agent
  parentName: string,     // window_name of the parent (for naming)
  name: string,           // short name of the new sub-agent
  directory: string,      // working directory (absolute path)
  agentType: string,      // "qalcode"|"claude"|"opencode"|"aider"|"terminal"
  model: string,          // model ID or ""
})
// Returns: Ok("spawned: <win_name> in <dir>")
```

---

## Future Enhancements

- **Kill-with-parent**: When the parent pane is killed, offer to kill all
  its gmux-spawned children. Requires a dedicated `kill_sub_agents(parent_pane_id)`
  Rust command that scans the sub-agents JSON and sends `tmux kill-window` for
  each matching window.

- **Follow-mode**: When the user clicks a parent agent, automatically show
  the first active child pane in a split or secondary view.

- **Broadcast-to-children**: Send a message to all child agents simultaneously
  via `send_to_agent`. Useful for coordinating parallel work on the same codebase.

- **Cascade renaming**: If the parent is renamed, offer to rename its children
  (strip old prefix, add new one).

- **Sub-agent depth limit**: Prevent infinite spawn chains. Monitor.py could
  warn if `is_child_pane` is set and the pane's own window_name contains `+`
  more than N times.

- **Persist across restarts**: Currently the sub-agents JSON is in /tmp and
  is lost on reboot. session_restore.py could back it up alongside the window
  names cache.
