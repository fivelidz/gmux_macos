# Rollback: alpha.15 → alpha.14

**Date:** 2026-05-18  ~14:30 AEST
**Reason (user):** *"the new changes made a mess of things"* — alpha.15
broke things that worked in alpha.14:

1. **Agent Monitor was working in alpha.14** (user only asked the previous
   agent to add a workshop folder to iterate on it — instead, alpha.15
   broke the working link).
2. **Chat panel proportion is still wrong** in alpha.15 (the 28%-of-window
   rule didn't behave the way the user wanted on windowed mode).
3. **Topbar tabs run into each other** in windowed mode — should fall to a
   second row when there isn't space, not collide.
4. **Usage bar is missing** entirely in alpha.15 (was at least placeholdered
   in alpha.14).
5. **Maestro colour rule** (high usage = green, low = red) was attempted in
   alpha.15 but rolled into the same broken commit.

## What this rollback did

| Action | Detail |
| --- | --- |
| Archived alpha.15 source | `archive/snapshots/alpha.15-source-20260518-042716.tar.gz` (8.0 MB) |
| Archived alpha.15 HANDOVER doc | `archive/snapshots/HANDOVER_alpha15-20260518-042716.md` |
| Kept alpha.15 binary | `archive/binaries/gmuxtest-v4.0.0-alpha.15-20260518-1309` |
| Restored alpha.14 binary | `app/src-tauri/target/release/gmuxtest` (md5 `1d68433…`) |
| Reverted source commit | `5d990ce` (alpha.15 UI changes — `app/src/index.html` + `ui/v3/index.html`) |
| KEPT in repo | `docs/HANDOVER_alpha15.md` (separate commit `e0b1e51`) — useful notes |
| Stopped old process | killed PIDs 2994491 (gmuxtest), 2985691 (monitor), 2994533 (saver) |
| Launched alpha.14 | new PID 3114803, monitor :8769 (`/health` → `ok`), saver running |

## Git state after rollback

```
5b78cc2 Revert "v4.0.0-alpha.15: …"        ← HEAD (working tree = alpha.14 source)
e0b1e51 docs: HANDOVER_alpha15.md           ← kept on purpose (useful notes)
5d990ce v4.0.0-alpha.15: …                  ← reverted
8a04d7e v4.0.0-alpha.14: …                  ← the target we want
```

To go back to alpha.15 if ever needed:

```bash
# Source:
git revert 5b78cc2                                           # un-revert
# Binary:
cp archive/binaries/gmuxtest-v4.0.0-alpha.15-20260518-1309 \
   app/src-tauri/target/release/gmuxtest
```

## Working tree right now

- Source: byte-identical to `v4.0.0-alpha.14` (`git diff v4.0.0-alpha.14` returns nothing for the two reverted files)
- Binary: `app/src-tauri/target/release/gmuxtest` = alpha.14 (md5 `1d684333c050997dc39f62791dd2913b`)
- The brand badge in the running app should now read `4.0.0-alpha.14`
- Two extra files vs the alpha.14 tag commit:
  - `docs/HANDOVER_alpha15.md` (intentional — kept for notes)
  - `docs/ROLLBACK_alpha15_to_alpha14.md` (this file)

## Agenda forward (alpha.16 — careful, incremental)

We do NOT redo the whole alpha.15 commit. Instead each fix is its own
small commit so we can isolate regressions.

### Priorities
1. **Agent Monitor — DON'T BREAK IT.** First verify it works in alpha.14.
   The previous agent's mistake was rewriting the wiring instead of just
   adding a parallel workshop folder. The workshop folder is `agent-monitor/`
   — that is the playground; the live wiring is in `app/src/dashboard/`
   and `app/src-tauri/src/lib.rs::open_dashboard`. Don't touch the live
   wiring while iterating on the workshop.

2. **Chat panel proportion.** Rule should be:
   - If the *current window* is narrow (≤ ~1500 px), chat ≈ 360 px.
   - If the window is genuinely wide (≥ 2400 px on a real ultrawide),
     chat can be up to ~520 px.
   - Never let chat exceed ~30 % of the window's *current* width.
   - The previous formula used `screen.width` (the monitor) instead of
     `window.innerWidth`. That's the bug: on a 3440-px monitor it picked
     480 px even when the gmux window was only 1400 px wide.

3. **Topbar in windowed mode.** User wants:
   > "on windowed mode the tabs should be on different levels than
   > running into each other"

   So when `flex-wrap: nowrap` overflows (sessions can't fit on the same
   row as brand+options), allow it to wrap. The alpha.15 attempt locked
   it to one row and hid buttons — user does not want hidden buttons.
   Use `flex-wrap: wrap` with a `min-width` on the session-tabs group.

4. **Usage bar.** Make it always visible (placeholder when no data),
   colours per maestro: low = red, high = green. Position bottom-left
   of the agent panel.

5. **Element-label overlay (Ctrl+Shift+L).** This is from alpha.14 and
   the user liked it — preserve it.

### Files to touch (and only these unless absolutely needed)
- `app/src/index.html` — CSS + inline JS for topbar/chat/usage rules
- `app/src/dashboard/js/*.js` — for Agent Monitor iteration *(use the
  workshop folder `agent-monitor/` first)*
- NO Rust changes for UI tweaks — keep `app/src-tauri/src/` stable

### Testing protocol
After every change:
1. `bash ./scripts/launch-v4.sh --test` → must stay 13/13 green
2. `cargo build --release --manifest-path app/src-tauri/Cargo.toml` →
   must stay zero warnings
3. Kill old binary, launch new, click brand badge → confirm timestamp
   moved
4. Visually verify the SPECIFIC thing the change targets

### What NOT to do
- Don't rewrite `open_dashboard` in lib.rs — alpha.14 has it working.
- Don't change the Rust commands while doing CSS/JS work.
- Don't change more than one feature per commit.
- Don't `rm` any archive file or binary — copy first, write second.
