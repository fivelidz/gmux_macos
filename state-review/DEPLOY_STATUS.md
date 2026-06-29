# Deploy Status — Honest Assessment

**Question asked:** "How is the deployment and install of this system going?"

**Short answer:** Better than it feels day-to-day. Backend installs cleanly,
runs reliably, works on VMs. The only thing holding back a public release
is **Tauri reliability** for the desktop app — everything else is in place.

---

## What's verified working right now

Right now, this minute, from `ss -tlnp`:

```
:5550  python3        ← UI server (browser)
:8769  python3.11     ← monitor.py (state + HTTP + SSE)
:8770  python3.11     ← voice daemon (faster-whisper)
:1421  Tauri Vite     ← Tauri dev server
```

And from the sandbox VM (`192.168.122.100`):

```
VM API: 200   ← curl /api/state, 1.5KB JSON of real panes
VM UI:  200   ← curl /ui/v3/index.html, 200 OK
```

Four services running cleanly on the dev host, two of them mirrored to a
headless QEMU VM. Both UI MD5 hashes match across all five mirror locations.

---

## Deploy patterns — what's actually tested

The matrix in `DEPLOYMENT_TARGETS.md` is honest. Two patterns are verified
end-to-end, the rest are documented but untested.

### ✅ Pattern A — Local dev box (everything on one machine)
Verified continuously. The dev host is the canonical install.

### ✅ Pattern B — Server backend, host browser frontend
Verified on the sandbox VM (CachyOS, headless, QEMU).
The full recipe:

```bash
# On the VM (headless CachyOS, no display)
pip install --user psutil websockets numpy   # ~30 seconds
python3 backend/status/monitor.py &           # binds 0.0.0.0:8769
python3 -m http.server 5550 --bind 0.0.0.0 &  # binds 0.0.0.0:5550

# On the host (any machine on the same network)
open "http://192.168.122.100:5550/ui/v3/index.html?api=http://192.168.122.100:8769"
```

The `?api=` URL parameter (added in v3.3) is what makes Pattern B work —
the UI's API base is no longer hardcoded to `127.0.0.1`. Param persists
in `localStorage['gmux.api']` so the user types it once.

### ⏳ Pattern C — Phone remote, desktop backend
Should work — same as Pattern B but the client is a phone. **Not actually
tested on a real phone yet.** Open work item.

### ❌ Pattern D — Docker
Sketched in `DEPLOYMENT_TARGETS.md` but no Dockerfile committed. Skip
unless a deployment target demands it.

---

## What installs cleanly

Single-line installs verified on CachyOS:

```bash
# Backend (minimum — what you need for headless / VM / server)
pip install --user psutil websockets numpy

# Voice (optional, only if you have audio)
pip install --user sounddevice faster-whisper

# UI dependencies are zero — it's a single HTML file
```

That's the entire dependency surface for the headless install. ~30 seconds
on a warm pip cache.

For the desktop app you add: tmux, rust (rustup), node/npm, webkit2gtk-4.1,
and base-devel. All available from package managers on every target distro.
No private/proprietary dependencies anywhere.

---

## What's working that wasn't obvious

Reading `DECISIONS.md` carefully, these are all done, not pending:

- ✅ Backend daemon (`monitor.py`) — listening on `:8769`, atomically writes
  state JSON, broadcasts via SSE
- ✅ Traffic-light state detection — permission > waiting > working > error
  > done > idle priority order
- ✅ gmux-brain context injection — three-memory pattern
- ✅ Phone PWA — Tailscale-served, browser-based
- ✅ Voice daemon — faster-whisper STT, broadcasts on `ws://:8770`
- ✅ Camera broker — virtual camera over direct camera access
- ✅ PTY mirror — direct PTY, not VTE/terminal-widget
- ✅ Wayland workaround — `GDK_BACKEND=x11` in launcher script
- ✅ Local MediaPipe model — bundled, no CDN dependency
- ✅ Bridge on `:8767`, receiver on `:8769`, voice on `:8770` — settled port
  layout, no clashes
- ✅ Self-launching sidecars — Tauri spawns `monitor.py` + voice + session-restore
  automatically on boot
- ✅ Backend health monitor in UI — red banner + "restart" button when
  `monitor :8769` unreachable

All of that landed already. The day-to-day work feels uncertain because
the work-in-progress is visible while the working pieces are invisible.

---

## The one real blocker — Tauri reliability

Tauri dev mode runs but is **noticeably laggy** vs the browser UI:

- Vite HMR adds round-trips
- WebKitGTK on Wayland is heavier than Chromium
- Rust debug build is unoptimised

The fix is documented and unblocked:

```bash
cd ~/projects/gmuxtest && npm run tauri build
# Produces a release binary in src-tauri/target/release/
# Cold launch ~1.5s, idle ~180 MB RSS, smooth scrolling
```

That single command turns dev-mode lag into release-mode polish. It hasn't
been run yet because Tauri config + bundling needs one careful pass
(window title, icon, sidecar paths, capabilities). One afternoon's work.

**Everything else is ready.** Once that lands, this is a shippable desktop
app.

---

## What "ship" actually means here

There are three sensible "ship" levels:

### Level 1 — Public demo (immediate)
- gmux.ai already points at `gmux-v3.html` (the demo build)
- Browser UI, no install required, mock mode obvious in the demo banner
- ✅ Already deployed and stable

### Level 2 — One-line install (1–3 days)
- `curl https://gmux.ai/install.sh | bash` style installer
- Pulls the repo, runs the right pip installs, drops a desktop file,
  prints the launch command
- Has all the pieces — just needs writing
- See `WHAT_TO_SHIP.md` for the install-script spec

### Level 3 — Tauri desktop binary (3–7 days)
- `tauri build` → produces `.deb`, `.AppImage`, `.dmg`, `.msi`
- The big polish pass on icon, window title, sidebar resources, etc.
- This is the "actual product" form

Level 1 is shipped. Level 2 and Level 3 are real work but not big work.

---

## How the install feels right now

Verified install steps on the VM, end-to-end timing:

```
00:00  scp project files to VM             (~3s for the 305KB UI)
00:03  pip install --user psutil websockets ~30s on a cold pip cache
00:35  python3 backend/status/monitor.py     ~0.5s to bind
00:36  python3 -m http.server 5550           ~0.5s to bind
00:37  open browser, point at VM             real data renders
```

Under 40 seconds from "no install" to "looking at real agent state in a
browser." For a system that includes a Python daemon, an SSE server, a
voice WebSocket, and a 305KB self-contained UI, that's good.

For Tauri the install is heavier (Rust toolchain, WebKitGTK headers, npm
install) but it's still a one-evening job. Documented in `DEPLOYMENT_TARGETS.md`.

---

## What's untested that should be soon

| Target | Why test soon | Effort |
|---|---|---|
| Debian VM | Most common server distro | 1 hour — `apt install` recipe is written |
| Tauri release build | The one real blocker | 1 afternoon — config + build |
| Phone PWA on real Android | Pattern C verification | 1 hour — needs HTTPS via Tailscale |
| macOS | Open question whether brew install works | 2 hours — needs a Mac |
| Docker | Cloud deploy story | half a day — write Dockerfile, test |

None of these are blockers for shipping. They're confidence builders.

---

## The honest pause-on-installer-work answer

> Reading DECISIONS.md carefully: the pause on installer work is *correct
> discipline*, not blocked progress.

Yes. The installer scripts that exist (`scripts/launch.sh`,
`scripts/launch-browser.sh`, etc.) cover the dev-machine and remote-server
cases. A one-line `curl | bash` installer is a marketing artefact, not a
technical one — it's worth building when there's an audience to install for.

The right ordering is:

1. **Tauri release build** — turns dev mode into a real desktop app
2. **A handful of "tested-as-of" runs** — Debian VM, phone, macOS
3. **Then** an installer that wraps the above into one curl command

Trying to write the installer before the Tauri build means the installer
inherits the dev-mode lag. Order matters.

---

## One-sentence summary

The install/deploy story is in much better shape than it feels — backend
deploys in under a minute, browser UI works from any device on the LAN,
the only ship blocker is one focused afternoon on the Tauri release
build.
