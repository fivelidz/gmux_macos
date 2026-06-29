# gmux HTTP API (alpha.22)

The gmux desktop app embeds a small HTTP API so **other apps and agents** can
query gmux state and control its agents — over plain HTTP, seeing the live v4
PTY agents the app owns directly (no tmux, no Python bridge required).

- **Base URL:** `http://127.0.0.1:6310`
- **Starts automatically** when the gmux desktop app launches.
- **Implemented in:** `app/src-tauri/src/api.rs` (axum).

## Configuration (env vars)

| Var | Default | Meaning |
|---|---|---|
| `GMUX_API_PORT` | `6310` | Port to listen on |
| `GMUX_API_BIND` | `127.0.0.1` | Bind address. Set `0.0.0.0` to expose on the LAN — **only behind Tailscale/VPN**; control routes still require a token |
| `GMUX_API_REQUIRE_AUTH` | _(unset)_ | Set to `1` to require a Bearer token for **read** routes too (by default reads are open on localhost) |

## Auth

Uses the **same token store** as the phone bridge and desktop pairing:
`~/.config/gmux/auth_tokens.json`. Pair a device in gmux **Options → Phone**
to mint a token, or any token already in that file works.

- **Read** routes (`GET`) — open on localhost by default.
- **Control** routes (`POST`) — **always** require
  `Authorization: Bearer <token>`.

```
{ "tokens": [ { "token": "<64 hex>", "name": "...", "created": 0, "last_seen": null } ] }
```

## Agent id (`:id`)

Control routes act on **v4 PTY agents** by session id. Accepts `12` or `v4-12`.
Read routes (`/api/agent/:id`) also accept any `pane_id` (URL-encode `%`, e.g.
`%251` for pane `%1`).

---

## Endpoints

### `GET /api/health`
```json
{ "ok": true, "service": "gmux-api", "version": "0.1.0", "v4_agents": 3 }
```

### `GET /api/state`
Full merged pane-state JSON (the same object the UI renders — file/tmux panes
**plus** live v4 PTY agents), keyed by `pane_id`. See
`agent-monitor/docs/BACKEND_CONTRACT.md` for the per-pane field schema
(`window_name, state, session_name, cwd, model, token_in/out, ram_mb, cpu_pct,
todos, tool_history, v4_session_id, …`).

### `GET /api/agents`
Compact list for quick polling.
```json
{ "ok": true, "count": 12, "agents": [
  { "pane_id": "%1", "window_name": "4chan_scrape_data_analysis",
    "session_name": "chanalyse", "state": "working", "agent_type": "opencode",
    "model": "claude-opus-4-8", "cwd": "/home/…", "is_v4": null,
    "v4_session_id": null, "todo_done": 0, "todo_total": 6 } ] }
```

### `GET /api/agent/:id`
One pane's full record. `{ "ok": true, "agent": { …full PaneInfo… } }` or `404`.

### `GET /api/usage`
Live Claude usage (subscription OAuth).
```json
{ "ok": true, "usage": {
  "sessionPercent": 14.0, "sessionResetsAt": "2026-06-16T04:00:00Z",
  "weeklyPercent": 80.0,  "weeklySonnetPercent": 3.0, "weeklyOpusPercent": 0.0,
  "needsAuth": false, "errorMessage": null } }
```

### `POST /api/agent/spawn`  🔒
Spawn a new v4 PTY agent.
```jsonc
// body
{ "directory": "/home/me/projects/x",   // required
  "agent_type": "qalcode",              // qalcode|claude|opencode|aider|terminal (default qalcode)
  "model": "opus",                      // optional
  "permission_mode": "safe",            // safe|restricted|extreme (default safe)
  "prompt": "Read the README and summarise it" }  // optional first message
// response
{ "ok": true, "session_id": 12, "pane_id": "v4-12" }
```

### `POST /api/agent/:id/send`  🔒
Write text + Enter into the agent's terminal.
```json
{ "text": "continue with the next task" }   →   { "ok": true }
```

### `POST /api/agent/:id/key`  🔒
Send a control key. `key` ∈ `Enter | Escape | C-c | Up | Down | y | n`.
```json
{ "key": "Escape" }   →   { "ok": true }
```

### `POST /api/agent/:id/kill`  🔒
Terminate the agent's PTY. `{ "ok": true }`

---

## Examples

```bash
# read (no token needed on localhost)
curl http://127.0.0.1:6310/api/health
curl http://127.0.0.1:6310/api/agents
curl http://127.0.0.1:6310/api/usage

# control (token required)
TOK=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/gmux/auth_tokens.json')))['tokens'][0]['token'])")

# spawn an agent that reads a repo and reports back
curl -X POST http://127.0.0.1:6310/api/agent/spawn \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"directory":"~/projects/x","agent_type":"qalcode","prompt":"audit the codebase"}'

# nudge an agent to continue
curl -X POST http://127.0.0.1:6310/api/agent/12/send \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"text":"continue"}'

# stop / kill
curl -X POST http://127.0.0.1:6310/api/agent/12/key  -H "Authorization: Bearer $TOK" -d '{"key":"C-c"}'
curl -X POST http://127.0.0.1:6310/api/agent/12/kill -H "Authorization: Bearer $TOK"
```

---

## How this relates to the other gmux surfaces

| Surface | Port | Role |
|---|---|---|
| **gmux HTTP API** (this doc) | `:6310` | **Public read+control for apps/agents**, in-process, sees v4 PTY agents, no tmux |
| monitor.py state server | `:8769` | Internal read-only feed (SSE), data source |
| phone bridge | `:6301/:6302` | Phone app read+control (tmux path) |
| MCP server | stdio | LLM-agent tools (proxies the above) |

For LLM agents embedded in a CLI, the MCP server (`backend/mcp/gmux_mcp.py`) is
still the idiomatic path. For arbitrary apps/scripts/webhooks, use this HTTP API.

## Status / roadmap
- ✅ Read: health, state, agents, agent, usage
- ✅ Control: spawn, send, key, kill (v4 PTY agents)
- 🔜 SSE stream endpoint (`GET /api/stream`) for push updates
- 🔜 Supervisor/governor introspection (`GET /api/governor`)
- 🔜 Control of tmux/file-backed (non-v4) panes via the bridge
