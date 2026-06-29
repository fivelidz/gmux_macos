# gmux-system — Version Control Guide

**Last updated:** 2026-05-12 (v3.2)
**Authoritative copy:** `/home/fivelidz/projects/gmux-system/`
**Remote:** [github.com/fivelidz/gmux-system](https://github.com/fivelidz/gmux-system) (private)

This document is the single source of truth for "where does the latest code
live and how do I keep things in sync".

---

## TL;DR — where is the latest code?

| What you want | Where it lives |
|---|---|
| **Latest of EVERYTHING** | `~/projects/gmux-system/` (this repo) |
| Run the system | `cd ~/projects/gmux-system && ./scripts/launch.sh` |
| Browser-only UI | `./scripts/launch.sh --browser` → http://localhost:5550/v2/index.html |
| Tauri desktop app | `cd ~/projects/gmuxtest && GDK_BACKEND=x11 npm run tauri dev` |
| Edit the UI | edit `~/projects/gmuxtest/UI_creation_independent/v2/index.html` then sync |
| Edit Rust backend | edit `~/projects/gmuxtest/src-tauri/src/lib.rs` then sync |
| Edit Python backend | edit `~/projects/gmux-system/backend/status/monitor.py` directly |

---

## The three-repo architecture (why it's like this)

```
~/projects/gmuxtest/                              ← dev sandbox (Tauri lives here)
├── src-tauri/src/lib.rs                          ← Rust backend, edited here first
├── src/index.html                                ← what Tauri serves (auto-synced)
└── UI_creation_independent/                      ← git submodule pointing to:
    └── v2/index.html                             ← UI canonical source, edit here

~/projects/gmuxtest/UI_creation_independent/      ← github.com/fivelidz/gmux-ui-demo
                                                    Public-friendly UI-only repo

~/projects/gmux-system/                           ← github.com/fivelidz/gmux-system (PRIVATE)
├── ui/v3/index.html                              ← mirror of UI source
├── app/src-tauri/src/lib.rs                      ← mirror of Rust source
├── backend/status/monitor.py                     ← Python backend (canonical here)
├── backend/voice/gmux_voice_daemon.py            ← faster-whisper STT
├── HANDOVER.md / NEXT_ACTIONS.md / etc.          ← project docs
└── extras/                                       ← archived features (e.g. avatar_system/)
```

**Why three:**
1. `gmuxtest` started as the Tauri dev sandbox. Has commit history of all
   Tauri experiments — keeping it separate keeps the consolidated repo clean.
2. `gmux-ui-demo` is a submodule because it's also useful as a standalone
   UI-only repo (it powered gmux.ai's public demo at one point).
3. `gmux-system` is the **CANONICAL CONSOLIDATED REPO**. When in doubt, look here.

---

## Sync flow — what to edit where

### When you edit the UI (`v2/index.html`)

1. Edit `~/projects/gmuxtest/UI_creation_independent/v2/index.html`
2. Sync (one command):
   ```bash
   SRC=~/projects/gmuxtest/UI_creation_independent/v2/index.html
   cp "$SRC" ~/projects/gmuxtest/src/index.html
   cp "$SRC" ~/projects/gmux-system/ui/v3/index.html
   cp "$SRC" ~/projects/gmuxtest/UI_creation_independent/releases/gmux-v3.0.html
   cp "$SRC" ~/projects/gmux-system/ui/releases/gmux-v3.0.html
   ```
3. Rebuild the demo variant (title swap + banner forced on):
   ```bash
   python3 -c "
   SRC='/home/fivelidz/projects/gmuxtest/UI_creation_independent/v2/index.html'
   html = open(SRC).read()
   demo = html.replace('<title>gmux v3.0</title>','<title>gmux · demo</title>',1)
   demo = demo.replace(\"if (new URLSearchParams(window.location.search).has('demo')) {\",
                       \"if (true || new URLSearchParams(window.location.search).has('demo')) {\",1)
   for o in [
     '/home/fivelidz/projects/gmuxtest/UI_creation_independent/gmux-v3.html',
     '/home/fivelidz/projects/gmuxtest/UI_creation_independent/releases/gmux-v3.0-demo.html',
     '/home/fivelidz/projects/gmux-system/ui/releases/gmux-v3.0-demo.html',
   ]: open(o,'w').write(demo)
   "
   ```
4. Verify all files have the same MD5:
   ```bash
   md5sum ~/projects/gmuxtest/UI_creation_independent/v2/index.html \
          ~/projects/gmuxtest/src/index.html \
          ~/projects/gmux-system/ui/v3/index.html | awk '{print substr($1,1,12)}'
   ```
   All three should print the same hash.

### When you edit the Rust (`lib.rs`)

1. Edit `~/projects/gmuxtest/src-tauri/src/lib.rs`
2. Sync: `cp ~/projects/gmuxtest/src-tauri/src/lib.rs ~/projects/gmux-system/app/src-tauri/src/lib.rs`
3. Verify it compiles: `cd ~/projects/gmuxtest && cargo check --manifest-path src-tauri/Cargo.toml`

### When you edit the Python backend (`monitor.py`)

1. Edit `~/projects/gmux-system/backend/status/monitor.py` (canonical)
2. Sync: `cp ~/projects/gmux-system/backend/status/monitor.py ~/projects/gmuxtest/src-py/status/monitor.py`
3. Test: `pkill -f "monitor.py"; sleep 1; python3.11 ~/projects/gmux-system/backend/status/monitor.py &` then `curl http://127.0.0.1:8769/api/state`

---

## Git commits — what goes where

Every meaningful change must be committed to **all three repos**:

```bash
# 1. gmuxtest (Rust + UI submodule + sync)
cd ~/projects/gmuxtest
git add -A
git commit -m "feat: <one-line summary>"
git push origin main

# 2. gmux-ui-demo (UI submodule, public)
cd ~/projects/gmuxtest/UI_creation_independent
git add v2/index.html releases/ gmux-v3.html
git commit -m "feat: <one-line summary>"
git push origin main

# 3. gmux-system (CONSOLIDATED — the canonical repo)
cd ~/projects/gmux-system
git add -A
git commit -m "feat: <one-line summary>"
git push origin main
```

**Always push in this order.** The submodule in `gmuxtest` needs to be
committed/pushed first so its reference is stable.

---

## Latest commits (2026-05-12)

| Repo | Commit | Note |
|---|---|---|
| `gmux-system` | `ac56589` | Avatar toggle + responsive design + next-actions log |
| `gmuxtest` | `683ddd0` | Tauri+UI mirror |
| `gmux-ui-demo` | `0a9cabc` | UI public mirror |

Use `git log --oneline -10` in each repo to see history. The commit titles
should match between repos for the same logical change.

---

## Version naming

| Version | What changed |
|---|---|
| v2.4 | Original gesture UI baseline (May 2026 first build) |
| v3.0 | Real backend wiring: state JSON, OpenCode SSE, voice STT |
| v3.1 | psutil metrics, OpenCode token aggregator, real todos in JSON |
| v3.2 | Avatar removed (archived), markdown chat, visible scrollbars, fullscreen redesign, HW tab fix |

The version number lives in the `<!-- gmux v3.x → -->` HTML comment at the
top of `v2/index.html` and the `<title>` tag.

---

## Branches

We use **only `main`** on all three repos. No long-lived branches. Reasons:
- The code is moving fast and merge conflicts in a 7000-line HTML file are unpleasant
- Each repo has a clear single-direction sync (UI source → all mirrors)
- Reverts via `git revert` are easy if something breaks

If you do start a feature branch, keep it under a week.

---

## v3.5+ — Tags + named milestones

Now that gmux-system is the consolidated single repo and the older
gmuxtest/gmux UI directories are reference-only, we shift to tagging
milestones explicitly so we can roll back without code-archaeology.

### Tagging convention

```bash
# After a passing test run, tag the commit:
cd ~/projects/gmux-system
git tag -a v3.5.0 -m "v3.5: Agent Monitor + activity feed + Views dropdown"
git tag -a v3.5.1 -m "v3.5.1: macOS deployment doc + provider auth plan"
```

Tag format: `vMAJOR.MINOR.PATCH`
- MAJOR — never bumped without explicit user approval (would mean a
  breaking API/UI change like rewriting the dashboard)
- MINOR — new feature surface (new toolbar button, new producer file, new
  Tauri command). Bumped when the user agrees the feature is "done enough".
- PATCH — bug fixes, doc updates, dep bumps.

### Pre-tag checklist
Before tagging anything:
1. `python3.11 backend/status/test_monitor_producers.py` passes
2. `git status` clean
3. `git log --oneline -5` makes sense
4. The `archive/ui/` snapshot for the version exists (latest snapshot
   matches `ui/v3/index.html`)
5. `docs/PROMPT_HISTORY.md` has the session entry for what changed

### What gets tagged automatically vs manually
- Manually: every "user says save this version" moment
- Automatically: nothing yet. Future GitHub Actions could tag every
  green-CI commit, but premature for now.

### Snapshot policy (the archive/ folder)
- Every time the user says "save this version" we **both**:
  - Tag the git commit (`git tag v3.X.Y`)
  - Drop a frozen HTML copy in `archive/ui/index.v3.X-<short-name>-<date>.html`
- The archive/ folder is in git — it's a recoverable record even if the
  remote vanishes.
- Snapshots are described in `archive/MANIFEST.md`.

### Rolling back
```bash
# View tags
git tag -l 'v3.*' --sort=-version:refname | head

# Roll the working tree to a tag (keeps history clean)
git checkout v3.5.0
# … inspect …
# Either return to main:
git checkout main
# Or branch off the tag to fix forward:
git checkout -b hotfix/v3.5.1 v3.5.0
```

### What we never do
- `git push --force` to main (rewrites history; breaks collaborators)
- Squash-merge commits that contain doc updates we want to preserve
  (PROMPT_HISTORY entries are part of the record)
- Delete tags
- Delete `archive/` contents

### Two-machine sync (host ↔ VM)
- The VM is **never** a git remote. It's a deploy target.
- Code only flows host → VM via rsync.
- VM-AI reports flow VM → host via rsync of `docs/VM_REPORTS/` only
  (see `docs/VM_AGENT_COORDINATION.md`).
- If we ever need git on the VM (e.g. to test cloning during install), the
  VM clones from the public GitHub URL, not from the host.

---

## Where to ask "what version am I running?"

Inside the UI: open Options panel (gear icon top-right) → version number is
in the title `gmux v3.x`. The status bar at the bottom-right shows:

- `● tauri live` — running in Tauri AND connected to monitor
- `● live :8769` — running in browser AND connected to monitor HTTP
- `● live (poll)` — connected via HTTP polling (SSE failed)
- `● mock` — no backend reachable, fake data

Hover the indicator for a tooltip showing data source + agent count + session count.

Inside Tauri logs: `tail /tmp/gmux-monitor.log /tmp/gmux-voice.log` shows the
running daemon versions.
