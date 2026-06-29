# Agent Monitor — Workshop

**Status:** Not working in the main app (alpha.11) — under reconstruction
in this isolated workspace.
**Owner:** the agent that picks this up next (could be one of: Claude
Code, OpenCode, aider, or a separate gmux sub-agent)

---

## What this folder is

A self-contained workshop for rebuilding the gmux Agent Monitor — the
**flow-chart display** that shows agents accessing different files in
different ways. It's currently broken in the main gmux app (we have an
empty window where the flowchart should be), and rather than keep
chasing the bug inside the production codebase, we're rebuilding it
here in isolation.

Once it works here, we'll integrate it back into `app/src/dashboard/`.

## Why it's separate

1. The main gmux app is already complex (~9800 lines of UI code, Tauri
   release-build quirks, etc.). Iterating on the Agent Monitor inside
   it has been slow and fragile.
2. A fresh agent picking this up shouldn't need to read the entire
   gmux codebase — just this folder + `spec/AGENT_MONITOR_SPEC.md`.
3. Once working, the integration is a focused file-replace, not a
   from-scratch merge.

## Folder layout

```
agent-monitor/
├── README.md                       ← this file
├── spec/
│   └── AGENT_MONITOR_SPEC.md       ← what to build, contracts, success criteria
├── src/
│   └── dashboard/                  ← the actual code being built
│       ├── index.html
│       ├── css/dashboard.css
│       └── js/{app,data,...}.js
├── docs/
│   ├── BACKEND_CONTRACT.md         ← how to read data from gmux backend
│   └── INTEGRATION_GUIDE.md        ← how to merge back into the main app
└── reference/                      ← context material for the new agent
    ├── current-state-of-broken.md
    └── working-screenshots/
```

## Getting started (for the new agent)

1. Read `spec/AGENT_MONITOR_SPEC.md` first. It tells you what to build.
2. Read `docs/BACKEND_CONTRACT.md`. It tells you what data sources to
   read from and what shape they have.
3. Open `src/dashboard/index.html` in your editor. That's the current
   (broken) starting point — feel free to gut it or keep what helps.
4. Test against live data:
   ```bash
   # In one terminal: make sure the gmux backend is running
   python3.11 ~/projects/gmux_v4/backend/status/monitor.py
   # In another: serve your dashboard
   cd ~/projects/gmux_v4/agent-monitor/src
   python3 -m http.server 5601
   # Open http://localhost:5601/dashboard/
   ```
5. When it's working in a browser, see `docs/INTEGRATION_GUIDE.md` to
   merge it back into the Tauri app.

## What "done" looks like

The Agent Monitor should show, AT MINIMUM:

- A list of agents that are **currently running** (not idle shells)
- For each agent: which **files they've touched** so far (historically)
  and **what they're currently working on**
- A flow visualisation that makes the file ↔ agent relationships
  visible at a glance (could be: a node graph, a heatmap, a timeline,
  or whatever is most legible — the SPEC has more detail)

It should NOT:
- Duplicate the main pane grid (that's already visible in the main app)
- Show idle/empty shell panes
- Require the user to refresh manually — data is live

## Coordination

If a human or another agent is also working on this folder, leave a
note in `notes/CURRENT_OWNER.md` so we don't conflict. Use the
existing patterns in `~/projects/gmux_v4/HANDOVER.md` for handoff.

## Where the existing broken version lives in the main app

For reference (don't edit these from the workshop — work in this
folder first, then integrate):

- `~/projects/gmux_v4/app/src/dashboard/` — the broken version
- `~/projects/gmux_v4/app/src-tauri/src/lib.rs` — `open_dashboard` cmd
- `~/projects/gmux_v4/app/src-tauri/tauri.conf.json` — `dashboard`
  window registration
- `~/projects/gmux_v4/docs/AGENT_MONITOR_DEBUG.md` — history of what
  we've tried so far + what's been ruled out
