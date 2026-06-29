# Agent Monitor — Specification

**Version:** 1.0 (initial spec for the rebuild)
**Last updated:** 2026-05-17 alpha.11 era
**For:** the agent picking this up next

---

## One-paragraph summary

The Agent Monitor is a **second window** (separate from the main gmux
pane grid) that shows, at a glance, **which AI agents are currently
running and which files they've each touched**. Its core view is a
flow visualisation — agents on one side, files on the other, lines
connecting them, animated as new tool calls happen.

The main gmux window already shows individual pane state (tasks, RAM,
chat). The Agent Monitor is for the **whole-system view** — "what
is everyone collectively doing across all my projects right now?"

---

## What the user wants to see

### Mandatory (MVP)

1. **Only running agents** — filter out idle shells, dormant panes,
   anything that doesn't have `has_ai: true` or `state ∈ {working,
   waiting, permission, sub_permission, rate_limited}`.

2. **Files touched** — for each agent, the full historical list of
   files it has read, written, edited, or executed. Sourced from
   `/tmp/gmuxtest-files.json` (path-keyed, see backend contract).

3. **Currently working on** — the tool currently in flight (read,
   edit, bash, etc.) and on which file/path. Sourced from each
   agent's `current_tool` field + the latest entry in
   `tool_history`.

4. **Live updates** — the view auto-refreshes whenever new data
   arrives. No manual refresh button needed.

### Nice-to-have (V2)

5. A **timeline** showing when each file was touched, which agent
   touched it, and what kind of operation.

6. **Cross-agent file sharing** — visual indicator when multiple
   agents have touched the same file (hotspot, conflict signal).

7. **Lineage** — for sub-agents (spawned from another agent), show
   the parent-child relationship.

8. **Memory recall** — link to the memory-aggregator output
   (`/tmp/gmuxtest-memory.json`) so user can see what each agent
   has stored about a file.

### Explicitly out of scope

- Per-pane chat (already in main gmux window)
- RAM / CPU bars per pane (already in main app's pane cards)
- Sending messages to agents (use the main app's chat)
- Approve / Reject permissions (already in main app)

---

## Data sources

All from `/tmp/`, written by `~/projects/gmux_v4/backend/status/monitor.py`.

| File | Updated | Contents (top level) |
|---|---|---|
| `/tmp/gmuxtest-pane-state.json` | every 2s | `{pane_id: {…agent fields…}}` |
| `/tmp/gmuxtest-files.json` | every ~10s | `{abs_path: {…file fields…}}` |
| `/tmp/gmuxtest-activity.json` | event-driven | `{events: [{ts, agent, tool, path, …}, …]}` |
| `/tmp/gmuxtest-memory.json` | every 30s | `{total_count, by_agent, by_kind, …}` |

See `docs/BACKEND_CONTRACT.md` for full field schemas.

The Tauri release-mode wrapper emits these as events too:
- `gmux-state`     ↔ `gmuxtest-pane-state.json`
- `files-update`   ↔ `gmuxtest-files.json`
- `activity-tick`  ↔ `gmuxtest-activity.json`
- `memory-update`  ↔ `gmuxtest-memory.json`

Use **Tauri events when running embedded** (in the Tauri webview) and
**HTTP fetch to monitor.py on :8769** when running standalone (browser
dev).

---

## Suggested visualisation

The current broken version has a complicated flow-rendering system
(`js/flow_render.js`, `js/flow_pulses.js`, `js/flow_layout.js`).
You don't have to keep it — feel free to pick whatever is clearest.
Three options ranked:

### Option A — Two-column flow graph (the original intent)
- Left column: agent cards (running agents only)
- Right column: file cards (files touched)
- Lines between them: animated when a tool call fires
- Highlights: hotspot files (touched by ≥2 agents) glow
- This is what the broken `flow_render.js` was trying to do.

### Option B — Force-directed graph
- Each agent + each file is a node
- Edges are tool calls
- Repulsion physics keeps the layout legible
- Library: d3-force, vivagraphjs, cytoscape.js, or hand-rolled

### Option C — Timeline + heatmap
- X axis: time
- Y axis: file paths (most-touched files at top)
- Cells: coloured by which agent touched, animated for current tool
- Simpler than a graph; loses spatial intuition but easier to follow

**Pick whichever you can ship working in a day.** A clean Option C is
better than a half-broken Option A.

---

## Layout requirements

- **Top bar**: session selector, source indicator (live | mock),
  build version (so user can confirm what build they're looking at).
- **Main area**: the visualisation. Fills the rest of the viewport.
- **Right side panel (collapsible)**: details of the selected agent
  OR selected file (clicking either should populate this).
- **Bottom**: thin status strip — N agents tracked, M files,
  last update time.

Make it work on a **1600×1000 window** (Tauri default — see
`tauri.conf.json` `dashboard` window). Resizable. No fixed pixel
positions that break when the window is resized.

---

## Success criteria

The Agent Monitor is "done" when:

- [ ] Opens via clicking "Agent Monitor" in the main gmux Views menu
  (the Tauri integration). For workshop work: opens as a standalone
  browser tab.
- [ ] Shows only agents that are actively running (filter described
  above).
- [ ] For each running agent, lists every file it has touched
  historically (path + count of operations).
- [ ] Highlights the file the agent is currently working on (matches
  `current_tool` + last tool_history entry).
- [ ] Updates live (within ≤3 seconds) when an agent fires a new tool
  call.
- [ ] Survives the main app being closed (i.e., it's its own window).
- [ ] Works in BOTH `npm run tauri dev` (Vite-served) AND release
  builds (`npm run tauri build`). The current broken version only
  works in dev mode.
- [ ] Doesn't crash if any of the `/tmp/gmuxtest-*.json` files is
  missing or empty (degrades to "waiting for data" placeholder).

---

## Anti-goals / non-requirements

- Don't try to replace the main gmux pane grid — it's its own thing.
- Don't try to handle authentication, multi-user, network agents.
  This is single-user, single-machine.
- Don't worry about mobile/phone display — the phone has its own UI
  via the gmux-phone PWA + bridge.
- Don't add features that aren't in the success criteria. We can
  iterate later.

---

## Test data

If the live backend isn't running, mock data is in
`reference/sample-data/` (I'll seed these so you can develop offline).

To regenerate mock data from a real running gmux session:
```bash
cp /tmp/gmuxtest-*.json ~/projects/gmux_v4/agent-monitor/reference/sample-data/
```

---

## How to test against the live gmux backend

```bash
# 1. Ensure monitor.py is running
cd ~/projects/gmux_v4
./scripts/launch-v4.sh --kill  # cleanup any stale state
python3.11 backend/status/monitor.py &  # start monitor
sleep 3
curl http://localhost:8769/health  # should say "ok"

# 2. Open at least one agent (in the main app or via tmux+claude/opencode)
# Otherwise the monitor will show nothing

# 3. Run your workshop dashboard
cd ~/projects/gmux_v4/agent-monitor/src
python3 -m http.server 5601
# Open http://localhost:5601/dashboard/ in Chrome
```

---

## Handoff back to main app

When the workshop version works in the browser, follow
`docs/INTEGRATION_GUIDE.md` to merge it into the main app's
`app/src/dashboard/` directory. The Tauri window infrastructure is
already in place (window registered, events emitted, Vite plugin
bundles files) — you just swap the HTML/JS/CSS.
