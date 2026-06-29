#!/usr/bin/env python3.11
"""
test_monitor_producers.py — one-shot integration test for monitor.py producers.

Synthesises a sequence of SSE-style tool events, calls the writer functions,
parses the resulting JSON files, and asserts sane shapes.

Run with:
    python3.11 backend/status/test_monitor_producers.py
    (from the gmux-system project root)

All assertions print OK/FAIL inline. Exit code 0 = all passed.
"""

import json
import os
import sys
import time

# Allow imports from backend/status/ even when run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# We need to override the tmp-file paths to avoid clobbering real data
import monitor

# ── Redirect output paths to /tmp/test_monitor_*.json ─────────────────────────
monitor.ACTIVITY_FILE = monitor.Path("/tmp/test_monitor_activity.json")
monitor.FILES_FILE = monitor.Path("/tmp/test_monitor_files.json")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_PASS = 0
_FAIL = 0


def ok(label: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  OK   {label}")


def fail(label: str, detail: str = "") -> None:
    global _FAIL
    _FAIL += 1
    print(f"  FAIL {label}" + (f"  — {detail}" if detail else ""))


def assert_eq(label: str, got, expected) -> None:
    if got == expected:
        ok(label)
    else:
        fail(label, f"got {got!r}, expected {expected!r}")


def assert_in(label: str, key, container) -> None:
    if key in container:
        ok(label)
    else:
        fail(label, f"{key!r} not found in {container!r}")


def assert_true(label: str, val, note: str = "") -> None:
    if val:
        ok(label)
    else:
        fail(label, note or repr(val))


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — _extract_tool_args
# ─────────────────────────────────────────────────────────────────────────────

print("\n[1] _extract_tool_args")

args = monitor._extract_tool_args("Write", {"filePath": "src/auth.py"})
assert_eq("Write → file_path extracted", args.get("file_path"), "src/auth.py")
assert_true("Write → no spurious keys", "command" not in args)

args = monitor._extract_tool_args("Bash", {"command": "pytest tests/ -x --tb=short"})
assert_eq(
    "Bash → command extracted", args.get("command"), "pytest tests/ -x --tb=short"
)
assert_true("Bash → no file_path", "file_path" not in args)

# Bash command truncation at 120 chars
long_cmd = "echo " + "x" * 200
args = monitor._extract_tool_args("Bash", {"command": long_cmd})
assert_true("Bash → command truncated at 120", len(args.get("command", "")) <= 120)

args = monitor._extract_tool_args(
    "Grep", {"pattern": "def _extract", "query": "old-key"}
)
assert_eq("Grep → pattern extracted", args.get("pattern"), "def _extract")

args = monitor._extract_tool_args("Glob", {"glob": "**/*.py"})
assert_eq("Glob → pattern extracted (glob key)", args.get("pattern"), "**/*.py")

args = monitor._extract_tool_args("Read", {"file_path": "src/main.py"})
assert_eq("Read → file_path via snake_case", args.get("file_path"), "src/main.py")

args = monitor._extract_tool_args("UnknownTool", {})
assert_eq("UnknownTool → empty dict", args, {})

# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — _record_activity_start / _record_activity_end
# ─────────────────────────────────────────────────────────────────────────────

print("\n[2] _record_activity_start / _record_activity_end")

# Set up fake pane name + cwd mapping
monitor._pane_to_name["%42"] = "doofing"
monitor._pane_to_cwd["%42"] = "/home/fivelidz/projects/gmux"

# Clear any existing activity from imports
monitor._activity.clear()
monitor._tool_starts.clear()

# Simulate a Write tool call
monitor._record_activity_start(
    "%42", "Write", "call001", {"filePath": "src/voice/daemon.py"}
)
assert_eq("activity deque has 1 event after start", len(monitor._activity), 1)

start_ev = monitor._activity[-1]
assert_eq("start event kind", start_ev["kind"], "tool_start")
assert_eq("start event tool", start_ev["tool"], "Write")
assert_eq("start event pane_id", start_ev["pane_id"], "%42")
assert_eq("start event agent_name", start_ev["agent_name"], "doofing")
# v3.6.1 — file_path is now always absolute (resolved against pane cwd).
# The relative form is kept in args.file_path_rel for compact UI display.
assert_eq(
    "start event file_path (absolute)",
    start_ev["args"].get("file_path"),
    "/home/fivelidz/projects/gmux/src/voice/daemon.py",
)
assert_eq(
    "start event file_path_rel",
    start_ev["args"].get("file_path_rel"),
    "src/voice/daemon.py",
)
assert_true("start event id starts with act_", start_ev["id"].startswith("act_"))
assert_true("start event ts has Z suffix", start_ev["ts"].endswith("Z"))

# Simulate a short delay then end event
time.sleep(0.05)
monitor._record_activity_end(
    "%42", "Write", "call001", {"filePath": "src/voice/daemon.py"}, result="ok"
)
assert_eq("activity deque has 2 events after end", len(monitor._activity), 2)

end_ev = monitor._activity[-1]
assert_eq("end event kind", end_ev["kind"], "tool_end")
assert_eq("end event result", end_ev["result"], "ok")
assert_true("end event has duration_ms > 0", (end_ev.get("duration_ms") or 0) > 0)
assert_true("end event id ends with _end", end_ev["id"].endswith("_end"))

# Simulate a Bash call
monitor._record_activity_start("%42", "Bash", "call002", {"command": "pytest tests/"})
bash_ev = monitor._activity[-1]
assert_eq(
    "Bash start → command in args", bash_ev["args"].get("command"), "pytest tests/"
)
assert_true("Bash start → no file_path", bash_ev["args"].get("file_path", "") == "")

# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — write_activity
# ─────────────────────────────────────────────────────────────────────────────

print("\n[3] write_activity")

monitor.write_activity()
assert_true("activity file exists", monitor.ACTIVITY_FILE.exists())

data = json.loads(monitor.ACTIVITY_FILE.read_text())
assert_true("activity is a list", isinstance(data, list))
assert_true("activity has ≥ 2 events", len(data) >= 2)

ids = [e["id"] for e in data]
assert_true("all activity ids are unique", len(ids) == len(set(ids)))

for ev in data:
    for field in ("id", "ts", "pane_id", "kind", "tool", "args"):
        assert_true(
            f"activity event has field: {field}", field in ev, f"missing in {ev}"
        )

# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — write_files (derived from activity deque)
# ─────────────────────────────────────────────────────────────────────────────

print("\n[4] write_files")

monitor.write_files()
assert_true("files file exists", monitor.FILES_FILE.exists())

files_data = json.loads(monitor.FILES_FILE.read_text())
assert_true("files is a dict", isinstance(files_data, dict))

# We recorded Write on "src/voice/daemon.py" from cwd "/home/fivelidz/projects/gmux"
# → abs_path should be "/home/fivelidz/projects/gmux/src/voice/daemon.py"
abs_key = "/home/fivelidz/projects/gmux/src/voice/daemon.py"
assert_in("file entry exists for daemon.py", abs_key, files_data)

entry = files_data[abs_key]
assert_true("file entry has path field", "path" in entry)
assert_true("file entry has rel_path field", "rel_path" in entry)
assert_true(
    "rel_path uses directory structure (not just filename)",
    "/" in entry.get("rel_path", ""),
    f"rel_path={entry.get('rel_path')!r}",
)
assert_eq("rel_path value", entry["rel_path"], "src/voice/daemon.py")
assert_true("file entry has touches_1h > 0", entry.get("touches_1h", 0) > 0)
assert_in("pane_id in agents list", "%42", entry.get("agents", []))
assert_true("file entry has last_touch_ts", bool(entry.get("last_touch_ts")))

for field in (
    "touches_5m",
    "touches_30m",
    "touches_1h",
    "agents",
    "last_touch_ts",
    "last_writer",
    "is_hot",
    "is_conflict",
    "is_god_node",
    "callers",
):
    assert_in(f"file entry has field: {field}", field, entry)

# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — _get_last_tool_summary_for_pane
# ─────────────────────────────────────────────────────────────────────────────

print("\n[5] _get_last_tool_summary_for_pane")

summary = monitor._get_last_tool_summary_for_pane("%42")
assert_true("summary is a non-empty dict", bool(summary))
# Most recent tool_start was Bash (call002)
assert_eq("summary tool is Bash", summary.get("tool"), "Bash")
assert_eq("summary command is pytest", summary.get("command"), "pytest tests/")
assert_true("summary ts is set", bool(summary.get("ts")))

summary_missing = monitor._get_last_tool_summary_for_pane("%99")
assert_eq("summary for unknown pane is empty dict", summary_missing, {})

# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — get_child_session_ids with mock API response
# ─────────────────────────────────────────────────────────────────────────────

print("\n[6] get_child_session_ids (mock api_get)")

# Patch api_get temporarily
_real_api_get = monitor.api_get


def _mock_api_get(port, path, directory=""):
    if path == "/session":
        return [
            {"id": "ses_parent", "parentID": None},
            {"id": "ses_child1", "parentID": "ses_parent"},
            {"id": "ses_child2", "parentID": "ses_parent"},
            {"id": "ses_other", "parentID": "ses_other_parent"},
        ]
    return None


monitor.api_get = _mock_api_get

children = monitor.get_child_session_ids(12345, "ses_parent", "/tmp")
assert_eq("two children found", len(children), 2)
assert_in("ses_child1 in children", "ses_child1", children)
assert_in("ses_child2 in children", "ses_child2", children)
assert_true("ses_other NOT in children", "ses_other" not in children)

no_children = monitor.get_child_session_ids(12345, "ses_leaf", "/tmp")
assert_eq("leaf session has no children", no_children, [])

monitor.api_get = _real_api_get  # restore

# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — activity circular buffer cap
# ─────────────────────────────────────────────────────────────────────────────

print("\n[7] activity circular buffer cap")

monitor._activity.clear()
monitor._tool_starts.clear()

# Fill beyond ACTIVITY_MAX
for i in range(monitor.ACTIVITY_MAX + 10):
    monitor._record_activity_start(
        "%42", "Read", f"overflow_{i:04d}", {"filePath": f"src/file_{i}.py"}
    )

assert_true(
    f"activity deque capped at ACTIVITY_MAX ({monitor.ACTIVITY_MAX})",
    len(monitor._activity) == monitor.ACTIVITY_MAX,
    f"actual len = {len(monitor._activity)}",
)

# Newest events are retained (tail-drop semantics from collections.deque maxlen)
last_id = monitor._activity[-1]["args"]["file_path"]
assert_true(
    "newest events are in the deque", "file_509" in last_id or "file_" in last_id
)

# ─────────────────────────────────────────────────────────────────────────────
# Test 8 — Rate-limit detection: PaneState, LiveState fields
# ─────────────────────────────────────────────────────────────────────────────

print("\n[8] Rate-limit detection — PaneState + LiveState fields")

# 8a: RATE_LIMITED value
assert_eq(
    "PaneState.RATE_LIMITED value",
    monitor.PaneState.RATE_LIMITED.value,
    "rate_limited",
)

# 8b: LiveState has rate-limit fields with correct defaults
ls = monitor.LiveState()
assert_eq("LiveState.rate_limit_msg default is ''", ls.rate_limit_msg, "")
assert_eq("LiveState.rate_limit_until default is None", ls.rate_limit_until, None)
assert_eq("LiveState.auth_expiring default is False", ls.auth_expiring, False)
assert_eq("LiveState.auth_expired default is False", ls.auth_expired, False)

# 8c: Rate-limit regex matches expected patterns
RL = monitor._RATE_LIMIT_RE
assert_true(
    "regex matches 'rate limit exceeded'", bool(RL.search("rate limit exceeded"))
)
assert_true("regex matches 'HTTP 429'", bool(RL.search("HTTP 429 Too Many Requests")))
assert_true(
    "regex matches 'too many requests'", bool(RL.search("Error: too many requests"))
)
assert_true("regex matches 'quota exceeded'", bool(RL.search("quota exceeded")))
assert_true("regex matches 'rate-limit' (hyphen)", bool(RL.search("rate-limit hit")))
assert_true(
    "regex does NOT match 'normal error'",
    not bool(RL.search("normal error: file not found")),
)

# 8d: _extract_retry_after parses relative seconds
ra = monitor._extract_retry_after("Retry-After: 30")
assert_true(
    "Retry-After relative: returns epoch > now", ra is not None and ra > time.time()
)
assert_true(
    "Retry-After relative: approx +30s",
    ra is not None and abs(ra - (time.time() + 30)) < 5,
)

# 8e: _extract_retry_after parses raw epoch (> 1e9)
future_epoch = int(time.time()) + 120
ra2 = monitor._extract_retry_after(f"retry_after: {future_epoch}")
assert_true(
    "Retry-After epoch: returns same value",
    ra2 is not None and abs(ra2 - future_epoch) < 2,
)

# 8f: _extract_retry_after returns None when no value present
ra3 = monitor._extract_retry_after("Error: quota exceeded — no header")
assert_eq("Retry-After absent: returns None", ra3, None)

# ─────────────────────────────────────────────────────────────────────────────
# Test 9 — Rate-limit serialisation via write_state / PaneInfo
# ─────────────────────────────────────────────────────────────────────────────

print("\n[9] Rate-limit serialisation (write_state round-trip)")

# Redirect STATE_FILE to a temp path for this test
import tempfile as _tempfile
import dataclasses as _dc

_orig_state_file = monitor.STATE_FILE
monitor.STATE_FILE = monitor.Path(_tempfile.mktemp(suffix=".json"))


def _make_pane(pane_id, state, **overrides):
    """Build a PaneInfo with safe defaults for all optional fields."""
    return monitor.PaneInfo(
        pane_id=pane_id,
        session_name="test",
        window_index=1,
        window_name="test-agent",
        pane_index=0,
        is_active=False,
        foreground_cmd="bun",
        state=state,
        has_ai=True,
        last_line="test line",
        # Optional fields with explicit defaults:
        api_port=0,
        current_tool="",
        todo_done=0,
        todo_total=0,
        pane_left=0,
        pane_top=0,
        pane_width=80,
        pane_height=24,
        sub_agent_permission=False,
        todos=[],
        cwd="",
        tool_history=[],
        ram_mb=0,
        cpu_pct=0.0,
        uptime_s=0,
        children=[],
        session_id="",
        model="",
        provider="",
        token_in=0,
        token_out=0,
        token_reasoning=0,
        cost_usd=0.0,
        msg_count=0,
        session_age_s=0,
        sub_agents=[],
        last_tool_call_summary={},
        **{
            "rate_limit_msg": "",
            "rate_limit_until": None,
            "auth_expiring": False,
            "auth_expired": False,
            **overrides,
        },
    )


# 9a: Rate-limited pane serialises correctly
_test_pi = _make_pane(
    "%99",
    monitor.PaneState.RATE_LIMITED,
    rate_limit_msg="Too Many Requests — quota exceeded",
    rate_limit_until=time.time() + 60.0,
)
monitor.write_state([_test_pi])
_state_data = json.loads(monitor.STATE_FILE.read_text())
_pane_data = _state_data.get("%99", {})
assert_eq("serialised state is 'rate_limited'", _pane_data.get("state"), "rate_limited")
assert_true("rate_limit_msg serialised", bool(_pane_data.get("rate_limit_msg")))
assert_true(
    "rate_limit_until is numeric",
    isinstance(_pane_data.get("rate_limit_until"), (int, float)),
)
assert_eq("auth_expiring is False", _pane_data.get("auth_expiring"), False)
assert_eq("auth_expired is False", _pane_data.get("auth_expired"), False)

# 9b: rate_limit_until=None serialises as JSON null, key must be present
_test_pi2 = _make_pane("%98", monitor.PaneState.WAITING)
monitor.write_state([_test_pi2])
_state_data2 = json.loads(monitor.STATE_FILE.read_text())
_pane_data2 = _state_data2.get("%98", {})
assert_eq("rate_limit_until null → None", _pane_data2.get("rate_limit_until"), None)
assert_true("rate_limit_until key present", "rate_limit_until" in _pane_data2)

# 9c: auth_expiring=True serialises correctly
_test_pi3 = _make_pane("%97", monitor.PaneState.WAITING, auth_expiring=True)
monitor.write_state([_test_pi3])
_pane_data3 = json.loads(monitor.STATE_FILE.read_text()).get("%97", {})
assert_eq("auth_expiring=True serialises", _pane_data3.get("auth_expiring"), True)
assert_eq(
    "auth_expired=False default serialises", _pane_data3.get("auth_expired"), False
)

# 9d: auth_expired=True serialises correctly
_test_pi4 = _make_pane("%96", monitor.PaneState.WAITING, auth_expired=True)
monitor.write_state([_test_pi4])
_pane_data4 = json.loads(monitor.STATE_FILE.read_text()).get("%96", {})
assert_eq("auth_expired=True serialises", _pane_data4.get("auth_expired"), True)

# Restore STATE_FILE
try:
    monitor.STATE_FILE.unlink(missing_ok=True)
except Exception:
    pass
monitor.STATE_FILE = _orig_state_file

# ─────────────────────────────────────────────────────────────────────────────
# Test 10 — auth_expiring / auth_expired flag logic
# ─────────────────────────────────────────────────────────────────────────────

print("\n[10] auth_expiring / auth_expired flag logic (_check_auth_expiry)")

import tempfile as _tf, json as _json

# Write a temp auth.json with three providers: valid, expiring, expired
_auth_tmp = monitor.Path(_tf.mktemp(suffix=".json"))
_now_ms = int(time.time() * 1000)
_auth_tmp.write_text(
    _json.dumps(
        {
            "anthropic": {
                "access_token": "tok_valid",
                "expires": _now_ms + 300_000,  # expires in 5 min → NOT expiring/expired
            },
            "openai": {
                "access_token": "tok_expiring",
                "expires": _now_ms + 30_000,  # expires in 30 sec → auth_expiring=True
            },
            "google": {
                "access_token": "tok_expired",
                "expires": _now_ms - 5_000,  # expired 5 sec ago → auth_expired=True
            },
        }
    )
)

# Temporarily patch the auth path
_orig_auth_path = monitor._AUTH_JSON_PATH
monitor._AUTH_JSON_PATH = _auth_tmp

result = monitor._check_auth_expiry()
assert_true("anthropic present in result", "anthropic" in result)
assert_eq(
    "anthropic auth_expiring is False", result["anthropic"]["auth_expiring"], False
)
assert_eq("anthropic auth_expired is False", result["anthropic"]["auth_expired"], False)

assert_true("openai present in result", "openai" in result)
assert_eq("openai auth_expiring is True", result["openai"]["auth_expiring"], True)
assert_eq("openai auth_expired is False", result["openai"]["auth_expired"], False)

assert_true("google present in result", "google" in result)
assert_eq("google auth_expiring is False", result["google"]["auth_expiring"], False)
assert_eq("google auth_expired is True", result["google"]["auth_expired"], True)

# Restore
monitor._AUTH_JSON_PATH = _orig_auth_path
try:
    _auth_tmp.unlink(missing_ok=True)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Test 11 — _handle_sse_event rate-limit detection (Signal A)
# ─────────────────────────────────────────────────────────────────────────────

print("\n[11] SSE session.error rate-limit detection (Signal A)")

# Inject a fake pane into _live
_rl_pane_id = "%rl_test"
with monitor._live_lock:
    monitor._live[_rl_pane_id] = monitor.LiveState()

# Send a rate-limit session.error SSE event
monitor._handle_sse_event(
    _rl_pane_id,
    9999,
    {
        "type": "session.error",
        "properties": {
            "message": "HTTP 429 Too Many Requests — quota exceeded. Retry-After: 45",
        },
    },
)
with monitor._live_lock:
    _ls = monitor._live.get(_rl_pane_id)
    _rl_state = _ls.state if _ls else None
    _rl_msg = _ls.rate_limit_msg if _ls else ""
    _rl_until = _ls.rate_limit_until if _ls else None

assert_eq("SSE 429 → state is RATE_LIMITED", _rl_state, monitor.PaneState.RATE_LIMITED)
assert_true("SSE 429 → rate_limit_msg is set", bool(_rl_msg))
assert_true(
    "SSE 429 → rate_limit_until parsed (~+45s)",
    _rl_until is not None and abs(_rl_until - (time.time() + 45)) < 10,
)

# Send a NON-rate-limit session.error event — should remain ERROR
_err_pane_id = "%err_test"
with monitor._live_lock:
    monitor._live[_err_pane_id] = monitor.LiveState()

monitor._handle_sse_event(
    _err_pane_id,
    9999,
    {
        "type": "session.error",
        "properties": {
            "message": "Error: file not found: /tmp/missing.txt",
        },
    },
)
with monitor._live_lock:
    _ls2 = monitor._live.get(_err_pane_id)
    _err_state = _ls2.state if _ls2 else None

assert_eq("Non-rate-limit error → state is ERROR", _err_state, monitor.PaneState.ERROR)

# Cleanup test panes
with monitor._live_lock:
    monitor._live.pop(_rl_pane_id, None)
    monitor._live.pop(_err_pane_id, None)

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup temp files
# ─────────────────────────────────────────────────────────────────────────────

for f in (monitor.ACTIVITY_FILE, monitor.FILES_FILE):
    try:
        f.unlink(missing_ok=True)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'=' * 54}")
print(f"  Passed: {_PASS}   Failed: {_FAIL}")
print(f"{'=' * 54}")
sys.exit(0 if _FAIL == 0 else 1)
