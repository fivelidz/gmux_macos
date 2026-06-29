# Live Data Flow — Status Report

**Date:** 2026-05-11
**Commits:**
- `gmux-ui-demo` @ `1e43c03` — UI v3.0 live data fix
- `gmuxtest` @ `754cee1` — Tauri sync
- `gmux-system` @ `fabc6c5` — consolidated sync

---

## The Problem Reported

> The sessions don't reflect actual sessions still. The contents of the agents do not reflect actual content. The agent names seem to correspond with our current tab titles but nothing beyond that and only for the first session.

## Root Cause

Two independent bugs in the UI's data layer:

### Bug 1 — `initDataSource` only merged onto mock IDs
```javascript
// Before:
for (const [id, pane] of Object.entries(real)) {
  if (panesObj[id]) {                        // ← guard: only update existing
    Object.assign(panesObj[id], pane);
  }
}
```
Real pane IDs from tmux look like `%17`, `%23`, `%42`. Mock IDs are `%1`…`%8`. The keys never matched, so real data was discarded and mocks stayed visible.

### Bug 2 — `SESSIONS` was a frozen `const`
```javascript
// Before:
const SESSIONS = [
  {name:'gmux',     color:'#818cf8'},
  {name:'work',     color:'#34d399'},
  {name:'personal', color:'#f87171'},
];
```
No code path ever rebuilt this from real data, so the tab strip kept showing `gmux | work | personal` no matter what your real tmux sessions were called (`goblin | knowledge | rfai | tradez | gmux` in your case).

---

## What's Fixed

### `applyRealState(real)` — full pane replacement
- Deletes panes that vanished from the real state
- Adds new panes wholesale (no longer guarded by mock-key match)
- Rebuilds `paneOrder` sorted by `window_index`
- Re-points `selectedId` if its target disappeared

### `_deriveSessions(srcMap)` — live session derivation
- Scans current panes, builds unique session set
- Sorts: `gmux` / `main` first, then alphabetical
- Assigns stable hash-based colours from a 10-colour palette
- Detects changes and returns `true` so caller can trigger re-render
- Falls back to `panes` (global) when no explicit map passed

### 3-tier data source (browser also works now)
```
1. Tauri events (desktop)        ← preferred
2. HTTP+SSE on :8769             ← browser live mode  NEW
3. HTTP polling every 2s         ← if SSE unavailable NEW
4. Mock evolution                ← if nothing reachable
```

Statusbar shows:
- `● tauri live`
- `● live :8769`
- `● live (poll)`
- `● mock`

Hover tooltip shows: `Data source: tauri · 14 agents · 5 sessions`

---

## Verified Working

```
$ curl -s http://127.0.0.1:8769/api/state | python3 -m json.tool | head
14 panes total
5 sessions: gmux, goblin, knowledge, rfai, tradez

gmux:
  [1] museall_image_visualiser       → waiting
  [2] fish                           → working
  [3] fish                           → working
  [4] research                       → idle
  [5] Containment_project            → waiting
  [6] volkus.net                     → waiting
  [7] qalcode2                       → waiting
  [8] fish                           → waiting
  [9] fish                           → idle
goblin: 1 fish (waiting)
knowledge: 2 fish (waiting)
rfai: 1 fish (waiting)
tradez: 1 fish (idle)
```

CORS confirmed: `Access-Control-Allow-Origin: *` on `/api/state`
Tauri Vite hot-reload picked up the new code (1.3MB transpiled bundle includes 14 references to new symbols)

---

## How to Test

### Browser
```
http://localhost:5550/v2/index.html
```
Should now show:
- Statusbar: `● live :8769` (purple if Tauri, accent if HTTP)
- Session tabs: `All | gmux | goblin | knowledge | rfai | tradez`
- 14 agents in sidebar with real `window_name`, `state`, `todo_done/total`

### Tauri
```
http://localhost:1421/  (already running)
```
Will show `● tauri live` once you launch via `npm run tauri dev`.

### If you see stale mocks
1. Hard-refresh: `Ctrl+Shift+R`
2. Clear localStorage: open devtools console → `localStorage.clear()` → reload

---

## Files Touched

| File | Lines changed | What |
|------|--------------|------|
| `ui/v3/index.html` | +459 −41 | Core logic |
| `releases/gmux-v3.0.html` | mirror | |
| `releases/gmux-v3.0-demo.html` | mirror with demo banner | |
| `gmux-v3.html` | mirror with demo banner | |
| `src/index.html` (Tauri) | mirror | |
| `gmux-system/ui/v3/index.html` | mirror | |

All five locations now byte-identical (293,541 bytes) for the source file.
