# Memory Panel Integration — Roadmap

**Status:** Coming soon (in development)
**Demo state visible at:** click "🧠 Memory" in the top bar
**Full prototype:** `~/projects/Knowledge_systems/gmux_memory_integration/dummy_ui/`

---

## What it is

A side panel that shows agent memory across the gmux fleet — what each agent has
read, written, and remembered. Cross-references context between agents and
visualises file hotspots + the agent ↔ memory knowledge graph.

Four tabs:

| Tab | What it shows |
|---|---|
| **Activity** | Live tool feed across all agents (combined `tool_history` stream) |
| **Memory** | Browse and recall stored context entries per agent + global pool |
| **Files** | Heat map of which files each agent has touched, and how recently |
| **Graph** | Visual graph of agents ↔ memory entries ↔ files |

---

## Where the source lives

Built out as a standalone HTML/JS prototype:

```
~/projects/Knowledge_systems/gmux_memory_integration/
├── README.md
├── docs/
│   ├── 00_FOR_AGENTS.md
│   ├── 01_WHAT_IT_IS.md
│   ├── 02_DATA_CONTRACTS.md
│   ├── 03_INTEGRATION_GUIDE.md   ← step-by-step integration playbook
│   ├── 04_MEMORY_MODEL.md
│   ├── 05_EXTENSION_POINTS.md
│   └── 06_FAQ.md
└── dummy_ui/
    ├── index.html
    ├── css/panel.css
    ├── js/
    │   ├── app.js
    │   ├── data.js
    │   ├── panel_activity.js
    │   ├── panel_memory.js
    │   ├── panel_heatmap.js
    │   └── panel_graph.js
    └── data/  (60+ mock memory entries, 120+ activity events)
```

Run the standalone dummy: `cd ~/projects/Knowledge_systems/gmux_memory_integration/dummy_ui && ./serve.sh` → opens at http://localhost:1899.

---

## What's in v3.4 (right now)

- "🧠 Memory" button in the top bar with a `soon` badge
- Side panel that slides in (matches `#chat-panel` / `#graph-panel` pattern)
- Placeholder card explaining what's coming, with the 4 tabs labelled
- Clicking a tab highlights the matching feature row in the placeholder

So users can see where the feature will live and that it's planned — without
us pretending the data is real.

---

## Integration plan (next steps)

In order:

1. **Phase 1 — Activity tab** (smallest dependency surface)
   - Merge `dummy_ui/js/panel_activity.js` into `ui/v3/index.html`
   - Pull tool events from `panes[].tool_history` directly (already exists)
   - No new backend work needed

2. **Phase 2 — Files tab**
   - Hook into the file-access pattern already tracked by monitor.py
   - Add `file_history` field to `PaneInfo` (paths touched by each agent)
   - Render heat map from that

3. **Phase 3 — Memory tab**
   - This requires a memory backend — `kalarc-memory` project is the candidate
   - Add `GET /api/memory?agent=<pane_id>` to monitor.py
   - Pull from kalarc-memory's SQLite DB
   - Show recall hits + browseable history

4. **Phase 4 — Graph tab**
   - Reuse the existing `#graph-canvas` rendering primitives
   - Edges = agent-touched-file relationships
   - Nodes = agents, files, memory chunks

Each phase ships independently. Until Phase 4 ships, the panel shows the
placeholder for tabs that aren't ready, and renders the live data for tabs
that are.

---

## Why "coming soon" labels matter

If we ship the demo publicly while the panel is still incomplete, users
need to know it's WIP — otherwise they'll think the empty panel is a bug.

The `coming-soon-badge` CSS class is now reusable. Any future feature that
ships in a partial state can opt in by adding `<span class="coming-soon-badge">soon</span>`
next to its label.

---

## Reference docs

- `~/projects/Knowledge_systems/gmux_memory_integration/docs/03_INTEGRATION_GUIDE.md` — the actual integration playbook
- `~/projects/Knowledge_systems/gmux_memory_integration/docs/02_DATA_CONTRACTS.md` — every JSON schema
- `~/projects/Knowledge_systems/gmux_memory_integration/README.md` — overview
