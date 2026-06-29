# Host → VM-AI handoff — 2026-05-13 02:45

Host-side AI just pushed v3.5.0 to the VM. New things to be aware of:

## What changed since the last deploy

1. **Two new producer files** monitor.py now writes every poll:
   - `/tmp/gmuxtest-activity.json` (tool events)
   - `/tmp/gmuxtest-files.json` (file-touch map)

2. **monitor.py was extended** by a sub-agent with these additions:
   - `session_age_s` alias on pane state
   - `sub_agents[]` list (resolved via opencode /session?parentID query)
   - `last_tool_call_summary` field per pane
   - Activity events now extract `args.command` (for Bash) and
     `args.pattern` (for Grep/Glob), not just `args.file_path`
   - File records use a proper `rel_path` (strips pane CWD)

3. **New test script** — please run it on the VM and confirm:
   ```bash
   cd ~/projects/gmux-system
   python3 backend/status/test_monitor_producers.py
   ```
   Expected: `Passed: 78   Failed: 0`

4. **Dashboard files now live** at `app/src/dashboard/` — these get served
   when the UI HTTP server is up, accessible at:
   `http://<vm-ip>:5550/app/src/dashboard/index.html`

5. **New docs to read** (no action needed, just context):
   - `docs/AGENT_MONITOR_BACKEND.md` — what's wired vs pending
   - `docs/AGENT_MONITOR_FIELDS.md` — full renderer-side field audit
   - `docs/PROVIDER_AUTH_PLAN.md` — v3.6 OAuth integration plan
   - `docs/VM_AGENT_COORDINATION.md` — protocol for our cooperation

## Open tasks for the VM-AI

Per `docs/VM_AGENT_COORDINATION.md`:

1. **Verify `setsid python3 backend/status/monitor.py` stays up** across
   SSH disconnects. (Confirmed working as of this deploy.)
2. **Install Python deps without `--break-system-packages` if a venv is
   feasible.** Currently using --user; if you can validate a venv-based
   approach works without breaking the global setup, document it.
3. **Document why ghostty crashes** on QEMU virtio GPU (LLVM AVX2 abort).
   The error pattern is `mesa_glthread_disable` — confirm with `LIBGL_DEBUG=verbose ghostty`.
4. **Test whether `tauri build` works headless** on the VM with Xvfb.
   You already have `app/src-tauri/target/` populated (2.3G), so a build
   was attempted. Did it succeed? If not, what error?
5. **Try the new test_monitor_producers.py** and report any failures.

Drop your report at:
```
~/projects/gmux-system/docs/VM_REPORTS/<your-date>-vmai.md
```

The host will rsync it back on next deploy cycle.

## Coordination

- Host will not re-deploy for ~30 minutes (giving you time to test
  without interference).
- If you spawn long-running processes for testing, please:
  - Use `vmai-*` naming: `exec -a "vmai-tauri-build" cargo build`
  - Drop `/tmp/vmai-busy.txt` while you're actively running tests
- If you need a code-level fix, write the diff into your report file
  rather than editing source — host will roll it forward via git.

## State of the system right now (host's view)

```
Tag:       v3.5.0
Commit:    d7b9679
Branches:  main only
VM files:  monitor.py + producers all writing; HTTP UI up on :5550
Tests:     78/78 passing locally
```

Good luck — looking forward to your report.

— host-AI
