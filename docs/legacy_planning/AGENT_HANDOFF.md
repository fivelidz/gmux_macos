# Agent Handoff — current state of the repo

**Always read this last** when starting a new session. Always update it
when finishing.

---

## Where we are right now

**As of:** 2026-05-17 17:30 (docs-pivot session)
**Last touched by:** Claude (Sonnet 4.6) via opencode
**Current phase:** **Phase −1 — Documentation complete; Phase 0 next**
**Next phase:** Phase 0 — Scaffold (real Tauri/Vite/Rust code)
**Repo:** private at `github.com/fivelidz/gmux-v4`
**Working directory:** `/home/fivelidz/projects/gmux_v4/`

---

## Most-recent session summary

### Big direction pivot
The user clarified that **v4 is the all-in-one successor to v3**, not
a sibling product. v3 gets archived when v4.0.0 ships. v4 absorbs:
- Desktop app (Linux/macOS/Windows)
- Headless mode (was v3's `monitor.py + http.server` combo)
- Phone bridge (was v3's planned `bridge.py`)
- Voice + gesture (lifted from v3 UI, voice daemon stays as optional sidecar)
- Agent monitor dashboard, sub-agents, todos, activity log
- All of v3's UI

### Additional spec requested
The user emphasised:
- "Efficient agent handling in backend with minimal fuss"
- "Keep todo lists and markers" as first-class features

This drove the **`AGENT_LIFECYCLE.md`** doc (new this session): a
detailed spec for how v4 tracks agents end-to-end with:
- Single in-process state store (no `/tmp/*.json` shuffling)
- Event bus via tokio broadcast channels
- SQLite-backed persistence with autosave
- First-class todos per agent with checkbox UI + persistence
- Typed activity log (500-event rolling buffer + DB)
- Sub-agent registry with parent-child links
- Permission store for pending approvals
- 30s Anthropic usage cache with 429-aware TTL

### What I did this session

1. Rewrote **`docs/OBJECTIVES.md`** — replaced sibling-product framing
   with all-in-one successor scope. Added 9 new goals (N1-N9) covering
   cross-platform, latency, usage API, todos, activity, UTF-8, install
   simplicity, phone bridge, headless mode. New success-criteria
   checklist with explicit "state management" section.

2. Wrote **`docs/AGENT_LIFECYCLE.md`** (new, ~600 lines) — the core
   backend spec. Full Agent struct, state machine diagram, lifecycle
   phases (spawn, activity, interaction, sub-agent, termination),
   todo/activity/permission systems, SQLite schema, event bus pattern,
   Tauri command surface.

3. Rewrote **`docs/ARCHITECTURE.md`** — removed sidecar references,
   centralised all state in the Tauri process, added explicit comparison
   with v3 showing what we eliminated.

4. Rewrote **`docs/PHASES.md`** — 8 phases now (was 7):
   - Phase 0 — Scaffold
   - Phase 1 — PTY core (Linux)
   - Phase 2 — **Agent layer + state stores** (new this version)
   - Phase 3 — opencode SSE + usage tracking
   - Phase 4 — Full v3 UI integration
   - Phase 5 — Phone bridge + headless
   - Phase 6 — Cross-platform
   - Phase 7 — Polish + release

5. Rewrote **`docs/TODO.md`** to match the new phase structure with
   granular sub-tasks for the new Phase 2 (agent layer).

6. Updated **`README.md`** to reflect successor framing.

### What I did NOT do

- No source code yet. The scaffold (Phase 0) will start next session.
- No commits yet from this session — about to commit now.

---

## State of files

```
gmux_v4/
├── .gitignore
├── LICENSE
├── README.md                       ← updated for successor scope
└── docs/
    ├── AGENT_HANDOFF.md            ← this file (updated)
    ├── AGENT_LIFECYCLE.md          ← NEW: core backend spec
    ├── ARCHITECTURE.md             ← rewritten
    ├── CONTRIBUTING.md             ← unchanged from initial
    ├── FROM_MAESTRO.md             ← unchanged
    ├── FROM_V3.md                  ← unchanged (still valid)
    ├── OBJECTIVES.md               ← rewritten for successor
    ├── PHASES.md                   ← rewritten with 8 phases
    └── TODO.md                     ← rewritten with new Phase 2
```

**No source code yet.** That's still true. Phase 0 starts next.

---

## What to do next

### If you're picking this up cold:

1. **Read** in this order:
   - `README.md`
   - `docs/OBJECTIVES.md`
   - `docs/ARCHITECTURE.md`
   - `docs/AGENT_LIFECYCLE.md`  ← **THE critical spec**
   - `docs/PHASES.md`
   - `docs/TODO.md`
   - `docs/FROM_V3.md`, `docs/FROM_MAESTRO.md`
   - `docs/CONTRIBUTING.md`
   - This file (last)

2. **Start Phase 0** (Scaffold) from `docs/TODO.md`. The first sub-task
   is creating `package.json`. Then `vite.config.js`, then the Rust
   scaffold. After `npm run tauri:dev` opens a window and IPC works,
   commit + tag `v0.1.0-scaffold` and update this file.

3. **End your session by:**
   - Marking completed boxes `[x]` in `docs/TODO.md`
   - Updating this `AGENT_HANDOFF.md` with what you did
   - Tagging if you reached a milestone
   - `git push --tags`

---

## Open decisions

| Decision | Status | Notes |
|---|---|---|
| v4 is all-in-one successor (not sibling) | **YES** | This session's pivot |
| Use React in frontend? | NO | Lift v3 vanilla-JS UI |
| Add Tauri auto-updater in v1.0? | YES | Phase 7 |
| Cloud relay for phone bridge in v1? | NO | LAN + Tailscale ships; relay is v4.1 |
| Persist sessions across app restart? | **NO (PTYs)** / YES (todos, activity, agent metadata) | PTYs die with the process; we accept this trade-off. State around them persists. |
| Code-sign macOS .dmg in v1? | YES | Phase 7 |
| Code-sign Windows .msi in v1? | YES if cheap | Phase 7 |
| Bundle MCP server (like maestro)? | NO | Use opencode SSE + our own activity log |
| Bundle git worktree feature? | NO | Defer to v4.1 |
| Use SQLite vs append-only log? | **SQLite** | rusqlite is mature; easier queries |
| Per-event UI emit vs batched? | **Both** | PTY output 16ms-batched; agent updates per-event |
| Headless mode in v1? | **YES** | Replaces v3's `monitor.py + http.server` |
| Voice daemon shipped with installer? | NO | Optional sidecar; user does separate pip install |

---

## Issues / blockers

None. Everything is documented and ready for Phase 0 work.

---

## Useful commands

When you're ready to start coding:

```bash
cd ~/projects/gmux_v4

# Sanity check
git log --oneline -5
git status
cat docs/TODO.md | head -60   # Phase 0 tasks visible

# Begin Phase 0 — first file is package.json
```

After Phase 0:

```bash
npm install
npm run tauri:dev   # opens a Tauri window
```

---

## Reference paths (all read-only)

```bash
# v3 reference repo (HUGE — has the UI we'll lift in Phase 4)
ls ~/projects/gmux-system/

# Maestro reference (PTY architecture)
ls ~/projects/github_repos/maestro/src-tauri/src/

# gmux-phone reference (frozen v0.6.1 contract for Phase 5)
ls ~/projects/gmux-phone/

# v3's maestro deep-dive (where the AGENT_LIFECYCLE inspiration came from)
ls ~/projects/gmux-system/docs/maestro_study/
```

---

## How to update this file

End of every session, replace the "Most-recent session summary"
section with your own summary, and update:
- "Where we are right now" (date, phase)
- "Open decisions" if any new ones made
- "Issues / blockers" if any
