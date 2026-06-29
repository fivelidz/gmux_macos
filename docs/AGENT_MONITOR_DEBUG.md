# Agent Monitor — diagnostic + debug history

**Status (alpha.11):** Dashboard window is built and bundled correctly, lib.rs
correctly emits `gmux-state` events to the `dashboard` window label,
dashboard's `data.js` correctly listens for those events. But user reports
clicking "Agent Monitor" still doesn't visibly open a window.

This doc tracks what we've ruled out and what remains.

---

## Reference: gmux-integration repo (Yuki's workbench)

URL: https://github.com/team-qalarc/gmux-integration

This repo runs a working setup of gmux against the yuki2 substrate.
Key insight from their `docs/TAURI_BACKEND_ANALYSIS.md`:

```rust
// app/src-tauri/src/lib.rs:885-922
thread::spawn(move || loop {
    thread::sleep(Duration::from_secs(1));
    let state_json = fs::read_to_string("/tmp/gmuxtest-pane-state.json")
        .or_else(|_| fs::read_to_string("/tmp/gmux-pane-state.json"))
        .unwrap_or_else(|_| "{}".to_string());
    for label in &["main", "dashboard", "aquarium"] {
        if let Some(win) = h3.get_webview_window(label) {
            let _ = win.emit("gmux-state",    &state_json);
            let _ = win.emit("gmux-services", &svc_json);
            let _ = win.emit("gmux-ram",      &ram_json);
            let _ = win.emit("memory-update", &mem_json);
            let _ = win.emit("activity-tick", &act_json);
            let _ = win.emit("files-update",  &files_json);
        }
    }
});
```

**Confirmed our `lib.rs` does this identically** (line ~1469).

The integration repo's verification doc (`TAURI_LIVE_VERIFIED.md`) shows
screenshots of a working flowchart dashboard at:
- `docs/screenshots/01-tauri-idle-3-panes.png` — sidebar shows agents
- `docs/screenshots/04-tauri-with-shim-spawned-agent.png` — live agent visible
- `docs/screenshots/08-tauri-final-state-tool-history.png` — tool history

These were all from **DEV MODE** (`npm run tauri dev`), not release builds.
Vite serves `dashboard/index.html` directly from `src/` so the bundle issue
we hit doesn't affect them.

---

## What we've ruled out (alpha.7 → alpha.11)

| Hypothesis | Outcome |
|---|---|
| Tauri CSP blocking dashboard JS | Ruled out — CSP is null |
| Dashboard files missing from release dist/ | **Was true, fixed in alpha.8** with vite plugin |
| Vite path-resolve bug writing to wrong dist/ | **Was true, fixed in alpha.8** with `__dirname` |
| `open_dashboard` calling only `show()` → window stays 10×10 | **Was true, fixed in alpha.10** with `set_size + center` |
| Global Ctrl+Alt+D handler also had the size bug | **Was true, fixed in alpha.10** |
| Dashboard JS doesn't listen for Tauri events | False — `data.js:480` listens for `gmux-state` |
| lib.rs doesn't emit events to dashboard window | False — `lib.rs:1469-1471` emits to `["main", "dashboard", "aquarium"]` |
| `withGlobalTauri: false` blocks event API | False — `withGlobalTauri: true` confirmed |
| URL `dashboard/index.html` wrong format | False — same string works in gmux-system dev mode |
| WebKitGTK + Wayland creates window at -100,-100 10×10 | **Likely cause** — confirmed via xdotool |

---

## Current behaviour to verify (need user to click Agent Monitor on alpha.11+)

After alpha.11, `open_dashboard` returns a diagnostic string:

```
open_dashboard: visible_before=false minimized=false set_size=ok center=ok show=ok size=1600x1000 pos=920,40
```

The frontend logs this to console AND shows it as a 5-second toast.
**This will tell us exactly what state the window ended up in.**

If toast says `size=1600x1000 pos=...` with sensible coords but no window
visible → KDE/Wayland is hiding it somehow (compositor issue).

If toast says `set_size=err(...)` or `show=err(...)` → we have a concrete
Tauri API error to chase.

If toast doesn't appear at all → `invoke('open_dashboard')` is throwing
or the click handler isn't wired.

---

## What to try if the diagnostic doesn't help

1. **Check DevTools console** — right-click in app → Inspect → Console.
   Look for `[gmux] open_dashboard →` log line and any errors.

2. **Manually invoke from console**:
   ```js
   const { invoke } = window.__TAURI__.core;
   invoke('open_dashboard').then(r => console.log('result:', r))
                            .catch(e => console.error('err:', e));
   ```

3. **Run in DEV mode** (proves the dashboard ITSELF is fine):
   ```bash
   cd ~/projects/gmux_v4/app && npm run tauri dev
   ```
   This bypasses the release-bundle issue entirely.

4. **Look in window manager for hidden gmux windows**:
   ```bash
   wmctrl -l | grep -i gmux
   xdotool search --name gmux | while read w; do
     xdotool getwindowgeometry $w
   done
   ```
   If you see a window at 10×10 px or position -100,-100 → that's the
   dashboard, the size fix didn't take effect.

5. **As last resort — open dashboard in browser**:
   ```bash
   cd ~/projects/gmux_v4/app/dist
   python3 -m http.server 5600
   # then visit http://localhost:5600/dashboard/index.html in Firefox/Chrome
   ```
   This bypasses Tauri entirely and proves the dashboard HTML+JS is fine.

---

## Files involved

| File | Role |
|---|---|
| `app/src-tauri/src/lib.rs:265-340` | `open_dashboard` command (alpha.11) |
| `app/src-tauri/src/lib.rs:1469-1471` | Event emitter to dashboard window |
| `app/src-tauri/src/lib.rs:1815-1850` | Global Ctrl+Alt+D shortcut |
| `app/src-tauri/tauri.conf.json` | Dashboard window registration |
| `app/vite.config.js` | Vite plugin to copy `src/dashboard/` to `dist/` |
| `app/src/dashboard/index.html` | Dashboard UI entry |
| `app/src/dashboard/js/data.js:425-540` | Tauri event listeners |
| `app/src/dashboard/js/app.js` | Flowchart renderer |
| `app/dist/dashboard/*` | Production build output (verified present) |
| `ui/v3/index.html:8423-8450` | `openAgentMonitor()` button handler |

---

## Decision: do not modify gmux-system

The gmux-integration repo is a *reference* — it shows the chain works in
their setup. We are NOT changing gmux-system; we have our own gmux_v4
with extra changes (v4 PTY layer, etc).

The dashboard fix needs to happen in gmux_v4 only.
