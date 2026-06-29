# gmux-system — Decision Log

A running log of project-level decisions. Most recent at the top.

---

## 2026-05-12 — PAUSE installer / packaging work

**Decision:** Stop development on `install.sh`, systemd service files, and
desktop shortcuts until the Tauri app itself is actually working end-to-end.

**Context:**
- An installer was drafted (`install.sh`) that would:
  - check deps (node/npm, rust/cargo, python3.11, bun, tmux)
  - install Python deps (faster-whisper, sounddevice, websockets, numpy)
  - install Node deps in `app/`
  - download the MediaPipe hand model into `models/`
  - write `~/.config/systemd/user/gmux-monitor.service` + enable/start it
  - write `~/.local/share/applications/gmux.desktop`
- Backend infrastructure (monitor on :8769, voice daemon on :8770) IS already
  running and observable — the pane state JSON is live, SSE works, ports bound.
- The blocking issue is that the Tauri app itself is not yet a reliable,
  user-facing experience. Packaging something that doesn't run cleanly is
  premature.

**What this means in practice:**
- ❌ Do NOT write/refine `install.sh` further right now.
- ❌ Do NOT create or modify the systemd unit file.
- ❌ Do NOT create or modify the `.desktop` entry.
- ❌ Do NOT spend time on "one-command install" UX, packaging scripts, AUR
  packaging, or release artefacts.
- ✅ DO focus on making `./scripts/launch.sh` reliably bring up a working
  Tauri window with the v3 UI, real PTY, and live status sidebar.
- ✅ DO fix any Tauri command bugs (open_agent, approve_agent, send_to_agent,
  PTY plumbing) before thinking about distribution.
- ✅ DO keep the backend (monitor.py, voice daemon) stable since that part
  already works.

**Resume condition:**
The installer work resumes once:
1. `./scripts/launch.sh` opens the Tauri app cleanly on a fresh shell.
2. The status sidebar shows live pane state from :8769.
3. Spawning an agent via the UI actually creates a new tmux window + opencode.
4. Permission approve/reject from the UI works against a real OpenCode session.
5. Voice (ws://localhost:8770) connects and transcribes into the UI.

Only after those five are green does packaging make sense.

**Owner:** fivelidz
**Logged by:** Claude (agent session)

---
