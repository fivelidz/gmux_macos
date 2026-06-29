#!/usr/bin/env python3.11
"""
gmux MCP stdio server — lets AI agents control gmux from inside a pane.

Protocol: JSON-RPC 2.0 over stdin/stdout, MCP spec "2024-11-05".
Deps: stdlib only (urllib, json, sys, os, threading).
Logging: stderr only — stdout is the protocol channel.

Endpoints consumed:
  Monitor (read-only, no auth): http://127.0.0.1:8769
    GET /api/state
    GET /api/pane/<id>/messages?limit=N
    GET /api/pane/<id>/todos
    GET /health

  Bridge (write ops, Bearer token): http://127.0.0.1:6302
    GET  /api/status
    POST /api/spawn_agent
    POST /api/send_text
    POST /api/send_key
    POST /api/permission_response

Token source: ~/.config/gmux/auth_tokens.json  {tokens:[{token,name,...},...]}
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

MONITOR_BASE = "http://127.0.0.1:8769"
BRIDGE_BASE = "http://127.0.0.1:6302"
TOKEN_FILE = os.path.expanduser("~/.config/gmux/auth_tokens.json")
SA_JSON_PATH = "/tmp/gmuxtest-sub-agents.json"
HTTP_TIMEOUT = 5  # seconds — all HTTP calls
MCP_VERSION = "2024-11-05"
SERVER_NAME = "gmux-mcp"
SERVER_VER = "1.0.0"

ALLOWED_KEYS = {"Escape", "C-c", "Enter", "Up", "Down", "y", "n"}

# ──────────────────────────────────────────────────────────────────────────────
# Logging helpers (stderr only)
# ──────────────────────────────────────────────────────────────────────────────


def _log(msg: str) -> None:
    print(f"[gmux-mcp] {msg}", file=sys.stderr, flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Token loading
# ──────────────────────────────────────────────────────────────────────────────


def _load_token() -> str | None:
    """
    Return the first usable token from TOKEN_FILE.
    Tokens are trusted in order; prefer last_seen != null (active devices).
    Returns None if file is missing, unreadable, or empty.
    """
    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        tokens = data.get("tokens", [])
        if not tokens:
            return None
        # Prefer a token that has been seen recently; fall back to first.
        for t in tokens:
            if t.get("last_seen") is not None:
                return t["token"]
        return tokens[0]["token"]
    except Exception as e:
        _log(f"WARNING: cannot load token from {TOKEN_FILE}: {e}")
        return None


_TOKEN: str | None = _load_token()

# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────


def _http_get(url: str, auth: bool = False) -> dict:
    req = urllib.request.Request(url)
    if auth and _TOKEN:
        req.add_header("Authorization", f"Bearer {_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read().decode(errors="replace").strip()
        # Some endpoints return plain text (e.g. monitor /health returns "ok")
        if raw.startswith("{") or raw.startswith("["):
            return json.loads(raw)
        # Plain text — wrap in a dict so callers always get a dict
        return {"_text": raw, "ok": raw == "ok"}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"GET {url} failed: {e}") from e


def _http_post(url: str, payload: dict, auth: bool = True) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Content-Length", str(len(body)))
    if auth and _TOKEN:
        req.add_header("Authorization", f"Bearer {_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body_text}") from e
    except Exception as e:
        raise RuntimeError(f"POST {url} failed: {e}") from e


# ──────────────────────────────────────────────────────────────────────────────
# Sub-agent JSON file helpers
# ──────────────────────────────────────────────────────────────────────────────

_sa_lock = threading.Lock()


def _write_sub_agent_record(win_name: str, record: dict) -> None:
    """
    Atomically append a parent-pointer record to /tmp/gmuxtest-sub-agents.json.
    The file is a JSON object keyed by window_name (same as Rust code).
    """
    with _sa_lock:
        try:
            try:
                with open(SA_JSON_PATH, "r") as f:
                    mapping = json.load(f)
            except Exception:
                mapping = {}
            if not isinstance(mapping, dict):
                mapping = {}
            mapping[win_name] = record
            tmp = SA_JSON_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(mapping, f, indent=2)
            os.replace(tmp, SA_JSON_PATH)
        except Exception as e:
            _log(f"WARNING: failed to write sub-agent record: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────────────────────────────────────


def tool_gmux_health(args: dict) -> dict:
    """Check monitor + bridge reachability and token presence."""
    result = {
        "monitor_url": MONITOR_BASE,
        "bridge_url": BRIDGE_BASE,
        "token_file": TOKEN_FILE,
        "token_loaded": _TOKEN is not None,
        "token_preview": (_TOKEN[:8] + "…") if _TOKEN else None,
    }

    # Monitor
    try:
        data = _http_get(f"{MONITOR_BASE}/health")
        result["monitor_up"] = True
        result["monitor_detail"] = data
    except Exception as e:
        result["monitor_up"] = False
        result["monitor_error"] = str(e)

    # Bridge
    if _TOKEN:
        try:
            data = _http_get(f"{BRIDGE_BASE}/api/status", auth=True)
            result["bridge_up"] = True
            result["bridge_detail"] = data
        except Exception as e:
            result["bridge_up"] = False
            result["bridge_error"] = str(e)
    else:
        result["bridge_up"] = False
        result["bridge_error"] = "no token — write ops unavailable"

    return result


def tool_gmux_list_panes(args: dict) -> list:
    """Return a compact per-pane summary from the monitor."""
    state = _http_get(f"{MONITOR_BASE}/api/state")
    panes = []
    for pane_id, pane in state.items():
        panes.append(
            {
                "pane_id": pane_id,
                "session_name": pane.get("session_name"),
                "window_name": pane.get("window_name"),
                "state": pane.get("state"),
                "model": pane.get("model"),
                "cwd": pane.get("cwd"),
                "has_ai": pane.get("has_ai", False),
                "is_v4": pane.get("is_v4", False),
                "foreground_cmd": pane.get("foreground_cmd"),
                "todo_done": pane.get("todo_done", 0),
                "todo_total": pane.get("todo_total", 0),
            }
        )
    return panes


def tool_gmux_pane_messages(args: dict) -> dict:
    """Return chat message history for a pane."""
    pane_id = str(args.get("pane_id", "")).strip()
    if not pane_id:
        raise ValueError("pane_id is required")
    limit = int(args.get("limit", 10))
    encoded_id = urllib.parse.quote(pane_id, safe="")
    url = f"{MONITOR_BASE}/api/pane/{encoded_id}/messages?limit={limit}"
    return _http_get(url)


def tool_gmux_pane_todos(args: dict) -> dict:
    """Return todos for a pane."""
    pane_id = str(args.get("pane_id", "")).strip()
    if not pane_id:
        raise ValueError("pane_id is required")
    encoded_id = urllib.parse.quote(pane_id, safe="")
    url = f"{MONITOR_BASE}/api/pane/{encoded_id}/todos"
    return _http_get(url)


def _require_bridge() -> None:
    if not _TOKEN:
        raise RuntimeError(
            f"No auth token available — write ops disabled. "
            f"Add a token to {TOKEN_FILE} and restart the server."
        )


def tool_gmux_spawn_agent(args: dict) -> dict:
    """Spawn a new agent pane via the bridge."""
    _require_bridge()
    name = str(args.get("name", "agent")).strip()
    directory = str(args.get("directory", "")).strip()
    agent_type = str(args.get("agent_type", "opencode")).strip()
    session = args.get("session")

    if not directory:
        raise ValueError("directory is required")

    payload: dict = {
        "name": name,
        "agent_type": agent_type,
        "cwd": directory,
    }
    if session:
        payload["session_id"] = session

    return _http_post(f"{BRIDGE_BASE}/api/spawn_agent", payload)


def tool_gmux_spawn_sub_agent(args: dict) -> dict:
    """
    Spawn a sub-agent via the bridge, then write a parent-pointer record to
    /tmp/gmuxtest-sub-agents.json replicating the Rust spawn_sub_agent_v4 schema.
    """
    _require_bridge()
    parent_pane_id = str(args.get("parent_pane_id", "")).strip()
    name = str(args.get("name", "agent")).strip()
    directory = str(args.get("directory", "")).strip()
    agent_type = str(args.get("agent_type", "opencode")).strip()

    if not parent_pane_id:
        raise ValueError("parent_pane_id is required")
    if not directory:
        raise ValueError("directory is required")

    # Derive the parent_name from the monitor so the window_name matches
    # the Rust pattern "parent_name+child_name".
    parent_name = parent_pane_id  # fallback
    try:
        state = _http_get(f"{MONITOR_BASE}/api/state")
        if parent_pane_id in state:
            parent_name = state[parent_pane_id].get("window_name", parent_pane_id)
    except Exception:
        pass  # use fallback

    win_name = f"{parent_name}+{name}"

    payload: dict = {
        "name": win_name,
        "agent_type": agent_type,
        "cwd": directory,
    }
    resp = _http_post(f"{BRIDGE_BASE}/api/spawn_agent", payload)

    # Write parent-pointer record — same shape as spawn_sub_agent_v4 in lib.rs
    now_ms = int(time.time() * 1000)
    _write_sub_agent_record(
        win_name,
        {
            "parent_pane_id": parent_pane_id,
            "parent_name": parent_name,
            "spawned_at": now_ms,
            "agent_type": agent_type,
            "model": "",  # not known at spawn time from Python
        },
    )

    resp["win_name"] = win_name
    resp["sub_agent_record"] = "written"
    return resp


def tool_gmux_send_text(args: dict) -> dict:
    """Send text to a pane via the bridge."""
    _require_bridge()
    pane_id = str(args.get("pane_id", "")).strip()
    text = str(args.get("text", ""))
    if not pane_id:
        raise ValueError("pane_id is required")
    return _http_post(
        f"{BRIDGE_BASE}/api/send_text",
        {
            "pane_id": pane_id,
            "text": text,
        },
    )


def tool_gmux_send_key(args: dict) -> dict:
    """Send a keystroke to a pane (allowed: Escape, C-c, Enter, Up, Down, y, n)."""
    _require_bridge()
    pane_id = str(args.get("pane_id", "")).strip()
    key = str(args.get("key", "Enter")).strip()
    if not pane_id:
        raise ValueError("pane_id is required")
    if key not in ALLOWED_KEYS:
        raise ValueError(f"key must be one of {sorted(ALLOWED_KEYS)}, got {key!r}")
    return _http_post(
        f"{BRIDGE_BASE}/api/send_key",
        {
            "pane_id": pane_id,
            "key": key,
        },
    )


def tool_gmux_respond_permission(args: dict) -> dict:
    """Respond to a permission prompt in a pane (approve=True/False)."""
    _require_bridge()
    pane_id = str(args.get("pane_id", "")).strip()
    approve = bool(args.get("approve", False))
    if not pane_id:
        raise ValueError("pane_id is required")
    # Bridge uses resp="approve"/"reject"
    return _http_post(
        f"{BRIDGE_BASE}/api/permission_response",
        {
            "pane_id": pane_id,
            "resp": "approve" if approve else "reject",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tool registry
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "gmux_health",
        "description": (
            "Check the health of gmux services: monitor (read-only state server on :8769) "
            "and bridge (write-ops server on :6302). Returns a diagnostic dict including "
            "token presence, reachability, and any error messages."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "gmux_list_panes",
        "description": (
            "List all active tmux panes tracked by gmux. Returns compact summary per pane: "
            "pane_id, session_name, window_name, state, model, cwd, has_ai, is_v4, "
            "foreground_cmd, todo_done, todo_total."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "gmux_pane_messages",
        "description": (
            "Retrieve the AI chat message history for a specific pane. "
            "Returns the raw session data proxied from the opencode/qalcode API."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pane_id": {
                    "type": "string",
                    "description": "The pane identifier, e.g. '%2' or 'chanalyse:%2'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default 10).",
                    "default": 10,
                },
            },
            "required": ["pane_id"],
        },
    },
    {
        "name": "gmux_pane_todos",
        "description": "Return the todo list for a specific pane.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pane_id": {
                    "type": "string",
                    "description": "The pane identifier.",
                },
            },
            "required": ["pane_id"],
        },
    },
    {
        "name": "gmux_spawn_agent",
        "description": (
            "Spawn a new AI agent pane in gmux. Requires bridge to be running and a valid token. "
            "Returns {ok, pane_id} on success."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Window/pane name for the new agent.",
                },
                "directory": {
                    "type": "string",
                    "description": "Working directory for the new agent (absolute path).",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Agent type: opencode, claude, aider, terminal (default: opencode).",
                    "default": "opencode",
                },
                "session": {
                    "type": "string",
                    "description": "tmux session name to spawn into (optional, defaults to 'gmux').",
                },
            },
            "required": ["name", "directory"],
        },
    },
    {
        "name": "gmux_spawn_sub_agent",
        "description": (
            "Spawn a sub-agent that is a child of the calling pane. "
            "Creates the agent via the bridge AND writes a parent-pointer record to "
            "/tmp/gmuxtest-sub-agents.json (matching the Rust spawn_sub_agent_v4 schema) "
            "so the UI flowchart can visualise the parent-child relationship. "
            "Requires bridge to be running and a valid token."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_pane_id": {
                    "type": "string",
                    "description": "The pane_id of the spawning (parent) agent, e.g. '%2'.",
                },
                "name": {
                    "type": "string",
                    "description": "Short name for the sub-agent (window will be 'parentname+name').",
                },
                "directory": {
                    "type": "string",
                    "description": "Working directory for the sub-agent (absolute path).",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Agent type: opencode, claude, aider, terminal (default: opencode).",
                    "default": "opencode",
                },
            },
            "required": ["parent_pane_id", "name", "directory"],
        },
    },
    {
        "name": "gmux_send_text",
        "description": (
            "Send a text string to a pane via the bridge (like typing). "
            "Useful for submitting prompts or commands to an agent. "
            "Requires bridge + token."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pane_id": {
                    "type": "string",
                    "description": "Target pane identifier.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to send to the pane.",
                },
            },
            "required": ["pane_id", "text"],
        },
    },
    {
        "name": "gmux_send_key",
        "description": (
            "Send a single keystroke to a pane. "
            f"Allowed keys: {sorted(ALLOWED_KEYS)}. "
            "Requires bridge + token."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pane_id": {
                    "type": "string",
                    "description": "Target pane identifier.",
                },
                "key": {
                    "type": "string",
                    "description": f"Key to send. Must be one of: {sorted(ALLOWED_KEYS)}.",
                    "enum": sorted(ALLOWED_KEYS),
                },
            },
            "required": ["pane_id", "key"],
        },
    },
    {
        "name": "gmux_respond_permission",
        "description": (
            "Respond to a permission prompt shown in a pane (approve or deny). "
            "Requires bridge + token."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pane_id": {
                    "type": "string",
                    "description": "Pane with the pending permission prompt.",
                },
                "approve": {
                    "type": "boolean",
                    "description": "true to approve, false to reject.",
                },
            },
            "required": ["pane_id", "approve"],
        },
    },
]

# Map tool name → handler
TOOL_HANDLERS = {
    "gmux_health": tool_gmux_health,
    "gmux_list_panes": tool_gmux_list_panes,
    "gmux_pane_messages": tool_gmux_pane_messages,
    "gmux_pane_todos": tool_gmux_pane_todos,
    "gmux_spawn_agent": tool_gmux_spawn_agent,
    "gmux_spawn_sub_agent": tool_gmux_spawn_sub_agent,
    "gmux_send_text": tool_gmux_send_text,
    "gmux_send_key": tool_gmux_send_key,
    "gmux_respond_permission": tool_gmux_respond_permission,
}

# ──────────────────────────────────────────────────────────────────────────────
# JSON-RPC / MCP protocol layer
# ──────────────────────────────────────────────────────────────────────────────


def _send(obj: dict) -> None:
    """Write a single JSON-RPC message to stdout."""
    line = json.dumps(obj, separators=(",", ":"))
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _ok(req_id: Any, result: Any) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, message: str, data: Any = None) -> None:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    _send({"jsonrpc": "2.0", "id": req_id, "error": error})


def _handle_initialize(req_id: Any, params: dict) -> None:
    _ok(
        req_id,
        {
            "protocolVersion": MCP_VERSION,
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VER,
            },
        },
    )


def _handle_tools_list(req_id: Any, params: dict) -> None:
    _ok(req_id, {"tools": TOOLS})


def _handle_tools_call(req_id: Any, params: dict) -> None:
    tool_name = params.get("name", "")
    arguments = params.get("arguments") or {}

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        _err(req_id, -32601, f"Tool not found: {tool_name!r}")
        return

    try:
        result = handler(arguments)
        _ok(
            req_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2),
                    }
                ],
                "isError": False,
            },
        )
    except Exception as exc:
        _log(f"tool {tool_name!r} error: {exc}")
        _ok(
            req_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": str(exc),
                    }
                ],
                "isError": True,
            },
        )


def _dispatch(msg: dict) -> None:
    method = msg.get("method", "")
    params = msg.get("params") or {}
    req_id = msg.get("id")  # None means notification

    _log(f"← {method} id={req_id}")

    # Notifications (no id) — just ack silently
    if req_id is None:
        if method == "notifications/initialized":
            _log("client initialised")
        return

    if method == "initialize":
        _handle_initialize(req_id, params)
    elif method == "tools/list":
        _handle_tools_list(req_id, params)
    elif method == "tools/call":
        _handle_tools_call(req_id, params)
    elif method == "ping":
        _ok(req_id, {})
    else:
        _err(req_id, -32601, f"Method not found: {method!r}")


# ──────────────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    _log(f"gmux MCP server starting (monitor={MONITOR_BASE}, bridge={BRIDGE_BASE})")
    _log(f"token loaded: {_TOKEN is not None}")

    stdin = sys.stdin
    stdout = sys.stdout  # noqa: F841 — used via _send()

    for raw_line in stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _log(f"JSON parse error: {exc} — line: {raw_line[:200]!r}")
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue
        try:
            _dispatch(msg)
        except Exception as exc:
            _log(f"unhandled dispatch error: {exc}")
            req_id = msg.get("id")
            if req_id is not None:
                _err(req_id, -32603, f"Internal error: {exc}")


import urllib.parse  # noqa: E402 — needs to be importable before tool calls

if __name__ == "__main__":
    main()
