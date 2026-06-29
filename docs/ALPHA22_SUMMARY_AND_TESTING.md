# gmux alpha.22 — Summary & Testing Checklist

_Date: 2026-06-12 · commit `dfdf1c3` (composer + permissions + icon)_

---

## What changed

### 1. Frictionless agent creation — chat-panel composer
The "press Create" flow is replaced by a **composer that lives in the chat panel**.

- **`N`** → chat panel opens in *composer mode*. An info bar appears **above the
  prompt entry** showing four preselected fields:
  - **Agent type** (QalCode 2 default / last-used)
  - **Model** (last-used)
  - **Permission mode** (🛡 Safe / ⚠️ Yolo / ⚡ Yolo Extreme — mirrors global mode)
  - **Working folder** (this session's last-used folder)
- You **just type a prompt and press Enter** → the agent spawns and your prompt
  is delivered as its first message. No Create button.
- **Esc** cancels composer mode.
- **`Shift+N`** still opens the *full* New Agent dialog (presets, parent selection,
  naming) for advanced cases.
- Typing into an **empty / not-started / dead pane** no longer dead-ends with an
  error — it flips into composer mode and **carries your typed text over**, so one
  more Enter launches a fresh agent with that prompt.

### 2. Permission mode actually reaches the agent (bug fix)
Previously the safe/yolo/extreme pills were **computed but silently dropped** — every
agent launched in safe mode. Now wired end-to-end through the Rust spawn commands:

| Agent | Safe | Yolo (restricted) | Yolo Extreme |
|-------|------|-------------------|--------------|
| opencode/qalcode | `opencode` | `opencode --agent yolo` | `opencode --agent yolo-extreme` |
| claude | `claude --model X` | `+ --dangerously-skip-permissions` | same |
| aider | `aider --no-pretty` | `+ --yes-always` | same |

### 3. Sub-agents inherit parent permissions
`spawn_sub_agent_v4` now receives the **parent pane's recorded permission mode**, so
a yolo parent produces yolo children with no re-prompt. Mode is stored in
`gmux_v4_meta` (localStorage) and survives app restarts; also written into the
sub-agent JSON record for the flowchart.

### 4. App taskbar icon fixed
Window app_id is `gmuxtest`. Installed the real gmux logo into
`~/.local/share/icons/hicolor/{32,128,512}/apps/` (as `gmux.png` + `gmuxtest.png`)
and created/updated matching `.desktop` files. Taskbar now shows the gmux swirl.

---

## Manual testing checklist

### A. Composer (frictionless creation)
- [ ] Press **`N`** with a session open → chat panel shows the composer bar
      (agent/model/permission/folder) above the prompt entry, header reads "✦ New agent".
- [ ] The four fields are **prefilled** (QalCode 2, last model, current permission,
      session's last folder).
- [ ] Type a prompt, press **Enter** → toast "New chat … starting", a new pane appears
      within ~2s, and your prompt is delivered once the TUI boots.
- [ ] Press **`N`**, then **Esc** → composer closes cleanly, no orphaned panel.
- [ ] Change the **folder** field to a different path, launch → agent starts in that folder.
- [ ] Change **agent type** to Claude, launch → pane runs `claude --model …`.
- [ ] Select an **empty/not-started pane**, type in the chat box, Enter → it flips to
      composer mode with your text preserved; Enter again launches.
- [ ] Press **`Shift+N`** → the *full* New Agent dialog still opens (presets, parent).

### B. Permissions reach the PTY
- [ ] Composer permission = **🛡 Safe**, launch qalcode → in the pane terminal it ran
      plain `opencode` (agent asks before acting).
- [ ] Composer permission = **⚠️ Yolo**, launch → terminal shows `opencode --agent yolo`.
- [ ] Composer permission = **⚡ Yolo Extreme**, launch → `opencode --agent yolo-extreme`.
- [ ] Claude + Yolo → terminal shows `claude --model … --dangerously-skip-permissions`.

### C. Sub-agent inheritance
- [ ] Create a parent agent in **Yolo** mode.
- [ ] `Shift+N` with that pane as parent → create a sub-agent.
- [ ] Confirm the sub-agent launched with the **same yolo flags** (check the pane's
      terminal start command, or `/tmp/gmuxtest-sub-agents.json` → `permission_mode`).
- [ ] Restart the app → parent's permission mode is remembered (gmux_v4_meta).

### D. Icon
- [ ] Taskbar / alt-tab shows the gmux logo (not a generic terminal icon).
- [ ] After a reboot the icon persists.

---

---

## E. Looping / supervisor agent ♻️
- [ ] Press **N** → in the composer, tick **"♻️ Looping / supervisor agent"** →
      a mode dropdown + nudge-prompt field appear.
- [ ] Launch it → the new pane has a **dashed-teal frame** and a **`♻️ super`**
      badge in its header.
- [ ] With the supervisor running, start a **worker** agent and give it a task.
      When the worker finishes (goes ready/idle), confirm the supervisor sends a
      "continue" nudge into the worker's terminal (watch the worker's PTY; check
      the action log for `[supervisor] … nudged …`).
- [ ] Switch supervisor to **Notify mode** with a test URL (e.g. a webhook.site
      URL) → when a worker stalls, a JSON POST arrives at that URL.
- [ ] Restart the app → the supervisor pane is still tagged (badge + frame
      persist via `gmux_v4_meta`).

## F. Smart concurrency governor ⚖️
- [ ] Open **Options → Layout → Agent behaviour** → "Smart concurrency
      governor" toggle is **on** by default.
- [ ] The **⚖️ lamp** appears in the topbar (right side) showing `active/budget`
      and green/amber/red.
- [ ] Run several agents until one gets **rate-limited** → action log shows
      `[governor] rate-limit observed — concurrency budget ↓`, lamp goes red.
- [ ] After a clean 60s → log shows `[governor] clean 60s — budget ↑`, lamp
      returns toward green.
- [ ] With auto-resume on and multiple agents rate-limited, confirm resumes are
      **staggered** (log: `[auto-resume] staggering … by …ms (governor)`), not
      all at once.

## G. Scheduled sessions & timers ⏰
- [ ] Options → "Schedule & timers" → add a timer for **1–2 minutes from now**
      with a folder + prompt, repeat = once.
- [ ] Wait → at that minute an agent launches automatically (toast + the agent
      appears), and the once-timer flips to disabled.
- [ ] Add a **daily** timer → confirm it persists across app restarts
      (`gmux_schedules` in localStorage) and shows in the list with ⏸/✕ controls.
- [ ] Leave the prompt **blank** → confirm it still launches (warm-up only, no
      first message sent).

## H. Audio alerts 🚂
- [ ] Options → "Sound alert when an agent needs attention" → toggle **on** →
      you hear the train whistle immediately (confirmation + primes audio).
- [ ] Change "Alert sound" → each selection plays a preview; **▶ Test** replays.
- [ ] With alerts on, let an agent finish / hit a permission prompt → the chosen
      sound plays once on the transition (not repeatedly).
- [ ] Toggle **off** → no sound on the next transition.

---

## Known caveats
- Synthetic-pointer GUI automation is unreliable under XWayland, so the composer
  and these panels were verified by code + build presence, not an automated
  click-through. The keypress/Options tests above are the real confirmation.
- Governor budget is an **adaptive estimate** (halve-on-429, +1/clean-minute),
  not a hard API quota read. Conservative by design.
- Supervisor `notify` mode needs a reachable URL; `reprompt` mode needs the
  worker to be a v4 PTY agent (has `v4_session_id`).
- `gmux-ptyd` (terminals surviving app restarts) is designed in
  `docs/GMUX_PTYD_DESIGN.md` but not yet built — say go to build it.
