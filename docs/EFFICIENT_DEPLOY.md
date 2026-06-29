# Efficient Deploy — backend on a new machine in one command

Goal: from the host, get the gmux-system backend running on any new
target machine with zero per-machine configuration. The target machine
only needs SSH access and a working `bash`. Everything else installs
itself.

This is **not** a full Tauri deploy — that requires Rust + WebKitGTK +
display server (see `INSTALL_GUIDE.md` for the full path). This is the
**minimum useful backend** so you can point a host browser at the target
and see live data.

## TL;DR — one command from anywhere

```bash
ssh <target> 'bash <(curl -fsSL https://raw.githubusercontent.com/fivelidz/gmux-system/main/scripts/install-vm.sh)'
```

Replace `<target>` with the hostname/IP. The script:
1. Detects pacman/apt/dnf and installs system packages
2. Installs Python deps (psutil, websockets, requests)
3. Installs `bun` and `opencode-ai`
4. Clones (or pulls) `gmux-system` to `~/projects/gmux-system`
5. Creates the `gmux` tmux session
6. Starts `monitor.py` with `setsid` so it survives SSH disconnect
7. Starts `http.server :5550 --bind 0.0.0.0` so the UI is reachable
8. Prints sanity-check output + the URLs to open

Approx total time on a fresh CachyOS VM: **90 seconds**.

## Two deploy modes

### Mode A — host has the latest local code, target needs to mirror it

Use this when you've made local changes that aren't yet pushed to GitHub.

```bash
# One-shot deploy from host's working tree:
~/projects/gmux-system/scripts/deploy.sh sandbox
```

The `deploy.sh` script (new, this version) wraps:
1. rsync host's working tree → target's `~/projects/gmux-system/`
   (excludes .git, node_modules, target/, models/, VM_REPORTS)
2. Runs `install-vm.sh` on the target (which sees the repo already
   exists and skips the git clone, just updates deps + starts services)

### Mode B — target installs from public GitHub

Use this for any computer that just needs gmux-system running.

```bash
# On the target machine:
curl -fsSL https://raw.githubusercontent.com/fivelidz/gmux-system/main/scripts/install-vm.sh | bash
```

Or, equivalently, from the host:
```bash
ssh <target> 'curl -fsSL https://raw.githubusercontent.com/fivelidz/gmux-system/main/scripts/install-vm.sh | bash'
```

The script will:
- `git clone --depth 1` the repo into `~/projects/gmux-system`
- Install all deps
- Start monitor + UI server

## What "no extra install needed" means

The `install-vm.sh` script handles every system-level prerequisite.
After it runs, the target machine has:

| Component | Status after install |
|---|---|
| `tmux`, `git`, `python3.11`, `curl`, `rsync` | installed via system pkg manager |
| `psutil`, `websockets`, `requests` | installed via pip --user |
| `bun` at `~/.bun/bin/bun` | downloaded via the official installer |
| `opencode` at `~/.bun/bin/opencode` | installed via `bun install -g opencode-ai` |
| `gmux-system` repo at `~/projects/gmux-system` | cloned / updated |
| tmux session `gmux` | created if missing |
| `monitor.py` running on `:8769` | yes (setsid so SSH-safe) |
| UI HTTP server on `:5550` | yes (bound to 0.0.0.0) |
| `~/.local/share/opencode/auth.json` | NOT created — user must run `opencode auth login <provider>` once |

The auth step is the only manual remainder. We can't pre-bake credentials
into the deploy script — every machine needs its own OAuth.

## What the target machine does NOT need pre-installed

- ❌ No Rust / cargo (no Tauri build on the target)
- ❌ No Node.js / npm
- ❌ No WebKitGTK / GTK / X11 display server
- ❌ No display at all
- ❌ No camera/audio/gesture deps

You can deploy to a barebones Debian server with `apt install -y openssh-server`
and the install script handles the rest.

## How it stays "efficient"

| Optimisation | Saves |
|---|---|
| `--depth 1` on git clone | ~95% of `.git` size |
| Idempotent system-pkg install | re-runs are no-ops if already installed |
| `--needed` flag on pacman, similar logic on apt/dnf | skips already-installed pkgs |
| Skips `opencode-ai` install if binary already present | saves 5s reinstall |
| Skips voice/gesture deps entirely | saves ~500 MB of pip downloads |
| `setsid` not `nohup` | works correctly on systemd VMs |
| Single round-trip from host | one `ssh + bash` call |

## Updating an existing install

Re-run the same install command. It detects the existing repo and:
1. `git pull --ff-only` to update source
2. Re-installs only deps that have changed (pacman/apt are idempotent)
3. Kills the old monitor.py and starts the new one

Or from host with local changes:
```bash
~/projects/gmux-system/scripts/deploy.sh <target>
```

## Removing

```bash
ssh <target> '
  pkill -f gmux-system/backend
  pkill -f gmux-system/app
  tmux kill-session -t gmux 2>/dev/null
  rm -rf ~/projects/gmux-system
  rm -f /tmp/gmuxtest-*.json /tmp/gmux-*.log
'
```

`~/.bun/bin/opencode` is left in place since other things might use it.

## Verifying it worked

After deploy, from your host:
```bash
TARGET=<target-ip>
curl --max-time 3 http://$TARGET:8769/health           # → ok
curl --max-time 3 http://$TARGET:8769/api/state | jq . | head -20
curl -o /dev/null -w '%{http_code}' http://$TARGET:5550/ui/v3/index.html  # → 200
```

Open `http://$TARGET:5550/ui/v3/index.html` in your browser.

To point the UI at the **target's** API (rather than your host's):
```javascript
// in browser devtools console:
window.GMUX_API = `http://${location.hostname}:8769`;
location.reload();
```

(v3.7 plan: support `?api=http://host:port/` URL param so users don't
need devtools.)

## Where this still has rough edges

- **Auth.** Each target machine needs `opencode auth login <provider>`
  run once. Can't be deployed. v3.6.0's Provider panel UI helps if you
  have a display on the target.
- **Public GitHub repo.** Currently the repo IS public; if it becomes
  private, the curl-pipe pattern breaks for new installs. Workaround:
  rsync from host (Mode A), or deploy a deploy key to the target.
- **No service unit / autostart.** `setsid` keeps the process alive
  across SSH disconnect but a reboot kills it. Future: `scripts/install-systemd-user-units.sh`
  to install user-mode systemd units for monitor + http.server.

## Where to read next

- `INSTALL_GUIDE.md` — full install with Tauri desktop app
- `DEPLOYMENT_TARGETS.md` — what works on each platform
- `docs/VM_PROTOCOL.md` — the manual deploy procedure we used before
  this script existed
- `docs/VM_REPORTS/2026-05-13-install-run-summary.md` — actual VM run
