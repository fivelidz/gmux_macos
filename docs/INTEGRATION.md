# gmux-system — Integration Plan & Known Gaps

## Layer Map

```
ui/v3/index.html          ← Browser frontend (gesture + voice + agent grid)
       ↕ Tauri events / HTTP fetch
app/src-tauri/src/lib.rs  ← Rust: PTY, state poll, Tauri commands
       ↕ reads /tmp/*.json
backend/status/monitor.py ← Python: tmux poll + OpenCode SSE + HTTP :8769
       ↕ SSE streams
OpenCode instances        ← Each pane: random HTTP port, /session/status, /event
```

## Known Gaps & Fixes

### FIXED in this session
| Gap | Fix |
|-----|-----|
| `open_project` sent `\x01cnewp\r` (typed "newp" into new window) | Replaced with sequential write + sleep |
| `approve_agent` sent bare Enter to PTY (wrong window) | Now POSTs to OpenCode API; falls back to `tmux send-keys -t gmux:N` |
| No `reject_agent` command | Added — same pattern as approve |
| Session-save on close pointed to production gmux path | Now tries gmux-system first, falls back gracefully |
| State poll only read 2 files | Now also reads `/tmp/ram_tracker_agents.json`, emits `gmux-ram` event |
| Voice daemon not started by Tauri | Added to `spawn_sidecars` alongside monitor |
| `launch-gmux.sh` matched any `monitor.py` | Fixed pgrep to match exact path |
| MediaPipe loaded from CDN | Local model at `models/hand_landmarker.task` served at `/hand_landmarker.task` |

### Still TODO
| Gap | Fix needed |
|-----|-----------|
| `send_to_agent` doesn't auto-lookup session ID | UI now calls `_getActiveSessionId()` first — ✓ done in UI |
| `pane.cwd` not in state JSON | monitor.py should add `cwd` from `/proc/<pid>/cwd` |
| `ram_tracker_agents.json` only written by GTK GUI | Need headless `agent_feed.py` mode |
| MediaPipe CDN fallback if local 404 | Add try/catch in `initGesture()` to retry with CDN URL |
| No HTTPS for phone PWA | Add self-signed cert or Tailscale for camera+STT on mobile |

## OpenCode HTTP API Reference

All endpoints require `?directory=<cwd>` query param.

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/session` | — | `[{id, title, updated}]` |
| GET | `/session/status` | — | `[]` idle / `[{type:"busy"}]` working |
| GET | `/event` | — | SSE stream |
| POST | `/session/{id}/prompt_async` | `{parts:[{type:"text",text:"..."}]}` | 204 |
| POST | `/session/{id}/permission/allow` | — | 200/204 |
| POST | `/session/{id}/permission/deny` | — | 200/204 |
| POST | `/session/{id}/abort` | — | 204 |
| DEL | `/session/{id}` | — | 204 |

## Packaging Plan

### Phase 1 — Working dev build (current)
- `./scripts/launch.sh` → starts services + Tauri dev
- Browser fallback: `./scripts/launch.sh --browser`

### Phase 2 — Tauri production build
```bash
cd app && npm run tauri build
# Outputs: app/src-tauri/target/release/bundle/
#   - .deb (Debian/Ubuntu/CachyOS)
#   - .AppImage (portable Linux)
```
- Bundle the hand_landmarker.task as a Tauri resource
- Auto-start monitor.py as a Tauri sidecar (configured in tauri.conf.json)

### Phase 3 — Phone PWA
- Serve ui/v3/index.html via HTTPS (Tailscale cert or Caddy)
- PWA manifest + service worker for home screen install
- Simplified layout for mobile (single column, large approve/reject buttons)

### Phase 4 — gmux.ai hosted demo
- `ui/releases/gmux-v3.0-demo.html` → deploy to Cloudflare Pages
- No backend needed — runs in mock mode
- "Connect to local" button: tries ws://localhost:8770 and http://localhost:8769

---

## Phone integration — gmux-phone (added 2026-05-15)

The companion phone app lives at `~/projects/gmux-phone/` (v0.6.0, NERV theme
default, APK-ready via Bubblewrap).

**Authoritative protocol spec:** `~/projects/gmux-phone/docs/BACKEND_CONTRACT.md`

That file documents:
- Pairing payload format (locked v1 — `gmux-pair` QR JSON)
- WebSocket message protocol on `:8767` (phone ↔ bridge)
- HTTP fallback on `:8768`
- `Session` / `Agent` / `Todo` shapes the phone expects
- Recommended bridge composition (subscribe to `monitor.py` SSE, shell to
  `gmux.py` for spawn/kill, `tmux send-keys` for I/O)

**Host-side work required to make the phone go live** (currently paused per
gmux-system `DECISIONS.md`):

1. `backend/bridge.py` — implement WS :8767 + HTTP :8768 per the contract
2. `scripts/gmux pair` — token gen + QR render + write
   `~/.config/gmux/pair-tokens.json`
3. `scripts/gmux pair --cloud` — same but registers with relay (future)
4. systemd user unit for the bridge (after Tauri-app resume gate is green)

The phone's mock-mode (`src/js/mock.js` in gmux-phone) is the canonical
reference implementation of the Session/Agent shapes the bridge must emit.
