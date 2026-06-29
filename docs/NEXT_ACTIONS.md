# gmux-system — Next Actions Log

**Last updated:** 2026-05-12

## Completed in this session (2026-05-12)

- [x] Full UI/backend audit — identified every mock vs real field
- [x] `HANDOVER.md` — comprehensive project documentation
- [x] Backend: `psutil` collector (`ram_mb`, `cpu_pct`, `uptime_s`, `children`)
- [x] Backend: OpenCode aggregator thread (`model`, `provider`, `token_in/out`, `cost_usd`, `msg_count`)
- [x] Backend: real todos via `/session/:id/todo`
- [x] Backend: `cwd` field in PaneInfo (needed by UI for OpenCode API calls)
- [x] UI: replaced `MOCK_TODOS` lookup with `pane.todos` from backend
- [x] UI: replaced `MOCK_CHILDREN` with `pane.children` from backend
- [x] UI: real chat history fetch from `/session/:id/message` (`REAL_CHAT` cache)
- [x] UI: chat summary shows real model + RAM + CPU + tokens
- [x] UI: avatar mode toggle (off / crab / ASCII cat / coloured dot)
- [x] UI: media queries for 1024px / 768px / 480px / ultrawide 2560px

## Pending (high priority)

### 1. Token rate sparklines now have real data — verify it flows
The `TOKEN_RATE` buffer and `pushTokenRate()` infrastructure was built for mock
data. Now that `p.token_in`/`p.token_out` are real, the sparkline should
naturally show actual rate. Test that the sparkline + tokens/sec readout in
the pane footer reflect real activity.

### 2. Tool history `pushToolEvent()` not called in real mode
The audit found `pushToolEvent(id, toolName)` is never called from the SSE/HTTP
path — only from mock evolution. Add to `applyRealState`:
```javascript
if (pane.current_tool && pane.current_tool !== panesObj[id]?.current_tool) {
  pushToolEvent(id, pane.current_tool);
}
```
Currently the timeline in the Hardware tab stays empty on real panes.

### 3. Cost USD is `0.0` in QalCode 1.1.x
The OpenCode backend currently returns `info.cost = 0` for every step-finish
part. The aggregator sums these and writes `cost_usd = 0`. The UI then falls
back to `calcCostUsd(p)` which uses the `MODEL_COST` table.

Options:
- Keep `calcCostUsd()` fallback when `cost_usd === 0`
- Or wait for QalCode2 to start populating `info.cost`
- Or compute from token totals + `MODEL_COST` table on backend side

### 4. Chat panel: don't refetch on every render
Currently `renderChatPanel(p)` triggers `_fetchRealChat(p)` every time it
renders (rate-limited to 3s). Better: subscribe to OpenCode SSE events
(`message.part.updated`) and refresh only when content changes.

### 5. Live messages streaming (SSE → UI)
Currently real chat is fetched on panel open. For an active conversation
where tokens are streaming in, the UI shows a stale snapshot until the
next 3s fetch. Add SSE subscription in the UI:
```javascript
const es = new EventSource(`http://127.0.0.1:${port}/event?directory=${cwd}`);
es.addEventListener('message.part.updated', () => _fetchRealChat(p));
```

## Pending (medium priority)

### 6. Send message round-trip
`window.sendChat` invokes `send_to_agent` via Tauri or direct fetch. Need
to verify that after sending:
- The user's message appears in the chat panel
- The agent's streaming response appears as it generates
- Token count updates in real time

### 7. Approve / reject buttons
`window.approve` and `window.reject` invoke Tauri commands. Verify:
- `permission` state agents show the buttons
- Click → POST to OpenCode `/permission/allow` or `/permission/deny`
- State updates within 2s after approval

### 8. New agent modal
The "+ new agent" button opens a modal that calls `invoke('open_agent')`.
Verify it actually spawns a new tmux window with opencode running.

### 9. Voice → chat input bridge
faster-whisper daemon is running on :8770. The UI auto-connects. Need to
verify:
- Speaking pushes transcript to input field
- Final transcription replaces interim with `[final]` marker
- Thumbs-up gesture sends the message

### 10. Mobile/phone PWA path
With responsive CSS in place, phone access via `http://<host>:5550` should
work. But:
- HTTPS required for camera (MediaPipe) and mic (faster-whisper)
- Self-signed cert via Caddy or Tailscale ts cert
- PWA manifest for home screen install

## Pending (low priority)

### 11. Tauri production build
- `npm run tauri build` → `.deb` / `.AppImage` / `.msi`
- Bundle MediaPipe model + sidecar scripts as Tauri resources
- Use `tauri::api::path::resource_dir()` to locate them at runtime

### 12. Python deps installer
First-launch wizard:
- Check if `faster-whisper`, `psutil`, `websockets`, `sounddevice` are installed
- If missing: offer to `pip install` them
- If tmux/opencode missing: link to install docs

### 13. systemd user service for monitor
Already drafted in `scripts/install.sh`. Need to:
- Test on a clean machine
- Add `auto-restart on crash` (already in spec)
- Document how to disable

### 14. Aquarium window
Already registered in `tauri.conf.json` as second window. Has WebSocket
client at `ws://localhost:8767` but bridge.py needs to be running. Not
critical — moved to "later" per recent user feedback.

### 15. Knowledge dashboard window
Plan exists in `~/projects/Knowledge_systems/gmux_memory_integration/`.
Becomes a third Tauri window. See exploration from earlier session for
the integration plan (Step 1–7 in the explore report).

## Where to look (context recovery shortcuts)

| Question | Search here |
|----------|-------------|
| Why is this field showing mock data? | grep for the field in `MOCK_*` constants in `v2/index.html` |
| Does the backend send this field? | `curl http://127.0.0.1:8769/api/state \| python3 -m json.tool \| head -50` |
| What does the OpenCode API return for X? | `curl http://127.0.0.1:<port>/session/<id>/<endpoint>?directory=<cwd>` |
| Why did monitor.py die? | `tail -50 /tmp/gmux-monitor.log` |
| Why did Tauri start (or not)? | `tail -50 /tmp/gmux-tauri-test.log` |
| Where's the canonical UI source? | `/home/fivelidz/projects/gmuxtest/UI_creation_independent/v2/index.html` |
| Where's the canonical Rust source? | `/home/fivelidz/projects/gmuxtest/src-tauri/src/lib.rs` |
| Where's the canonical Python backend? | `/home/fivelidz/projects/gmux-system/backend/status/monitor.py` |

## Latest commits (2026-05-12)

| Repo | Commit | Note |
|------|--------|------|
| `gmux-system` | `56e507e` | Backend writes real data + HANDOVER.md |
| `gmuxtest` | `58ddf87` | UI uses real data + Tauri archive |
| `gmux-ui-demo` | `0cfb5b1` | Real chat + todos from OpenCode |

---

## 2026-05-16 — Next streams (post v3.7.0)

Three streams of work ready to start tomorrow. Each has its design doc + scope.
Pick one, two, or all three depending on time.

### Stream 1 — Implement `bridge.py` (v3.8) so the gmux-phone app goes live

**Goal:** make the gmux-phone PWA actually connect and control gmux-system.

**Design doc:** `docs/BRIDGE_DESIGN.md`
**Frozen client spec:** `~/projects/gmux-phone/docs/BACKEND_CONTRACT.md`

Order:
1. `backend/bridge/auth.py` + `scripts/gmux-pair` CLI
2. `backend/bridge/tmux_ops.py` + unit tests
3. `backend/bridge/adapter.py` (translates `monitor.py` JSON → phone Session schema)
4. `backend/bridge/bridge.py` — WS+HTTP server
5. SSE subscription → broadcast to phones
6. Phone commands → tmux_ops
7. End-to-end smoke test
8. `scripts/launch.sh` to auto-spawn bridge
9. Tauri sidecar registration

Effort: ~2-3 focused days. Add `backend/bridge/test_bridge.py` — 30+ assertions.

### Stream 2 — Implement usage tracking (v3.8) for per-provider quota display

**Goal:** show per-provider quota gauges (like claude.ai/settings/usage) in
the gmux UI status bar.

**Design doc:** `docs/USAGE_TRACKING.md`

**Pre-flight task:** connect to a running opencode session and inspect what
`metadata` fields are returned by `GET /session/{id}/message?directory=<cwd>`.
Decides whether to use Option B (opencode HTTP API) or Option C (mitm proxy).

Order:
1. `backend/status/usage_tracker.py` — produces `/tmp/gmuxtest-usage.json`
2. `usage-update` event broadcast in Rust state-poll thread
3. UI status-bar widget (right side, compact, clickable)
4. UI detail tab in dashboard (per-provider gauges + history)
5. New-agent modal shows provider quota under model dropdown

Effort: ~1-2 days.

### Stream 3 — Build fresh-VM test rig so installs stay green

**Goal:** every install/deploy regression caught against a clean snapshot.

**Design doc:** `docs/FRESH_VM_TEST_PLAN.md`

Order:
1. Build fresh QEMU snapshot of CachyOS minimal
2. `scripts/vm-fresh-boot.sh` to revert + boot headless
3. `scripts/test-fresh-install.sh` to run full cycle
4. Add `gmux-fresh` to `~/.ssh/config`
5. First test cycle — establish baseline pass
6. Tag releases only after green test on fresh-VM
7. (Future) GitHub Actions matrix for Ubuntu/Debian

Effort: half a day to set up + half a day per test cycle.

### Manual tests still to do (not blocking the streams)

From `latest_version_test/TEST_LIST.md`:

- [ ] Fish-name fix verification in actual Tauri window
- [ ] Process hygiene check (one monitor running, not two)
- [ ] Agent Monitor dashboard HUD counters move
- [ ] Agent creation live launch (Press N, agent appears)
- [ ] Per-session last-dir memory test
- [ ] Views dropdown click-outside / Esc dismiss
- [ ] Provider auth UI: Settings → Providers tab renders authed list
- [ ] Folder click-to-drill-in in Agent Monitor
- [ ] Full path display in file detail (subtitle)
- [ ] Agent quick-swap palette (Ctrl+P)
- [ ] Layout cycle hotkey (L)

Recommended: run `./latest_version_test/launch_tauri.sh --check` then
walk through the list.

### Quick state-check oneliners

```bash
cd ~/projects/gmux-system && git log --oneline -5 && git describe --tags

python3.11 backend/status/test_monitor_producers.py 2>&1 | tail -1
python3.11 backend/status/test_sub_agents.py 2>&1 | tail -1
python3.11 backend/status/test_memory_aggregator.py 2>&1 | tail -1
(cd app/src-tauri && cargo check 2>&1 | tail -2)

ssh sandbox 'curl -s http://127.0.0.1:8769/health'
pgrep -af gmux-system/backend/status/monitor.py | head -1
ls -la /tmp/gmuxtest-*.json
```

### Documents added 2026-05-16 (no code changes — docs only)

- `docs/BRIDGE_DESIGN.md` — spec for `backend/bridge.py` (Stream 1)
- `docs/USAGE_TRACKING.md` — per-provider quota display (Stream 2)
- `docs/FRESH_VM_TEST_PLAN.md` — clean-room test rig (Stream 3)
- `docs/NEXT_ACTIONS.md` — this block

All code, tests, and tags from v3.7.0 unchanged. Tomorrow starts on a clean base.
