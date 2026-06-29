# gmux agent display · GAD v4.6

A second-monitor view of what each agent in your gmux session is doing
right now — which files they're reading, writing, editing, and how their
attention moves through the codebase.

> Renamed from "gmux dashboard" to **gmux agent display** (`GAD`) in v4.4
> so the version stream isn't confused with `gmux` itself.

For full usage see [`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md) — or click
the **❓ guide** button in the top bar (or press `G`).

## Run it

```bash
./serve.sh --open      # → http://localhost:1900/dashboard/
```

Then drag to second monitor, press **F** for fullscreen.

## Two views

- **Default — watch one agent.** Top-down flowchart: agent → folder → folder → file. Coloured pulse-lines flow through every folder on the chain. Op label (running timer) sits to the side of the leaf edge.
- **Overview (`⊞ all`) — web/mycelium.** Agents placed in a ring; their active files orbit around them with dotted ellipse "territories" enclosing each agent's cluster. Stale edges fade to grey over 30s.

## Style options (`⚙ style`)

| Setting | Choices |
|---|---|
| Edge style | curve / ortho / arc (tighter bezier) |
| Stroke weight | thin / normal / thick |
| Pulse size | small / normal / large |
| Timer labels | on / off |

All persist to localStorage.

## Tech (zero deps)
Pure SVG + vanilla JS. No React. No build step. Tauri-ready.

## Versions

- **v4.6** ← you're here — top-left brand shows active gmux session name; product title moves to small two-line subtitle
- v4.5.1 — fix invisible vertical edges (SVG filter region bug + per-edge nudge for organic feel)
- v4.5 — single-action test mode, folder-left/file-right ordering, history-edge visibility fix
- v4.4 — GAD rename, style options panel, organic overview, edge label simplified, # pane IDs
- v4.3 — single op-label per chain, running timer, code deltas, node tints, more space
- v4.2 — path-match fix; todo-on-node; guide button; narrower panel
- v4.1 — todo checklist; inline copy button; auto-switch rename; overview time decay
- v4.0 — propagation through folder chain
- v3.0 — themes, follow-active, session selector
- v2.0 — flowchart introduction
- v1.0 — multi-panel cluttered (archived)
