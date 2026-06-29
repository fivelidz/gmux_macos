# gmux v4 — Full Handover Document
## Alpha.15 State + All Open Issues + User Feedback Log

**Date:** 2026-05-18 (session ended mid-context)
**Current tag:** `v4.0.0-alpha.15`
**Binary:** `app/src-tauri/target/release/gmuxtest` (18MB, built 03:07 UTC)
**Backups:** `archive/binaries/gmuxtest-v4.0.0-alpha.*`
**Tests:** 13/13 headless green (`./scripts/launch-v4.sh --test`)

---

## How to restart where we left off

```bash
# 1. Check what's running
pgrep -af release/gmuxtest
curl -s http://localhost:8769/health

# 2. Launch (or use script)
env GMUX_V4_PTY=1 DISPLAY=:0 GDK_BACKEND=x11 GST_DEBUG="*:0" \
  GST_PLUGIN_FEATURE_RANK="v4l2src:NONE,v4l2sink:NONE,v4l2videoenc:NONE" \
  WEBKIT_DISABLE_COMPOSITING_MODE=1 \
  nohup ~/projects/gmux_v4/app/src-tauri/target/release/gmuxtest \
  > /tmp/gmux-v4.log 2>&1 < /dev/null &
disown $!

# 3. Confirm brand badge says 4.0.0-alpha.15
# (click badge for build time toast)

# 4. Run tests
cd ~/projects/gmux_v4 && bash ./scripts/launch-v4.sh --test
```

---

## What works well (stable, don't break)

- ✅ 211/211 Python tests (`test_monitor_producers` 117, `test_sub_agents`
  30, `test_memory_aggregator` 64)
- ✅ Release binary builds in ~25s after first compile
- ✅ Monitor.py sidecars launch from gmux_v4's own backend
- ✅ `interrupt_agent` command (Esc/Ctrl-C for running agents)
- ✅ Model picker on pane cards (click model badge → popover)
- ✅ Agent-type badge (claude/opencode/qalcode/aider) colored + named
- ✅ Task progress numbers (4/5) in sidebar agent rows
- ✅ Sidebar session group headers are clickable to switch session
- ✅ Stop button in progress row + chat panel (stops agents mid-run)
- ✅ YOLO model presets (Yolo Sonnet 4.6, Yolo Opus 4.7 auto-set both)
- ✅ `Ctrl+Shift+L` element-label overlay — names every UI region so
  user can communicate precisely which element needs changing
- ✅ Brand version badge bright + clickable (shows build timestamp)
- ✅ Vite plugin bundles `dashboard/` to `dist/` on every release build
- ✅ `open_dashboard` uses `set_size + center + show + focus` so window
  appears at 1600×1000 centred (not 10×10 at -100,-100)
- ✅ Providers panel shows "Switch account" + "Add another" options

---

## OPEN ISSUES (all unresolved as of alpha.15)

### 🔴 CRITICAL — Agent Monitor doesn't open a visible window

**User feedback:** "the views option to open the agent monitor window
still does not work"

**What we know:**
- Dashboard HTML + JS is correctly bundled into dist/ (verified)
- lib.rs emits `gmux-state` events to the `dashboard` window label
- dashboard's `data.js` correctly listens for Tauri events
- The window IS being created (xdotool shows it exists)
- But it appears at 10×10 px at position -100,-100 in KDE/Wayland
- alpha.10+ `open_dashboard` forces `set_size(1600×1000) + center()`
- alpha.11 `open_dashboard` returns diagnostic toast — user MUST click
  "Agent Monitor" and tell me what the toast says

**Diagnosis needed:**
Right-click in gmux → Inspect → Console, then click "Agent Monitor".
Console should show: `[gmux] open_dashboard → open_dashboard: visible_before=...`
Tell an agent what this line says.

**Reference:** `docs/AGENT_MONITOR_DEBUG.md` has full history.

**Workshop fallback:** `agent-monitor/` folder is a self-contained
rebuild environment. Another agent can build it there and integrate back.

---

### 🔴 CRITICAL — Agent Monitor content (even if window opens)

**User feedback:** "it is not linked to the backend properly. It should
display only running agents and show the files that it has touched
historically as well as what it is currently working on."

**What the dashboard SHOULD show:**
1. Only active agents (state: working/waiting/permission/sub_permission)
2. Files each agent has touched (from `/tmp/gmuxtest-files.json`)
3. What the agent is currently working on (`current_tool` + `tool_history`)
4. Flow/graph visualisation of agent ↔ file relationships
5. Live updates (no manual refresh)

**Workshop spec:** `agent-monitor/spec/AGENT_MONITOR_SPEC.md`
**Backend contract:** `agent-monitor/docs/BACKEND_CONTRACT.md`

---

### 🟡 UI — Chat panel proportion is wrong

**User feedback:** "The chat message area is just the wrong proportion
to the pane grid."

**Root cause:** When `screen.width >= 2900` (user has 3440×1440
ultrawide), chat defaults to 480px. But user windows gmux at 1400px,
leaving only ~800px for pane-grid (sidebar=220 + chat=480 = 700px
overhead). Fixed in alpha.15 with a 28%-of-window cap but user
hasn't confirmed this is correct yet.

**Tuning knob:** Drag the splitter between chat and pane-grid. Width
is saved in `localStorage gmux_chat-w` and survives restarts.

**If still wrong:** The JS formula is in `_screenAwareChatDefault()`.
Current: `base = 380/420/480 by screen, cap = min(base, window*0.28)`.

---

### 🟡 UI — Topbar single row not working properly

**User feedback:** "brand version should be on the same row as the
session tabs. The session, title and options tab should be on the same
row IF space allows for it."

**What we built:** In alpha.15 topbar is `flex-wrap:nowrap`, strict
single row. Session-tabs is `flex:1 + overflow-x:auto`. Non-essential
buttons (mode-badge, gesture, voice) hide at <1100px. This SHOULD keep
brand+sessions+options on one row. User has NOT confirmed this works.

**User monitor setup:** 3440×1440 (primary) + 1920×1200 (secondary).
When windowed at 1400px, the topbar has ~1400px to work with which
SHOULD fit everything on one row.

---

### 🟡 UI — Claude usage badge not showing (despite being connected)

**User feedback:** "I am connected to claude but the usage bar still
does not appear."

**Root cause found:** `~/.claude/.credentials.json` has an EXPIRED
OAuth token (expires_at is 24h in the past). The Rust `get_claude_usage`
command reads this file, finds expired token, returns `needs_auth: true`,
and the JS was previously hiding the badge when `needs_auth: true`.

**Alpha.14 fix:** Badge now shows a placeholder "⏳ Claude usage…" from
first paint, then shows "🔑 Connect Claude" when token is expired.
User should see one or the other.

**To get real usage data:** User needs to refresh their Claude CLI token:
```bash
claude /login
# or
opencode auth login anthropic
```

This will update `~/.claude/.credentials.json` with a fresh token.
After that, the badge should show actual percentages.

**Secondary issue:** If user says the badge still doesn't appear,
check DevTools console for `[gmux usage]` log lines. They log every
30s fetch result.

---

### 🟡 UI — "Already connected" providers UX

**User feedback:** "Connect claude is displayed at the bottom but I
can't connect to claude as it says it is already connected. This is bad
as well as it should allow the connection of different accounts,
subscriptions and API"

**What we built in alpha.15:** Providers panel now always shows:
- "↺ Switch account" button on every authed provider
- "✕ Disconnect" for file-based OAuth providers
- "Add another [Provider]" visible for all providers (not just unauthed)
- Caption: "Connect a new account or API key — you can have multiple
  per provider."

**Has not been tested by user yet** — needs confirmation.

---

### 🟢 LOW — Agent output panel too wide in windowed mode

**User feedback:** "The agent output display panel you are making wider
when the app launches windowed and it is squashing the combined agent
panels. It would be better if it could be made wider on wider screens
only."

**Status:** Addressed in alpha.15 with the 28%-window-cap rule. User
hasn't confirmed.

---

## USER FEEDBACK LOG (verbatim)

These are all the improvement requests from this session, verbatim, for
reference by the next agent. All should be checked against the OPEN
ISSUES section above.

### Layout + sizing

> "the agent output display panel on default should be wider on a wide
> screen"

> "if the sessions/ options tab is too cramped the session tabs should
> wrap"
*(Note: User later said they should stay on same row if space allows —
so wrap is a fallback, not the primary behaviour)*

> "In windowed mode with many sessions the options menu is pushed off
> screen and can't be accessed. This could be bad on very small screens
> so a solution should be thought of."

> "the session, title and options tab should be on the same row IF
> space allows for it"

> "brand version should be on the same row as the session tabs"

> "The chat message area is just the wrong proportion to the pane grid."

> "The wider output display should not be so big when windowed, it just
> should be able to be wider when the monitor has a widescreen, it's
> like you did this the wrong way around and proportions have gotten
> worse not better."

> "It doesn't need to wrap in non windowed mode when the screen is wide.
> I don't need too tab lines then, only when the app can't support the
> length of it."

### Agent sidebar

> "The agents displayed there should have more than just the progress
> bars, it should also have numbers that show the to do list progress
> such as 4/5"
*(Done in alpha.12)*

> "In the side agents tab clicking the session names should allow us to
> swap to those sessions."
*(Done in alpha.12)*

> "The claude usage should be displayed in the bottom left like the
> maestro repo and be linked to the claude account too. Add these points
> also to the todo list, this should exist at the bottom of this agents
> management panel."
*(Badge added, not always visible — see open issue above)*

### Agent Monitor

> "the agent monitor link just opens another set of gmux panels, not
> the flowchart display of agents."

> "openning agent monitor still does not work?"

> "It should display only running agents and show the files that it has
> touched historically as well as what it is currently working on."

> "The views option to open the agent monitor window still does not
> work. Remember this is the system with the flow chart showing the
> agent accessing different files in different ways."

### Agents + models

> "It is not possible to select the right agent I want. For example I
> want our yolo sonnet4.6 or our yolo opus 4.7 as options. When I input
> a command it just uses build sonnet 4.6"
*(Done in alpha.6 — Yolo Sonnet 4.6 + Yolo Opus 4.7 presets exist)*

> "There is no agent display on the panel or in the agent screen
> details."
*(Done — model badge + agent-type badge on every pane card)*

> "I want there from gmux to be a means to cancel the agent running
> like how we would press escape here."
*(Done — Stop/Esc button in progress row + chat panel)*

### Providers

> "the connect claude link should instead be to connect providers and
> link to that section in options."
*(Done in alpha.6 — links to Providers tab)*

> "Connect claude is displayed at the bottom but I can't connect to
> claude as it says it is already connected. This is bad as well as it
> should allow the connection of different accounts, subscriptions and
> API"
*(Fixed in alpha.15 — Switch account + Add another options)*

> "I am connected to claude but the usage bar still does not appear."
*(Open issue — token is expired, user needs: `claude /login`)*

### Other

> "Some panels seem to be incorrectly conveying current agent states
> too. like saying waiting when they are actually working."
*(Partially addressed — 'waiting' relabelled to 'ready' in alpha.9.
The deeper issue is the SSE event ordering in monitor.py.)*

> "Panels should default on sessions to just display the agent panels
> that have something relevant running."
*(Done — Active/All toggle in toolbar, defaults to Active)*

> "I am confused about how the v4 PTY is going to be implemented."
*(Documented in `docs/V4_PTY_PLAN.md` and `docs/V4_BACKEND_DESIGN.md`)*

---

## What the next agent should do first

1. **Launch the app** and confirm the brand badge shows `4.0.0-alpha.15`
   and build time `2026-05-18 03:07:00 UTC`.

2. **Verify the topbar** is on one row (brand + sessions + options).
   If it's still wrapping in a wide window → the `flex-wrap:nowrap` CSS
   isn't taking effect; check for overriding styles.

3. **Test Agent Monitor** — click Views ▾ → 🧠 Agent Monitor. A toast
   should appear with diagnostic text. Report the exact toast content.
   If a window appears but is blank → check DevTools console for
   `[data] Tauri webview detected:` log line.

4. **Check Claude usage badge** at the bottom of the agent panel.
   - Shows "⏳ Claude usage…" → JS is running but waiting for fetch
   - Shows "🔑 Connect Claude" → token expired; run `claude /login`
   - Shows "XX% weekly" → working!
   - Nothing visible → check DevTools `[gmux usage]` log lines

5. **Check providers panel** (Options → Providers). Should show
   "↺ Switch account" and "+ Add another Anthropic" even when authed.

6. **Test chat proportion** — make the window 1400×900 (windowed), open
   a chat. Chat should be ~28% of 1400 = ~392px. Pane grid gets ~788px.
   If chat is wider than that, localStorage `gmux_chat-w` may have a
   saved value from a previous session — clear it with:
   ```js
   localStorage.removeItem('gmux_chat-w')
   ```
   then reload.

---

## Maestro reference

We tried to build maestro (`github.com/its-maestro-baby/maestro`) to
run side-by-side for comparison. It failed due to a Linux build.rs
path-resolution bug (binaries/maestro-mcp-server not found even when
present). The build script is correct in principle but has a race
condition where `target/release/` gets cleaned between steps.

**Their UI screenshot** (2551×1430) is at:
`/tmp/maestro/assets/platform_screenshot.png`

Key maestro UI patterns we want to adopt:
- Bottom-of-sidebar usage strip with:
  - A small "tamagotchi" character (pixel art creature)
  - Usage progress bar (horizontal, h-1.5)
  - Label: "XX% weekly" / "XX% daily"
  - Color: red=low, orange=medlow, purple=mid, blue=high, green=great
  (high usage = green = you're using your subscription productively)
  ← **DONE in alpha.15**
- Drag-to-resize panels
  ← **DONE — chat-panel + graph-panel have left-edge resize handles**
- Clean single-row topbar
  ← **Attempted — needs user confirmation**

---

## Git history this long session

```
5d990ce v4.0.0-alpha.15: usage color + topbar + chat proportion + providers UI
8a04d7e v4.0.0-alpha.14: element labels overlay + topbar one-row + screen-aware chat
9e3ec9d v4.0.0-alpha.13: simpler layout — sensible chat width + reliable topbar wrap
658e661 v4.0.0-alpha.12: topbar wrap fixed + screen-aware chat + sidebar usage badge
4b58ab8 docs: AGENT_MONITOR_DEBUG.md
fdc606d v4.0.0-alpha.11: wider chat on widescreen + topbar wraps + sidebar groups
d9c5bf4 v4: global Ctrl+Alt+D shortcut also uses explicit-geometry fix
28d368f v4.0.0-alpha.10: Agent Monitor + resizable panels + responsive grid
84deae3 v4.0.0-alpha.9: state-label clarification + multi-line toast
de5379e v4.0.0-alpha.8: Agent Monitor + version badge + ergonomics
7d7106c v4.0.0-alpha.7: v4↔v3 parity (chat + interrupt + state) + version badge
02674e1 v4: interrupt_agent Tauri command
22eb041 v4.0.0-alpha.5: launch-v4.sh + 13/13 headless tests green
```

---

## Binary archive

```
archive/binaries/
├── gmuxtest-v4.0.0-alpha.7-20260517-2237
├── gmuxtest-v4.0.0-alpha.9-20260517-2255
├── gmuxtest-v4.0.0-alpha.10-20260518-0016
├── gmuxtest-v4.0.0-alpha.10-20260518-0145
├── gmuxtest-v4.0.0-alpha.11-20260518-0819
├── gmuxtest-v4.0.0-alpha.12-20260518-1157
└── gmuxtest-v4.0.0-alpha.13-*  (somewhere in /tmp or local)
```

To roll back: `cp archive/binaries/gmuxtest-v4.0.0-alpha.X <target>`

---

*This document was written after a context-window disconnect. The user's
exact final words before disconnection: "WE got disconnected. please
continue and do a write up on progress and objectives. record all my
prompts and notes so these issues are known for next time too until fixed"*
