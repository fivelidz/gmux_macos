#!/usr/bin/env python3.11
"""
test_sub_agents.py — unit tests for the v3.7 gmux-spawned sub-agent feature.

Tests:
  1. _load_spawned_sub_agents — reads JSON file, resolves window_name→pane_id
  2. write_state — merges parent_pane_id onto the correct pane dict
  3. Integration: synthesised entry → monitor parse → pane dict assertions

Run with:
    python3.11 backend/status/test_sub_agents.py
    (from the gmux-system project root)

All assertions print OK/FAIL inline. Exit code 0 = all passed.
Does NOT require a running tmux session.
"""

import json
import os
import sys
import time
import tempfile
from pathlib import Path
from dataclasses import asdict

# Allow imports from backend/status/ even when run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import monitor

# ── Redirect output paths so we don't clobber real data ───────────────────────
monitor.ACTIVITY_FILE = Path("/tmp/test_sub_agents_activity.json")
monitor.FILES_FILE = Path("/tmp/test_sub_agents_files.json")
monitor.STATE_FILE = Path("/tmp/test_sub_agents_state.json")

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


def assert_true(label: str, val, note: str = "") -> None:
    if val:
        ok(label)
    else:
        fail(label, note or repr(val))


def assert_in(label: str, key, container) -> None:
    if key in container:
        ok(label)
    else:
        fail(label, f"{key!r} not found in {container!r}")


def assert_not_in(label: str, key, container) -> None:
    if key not in container:
        ok(label)
    else:
        fail(label, f"{key!r} unexpectedly found in {container!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — _load_spawned_sub_agents: reads JSON and resolves window_name→pane_id
# ─────────────────────────────────────────────────────────────────────────────

print("\n[1] _load_spawned_sub_agents — file reading and name resolution")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    sub_agents_file = Path(f.name)
    json.dump(
        {
            "parent+sub-worker": {
                "parent_pane_id": "%10",
                "spawned_at": 1747123456789,
                "agent_type": "claude",
                "model": "claude-sonnet-4-5",
            },
            "toplevel-agent": {
                "parent_pane_id": "%99",
                "spawned_at": 1747123400000,
                "agent_type": "opencode",
                "model": "",
            },
        },
        f,
    )

# Patch the module-level path and clear any existing state
monitor.SUB_AGENTS_FILE = sub_agents_file
monitor._pane_to_name.clear()
monitor._spawned_sub_agents_raw.clear()
monitor._spawned_sub_agents_by_pane.clear()

# Before name resolution is available — raw dict should load but by_pane is empty
monitor._load_spawned_sub_agents()
assert_eq("raw dict loaded (2 entries)", len(monitor._spawned_sub_agents_raw), 2)
assert_in(
    "parent+sub-worker in raw", "parent+sub-worker", monitor._spawned_sub_agents_raw
)
assert_eq(
    "by_pane is empty before _pane_to_name is set",
    len(monitor._spawned_sub_agents_by_pane),
    0,
)

# Now populate _pane_to_name to simulate post-tmux-poll state
monitor._pane_to_name["%42"] = "parent+sub-worker"
monitor._pane_to_name["%10"] = "parent"
monitor._pane_to_name["%55"] = "toplevel-agent"

monitor._load_spawned_sub_agents()
assert_eq(
    "by_pane has 2 entries after name resolution",
    len(monitor._spawned_sub_agents_by_pane),
    2,
)
assert_in(
    "%42 resolved from parent+sub-worker", "%42", monitor._spawned_sub_agents_by_pane
)
assert_in(
    "%55 resolved from toplevel-agent", "%55", monitor._spawned_sub_agents_by_pane
)
assert_not_in(
    "%10 NOT in by_pane (it is the parent, not a spawned child)",
    "%10",
    monitor._spawned_sub_agents_by_pane,
)
assert_eq(
    "parent_pane_id for %42",
    monitor._spawned_sub_agents_by_pane["%42"]["parent_pane_id"],
    "%10",
)
assert_eq(
    "agent_type for %42",
    monitor._spawned_sub_agents_by_pane["%42"]["agent_type"],
    "claude",
)

# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — write_state merges parent_pane_id onto the correct pane dict
# ─────────────────────────────────────────────────────────────────────────────

print("\n[2] write_state — parent_pane_id merged into pane state dict")

# Build minimal PaneInfo objects — only the fields needed for asdict()
from monitor import PaneInfo, PaneState


def make_pane(pane_id: str, win_name: str, has_ai: bool = False) -> PaneInfo:
    return PaneInfo(
        pane_id=pane_id,
        session_name="gmux",
        window_index=1,
        window_name=win_name,
        pane_index=0,
        is_active=False,
        foreground_cmd="fish",
        state=PaneState.IDLE,
        has_ai=has_ai,
        last_line="",
    )


# Ensure _spawned_sub_agents_by_pane has our entry from Test 1
assert_true(
    "_spawned_sub_agents_by_pane still populated from Test 1",
    "%42" in monitor._spawned_sub_agents_by_pane,
)

panes_list = [
    make_pane("%10", "parent", has_ai=True),
    make_pane("%42", "parent+sub-worker", has_ai=True),
    make_pane("%99", "other-agent", has_ai=True),
]

monitor.write_state(panes_list)
assert_true("state file written", monitor.STATE_FILE.exists())

state_data = json.loads(monitor.STATE_FILE.read_text())

# %42 should have parent_pane_id and is_child_pane
p42 = state_data.get("%42", {})
assert_eq("parent_pane_id on %42", p42.get("parent_pane_id"), "%10")
assert_eq("is_child_pane on %42", p42.get("is_child_pane"), True)
assert_eq("spawned_agent_type on %42", p42.get("spawned_agent_type"), "claude")
assert_eq("spawned_model on %42", p42.get("spawned_model"), "claude-sonnet-4-5")
assert_true("spawned_at_ms on %42 > 0", p42.get("spawned_at_ms", 0) > 0)

# %10 (parent) should NOT have is_child_pane set
p10 = state_data.get("%10", {})
assert_eq("is_child_pane on %10 (parent) is False", p10.get("is_child_pane"), False)
assert_eq("parent_pane_id on %10 is empty", p10.get("parent_pane_id"), "")

# %99 (unrelated) should also NOT have is_child_pane set
p99 = state_data.get("%99", {})
assert_eq("is_child_pane on %99 (unrelated) is False", p99.get("is_child_pane"), False)

# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — non-existent / malformed sub-agents file is handled gracefully
# ─────────────────────────────────────────────────────────────────────────────

print("\n[3] _load_spawned_sub_agents — missing / malformed file handled gracefully")

# Point at a non-existent file
monitor.SUB_AGENTS_FILE = Path("/tmp/this_does_not_exist_abc123.json")
monitor._spawned_sub_agents_raw.clear()
monitor._spawned_sub_agents_by_pane.clear()
monitor._load_spawned_sub_agents()  # must not raise
assert_eq("raw stays empty on missing file", monitor._spawned_sub_agents_raw, {})
assert_eq(
    "by_pane stays empty on missing file", monitor._spawned_sub_agents_by_pane, {}
)
ok("no exception on missing file")

# Empty file
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    empty_file = Path(f.name)
    f.write("")
monitor.SUB_AGENTS_FILE = empty_file
monitor._load_spawned_sub_agents()  # must not raise
assert_eq("raw stays empty on empty file", monitor._spawned_sub_agents_raw, {})
ok("no exception on empty file")

# Malformed JSON
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    bad_file = Path(f.name)
    f.write("{not valid json!")
monitor.SUB_AGENTS_FILE = bad_file
monitor._load_spawned_sub_agents()  # must not raise
assert_eq("raw stays empty on malformed JSON", monitor._spawned_sub_agents_raw, {})
ok("no exception on malformed JSON")

# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — write_state does not break existing panes when sub-agents file empty
# ─────────────────────────────────────────────────────────────────────────────

print("\n[4] write_state — existing panes unaffected when no sub-agents file")

monitor._spawned_sub_agents_by_pane.clear()
panes_list_plain = [
    make_pane("%1", "myproject", has_ai=True),
    make_pane("%2", "other-project", has_ai=False),
]
monitor.write_state(panes_list_plain)
state_plain = json.loads(monitor.STATE_FILE.read_text())

for pid in ("%1", "%2"):
    p = state_plain.get(pid, {})
    assert_eq(f"is_child_pane False for {pid}", p.get("is_child_pane"), False)
    assert_eq(f"parent_pane_id empty for {pid}", p.get("parent_pane_id"), "")

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

for f in (
    sub_agents_file,
    empty_file,
    bad_file,
    monitor.ACTIVITY_FILE,
    monitor.FILES_FILE,
    monitor.STATE_FILE,
):
    try:
        f.unlink(missing_ok=True)
    except Exception:
        pass

# Restore the module-level paths to their real values
monitor.SUB_AGENTS_FILE = Path("/tmp/gmuxtest-sub-agents.json")
monitor.STATE_FILE = Path("/tmp/gmuxtest-pane-state.json")

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{'=' * 54}")
print(f"  Passed: {_PASS}   Failed: {_FAIL}")
print(f"{'=' * 54}")
sys.exit(0 if _FAIL == 0 else 1)
