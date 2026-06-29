# gmux-ptyd — Backend Terminal Daemon (Design)

**Status:** design — alpha.21
**Problem owner:** PTY persistence across app restarts

## The problem

v4 PTYs live inside the Tauri process (`ProcessManager`, portable-pty).
When the app restarts (update, crash, rebuild), every in-app terminal and
the agents running in them **die with the process**. The UI then shows
panes flickering between existing/not-existing as stale state ages out
(the state-merge flicker is fixed in alpha.21, but the *terminals are
still gone*).

tmux solves exactly this — but the standalone goal is "no tmux required",
and packaging gmux with a backend daemon is acceptable ("if we package it
with gmuxtest that is fine").

## Design: gmux-ptyd

A small standalone daemon that OWNS all PTYs. The Tauri app becomes a
*client* that attaches/detaches; PTYs survive app restarts.

```
┌────────────┐   unix socket    ┌────────────┐   PTY pairs   ┌──────────┐
│ gmux app   │ ◄══════════════► │ gmux-ptyd  │ ◄═══════════► │ agents   │
│ (Tauri UI) │  JSON-RPC frames │  (daemon)  │  portable-pty │ opencode │
└────────────┘                  └────────────┘               └──────────┘
      ▲  app restart = reconnect + replay scrollback
```

### Components

1. **gmux-ptyd binary** (Rust, reuses `core/process_manager.rs` nearly
   verbatim — same portable-pty, same reader-thread pattern):
   - Listens on `$XDG_RUNTIME_DIR/gmux-ptyd.sock` (Unix) / named pipe (Windows)
   - Daemonizes on first launch; the app spawns it if not running
     (`Command::new("gmux-ptyd").spawn()` — packaged in the same bundle)
   - Holds a ring buffer (e.g. 256 KB) of scrollback per session for replay
     on reattach

2. **Protocol** (newline-delimited JSON over the socket):
   - `spawn {cwd, env, cols, rows} → {session_id}`
   - `attach {session_id, replay: bool} → stream of {output} frames`
   - `write {session_id, data}`
   - `resize {session_id, cols, rows}`
   - `kill {session_id}` / `list {} → [{session_id, pid, cwd, alive}]`

3. **Tauri side** — `ProcessManager` becomes a thin proxy:
   - `spawn_shell` → ptyd `spawn` + `attach`
   - `write_stdin` → ptyd `write`
   - output frames → existing `pty-output-{id}` Tauri events (UI unchanged)
   - On app start: `list` + `attach` to every live session → panes
     REAPPEAR with scrollback instead of dying

4. **Fallback**: if the daemon can't start (perms, sandbox), fall back to
   the current in-process ProcessManager — identical UI, just no
   persistence. One env var (`GMUX_PTYD=0`) forces the fallback.

### Packaging

- Build as a second `[[bin]]` target in the existing src-tauri crate —
  shares `core/` code, no new repo.
- Tauri bundler `externalBin` ships it alongside the app binary.
- Daemon lifecycle: started lazily by the app; survives app exit;
  `gmux-ptyd --shutdown` for explicit stop; idle-exit after N hours with
  zero sessions (configurable).

### Crash/upgrade semantics

| Event | Result |
|---|---|
| App restart/upgrade | sessions persist, UI reattaches + replays scrollback |
| ptyd crash | sessions lost (same as today) — but ptyd is tiny/stable |
| reboot | sessions lost — session_restore manifest offers respawn (exists) |

### Sizing

- ~400 lines new Rust (socket server + framing + ring buffer)
- ~150 lines changed in ProcessManager (proxy mode)
- No frontend changes (events identical)

### Why not just require tmux?

tmux delivers persistence today (the v3 path) but: not on Windows, extra
install for new users, and the long-term direction is app-owned terminals.
ptyd keeps the portable-pty investment and works identically on all three
OSes. Power users on Linux can still prefer the tmux path — both remain.
