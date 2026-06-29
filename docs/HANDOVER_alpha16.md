# gmux v4 — alpha.16 series handover

**Date:** 2026-05-18
**Current version:** `v4.0.0-alpha.16.6` (post-tag commit `930bdf9`)
**Running binary:** `app/src-tauri/target/release/gmuxtest`
**Tests:** 13/13 headless green

This document covers everything the agent and user accomplished in
this session, with verbatim user feedback and exact rationale for each
change. It supersedes `docs/HANDOVER_alpha15.md` (kept on disk for
reference but the issues described there are resolved).

---

## TL;DR — what got fixed today

1. **THE BIG ONE — release builds were silently broken.** Every binary
   from alpha.7 onwards opened a blank window with "Could not connect
   to localhost: Connection refused". Root cause: the `tauri` crate's
   `custom-protocol` feature was not enabled in `Cargo.toml`. Without
   it, even `cargo build --release` produces a binary that tries to
   load `http://localhost:1421/` (the vite dev server). Fix:
   `tauri = { version = "2", features = ["custom-protocol"] }`. One
   word. Tauri's `build.rs` line 252-255 does `let dev = !custom_protocol`.

2. **Chat panel proportion.** Rewrote `_screenAwareChatDefault` to key
   off `window.innerWidth` instead of `screen.width`. Defaults now
   scale up gently with the window: 360px windowed → 900px on a maxed
   ultrawide. Drag-max bumped to 1800px so user can pull the splitter
   half-way across a 3440px ultrawide. Saved values are clamped to
   60% of current window so old saved widths don't dominate after a
   resize.

3. **Topbar wrap.** In windowed mode the topbar wraps cleanly with
   row-gap 6→8px. The `.cramped` JS observer now keeps session-tabs on
   the same row as brand+version (scrolling horizontally if too many),
   instead of taking its own full row. On widescreen everything fits
   on one row naturally.

4. **Maestro colour rule on usage badge.** Low% = red (under-using),
   high% = green (great usage). Bands: <20 red, <40 orange, <60 purple,
   <80 blue, ≥80 green.

5. **Coloured progress bar.** A skinny bar under the usage cycle row,
   width = pct, colour follows the same maestro percentage rule.
   Smooth 350ms width transitions.

6. **Click usage badge = cycle views.** Cycle order is **Weekly → 5h →
   Opus 7d → Weekly**. Default landing view is Weekly (the meaningful
   sonnet-dominated all-models number for Max users). A small `↗`
   button next to the cycle button opens `claude.ai/settings/usage` in
   the user's browser via `tauri-plugin-shell`.

7. **Faster auth-error recovery.** Cache TTL for `needs_auth: true`
   responses dropped from 30s to 5s. Window-focus events trigger an
   extra refresh (throttled). When the user runs `claude /login` to
   refresh their token externally, gmux picks up the new credentials
   within ~5s, or instantly on alt-tab back to gmux.

---

## Git history of this session

```
2f67e0b fix(ui): alpha.16.3 — tab wrap back to row-2, contained usage badge, visible bar  ← alpha.16.3
0b019fe docs: HANDOVER_alpha16.md — full session writeup
38534c4 feat(usage): coloured progress bar + Weekly default + clearer labels   ← alpha.16.2
babe7a8 feat(usage): click badge → claude.ai/settings/usage + faster cache    ← alpha.16.1
965568d feat(ui): alpha.16 UX fixes — chat width + topbar wrap + usage msg
76f40b4 fix(tauri): enable custom-protocol feature — release builds were broken
eceeeb9 alpha.16-dev: fix chat-width formula + maestro usage colour rule
84a715d rollback: alpha.15 → alpha.14 (Agent Monitor regression)
5b78cc2 Revert "v4.0.0-alpha.15: …"
e0b1e51 docs: HANDOVER_alpha15.md   (kept on purpose — useful notes)
5d990ce v4.0.0-alpha.15: …          (reverted)
8a04d7e v4.0.0-alpha.14: …          (the baseline we restored from)
```

Tags now in repo: `v4.0.0-alpha.16`, `v4.0.0-alpha.16.1`, `v4.0.0-alpha.16.2`, `v4.0.0-alpha.16.3`, `v4.0.0-alpha.16.4`, `v4.0.0-alpha.16.5`.

### alpha.16.3 (post-handover-doc UX polish)

User reported three regressions/issues with alpha.16.2:

1. **"the tab wrapping on windowed mode was better than the side
   scroll"** — earlier in this session the cramped topbar was wrapping
   sessions to row 2. Commit 965568d switched it to inline-scroll
   which the user disliked. alpha.16.3 reverts to wrap behaviour
   (`flex-wrap:wrap; width:100%; order:2` on `.cramped #session-tabs`).
2. **"On windowed mode all the panels shake when I try to click to the
   5h usage bar"** — caused by `transition:all 100ms` on the inner
   button + uncontained reflow. alpha.16.3 pins the whole `.sl-usage`
   to a fixed `height:44px` with `contain:strict`, removes `transition:all`,
   removes box-shadows that painted outside element bounds. The badge
   is now a sealed paint region.
3. **"The progress bar is not coloured"** — at low percentages the bar
   was 2px wide with a heavy box-shadow which read as a faint dot. The
   bar is now 6px tall on a visible rgba(.08) track + 1px border,
   no box-shadow, min displayed width 4%. Default fill colour removed
   so `.use-*` classes always supply the colour explicitly.

### alpha.16.4 — Sonnet-only sub-limit + page-label parity

User compared the badge to the official `claude.ai/settings/usage`
page and noticed gmux was showing **Opus** (null / 0 % for most users)
in a slot where it should be showing **Sonnet** (the real headline
sub-limit the page makes prominent).

Investigation: probed the real Anthropic OAuth API directly and found
the response has MORE fields than gmux was reading:

| API field | Page label | gmux <16.3 | gmux 16.4 |
| --- | --- | --- | --- |
| `five_hour` | 5-hour rolling | `5h` (correct) | `5h` |
| `seven_day` | "All models" | `Weekly` | `All` |
| `seven_day_sonnet` | "Sonnet only" | **missing** | `Sonnet` ✅ |
| `seven_day_opus` | "Opus only" / "Claude Design" | `Opus 7d` | `Opus` |

Changes in `app/src-tauri/src/commands/usage.rs`:
- `ApiUsageResponse` now also deserialises `seven_day_sonnet`
- `UsageData` adds `weeklySonnetPercent` + `weeklySonnetResetsAt`
- Log line includes sonnet + opus alongside the headline

Changes in `app/src/index.html`:
- Cycle order now: **All → Sonnet → 5h → Opus**
- Labels shortened to match the page: `All`, `Sonnet`, `5h`, `Opus`
  (was `Weekly`, `5h`, `Opus 7d`)

Verified live against `curl https://api.anthropic.com/api/oauth/usage`:
- `seven_day` 48 % → page "All models" 48 %  ✓
- `seven_day_sonnet` 8 % → page "Sonnet only" 8 %  ✓
- `seven_day_opus` null → page "Claude Design" 0 %  ✓

### alpha.16.5 — chat-panel activity strip + Esc binding

User feedback: *"In the output it should be shown what the agent is
with some visual system to show if it is active. Similar to how
qalcode has moving bars and the explanation to press esc to escape
and often a description of what it is doing."* and clarification *"I
mean it does show activity currently in the agent panel but I want to
see this in the chat panel also."*

Per-pane activity was already shown in the grid (`bash [0/1 tools] ◆
0 esc interrupt` line is the actual claude-code prompt being mirrored
from the tmux pane). The user wanted parity in the **chat panel** so
they don't have to scan the grid to know what the focused agent is
doing.

Added (when `state === 'working'` or permission):
```
[● Tinkering] file.py            press [Esc] to interrupt
[──────▓▓▓▓▓▓────────────────] animated marquee bar
```

The verb is derived from `last_tool_call_summary.tool` which
`monitor.py` already populates per pane — no backend change needed:

| Tool | Verb |
| --- | --- |
| write / edit / multi_edit | Forging / Tinkering |
| read / glob / grep / list | Reading / Scanning / Searching / Listing |
| bash / shell / execute | Cogitating |
| webfetch / web_search | Browsing / Surfing |
| task / todowrite / todoread | Delegating / Planning |
| no recent tool | Thinking |
| permission pending | Awaiting approval (strip turns orange) |

Detail line shows the basename of `file_path` (for file tools) or a
truncated `command` (for shell tools). Strip uses `contain:layout` so
re-renders don't shake the chat header above.

**Esc key in chat input** now stops the focused agent when:
- the textarea is empty
- the agent is in `working`, `waiting`, `permission`, or `sub_permission`

Matches the in-strip hint and the Claude CLI behaviour. With text in
the input Esc is still no-op so the user can keep typing.

### alpha.16.6 — fix false "backend down" indicator

(No formal tag yet — folded into HEAD at commit `930bdf9`.)

User noticed an intermittent `monitor down (voice OK)` notice in the
statusbar bottom-right even when the backend was actually healthy.

Root cause: `_checkBackendHealth()` was using
`await import('https://cdn.jsdelivr.net/...')` on every 8-second poll
to load the Tauri API client. When the CDN was slow / blocked /
offline, the import threw, the result fell through to a browser-mode
voice-WebSocket race, and a stale 'backend down' state was rendered
for up to ~8 seconds.

`tauri.conf.json` already had `withGlobalTauri: true` exposing
`window.__TAURI__.core.invoke` synchronously. Switched the probe
(and `_restartBackend`, and the initial data-source bootstrap
listeners) to use the global API first, with the CDN import kept
only as last-resort fallback.

---

## How to start from this point

```bash
# Pull latest
cd ~/projects/gmux_v4
git checkout main

# Verify clean release build
bash ./scripts/launch-v4.sh --test           # should say 13/13 passed

# Build (cargo will rebuild only if source touched)
(cd app/src-tauri && cargo build --release)

# Launch (NB: use systemd-run for reliable detach on KDE Wayland/X11)
systemd-run --user --scope -p RuntimeMaxSec=infinity --collect \
  env GMUX_V4_PTY=1 DISPLAY=:0 GDK_BACKEND=x11 \
  ./app/src-tauri/target/release/gmuxtest >/tmp/gmux-v4.log 2>&1 &
disown
```

Brand badge should show `4.0.0-alpha.16.2` (clean) or
`4.0.0-alpha.16.2-N-gHASH` (after extra commits).

---

## Detailed write-up per fix

### Fix 1 — `custom-protocol` feature (commit 76f40b4)

The decisive moment of the session. User came in with: *"please take
us back to alpha 14 as the new changes made a mess of things"* — but
the actual underlying problem went all the way back to alpha.7: the
release binary was loading from `http://localhost:1421/` (a dev
server) instead of the bundled `tauri://localhost/` assets, so the
window was just blank text saying "Could not connect to localhost:
Connection refused".

That URL is the vite dev port. The Tauri 2 crate decides between dev
and release mode at build time via `let dev = !has_feature("custom-protocol")`
in `tauri-2.10.3/build.rs` lines 252-255. With `features = []` in
`Cargo.toml`, the binary thinks it's a dev build and uses `devUrl`.

Fix:
```toml
tauri = { version = "2", features = ["custom-protocol"] }
```

A one-word change in `app/src-tauri/Cargo.toml`. Verified by checking
`target/release/build/tauri-*/output` files:
- Without feature: `cargo:dev=true` + `cargo:rustc-cfg=dev`
- With feature: `cargo:dev=false` + `cargo:rustc-cfg=custom_protocol`

After this fix, the entire app rendered correctly and all the
subsequent UI work could be validated visually.

### Fix 2 — Chat width (commit 965568d, refined in eceeeb9)

User feedback: *"For the chat width I think you should be considering
that it should be smaller when it is in a small window. I am quite
happy for it to be as large as a user wants it to be when sliding the
scale and wider for the widescreen. Just on default in the windowed
mode it was poorly proportional"*

Then later: *"when the screen is ultrawide though I would like the
chat panel to be able to extend across the whole way."*

Old rule (alpha.14):
```
screen.width < 2000 → 400px,  <2900 → 460px,  >=2900 → 540px
Hard cap: 40% of window
```
On a 3440px monitor with a 1400px window: 540px (= 39% of window).
That's too wide for a 1400px window.

New rule (alpha.16):
```
window <1500  → 360px  (cap 32%)  windowed
window <2000  → 440px  (cap 32%)
window <2600  → 540px  (cap 36%)
window <3200  → 700px  (cap 42%)
window >=3200 → 900px  (cap 50%)  ultrawide maxed
```
At a 1400px window → 360px, leaving 820px+ for pane-grid. At a 3440px
maxed ultrawide → 900px, with the splitter still draggable up to ~2400px
if the user wants it bigger. Splitter max raised from 900 to 1800px.

### Fix 3 — Topbar single-row + wrap quality (commit 965568d)

User feedback: *"on windowed mode the tabs should be on different
levels than running into each other"* and *"same issue with the
sessions tab and options being displayed poorly"*.

The HTML already had `flex-wrap: wrap` and a `.cramped` JS observer
that adds a class when wrapping. The observer was correct but the CSS
rule put session-tabs on its OWN full-width row, which made the brand
sit alone on row 1 (silly waste of space).

New rule for `.cramped`:
- session-tabs becomes `flex-wrap:nowrap; overflow-x:auto; flex:1 1 240px`
  so it shares the row with brand and just scrolls horizontally if too
  long
- `row-gap` increased from 6→8px so wrapped rows visually separate

Now on a 1400px windowed app: Row 1 = brand + scrollable session pills;
Row 2 = filter buttons + Active/Views/Options. On a 3440px ultrawide:
one row total.

### Fix 4 — Maestro colour rule (commit eceeeb9)

User feedback: *"1. Maestro's colour rule — usage badge now: red=barely
using, orange=some, purple=half, blue=mostly, green=great usage. High
usage is good (you paid for it, use it)."*

Previously: low=blue (calm), high=red (alarm). Now flipped per the
maestro doctrine: low usage = red (you're under-using your sub), high
usage = green (good — you're getting your money's worth).

Bands: <20 red, <40 orange, <60 purple, <80 blue, ≥80 green.
Both the dot AND the progress bar use these same classes.

### Fix 5 — Coloured progress bar (commit 38534c4)

User feedback: *"I'd like it if it displayed it with not just the
percentage but a colour changing bar."*

Added markup:
```html
<div class="sl-usage-bar"><div class="sl-usage-bar-fill" id="sl-usage-bar-fill"></div></div>
```

Fill width = `Math.max(2, Math.min(100, intPct))` % so it's never
totally invisible. `className` set to `sl-usage-bar-fill ${dotClass}`
so the bar inherits the same percentage-based colour as the dot. 350ms
width transition + 250ms colour transition for a smooth update animation.

### Fix 6 — Click cycles views (commit 38534c4)

User feedback: *"when pressing on it it should show the weekly limits."*

In alpha.16.1 the click had been wired to open `claude.ai/settings/usage`
in the browser. In alpha.16.2 the click cycles **Weekly → 5h → Opus 7d
→ Weekly**. The dedicated `↗` button to the right of the cycle area
opens the browser page.

Default starting view is `weekly` (changed from `daily`) because the
Weekly (7-day all-models) limit is the more meaningful number for Max
users — it's heavily dominated by Sonnet usage. Labels clarified:

| Code key | Label | Field | Meaning |
|---|---|---|---|
| `weekly` | `Weekly` | `weeklyPercent` (`seven_day` from API) | 7-day cap on ALL models combined (Sonnet + Haiku + Opus). For most users this is the daily-driver number. |
| `daily`  | `5h`     | `sessionPercent` (`five_hour` from API) | rolling 5-hour window across all models |
| `opus`   | `Opus 7d` | `weeklyOpusPercent` (`seven_day_opus` from API) | 7-day Opus-only sub-limit (Max plans have a separate cap on Opus 4) |

### Fix 7 — Faster auth-error recovery (commit babe7a8)

In `app/src-tauri/src/commands/usage.rs`:

```rust
let ttl = if data.needs_auth { 5 } else { CACHE_TTL_SECS };
```

When the OAuth token is expired, we use a 5-second cache TTL instead
of 30s. This way running `claude /login` in a terminal causes the
gmux badge to refresh within ~5s on the next poll.

Plus in JS: refresh on window-focus + visibilitychange events, throttled
to once per 3s. So alt-tabbing back to gmux after `claude /login` gives
an immediate refresh.

---

## Architecture findings (from the maestro study)

`docs/MAESTRO_USAGE_COMPARISON.md` has the deep dive. Headline:

**gmux's `usage.rs` is byte-identical to maestro's.** Same logic, same
caching, same credential-store + file fallback. Both apps rely on the
user running `claude /login` externally to obtain/refresh tokens —
neither implements an in-app OAuth flow.

The maestro mood thresholds (the 20/40/60/80 % bands) are mirrored in
gmux's dot+bar colour rule. The frontend differences are mostly tech
choice (vanilla JS vs React+Zustand).

---

## What's NOT yet done — known issues for next agent

### Agent Monitor — needs user-verification click

The wiring is unchanged from alpha.14 (which the user said was working).
The `Views ▾ → 🧠 Agent Monitor` button calls the `open_dashboard`
Tauri command which does `set_size(1600x1000) + center() + show()` on
the `dashboard` window. The dashboard JS listens for `gmux-state`
Tauri events.

**Verification step needed:** Click Views → Agent Monitor in the
running app and confirm the dashboard window appears centred at
1600x1000. If it appears but is blank, check DevTools console (right
click → Inspect) for `[data] Tauri webview detected:` and
`[data] Tauri listeners attached. Awaiting first gmux-state…` lines.

The dashboard window currently exists at 10×10 in the corner until
the user clicks. That's expected — the show+resize happens on click.

### In-app OAuth (alpha.17 territory)

User: *"one will require the opencode oauth system for actual
authentication, but the usage bar should follow whatever worked for
maestro right?"*

Yes — the usage bar already does what maestro does. The OAuth-in-app
work is a separate alpha.17+ project. opencode/qalcode's flow:
1. Generate PKCE pair
2. Open browser to `https://claude.ai/oauth/authorize?...`
3. User authorises, sees a code
4. User pastes code back into gmux
5. gmux exchanges code → tokens → writes `~/.claude/.credentials.json`

We have `tauri-plugin-shell` for step 2, need new Rust commands for
steps 1, 4, 5. Plus a modal in the UI for the paste-code step.
Reference: `/home/fivelidz/projects/github_repos/qalcode2/packages/opencode/src/cli/cmd/auth.ts`.

### Sundry small things noticed but not addressed

- Brand badge says `4.0.0-alpha.16.1-dirty` in some shots even after
  tag v4.0.0-alpha.16.2 — this just needs another rebuild after the
  tag and the binary's `GMUX_GIT_TAG` env var will pick up the new tag.
- "backend down — UI on rock" string in the bottom-right status line —
  the monitor IS reachable on :8769, but something else (maybe the
  SSE stream or a different probe) thinks it's down. Diagnose in a
  future session.

---

## Archive map (everything saved, nothing deleted)

```
archive/binaries/
├── gmuxtest-v4.0.0-alpha.7-20260517-2237          ← old, kept for posterity
├── gmuxtest-v4.0.0-alpha.9-…
├── gmuxtest-v4.0.0-alpha.10 / 11 / 12 / 13 / 14   ← previous tags
├── gmuxtest-v4.0.0-alpha.15-20260518-1309         ← the "messy" alpha.15
├── gmuxtest-v4.0.0-alpha.16-dev1 / 2 / 3 / 4 / 5  ← dev iterations today
├── gmuxtest-v4.0.0-alpha.16.1-claudeurl-…         ← intermediate
├── gmuxtest-v4.0.0-alpha.16.1-USAGE-WORKING-…     ← user-confirmed checkpoint
├── gmuxtest-v4.0.0-alpha.16.2-progressbar-…       ← progress bar working
├── gmuxtest-v4.0.0-alpha.16.2-bar-fixed-…         ← ↗ char fixed
├── gmuxtest-v4.0.0-alpha.16.2-labels-…            ← labels updated
└── gmuxtest-v4.0.0-alpha.16.2-…                   ← final tagged binary

archive/snapshots/
├── alpha.7-pre-changes-…tar.gz
├── alpha.15-source-20260518-042716.tar.gz         ← pre-rollback state
├── HANDOVER_alpha15-20260518-042716.md            ← prev handover
└── alpha.16.1-USAGE-WORKING-20260518-054104.tar.gz ← user-confirmed checkpoint

archive/build-artifacts/
└── tauri-643a5dca9b9cf289-dev-stale-…             ← the stale dev fingerprint
                                                     that briefly confused cargo
```

---

## Recommended next session priorities

1. **User-verify Agent Monitor**. Click Views → Agent Monitor. Report
   exact toast text. If window appears blank, check DevTools console.
2. **The "backend down" status indicator** — diagnose why it shows
   despite monitor.py being healthy on :8769.
3. **In-app OAuth flow** (alpha.17). Big feature. See
   `docs/MAESTRO_USAGE_COMPARISON.md` action items + qalcode
   reference.
4. **Nice-to-have**: maestro tamagotchi pixel-art character in the
   bottom sidebar. Pure decoration. See `/tmp/maestro/src/lib/usageParser.ts`.

---

## Key user feedback verbatim (chronological)

1. *"please take us back to alpha 14 as the new changes made a mess of things."*
2. *"It now says Could not connect to localhost: Connection refused"*
3. *"For the chat width I think you should be considering that it should be smaller when it is in a small window."*
4. *"same issue with the sessions tab and options being displayed poorly. … the tabs should be on different levels than running into each other"*
5. *"the claude usage thing still has to be fixed."*
6. *"Actually you taking and reading screenshots can cause big issues where the pixel size is too great. you must ensure that any screenshot you take is made extra smaller"*  → resulted in `/tmp/safe-shot.sh` helper which resizes to 1600px max
7. *"It says token expired for claude which is not correct. Do I have to connect to it through the gmux tauri?"*
8. *"At the end of the day all it need to do is also access this page https://claude.ai/settings/usage from the main browser"*
9. *"one will require the opencode oauth system for actual authentication, but the usage bar should follow whatever worked for maestro right?"*
10. *"document all of this too"*
11. *"Fantastic, great job. That is working. Save this version for continuing. when pressing on it it should show the weekly limits. I'd like it if it displayed it with not just the percentage but a colour changing bar."*
12. *"The bars changing colour should be based on usage percentage as well rather than type of usage."* — confirmed the colour rule is already percentage-based; default view changed to Weekly + label clarified.
13. *"good improvements. It is listing claude design as opus. Instead it should be listing the weekly sonnet %"* — addressed by making `weekly` the default view and clarifying `Opus 7d` is the Opus-only sub-limit.
14. *"In the output it should be shown what the agent is with some
    visual system to show if it is active. Similar to how qalcode has
    moving bars and the explanation to press esc to escape and often
    a description of what it is doing. Or like how claude says stuff
    like 'tinkering'"* / clarification *"I mean it does show activity
    currently in the agent panel but I want to see this in the chat
    panel also"* → alpha.16.5 chat panel activity strip.
15. *"Look I should probably have to come back to test 16.5. For now
    though you have the tokens and the time. Please continue working
    on fixing and checking things."* → autonomous work block in
    which I:
    - diagnosed + fixed the false "backend down" indicator (CDN-import-
      on-every-poll race) → alpha.16.6
    - verified the Agent Monitor wiring is intact (no code change, just
      confirmed open_dashboard + the JS click handler are sound)
    - extended this handover doc

---

*Written across a long session that started with a broken
"Connection refused" white screen and ended with a working coloured
usage bar showing real Anthropic OAuth data + per-pane activity
mirrored into the chat panel. Every change made was discussed first
or driven directly by user feedback. Nothing was deleted; every
binary + source snapshot is in `archive/`.*

---

## Autonomous agent session — alpha.17-dev1 additions (2026-05-19)

The following was added while the user was away.

### alpha.17-dev1 — session restore system

User request: *"It would also be good to have some kind of restore function
for claude code AI. A system where the agent panels can be remembered and
restarted easily if the computer is closed or the panel is closed. this can
work by firing off the /resume commands or something to bring back the
relevant chats."*

Three-layer implementation committed in `a4637ba`:

**Backend** (`backend/session/session_restore.py`):
- `save_session_manifest()` reads `/tmp/gmuxtest-pane-state.json` (written
  every 2s by the monitor) and writes a durable copy to
  `~/.local/share/gmuxtest/session_manifest.json` every 30s.
- Entries keyed by `pane_id` with: `window_name`, `working_dir`, `model`,
  `api_port`, `session_id`, `tmux_session`, `tmux_window`,
  `last_message_preview` (first 200 chars of last assistant message),
  `todo_done`/`todo_total`, `snapshot_ts`, `stale`.
- Stale entries (pane gone from current state) kept 30 days then pruned.
- Verified live: 7-entry manifest created and 1s fresh.

**Rust** (`app/src-tauri/src/lib.rs`):
- `list_saved_sessions()` reads the manifest, returns entries sorted by
  `snapshot_ts` descending (newest first) as a JSON array.
- `restore_session(pane_id)`:
  - Looks up manifest entry for `pane_id`
  - Checks if tmux window still exists via `tmux list-windows`
  - If YES → `tmux select-window` to focus it
  - If NO  → emits `gmux-restore-session` Tauri event with the saved name/dir/
    model so the JS can call `open_agent_v4` and send `/resume`

**UI** (`app/src/index.html`):
- New `♻ Restore` tab added to Options overlay (between Hotkeys and v4 Lab)
- Session cards show: name, working dir, model chip, todo progress,
  last message preview, relative timestamp, live/stale status dot
- Resume button → `restore_session(pane_id)` → toast result
- Handles `gmux-restore-session` events to respawn dead agents + send `/resume`
  after 4s grace period

### Other autonomous work (already committed above)

- **alpha.16.6** — false "backend down" fixed (CDN-import race)
- **Clippy autofix** — 7 idiomatic improvements, zero behaviour change
- **ROADMAP_ALPHA17.md** — SSH/cloud design documented
- **Archive snapshots** tracked in git for rollback safety

### Running now

Binary: `v4.0.0-alpha.17-dev1` (PID ~107706)
Session manifest at: `~/.local/share/gmuxtest/session_manifest.json` (7 entries, live)

### Next session priorities

1. **User to test** alpha.16.5 (chat activity strip) — does verb show, does bar animate, no shake?
2. **User to test** alpha.17-dev1 restore panel — click Options → ♻ Restore, see the 7 session cards, try Resume on one
3. **User to verify** Agent Monitor — click Views → 🧠 Agent Monitor, report toast text
4. **Claude token refresh** — run `claude /login` to refresh the OAuth token so the usage bar shows real data again
5. **alpha.17 polish** — once restore panel is verified, clean up and tag `v4.0.0-alpha.17`
6. **alpha.18 roadmap** — SSH tunnel manager, Remote tab in Settings
