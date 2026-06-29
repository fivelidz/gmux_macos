#!/usr/bin/env python3.11
"""
test_memory_aggregator.py — one-shot integration test for memory_aggregator.

Mirrors the style of test_monitor_producers.py: inline asserts, OK/FAIL output,
exit code 0 = all passed.

Run with:
    python3.11 backend/status/test_memory_aggregator.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Allow imports from backend/status/ even when run from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import memory_aggregator as MA  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Test harness — same idiom as test_monitor_producers.py
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


def assert_eq(label, got, expected):
    if got == expected:
        ok(label)
    else:
        fail(label, f"got {got!r}, expected {expected!r}")


def assert_in(label, key, container):
    if key in container:
        ok(label)
    else:
        fail(label, f"{key!r} not in {container!r}")


def assert_true(label, val, note: str = ""):
    if val:
        ok(label)
    else:
        fail(label, note or repr(val))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def make_memory_tree(root: Path) -> None:
    """Create a fake memory tree with valid + malformed files."""
    for kind in MA.MEMORY_KINDS:
        (root / kind).mkdir(parents=True, exist_ok=True)

    # Valid: episodic
    (root / "episodic" / "ep_one.json").write_text(
        json.dumps(
            {
                "id": "mem_test_ep_01",
                "type": "episodic",
                "agent_id": "pane-1",
                "agent_name": "doofing",
                "created_at": "2026-05-13T10:00:00Z",
                "title": "Refactored auth module",
                "tags": ["auth", "refactor"],
                "produced_by": "agent_self",
                "confidence": 0.9,
            }
        )
    )

    # Valid: episodic from a different agent
    (root / "episodic" / "ep_two.json").write_text(
        json.dumps(
            {
                "id": "mem_test_ep_02",
                "type": "episodic",
                "agent_id": "pane-4",
                "created_at": "2026-05-13T10:30:00Z",
                "title": "Built dashboard prototype",
                "tags": ["dashboard", "ui"],
            }
        )
    )

    # Valid: semantic shared by pane-1 (same agent as ep_one — tests by_agent grouping)
    (root / "semantic" / "sem_one.json").write_text(
        json.dumps(
            {
                "id": "mem_test_sem_01",
                "type": "semantic",
                "agent_id": "pane-1",
                "created_at": "2026-05-13T09:00:00Z",
                "title": "OpenCode requires ?directory= on SSE",
                "tags": ["opencode", "api"],
                "verified": True,
            }
        )
    )

    # Valid: procedural with a tag overlap (tests by_tag aggregation)
    (root / "procedural" / "proc_one.json").write_text(
        json.dumps(
            {
                "id": "mem_test_proc_01",
                "type": "procedural",
                "agent_id": "human",
                "created_at": "2026-05-12T22:00:00Z",
                "title": "Atomic JSON write pattern",
                "tags": ["pattern", "io"],
            }
        )
    )

    # Valid: shared
    (root / "shared" / "share_one.json").write_text(
        json.dumps(
            {
                "id": "mem_test_share_01",
                "type": "shared",
                "agent_id": "monitor",
                "created_at": "2026-05-13T12:00:00Z",
                "title": "pane-1 editing auth (hot file)",
                "tags": ["coordination", "auth"],  # "auth" overlaps with ep_one
                "shared_with": ["*"],
            }
        )
    )

    # Malformed: not valid JSON
    (root / "episodic" / "broken.json").write_text("{ this is not json !!! ")

    # Missing required key (id)
    (root / "semantic" / "no_id.json").write_text(
        json.dumps(
            {
                "type": "semantic",
                "title": "Missing id field",
            }
        )
    )

    # Non-JSON file extension should be ignored
    (root / "episodic" / "README.txt").write_text("not a memory file")


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — missing memory dir → empty output, no crash
# ─────────────────────────────────────────────────────────────────────────────

print("\n[1] aggregate_once with MISSING memory dir")

with tempfile.TemporaryDirectory() as tmpd:
    missing_root = Path(tmpd) / "definitely-not-there"
    out_file = Path(tmpd) / "out_missing.json"
    result = MA.aggregate_once(
        memory_root=missing_root, output_file=out_file, verbose=False
    )
    assert_true("returns dict", isinstance(result, dict))
    assert_eq("total_count == 0", result["total_count"], 0)
    assert_eq("memories empty", result["memories"], {})
    assert_eq("by_agent empty", result["by_agent"], {})
    assert_true(
        "by_kind has all kinds (with empty lists)",
        all(k in result["by_kind"] for k in MA.MEMORY_KINDS),
    )
    assert_true("output file written", out_file.exists())
    on_disk = json.loads(out_file.read_text())
    assert_eq("on-disk total_count == 0", on_disk["total_count"], 0)
    assert_eq("schema_version 1.0", on_disk["_schema_version"], "1.0")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — valid files parsed correctly
# ─────────────────────────────────────────────────────────────────────────────

print("\n[2] aggregate_once parses valid memories")

with tempfile.TemporaryDirectory() as tmpd:
    root = Path(tmpd) / "memory"
    make_memory_tree(root)
    out_file = Path(tmpd) / "out_valid.json"
    result = MA.aggregate_once(memory_root=root, output_file=out_file, verbose=False)

    # 5 valid files were written (ep_one, ep_two, sem_one, proc_one, share_one)
    assert_eq("total_count == 5", result["total_count"], 5)
    assert_in("ep_one parsed", "mem_test_ep_01", result["memories"])
    assert_in("ep_two parsed", "mem_test_ep_02", result["memories"])
    assert_in("sem_one parsed", "mem_test_sem_01", result["memories"])
    assert_in("proc_one parsed", "mem_test_proc_01", result["memories"])
    assert_in("share_one parsed", "mem_test_share_01", result["memories"])

    # Field normalisation — agent_id → agent, title preserved
    ep_one = result["memories"]["mem_test_ep_01"]
    assert_eq("agent_id mapped to agent", ep_one["agent"], "pane-1")
    assert_eq("title preserved", ep_one["title"], "Refactored auth module")
    assert_eq("summary alias of title", ep_one["summary"], "Refactored auth module")
    assert_eq("kind resolved from type field", ep_one["kind"], "episodic")
    assert_eq("ts from created_at", ep_one["ts"], "2026-05-13T10:00:00Z")
    assert_true("size populated", ep_one["size"] > 0)
    assert_eq("confidence preserved", ep_one["confidence"], 0.9)

    # Default values for missing fields
    ep_two = result["memories"]["mem_test_ep_02"]
    assert_eq("default confidence 0.5", ep_two["confidence"], 0.5)
    assert_eq("default pinned False", ep_two["pinned"], False)
    assert_eq("default verified False", ep_two["verified"], False)

    # verified preserved when set
    sem_one = result["memories"]["mem_test_sem_01"]
    assert_eq("verified=True preserved", sem_one["verified"], True)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — malformed files are skipped, not crash
# ─────────────────────────────────────────────────────────────────────────────

print("\n[3] malformed JSON + missing-key files are skipped")

with tempfile.TemporaryDirectory() as tmpd:
    root = Path(tmpd) / "memory"
    make_memory_tree(root)
    out_file = Path(tmpd) / "out_malformed.json"
    # We expect: 5 valid + 2 invalid (broken.json + no_id.json) + 1 ignored (README.txt)
    result = MA.aggregate_once(memory_root=root, output_file=out_file, verbose=False)
    assert_eq("still 5 valid memories (malformed skipped)", result["total_count"], 5)
    assert_true(
        "broken.json NOT in memories",
        all("broken" not in k for k in result["memories"]),
    )
    assert_true("no_id.json NOT in memories", "no_id" not in result["memories"])
    assert_true(
        "README.txt NOT processed", all("README" not in k for k in result["memories"])
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — by_agent / by_kind / by_tag groupings
# ─────────────────────────────────────────────────────────────────────────────

print("\n[4] by_agent / by_kind / by_tag groupings")

with tempfile.TemporaryDirectory() as tmpd:
    root = Path(tmpd) / "memory"
    make_memory_tree(root)
    out_file = Path(tmpd) / "out_groups.json"
    result = MA.aggregate_once(memory_root=root, output_file=out_file, verbose=False)

    # by_agent: pane-1 owns ep_one + sem_one (2 memories)
    by_agent = result["by_agent"]
    assert_in("by_agent contains pane-1", "pane-1", by_agent)
    assert_eq(
        "pane-1 has 2 memories",
        sorted(by_agent["pane-1"]),
        sorted(["mem_test_ep_01", "mem_test_sem_01"]),
    )
    assert_in("by_agent contains pane-4", "pane-4", by_agent)
    assert_eq("pane-4 has 1 memory", by_agent["pane-4"], ["mem_test_ep_02"])
    assert_in("by_agent contains human", "human", by_agent)
    assert_in("by_agent contains monitor", "monitor", by_agent)

    # by_kind: episodic=2, semantic=1, procedural=1, shared=1
    by_kind = result["by_kind"]
    assert_eq("by_kind episodic has 2", len(by_kind["episodic"]), 2)
    assert_eq("by_kind semantic has 1", len(by_kind["semantic"]), 1)
    assert_eq("by_kind procedural has 1", len(by_kind["procedural"]), 1)
    assert_eq("by_kind shared has 1", len(by_kind["shared"]), 1)

    # by_tag: 'auth' appears in ep_one + share_one (overlap from different kinds)
    by_tag = result["by_tag"]
    assert_in("by_tag contains 'auth'", "auth", by_tag)
    assert_eq(
        "'auth' tag has 2 memories",
        sorted(by_tag["auth"]),
        sorted(["mem_test_ep_01", "mem_test_share_01"]),
    )
    assert_in("by_tag contains 'refactor'", "refactor", by_tag)
    assert_eq("'refactor' tag has 1 memory", by_tag["refactor"], ["mem_test_ep_01"])
    assert_in("by_tag contains 'dashboard'", "dashboard", by_tag)
    assert_in("by_tag contains 'opencode'", "opencode", by_tag)
    assert_in("by_tag contains 'coordination'", "coordination", by_tag)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — atomic write verification (on-disk JSON matches return value)
# ─────────────────────────────────────────────────────────────────────────────

print("\n[5] atomic write — on-disk JSON matches return value")

with tempfile.TemporaryDirectory() as tmpd:
    root = Path(tmpd) / "memory"
    make_memory_tree(root)
    out_file = Path(tmpd) / "out_atomic.json"
    result = MA.aggregate_once(memory_root=root, output_file=out_file, verbose=False)

    # File exists and is well-formed JSON
    assert_true("output file exists", out_file.exists())
    on_disk = json.loads(out_file.read_text())
    assert_eq(
        "on-disk total_count matches", on_disk["total_count"], result["total_count"]
    )
    assert_eq(
        "on-disk memories keys match",
        sorted(on_disk["memories"].keys()),
        sorted(result["memories"].keys()),
    )
    assert_eq("on-disk schema_version", on_disk["_schema_version"], "1.0")
    assert_true("last_aggregated_ts present", bool(on_disk["last_aggregated_ts"]))
    assert_true(
        "last_aggregated_ts ends with Z", on_disk["last_aggregated_ts"].endswith("Z")
    )

    # Tmp file should NOT linger after rename
    tmp_path = out_file.with_suffix(".tmp")
    assert_true(".tmp file removed after atomic rename", not tmp_path.exists())

    # Re-running overwrites cleanly (no leftover keys)
    result2 = MA.aggregate_once(memory_root=root, output_file=out_file, verbose=False)
    on_disk2 = json.loads(out_file.read_text())
    assert_eq("re-run total_count stable", on_disk2["total_count"], 5)


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — partially-populated memory tree (only some kind dirs exist)
# ─────────────────────────────────────────────────────────────────────────────

print("\n[6] partial memory tree (only episodic/ exists)")

with tempfile.TemporaryDirectory() as tmpd:
    root = Path(tmpd) / "memory"
    (root / "episodic").mkdir(parents=True)
    (root / "episodic" / "only.json").write_text(
        json.dumps(
            {
                "id": "mem_only_one",
                "type": "episodic",
                "agent_id": "solo",
                "created_at": "2026-05-13T00:00:00Z",
                "title": "Solo memory",
                "tags": [],
            }
        )
    )
    out_file = Path(tmpd) / "out_partial.json"
    result = MA.aggregate_once(memory_root=root, output_file=out_file, verbose=False)
    assert_eq("partial-tree total_count == 1", result["total_count"], 1)
    assert_in("solo agent indexed", "solo", result["by_agent"])
    # Empty kinds still present as empty lists
    assert_eq("semantic empty list", result["by_kind"]["semantic"], [])
    assert_eq("procedural empty list", result["by_kind"]["procedural"], [])
    assert_eq("shared empty list", result["by_kind"]["shared"], [])


# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — schema fields the dashboard cares about
# ─────────────────────────────────────────────────────────────────────────────

print("\n[7] dashboard-expected fields present on every memory")

with tempfile.TemporaryDirectory() as tmpd:
    root = Path(tmpd) / "memory"
    make_memory_tree(root)
    out_file = Path(tmpd) / "out_fields.json"
    result = MA.aggregate_once(memory_root=root, output_file=out_file, verbose=False)

    required_per_mem = {
        "id",
        "kind",
        "agent",
        "ts",
        "title",
        "summary",
        "tags",
        "pinned",
        "verified",
        "confidence",
        "size",
    }
    for mem_id, mem in result["memories"].items():
        missing = required_per_mem - set(mem.keys())
        assert_true(
            f"{mem_id} has all required fields", not missing, f"missing keys: {missing}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n=== {_PASS} passed, {_FAIL} failed ===")
sys.exit(0 if _FAIL == 0 else 1)
