# Handover — alpha.17-dev2 GOLD → alpha.17-dev3 (quick wins)

**Date saved:** 2026-05-19 ~14:05 AEST
**Gold version:** `v4.0.0-alpha.17-dev2` (commit `b63c1e8`)
**Gold binary:** `archive/binaries/gmuxtest-v4.0.0-alpha.17-dev2-GOLD`
**Gold snapshot:** `archive/snapshots/alpha.17-dev2-GOLD.tar.gz`
**Tests:** 13/13 headless green (per the dev1 handover; not extended in dev2)

## User feedback on alpha.17-dev2 (verbatim)

> *"This is working brilliantly. Very happy with this. for now we can
> have this as the gold standard."*

✅ All five alpha.17-dev2 issues resolved:
1. Sidebar inline ✓/✗ for permission state (compact, same row, with tooltip)
2. Pagination — sliding-window cycle (1-6 → 2-7 → wrap) so every page is full
3. Topbar single row on widescreen (≥1700px)
4. Restore tab opens correctly + label not clipped
5. Token expired auto-refresh implemented (qalcode2-style)
6. Bonus: anti-flicker via `_setHTML` memo + skip pane reorder when order unchanged

---

## Read these in order

1. **`docs/ROADMAP_ALPHA18.md`** — the full plan: 3 quick UI wins +
   5 major epics with file pointers, line numbers, acceptance
   criteria, and recommended sequencing. **Start here.**
2. **`CLAUDE.md` in user home** — image-size + `rm -rf` rules.
   Critical, do not skip.
3. This file — quick context, hotspots, working pattern.

---

## Recommended next session (alpha.17-dev3 — three quick UI wins)

All three are documented in detail in `ROADMAP_ALPHA18.md` Section 1.
They're tightly scoped (½ day total), all share `app/src/index.html`,
and they unblock a much nicer demo:

1. **Close-agent button** (replaces the rarely-used fullscreen button).
   Alt-hold + click to prevent accidents. Add same to sidebar rows.
   Wire `close_agent` Tauri command. ~1–2 hours.

2. **Alt+←/→ session switching.** Slot already reserved in main
   keydown handler. ~30 minutes.

3. **Star indicator in sidebar + "⭐ Starred" pseudo-session.** The
   `toggleFavoriteAgent` infrastructure already exists; just need
   a visible star button and a filter mode. ~1 hour.

Tag `v4.0.0-alpha.17-dev3` after all three pass visual inspection.

---

## After dev3 — pick ONE of these (each is a full session)

In priority order per `ROADMAP_ALPHA18.md`:

| Order | Tag | Scope | Effort |
| ----- | --- | ----- | ------ |
| 1 | alpha.18 | Agents spawn sub-agents (CLI shim approach) | 1–2 days |
| 2 | alpha.19 | Agent Monitor v2 (fix wrong-window bug) | 2–3 days |
| 3 | alpha.20 | Voice features end-to-end + port fix | 1–2 days |
| 4 | alpha.21 | Phone app bridge (biggest — bridge.py + QR + tailscale + ssh) | 3–5 days |
| 5 | alpha.22 | v4 PTY substrate completion (remove env-var gate) | 2–3 days |

The roadmap doc has acceptance criteria for each. **Do not bundle.**
Each epic should yield 1 tag at the end.

---

## Quick state pointers

### How to relaunch the gold binary
```bash
cd ~/projects/gmux_v4
pkill -KILL -f release/gmuxtest 2>/dev/null
pkill -KILL -x gmuxtest 2>/dev/null
sleep 2
python3 -c "
import os, sys
pid = os.fork()
if pid > 0: sys.exit(0)
os.setsid()
pid = os.fork()
if pid > 0: sys.exit(0)
os.environ['GMUX_V4_PTY']='1'
os.environ['DISPLAY']=':0'
os.environ['GDK_BACKEND']='x11'
sys.stdin = open('/dev/null')
sys.stdout = open('/tmp/gmux-v4.log','w')
sys.stderr = sys.stdout
os.execvp('./app/src-tauri/target/release/gmuxtest', ['gmuxtest'])
" &
```

Note: previously the handover used `systemd-run --user --scope` —
that auto-cleaned the scope when the parent shell exited. The
double-fork above is more reliable inside agent tool calls. Either
works when launched from a real terminal.

### Key file locations (unchanged from dev1)

| What | Path |
| --- | --- |
| Main UI source | `app/src/index.html` (~10780 lines) |
| Tauri Rust commands | `app/src-tauri/src/lib.rs` |
| Claude usage Rust impl | `app/src-tauri/src/commands/usage.rs` |
| PTY commands | `app/src-tauri/src/commands/terminal.rs` |
| Backend monitor | `backend/status/monitor.py` |
| Session-restore daemon | `backend/session/session_restore.py` |
| Voice daemon | `backend/voice/gmux_voice_daemon.py` |
| Voice bridge (v3) | `backend/voice/bridge.py` ⚠ port mismatch (:8765 vs daemon :8770) |
| Capabilities config | `app/src-tauri/capabilities/default.json` |
| Tauri config | `app/src-tauri/tauri.conf.json` |
| Agent monitor workshop | `agent-monitor/src/dashboard/` |
| Agent monitor spec | `agent-monitor/spec/AGENT_MONITOR_SPEC.md` |
| Phone app (separate repo) | `~/projects/gmux-phone/` v0.7.1 |
| Bridge design (spec only) | `docs/BRIDGE_DESIGN.md` |

### Git state

```
b63c1e8  fix(ui): alpha.17-dev2 v3 — sliding-window pagination + deeper anti-flicker
08771d9  fix(ui): alpha.17-dev2 v2 — regressions from first dev2 build
040d0b8  fix(usage): use 'expired' wording when refresh fails so UI shows /login hint
16d328a  feat(usage): auto-refresh expired Claude OAuth token (qalcode2-style)
fcb8c19  feat(ui): alpha.17-dev2 — inline approve/reject buttons in sidebar (#1)
7efbece  fix(ui): alpha.17-dev2 — three small UI fixes
d57f224  docs: HANDOVER_NEXT.md — 5 bugs to fix for alpha.17-dev2
a4637ba  feat(restore): alpha.17-dev1 — session restore system
```

### Things that are easy to break

1. **`tauri = { features = ["custom-protocol"] }`** in `Cargo.toml`
   is required for release builds. Without it the binary tries to load
   from the dev URL.
2. **`cargo clean`** blows away the dev-fingerprint cache. Touch
   `src/lib.rs` to force a rebuild if needed.
3. **Vite must rebuild `dist/` when `index.html` changes.** `npm run
   build` from `app/` does it; `cargo`'s `beforeBuildCommand` runs
   it on fresh cargo builds, but if cargo decides nothing changed
   it skips vite too. Touch `src/lib.rs` to force.
4. **xdotool clicks don't always register** on the Tauri webview on
   KDE/X11 — testing UI behaviour usually needs human eyeballs.
5. **Don't `rm -rf` anything** — copy to archive first per CLAUDE.md.
   The user has lost approved work to "cleanup" deletes in past
   projects.
6. **Per-tick innerHTML writes cause visible flicker.** Use the new
   `_setHTML(el, html)` helper (defined just before `renderSidebar`).
   It uses `dataset.gmuxLastHtml` to skip identical re-renders.

---

## How the alpha.17-dev2 cycle went (for context)

The user reported 5 bugs after dev1. Initial dev2 attempt fixed 4
quickly but introduced 2 regressions:

- **Regression 1:** balanced pagination (4+3) was wrong — user
  preferred full pages + orphan. **Fix:** sliding-window cycle.
- **Regression 2:** pane grid flicker. Root cause was a stray
  `grid.appendChild()` loop running every SSE tick (10 Hz),
  re-appending every pane DOM node to its parent each frame. This
  was pre-existing (since alpha.7) but more visible after dev2 made
  permission rows heavier. **Fix:** only reorder DOM when the
  desired pane_id order actually differs from current DOM order.

Took 3 commits to land dev2 cleanly. Pattern: each round saved a
checkpoint binary + source snapshot BEFORE the next change. When
user feedback flagged the regression, rollback would have been one
`cp` away. Always do this.

---

## What we explicitly did NOT do (intentional)

- **In-app OAuth login flow** — postponed. `claude /login` from
  terminal still required to seed the refresh-token chain.
- **Phone bridge / Tailscale / SSH** — all postponed to alpha.21.
- **Agent Monitor wiring** — postponed to alpha.19.
- **v4 PTY env-var → runtime toggle** — postponed to alpha.22.

---

## Closing note

The user has settled into a comfortable working rhythm:
1. Get a feature working roughly
2. Iterate on small UX issues (1–3 per round)
3. Tag when satisfied
4. Move on

Don't over-engineer. Don't bundle. Don't keep adding features when
something has regressed. Listen to the verbatim feedback and act on
it before moving on.

The roadmap in `ROADMAP_ALPHA18.md` is the authoritative plan from
here. Start with the three quick UI wins (Section 1) — they're small,
visible, and the user explicitly asked for them.
