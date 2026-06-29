#!/usr/bin/env python3.11
"""
memory_aggregator.py — aggregate raw memory JSON files into a single index.

Reads `~/.local/share/gmux/memory/{episodic,semantic,procedural,shared}/*.json`
and writes a merged index to `/tmp/gmuxtest-memory.json`.

Data contract: Knowledge_systems/gmux_memory_integration/docs/02_DATA_CONTRACTS.md
Schema version 1.0.

Usage
-----
  # One-shot (used by monitor.py integration)
  python3 memory_aggregator.py

  # Daemon mode — re-aggregates every N seconds (default 10)
  python3 memory_aggregator.py --daemon [--interval 10]

  # Watch mode — inotify if available, else polling fallback
  python3 memory_aggregator.py --watch [--interval 10]

Public API (for monitor.py integration)
-----------------------------------------
  from memory_aggregator import aggregate_once
  aggregate_once()   # safe to call from any thread; errors are caught + logged

Output schema
-------------
{
  "_schema_version": "1.0",
  "memories": {
    "<memory_id>": {
      "id":       "mem_…",
      "kind":     "episodic"|"semantic"|"procedural"|"shared",
      "agent":    "<agent_id or agent_name>",
      "ts":       "ISO-8601",
      "summary":  "…",
      "tags":     [],
      "size":     1234,       # raw bytes of the source file
      "pinned":   false,
      "verified": false,
      "confidence": 0.5,
      "title":    "…",        # alias of summary for UI compat
      "sources":  [],
      "links":    [],
      "shared_with": []
    }
  },
  "by_agent":  { "<agent>":  ["mem_id", …] },
  "by_kind":   { "episodic": ["mem_id", …], "semantic": […], … },
  "by_tag":    { "<tag>":    ["mem_id", …] },
  "total_count":         42,
  "last_aggregated_ts":  "ISO-8601"
}

Memory source file schema (minimum required fields)
---------------------------------------------------
  { "id": "…", "kind": "…", "agent_id": "…", "created_at": "…",
    "title": "…", "tags": [] }

All unknown fields are forwarded into the memory entry unchanged.
Files missing required fields are skipped with a warning.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────────

MEMORY_ROOT = Path.home() / ".local" / "share" / "gmux" / "memory"
MEMORY_KINDS = ("episodic", "semantic", "procedural", "shared")
OUTPUT_FILE = Path("/tmp/gmuxtest-memory.json")
SCHEMA_VERSION = "1.0"
DEFAULT_INTERVAL = 10  # seconds between re-aggregations in daemon/watch mode
# Required keys in each raw memory file
_REQUIRED_KEYS = {"id"}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _iso_now() -> str:
    """ISO-8601 UTC timestamp with Z suffix (no milliseconds)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalise_entry(raw: dict, kind: str, file_size: int) -> Optional[dict]:
    """Convert a raw memory dict into the aggregator's canonical shape.

    Returns None if the file is missing required keys (caller skips it).

    Field mapping
    ~~~~~~~~~~~~~
    The raw schema (02_DATA_CONTRACTS.md §memory entry) uses:
      type / kind        → normalised as "kind"
      agent_id           → "agent"
      created_at         → "ts"
      title              → "summary" (also kept as "title" for UI compat)

    Any extra fields in the raw file are forwarded transparently.
    """
    if not isinstance(raw, dict):
        return None

    # Check minimum required keys
    for k in _REQUIRED_KEYS:
        if k not in raw:
            return None

    mem_id: str = str(raw["id"])

    # Resolve kind: prefer the "type" key (schema uses "type"), fall back to
    # the "kind" key, fall back to the directory name we already know.
    resolved_kind = raw.get("type") or raw.get("kind") or kind

    # Agent: prefer agent_id; fall back to agent_name; else "unknown"
    agent = (
        raw.get("agent_id") or raw.get("agent_name") or raw.get("agent") or "unknown"
    )

    # Timestamp: prefer created_at; fall back to updated_at; else empty
    ts = raw.get("created_at") or raw.get("updated_at") or raw.get("ts") or ""

    # Summary/title — the UI shows whichever is present
    title = raw.get("title") or raw.get("summary") or ""
    summary = title  # alias

    tags: list = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).lower() for t in tags]

    entry: dict = {
        # Core identity
        "id": mem_id,
        "kind": resolved_kind,
        "agent": agent,
        "ts": ts,
        # Display
        "title": title,
        "summary": summary,
        # Classification
        "tags": tags,
        # Quality
        "pinned": bool(raw.get("pinned", False)),
        "verified": bool(raw.get("verified", False)),
        "confidence": float(raw.get("confidence", 0.5)),
        # Provenance
        "produced_by": raw.get("produced_by", ""),
        "session_id": raw.get("session_id"),
        # Relations / sharing
        "sources": raw.get("sources") or [],
        "links": raw.get("links") or [],
        "shared_with": raw.get("shared_with") or [],
        # Meta
        "size": file_size,
        # Preserve any extra fields the writer included
        **{
            k: v
            for k, v in raw.items()
            if k
            not in {
                "id",
                "type",
                "kind",
                "agent_id",
                "agent_name",
                "agent",
                "created_at",
                "updated_at",
                "ts",
                "title",
                "summary",
                "tags",
                "pinned",
                "verified",
                "confidence",
                "produced_by",
                "session_id",
                "sources",
                "links",
                "shared_with",
            }
        },
    }
    return entry


def _build_empty_output() -> dict:
    """Return the empty aggregated structure (used when memory dir is missing/empty)."""
    return {
        "_schema_version": SCHEMA_VERSION,
        "memories": {},
        "by_agent": {},
        "by_kind": {k: [] for k in MEMORY_KINDS},
        "by_tag": {},
        "total_count": 0,
        "last_aggregated_ts": _iso_now(),
    }


# ── Core aggregation ──────────────────────────────────────────────────────────


def aggregate_once(
    memory_root: Path = MEMORY_ROOT,
    output_file: Path = OUTPUT_FILE,
    verbose: bool = False,
) -> dict:
    """Walk memory dirs, parse files, write aggregated JSON.

    Safe to call from any thread — atomic write guarantees the output file is
    never in a partially-written state.

    Returns the aggregated dict (useful for tests / callers that want the data
    without touching disk).
    """
    out = _build_empty_output()
    memories: dict = {}
    by_agent: dict = {}
    by_kind: dict = {k: [] for k in MEMORY_KINDS}
    by_tag: dict = {}

    if not memory_root.exists():
        # Dir absent — write empty structure, return gracefully
        if verbose:
            print(
                f"[memory_aggregator] Memory root not found: {memory_root}",
                file=sys.stderr,
            )
        _write_output(out, output_file)
        return out

    skipped = 0
    parsed = 0

    for kind in MEMORY_KINDS:
        kind_dir = memory_root / kind
        if not kind_dir.exists():
            continue

        try:
            entries_iter = kind_dir.iterdir()
        except PermissionError as e:
            print(f"[memory_aggregator] Cannot read {kind_dir}: {e}", file=sys.stderr)
            continue

        for fpath in entries_iter:
            if fpath.suffix.lower() != ".json":
                continue

            try:
                file_size = fpath.stat().st_size
                text = fpath.read_text(encoding="utf-8")
            except Exception as e:
                if verbose:
                    print(
                        f"[memory_aggregator] Cannot read {fpath}: {e}", file=sys.stderr
                    )
                skipped += 1
                continue

            try:
                raw = json.loads(text)
            except json.JSONDecodeError as e:
                if verbose:
                    print(
                        f"[memory_aggregator] Malformed JSON in {fpath}: {e}",
                        file=sys.stderr,
                    )
                skipped += 1
                continue

            entry = _normalise_entry(raw, kind, file_size)
            if entry is None:
                if verbose:
                    print(
                        f"[memory_aggregator] Missing required keys in {fpath}",
                        file=sys.stderr,
                    )
                skipped += 1
                continue

            mem_id = entry["id"]
            # Dedup: last-write-wins if the same id appears in multiple dirs
            memories[mem_id] = entry
            parsed += 1

            # Index: by_agent
            agent = entry["agent"]
            by_agent.setdefault(agent, [])
            if mem_id not in by_agent[agent]:
                by_agent[agent].append(mem_id)

            # Index: by_kind (use the resolved kind, not the dir name)
            ek = entry["kind"]
            by_kind.setdefault(ek, [])
            if mem_id not in by_kind[ek]:
                by_kind[ek].append(mem_id)

            # Index: by_tag
            for tag in entry["tags"]:
                by_tag.setdefault(tag, [])
                if mem_id not in by_tag[tag]:
                    by_tag[tag].append(mem_id)

    out = {
        "_schema_version": SCHEMA_VERSION,
        "memories": memories,
        "by_agent": by_agent,
        "by_kind": by_kind,
        "by_tag": by_tag,
        "total_count": len(memories),
        "last_aggregated_ts": _iso_now(),
    }

    if verbose:
        print(
            f"[memory_aggregator] Parsed {parsed} memories, skipped {skipped}. "
            f"Total: {len(memories)}.",
            flush=True,
        )

    _write_output(out, output_file)
    return out


def _write_output(data: dict, output_file: Path) -> None:
    """Atomic write: tmpfile + rename (POSIX rename is atomic)."""
    try:
        tmp = output_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.rename(output_file)
    except Exception as e:
        print(f"[memory_aggregator] Write failed ({output_file}): {e}", file=sys.stderr)


# ── Watch / daemon modes ──────────────────────────────────────────────────────


def _try_inotify_watch(memory_root: Path, interval: int, output_file: Path) -> bool:
    """Attempt to use inotify (Linux only) for efficient change detection.

    Returns True if inotify was used (loop ran forever), False if unavailable.
    Falls back to polling gracefully.
    """
    try:
        # inotify_simple or pyinotify — both optional.  We use the lower-level
        # os-level inotify syscall via ctypes only if neither is available.
        # For stdlib-only compliance we do a ctypes approach — but most distros
        # won't have inotify bindings anyway.  We signal "not available" and the
        # caller falls through to polling.
        import ctypes
        import ctypes.util

        libc_name = ctypes.util.find_library("c")
        if not libc_name:
            return False
        libc = ctypes.CDLL(libc_name, use_errno=True)

        IN_CLOSE_WRITE = 0x00000008
        IN_MOVED_TO = 0x00000080
        IN_CREATE = 0x00000100
        IN_DELETE = 0x00000200
        WATCH_MASK = IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE | IN_DELETE

        # inotify_init1
        inotify_init1 = getattr(libc, "inotify_init1", None)
        inotify_add_watch = getattr(libc, "inotify_add_watch", None)
        if not inotify_init1 or not inotify_add_watch:
            return False

        fd = inotify_init1(0)
        if fd < 0:
            return False

        # Watch each kind subdirectory
        watched = 0
        for kind in MEMORY_KINDS:
            kind_dir = memory_root / kind
            if kind_dir.exists():
                wd = inotify_add_watch(fd, str(kind_dir).encode(), WATCH_MASK)
                if wd >= 0:
                    watched += 1

        if not watched:
            os.close(fd)
            return False

        print(
            f"[memory_aggregator] inotify watching {watched} dirs "
            f"(fallback poll every {interval}s)",
            flush=True,
        )

        # Event struct: wd(i) mask(I) cookie(I) len(I) + name[len]
        EVENT_SIZE = 16  # 4 ints × 4 bytes (wd is int not uint, but same size)
        import select

        # Do an initial aggregation
        aggregate_once(memory_root=memory_root, output_file=output_file, verbose=True)

        last_poll = time.time()
        while True:
            # Wait up to `interval` seconds for an inotify event
            ready = select.select([fd], [], [], interval)
            if ready[0]:
                # Drain all pending events (we don't need the details, just "changed")
                try:
                    os.read(fd, 4096)
                except OSError:
                    pass
                aggregate_once(
                    memory_root=memory_root, output_file=output_file, verbose=True
                )
                last_poll = time.time()
            elif time.time() - last_poll >= interval:
                # Periodic fallback in case inotify missed something
                aggregate_once(
                    memory_root=memory_root, output_file=output_file, verbose=True
                )
                last_poll = time.time()

    except Exception:
        return False

    return True  # never reached in normal operation


def run_daemon(interval: int, output_file: Path, verbose: bool = True) -> None:
    """Poll-based daemon: re-aggregate every `interval` seconds."""
    print(
        f"[memory_aggregator] Daemon mode — polling every {interval}s → {output_file}",
        flush=True,
    )
    while True:
        try:
            aggregate_once(
                memory_root=MEMORY_ROOT, output_file=output_file, verbose=verbose
            )
        except Exception as e:
            print(f"[memory_aggregator] aggregate_once error: {e}", file=sys.stderr)
        time.sleep(interval)


def run_watch(interval: int, output_file: Path) -> None:
    """Watch mode: inotify if available, polling fallback."""
    print(
        f"[memory_aggregator] Watch mode — inotify preferred, polling fallback every {interval}s",
        flush=True,
    )

    # Only attempt inotify on Linux
    if sys.platform.startswith("linux") and MEMORY_ROOT.exists():
        used = _try_inotify_watch(MEMORY_ROOT, interval, output_file)
        if used:
            return  # the inotify loop ran forever

    # Fallback: polling
    print(
        f"[memory_aggregator] inotify not available — falling back to {interval}s polling",
        flush=True,
    )
    run_daemon(interval, output_file, verbose=True)


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    # MEMORY_ROOT may be overridden via --memory-root. The `global` declaration
    # must appear before any *use* of the name in this scope, including the
    # parser.add_argument(default=MEMORY_ROOT) line below.
    global MEMORY_ROOT
    parser = argparse.ArgumentParser(
        description="Aggregate gmux memory files into a single JSON index.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode, re-aggregating every --interval seconds.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help=(
            "Watch for file-system changes (inotify on Linux; "
            "falls back to polling when inotify is unavailable)."
        ),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        metavar="SECS",
        help=f"Seconds between re-aggregations in daemon/watch mode (default: {DEFAULT_INTERVAL}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        metavar="FILE",
        help=f"Output file path (default: {OUTPUT_FILE}).",
    )
    parser.add_argument(
        "--memory-root",
        type=Path,
        default=MEMORY_ROOT,
        metavar="DIR",
        help=f"Root directory for memory files (default: {MEMORY_ROOT}).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print per-file details to stderr.",
    )
    args = parser.parse_args()

    # Override module-level MEMORY_ROOT if a custom path was given
    # (affects aggregate_once defaults; daemon/watch modes pass it explicitly)
    MEMORY_ROOT = args.memory_root

    if args.watch:
        run_watch(args.interval, args.output)
    elif args.daemon:
        run_daemon(args.interval, args.output, verbose=args.verbose)
    else:
        # One-shot
        result = aggregate_once(
            memory_root=args.memory_root,
            output_file=args.output,
            verbose=True,
        )
        total = result["total_count"]
        kinds = {k: len(v) for k, v in result["by_kind"].items() if v}
        agents = list(result["by_agent"].keys())
        print(f"[memory_aggregator] {total} memories written to {args.output}")
        if kinds:
            print(f"  kinds:  {kinds}")
        if agents:
            print(f"  agents: {agents}")


if __name__ == "__main__":
    main()
