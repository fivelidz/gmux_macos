#!/usr/bin/env python3.11
"""
seed_memory.py — write a handful of fake memory files for dashboard testing.

Run once:
    python3 tools/seed_memory.py

This populates `~/.local/share/gmux/memory/{episodic,semantic,procedural,shared}/`
with 8 example memory entries spanning multiple agents, kinds, and tags.
Useful for manually verifying the Memory tab in the dashboard before any
real agent has produced anything.

This script is for TESTING ONLY. It is never invoked automatically and is
not wired into monitor.py / aggregator daemons.

Re-running is idempotent — files are overwritten by id (deterministic names).
Add --clear to delete the seeded files first.
"""

import argparse
import json
import sys
import time
from pathlib import Path

MEMORY_ROOT = Path.home() / ".local" / "share" / "gmux" / "memory"

# 8 fake memories spanning 4 kinds, 4 agents, plus shared memories
SEEDS = [
    {
        "_kind_dir": "episodic",
        "id": "mem_seed_ep_01",
        "type": "episodic",
        "agent_id": "pane-1",
        "agent_name": "doofing",
        "session_id": "ses_seed_doofing",
        "created_at": "2026-05-13T09:14:03Z",
        "updated_at": "2026-05-13T09:14:03Z",
        "title": "Refactored auth.py to use SAML middleware",
        "body": "Replaced custom OAuth handler with django-saml2-auth. The custom one was failing on assertion-encrypted responses.",
        "tags": ["auth", "saml", "refactor", "django"],
        "produced_by": "agent_self",
        "confidence": 0.9,
        "verified": False,
    },
    {
        "_kind_dir": "episodic",
        "id": "mem_seed_ep_02",
        "type": "episodic",
        "agent_id": "pane-4",
        "agent_name": "ai_UI",
        "created_at": "2026-05-13T10:21:18Z",
        "title": "Built memory tab v1 prototype",
        "body": "Tabs render but the data source is empty — need memory_aggregator.py.",
        "tags": ["dashboard", "memory", "ui"],
        "produced_by": "agent_self",
        "confidence": 1.0,
    },
    {
        "_kind_dir": "semantic",
        "id": "mem_seed_sem_01",
        "type": "semantic",
        "agent_id": "graphify",
        "created_at": "2026-05-13T08:00:00Z",
        "title": "voice_router.py is a god-node (9 callers)",
        "body": "Identified via graphify call-graph analysis. Editing this file affects 9 downstream consumers.",
        "tags": ["graph", "god-node", "voice"],
        "produced_by": "graphify",
        "confidence": 0.95,
        "verified": True,
    },
    {
        "_kind_dir": "semantic",
        "id": "mem_seed_sem_02",
        "type": "semantic",
        "agent_id": "pane-6",
        "agent_name": "voice-router",
        "created_at": "2026-05-13T11:02:45Z",
        "title": "OpenCode SSE events include parentID for sub-sessions",
        "body": "Confirmed by reading /session/<id> — sub-agents always have parentID set; top-level sessions don't.",
        "tags": ["opencode", "api", "sub-agents"],
        "produced_by": "agent_self",
        "confidence": 0.85,
    },
    {
        "_kind_dir": "procedural",
        "id": "mem_seed_proc_01",
        "type": "procedural",
        "agent_id": "human",
        "created_at": "2026-05-12T22:00:00Z",
        "title": "How to deploy gmux to a VM",
        "body": "1. Run scripts/install-vm.sh\n2. Source `.env`\n3. Start systemd user services\n4. Verify port 8769 responds",
        "tags": ["deploy", "vm", "ops", "playbook"],
        "produced_by": "human",
        "confidence": 1.0,
        "verified": True,
        "pinned": True,
    },
    {
        "_kind_dir": "procedural",
        "id": "mem_seed_proc_02",
        "type": "procedural",
        "agent_id": "pane-1",
        "agent_name": "doofing",
        "created_at": "2026-05-13T07:30:00Z",
        "title": "Pattern: atomic JSON write via tmpfile+rename",
        "body": "Always write `/tmp/foo.tmp` first then `os.rename(tmp, target)`. POSIX guarantees atomicity.",
        "tags": ["pattern", "io", "json"],
        "produced_by": "agent_self",
        "confidence": 0.99,
    },
    {
        "_kind_dir": "shared",
        "id": "mem_seed_share_01",
        "type": "shared",
        "agent_id": "monitor",
        "created_at": "2026-05-13T12:00:00Z",
        "title": "pane-4 is editing the dashboard files",
        "body": "Heads-up to other agents — touch_30m on dashboard/js/*.js is high. Coordinate before editing.",
        "tags": ["coordination", "hot-files"],
        "produced_by": "monitor",
        "confidence": 1.0,
        "shared_with": ["*"],
    },
    {
        "_kind_dir": "shared",
        "id": "mem_seed_share_02",
        "type": "shared",
        "agent_id": "human",
        "created_at": "2026-05-13T13:11:00Z",
        "title": "Decision: memory aggregator runs inside monitor.py",
        "body": "Per v3.7 — no separate daemon; aggregate_once() called from the monitor's existing aggregate worker.",
        "tags": ["decision", "architecture"],
        "produced_by": "human",
        "confidence": 1.0,
        "verified": True,
        "pinned": True,
        "shared_with": ["*"],
    },
]


def _clear_seeded(root: Path) -> int:
    """Remove only the files this script seeded (matched by id prefix)."""
    removed = 0
    for kind_dir in root.iterdir() if root.exists() else []:
        if not kind_dir.is_dir():
            continue
        for fpath in kind_dir.glob("mem_seed_*.json"):
            try:
                fpath.unlink()
                removed += 1
            except Exception as e:
                print(f"  could not remove {fpath}: {e}", file=sys.stderr)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write a handful of fake memory files for dashboard testing."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete previously-seeded files (mem_seed_*.json) and exit.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=MEMORY_ROOT,
        help=f"Memory root directory (default: {MEMORY_ROOT}).",
    )
    args = parser.parse_args()

    root: Path = args.root

    if args.clear:
        n = _clear_seeded(root)
        print(f"[seed_memory] Removed {n} seed file(s) from {root}")
        return

    written = 0
    for seed in SEEDS:
        kind_dir = root / seed["_kind_dir"]
        kind_dir.mkdir(parents=True, exist_ok=True)
        out_path = kind_dir / f"{seed['id']}.json"
        payload = {k: v for k, v in seed.items() if not k.startswith("_")}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written += 1

    print(f"[seed_memory] Wrote {written} seed memories under {root}")
    print(f"[seed_memory] Now run: python3 backend/status/memory_aggregator.py")


if __name__ == "__main__":
    main()
