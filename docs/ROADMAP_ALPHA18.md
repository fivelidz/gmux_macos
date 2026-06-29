# Roadmap — alpha.18 and beyond

**Date written:** 2026-05-19 ~14:00 AEST
**Gold baseline:** `v4.0.0-alpha.17-dev2` (commit `b63c1e8`)
**Gold binary:** `archive/binaries/gmuxtest-v4.0.0-alpha.17-dev2-GOLD`
**Gold snapshot:** `archive/snapshots/alpha.17-dev2-GOLD.tar.gz`

User has signed off on alpha.17-dev2 as the new gold standard.
Quote: *"This is working brilliantly. Very happy with this. for now we can
have this as the gold standard."*

This document scopes everything between gold and the next milestone.
Three quick UI wins to do first (alpha.17-dev3), then five major
testing/integration epics that each get their own dev cycle.

---

## Recommended order (assistant's pick)

1. **alpha.17-dev3 — three quick UI wins** (½ day, low risk)
   - Close-agent button (replace pointless fullscreen button)
   - Alt+←/→ session switching
   - Star/favourite indicator in sidebar + "⭐ Starred" pseudo-session

2. **alpha.18 — agents spawning sub-agents** (1–2 days, builds on dev3)
   - The plumbing already exists (`spawn_sub_agent_v4` works). What's
     missing is the *agent-facing* affordance: a tool call or CLI helper
     that an in-pane agent can use to spawn a sibling. Most of this
     happens in `monitor.py` and a small new Rust command.

3. **alpha.19 — Agent Monitor v2** (2–3 days)
   - The current `openAgentMonitor` button opens the wrong window
     (a second pane grid instead of the flow-diagram dashboard).
     The spec at `agent-monitor/spec/AGENT_MONITOR_SPEC.md` is good;
     we just need to wire `agent-monitor/src/dashboard/` correctly
     in the Tauri capability + JS bridge.

4. **alpha.20 — Voice round-trip** (1–2 days)
   - faster-whisper daemon already exists on `:8770`. Fix the port
     mismatch in `bridge.py` (was hardcoded to `:8765`), wire PTT
     to the daemon, smoke-test gesture+voice combinations.

5. **alpha.21 — Phone app bridge** (3–5 days, biggest chunk)
   - Implement `bridge.py` per `docs/BRIDGE_DESIGN.md` (WS :8767 +
     HTTP :8768 + token auth). QR pairing via the existing
     gmux-phone PWA. Tailscale optional, ngrok/cloudflared as
     fallback. SSH-tunnel command (`spawn_ssh_tunnel`) for the
     remote-machine case.

6. **alpha.22 — v4 PTY substrate completion** (2–3 days)
   - Today `GMUX_V4_PTY=1` is required as an env var and the pane-id
     ↔ session_id mapping is unfinished (`index.html:9319` cuts off
     mid-sentence). Land the per-pane xterm.js wiring + UI to flip
     v4 mode without a restart.

Total: ~2 weeks of focused work to alpha.22.

---

# Section 1 — alpha.17-dev3 (three quick UI wins)

These are small, self-contained, and use existing infrastructure.
Each is its own commit.

## 1.1 Close / quit agent button

> *"A means to close/quit an agent and panel. A small button to do this.
> The fullscreen button on the panel in the pane grid is pretty pointless
> so maybe that could be replaced with a close X. Maybe it only shows
> when pressing Alt to stop mistakes."*

### Status now

- `kill_session(session_id: u32)` already works (`app/src-tauri/src/commands/terminal.rs:140`)
- `ProcessManager::kill_session` does SIGTERM → 3s grace → SIGKILL
  (`app/src-tauri/src/core/process_manager.rs:564`)
- **There is no `close_agent` / `kill_agent` Tauri command yet** — the
  existing `kill_session` operates on PTY session_ids (u32), not pane_ids.
- No close button in the pane header. The "⊞ Fullscreen" button on the
  pane (`.ph-fs` at `index.html:6299`) is rarely used.

### Plan

1. Add `close_agent(pane_id, port, session_id, directory, window_index,
   v4_session_id)` Tauri command in `lib.rs`. Resolution order:
   - If `v4_session_id` is set → call `process_manager.kill_session(v4_id)`
   - Else if `port + session_id` set → `POST /session/{id}/abort` then
     `POST /session/{id}/destroy` (best-effort, like the existing
     `interrupt_agent`)
   - Last resort → `tmux kill-window -t {session_name}:{window_index}`
2. Replace `.ph-fs` with `.ph-close` showing `✕` by default. **Hold Alt
   to confirm** — without Alt, clicking shows a "Hold Alt + click to
   close" toast. With Alt, calls `close_agent`.
3. Animation: fade-out the pane card before removing.
4. Also add an inline `.arow-close` button in the sidebar (visible only
   on hover + Alt, same toast pattern). Sits next to `arow-ram`.

### Files

| What | File | Approx line |
| --- | --- | --- |
| New Rust command | `app/src-tauri/src/lib.rs` | ~1141 (next to `approve_agent`) |
| Register command | `app/src-tauri/src/lib.rs` | ~1556 (invoke_handler list) |
| Pane close button | `app/src/index.html` | replace `ph-fs` at ~6299 |
| Sidebar close button | `app/src/index.html` | inside `renderRow` ~6072 |
| Alt-hold helper | `app/src/index.html` | new global `_altDown` + keydown/keyup |
| CSS for close btns | `app/src/index.html` | `.ph-close` near `.ph-fs` (~613) |

### Acceptance

- Click without Alt → toast "Hold Alt + click ✕ to close this agent"
- Alt+Click → pane fades + disappears, backend confirms agent gone
- Sidebar gets the same treatment so power users can close from there

---

## 1.2 Alt+←/→ session switching

> *"Being able to swap between sessions by pressing Alt + ← or →.
> Using Alt and arrow keys to swap sessions would be a nice feature."*

### Status now

- Session tabs are click-only (`index.html:5930-5946`)
- `selectSession(name)` is the existing entry point (line 5946)
- The main `keydown` handler at `index.html:7838` **already guards**
  Arrow keys with `!e.altKey` — Alt+Arrow is currently a no-op,
  meaning the slot is intentionally reserved for exactly this feature.

### Plan

Add a single keydown branch:
```js
if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
  e.preventDefault();
  const order = (SESSIONS||[]).map(s => s.name);
  if (!order.length) return;
  const cur = order.indexOf(activeSession);
  let next;
  if (e.key === 'ArrowLeft')  next = (cur - 1 + order.length) % order.length;
  else                        next = (cur + 1) % order.length;
  selectSession(order[next]);
}
```

Plus `Alt+0..9` to jump directly to session N for parity with browser tabs.

### Files

| What | File | Line |
| --- | --- | --- |
| keydown branch | `app/src/index.html` | inside main handler ~7838 |
| Tooltip on tabs | `app/src/index.html` | `.stab` template ~5936 — show "Alt+←/→" hint |

### Acceptance

- Alt+Right cycles forward through session pills (wraps)
- Alt+Left cycles backward (wraps)
- Alt+1..9 jumps to N-th session
- Status bar legend mentions the new hotkey

---

## 1.3 Star/favourite indicator + "⭐ Starred" pseudo-session

> *"In the agent list it would be good to be able to 'star' certain
> agents as favourites. They could be the main ones of a session.
> Having a 'starred' session tab as well as an 'all' session tab
> would be good potentially."*

### Status now

- Favourites system **already exists** since v3.7:
  - `_loadFavorites()` / `_saveFavorites()` at `index.html:7435`
  - `toggleFavoriteAgent(paneId)` at `index.html:7443`
  - `Ctrl+Shift+F` already toggles favourite on selected pane (line 7905)
  - Palette gives favs a +200 score boost (line 7491)
- **What's missing:**
  1. No visible ⭐ on agent rows in the sidebar
  2. No "Starred" pseudo-session pill in the topbar
  3. Favourites are pane-id-keyed → don't survive tmux restart
     (a real fix would also key by window_name fallback)

### Plan

1. **Visual star in sidebar.** In `renderRow` (`index.html:6020`),
   add a small star button after the window number:
   ```js
   const isFav = _favIds.has(p.pane_id);
   const starBtn = `<button class="arow-star${isFav ? ' on' : ''}"
     onclick="event.stopPropagation();toggleFavoriteAgent('${p.pane_id}')"
     title="${isFav?'Unstar':'Star'} this agent">★</button>`;
   ```
2. **"⭐ Starred" pseudo-session.** Treat it like the existing `'all'`
   session. In `sorted()` at `index.html:5863`:
   ```js
   if (activeSession === 'starred') {
     arr = arr.filter(p => _favIds.has(p.pane_id));
   }
   ```
   Add the pill in `renderSessionTabs`:
   ```js
   html += `<button class="stab starred${activeSession==='starred'?' active':''}"
     onclick="selectSession('starred')" title="Show only starred agents">
     <span class="stab-dot" style="background:gold"></span>⭐ Starred
     <span class="stab-count">${favCount}</span></button>`;
   ```
3. **Persistence improvement.** Store favourites as
   `{pane_id, window_name, session_name}` triples; on load, match by
   pane_id first, then by `(session, window_name)` fallback so favs
   survive tmux restarts.

### Files

| What | File | Line |
| --- | --- | --- |
| Star button in sidebar | `app/src/index.html` | `renderRow` ~6020 |
| Star CSS | `app/src/index.html` | near `.arow-tasks` ~396 |
| Starred pseudo-session filter | `app/src/index.html` | `sorted()` ~5866 |
| Starred pill in topbar | `app/src/index.html` | `renderSessionTabs` ~5930 |
| Persistence refactor | `app/src/index.html` | `_loadFavorites/_saveFavorites` ~7435 |

### Acceptance

- Click the star in a sidebar row → it fills yellow + counter updates
- Click the "⭐ Starred" pill → grid + sidebar show only favourites
- Restart gmux → favourites still there (matched by window_name)
- Ctrl+Shift+F still works (no regression)

---

# Section 1.5 — alpha.17-dev3 add-on: auto-resume rate-limited agents

> *"In options for gmux have the ability to auto control if periodically
> the system will attempt to resume an agent that has been stopped
> because it has been rate limited. Make this the default. This is
> another feature to add. We need however rate limit detection for
> this to work."*

## Status now

**Rate-limit detection is already implemented** (v3.7).
Discovered while reviewing this feature request — `backend/status/monitor.py`
already does all the heavy lifting:

- `PaneState.RATE_LIMITED` enum (`monitor.py:112`)
- Per-pane fields `rate_limit_msg` + `rate_limit_until` (`monitor.py:157-158, 370-371`)
- Detection regex `_RATE_LIMIT_RE` (`monitor.py:938`) and
  `_extract_retry_after()` that parses Anthropic's Retry-After header
- **Signal A** — SSE error payload check at `monitor.py:1497`
- **Signal C** — terminal output scan at `monitor.py:1852` for the case
  where the error appears in stdout instead of the API
- UI surface: `.rl-badge` chip + `<span class="rl-countdown">` already
  rendered in the pane header (`app/src/index.html:6298-6299`)

**What's missing:** the *auto-resume* loop. When `rate_limit_until` ticks
past, the pane stays in RATE_LIMITED state forever — no automatic
nudge to resume the agent. The user has to manually re-send the prompt.

## Plan

### Backend signal (already there — verify)
1. Confirm `_extract_retry_after()` actually returns sane epoch
   seconds for both API-side rate limits (Retry-After header) AND
   Claude's "5-hour limit reached" message (which uses different
   wording — may need regex extension).
2. Sanity-check `monitor.py:1499` clears `rate_limit_until` when the
   agent transitions back to WORKING / READY.

### UI: Options toggle
1. New row in Options → Layout (or new "Behaviour" section):
   ```
   [✓] Auto-resume rate-limited agents
       └ When an agent hits its API rate limit, gmux will automatically
         re-send the last prompt once the rate-limit window expires.
         Default ON. Disable for manual control.
   ```
2. localStorage key: `gmux_auto_resume` (default `'1'`).
3. Add a per-agent override chip on the rate-limited pane card:
   `[Auto-resume in 4m 12s]` (orange) with a tiny `✕` to cancel
   for that one agent.

### Frontend: polling loop
1. Add a `setInterval(_checkRateLimitedAgents, 5000)` ticker.
   Iterate `panes`: if `p.state === 'rate_limited'` AND
   `p.rate_limit_until <= Date.now()/1000` AND auto-resume is on:
   - Send `/resume` to the agent via existing `send_to_agent` Tauri
     command (same as restore-session flow), OR
   - Re-send the agent's last user message from `CHAT[pid]` if
     available, OR
   - Fallback: send a single newline to nudge the agent (works for
     claude-code which typically retries on its own once the window
     clears).
2. Toast: "▶ Auto-resumed {agent_name} (rate-limit window cleared)".
3. Cooldown: don't re-trigger for the same pane within 30s, to avoid
   loops if the resume itself triggers another rate-limit.

### Refinements
- **Backoff:** if the same agent rate-limits 3 times within 10 min,
  pause auto-resume for that pane and require manual confirmation
  (some accounts hit Anthropic's daily-usage cap, not just the 5h
  window — auto-retrying that just hits the same wall).
- **Per-session opt-out:** add a session-level checkbox alongside
  the global one so a "burn through quota fast" session can disable
  auto-resume while others keep it.

## Files

| What | File | Approx line |
| --- | --- | --- |
| Regex audit | `backend/status/monitor.py` | `_RATE_LIMIT_RE` @ 938 |
| Retry-After parser | `backend/status/monitor.py` | `_extract_retry_after` |
| Options toggle | `app/src/index.html` | new section ~2138 (Layout page) |
| Pane override chip | `app/src/index.html` | `.rl-badge` rendering ~6298 |
| Auto-resume loop | `app/src/index.html` | new function near `_checkBackendHealth` ~10381 |
| Cooldown map | `app/src/index.html` | global `_lastResumeTs = {}` |

## Acceptance

- Open gmux with an agent at 95% rate-limit usage. When it 429s,
  badge shows `⏱ rate-limited — resume in 4m 12s` (already works).
- 4 minutes 12 seconds later, gmux auto-sends `/resume` and a toast
  appears. Agent goes back to WORKING within 5s.
- If the second hit also rate-limits, gmux retries once more then
  gives up (backoff). The chip changes to `⏱ rate-limited — manual
  resume required` with a `▶ Retry` button.
- Toggle the Options checkbox off → no auto-resume fires.

## Sequencing note

This is **small enough to ship with the three dev3 quick wins**
(or as a fourth commit in alpha.17-dev3). Recommend doing it
**after** the close-agent button so we can ALSO offer a "close +
reset" path for agents stuck in a daily-cap loop. If shipped
separately, tag it as `alpha.17-dev4`.

---

# Section 2 — alpha.18 (agents spawning sub-agents)

> *"A means for agents in the session to spawn new agents in the session"*

## Status now

**Most of the machinery exists** — the gap is the agent-facing API.

- `spawn_sub_agent_v4` Rust command (`lib.rs:929`) works end-to-end
- Parent-pointer file written under `~/.local/share/gmuxtest/`
- `monitor.py:_load_spawned_sub_agents()` (line 217) reads it
- Each pane carries a `sub_agents[]` array so the UI can render the tree
- `sub_permission` is a distinct state with badge colour + priority

### What's missing

1. **No way for an agent to call `spawn_sub_agent_v4` from its own
   prompt.** Today only the gmux UI can spawn. We need either:
   - A tool the agent can invoke via opencode/claude-code's tool API, OR
   - A small daemon endpoint on the gmux backend that watches for
     `~/.local/share/gmuxtest/spawn_request.json` and acts on it, OR
   - A CLI shim (`gmux spawn --name X --dir Y --model Z`) the agent
     can invoke via Bash that POSTs to the backend.
2. **No tree visualisation in the main pane grid.** `sub_agents[]`
   is populated but not rendered.
3. **No "spawn child" UI button.** Should sit in the pane header next
   to the close button (1.1).

## Plan

### A. CLI shim (simplest, fastest)
- Add `scripts/gmux-spawn` (bash) that POSTs to a new
  `monitor.py` endpoint: `POST /api/spawn { name, directory, model,
  parent_pane_id }`
- `monitor.py` writes to a queue file; a tiny Rust watcher in `lib.rs`
  picks it up and calls the existing `open_agent_v4` flow.
- Agents discover the shim via `$PATH` or via an env-var that gmux
  exports when spawning: `GMUX_SPAWN_CMD=/path/to/gmux-spawn`.

### B. Tool definition (richer, future-proof)
- Define an opencode tool `gmux.spawn_child` with parameters
  `{name, directory, model, system_prompt}`. The tool POSTs to the
  same endpoint as (A).
- Requires a tool-registration plugin — opencode supports plugin tools.
  See `https://github.com/sst/opencode/blob/main/docs/plugins.md`.

### C. UI: pane child counter + tree
- In `updatePaneEl` (`index.html:6276`), if `p.sub_agents.length > 0`
  show a small "👶 N" badge in the pane header.
- Click the badge → expand a child-list inside the pane (collapsible).
- Optionally: keep the relationship in the Agent Monitor (alpha.19)
  rather than cluttering the main grid.

## Files

| What | File | Line |
| --- | --- | --- |
| CLI shim | `scripts/gmux-spawn` | new file |
| `/api/spawn` endpoint | `backend/status/monitor.py` | near `/api/state` |
| Queue watcher | `app/src-tauri/src/lib.rs` | new `spawn_queue_loop` |
| Pane child badge | `app/src/index.html` | `updatePaneEl` ~6360 |
| Tree popover | `app/src/index.html` | new component |

## Acceptance

- An agent running in any pane can run `gmux-spawn --name child1 --dir
  /tmp/test --model opus-4-7` and a new pane appears
- The new pane's parent points to the spawning pane
- The parent's "👶 1" badge appears within 1s
- Killing the parent (with confirm) offers to also kill children

---

# Section 3 — alpha.19 (Agent Monitor v2)

> *"Troubleshooting the agent monitor display more"*

## Status now

- Button + plumbing works: `openAgentMonitor()` → invokes `open_dashboard`
  Tauri command → opens a new window (`index.html:9055`)
- **The window opens a SECOND copy of the pane grid, not the flow
  dashboard.** Confirmed by user, recorded in `HANDOVER_alpha15.md:63`.
- The standalone workshop at `agent-monitor/src/dashboard/` has a
  full flow-render engine (`flow_render.js`, `flow_pulses.js`,
  `flow_layout.js`) that was never wired to the Tauri window.
- Spec at `agent-monitor/spec/AGENT_MONITOR_SPEC.md` has 8 unchecked
  success criteria (lines 143–158).
- Backend already writes the four `/tmp/gmuxtest-*.json` files the
  workshop reads.

## Plan

1. **Audit:** What does `open_dashboard` actually open? Check Tauri
   `webview` config and the URL it loads.
2. **Route the new window to the dashboard HTML** not `index.html`.
   The `app/src/dashboard/` folder already has an `index.html`; the
   capability file allows it (`capabilities/default.json:4`). Likely
   the URL is wrong or the dashboard's data-source bootstrap is broken.
3. **Wire live data:** the dashboard currently expects to read from
   `/tmp/gmuxtest-*.json`. Either:
   - Bind them via a new Tauri command `get_monitor_state()` that
     returns the same structure, OR
   - Make the dashboard subscribe to the existing SSE stream at
     `http://127.0.0.1:8769/api/stream`.
4. **Tick off SPEC success criteria** one by one:
   1. Open window shows live agents (not panes)
   2. Each agent box shows current tool + files touched
   3. Edges show parent → child relationships
   4. Live updates within 1s
   5. Click an agent → detail panel
   6. Status strip at bottom shows aggregate
   7. Closing window doesn't crash main app
   8. Works headless (no flicker, no console errors)

## Files

| What | File |
| --- | --- |
| Tauri window route | `app/src-tauri/src/lib.rs` (`open_dashboard`) |
| Window HTML | `app/src/dashboard/index.html` |
| Flow rendering | `app/src/dashboard/js/flow_render.js` (already exists in workshop) |
| Data binding | new `app/src/dashboard/js/live_bridge.js` |
| Spec | `agent-monitor/spec/AGENT_MONITOR_SPEC.md` |

## Acceptance

All 8 success criteria in the spec pass.

---

# Section 4 — alpha.20 (Voice features end-to-end)

> *"Testing full voice features"*

## Status now

Voice is the most mature optional feature.

- `gmux_voice_daemon.py` — complete faster-whisper STT daemon, WS :8770
- `toggleVoice()` works, mic access works, waveform visualiser works
- Web Speech API path works as fallback
- PTT button (`startPTT`/`stopPTT`) wired to mic
- **Port mismatch:** `bridge.py` uses `:8765`, daemon uses `:8770`.
  The v3 bridge can never connect — needs a one-line fix.
- Voice commands in `bridge.py` are tmux-specific; need a v4 path
  via Tauri command instead.

## Plan

1. **Fix port mismatch** in `backend/voice/bridge.py` (one line).
2. **Smoke test:** start daemon, start gmux, click voice button, say
   "Hello world", expect the message to appear in the chat panel of
   the selected agent.
3. **PTT smoke test:** hold mic button, say "Plan for today", release,
   verify the transcript reaches the agent's chat input.
4. **Gesture + voice combo:** POINT gesture switches to voice mode,
   speak, verify command routes to gesture-selected pane.
5. **Voice commands routing:** "Approve", "Reject", "Stop", "New agent
   named X" — route these as Tauri command invocations, not tmux
   send-keys.
6. **Document:** record short screen-cast for the README.

## Files

| What | File |
| --- | --- |
| Port fix | `backend/voice/bridge.py` |
| Voice → Tauri commands | `app/src/index.html` (new `_voiceCmdHandler`) |
| Daemon | `backend/voice/gmux_voice_daemon.py` (already complete) |

## Acceptance

- Push-to-talk reliably appends transcript to the agent's chat input
- Voice command "Approve" approves the focused agent's permission
- No console errors during a 10-minute continuous voice session

---

# Section 5 — alpha.21 (Phone app bridge)

> *"Linking this with the gmux phone app -> QR code tailscale, audio
> code transmission ssh etc. Gmux phone app has been made but needs
> to be linked."*

## Status now

- **Phone app exists**: `~/projects/gmux-phone/` v0.7.1 (PWA-first,
  APK in progress). Multi-card UI, push-to-talk, NERV theme, QR
  pairing UI. Talks to `bridge.py` at WS `:8767` / HTTP `:8768`.
- **Bridge in gmux-system: spec-only.** `docs/BRIDGE_DESIGN.md`
  reads "Status: spec only — not implemented. Planned for v3.8."
- Tailscale, SSH tunnel, ngrok: all referenced in roadmap docs but
  none implemented.
- `legacy_planning/TODO.md:325-344` has unchecked items for
  `commands/bridge.rs` (start_bridge / stop_bridge / list_phones) and
  `gmux pair` CLI with QR generation using the `qrcode` crate.

## Plan

This is the biggest epic. Break it into 5 sub-tasks:

### 5a. Local-network bridge (LAN only)
- Implement `bridge.py` per `docs/BRIDGE_DESIGN.md`:
  - WS server on `:8767` (real-time pane state + commands)
  - HTTP server on `:8768` (snapshot endpoints for slow links)
  - Token auth (random 32-byte hex, written to
    `~/.local/share/gmuxtest/bridge_token`)
- Add `commands/bridge.rs` in Tauri: `start_bridge` / `stop_bridge`
  / `bridge_status`.
- Test with the phone PWA on the same WiFi.

### 5b. QR pairing
- Generate QR at gmux side encoding
  `gmuxapp://pair?host=<lan-ip>&port=8767&token=<hex>`.
- Use `qrcode` Rust crate. Tauri command returns the SVG.
- Add an Options → Pair Phone panel.
- Phone app already has a QR scanner per its docs.

### 5c. Tailscale path
- Optional: detect Tailscale via `tailscale ip -4` shell-out.
- If present, prefer the Tailscale IP over LAN IP in the QR payload.
- Phone uses Tailscale's Android app to be on the same tailnet.

### 5d. SSH tunnel fallback
- For "remote dev machine, phone at home" case, implement the
  `spawn_ssh_tunnel(host, port, key_path)` Tauri command per
  `docs/ROADMAP_ALPHA17.md:115-134`.
- UI: Options → Remote tab → "Connect to remote gmux" form.

### 5e. Audio transmission
- Phone PTT → WS `voice.audio` frames → bridge.py → faster-whisper
  daemon on :8770 → transcript back to phone + sent to agent.
- This piggy-backs on alpha.20 voice work.

## Files

| What | File |
| --- | --- |
| Bridge server | `backend/bridge/bridge.py` (new) |
| Tauri commands | `app/src-tauri/src/commands/bridge.rs` (new) |
| QR generator | reuse `qrcode` crate |
| Pair UI | `app/src/index.html` (new Options tab) |
| Phone-side | `~/projects/gmux-phone/` (separate repo) |

## Acceptance

- Phone on same WiFi pairs via QR and shows live agent state
- Phone over Tailscale works without LAN access
- Phone over SSH-tunnel works from outside the LAN
- Push-to-talk from phone reaches agent within 2s
- 4-hour idle session — bridge auto-recovers from network blip

---

# Section 6 — alpha.22 (v4 PTY substrate completion)

> *"The PTY system and see if that can properly connect with all of
> the attributes"*

## Status now

- `commands/terminal.rs` has working `spawn_shell`, `write_stdin`,
  `resize_pty`, `kill_session`, `kill_all_sessions`, `pty_ping`.
- `ProcessManager` uses SIGTERM-then-SIGKILL on process groups.
- `open_agent_v4` and `spawn_sub_agent_v4` are wired.
- xterm.js per-pane mounting via `gmuxMountXterm` (`index.html:9194`)
  is mostly there but has an unfinished assignment of pane_id from
  the `open_agent_v4` response (comment cuts off mid-sentence at
  `index.html:9319`).
- `GMUX_V4_PTY=1` env var is required — there is no runtime toggle
  that doesn't require restart.

## Plan

1. **Finish pane_id assignment.** When `open_agent_v4` returns the
   `session_id` (u32), record it on the corresponding pane and pass
   it to `gmuxMountXterm`. The unfinished comment at line 9319 is
   the breadcrumb.
2. **Verify all attributes flow:**
   - Token counts (`token_in`, `token_out`) — does opencode export
     these in v4 mode?
   - `current_tool` updates — SSE stream from opencode HTTP API
   - `todos` mirrored into TODOS store
   - `tool_history` for the timeline ribbon
   - `last_tool_call_summary` (alpha.16.5)
   - `last_message_preview` (alpha.17 restore)
   - `sub_agents[]` (parent-pointer file)
3. **Runtime toggle without restart.** The Options → v4 Lab checkbox
   sets `localStorage.gmux_v4_pty=1` but the env var must already be
   set for the binary. Plan: kill the env-var gate in `lib.rs:401`
   and use the per-call `v4_mode` instead, decided at agent-spawn time.
4. **Smoke test 4 agents in v4 mode:**
   - Each shows its xterm.js terminal pane
   - State chips update live
   - Approve/reject works
   - Close via 1.1's button works
5. **Document migration path** in `docs/V4_PTY_SWAP.md`.

## Files

| What | File |
| --- | --- |
| Pane_id assignment | `app/src/index.html` ~9319 |
| Env-var → runtime | `app/src-tauri/src/lib.rs` ~401 |
| Per-pane xterm wiring | `app/src/index.html` `gmuxMountXterm` ~9194 |
| Attribute audit | `docs/V4_PTY_SWAP.md` |

## Acceptance

- 4 agents running in v4 mode show all the same data that v3/tmux mode shows
- No env-var required — Options toggle is enough
- Closing an agent (1.1's button) works in v4 mode
- Spawn-sub-agent (alpha.18) works in v4 mode

---

# Cross-cutting infrastructure (do once, benefits all)

These aren't user-visible features but every epic above needs them.

## Test harness

- `tests/` directory with pytest-style headless tests using a
  scriptable webview (e.g. Playwright on the Tauri webview, or
  a thin Node script that loads `index.html` standalone).
- CI runs them on each push. Currently we have 13 headless tests
  per the alpha.17-dev1 handover — those should be extended.

## Telemetry / debug page

- An Options → "Debug" tab showing:
  - Connected backend (Tauri / HTTP / mock)
  - Last 10 SSE events
  - Render tick rate
  - Memory: how many DOM nodes, how large `panes` object is
  - Token-refresh status (last attempt, success/fail)
- Right now the user has to open DevTools to see this.

## Crash & restart resilience

- `backend/status/monitor.py` already auto-spawns gmux-monitor and
  gmux-voice if their ports aren't bound (lib.rs:1700ish). Extend
  this so a daemon crash within the first 5s triggers a retry.
- Session-restore manifest writer (alpha.17-dev1) is already on this
  pattern; the bridge/voice daemons can copy it.

---

# What we explicitly are NOT doing

- **Multi-window UI** — keep gmux a single window (Agent Monitor is
  the lone exception and only because it's intentionally a separate
  display).
- **Cloud-hosted gmux** — out of scope. SSH tunnel + Tailscale cover
  the "remote machine" use case.
- **AI orchestration** (gmux deciding what agents should do) — gmux
  remains a monitor + control surface, not a director.
- **Tamagotchi creature, gesture aquarium, decorative animations** —
  defer indefinitely. Function over form until alpha.30.

---

# Working pattern with this user (assistant note)

For the next agent picking up this roadmap:

1. **Save a checkpoint binary + source snapshot BEFORE each iteration.**
   Use `archive/binaries/` and `archive/snapshots/`. Pattern from
   alpha.17 is `gmuxtest-vX.Y.Z-STAMP` and `vX.Y.Z-STAMP.tar.gz`.
2. **Each fix is its own focused commit.** Multi-fix commits are
   acceptable for tightly related UI tweaks (see
   `7efbece fix(ui): alpha.17-dev2 — three small UI fixes`).
3. **Screenshot after every visible change.** Use
   `/tmp/safe-shot.sh <window-id> /tmp/out.png` — resizes to ≤1600px
   per longest side, mandatory per CLAUDE.md (avoids agent crash on
   image read).
4. **Tag conservatively.** Only when a feature set is verified working.
   Move the tag if mid-tag regressions surface (alpha.17-dev2 was
   re-tagged THREE times during dev2's review cycle — that's fine).
5. **Don't `rm -rf` anything** — copy to `archive/` first per
   CLAUDE.md. The user has lost approved work to "cleanup" deletes
   in past projects.
6. **Don't keep adding features when something has regressed.** The
   user is specific about feedback — listen and ACT before the next
   feature.
7. **The user is intermittent at the keyboard.** Write verbosely so
   they can resume at any point without losing context.
