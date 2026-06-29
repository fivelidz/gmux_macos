# gmux MCP Server

A **dependency-free** Python 3.11 MCP (Model Context Protocol) stdio server that lets AI agents running inside gmux panes control gmux itself — inspecting other panes, spawning sub-agents, sending text/keys, and responding to permission prompts.

## How it works

```
AI Agent (opencode / claude code)
        │ JSON-RPC 2.0 over stdin/stdout
        ▼
  gmux_mcp.py  (this file, MCP "2024-11-05")
   ├── read ops  ──► monitor  http://127.0.0.1:8769  (no auth)
   └── write ops ──► bridge   http://127.0.0.1:6302  (Bearer token)
```

### Services

| Service | Port | Auth | Purpose |
|---------|------|------|---------|
| **monitor** (`backend/status/monitor.py`) | 8769 | none | Read-only pane state, chat history, todos |
| **bridge** (`gmux_phone_bridge_system/bridge/bridge.py`) | 6302 | Bearer token | Write ops: spawn agents, send text/keys, permission responses |

### Auth tokens

Tokens live in `~/.config/gmux/auth_tokens.json`:
```json
{"tokens": [{"token": "abc123...", "name": "device-name", "created": 123, "last_seen": 456}]}
```
The server loads the **first token with a non-null `last_seen`** (most recently active). All 9 tools work when the monitor is up; the 6 write tools additionally require the bridge to be running and a token to be present.

### Bridge not running?

Start it with:
```bash
cd /home/fivelidz/projects/gmux_v4/gmux_phone_bridge_system/bridge
bash start_bridge.sh
```

Write tools (`gmux_spawn_agent`, `gmux_spawn_sub_agent`, `gmux_send_text`, `gmux_send_key`, `gmux_respond_permission`) will return a clear error if the bridge is down. Read tools (`gmux_health`, `gmux_list_panes`, `gmux_pane_messages`, `gmux_pane_todos`) continue to work as long as the monitor is up.

---

## Tools

### Read-only (monitor on :8769, no auth required)

| Tool | Description |
|------|-------------|
| `gmux_health` | Diagnostic: monitor reachability, bridge reachability, token presence |
| `gmux_list_panes` | Compact summary of all tracked tmux panes (pane_id, session, window, state, model, cwd, has_ai, is_v4, todos) |
| `gmux_pane_messages(pane_id, limit=10)` | Chat message history for a pane (proxied from the opencode/qalcode API) |
| `gmux_pane_todos(pane_id)` | Todo list for a pane |

### Write ops (bridge on :6302, Bearer token required)

| Tool | Description |
|------|-------------|
| `gmux_spawn_agent(name, directory, agent_type='opencode', session=None)` | Spawn a new agent pane. Returns `{ok, pane_id}`. |
| `gmux_spawn_sub_agent(parent_pane_id, name, directory, agent_type='opencode')` | Spawn a sub-agent and write a parent-pointer record to `/tmp/gmuxtest-sub-agents.json` (matches the Rust `spawn_sub_agent_v4` schema so the UI flowchart can visualise parent→child). |
| `gmux_send_text(pane_id, text)` | Send text to a pane (like typing). |
| `gmux_send_key(pane_id, key)` | Send a single keystroke. Allowed: `C-c`, `Enter`, `Escape`, `Down`, `Up`, `n`, `y`. |
| `gmux_respond_permission(pane_id, approve: bool)` | Approve or reject a pending permission prompt. |

### agent_type values

`opencode` (default), `claude`, `aider`, `terminal`

---

## Self-test

```bash
python3.11 /home/fivelidz/projects/gmux_v4/backend/mcp/test_mcp.py
```

Exits 0 if all pass. The test performs the full MCP handshake + calls `gmux_health` and `gmux_list_panes` against the live monitor on :8769. Bridge-down is warned but not a failure.

---

## Registration snippets

### opencode / qalcode (global config)

Add to `~/.config/opencode/opencode.jsonc` inside the `"mcp"` block:

```jsonc
"mcp": {
  // ... existing entries ...

  "gmux": {
    "type":    "local",
    "command": ["python3.11", "/home/fivelidz/projects/gmux_v4/backend/mcp/gmux_mcp.py"],
    "enabled": true,
    "timeout": 15000
  }
}
```

Or per-project, create/edit `.opencode/config.json` in the project root:
```json
{
  "mcp": {
    "gmux": {
      "type":    "local",
      "command": ["python3.11", "/home/fivelidz/projects/gmux_v4/backend/mcp/gmux_mcp.py"],
      "enabled": true,
      "timeout": 15000
    }
  }
}
```

### Claude Code (claude code CLI)

```bash
claude mcp add gmux -- python3.11 /home/fivelidz/projects/gmux_v4/backend/mcp/gmux_mcp.py
```

Or manually add to `~/.claude/claude_desktop_config.json` → `"mcpServers"`:
```json
{
  "mcpServers": {
    "gmux": {
      "command": "python3.11",
      "args": ["/home/fivelidz/projects/gmux_v4/backend/mcp/gmux_mcp.py"]
    }
  }
}
```

### Cursor / VS Code (MCP extension)

```json
{
  "mcp": {
    "servers": {
      "gmux": {
        "command": "python3.11",
        "args": ["/home/fivelidz/projects/gmux_v4/backend/mcp/gmux_mcp.py"]
      }
    }
  }
}
```

---

## Sub-agent parent linkage

`gmux_spawn_sub_agent` writes to `/tmp/gmuxtest-sub-agents.json` using the same atomic-rename pattern and record schema as the Rust `spawn_sub_agent_v4` function in `app/src-tauri/src/lib.rs`:

```json
{
  "parentwindow+childname": {
    "parent_pane_id": "%5",
    "parent_name":    "parentwindow",
    "spawned_at":     1718000000000,
    "agent_type":     "opencode",
    "model":          ""
  }
}
```

The UI flowchart reads this file and resolves `window_name → pane_id` on the next monitor poll.

---

## Files

```
backend/mcp/
├── gmux_mcp.py    — the MCP server (stdlib only, no pip installs)
├── test_mcp.py    — self-test (run directly with python3.11)
└── README.md      — this file
```
