# gmux-system — Full Testing Checklist

**For:** v3.3 and onward
**Last updated:** 2026-05-12
**Companion to:** TESTING_GUIDE.md (the *how*), this file is the *what*.

Tick every box before stamping a version. Use this as a literal pre-flight
checklist. If a check fails, file it as a bug and link the commit that
broke it.

---

## 🟢 Pre-flight — services and sanity

- [ ] **Monitor process running** — `ss -tlnp | grep 8769` returns a line
- [ ] **Voice daemon running** (if voice features needed) — `ss -tlnp | grep 8770`
- [ ] **`/health` returns `ok`** — `curl -s http://127.0.0.1:8769/health`
- [ ] **`/api/state` returns valid JSON with at least 1 pane** — `curl -s http://127.0.0.1:8769/api/state | python3 -m json.tool | head`
- [ ] **At least 1 pane has `model` populated** (real data is flowing) — see the smoke test
- [ ] **MD5 sync check**: source UI matches all three mirror locations
  ```bash
  md5sum ~/projects/gmuxtest/UI_creation_independent/v2/index.html \
         ~/projects/gmuxtest/src/index.html \
         ~/projects/gmux-system/ui/v3/index.html
  ```
- [ ] **No console errors on page load** — open DevTools, reload, check Console tab is clean
- [ ] **No 404s in Network tab** — except optional CDN fallbacks (MediaPipe model)

---

## 🟢 Data layer

### Live data
- [ ] Status bar shows `● tauri live` (in Tauri) or `● live :8769` (browser) — NOT `● mock`
- [ ] Pane count in topbar matches `tmux list-windows -a | wc -l`
- [ ] Real session names appear in session tabs (not just `gmux/work/personal` placeholders)
- [ ] Each pane shows its real `window_name` (project folder name, not "fish" or "bun")
- [ ] State dot colours match the real state of each agent (working = green, waiting = red, permission = orange)
- [ ] Permission badges appear within 2s of a real opencode permission prompt
- [ ] Last terminal line updates within 2s of agent output

### Fields per pane
For any pane with an active opencode session:
- [ ] **Model name** shown (e.g. `claude-sonnet-4-6`)
- [ ] **Token count** matches `info.tokens` from opencode API (verify via `curl http://127.0.0.1:<port>/session/<id>/message`)
- [ ] **RAM** non-zero, matches `ps -p <bun_pid> -o rss`
- [ ] **CPU%** updates every 2s (test by running an agent task)
- [ ] **Uptime** ticks up by ~2s every poll
- [ ] **Todo count** matches `/session/<id>/todo` length
- [ ] **Todo content text** matches actual todo items (not "Test C2 fix..." mock)
- [ ] **Cost USD** present (may be 0 in current QalCode 1.1.x — that's expected)

### Mock fallback (test by stopping backend)
- [ ] Kill monitor: `pkill -f gmux-system/backend/status/monitor.py`
- [ ] Status bar switches to `● mock` within 8s
- [ ] Red `⚠ backend down — restart` button appears
- [ ] Click restart → backend respawns and label returns to `● live`
- [ ] In Tauri: restart works via `invoke('restart_backend')`
- [ ] In browser: shows helpful toast pointing to `./scripts/launch.sh`

---

## 🟢 UI core layout

### Agent sidebar
- [ ] All panes from all sessions visible (`activeSession === 'all'`)
- [ ] Clicking a session tab filters the sidebar correctly
- [ ] Clicking "All" shows everything again
- [ ] Sort dropdown options work: priority / name / RAM / window
- [ ] In RAM-sort mode, RAM column appears beside each row

### Session tabs (top strip)
- [ ] **Distinct visual styling from window tabs** — sessions look more elevated, window tabs more recessed
- [ ] Active session has visible highlight (glow, brighter background)
- [ ] Counter badge per session shows correct pane count
- [ ] `+ add session` button opens a prompt and creates a new session row

### Window tabs (tabstrip below)
- [ ] All windows of currently-selected session listed
- [ ] Active window highlighted distinctly from session-tabs styling
- [ ] Clicking a window tab selects that pane

### Pane grid
- [ ] Default grid mode (`auto`) chooses sensible columns based on pane count
- [ ] Switching grid mode in Options (2/3/4/6 columns) works immediately
- [ ] Click a pane → it gets the "selected" outline + brightness boost
- [ ] Drag a pane onto another → insert-above visual indicator appears, drop reorders correctly
- [ ] Voice target pane (when voice on) has a distinct red outline
- [ ] Empty session shows "No agents in this session" placeholder

---

## 🟢 Pane internals — tab cycle (Tab key)

Test each of the three tabs on a real pane with active opencode:

### Todos tab
- [ ] Todo items listed with real content text
- [ ] Completed items have ✓ checkbox + strikethrough
- [ ] In-progress item has ⬛ + accent colour
- [ ] Progress bar reflects `done/total` accurately
- [ ] Activity line at bottom shows real `last_line` from tmux
- [ ] Working state shows the dot spinning

### Chat tab
- [ ] Last 3-5 messages of the conversation appear inline
- [ ] User messages on right, agent on left
- [ ] Auto-scrolls to bottom when entering this tab
- [ ] "No conversation history yet" shown if cache empty

### Hardware tab — **CRITICAL** (was broken in v3.1 by a typo)
- [ ] Tab loads without throwing — pane body has content (not blank)
- [ ] RAM bar shows real MB value, fills correctly proportional to budget
- [ ] CPU bar shows real %, colour-warns at >60% (orange) and >80% (red)
- [ ] Model name shown (`claude-sonnet-4-6` etc)
- [ ] Session, Port, Tokens, Cost, Uptime, Tool all populated
- [ ] Tool history timeline renders ticks (one per recent tool call)
- [ ] Child processes section appears if pane has children, else hidden gracefully

---

## 🟢 Chat panel (right sidebar)

### Open / close
- [ ] Clicking an agent auto-opens the chat panel (when `autoChat` is on)
- [ ] Chat panel shows the agent's name + state dot in header
- [ ] ⛶ button toggles fullscreen mode

### Message rendering
- [ ] User prompts appear right-aligned, blue tint
- [ ] Agent responses appear left-aligned, default tint
- [ ] Tool calls collapsed into compact monospace rows
- [ ] Streaming messages show animated cursor (`▌`)
- [ ] **Markdown rendering** (CRITICAL — added in v3.2):
  - [ ] Triple-backtick code blocks render with dark background + monospace + language label
  - [ ] Inline `code` highlighted yellow with rounded background
  - [ ] **bold** and *italic* both work
  - [ ] # ## ### headings size appropriately
  - [ ] - lists indent with bullets, `1.` lists too
  - [ ] > blockquotes have left border + tinted background
  - [ ] Links `[text](url)` are clickable, open in new tab
  - [ ] Horizontal rule `---` renders as thin line
  - [ ] Plain text paragraphs separated by blank lines have correct spacing

### Input
- [ ] Type → Enter sends (Shift+Enter for newline)
- [ ] Mic button (`🎙`) — hold-to-talk works if voice daemon is up
- [ ] `↑` button (history):
  - [ ] **Single click** → scrolls chat to last user message + flash-highlights it
  - [ ] **Double-click** → loads the last prompt into input
  - [ ] **↑ key when empty** → cycles backwards through history
  - [ ] **↓ key when navigating** → cycles forwards
- [ ] Button glows accent when there's history to recall

### Fullscreen mode (v3.2+)
- [ ] **Sidebar (left) stays visible** — agent list still clickable
- [ ] **Session tabs (top) stay visible** — clicking another session updates chat in place
- [ ] **Window tabs stay visible** — clicking another window switches the active agent in fullscreen
- [ ] Esc key closes fullscreen
- [ ] On widescreen (≥1400px) → todos panel appears on the right side
- [ ] Todo panel shows real todos with title "Tasks · &lt;agent name&gt; · done/total"
- [ ] Switching agents while in fullscreen → todos panel updates to new agent's tasks
- [ ] On narrower screens → todos panel hidden, only chat shown

---

## 🟢 Themes (v3.3 features)

### Built-in presets
- [ ] All 10 themes render in the grid: Ocean, Gruvbox, Forest, Crimson, Slate, Amber, Mono (dark), Paper, Latte, Sand (light)
- [ ] "Dark" and "Light" section headers visible
- [ ] Clicking a preset:
  - [ ] Whole UI re-themes instantly
  - [ ] Custom-colour pickers below update to show that preset's values
  - [ ] Active preset card gets highlighted border
  - [ ] Toast says "Theme: &lt;name&gt;"

### Custom colours (v3.3 — formerly was hardcoded Ocean)
- [ ] Open Options → Style → Custom Colours collapsible
- [ ] All ~15 pickers show values matching the active preset
- [ ] Hex code label beside each picker matches the swatch
- [ ] Changing a picker → UI updates live + hex label updates
- [ ] Reset button → re-applies the active preset's defaults

### User themes (v3.3 — new)
- [ ] Tweak a colour, type a name in "my-theme" input, click 💾 Save
- [ ] Toast says `✓ Saved theme "<name>"`
- [ ] New theme appears under "My themes" section in the grid with a ⭐
- [ ] Clicking the user theme applies it
- [ ] Hovering a user theme card → red `×` delete button appears top-right
- [ ] Clicking × → confirm dialog → on yes, theme removed and grid re-renders
- [ ] Saving with an existing name → confirm dialog asks to overwrite
- [ ] Themes persist across page reloads (stored in `localStorage['gmux.userThemes']`)
- [ ] On reload, last-active theme (built-in or user) is auto-applied

---

## 🟢 Tab strip distinction (v3.3)

- [ ] Session tabs (top) and window tabs (below) are **visually distinct**
- [ ] Session tabs background is brighter (more elevated)
- [ ] Window tabs background is darker (more recessed)
- [ ] Both have different active-state styling
- [ ] In dark theme: session tabs have a subtle accent-glow inset shadow
- [ ] In light theme: distinction is still readable

---

## 🟢 Voice (when daemon running)

- [ ] Status pill `🎙 LIVE` visible at top of chat panel when voice mode is on
- [ ] Speak into mic → words appear in voice transcript area in real-time
- [ ] Final transcript replaces interim text smoothly
- [ ] Voice gauge bar animates with amplitude
- [ ] Wave canvas draws live audio waveform
- [ ] `V` key or 🎙 button toggles voice mode
- [ ] CapsLock toggles voice (alternate hotkey)

---

## 🟢 Gestures (when MediaPipe camera enabled)

- [ ] `G` key toggles gesture mode
- [ ] Camera permission prompt appears on first toggle
- [ ] PiP video appears at top of viewport with hand landmarks drawn
- [ ] Hand-state hints update (e.g. "Right: OPEN_PALM 0.93")
- [ ] Gestures tested (one each):
  - [ ] Pinch → click at fingertip
  - [ ] Swipe right → next window
  - [ ] Swipe left → prev window
  - [ ] Point (left hand) → toggle voice
  - [ ] Thumbs up (left) → approve
  - [ ] Three fingers (left) → jump to next waiting agent
  - [ ] Open palm (left) → open chat

---

## 🟢 Hot-key reference

- [ ] `←` `→` `↑` `↓` move selection
- [ ] `J` jump to next waiting/permission agent
- [ ] `Enter` approve permission OR open chat
- [ ] `Tab` cycle pane view: todos → chat → hardware
- [ ] `Esc` close modal / chat fullscreen / overlays
- [ ] `N` new agent modal
- [ ] `G` toggle gesture
- [ ] `V` toggle voice
- [ ] `CapsLock` toggle voice
- [ ] `Space` approve selected
- [ ] `?` open hotkey help
- [ ] `F` chat fullscreen
- [ ] **Easter eggs:** triple-click brand dot → demo banner toggle; long-press → open gmux.ai/demo

---

## 🟢 Scrollbars (v3.2)

- [ ] All scrollable areas show a visible 10px-wide scrollbar
- [ ] Thumb is accent-purple, ~30px minimum length
- [ ] Hover thumb → it brightens
- [ ] `#win-tabs` and `#session-tabs` correctly have NO scrollbar (overflow:auto but hidden)

---

## 🟢 Edge cases & resilience

- [ ] **Agent dies mid-session** — pane disappears from list within 2s
- [ ] **New tmux window opens** — appears in sidebar within 2s
- [ ] **No agents at all** — UI shows empty state, doesn't crash
- [ ] **Wide-screen >2560px** — UI doesn't stretch awkwardly, max-width applies
- [ ] **Narrow viewport <768px** — chat panel becomes overlay, grid goes 1-column
- [ ] **Phone <480px** — sidebar collapses to drawer (mobile-open class on `#sidebar-panel`)
- [ ] **Backend goes down mid-session** — status bar warns, mock fallback keeps UI alive
- [ ] **Same opencode session attached to two panes** — both show same todos (correct behaviour, not a bug)
- [ ] **opencode.db is locked** — aggregator gracefully skips that pane, doesn't crash

---

## 🟢 Tauri-specific

- [ ] `npm run tauri dev` boots without compile errors
- [ ] `cargo check --manifest-path src-tauri/Cargo.toml` clean (1 warning OK: `_window` unused)
- [ ] Tauri window opens (on Wayland needs `GDK_BACKEND=x11`)
- [ ] PTY mirror works — terminal output appears in the embedded PTY
- [ ] All Tauri commands callable from JS DevTools:
  - [ ] `invoke('get_pane_state')` returns JSON
  - [ ] `invoke('backend_health')` returns `{monitor:bool, voice:bool, ...}`
  - [ ] `invoke('restart_backend')` respawns sidecars
  - [ ] `invoke('send_to_agent', {...})` posts message to opencode
  - [ ] `invoke('approve_agent', {...})` / `reject_agent` work
- [ ] Sidecars auto-start on launch (visible in `/tmp/gmux-monitor.log` etc)
- [ ] On Tauri close, sidecars cleaned up (or left running per design — check spawn_sidecars policy)
- [ ] WebView devtools accessible (right-click → Inspect in dev mode, OR open the same `http://localhost:1421/` in Chromium for proper DevTools)

---

## 🟢 Performance

- [ ] Cold start (browser) → first paint in &lt;1s, fully wired in &lt;3s
- [ ] Cold start (Tauri) → window opens in &lt;5s, all sidecars up in &lt;6s
- [ ] Idle CPU: total system ~3-5% with monitor running
- [ ] No memory leak after 30 minutes of running — RSS should stabilise
- [ ] Browser: open DevTools → Performance → record 10s, no long tasks &gt;100ms during idle
- [ ] Tauri (WebKitGTK) is noticeably slower than browser — **DOCUMENTED** known issue, use browser for dev work
- [ ] Re-renders are throttled — clicking around quickly doesn't queue up dozens of render() calls

---

## 🟢 Version sync (before commit)

- [ ] UI source file MD5 identical across all 3 mirror locations
- [ ] Rust lib.rs MD5 identical in `gmuxtest/src-tauri/` and `gmux-system/app/src-tauri/`
- [ ] `<title>` tag in source matches the demo build's title (`gmux v3.x` vs `gmux · demo`)
- [ ] Version comment in HTML top matches the version intended for this release
- [ ] HANDOVER.md / NEXT_ACTIONS.md / TESTING_GUIDE.md updated if architecture changed

---

## 🟢 Git hygiene (per release)

- [ ] All three repos pushed:
  - `gmuxtest` (private) — Rust + dev sandbox
  - `gmux-ui-demo` (public submodule) — UI only
  - `gmux-system` (private) — consolidated canonical
- [ ] Commit messages follow `feat: / fix: / docs:` prefix
- [ ] All three repos have matching commit-message wording for the same logical change
- [ ] No build artefacts committed (`node_modules`, `target/`, `*.log`)
- [ ] `extras/` folder updated if you archived any feature out of the UI

---

## 🟢 Documentation freshness (per release)

- [ ] `HANDOVER.md` reflects current architecture
- [ ] `NEXT_ACTIONS.md` updated — completed items moved to "Done in this session"
- [ ] `VERSION_CONTROL.md` matches current sync flow
- [ ] `BACKEND_CONNECTION.md` schema section matches actual PaneInfo fields
- [ ] `TESTING_GUIDE.md` and **THIS FILE** updated with new features

---

## 🟢 Final release smoke

```bash
# Run as a single one-liner
cd ~/projects/gmux-system && \
  echo "=== ports ===" && ss -tlnp | grep -E "8769|8770|5550|1421" && \
  echo "=== api ===" && curl -s http://127.0.0.1:8769/api/state | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} panes, {sum(1 for p in d.values() if p.get(\"model\"))} have real data')" && \
  echo "=== voice ===" && python3.11 -c "import asyncio,websockets; asyncio.run((lambda: websockets.connect('ws://127.0.0.1:8770', open_timeout=2))())" 2>&1 | head -1 && \
  echo "=== md5 ===" && md5sum ~/projects/gmuxtest/UI_creation_independent/v2/index.html ~/projects/gmux-system/ui/v3/index.html | awk '{print substr($1,1,12),$2}' && \
  echo "=== git ===" && git -C ~/projects/gmux-system log --oneline -1 && \
  echo "=== DONE ==="
```

All four lines should print healthy output and the two MD5s should match.

---

## What to do when something breaks

| Symptom | First check |
|---|---|
| UI blank / partial | DevTools console for `ReferenceError` or `SyntaxError` |
| `● mock` despite backend running | `curl http://127.0.0.1:8769/health` from same browser machine |
| Hardware tab fails | Look for variable name typos in `updatePaneEl()` HW template (history of bug: `children` vs `childrenSource`) |
| Todos wrong agent | Check `session_id` in state JSON — two panes with same `session_id` legitimately share todos |
| Markdown not rendering | Test in DevTools: `renderMarkdown("**hi**")` should return `'<p class="md-p"><strong>hi</strong></p>'` |
| Theme picker shows wrong values | Reload the page; pickers refresh on Options-open or theme switch |
| Tauri laggy | Use `npm run tauri build` for release performance — dev mode adds significant overhead |

---

## 🟢 v3.5 — Agent + Session creation (live launch path)

### New-agent modal
- [ ] Press `N` or click `+` — modal opens with all 6 agent type tiles visible
- [ ] Selecting each agent type highlights it; only one is selected at a time
- [ ] **Working directory field is visible**, labelled "(where the agent starts — defaults to $HOME)"
- [ ] Project name field accepts free text; empty becomes "new-agent"
- [ ] Model dropdown populated with Claude / Deepseek / GPT / Gemini options
- [ ] Yolo pills (Safe / Yolo / Yolo Extreme) one-of-three selection works
- [ ] Preset list (if any presets defined) shows + preset details box reveals on click

### Live launch (Tauri mode)
- [ ] Fill working directory with a real path (e.g. `~/projects/gmux-system`) → Create
- [ ] Toast shows `✓ Agent '<name>' launching in <dir>`
- [ ] **A new tmux window opens** in the gmux session (visible in the main pane PTY)
- [ ] The window has the correct **window name** (rename succeeded via prefix+,)
- [ ] The shell is **already at the requested directory** when the new window loads (`pwd` confirms)
- [ ] The agent command runs (`opencode` / `claude` / `aider` per agent type)
- [ ] Within ~2s the new pane appears in `/api/state` (monitor catches it next poll)
- [ ] Pane state transitions `not_started` → `waiting` once agent boots
- [ ] Pane shows correct `model` (or empty if claude-cli without --model)

### Empty-directory default
- [ ] Leaving working directory empty triggers a toast: "No folder specified — using <HOME>"
- [ ] Agent launches in `$HOME` and pwd confirms

### Browser fallback (no Tauri)
- [ ] In a plain browser, Create adds a mock pane to the grid (no real tmux spawn)
- [ ] Toast clearly indicates "mock" or the directory it would have used

### Session creation
- [ ] Click `+` on the session tab strip — new tmux session is created
- [ ] New session appears in the tab strip without reload
- [ ] Each session is isolated — windows in session A don't appear in session B's pane list
- [ ] Closing the last window in a session prompts for tmux session kill

---

## 🟢 v3.5 — Agent Monitor (dashboard) end-to-end

### Producer files (backend prerequisite)
- [ ] `/tmp/gmuxtest-pane-state.json` exists, mtime within last 5s
- [ ] `/tmp/gmuxtest-activity.json` exists (may be `[]` if no tool calls yet)
- [ ] `/tmp/gmuxtest-files.json` exists (may be `{}` if no edits yet)
- [ ] `/tmp/gmuxtest-services.json` exists with at minimum `{"camera":false}`

### Dashboard window
- [ ] Toolbar shows `👁 Views ▾` dropdown
- [ ] Clicking it shows: Agent Monitor / Folder Graph / Memory Panel
- [ ] Clicking Agent Monitor opens a second Tauri window titled "gmux — agent display"
- [ ] **Ctrl+Alt+D** toggles the dashboard from any window
- [ ] Top-right HUD shows `🟢 tauri · state:N mem:N act:N files:N` with counters incrementing
- [ ] `state:` counter reaches > 0 within ~2s of opening (agents data received)
- [ ] Agent rail (left side) populates with one row per pane
- [ ] Each row shows agent name + state dot color matching the main UI

### With live tool activity (requires opencode running in a pane)
- [ ] Trigger an edit in any agent — within ~2s the file appears in the heatmap
- [ ] `act:` counter increments on each tool call
- [ ] `files:` counter increments when a file gets touched
- [ ] Flowchart renders edges from agent → folder → file for current activity
- [ ] Two agents editing the same file → file shows `is_conflict` flag (visual highlight)
- [ ] Five+ edits to the same file in 30m → `is_hot` flag (different visual)

---

## 🟢 v3.5 — Provider auth (OAuth + API keys)

Currently the UI relies on `opencode auth login` having been run before launching gmux.
**Not yet implemented in Tauri** — tracked under "qalcode2 options exposure".

- [ ] `~/.local/share/opencode/auth.json` exists (run `opencode auth login` once)
- [ ] `check_auth` Tauri command returns true (DevTools: `await __TAURI__.core.invoke('check_auth')`)
- [ ] When auth is missing, first-launch tutorial nudges user to run `opencode auth login`

**Planned (v3.6):** Settings panel with "Connect provider" buttons that shell out to
`opencode auth login <provider>` and surface OAuth callback URLs. See `docs/PROVIDER_AUTH_PLAN.md`.
