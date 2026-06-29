# Resume note — gmux macOS setup on Ashley's Mac

**Last session:** 2026-06-29. Stopped mid-Tauri-build (user had to go).

## How to reconnect
```bash
ssh ashmac      # alias already in ~/.ssh/config -> ashleychapman-davies@100.92.187.3
```
Passwordless key + passwordless sudo are set up. Tailscale IP 100.92.187.3.

## ✅ DONE (working now)
- Remote access: Tailscale SSH, persistent (sshd + Tailscale login item + nopasswd sudo).
- Cloned repo: `~/projects/gmux_macos` (note: Ashley's own Claude has a 2nd clone at
  `~/projects/claude-coding/gmux_macos` — be aware of both).
- gmux **Phase 1** backend + browser UI verified (`:8769` /health, /api/*).
- **qalcode** terminal AI coder works (bun + ripgrep deps; launcher self-hardened).
  Only needs Ashley to do a one-time interactive Claude login (`qalcode` then sign in).
- **Ghostty** installed + `~/.config/ghostty/config` opens in `~/projects`.
- **Demo-agent bug FIXED** in both `app/src/index.html` and `ui/v3/index.html`
  (commit 95412eb, pushed). Mock seed now clears once a real backend connects.
- Docs written + pushed: `START_HERE_ASHLEY.md` (simple guide, also on his Desktop),
  `docs/VM_REPORTS/macos-install-log.md` (full field report, 10 lessons),
  `FOR_ASHLEYS_CLAUDE.md`, `ACCESS_SETUP.md`.

## ⏳ IN PROGRESS
- **Tauri release build** running in background: log at `/tmp/gmux-tauri-build2.log`
  on the Mac. Was compiling gmux's own crates (portable-pty, axum, reqwest) — i.e.
  nearly done. Check on resume:
  ```bash
  ssh ashmac 'tail -20 /tmp/gmux-tauri-build2.log; ls ~/projects/gmux_macos/app/src-tauri/target/release/bundle/macos/*.app 2>/dev/null'
  ```
  If it finished: the `.app` is under `app/src-tauri/target/release/bundle/macos/`.
  If it died: just re-run `cd ~/projects/gmux_macos/app && npm run tauri build`
  (crates are cached, so it resumes fast). The esbuild platform-lock issue is
  already fixed (node_modules reinstalled on the Mac).

## 📋 TODO (next session)
1. Confirm Tauri `.app` built; launch it and verify the demo-agent fix shows the
   real (empty) state, not demos. Then open an agent pane / PTY terminal works.
2. (Optional) QTK plugin for qalcode — `tooling/qtk/INSTALL_FOR_CLAUDE.md`.
3. Hand to **Ashley's local Claude** (`FOR_ASHLEYS_CLAUDE.md`):
   - Recovery-Mode First Aid to fix the **APFS filesystem corruption**
     (`diskutil verifyVolume /` fails — that's why Homebrew broke).
   - Re-clone/repair Homebrew after FS fix.
   - Finder sidebar/Dock GUI shortcut for `~/projects`.
4. **fivelidz (web console):** disable Tailscale key-expiry for ashleys-macbook-pro;
   revoke the invite link that was shared in chat.

## ⚠️ Known issues
- **APFS corruption** localized to `/usr/local/Homebrew` — not fixed (needs Recovery
  Mode). Does NOT block gmux/qalcode (they don't need brew once node/rust/python/
  psutil present, which they are).
- `gh auth` for account `chappas01` is expired (didn't matter — public repo clone).
