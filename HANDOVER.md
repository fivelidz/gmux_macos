# gmux-system — Agent Handover Document

**Last updated:** 2026-05-13  
**Branch:** `main` — HEAD commit `4f27c7c`  
**Maintainer:** fivelidz  
**Status:** Active development — Tauri app compiling and launching, UI rendering under investigation

---

## ⚡ QUICK RECOVERY (read this first)

```bash
# Start everything on the HOST machine
cd ~/projects/gmux-system
./scripts/launch.sh              # Tauri + monitor + voice + session-saver

# Browser-only (no Tauri)
./scripts/launch.sh --browser    # monitor + voice + http.server :5550

# Check what's running
ss -tlnp | grep -E "8769|8770|1421|5550"
cat /tmp/gmux-monitor.log
cat /tmp/gmux-tauri.log | grep -vE "Building|Compiling" | tail -30

# If Tauri starts but renders blank / GStreamer spam in log:
export GST_DEBUG="*:0"
export GST_PLUGIN_FEATURE_RANK="v4l2src:NONE"
export GDK_BACKEND=x11
export WEBKIT_DISABLE_COMPOSITING_MODE=1
cd app && npm run tauri dev
```

---

## 📁 REPOSITORY STRUCTURE

```
gmux-system/
├── app/                        ← Tauri desktop app (Rust + WebKit2GTK)
│   ├── src/
│   │   ├── index.html          ← v3 UI (real copy, NOT a symlink — vite needs this)
│   │   └── aquarium.html       ← secondary Tauri window
│   ├── src-tauri/
│   │   ├── src/lib.rs          ← ALL Tauri commands (845 lines), sidecar launcher
│   │   ├── Cargo.toml          ← tauri 2.10.3, portable-pty, serde
│   │   └── tauri.conf.json     ← window config (1400×900), CSP null
│   ├── public/aquarium.html    ← source for aquarium (copy into src/ before build)
│   ├── vite.config.js          ← root:'src', port:1421, strict
│   └── package.json            ← @tauri-apps/api 2.11.0 (minor mismatch w/ Rust 2.10.3 — harmless)
│
├── backend/
│   ├── status/
│   │   ├── monitor.py          ← HTTP :8769 — THE core daemon (1558 lines)
│   │   ├── pane_status.py      ← CLI snapshot tool
│   │   └── jump_red.py         ← tmux status-bar jump helper
│   ├── session/
│   │   └── session_restore.py  ← saves/restores tmux window names
│   ├── voice/
│   │   ├── gmux_voice_daemon.py← faster-whisper WS :8770 (requires sounddevice)
│   │   └── bridge.py           ← voice-to-tmux bridge
│   ├── gesture/                ← EMPTY dir — gesture code lives in ui/gesture-*.js
│   └── gmux.py                 ← full gmux orchestrator (821 lines) — start/attach/restore
│
├── ui/
│   ├── v3/index.html           ← THE UI — 7400 lines, single-file standalone (v3.3)
│   ├── gesture-engine.js       ← MediaPipe hand-tracking engine
│   ├── gesture-renderer.js     ← hand overlay canvas renderer
│   ├── mock-data.js            ← mock pane data for pure-demo mode
│   ├── archive/                ← v3.1 snapshot (2026-05-11)
│   └── releases/               ← v3.0 and v3.0-demo frozen builds
│
├── scripts/
│   ├── launch.sh               ← MASTER launcher — use this
│   ├── launch-browser.sh       ← browser-only shortcut
│   ├── launch-gmux.sh          ← gmux session launch (calls gmux.py)
│   └── launch-voice.sh         ← voice daemon only
│
├── docs/
│   ├── VM_DEPLOYMENT_LOG.md    ← full VM deploy log (session 1 + 2 addendum)
│   ├── VM_PROTOCOL.md          ← standard VM deploy-and-test protocol
│   ├── INTEGRATION.md          ← layer map + OpenCode API reference
│   ├── NEXT_ACTIONS.md         ← TODO list (update as you work)
│   ├── LIVE_DATA_STATUS.md     ← root cause + fix for live data bugs
│   └── SELF_LAUNCH_TEST.md     ← E2E cold-start test results
│
├── archive/
│   ├── MANIFEST.md             ← what's in each snapshot + working matrix
│   ├── ui/                     ← HTML snapshots (in git)
│   ├── backend/                ← backend tarballs (.tar.gz, gitignored)
│   ├── app/                    ← Tauri state tarballs (.tar.gz, gitignored)
│   └── logs/                   ← build/runtime logs (.log, gitignored)
│
├── state-review/               ← Honest project state review (2026-05-12)
│   ├── STATE_OF_THE_STACK.md
│   ├── WHAT_TO_SHIP.md
│   ├── COMPOSITION_GAPS.md
│   ├── DEPLOY_STATUS.md
│   └── MARKETING_LINES.md
│
├── extras/avatar_system/       ← archived avatar UI component
├── models/hand_landmarker.task ← MediaPipe hand model (7.8MB, gitignored)
│
├── HANDOVER.md                 ← THIS FILE
├── DECISIONS.md                ← architectural decisions log
├── DEPENDENCIES.md             ← exhaustive runtime dep map
├── DEPLOYMENT_TARGETS.md       ← which features work where
├── BACKEND_CONNECTION.md       ← connection modes + full JSON schema
├── TESTING_CHECKLIST.md        ← pre-flight test checklist
├── TESTING_GUIDE.md            ← how to run tests efficiently
└── VERSION_CONTROL.md          ← git commit conventions + sync flow
```

---

## ✅ WHAT HAS BEEN IMPLEMENTED

### Core Backend — FULLY WORKING
| Component | Status | Notes |
|-----------|--------|-------|
| `monitor.py` HTTP server | ✅ Verified | Port 8769, binds 0.0.0.0, CORS `*` |
| `/health` endpoint | ✅ Verified | Returns `ok` |
| `/api/state` endpoint | ✅ Verified | Full 27-field pane JSON |
| `/api/stream` SSE | ✅ Verified | Real-time push on pane changes |
| `/api/pane/<id>/todos` | ✅ Verified | Proxies OpenCode todo list |
| `/api/pane/<id>/messages` | ✅ Verified | Proxies chat history |
| tmux pane polling | ✅ Verified | 2s cycle, all panes tracked |
| SSE listener threads | ✅ Verified | Per-pane, reconnects on drop |
| psutil metrics | ✅ Verified | RAM/CPU/uptime/children populated |
| Token/cost aggregation | ✅ Verified | 10s cycle, pulls OpenCode messages |
| Window name cache | ✅ Verified | Persists across monitor restarts |
| Session restore daemon | ✅ Verified | Saves/restores tmux window names |
| Voice daemon (local) | ✅ Verified | faster-whisper ws://localhost:8770 |
| Sidecar auto-launch | ✅ Verified | Tauri starts all 3 daemons, port-checks first |

### UI (v3.3) — WORKING IN BROWSER
| Feature | Status | Notes |
|---------|--------|-------|
| Live pane grid | ✅ | Fetches /api/state every 2s |
| SSE real-time updates | ✅ | Subscribes to /api/stream |
| Session tabs | ✅ | Derived from real tmux sessions |
| Window tabs per session | ✅ | Real window names from monitor |
| Pane state indicators | ✅ | working/waiting/idle/permission/error |
| Todo panel | ✅ | From /api/pane/:id/todos |
| Chat panel | ✅ | From /api/pane/:id/messages |
| Chat ✕ context-aware | ✅ v3.3 | Exits fullscreen only when fullscreen |
| Hardware metrics strip | ✅ | RAM/CPU/uptime via psutil |
| Token/cost display | ✅ | Real from OpenCode aggregation |
| Tool history ribbon | ✅ | Last 30 tools, populated from SSE |
| Approve/Reject buttons | ✅ | Calls Tauri command or HTTP fallback |
| Send prompt | ✅ | Calls Tauri send_to_agent or HTTP |
| Voice strip | ✅ | Web Speech API + faster-whisper WS |
| Gesture engine | ✅ | MediaPipe hand tracking (needs camera) |
| Theme system | ✅ v3.3 | CSS variable overrides, presets, user themes |
| Fullscreen pane view | ✅ | Pane grid fullscreen mode |
| Chat fullscreen | ✅ | Chat panel fullscreen + side todos panel |
| Sparklines | ✅ | Per-pane token rate + CPU graphs |
| YOLO mode selector | ✅ | UI cosmetic, no backend enforcement yet |
| Agent presets / new agent modal | ✅ | Type selection, name input |
| Drag-to-reorder panes | ✅ | Drag handle on pane cards |
| `window.GMUX_API` override | ✅ | For remote-browser → VM scenarios |

### Tauri App — PARTIAL
| Feature | Status | Notes |
|---------|--------|-------|
| `cargo build` success | ✅ | Tauri 2.10.3, 493 crates, 1m20s first / 0.5s incremental |
| Window opens | ✅ | 1400×900 main window |
| WebKit subprocess | ✅ | WebKitWebProcess spawns |
| Sidecar auto-launch | ✅ | monitor + voice + session-restore |
| PTY attach to tmux | ✅ | Auto-detects `gmux` session |
| All Tauri Rust commands compile | ✅ | 15+ commands |
| WebView renders UI | ⚠️ | GStreamer assertions caused jank; env var workaround applied |
| Live data in WebView | ❓ | Not confirmed — user closed before verified |
| Approve/Reject end-to-end | ❓ | Not tested |
| Chat send end-to-end | ❓ | Not tested |
| Global shortcuts | ❓ | Alt+G / Ctrl+Shift+Space / Ctrl+Alt+D defined, not tested |
| Aquarium window | ❓ | Not tested |

### VM Deployment — VERIFIED
| Feature | Status | Notes |
|---------|--------|-------|
| rsync deploy | ✅ | < 1s, 51 files |
| monitor.py on VM | ✅ | :8769 accessible from host |
| UI server on VM | ✅ | :5550 accessible from host |
| API from host machine | ✅ | `curl 192.168.122.100:8769/health` → `ok` |
| Ghostty on VM | ❌ | LLVM AVX2 JIT crash (QEMU virtio GPU) |
| Tauri on VM | ❌ | No cargo, no display |
| Voice on VM | ❌ | No audio device |
| opencode on VM | ❌ | Not on npm registry |

---

## 🔬 WHAT NEEDS TO BE TESTED

### P0 — Do first
1. **Tauri WebView renders correctly** — does v3 UI appear after GST env vars? Agent grid visible?
2. **Agent titles / content missing** — some panes show `bun`/`fish` instead of real window name
3. **Live data in Tauri** — does `/api/state` load, or is it stuck on mocks?

### P1 — This week
4. Approve/Reject flow end-to-end in Tauri
5. Chat send prompt in Tauri
6. Voice dictation (WS :8770, transcription pipeline)
7. Gesture tracking (camera, MediaPipe, click/scroll)
8. Global keyboard shortcuts
9. Session tab switching
10. Window rename persistence
11. Chat fullscreen side-todos panel (1400px+ viewport)

### P2 — Before release
12. Theme persistence across reload
13. Multi-session tracking
14. Sub-agent permission indicator
15. Token rate sparklines accuracy
16. SSE reconnect (kill/restart monitor, UI recovers)
17. YOLO mode — is it wired to anything or purely cosmetic?
18. Aquarium window
19. `npm run tauri build` → installable bundle
20. VM browser live data via `window.GMUX_API`

---

## 🗺️ FUTURE PLANS

### Near term (next 1–3 sessions)
- [ ] Fix GStreamer permanently in launch.sh (add env vars there)
- [ ] Sync hook: auto-copy `ui/v3/index.html` → `app/src/index.html` on save
- [ ] Fix agent title fallback: show `session:window[pane]` when generic name detected
- [ ] Add `?api=<url>` URL param support in the UI (5 lines of JS, documented gap)
- [ ] Wire YOLO mode to Tauri command or agent env var

### Medium term
- [ ] `npm run tauri build` — AppImage/deb for easy install
- [ ] opencode auto-install in launch.sh
- [ ] Installer script (`install.sh`) with systemd user service for monitor
- [ ] Mobile PWA — thin client using `/api/state` + `/api/stream`
- [ ] Memory panel data feed (`docs/MEMORY_INTEGRATION.md`)

### Long term / aspirational
- [ ] Gesture approval — pinch-to-approve permission requests
- [ ] Voice approval — "yes/approve" voice command
- [ ] Fleet view — multiple gmux-system backends, aggregate dashboard
- [ ] Tmux layout control — gmux sends split/move/focus commands from UI
- [ ] Cost budget enforcement — pause agent when `cost_usd` threshold hit

---

## 🐛 KNOWN BUGS

| Bug | Severity | Workaround |
|-----|----------|-----------|
| Tauri WebView GStreamer crash | High | `GST_DEBUG=*:0 GST_PLUGIN_FEATURE_RANK=v4l2src:NONE` before launch |
| Agent titles show generic names | Medium | Wait 10s for name cache to warm; or pre-populate via tmux rename-window |
| `app/src/index.html` drifts from `ui/v3/index.html` | Medium | `cp ui/v3/index.html app/src/index.html` after any UI edit |
| `@tauri-apps/api` version mismatch (2.11 vs 2.10) | Low | Cosmetic warning — no runtime impact |
| `window.GMUX_API` not settable from URL param | Low | Browser console: `window.GMUX_API='http://...'; location.reload()` |

---

## 🏗️ ARCHITECTURE (quick reference)

```
HOST MACHINE
┌─────────────────────────────────────────────────────────────┐
│  Tauri app (target/debug/gmuxtest)                          │
│  ├── WebKit2GTK WebView ← loads http://localhost:1421/      │
│  │    └── ui/v3/index.html (7400 lines, single-file)       │
│  │         ├── fetch() → monitor.py :8769 /api/state       │
│  │         ├── EventSource → /api/stream (SSE)             │
│  │         └── window.__TAURI_INTERNALS__ → Rust commands  │
│  └── Rust sidecars (auto-spawned at startup):               │
│       ├── monitor.py       :8769  (tmux + OpenCode poller) │
│       ├── voice daemon     :8770  (faster-whisper WS)      │
│       └── session_restore  (tmux name cache daemon)        │
│                                                             │
│  tmux session 'gmux'  (PTY attached by lib.rs)             │
│  ├── [win 0] opencode agent A  → bun pid → port X         │
│  ├── [win 1] opencode agent B  → bun pid → port Y         │
│  └── ...                                                    │
│        ↑ monitor.py polls every 2s + SSE per agent port    │
└─────────────────────────────────────────────────────────────┘

VM (sandbox 192.168.122.100) — headless, browser-only
┌──────────────────────────────┐
│  monitor.py :8769            │ ← rsync + python3 run
│  http.server :5550           │ ← serves ui/v3/index.html
│  tmux session 'gmux'         │
└──────────────────────────────┘
   Browser: http://192.168.122.100:5550/ui/v3/index.html
   (set window.GMUX_API in console for live data)
```

### Tauri command reference (lib.rs)
| Command | What it does |
|---------|-------------|
| `pty_write(data)` | Send keystrokes to tmux PTY |
| `pty_resize(cols, rows)` | Resize PTY |
| `get_pane_state()` | Read /tmp/gmuxtest-pane-state.json |
| `approve_agent(pane_id)` | POST to OpenCode permission endpoint |
| `reject_agent(pane_id)` | POST to OpenCode permission endpoint |
| `send_to_agent(pane_id, text)` | POST /session/:id/prompt_async |
| `open_project(path)` | New tmux window: cd path && opencode |
| `check_auth()` | ~/.config/opencode/auth.json exists? |
| `backend_health()` | TCP probe :8769 |
| `restart_backend()` | Kill + respawn monitor.py |
| `open_aquarium()` | Show aquarium Tauri window |
| `get_opencode_sessions()` | List OpenCode sessions across all ports |

---

## 📋 NEXT-AGENT PROMPT

Copy this verbatim when starting a new agent session from gmux-system:

---

```
You are continuing development of gmux-system, a gesture-aware AI terminal
multiplexer. The codebase is at ~/projects/gmux-system.

READ FIRST (in this order):
  1. cat HANDOVER.md              — full project state, architecture, known bugs
  2. cat DECISIONS.md             — what has been decided and why
  3. cat docs/NEXT_ACTIONS.md     — prioritised TODO list
  4. cat archive/MANIFEST.md      — snapshot history and working/not-working matrix
  5. cat docs/VM_DEPLOYMENT_LOG.md — VM deploy results

SYSTEM STATE:
  - monitor.py runs on :8769 (tmux pane tracker + HTTP API)
  - voice daemon on :8770 (faster-whisper WebSocket)
  - Tauri app: app/src-tauri/target/debug/gmuxtest (pre-built, 0.5s incremental)
  - UI source: ui/v3/index.html (7400 lines, single-file standalone)
  - app/src/index.html is a REAL COPY of ui/v3/index.html (not a symlink!)
    → whenever you edit ui/v3/index.html, also run:
      cp ui/v3/index.html app/src/index.html

LAUNCH TAURI (always use these env vars to suppress GStreamer crash):
  export GDK_BACKEND=x11
  export WEBKIT_DISABLE_COMPOSITING_MODE=1
  export GST_DEBUG="*:0"
  export GST_PLUGIN_FEATURE_RANK="v4l2src:NONE"
  cd ~/projects/gmux-system/app && npm run tauri dev

  Or simply:
  ./scripts/launch.sh   (but add the GST_ vars to scripts/launch.sh first!)

P0 ISSUES — fix before anything else:
  1. Tauri GStreamer crash: env vars above suppress it — verify UI renders correctly.
  2. Agent titles showing 'bun'/'fish' for some panes — window name cache cold start.
  3. Add GST_DEBUG + GST_PLUGIN_FEATURE_RANK to scripts/launch.sh Tauri block.
  4. app/src/index.html sync: add Makefile or pre-commit hook.

VM TESTING (see docs/VM_PROTOCOL.md):
  VM: ssh sandbox  →  192.168.122.100, user agent, passwordless key auth
  Shell on VM: fish (use bash -c "..." for one-liners)
  Deploy: rsync -av --exclude .git --exclude node_modules \
            ~/projects/gmux-system/ sandbox:~/projects/gmux-system/
  Run monitor: ssh sandbox bash -c "cd ~/projects/gmux-system && nohup python3 backend/status/monitor.py > /tmp/gmux-monitor.log 2>&1 &"
  Test: curl http://192.168.122.100:8769/health
  UI:   http://192.168.122.100:5550/ui/v3/index.html
        (in browser console: window.GMUX_API='http://192.168.122.100:8769'; location.reload())

GIT CONVENTIONS:
  Format: "v3.X: short summary\n\ndetail lines"
  Always cp ui/v3/index.html app/src/index.html before committing UI changes
  Snapshot to archive/ui/ before major UI changes, update archive/MANIFEST.md
  Update docs/NEXT_ACTIONS.md to reflect what you've done

DO NOT:
  - Use symlinks in app/src/ — vite cannot traverse them
  - Run tauri dev without GST_* env vars
  - Edit ui/v3/index.html without also updating app/src/index.html
  - Commit app/src-tauri/target/ (gitignored, 170MB+)
  - Try to run Tauri, Ghostty, voice, or gestures on the VM (all fail headless)

ARCHITECTURE ONE-LINER:
  monitor.py polls tmux + OpenCode SSE → /api/state JSON + /api/stream SSE →
  UI fetches live data → renders pane grid → Tauri commands handle approve/reject/send.
  Tauri auto-spawns all sidecars at startup, attaches PTY to tmux 'gmux' session.
```

---

## 📅 SESSION HISTORY

| Date | What happened |
|------|---------------|
| 2026-05-11 | Repo init: v3.0 UI + Rust Tauri backend consolidated from gmuxtest |
| 2026-05-12 | v3.2: avatar archived; v3.3: theme overhaul + TESTING_CHECKLIST |
| 2026-05-12 | Live data verified: RAM/CPU/tokens/todos/chat all working via psutil + OpenCode |
| 2026-05-12 | Agent run: full VM deploy — rsync, monitor :8769, UI :5550 all verified from host |
| 2026-05-12 | Chat ✕ button made context-aware (v3.3 — exits fullscreen vs closes panel) |
| 2026-05-12 | Tauri first launch: 1m20s cargo build, GStreamer crash discovered, symlink bug fixed |
| 2026-05-12 | Archive folder created: MANIFEST + slightly-working snapshots saved |
| 2026-05-13 | Tauri relaunched: GST env vars suppress crash, 0.5s incremental build, window open |
| 2026-05-13 | This HANDOVER.md fully rewritten with implemented/planned/bugs/next-agent prompt |
