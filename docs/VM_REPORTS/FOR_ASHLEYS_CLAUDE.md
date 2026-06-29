# Handoff to Ashley's local Claude — fixes that need on-machine / GUI / Recovery access

**Context:** A remote Claude (running on fivelidz's Linux box, `superlocal`) is
SSH'd into this Mac over Tailscale and has set up gmux. Most of the software install
is done remotely. **A few tasks need YOU (the local Claude on Ashley's Mac)** because
they require the GUI, a logged-in Finder session, or Recovery Mode — none of which
work over a headless SSH session.

Please do the tasks below, in order. Each has a verify step. Tell Ashley before
the Recovery-Mode reboot (it interrupts his session).

---

## ⚠️ TASK 1 (IMPORTANT) — Repair the filesystem corruption

### Why
`diskutil verifyVolume /` reports APFS allocation/catalog corruption:
```
error: cib: ci_free_count ... is not valid ...
error: sm: sm_free_count ... is not valid ...
Space Verification failed — File system check exit code is 8
```
This is why Homebrew broke: 26 files in `/usr/local/Homebrew/...` cannot be
recreated (orphaned directory entries). It is **localized** — the rest of the disk
is healthy — but it should be repaired, and it **cannot be fixed while booted**
(the boot volume can't be unmounted live).

### What's at risk
Low, but **back up first** if anything on this Mac is important — there are
personal/legal documents in the home folder. Time Machine or copy critical files
off before repairing.

### How to fix (needs a reboot — tell Ashley)
1. **Apple menu → Restart.** As it powers back on, **hold ⌘ + R** until you see
   the Recovery screen (Apple logo / spinning globe, then macOS Utilities).
2. In **macOS Utilities** → open **Disk Utility**.
3. View → **Show All Devices**. Select the **container/volume** (e.g. `Macintosh HD`
   — pick the data volume, and also run on the container `disk1`).
4. Click **First Aid** → **Run**. Let it complete (may take several minutes).
   - If Disk Utility can't fix it, use **Utilities → Terminal** in Recovery and run:
     ```bash
     diskutil list                      # find the APFS data volume, e.g. disk1s5
     fsck_apfs -y /dev/disk1s5          # repair (use the right identifier)
     ```
5. **Reboot normally.**
6. **Verify** (back in normal macOS, Terminal):
   ```bash
   sudo diskutil verifyVolume /         # should now say "appears to be OK"
   ```

---

## TASK 2 — Finish repairing Homebrew (after Task 1)

Once the filesystem is clean, the broken Homebrew tree can be restored.

Try the gentle repair first:
```bash
cd /usr/local/Homebrew
git checkout -- .          # should now succeed (the 26 missing files restore)
brew --version             # should print a version cleanly
```

If `git checkout` still errors, do a clean re-clone of the Homebrew core
(your installed packages in `/usr/local/Cellar` are NOT touched):
```bash
# Move the corrupt tree aside (do NOT delete — archive it)
sudo mv /usr/local/Homebrew /usr/local/Homebrew.broken.$(date +%Y%m%d)
# Re-clone Homebrew core
sudo mkdir -p /usr/local/Homebrew
sudo chown -R "$(whoami):admin" /usr/local/Homebrew
git clone https://github.com/Homebrew/brew /usr/local/Homebrew
# Relink the brew binary
sudo ln -sf /usr/local/Homebrew/bin/brew /usr/local/bin/brew
brew --version
brew doctor                # follow any remaining advice
brew update
```

**Verify:** `brew --version` prints cleanly and `brew doctor` is happy.

> Note: gmux itself does NOT need Homebrew once node/rust/python/psutil are present
> (they already are). Fix brew mainly for Ashley's general use and for the Ghostty
> cask in Task 4.

---

## TASK 3 — Make the `~/projects` folder easy to find in Finder (GUI)

The folder **exists** at `/Users/ashleychapman-davies/projects` and is full of real
projects (it was hard to find only because it's buried among many loose files in the
home directory, and the filesystem is case-insensitive so `projects`/`Projects`/
`PROJECTS` are the same folder). A terminal alias (`proj`, `projects`) is already in
`~/.zshrc`. Please also add the **GUI shortcuts** (these need a logged-in Finder, so
they couldn't be done over SSH):

1. **Add to Finder sidebar Favorites:**
   - Open Finder → press **⌘⇧H** (Home) → drag the **projects** folder into the
     left sidebar under "Favorites".
   - Or in Terminal: `open ~` then drag, or install `mysides`:
     `brew install mysides && mysides add projects "file://$HOME/projects/"`
2. **Add to the Dock:** drag the `projects` folder to the right side of the Dock
   (next to Trash) to make a stack.
3. **Desktop alias (optional):** in Finder, right-click `projects` →
   **Make Alias**, drag the alias to the Desktop.

**Verify:** `projects` appears in the Finder sidebar and opens to the project list.

---

## TASK 4 — (Optional) Ghostty terminal

After brew is fixed:
```bash
brew install --cask ghostty
```
Then set its default working directory to `~/projects` (Ghostty config
`~/.config/ghostty/config`):
```
working-directory = /Users/ashleychapman-davies/projects
```
Follow `tooling/ghostty/INSTALL_FOR_CLAUDE.md` in the repo for details.

---

## TASK 5 — (Optional) Re-auth GitHub for Ashley's account

`gh auth status` shows account `chappas01` is **failed/expired**. gmux didn't need
it (public repo), but if Ashley wants to push:
```bash
gh auth login        # follow the browser/device flow
```

> **Note on the operator's access:** changing Ashley's GitHub account does NOT
> affect the remote Tailscale/SSH access fivelidz set up — they're independent.

---

## What the remote Claude already did (so you don't redo it)
- ✅ Tailscale CLI symlinked to `/usr/local/bin/tailscale`
- ✅ Remote Login (sshd) enabled + persistent; operator's SSH key authorized
- ✅ Tailscale added as a hidden login item (auto-starts on boot)
- ✅ Passwordless sudo for `ashleychapman-davies` (`/etc/sudoers.d/gmux-admin`)
- ✅ `~/.zshrc` has `proj` / `projects` aliases
- ✅ Cloned `gmux_macos` → `~/projects/gmux_macos`
- ✅ gmux **Phase 1 (backend + browser UI) verified working** on this Mac
- ⏳ gmux **Phase 2 (Tauri .app build)** — building; result in `macos-install-log.md`

## One thing only fivelidz can do (web console)
- Disable Tailscale **key expiry** for this machine at
  https://login.tailscale.com/admin/machines → ashleys-macbook-pro → ⋯ →
  Disable key expiry. (And revoke any invite link that was shared.)
