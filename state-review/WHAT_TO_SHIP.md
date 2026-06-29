# What to Ship — Stop-Iterating-Ship-the-Thing List

The single biggest move you're underrating: **stitching what you have**.
This document separates ship-now from ship-after, and growth from blocker.

---

## The "ready to ship" claim, defended

Reading `DECISIONS.md` end to end:

| Capability | Status |
|---|---|
| Backend daemon | ✅ Done |
| Traffic-light state detection | ✅ Done |
| gmux-brain context injection | ✅ Done |
| Phone PWA | ✅ Done |
| Voice daemon | ✅ Done |
| Camera broker | ✅ Done |
| PTY mirror | ✅ Done |
| Sidecar auto-spawn | ✅ Done |
| Backend health monitor + restart | ✅ Done |
| Live data from real agents | ✅ Done |
| Markdown chat rendering | ✅ Done |
| Theme system + user themes | ✅ Done |
| Self-launching Tauri | ✅ Done in dev mode |
| Tauri **release** build | ⬜ **One blocker** |

Thirteen of fourteen capabilities are green. The one remaining is one
afternoon's work.

---

## Three ship levels

### Level 1 — Public demo (already live)

`https://gmux.ai/demo` shows the v3.x UI in mock mode. The demo banner is
visible so it doesn't pretend to be live. Browser-only, no install, works
on every modern browser including phone.

**Status:** ✅ Shipped, just needs the v3.4 build pushed up.

### Level 2 — One-line install (3 days)

```bash
curl -fsSL https://gmux.ai/install.sh | bash
```

Drops:
- `~/projects/gmux-system/` (git clone)
- Python deps (pip install)
- Desktop file (`~/.local/share/applications/gmux.desktop`)
- A systemd user service for the monitor (optional, prompted)

Prints the launch command. That's the install.

**Spec for `install.sh` — to be built:**

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Sanity checks
command -v git    >/dev/null || { echo "Install git first"; exit 1; }
command -v python3.11 >/dev/null || command -v python3 >/dev/null || { echo "Install Python 3.10+ first"; exit 1; }

# 2. Clone
mkdir -p ~/projects
test -d ~/projects/gmux-system || git clone https://github.com/fivelidz/gmux-system.git ~/projects/gmux-system

# 3. Python deps
python3 -m pip install --user --upgrade psutil websockets numpy
# Optional voice
read -p "Install voice (faster-whisper, sounddevice)? [y/N]: " ans
[ "$ans" = "y" ] && python3 -m pip install --user --upgrade faster-whisper sounddevice

# 4. Desktop file
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/gmux.desktop <<EOF
[Desktop Entry]
Name=gmux
Exec=$HOME/projects/gmux-system/scripts/launch.sh --browser
Icon=$HOME/projects/gmux-system/app/src-tauri/icons/icon.png
Type=Application
Categories=Development;
EOF

echo "✓ Installed. Launch with: ~/projects/gmux-system/scripts/launch.sh --browser"
```

That's ~30 lines. The work isn't the install script — it's testing it on
three distros.

**Status:** ⬜ 3 days from "decide to do it" to "shipped"

### Level 3 — Tauri desktop binary (5–7 days)

The one real blocker. Steps:

1. `cd ~/projects/gmuxtest/src-tauri && cargo update` — keep deps fresh
2. Set window title, icon, productName in `tauri.conf.json`
3. Pin sidecar paths to `$RESOURCE_DIR` (Tauri-relative) not `$HOME`
4. `npm run tauri build` — produces `.deb`, `.AppImage`, `.dmg`, `.msi`
5. Sanity-check launches on at least CachyOS + Debian VM
6. Upload binaries to a release page (gmux.ai/releases or GitHub releases)

**Status:** ⬜ 5–7 days, but **most of that is testing, not building**.
Build itself is `cargo build --release`.

---

## Blockers vs growth features — be honest

### Genuinely blocks shipping

- Tauri release build (the one above)
- Nothing else

### Genuinely doesn't block shipping (despite feeling like it does)

- Multi-camera gesture support — growth feature, single camera works fine
- Scheduled prompts — growth feature, manual prompts work fine
- Tool history tab — growth feature, the live last-line shows what's happening
- DeerFlow integration — growth feature, gmux supervises agents adequately without a planner
- HALO self-improvement — growth feature
- Memory panel full implementation — growth feature, the "coming soon" stub
  is honest and reusable
- Agent-quality scoring — growth feature
- Phone PWA HTTPS — only blocks the **phone** path, doesn't block desktop ship

### Doesn't block shipping, but worth doing before a wider audience

- Public install script (Level 2 above)
- One verified install on Debian
- One verified install on macOS
- Tauri release on a non-dev machine
- HANDOVER for "if you're new to the codebase, start here"
  *(already exists at `gmux-system/HANDOVER.md` — good)*

---

## The 7-day ship plan

If you decided right now to ship to a wider audience in a week:

### Day 1 — Tauri release build pass
- Update `tauri.conf.json` for production (title, icon, productName, bundle ids)
- Move sidecar discovery from `$HOME` paths to `tauri::path::resource_dir()`
- `npm run tauri build`
- Smoke-test the binary on dev box

### Day 2 — Debian VM verification
- Spin up Debian VM via QEMU
- Run install recipe end-to-end
- Document any pacman→apt differences in `DEPLOYMENT_TARGETS.md`
- Test Tauri binary on the Debian VM

### Day 3 — Write the install script
- `install.sh` per the spec above
- Test on CachyOS + Debian VM
- Host at `gmux.ai/install.sh`

### Day 4 — Phone PWA
- Set up Tailscale serve or self-signed cert
- Test on real Android device
- Update phone-pwa section of `DEPLOYMENT_TARGETS.md`

### Day 5 — Demo polish
- Update gmux.ai with the new v3.x build
- Record a 90-second demo video showing:
  - Gesture-approval of an agent permission prompt
  - Voice → markdown chat reply with code block
  - Theme switching with live preview
- Commit video to the repo, link from README

### Day 6 — Write LAUNCH.md
- Single doc that links: install command, demo URL, video, GitHub repo
- Make this the answer to "how do I try gmux?"

### Day 7 — Launch
- Post on Hacker News / Twitter / wherever
- Watch for issues in `monitor.py` / Tauri binary
- Hotfix as needed

That's a realistic timeline. None of it requires new architecture.

---

## What NOT to ship in v1

Resist the urge to ship these until v1 has settled:

- Memory panel full implementation (it's a stub for a reason)
- DeerFlow long-horizon harness (composition work, not bundled)
- HALO self-improvement (post-launch experiment)
- Multi-camera gesture
- Scheduled prompts
- ATLAS-style agent weighting

Every one of these is a real feature. None of them are v1 blockers.

---

## The composition argument

The pattern across the research batch and your own stack is that **the
biggest wins from now on come from composition, not new builds**:

- `gmux ↔ DeerFlow`: gmux supervises, DeerFlow plans long-horizon
- `Knowledge_systems ↔ DeerFlow`: DeerFlow's MCP tools call `knowledge_query`
- `mempalace ↔ jcode`: borrow the side-agent-verifies-relevance pattern
- `claude_TUI ↔ DeerFlow`: borrow the multi-transport IM-channel pattern
- `mempalace ↔ kalarc-memory ↔ Knowledge_systems`: a unified
  "what we know / what was said / what's true" tri-store

Most of those are doc + glue work, not new architecture. **Schedule them
into v1.1 and v1.2, not v1.**

---

## Stop-iterating-ship-the-thing — the one-line version

The Tauri release build is the only true blocker.
Everything else is either done, or growth.
