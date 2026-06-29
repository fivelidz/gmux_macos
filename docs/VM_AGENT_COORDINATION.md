# Coordinating with the AI agent running on the VM

There's another AI agent (running inside the sandbox VM) that is also working
on the gmux-system installation/deployment. To avoid stepping on each other,
we use a simple convention.

## Source of truth

- **Host machine** (`fivelidz`, this repo) — the **canonical source** for code
  changes. The host is where development happens; commits land here first.
- **VM** (`sandbox`, `192.168.122.100`, user `agent`) — a **deployment target**
  and **test environment**. The VM-AI is allowed to:
  - Install system packages
  - Run / restart the monitor + HTTP server
  - Modify `/tmp/*` files
  - Write to its own home directory
  - Write reports / test notes in `~/projects/gmux-system/docs/VM_REPORTS/`
- The VM-AI must **NOT** push code changes back into git. If it finds a
  needed fix, it writes the diff/notes into `docs/VM_REPORTS/<date>.md` and
  the host-AI rolls it forward.

## Sync protocol

### Host → VM (every deploy)
```bash
rsync -a --delete \
  --exclude .git \
  --exclude node_modules \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'app/src-tauri/target' \
  --exclude 'models/' \
  --exclude 'docs/VM_REPORTS' \
  ~/projects/gmux-system/ sandbox:~/projects/gmux-system/
```

The `--exclude docs/VM_REPORTS` is critical — that's the VM's outbox; the
host must not clobber it.

### VM → Host (every test run)
The VM-AI appends a markdown file like
`~/projects/gmux-system/docs/VM_REPORTS/2026-05-13-T0230.md` summarising:
- What it tried to install/run
- What worked, what failed (with logs)
- Any code-level fix it would suggest
- Whether it touched any system config (with diffs)

Then the host pulls reports back:
```bash
rsync -a sandbox:~/projects/gmux-system/docs/VM_REPORTS/ \
  ~/projects/gmux-system/docs/VM_REPORTS/
```

The host-AI reads these reports, applies fixes to source, commits, then
re-deploys.

## Process-name convention

When the VM-AI spawns processes it should set a recognisable process name so
the host can distinguish "stuff the VM-AI started" from "stuff a human did
manually":

```bash
exec -a "vmai-monitor" python3 backend/status/monitor.py
```

Patterns reserved for VM-AI use: `vmai-*`

## File-touch convention

Files the VM-AI is allowed to create or modify on the VM (no permission needed):
- `/tmp/*`
- `~/projects/gmux-system/docs/VM_REPORTS/*` (the outbox)
- `~/.local/share/gmux/` (runtime state)
- `~/.config/gmuxtest/` (UI state)

Files the VM-AI must NOT modify on the VM:
- Anything under `~/projects/gmux-system/` outside `docs/VM_REPORTS/`
  (the host owns this; rsync will overwrite the VM's copy on next deploy
  anyway, so VM edits are pointless)
- `/etc/*` (asks first)
- `~/.ssh/*`, `~/.gnupg/*` (asks first)

## What to ask the VM-AI to do (current open tasks)

Tracked here so when the host or VM-AI restarts, the next instance knows
what to pick up.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Verify `setsid python3 backend/status/monitor.py` runs and stays up across SSH disconnect | VM-AI | ✅ confirmed 2026-05-13 |
| 2 | Install Python deps without `--break-system-packages` if a venv is feasible | VM-AI | open |
| 3 | Document why `ghostty` crashes on the VM's QEMU virtio GPU (LLVM AVX2) | VM-AI | open |
| 4 | Test whether `tauri build` (release mode) works headless on VM with `Xvfb` | VM-AI | open |
| 5 | Bundle `hand_landmarker.task` model under `models/` so VMs don't need CDN | host-AI | open |
| 6 | Write `memory_aggregator.py` to produce `/tmp/gmuxtest-memory.json` | host-AI | open |

## How the VM-AI can communicate "I'm working on this now"

Drop a sentinel file:
```bash
echo "started at $(date -Iseconds)" > /tmp/vmai-busy.txt
```

The host-AI checks this before deploying. If present, host waits or notifies
the user.

When done:
```bash
rm /tmp/vmai-busy.txt
```

## Conflict resolution

If both host and VM-AI claim to have edited the same conceptual thing:
1. Host-side commits are authoritative for source code.
2. VM-side test results / logs / measurements are authoritative for "does
   this actually work on a CachyOS VM".
3. If they disagree on a code-level fact, the host re-deploys fresh from
   git, the VM-AI re-runs the test, and we get a definitive answer.
