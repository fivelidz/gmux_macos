# gmux on macOS — Real Install Log & Field Report

**Target machine:** Ashley's MacBook Pro
**Date:** 2026-06-29
**Driven remotely** from `superlocal` (Linux) over Tailscale SSH.
**Author:** Claude (remote agent)

> This is a *real* install transcript — what actually happened installing gmux on
> fresh Mac hardware for the first time, including the surprises. It is meant to
> become the authoritative "how to install gmux on macOS" reference, alongside
> `MACOS_AGENT_SETUP.md` (the plan) and `MACOS_PORTING.md` (the code patches).

---

## 0. Machine baseline (what we started with)

| Item | Value | Notes |
|---|---|---|
| macOS | 12.7.6 Monterey | older than dev target, worth noting |
| CPU | **Intel x86_64** | NOT Apple Silicon — affects brew prefix (`/usr/local` not `/opt/homebrew`) and Tauri target |
| Disk free | 367 GB | plenty |
| Xcode CLT | installed (`/Library/Developer/CommandLineTools`) | required for Rust/cargo native builds |
| git | 2.37.1 (Apple) | fine |
| node | v22.19.0 | fine (repo wants 18+) |
| npm | 10.9.3 | fine |
| cargo/rustc | **1.96.0 already installed** | user had rustup already |
| python3 | **3.14.5** (Homebrew) | repo *prefers* 3.11; 3.14 works because backend is stdlib + psutil |
| psutil | **7.2.2 already installed** | the one real Python dep — already satisfied |
| pip | 26.1.1 | fine |
| Homebrew | **installed but BROKEN** | see §2 — turned out to be filesystem corruption |

**Lesson #1:** A "developer" Mac often already has node, rust, python, psutil. The
gmux prerequisite list (`brew install python@3.11 node git` + rustup) can be
*mostly already satisfied*. Always **survey first**, install only the gaps.

**Lesson #2:** gmux's runtime deps are lighter than the guide implies. For
Phase 1 (backend + browser UI) you only strictly need: **Python 3.x + psutil**.
Node/Rust are only for Phase 2 (the Tauri app). Homebrew is only needed to
*acquire* python/node if they're missing — if they're already present, a broken
Homebrew does **not** block the gmux build.

---

## 1. Remote access setup (Tailscale + SSH)

For driving the install from another machine (recommended for support):

- Mac joined the operator's tailnet via the **standalone** Tailscale.app
  (NOT the Mac App Store build — the App Store build can't do `tailscale ssh`).
- The `tailscale` **CLI is not on PATH** by default with the GUI app. Symlink it:
  ```bash
  sudo ln -sf /Applications/Tailscale.app/Contents/MacOS/Tailscale /usr/local/bin/tailscale
  ```
- **SSH itself must be enabled separately** — Tailscale being "connected" only
  means the network is up. Enable macOS Remote Login:
  *System Settings → General → Sharing → Remote Login = ON*
  (this starts `sshd` via the system LaunchDaemon `/System/Library/LaunchDaemons/ssh.plist`,
  which persists across reboots).
- Passwordless key auth: append the operator's ed25519 pubkey to
  `~/.ssh/authorized_keys` (chmod 700 ~/.ssh, chmod 600 the file).
- For unattended admin: a scoped `/etc/sudoers.d/` NOPASSWD entry.
- **Make Tailscale auto-start:** add `Tailscale.app` as a (hidden) login item so
  the tunnel rejoins the tailnet after reboot.
- **Disable node key expiry** in the Tailscale admin console so access doesn't
  lapse in ~180 days (web-console only, can't be done from CLI).

**Lesson #3:** "Tailscale shows connected" ≠ "you can SSH in". sshd is a separate
toggle. And the App-Store Tailscale silently lacks `tailscale ssh`.

---

## 2. The big surprise: APFS filesystem corruption

Homebrew was installed but every `brew` command errored:
```
/usr/local/Homebrew/Library/Homebrew/brew.sh: line 624:
  /usr/local/Homebrew/Library/Homebrew/cmd/--version.sh: No such file or directory
homebrew-version: command not found
```

`git status` in `/usr/local/Homebrew` showed **26 files deleted** from the working
tree. But `git checkout -- .` / `git reset --hard` could **not** recreate them:
```
error: unable to create file Library/Homebrew/cask/dsl/container.rb: No such file or directory
```// …even though the parent directory `cask/dsl/` clearly exists and is writable.

Even a plain `touch Library/Homebrew/cask/dsl/container.rb` failed with
"No such file or directory" — while `touch .anyothername` in the *same dir*
**succeeded**. That signature (a specific set of filenames that cannot be
created, in an otherwise-writable directory) is **APFS catalog/B-tree corruption**:
orphaned directory entries for those exact names.

Confirmed with:
```bash
sudo diskutil verifyVolume /
# error: cib: ci_free_count (32751) is not valid (16390) ...
# error: sm: sm_free_count (96093510) is not valid (96019628)
# Space Verification failed — File system check exit code is 8
```

**Crucially, the corruption is LOCALIZED.** File creation works fine in `~/projects`,
`/tmp`, `~/.cargo`, including deep nested trees. Only the specific damaged
Homebrew directory entries are affected. So the gmux build can proceed; only
Homebrew itself needs repair.

**The repair requires Recovery Mode** — the live boot volume can't be unmounted
while running (`diskutil verifyVolume` fails with "dissented by PID 0 / kernel_task").
First Aid / `fsck_apfs -y` must run from macOS Recovery (⌘+R at boot).

**Lesson #4:** A "broken Homebrew" on macOS can actually be a symptom of
filesystem corruption, not a brew problem. If `git checkout`/`touch` fail to
create *specific* filenames in a writable dir, run `diskutil verifyVolume /` —
and if it fails, the real fix is Recovery-Mode First Aid, not reinstalling brew.

**Lesson #5:** Don't fight FS corruption from a live session. Diagnose, document,
and hand the Recovery-Mode repair to someone with physical access. Meanwhile,
build everything that lives on the *healthy* part of the disk.

---

## 3. Install steps that worked (build path, no brew needed)

### Clone (into the projects folder)
```bash
cd ~/projects
git clone https://github.com/fivelidz/gmux_macos.git
```
Note: the repo is **public**, so `gh auth` is not required (Ashley's `gh` login
was expired anyway — `git clone` over HTTPS worked regardless).

### Phase 1 — backend + browser UI  ✅ GREEN
```bash
cd ~/projects/gmux_macos
chmod +x scripts/*.sh
./scripts/launch-v4.sh --browser
```
Result on macOS 12.7.6:
- Monitor bound **:8769** (uses `lsof` fallback on Darwin — Patch 7 works).
- Voice auto-skipped (faster-whisper/sounddevice not installed) — expected.
- Static UI served at `http://localhost:5550/ui/v3/index.html` (HTTP 200).

Verified endpoints (all correct for an idle machine):
```
curl http://localhost:8769/health      -> ok
curl http://localhost:8769/api/state    -> {}        (no agents running yet)
curl http://localhost:8769/api/files    -> {}
curl http://localhost:8769/api/activity -> []
curl http://localhost:8769/api/memory   -> {schema 1.0, empty stores}
```
**Checkpoint 1 PASSED with zero code changes** — the Linux→mac guards already in
place (`MACOS_PORTING.md`) carried Phase 1 cleanly. Empty `{}` state is *correct*,
not a bug (the Agent Monitor only populates when an AI agent is actively touching
files in the last hour).

**Lesson #6:** On a dev Mac with psutil already present, Phase 1 is essentially
"clone + run". No brew, no pip step needed if psutil is already installed.

### Phase 2 — Tauri desktop app
```bash
cd ~/projects/gmux_macos/app
npm install          # succeeded (2 npm-audit warnings, non-blocking)
npm run tauri build  # vite build -> cargo release build (slow, many crates)
```
- rustc host confirmed **x86_64-apple-darwin** (Intel) — correct target present.
- Build kicked off: vite frontend build first, then the long cargo compile.
- (Result recorded in §4 once the compile finishes.)

<!-- §4 build outcome appended after compile -->

