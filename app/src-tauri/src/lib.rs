/// gmuxtest — UI sandbox for the gmux gesture-aware terminal multiplexer
///
/// Separate from gmux/gmux-app so it can be freely hacked without affecting
/// the working terminal gmux.
///
/// Key difference from gmux-app:
///   - Reads pane state directly from /tmp/gmux-pane-state.json via a Rust
///     polling thread → emits "gmux-state" Tauri event every second.
///     No WebSocket bridge required for the status sidebar to work.
///   - Port 1421 (gmux-app uses 1420) so both can run simultaneously.
///   - Config stored in ~/.config/gmuxtest/ (separate from gmux)
///
/// Tauri commands exposed to JS:
///   pty_write / pty_resize  — PTY I/O
///   get_home_dir            — home directory path
///   get_pane_state          — read /tmp/gmux-pane-state.json (one-shot)
///   get_pane_state_v4       — live session state from ProcessManager (v4)
///   get_services            — read /tmp/gmux-services.json
///   open_aquarium           — show aquarium window
///   open_project(path)      — new tmux window: cd <path> && qc
///   check_auth              — opencode auth.json exists?

use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

// v4 PTY core (additive — does not replace the legacy single-PTY path yet).
// See docs/V4_PTY_SWAP.md for the migration plan.
pub mod core;
pub mod commands;
// alpha.22 — embedded gmux HTTP API for other apps/agents (axum on :6310).
pub mod api;

use crate::core::ProcessManager;

// ── Shared state ──────────────────────────────────────────────────────────────

struct AppState {
    pty_writer: Option<Box<dyn Write + Send>>,
    pty_master: Option<Box<dyn MasterPty + Send>>,
    sidecars:   Vec<Child>,
}

impl AppState {
    fn new() -> Self {
        Self { pty_writer: None, pty_master: None, sidecars: Vec::new() }
    }
}

type SharedState = Arc<Mutex<AppState>>;

// ── Tauri commands ────────────────────────────────────────────────────────────

#[tauri::command]
fn pty_write(data: String, state: tauri::State<SharedState>) {
    let mut s = state.lock().unwrap();
    if let Some(writer) = &mut s.pty_writer {
        let _ = writer.write_all(data.as_bytes());
    }
}

#[tauri::command]
fn pty_resize(cols: u16, rows: u16, state: tauri::State<SharedState>) {
    let s = state.lock().unwrap();
    if let Some(master) = &s.pty_master {
        let _ = master.resize(PtySize { rows, cols, pixel_width: 0, pixel_height: 0 });
        eprintln!("[gmuxtest] PTY resized: {cols}×{rows}");
    }
}

#[tauri::command]
fn get_home_dir() -> String {
    std::env::var("HOME").unwrap_or_else(|_| "/home".to_string())
}

/// Read pane state — gmuxtest-specific file first, fall back to gmux production
#[tauri::command]
fn get_pane_state() -> String {
    std::fs::read_to_string("/tmp/gmuxtest-pane-state.json")
        .or_else(|_| std::fs::read_to_string("/tmp/gmux-pane-state.json"))
        .unwrap_or_else(|_| "{}".to_string())
}

/// v4 — Read live pane state from the ProcessManager (no tmux or tmp file needed).
///
/// Returns a JSON dict keyed by "v4-{session_id}" with the same shape that
/// the dashboard's data.js expects from gmuxtest-pane-state.json so the UI
/// can consume it without changes.
///
/// Fields emitted per session:
///   pane_id, session_name, window_index, window_name, cwd,
///   state ("working"|"idle"), ram_mb, cpu_pct, uptime_s,
///   api_port (0 — not tracked by Rust yet), is_v4 (true),
///   v4_session_id, child_pid
///
/// Falls back to the tmux-backed file if ProcessManager has no sessions
/// (compatible with mixed v3+v4 deployments).
#[tauri::command]
fn get_pane_state_v4(pm: tauri::State<core::ProcessManager>) -> String {
    // alpha.21 FIX — previously this returned ONLY v4 panes whenever any v4
    // session existed, while the 1Hz gmux-state emitter returned ONLY tmux
    // panes. The two sources stomped each other in the UI's full-replacement
    // apply, making panes flicker between existing / not-existing. Both
    // paths now emit the same MERGED state (file/tmux panes + v4 panes).
    let file_json = std::fs::read_to_string("/tmp/gmuxtest-pane-state.json")
        .or_else(|_| std::fs::read_to_string("/tmp/gmux-pane-state.json"))
        .unwrap_or_else(|_| "{}".to_string());
    merge_state_with_v4(&file_json, &pm)
}

/// Build the synthesized pane-state entries for every live v4 PTY session.
/// Shape matches gmuxtest-pane-state.json entries.
fn build_v4_entries(pm: &core::ProcessManager) -> Vec<String> {
    let sessions = pm.get_all_session_pids();
    if sessions.is_empty() {
        return Vec::new();
    }

    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;

    // Build a JSON object in the same shape as gmuxtest-pane-state.json.
    // We only have the session_id and child_pid from the Rust side; the rest
    // is synthesised with safe defaults.  monitor.py (when running) will
    // overwrite its own entries, so these v4 entries coexist cleanly.
    let mut entries = Vec::with_capacity(sessions.len());
    for (session_id, child_pid) in &sessions {
        // Derive minimal state for this PTY session.
        // cpu/ram: read from /proc/<pid>/stat if available (Linux).
        let (ram_mb, cpu_pct) = read_proc_stats(*child_pid);
        // foreground_cmd: read /proc/<pid>/comm (Linux) — gives 'bash',
        // 'claude', 'bun', etc. The UI's agentTypeOf() helper turns this
        // into a friendly type label.
        let fg_cmd = read_proc_comm(*child_pid);
        let entry = format!(
            r#""v4-{id}":{{"pane_id":"v4-{id}","session_name":"gmux-v4","window_index":{id},"window_name":"v4-{id}","cwd":"","state":"idle","is_v4":true,"v4_session_id":{id},"child_pid":{pid},"ram_mb":{ram},"cpu_pct":{cpu},"uptime_s":0,"api_port":0,"last_update_ms":{ts},"foreground_cmd":"{fg}"}}"#,
            id  = session_id,
            pid = child_pid,
            ram = ram_mb,
            cpu = cpu_pct,
            ts  = now_ms,
            fg  = fg_cmd.replace(['"', '\\'], ""),
        );
        entries.push(entry);
    }
    entries
}

/// Merge file-backed (tmux) pane state with live v4 PTY entries into one
/// JSON object string. Both the `get_pane_state_v4` command and the 1Hz
/// state emitter use this so the UI always sees the COMPLETE pane set.
pub(crate) fn merge_state_with_v4(file_json: &str, pm: &core::ProcessManager) -> String {
    let v4 = build_v4_entries(pm);
    let trimmed = file_json.trim();
    let valid_obj = trimmed.starts_with('{') && trimmed.ends_with('}') && trimmed.len() >= 2;
    if v4.is_empty() {
        return if valid_obj { trimmed.to_string() } else { "{}".to_string() };
    }
    if valid_obj {
        let inner = trimmed[1..trimmed.len() - 1].trim();
        if inner.is_empty() {
            format!("{{{}}}", v4.join(","))
        } else {
            format!("{{{},{}}}", inner, v4.join(","))
        }
    } else {
        format!("{{{}}}", v4.join(","))
    }
}

/// Read the leaf executable name (`comm`) for a process on Linux.
/// `/proc/<pid>/comm` is one line, e.g. "bash" or "claude" or "bun".
/// Walks the child process tree once to prefer an interesting process
/// over the shell — e.g. if the PTY shell launched `claude`, we want
/// "claude" not "bash".
fn read_proc_comm(pid: i32) -> String {
    #[cfg(target_os = "linux")]
    {
        // Helper: read /proc/<pid>/comm safely
        let read_comm = |p: i32| -> String {
            std::fs::read_to_string(format!("/proc/{}/comm", p))
                .map(|s| s.trim().to_string())
                .unwrap_or_default()
        };
        // Walk children once to find a more interesting comm than 'bash'/'sh'/'fish'
        let parent = read_comm(pid);
        let shells = ["bash", "sh", "fish", "zsh", "dash"];
        if !shells.contains(&parent.as_str()) {
            return parent;
        }
        // Look in /proc/<pid>/task/<tid>/children for child pids
        if let Ok(entries) = std::fs::read_dir(format!("/proc/{}/task", pid)) {
            for entry in entries.flatten() {
                let children_path = entry.path().join("children");
                if let Ok(contents) = std::fs::read_to_string(&children_path) {
                    for cpid_str in contents.split_whitespace() {
                        if let Ok(cpid) = cpid_str.parse::<i32>() {
                            let cname = read_comm(cpid);
                            if !cname.is_empty() && !shells.contains(&cname.as_str()) {
                                return cname;
                            }
                        }
                    }
                }
            }
        }
        parent
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = pid;
        String::new()
    }
}

/// Read RAM (MB) and CPU% from /proc/<pid>/statm + /proc/<pid>/stat on Linux.
/// Returns (0, 0.0) on any error or non-Linux platform.
fn read_proc_stats(pid: i32) -> (u64, f32) {
    #[cfg(target_os = "linux")]
    {
        // statm: page counts — field 0 is resident set size in pages
        let ram_mb = (|| -> Option<u64> {
            let statm = std::fs::read_to_string(format!("/proc/{}/statm", pid)).ok()?;
            let rss_pages: u64 = statm.split_whitespace().nth(1)?.parse().ok()?;
            let page_kb = 4u64; // 4 KB pages on x86_64
            Some(rss_pages * page_kb / 1024)
        })()
        .unwrap_or(0);

        // CPU%: very rough — not sampling between ticks, just best-effort
        // Read /proc/<pid>/stat field 14+15 (utime+stime in jiffies)
        let cpu_pct: f32 = (|| -> Option<f32> {
            let stat = std::fs::read_to_string(format!("/proc/{}/stat", pid)).ok()?;
            let parts: Vec<&str> = stat.split_whitespace().collect();
            let utime: u64 = parts.get(13)?.parse().ok()?;
            let stime: u64 = parts.get(14)?.parse().ok()?;
            let total_jiffies = utime + stime;
            // Jiffies since process started — not a %, but the UI
            // treats 0 as idle so any non-zero value shows activity.
            Some(if total_jiffies > 0 { 1.0 } else { 0.0 })
        })()
        .unwrap_or(0.0);

        (ram_mb, cpu_pct)
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = pid;
        (0, 0.0)
    }
}

/// Read services flags — gmuxtest-specific file first, fall back to gmux production
#[tauri::command]
fn get_services() -> String {
    std::fs::read_to_string("/tmp/gmuxtest-services.json")
        .or_else(|_| std::fs::read_to_string("/tmp/gmux-services.json"))
        .unwrap_or_else(|_| "{}".to_string())
}

/// Show or raise the aquarium window
#[tauri::command]
fn open_aquarium(app: AppHandle) -> Result<String, String> {
    let win = app
        .get_webview_window("aquarium")
        .ok_or_else(|| "aquarium window not registered".to_string())?;
    let _ = win.unminimize();
    let size = tauri::Size::Logical(tauri::LogicalSize { width: 900.0, height: 600.0 });
    let _ = win.set_size(size);
    let _ = win.center();
    win.show().map_err(|e| format!("show failed: {}", e))?;
    let _ = win.set_focus();
    Ok("aquarium opened".to_string())
}

/// Hide the aquarium window
#[tauri::command]
fn hide_aquarium(app: AppHandle) {
    if let Some(win) = app.get_webview_window("aquarium") {
        let _ = win.hide();
    }
}

/// Show or raise the dashboard window (agent display — knowledge / flowchart view).
///
/// v3.8.3 fix: previously this only called `.show()` and `.set_focus()`.
/// In some WebKitGTK + Wayland combinations the window was created at
/// 10×10 px at position -100,-100 (essentially invisible), even though
/// the conf specified width=1800 height=1100. Now we explicitly set
/// the size + position + unmaximize + center before showing, so the
/// window always appears at a usable size in front of the user.
///
/// Returns a diagnostic string describing each step's outcome so the
/// frontend (and dev console) can see exactly what happened.
#[tauri::command]
fn open_dashboard(app: AppHandle) -> Result<String, String> {
    let win = app
        .get_webview_window("dashboard")
        .ok_or_else(|| "dashboard window not registered".to_string())?;

    let mut log = String::from("open_dashboard: ");

    // Pre-state
    let visible_before = win.is_visible().unwrap_or(false);
    let minimized = win.is_minimized().unwrap_or(false);
    log.push_str(&format!("visible_before={} minimized={} ", visible_before, minimized));

    // Make sure it's not minimized / collapsed
    if minimized {
        let _ = win.unminimize();
        log.push_str("unminimized ");
    }
    let _ = win.unmaximize();

    // Force a sane size + centre it (some WMs ignore the conf defaults
    // when the window is created with visible:false).
    let size = tauri::Size::Logical(tauri::LogicalSize { width: 1600.0, height: 1000.0 });
    match win.set_size(size) {
        Ok(_)  => log.push_str("set_size=ok "),
        Err(e) => log.push_str(&format!("set_size=err({}) ", e)),
    }
    match win.center() {
        Ok(_)  => log.push_str("center=ok "),
        Err(e) => log.push_str(&format!("center=err({}) ", e)),
    }

    // Move it to the front explicitly (some WMs need set_always_on_top
    // briefly to lift the window above the main one)
    let _ = win.set_always_on_top(true);

    // Show + raise + focus
    match win.show() {
        Ok(_)  => log.push_str("show=ok "),
        Err(e) => return Err(format!("{} show=err({})", log, e)),
    }
    let _ = win.set_focus();

    // Release always-on-top after a moment so the user can switch back
    // to the main window normally.
    std::thread::spawn({
        let w = win.clone();
        move || {
            std::thread::sleep(std::time::Duration::from_millis(500));
            let _ = w.set_always_on_top(false);
        }
    });

    // Post-state
    let size_after = win.outer_size().ok().map(|s| format!("{}x{}", s.width, s.height)).unwrap_or_default();
    let pos_after = win.outer_position().ok().map(|p| format!("{},{}", p.x, p.y)).unwrap_or_default();
    log.push_str(&format!("size={} pos={}", size_after, pos_after));
    Ok(log)
}

/// Hide the dashboard window
#[tauri::command]
fn hide_dashboard(app: AppHandle) {
    if let Some(win) = app.get_webview_window("dashboard") {
        let _ = win.hide();
    }
}

/// Open a project in a new tmux window: prefix+c, cd <path>, opencode
/// Fixed: was sending "\x01cnewp\r" which typed "newp" into the new window.
/// Now correctly sequences: new-window → sleep → run command → rename.
///
/// v4: when GMUX_V4_PTY=1 or tmux is absent this returns an error directing
/// the caller to use `open_agent_v4` instead (no tmux writer available).
#[tauri::command]
fn open_project(path: String, state: tauri::State<SharedState>) -> Result<String, String> {
    if is_v4_mode() {
        return Err("v4-redirect: use open_agent_v4 — tmux writer not available in v4 PTY mode".to_string());
    }
    let path = path.trim().to_string();
    if path.is_empty() { return Err("empty path".to_string()); }
    let win_name = path.split('/').next_back().unwrap_or("project").to_string();

    // Step 1: new tmux window (Ctrl+A c)
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(b"\x01c");
        }
    }
    thread::sleep(std::time::Duration::from_millis(300));

    // Step 2: cd into project and launch opencode
    let start_cmd = format!("cd {} && opencode\r", shell_escape(&path));
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            writer.write_all(start_cmd.as_bytes()).map_err(|e| e.to_string())?;
        }
    }
    thread::sleep(std::time::Duration::from_millis(250));

    // Step 3: rename window (Ctrl+A ,) + lock automatic-rename off
    let rename_cmd = format!("\x01,{}\r", win_name);
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(rename_cmd.as_bytes());
        }
    }
    thread::sleep(std::time::Duration::from_millis(200));
    let lock_cmd = "\x01:set-window-option automatic-rename off\r".to_string();
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(lock_cmd.as_bytes());
        }
    }

    Ok(format!("opened: {}", path))
}

fn shell_escape(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}

/// Returns true if the v4 PTY mode is active (env var set OR tmux not available).
/// When true, commands that previously went through the tmux-attached PTY writer
/// (open_project, spawn_sub_agent, login_provider) should return a redirect
/// error so the JS caller can use the v4 equivalents instead.
fn is_v4_mode() -> bool {
    std::env::var("GMUX_V4_PTY").as_deref() == Ok("1")
        || which::which("tmux").is_err()
}

/// Open a URL in the system browser in a cross-platform way.
///
/// - macOS: uses `open` (built into macOS)
/// - Linux: uses `xdg-open` (freedesktop standard)
/// - Windows: uses `start` via cmd /c (not a current target, included for
///   future-proofing)
///
/// This helper is used for OAuth flows and external links. Any caller that
/// previously hard-coded `xdg-open` should use this instead.
#[allow(dead_code)] // used by future OAuth URL-open flows (v3.6+)
fn open_url_in_browser(url: &str) {
    let opener = if cfg!(target_os = "macos") {
        "open"
    } else if cfg!(target_os = "windows") {
        "cmd"    // requires .args(["/c", "start", url]) — see open_url_command()
    } else {
        "xdg-open"
    };

    if cfg!(target_os = "windows") {
        let _ = std::process::Command::new("cmd")
            .args(["/c", "start", "", url])
            .spawn();
    } else {
        let _ = std::process::Command::new(opener).arg(url).spawn();
    }
}

#[tauri::command]
fn check_auth() -> bool {
    let home = std::env::var("HOME").unwrap_or_default();
    std::path::Path::new(&format!("{}/.local/share/opencode/auth.json", home)).exists()
}

/// v3.6 — list providers from ~/.local/share/opencode/auth.json.
///
/// Returns a JSON string (so we can keep the command signature simple and
/// let the JS side parse it):
/// `[ {id, type, authed:true, expires} , ... ]`
///
/// SECURITY: we explicitly DO NOT include access/refresh tokens in the
/// returned data. The keys exist only in the auth.json file on disk.
/// Env-var-only providers (e.g. ANTHROPIC_API_KEY exported in shell) are
/// also surfaced so the user can see "this is authed via env var".
#[tauri::command]
fn list_providers() -> Result<String, String> {
    use std::io::Write as _;
    let home = std::env::var("HOME").unwrap_or_default();
    let auth_path = format!("{}/.local/share/opencode/auth.json", home);

    let mut out = String::from("[");
    let mut first = true;
    let push_entry = |out: &mut String, first: &mut bool, body: String| {
        if !*first { out.push(','); }
        out.push_str(&body);
        *first = false;
    };

    // ── 1. Parse auth.json if present ────────────────────────────────────
    if let Ok(s) = std::fs::read_to_string(&auth_path) {
        // Very small ad-hoc parser to avoid pulling in serde_json::Value
        // for this one command. We expect the shape:
        //   { "anthropic": {"type":"oauth","access":"...","refresh":"...","expires":1234} ,
        //     "openai":    {"type":"api","key":"..."} }
        // We iterate top-level keys, skip the secret fields, and re-emit
        // only id + type + authed:true + expires (if any).
        // Use a real parser if available — serde_json is already in deps.
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&s) {
            if let Some(obj) = v.as_object() {
                for (id, val) in obj {
                    let ty = val.get("type").and_then(|x| x.as_str()).unwrap_or("unknown");
                    let expires = val.get("expires").and_then(|x| x.as_i64()).unwrap_or(0);
                    let body = format!(
                        r#"{{"id":"{}","type":"{}","authed":true,"source":"file","expires":{}}}"#,
                        id.replace('"', "\\\""),
                        ty.replace('"', "\\\""),
                        expires,
                    );
                    push_entry(&mut out, &mut first, body);
                }
            }
        }
    }

    // ── 2. Env-var-only providers ─────────────────────────────────────────
    // Detect common provider API-key env vars so the UI can show them as
    // authed even without an auth.json entry. Order matches the most-used
    // providers in the wild.
    let env_providers: &[(&str, &str)] = &[
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai",    "OPENAI_API_KEY"),
        ("google",    "GOOGLE_API_KEY"),
        ("google",    "GEMINI_API_KEY"),
        ("deepseek",  "DEEPSEEK_API_KEY"),
        ("mistral",   "MISTRAL_API_KEY"),
        ("groq",      "GROQ_API_KEY"),
        ("xai",       "XAI_API_KEY"),
    ];
    for (id, env) in env_providers {
        if std::env::var(env).is_ok() {
            let body = format!(
                r#"{{"id":"{}","type":"env","authed":true,"source":"env:{}","expires":0}}"#,
                id, env,
            );
            push_entry(&mut out, &mut first, body);
        }
    }

    // ── 3. Locally-running model servers (Ollama) ─────────────────────────
    // Try a short TCP check on the default Ollama port. Doesn't return
    // authed=true (no keys involved) but does flag presence.
    if let Ok(_) = std::net::TcpStream::connect_timeout(
        &"127.0.0.1:11434".parse().unwrap(),
        std::time::Duration::from_millis(150),
    ) {
        let body = r#"{"id":"ollama","type":"local","authed":true,"source":"localhost:11434","expires":0}"#.to_string();
        push_entry(&mut out, &mut first, body);
    }

    out.push(']');
    let _ = std::io::stdout().flush();
    Ok(out)
}

/// v3.6 — open a new tmux window running `opencode auth login <provider>`.
/// opencode prints an OAuth URL the user can click; the CLI exits once the
/// user completes the flow. We open it the same way as `open_agent` — via
/// the existing PTY writer + tmux prefix-c, so it appears as a normal pane.
///
/// v4: when GMUX_V4_PTY=1 or tmux is absent, spawns the auth flow via a
/// direct process (not tmux) and returns the spawned PID so the UI can
/// show a toast directing the user to the terminal.
#[tauri::command]
fn login_provider(provider_id: String, state: tauri::State<SharedState>) -> Result<String, String> {
    let provider_id = provider_id.trim().to_string();
    if provider_id.is_empty() { return Err("empty provider_id".to_string()); }
    // v4 mode: launch auth flow as a detached subprocess — no PTY writer needed.
    if is_v4_mode() {
        let allowed = [
            "anthropic", "openai", "google", "deepseek",
            "mistral", "groq", "xai", "ollama", "github",
        ];
        if !allowed.contains(&provider_id.as_str()) {
            return Err(format!("unknown provider '{}'", provider_id));
        }
        let child = std::process::Command::new("opencode")
            .args(["auth", "login", &provider_id])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .map_err(|e| format!("opencode not found: {}", e))?;
        return Ok(format!("auth flow started for {} (pid {})", provider_id, child.id()));
    }
    // Whitelist of provider IDs we accept — refuse anything that could be
    // a shell-injection vector.
    let allowed = [
        "anthropic", "openai", "google", "deepseek",
        "mistral", "groq", "xai", "ollama", "github",
    ];
    if !allowed.contains(&provider_id.as_str()) {
        return Err(format!("unknown provider '{}'", provider_id));
    }

    // Step 1: new tmux window
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(b"\x01c");
        }
    }
    thread::sleep(std::time::Duration::from_millis(300));

    // Step 2: run `opencode auth login <id>` — opencode prompts in this
    // pane; user pastes the OAuth callback URL when done.
    let cmd = format!("opencode auth login {}\r", provider_id);
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            writer.write_all(cmd.as_bytes()).map_err(|e| e.to_string())?;
        }
    }
    thread::sleep(std::time::Duration::from_millis(200));

    // Step 3: rename window so user can find it later + lock the name
    let win_name = format!("auth-{}", provider_id);
    let rename_cmd = format!("\x01,{}\r", win_name);
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(rename_cmd.as_bytes());
        }
    }
    thread::sleep(std::time::Duration::from_millis(200));
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(b"\x01:set-window-option automatic-rename off\r");
        }
    }

    Ok(format!("login flow started for {}", provider_id))
}

/// v3.6 — remove a provider's credentials. Spawns
/// `opencode auth logout <id>` non-interactively (opencode supports a
/// non-interactive --provider flag in 1.14+, but for safety we fall back
/// to running it in a new pane the same way as login). Returns immediately.
#[tauri::command]
fn logout_provider(provider_id: String) -> Result<String, String> {
    let provider_id = provider_id.trim().to_string();
    let allowed = [
        "anthropic", "openai", "google", "deepseek",
        "mistral", "groq", "xai", "ollama", "github",
    ];
    if !allowed.contains(&provider_id.as_str()) {
        return Err(format!("unknown provider '{}'", provider_id));
    }
    // Try CLI flag first (non-interactive)
    let output = std::process::Command::new("opencode")
        .args(["auth", "logout", "--provider", &provider_id])
        .output();
    match output {
        Ok(o) if o.status.success() => Ok(format!("logged out {}", provider_id)),
        Ok(o) => {
            // Fall back to deleting the key directly from auth.json since
            // older opencode builds don't support --provider.
            let home = std::env::var("HOME").unwrap_or_default();
            let path = format!("{}/.local/share/opencode/auth.json", home);
            if let Ok(content) = std::fs::read_to_string(&path) {
                if let Ok(mut v) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let Some(obj) = v.as_object_mut() {
                        if obj.remove(&provider_id).is_some() {
                            let new = serde_json::to_string_pretty(&v).unwrap_or(content);
                            std::fs::write(&path, new).map_err(|e| e.to_string())?;
                            return Ok(format!("logged out {} (manual)", provider_id));
                        }
                    }
                }
            }
            Err(format!(
                "opencode logout failed: {}",
                String::from_utf8_lossy(&o.stderr)
            ))
        }
        Err(e) => Err(format!("opencode binary not found: {}", e)),
    }
}

/// v3.6 — list available models grouped by provider.
/// Reads `opencode models` output (one `provider/model` per line) and
/// returns a JSON array of provider objects:
///   [{"id":"anthropic","models":["claude-sonnet-4","claude-opus-4"]}, ...]
#[tauri::command]
fn list_models() -> Result<String, String> {
    let output = std::process::Command::new("opencode")
        .args(["models"])
        .output()
        .map_err(|e| format!("opencode binary not found: {}", e))?;
    if !output.status.success() {
        return Err(format!(
            "opencode models failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut groups: std::collections::BTreeMap<String, Vec<String>> = Default::default();
    for line in stdout.lines() {
        let line = line.trim();
        if line.is_empty() { continue; }
        if let Some(idx) = line.find('/') {
            let provider = line[..idx].to_string();
            let model = line[idx + 1..].to_string();
            groups.entry(provider).or_default().push(model);
        }
    }
    let mut out = String::from("[");
    let mut first = true;
    for (provider, models) in groups {
        if !first { out.push(','); }
        first = false;
        out.push_str(&format!(r#"{{"id":"{}","models":["#, provider));
        let mut mfirst = true;
        for m in models {
            if !mfirst { out.push(','); }
            mfirst = false;
            // Escape backslashes and quotes only — model IDs don't have
            // other special chars in opencode's output.
            let esc = m.replace('\\', "\\\\").replace('"', "\\\"");
            out.push_str(&format!("\"{}\"", esc));
        }
        out.push_str("]}");
    }
    out.push(']');
    Ok(out)
}

/// Send a message to an OpenCode agent via its HTTP API (uses curl to avoid CORS + extra deps)
#[tauri::command]
async fn send_to_agent(
    port: u16,
    session_id: String,
    directory: String,
    message: String,
) -> Result<String, String> {
    // Build the URL — percent-encode the query params manually (simple chars only needed)
    let enc_session = session_id.replace(' ', "%20").replace('/', "%2F");
    let enc_dir     = directory.replace(' ', "%20");
    let url = format!(
        "http://127.0.0.1:{}/session/{}/prompt_async?directory={}",
        port, enc_session, enc_dir
    );

    // Build JSON body: {"parts":[{"type":"text","text":"..."}]}
    let escaped_msg = message
        .replace('\\', "\\\\")
        .replace('"',  "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r");
    let body = format!(r#"{{"parts":[{{"type":"text","text":"{}"}}]}}"#, escaped_msg);

    let result = std::process::Command::new("curl")
        .args([
            "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", &body,
            "--max-time", "10",
            &url,
        ])
        .output()
        .map_err(|e| format!("curl exec failed: {}", e))?;

    let status = String::from_utf8_lossy(&result.stdout);
    let code = status.trim();
    if code == "200" || code == "204" || code == "202" {
        Ok("sent".to_string())
    } else if code.is_empty() {
        Err("no response — is OpenCode running on that port?".to_string())
    } else {
        Err(format!("HTTP {}", code))
    }
}

/// Spawn a sub-agent in a new tmux window and record a parent-pointer to the
/// JSON file at /tmp/gmuxtest-sub-agents.json so monitor.py can merge the
/// parent_pane_id into the new pane's state dict.
///
/// Window is named `<parent_name>+<name>` so the dashboard can identify the
/// hierarchy visually even before the JSON file is read.
///
/// Shape written to /tmp/gmuxtest-sub-agents.json:
///   { "<new_window_name>": { "parent_pane_id": "...", "spawned_at": <ms>,
///                            "agent_type": "...", "model": "..." } }
/// Note: We key by window_name (not pane_id) because the pane_id is not
/// known until monitor.py's next poll assigns one. monitor.py resolves the
/// key by matching window_name against pane state records.
///
/// v4: when GMUX_V4_PTY=1 or tmux is absent, returns a redirect error so
/// the JS caller can use spawn_sub_agent_v4 instead.
#[tauri::command]
fn spawn_sub_agent(
    parent_pane_id: String,
    parent_name: String,
    name: String,
    directory: String,
    agent_type: String,
    model: String,
    state: tauri::State<SharedState>,
) -> Result<String, String> {
    if is_v4_mode() {
        return Err("v4-redirect: use spawn_sub_agent_v4 — tmux writer not available in v4 PTY mode".to_string());
    }
    let dir = directory.trim().to_string();
    if dir.is_empty() { return Err("empty directory".to_string()); }

    let win_name = format!("{}+{}", parent_name.trim(), name.trim());

    let start_cmd = match agent_type.as_str() {
        "opencode" | "qalcode" => format!("cd {} && opencode", shell_escape(&dir)),
        "claude"               => {
            let m = if model.is_empty() { "claude-sonnet-4-5".to_string() } else { model.clone() };
            format!("cd {} && claude --model {}", shell_escape(&dir), m)
        },
        "aider"                => format!("cd {} && aider --no-pretty", shell_escape(&dir)),
        "terminal"             => format!("cd {}", shell_escape(&dir)),
        _                      => format!("cd {} && opencode", shell_escape(&dir)),
    };

    // Step 1: new tmux window (prefix+c)
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(b"\x01c");
        }
    }
    thread::sleep(std::time::Duration::from_millis(300));

    // Step 2: launch agent in new window
    let full_cmd = format!("{}\r", start_cmd);
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            writer.write_all(full_cmd.as_bytes()).map_err(|e| e.to_string())?;
        }
    }

    // Step 3: rename window to parent+name
    thread::sleep(std::time::Duration::from_millis(250));
    let rename_cmd = format!("\x01,{}\r", win_name);
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(rename_cmd.as_bytes());
        }
    }

    // Step 4: lock automatic-rename off (v3.5.2 fix)
    thread::sleep(std::time::Duration::from_millis(200));
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(b"\x01:set-window-option automatic-rename off\r");
        }
    }

    // Step 5: write parent-pointer record to /tmp/gmuxtest-sub-agents.json
    // We store the mapping keyed by window_name (resolved to pane_id by monitor.py
    // on the next poll — pane_id is not known yet at this point).
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;
    let sa_path = "/tmp/gmuxtest-sub-agents.json";
    let existing = std::fs::read_to_string(sa_path).unwrap_or_else(|_| "{}".to_string());
    let mut map: serde_json::Value = serde_json::from_str(&existing)
        .unwrap_or_else(|_| serde_json::Value::Object(Default::default()));
    if let Some(obj) = map.as_object_mut() {
        obj.insert(
            win_name.clone(),
            serde_json::json!({
                "parent_pane_id": parent_pane_id,
                "spawned_at": now_ms,
                "agent_type": agent_type,
                "model": model,
            }),
        );
    }
    if let Ok(json_str) = serde_json::to_string_pretty(&map) {
        // Atomic write: write to .tmp then rename
        let tmp = format!("{}.tmp", sa_path);
        if std::fs::write(&tmp, &json_str).is_ok() {
            let _ = std::fs::rename(&tmp, sa_path);
        }
    }

    Ok(format!("spawned: {} in {}", win_name, dir))
}

/// v4 — Build the agent launch command for a fresh PTY, honouring the
/// requested permission mode.
///
/// permission_mode: "safe" (default) | "restricted" | "extreme"
///   - opencode/qalcode: restricted → `--agent yolo`, extreme → `--agent yolo-extreme`
///     (the user's qalcode2 config defines these yolo agent personas)
///   - claude: restricted/extreme → `--dangerously-skip-permissions`
///   - aider:  restricted/extreme → `--yes-always`
pub(crate) fn build_agent_start_cmd_v4(agent_type: &str, model: &str, permission_mode: &str) -> String {
    let perm = match permission_mode {
        "restricted" | "extreme" => permission_mode,
        _ => "safe",
    };
    match agent_type {
        "opencode" | "qalcode" => match perm {
            "extreme" => "opencode --agent yolo-extreme\r".to_string(),
            "restricted" => "opencode --agent yolo\r".to_string(),
            _ => "opencode\r".to_string(),
        },
        "claude" => {
            let m = if model.is_empty() {
                "claude-sonnet-4-5".to_string()
            } else {
                model.to_string()
            };
            let flags = match perm {
                "restricted" | "extreme" => " --dangerously-skip-permissions",
                _ => "",
            };
            format!("claude --model {}{}\r", m, flags)
        }
        "aider" => match perm {
            "restricted" | "extreme" => "aider --no-pretty --yes-always\r".to_string(),
            _ => "aider --no-pretty\r".to_string(),
        },
        "terminal" => String::new(), // raw shell — nothing to run
        _ => match perm {
            "extreme" => "opencode --agent yolo-extreme\r".to_string(),
            "restricted" => "opencode --agent yolo\r".to_string(),
            _ => "opencode\r".to_string(),
        },
    }
}

/// v4 — Open an agent directly via the new PTY ProcessManager (no tmux).
///
/// Replacement for `open_agent` that:
///   1. Calls ProcessManager::spawn_shell() with the requested cwd
///   2. Writes the agent's launch command into the new PTY's stdin
///   3. Returns the session_id so the UI can mount xterm.js and listen
///      on `pty-output-{id}` events
///
/// The UI subscribes to `pty-output-{session_id}` to render the agent's
/// terminal output in its grid pane.
///
/// `name` is informational only (no tmux rename involved). Stored by the
/// UI as part of the pane metadata.
///
/// `permission_mode` is optional ("safe"/"restricted"/"extreme") — older
/// callers that omit it get "safe".
#[tauri::command]
async fn open_agent_v4(
    app: tauri::AppHandle,
    pm: tauri::State<'_, core::ProcessManager>,
    name: String,
    directory: String,
    agent_type: String,
    model: String,
    permission_mode: Option<String>,
) -> Result<u32, String> {
    let dir = directory.trim().to_string();
    if dir.is_empty() {
        return Err("empty directory".to_string());
    }
    let _ = name;  // captured for future logging / future v4-side rename

    // Build the agent launch command (same as v3 open_agent, minus the
    // 'cd' part — the shell is already spawned in `dir`).
    let perm = permission_mode.unwrap_or_default();
    let start_cmd = build_agent_start_cmd_v4(&agent_type, &model, &perm);

    // Spawn shell directly in dir via the new ProcessManager.
    // No tmux involved. Cross-platform: portable-pty handles Win/Mac/Linux.
    let session_id = pm
        .spawn_shell(app, Some(dir.clone()), None)
        .map_err(|e| format!("spawn_shell failed: {}", e))?;

    // Give the shell ~100ms to print its prompt before we type into it.
    // This avoids the agent command racing the prompt and getting echoed
    // back as partial input.
    if !start_cmd.is_empty() {
        std::thread::sleep(std::time::Duration::from_millis(120));
        pm.write_stdin(session_id, &start_cmd)
            .map_err(|e| format!("write_stdin failed: {}", e))?;
    }

    Ok(session_id)
}

/// v4 — Spawn a sub-agent directly via the new PTY ProcessManager.
///
/// PTY-direct equivalent of `spawn_sub_agent`. Spawns a fresh PTY in
/// `directory`, writes the agent's launch command, and writes a
/// parent-pointer record to `/tmp/gmuxtest-sub-agents.json` so the
/// dashboard's flowchart can still discover the relationship.
///
/// Returns the new session_id.
///
/// `permission_mode` — sub-agents INHERIT their parent's permission mode:
/// the frontend passes the parent pane's recorded mode here so a yolo
/// parent gets yolo children without re-prompting the user.
#[tauri::command]
async fn spawn_sub_agent_v4(
    app: tauri::AppHandle,
    pm: tauri::State<'_, core::ProcessManager>,
    parent_pane_id: String,
    parent_name: String,
    name: String,
    directory: String,
    agent_type: String,
    model: String,
    permission_mode: Option<String>,
) -> Result<u32, String> {
    let dir = directory.trim().to_string();
    if dir.is_empty() {
        return Err("empty directory".to_string());
    }
    let win_name = format!("{}+{}", parent_name.trim(), name.trim());

    let perm = permission_mode.unwrap_or_default();
    let start_cmd = build_agent_start_cmd_v4(&agent_type, &model, &perm);

    let session_id = pm
        .spawn_shell(app, Some(dir.clone()), None)
        .map_err(|e| format!("spawn_shell failed: {}", e))?;

    if !start_cmd.is_empty() {
        std::thread::sleep(std::time::Duration::from_millis(120));
        pm.write_stdin(session_id, &start_cmd)
            .map_err(|e| format!("write_stdin failed: {}", e))?;
    }

    // Parent-pointer record (same path + shape as the v3 spawn_sub_agent)
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;
    let sa_path = "/tmp/gmuxtest-sub-agents.json";
    let existing = std::fs::read_to_string(sa_path).unwrap_or_else(|_| "{}".to_string());
    let mut map: serde_json::Value = serde_json::from_str(&existing)
        .unwrap_or_else(|_| serde_json::Value::Object(Default::default()));
    if let Some(obj) = map.as_object_mut() {
        obj.insert(
            win_name.clone(),
            serde_json::json!({
                "parent_pane_id": parent_pane_id,
                "parent_name":    parent_name,
                "v4_session_id":  session_id,
                "spawned_at":     now_ms,
                "agent_type":     agent_type,
                "model":          model,
                "permission_mode": if perm.is_empty() { "safe" } else { &perm },
            }),
        );
    }
    if let Ok(json_str) = serde_json::to_string_pretty(&map) {
        let tmp = format!("{}.tmp", sa_path);
        if std::fs::write(&tmp, &json_str).is_ok() {
            let _ = std::fs::rename(&tmp, sa_path);
        }
    }

    Ok(session_id)
}

/// v3 — Open a new tmux window and launch an AI agent tool
#[tauri::command]
fn open_agent(
    name: String,
    directory: String,
    agent_type: String,
    model: String,
    state: tauri::State<SharedState>,
) -> Result<String, String> {
    let dir = directory.trim().to_string();
    if dir.is_empty() { return Err("empty directory".to_string()); }

    let start_cmd = match agent_type.as_str() {
        "opencode" | "qalcode" => format!("cd {} && opencode", shell_escape(&dir)),
        "claude"               => {
            let m = if model.is_empty() { "claude-sonnet-4-5".to_string() } else { model.clone() };
            format!("cd {} && claude --model {}", shell_escape(&dir), m)
        },
        "aider"                => format!("cd {} && aider --no-pretty", shell_escape(&dir)),
        "terminal"             => format!("cd {}", shell_escape(&dir)),
        _                      => format!("cd {} && opencode", shell_escape(&dir)),
    };

    let win_name = if name.is_empty() {
        dir.split('/').next_back().unwrap_or("agent").to_string()
    } else {
        name.clone()
    };

    // prefix+c → new tmux window
    let new_win_cmd = "\x01c".to_string();
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(new_win_cmd.as_bytes());
        }
    }

    thread::sleep(std::time::Duration::from_millis(300));

    // Send the shell command to start the agent
    let full_cmd = format!("{}\r", start_cmd);
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            writer.write_all(full_cmd.as_bytes()).map_err(|e| e.to_string())?;
        }
    }

    // Rename the window: prefix+,
    // v3.5.2 — also turn off automatic-rename so tmux doesn't immediately
    // clobber our custom name back to "fish"/"bun" when the foreground
    // process changes. We do this via the tmux command prompt prefix+:.
    thread::sleep(std::time::Duration::from_millis(250));
    let rename_cmd = format!("\x01,{}\r", win_name);
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(rename_cmd.as_bytes());
        }
    }
    // After the interactive rename completes, disable automatic-rename for
    // this window so tmux doesn't overwrite our name when the shell process
    // changes (fish → bun → opencode).
    thread::sleep(std::time::Duration::from_millis(200));
    let lock_cmd = "\x01:set-window-option automatic-rename off\r".to_string();
    {
        let mut s = state.lock().unwrap();
        if let Some(writer) = &mut s.pty_writer {
            let _ = writer.write_all(lock_cmd.as_bytes());
        }
    }

    Ok(format!("opened: {} in {}", win_name, dir))
}

/// Approve a pending OpenCode permission request by POSTing to its HTTP API.
/// Falls back to sending Enter via PTY if no port/session is provided.
///
/// OpenCode permission approval endpoint (POST, no body needed):
///   POST /permission/{permission_id}/approve?directory=<cwd>
///   — or —
///   POST /session/{session_id}/permission/approve
///
/// Since OpenCode doesn't expose a dedicated approve REST endpoint in older builds,
/// we use the reliable approach: send 'y\n' to the specific pane via tmux send-keys
/// targeted at the correct window, not the PTY (which could be on a different window).
#[tauri::command]
fn approve_agent(
    port: u16,
    session_id: String,
    directory: String,
    window_index: u16,
    state: tauri::State<SharedState>,
) -> Result<(), String> {
    // Preferred: POST to OpenCode API if port is known
    if port > 0 && !session_id.is_empty() {
        let enc_dir = directory.replace(' ', "%20").replace('\'', "%27");
        let url = format!(
            "http://127.0.0.1:{}/session/{}/permission/allow?directory={}",
            port, session_id, enc_dir
        );
        let result = std::process::Command::new("curl")
            .args(["-s", "-o", "/dev/null", "-w", "%{http_code}",
                   "-X", "POST", "--max-time", "5", &url])
            .output();
        if let Ok(out) = result {
            let code = String::from_utf8_lossy(&out.stdout);
            if code.trim() == "200" || code.trim() == "204" || code.trim() == "202" {
                return Ok(());
            }
            // API didn't respond as expected — fall through to tmux send-keys
            eprintln!("[approve_agent] API returned {} — falling back to tmux send-keys", code.trim());
        }
    }

    // Fallback: send 'y' to the specific tmux window by index (not PTY)
    // This is safer than writing to the PTY which may be on a different active window
    if window_index > 0 {
        let target = format!("gmux:{}", window_index);
        let _ = std::process::Command::new("tmux")
            .args(["send-keys", "-t", &target, "y", "Enter"])
            .status();
        return Ok(());
    }

    // Last resort: write to PTY (original behavior)
    let mut s = state.lock().unwrap();
    if let Some(writer) = &mut s.pty_writer {
        writer.write_all(b"\r").map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// v3.7 — Interrupt / cancel a running agent.
///
/// Sends the equivalent of pressing **Escape** in the agent's terminal,
/// telling Claude Code / OpenCode to stop its current generation.
///
/// Tries three signals in order of preference:
///   1. **OpenCode HTTP API**: `POST /session/{id}/abort` — clean,
///      tells the agent to cancel its current tool/turn cleanly.
///   2. **tmux send-keys Escape** to the specific window. Claude Code
///      listens for Esc to interrupt streaming generation.
///   3. **tmux send-keys C-c** (SIGINT) — last-resort hard interrupt
///      if Escape didn't work (e.g. agent stuck in a tool).
///
/// `pane_id` is included for v4 PTY mode (future: route through
/// ProcessManager::write_stdin with the Esc byte). Currently the
/// tmux-targeted path is the working route for v3 panes.
///
/// `force_sigint`: if true, skip the API + Esc steps and go straight
/// to Ctrl-C. Used by a "Force kill" button if added later.
#[tauri::command]
fn interrupt_agent(
    port: u16,
    session_id: String,
    directory: String,
    session_name: String,
    window_index: u16,
    pane_id: String,
    force_sigint: bool,
    state: tauri::State<SharedState>,
) -> Result<String, String> {
    let _ = pane_id; // reserved for v4 PTY route (write_stdin with 0x1B)
    let _ = state;

    // ── Path 1: OpenCode HTTP /abort ──────────────────────────────
    // Only attempt if not in force_sigint mode and we have a session.
    if !force_sigint && port > 0 && !session_id.is_empty() {
        let enc_dir = directory.replace(' ', "%20").replace('\'', "%27");
        // OpenCode 1.1+: POST /session/{id}/abort?directory=...
        let url = format!(
            "http://127.0.0.1:{}/session/{}/abort?directory={}",
            port, session_id, enc_dir
        );
        let result = std::process::Command::new("curl")
            .args([
                "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "-X", "POST", "--max-time", "3", &url,
            ])
            .output();
        if let Ok(out) = result {
            let code = String::from_utf8_lossy(&out.stdout);
            let c = code.trim();
            if c == "200" || c == "204" || c == "202" {
                eprintln!("[interrupt_agent] API /abort ok (HTTP {})", c);
                return Ok(format!("aborted via API (HTTP {})", c));
            }
            eprintln!("[interrupt_agent] API /abort returned {} — falling through to tmux", c);
        }
    }

    // ── Path 2: tmux send-keys Escape ─────────────────────────────
    // Target the specific tmux window using its session name (not hardcoded
    // 'gmux' as approve_agent did — works across multiple sessions).
    let sess = if session_name.trim().is_empty() {
        "gmux".to_string()
    } else {
        session_name.trim().to_string()
    };
    if window_index > 0 {
        let target = format!("{}:{}", sess, window_index);
        if !force_sigint {
            // Step A: send Escape (Claude Code interrupt key)
            let res_esc = std::process::Command::new("tmux")
                .args(["send-keys", "-t", &target, "Escape"])
                .status();
            if let Ok(s) = res_esc {
                if s.success() {
                    eprintln!("[interrupt_agent] sent Esc to {}", target);
                    return Ok(format!("Esc sent to {}", target));
                }
            }
            // Esc failed — fall through to C-c
        }
        // Step B: send C-c (SIGINT) — explicit force or Esc failed
        let res_int = std::process::Command::new("tmux")
            .args(["send-keys", "-t", &target, "C-c"])
            .status();
        match res_int {
            Ok(s) if s.success() => {
                eprintln!("[interrupt_agent] sent C-c to {}", target);
                return Ok(format!("Ctrl-C sent to {}", target));
            }
            Ok(s) => return Err(format!("tmux send-keys C-c failed: {}", s)),
            Err(e) => return Err(format!("tmux not available: {}", e)),
        }
    }

    Err("no window_index — cannot route interrupt".to_string())
}

/// Reject a pending OpenCode permission request
#[tauri::command]
fn reject_agent(
    port: u16,
    session_id: String,
    directory: String,
    window_index: u16,
    state: tauri::State<SharedState>,
) -> Result<(), String> {
    if port > 0 && !session_id.is_empty() {
        let enc_dir = directory.replace(' ', "%20").replace('\'', "%27");
        let url = format!(
            "http://127.0.0.1:{}/session/{}/permission/deny?directory={}",
            port, session_id, enc_dir
        );
        let _ = std::process::Command::new("curl")
            .args(["-s", "-o", "/dev/null", "-X", "POST", "--max-time", "5", &url])
            .output();
        return Ok(());
    }
    if window_index > 0 {
        let target = format!("gmux:{}", window_index);
        let _ = std::process::Command::new("tmux")
            .args(["send-keys", "-t", &target, "n", "Enter"])
            .status();
        return Ok(());
    }
    let mut s = state.lock().unwrap();
    if let Some(writer) = &mut s.pty_writer {
        writer.write_all(b"n\r").map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// alpha.17-dev3 — Close / kill an agent and remove its pane.
///
/// Tries multiple paths in order of preference, falling through on failure:
///   1. **v4 PTY mode**: if `v4_session_id > 0`, call `ProcessManager::kill_session`
///      which sends SIGTERM with a 3s grace period then SIGKILL on the
///      process group. Cleanest path because we own the PTY directly.
///   2. **OpenCode HTTP API**: best-effort POST to `/session/{id}/abort`
///      then `/session/{id}/destroy?directory=...` so opencode tears down
///      its server-side state before we kill the terminal.
///   3. **tmux kill-window**: target `{session_name}:{window_index}` and
///      run `tmux kill-window -t <target>`. This is the v3 fallback when
///      no v4 session id is set.
///
/// All three paths are attempted in sequence — failures are logged but
/// not propagated, because the UI is going to remove the card visually
/// regardless. Returns Ok always except when ALL three paths fail.
///
/// `pane_id` is included for future routing (e.g. updating a Tauri-side
/// pane registry) but is currently unused — the actual termination is
/// dispatched purely from v4_session_id / port+session_id / tmux target.
#[tauri::command]
async fn close_agent(
    pane_id: String,
    port: u16,
    session_id: String,
    directory: String,
    session_name: String,
    window_index: u16,
    v4_session_id: u32,
    pm: tauri::State<'_, ProcessManager>,
) -> Result<String, String> {
    let _ = pane_id;
    let mut paths_tried: Vec<&'static str> = Vec::new();

    // ── Path 1: v4 PTY kill ───────────────────────────────────────
    // Call ProcessManager directly (rather than the kill_session Tauri
    // command) so we can await it without needing two Tauri State refs.
    if v4_session_id > 0 {
        paths_tried.push("v4_pty");
        match pm.inner().clone().kill_session(v4_session_id).await {
            Ok(_) => {
                eprintln!("[close_agent] killed v4 session {}", v4_session_id);
                return Ok(format!("v4 session {} killed", v4_session_id));
            }
            Err(e) => {
                eprintln!("[close_agent] v4 kill failed for {}: {:?} — falling through", v4_session_id, e);
            }
        }
    }

    // ── Path 2: OpenCode REST tear-down ───────────────────────────
    // Best-effort: abort current turn then destroy the session.
    // Even if both fail we continue to the tmux path.
    if port > 0 && !session_id.is_empty() {
        paths_tried.push("opencode_api");
        let enc_dir = directory.replace(' ', "%20").replace('\'', "%27");
        let abort_url = format!(
            "http://127.0.0.1:{}/session/{}/abort?directory={}",
            port, session_id, enc_dir
        );
        let _ = std::process::Command::new("curl")
            .args(["-s", "-o", "/dev/null", "-X", "POST", "--max-time", "3", &abort_url])
            .output();
        let destroy_url = format!(
            "http://127.0.0.1:{}/session/{}?directory={}",
            port, session_id, enc_dir
        );
        let _ = std::process::Command::new("curl")
            .args(["-s", "-o", "/dev/null", "-X", "DELETE", "--max-time", "3", &destroy_url])
            .output();
    }

    // ── Path 3: tmux kill-window ──────────────────────────────────
    // The reliable v3 fallback. Targets the specific session+window so
    // we don't accidentally nuke a different agent.
    if window_index > 0 {
        paths_tried.push("tmux_kill_window");
        let sess = if session_name.trim().is_empty() {
            "gmux".to_string()
        } else {
            session_name.trim().to_string()
        };
        let target = format!("{}:{}", sess, window_index);
        let result = std::process::Command::new("tmux")
            .args(["kill-window", "-t", &target])
            .status();
        match result {
            Ok(s) if s.success() => {
                eprintln!("[close_agent] tmux kill-window {} ok", target);
                return Ok(format!("tmux window {} killed", target));
            }
            Ok(s) => {
                eprintln!("[close_agent] tmux kill-window {} returned {}", target, s);
            }
            Err(e) => {
                eprintln!("[close_agent] tmux not available: {}", e);
            }
        }
    }

    Err(format!("close_agent: all paths failed (tried: {:?})", paths_tried))
}

/// Manually restart the backend sidecars. Called from the UI when monitor :8769
/// hasn't come up or the user wants to force a refresh.
/// Returns a JSON string with per-sidecar status.
#[tauri::command]
fn restart_backend(state: tauri::State<SharedState>) -> String {
    eprintln!("[gmux] restart_backend invoked from UI");
    // Spawn fresh sidecars — port_in_use check inside spawn_sidecars
    // will skip any that are already healthy
    spawn_sidecars(&state);
    // Wait briefly then probe ports
    thread::sleep(std::time::Duration::from_millis(500));
    let monitor_ok = port_in_use(8769);
    let voice_ok   = port_in_use(8770);
    format!(
        r#"{{"monitor":{}, "voice":{}, "monitor_url":"http://127.0.0.1:8769","voice_url":"ws://127.0.0.1:8770"}}"#,
        monitor_ok, voice_ok
    )
}

/// Check health of backend services without restarting them.
/// Returns JSON with port status.
#[tauri::command]
fn backend_health() -> String {
    let monitor_ok = port_in_use(8769);
    let voice_ok   = port_in_use(8770);
    // Check both naming variants — v4 writes /tmp/gmuxtest-pane-state.json,
    // gmux-system v3 writes /tmp/gmux-pane-state.json. Either being fresh
    // (< 10s old) means the monitor is producing output.
    let state_recent = ["/tmp/gmuxtest-pane-state.json", "/tmp/gmux-pane-state.json"]
        .iter()
        .any(|path| {
            std::fs::metadata(path)
                .ok()
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.elapsed().ok())
                .map(|d| d.as_secs() < 10)
                .unwrap_or(false)
        });
    format!(
        r#"{{"monitor":{}, "voice":{}, "state_fresh":{}}}"#,
        monitor_ok, voice_ok, state_recent
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// alpha.17 — Session restore commands
// ─────────────────────────────────────────────────────────────────────────────

/// Return the contents of the durable session manifest as a JSON string.
/// The manifest is written every 30s by session_restore.py --daemon.
/// Returns "[]" if the file doesn't exist yet (first launch before any
/// agents have been saved).
#[tauri::command]
fn list_saved_sessions() -> String {
    let home = match std::env::var("HOME") {
        Ok(h) => h,
        Err(_) => return "[]".to_string(),
    };
    let xdg_data = std::env::var("XDG_DATA_HOME")
        .unwrap_or_else(|_| format!("{home}/.local/share"));
    let manifest_path = std::path::Path::new(&xdg_data)
        .join("gmuxtest")
        .join("session_manifest.json");

    if !manifest_path.exists() {
        return "[]".to_string();
    }

    match std::fs::read_to_string(&manifest_path) {
        Ok(s) => {
            // The file is a dict keyed by pane_id. Convert to a sorted list
            // so the UI can display entries in a predictable order.
            match serde_json::from_str::<serde_json::Value>(&s) {
                Ok(serde_json::Value::Object(map)) => {
                    let mut entries: Vec<serde_json::Value> = map.into_values().collect();
                    // Sort by snapshot_ts descending (newest first)
                    entries.sort_by(|a, b| {
                        let ta = a.get("snapshot_ts").and_then(|v| v.as_f64()).unwrap_or(0.0);
                        let tb = b.get("snapshot_ts").and_then(|v| v.as_f64()).unwrap_or(0.0);
                        tb.partial_cmp(&ta).unwrap_or(std::cmp::Ordering::Equal)
                    });
                    serde_json::to_string(&entries).unwrap_or_else(|_| "[]".to_string())
                }
                _ => s, // return as-is if it's already an array or can't parse
            }
        }
        Err(e) => {
            log::warn!("list_saved_sessions: failed to read manifest: {}", e);
            "[]".to_string()
        }
    }
}

/// Restore (resume) a single saved agent session.
///
/// Steps:
///   1. Read the manifest entry for `pane_id`.
///   2. Check if the tmux window still exists (via `tmux list-windows`).
///   3. If YES  → focus the window (the agent may still be alive).
///   4. If NO   → spawn a new agent via `open_agent_v4`, then after a short
///      delay send `/resume` via `send_to_agent` so claude-code picks up its
///      previous session from its internal history.
///
/// Returns a brief diagnostic string (shown to the user as a toast).
#[tauri::command]
fn restore_session(pane_id: String, app: tauri::AppHandle) -> String {
    // ── 1. Read manifest entry ────────────────────────────────────────────
    let home = std::env::var("HOME").unwrap_or_default();
    let xdg_data = std::env::var("XDG_DATA_HOME")
        .unwrap_or_else(|_| format!("{home}/.local/share"));
    let manifest_path = std::path::Path::new(&xdg_data)
        .join("gmuxtest")
        .join("session_manifest.json");

    let manifest_str = match std::fs::read_to_string(&manifest_path) {
        Ok(s) => s,
        Err(_) => return "restore_failed: no manifest file".to_string(),
    };

    let manifest: serde_json::Value = match serde_json::from_str(&manifest_str) {
        Ok(v) => v,
        Err(_) => return "restore_failed: manifest parse error".to_string(),
    };

    let entry = match manifest.get(&pane_id) {
        Some(e) => e.clone(),
        None => return format!("restore_failed: pane {} not in manifest", pane_id),
    };

    let win_name = entry.get("window_name").and_then(|v| v.as_str()).unwrap_or("agent").to_string();
    let working_dir = entry.get("working_dir").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let model = entry.get("model").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let tmux_session = entry.get("tmux_session").and_then(|v| v.as_str()).unwrap_or("gmuxtest").to_string();
    let tmux_window = entry.get("tmux_window").and_then(|v| v.as_i64()).unwrap_or(0);

    // ── 2. Check if tmux window still exists ─────────────────────────────
    let window_alive = std::process::Command::new("tmux")
        .args(["list-windows", "-t", &tmux_session, "-F", "#{window_index}"])
        .output()
        .map(|o| {
            let out = String::from_utf8_lossy(&o.stdout);
            out.lines().any(|l| l.trim() == tmux_window.to_string().as_str())
        })
        .unwrap_or(false);

    if window_alive {
        // ── 3. Focus existing window ─────────────────────────────────────
        let _ = std::process::Command::new("tmux")
            .args(["select-window", "-t", &format!("{}:{}", tmux_session, tmux_window)])
            .status();
        return format!("restore_ok: focused existing window {}:{} ({})", tmux_session, tmux_window, win_name);
    }

    // ── 4. Respawn + send /resume ─────────────────────────────────────────
    // Re-use the existing open_agent_v4 logic by calling the core process-
    // manager path directly. We emit a Tauri event that the UI handles the
    // same way as clicking "+ New agent".
    let respawn_payload = serde_json::json!({
        "name": win_name,
        "directory": working_dir,
        "model": model,
        "restore_pane_id": pane_id,
        "send_resume": true,
    });

    // Notify the main window so it can open the new-agent modal pre-filled
    // OR (better UX) emit a "restore-session" event that the JS handles
    // by calling open_agent_v4 directly.
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.emit("gmux-restore-session", respawn_payload.to_string());
    }

    format!(
        "restore_respawning: {} in {} (model: {}) — sent resume event to UI",
        win_name, working_dir, model
    )
}

/// v4 — Return the app version string for display in the UI topbar.
/// Reads the `CARGO_PKG_VERSION` env var (set at compile time by Cargo)
/// and combines with the git tag if available at build time.
///
/// Returns a string like:  `0.1.0 · v4.0.0-alpha.6`
/// or just `0.1.0` if no git tag was detected.
///
/// Note: GIT_VERSION is set by build.rs at compile time so the binary
/// has a stable version string and doesn't need git at runtime.
#[tauri::command]
fn app_version() -> String {
    let pkg = env!("CARGO_PKG_VERSION");
    // GIT_VERSION is set by build.rs if available; otherwise "unknown".
    let git = option_env!("GMUX_GIT_TAG").unwrap_or("");
    if git.is_empty() {
        pkg.to_string()
    } else {
        format!("{} · {}", pkg, git)
    }
}

/// v4 — Return the build timestamp (UTC ISO-8601) of this binary.
/// Used by the UI to show "you're looking at a build from X" so users
/// can confirm a hot-reload picked up their changes.
#[tauri::command]
fn app_build_time() -> String {
    option_env!("GMUX_BUILD_TIME").unwrap_or("unknown").to_string()
}

/// List recent OpenCode sessions from the local SQLite DB (uses sqlite3 CLI)
#[tauri::command]
fn get_opencode_sessions() -> String {
    let home = std::env::var("HOME").unwrap_or_default();
    let db_path = format!("{}/.local/share/opencode/opencode.db", home);

    let result = std::process::Command::new("sqlite3")
        .args([
            &db_path,
            "-json",
            "SELECT id, title, updated FROM session ORDER BY updated DESC LIMIT 20",
        ])
        .output();

    match result {
        Ok(out) if out.status.success() =>
            String::from_utf8_lossy(&out.stdout).to_string(),
        _ => "[]".to_string(),
    }
}

// ── App entry point ───────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let shared: SharedState = Arc::new(Mutex::new(AppState::new()));

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(shared.clone())
        // v4 — register the new cross-platform PTY manager alongside the
        // legacy single-PTY state. Both coexist until the UI switches over.
        .manage(ProcessManager::new())
        .invoke_handler(tauri::generate_handler![
            // legacy v3 commands (still default — see V4_PTY_SWAP.md)
            pty_write,
            pty_resize,
            get_home_dir,
            get_pane_state,
            get_pane_state_v4,
            get_services,
            open_aquarium,
            hide_aquarium,
            open_dashboard,
            hide_dashboard,
            open_project,
            check_auth,
            list_providers,
            login_provider,
            logout_provider,
            list_models,
            send_to_agent,
            open_agent,
            open_agent_v4,
            spawn_sub_agent,
            spawn_sub_agent_v4,
            approve_agent,
            reject_agent,
            interrupt_agent,
            // alpha.17-dev3 — close/kill an agent + its pane
            close_agent,
            get_opencode_sessions,
            restart_backend,
            backend_health,
            // alpha.17 — session restore
            list_saved_sessions,
            restore_session,
            app_version,
            app_build_time,
            // v4 — new per-pane PTY commands (additive; opt-in from UI)
            commands::terminal::get_backend_info,
            commands::terminal::spawn_shell,
            commands::terminal::write_stdin,
            commands::terminal::resize_pty,
            commands::terminal::kill_session,
            commands::terminal::kill_all_sessions,
            commands::terminal::pty_ping,
            // v4 — Claude usage API (Anthropic /api/oauth/usage)
            commands::usage::get_claude_usage,
            // Phone pairing — generates QR + manages ~/.config/gmux/auth_tokens.json
            // (shared store with gmux-phone-bridge's bridge/auth.py).
            commands::pairing::gmux_pair_start,
            commands::pairing::gmux_pair_list,
            commands::pairing::gmux_pair_revoke,
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            let state  = shared.clone();

            // alpha.17-dev5 — Set the window icon at runtime so the taskbar
            // and alt-tab switcher show the gmux logo on X11/Wayland.
            // The bundle icons in tauri.conf.json only apply to installers;
            // for development + standalone binary runs we must call this.
            // Use include_image! macro which is the canonical Tauri v2 way.
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.set_icon(tauri::include_image!("icons/icon.png"));
            }

            // Start monitor.py if not already running
            spawn_sidecars(&state);

            // alpha.22 — start the embedded gmux HTTP API (:6310) so other
            // apps/agents can query state + control v4 PTY agents. Reuses the
            // managed ProcessManager (same live PTY sessions the UI drives) and
            // the shared ~/.config/gmux/auth_tokens.json for control auth.
            {
                let pm = app.state::<ProcessManager>().inner().clone();
                api::start(handle.clone(), std::sync::Arc::new(pm));
            }

            // PTY — short delay so the webview is ready
            let h2 = handle.clone();
            let s2 = state.clone();
            thread::spawn(move || {
                thread::sleep(std::time::Duration::from_millis(1200));
                start_pty(&h2, &s2);
            });

            // State poll thread — pushes pane state + services + ram feed to JS.
            //
            // Issue G fix: poll the state file's mtime every 250ms and emit a
            // gmux-state event the moment the file changes — this means new tmux
            // windows appear in the UI within ~250ms of monitor.py writing them,
            // instead of waiting up to 1s for the old fixed-interval tick.
            //
            // Non-state feeds (services, ram, memory, activity, files) only need
            // to refresh once per second so we still gate those on the 1s fallback.
            let h3 = handle.clone();
            thread::spawn(move || {
                let state_paths: &[&str] = &[
                    "/tmp/gmuxtest-pane-state.json",
                    "/tmp/gmux-pane-state.json",
                ];
                let mut last_state_mtime: Option<std::time::SystemTime> = None;
                let mut last_full_tick = std::time::Instant::now();
                let mut last_state_json = "{}".to_string();

                loop {
                    thread::sleep(std::time::Duration::from_millis(250));

                    // ── Check if pane-state file changed (mtime-based) ───────
                    let current_mtime = state_paths.iter().find_map(|p| {
                        std::fs::metadata(p).ok()?.modified().ok()
                    });

                    let state_changed = match (current_mtime, last_state_mtime) {
                        (Some(cur), Some(prev)) => cur != prev,
                        (Some(_), None) => true,  // file just appeared
                        _ => false,
                    };

                    if state_changed {
                        // Re-read state and emit immediately.
                        // alpha.21 — merge live v4 PTY panes in so this event
                        // never wipes them from the UI (flicker fix).
                        let new_json = state_paths.iter()
                            .find_map(|p| std::fs::read_to_string(p).ok())
                            .unwrap_or_else(|| "{}".to_string());

                        last_state_mtime = current_mtime;
                        last_state_json = new_json.clone();

                        let merged = {
                            let pm = h3.state::<core::ProcessManager>();
                            merge_state_with_v4(&new_json, &pm)
                        };
                        for label in &["main", "dashboard", "aquarium"] {
                            if let Some(win) = h3.get_webview_window(label) {
                                let _ = win.emit("gmux-state", &merged);
                            }
                        }
                    }

                    // ── Full tick (1 Hz): emit all non-state feeds ───────────
                    // Only run once per second even though we poll at 4 Hz.
                    if last_full_tick.elapsed() >= std::time::Duration::from_secs(1) {
                        last_full_tick = std::time::Instant::now();

                        // Re-emit state even if unchanged (keeps heartbeat alive)
                        let state_json = if last_state_json != "{}" {
                            last_state_json.clone()
                        } else {
                            state_paths.iter()
                                .find_map(|p| std::fs::read_to_string(p).ok())
                                .unwrap_or_else(|| "{}".to_string())
                        };

                        let svc_json = std::fs::read_to_string("/tmp/gmuxtest-services.json")
                            .or_else(|_| std::fs::read_to_string("/tmp/gmux-services.json"))
                            .unwrap_or_else(|_| "{}".to_string());
                        let ram_json = std::fs::read_to_string("/tmp/ram_tracker_agents.json")
                            .unwrap_or_else(|_| "{}".to_string());
                        let mem_json = std::fs::read_to_string("/tmp/gmuxtest-memory.json")
                            .or_else(|_| std::fs::read_to_string("/tmp/gmux-memory.json"))
                            .unwrap_or_else(|_| "{}".to_string());
                        let act_json = std::fs::read_to_string("/tmp/gmuxtest-activity.json")
                            .or_else(|_| std::fs::read_to_string("/tmp/gmux-activity.json"))
                            .unwrap_or_else(|_| "[]".to_string());
                        let files_json = std::fs::read_to_string("/tmp/gmuxtest-files.json")
                            .or_else(|_| std::fs::read_to_string("/tmp/gmux-files.json"))
                            .unwrap_or_else(|_| "{}".to_string());

                        // alpha.21 — heartbeat also carries merged v4 panes
                        let merged_state = {
                            let pm = h3.state::<core::ProcessManager>();
                            merge_state_with_v4(&state_json, &pm)
                        };
                        for label in &["main", "dashboard", "aquarium"] {
                            if let Some(win) = h3.get_webview_window(label) {
                                let _ = win.emit("gmux-state",    &merged_state);
                                let _ = win.emit("gmux-services", &svc_json);
                                let _ = win.emit("gmux-ram",      &ram_json);
                                let _ = win.emit("memory-update", &mem_json);
                                let _ = win.emit("activity-tick", &act_json);
                                let _ = win.emit("files-update",  &files_json);
                            }
                        }
                    }
                }
            });

            let _ = setup_shortcuts(&handle);

            // First-launch detection — stored in ~/.config/gmuxtest/
            let marker = format!(
                "{}/.config/gmuxtest/.launched",
                std::env::var("HOME").unwrap_or_default()
            );
            let first = !std::path::Path::new(&marker).exists();
            if let Some(win) = handle.get_webview_window("main") {
                let _ = win.emit("first-launch", first);
            }
            if first {
                let dir = format!("{}/.config/gmuxtest", std::env::var("HOME").unwrap_or_default());
                let _ = std::fs::create_dir_all(&dir);
                let _ = std::fs::write(marker, "1");
            }

            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // Window closed — trigger a gmux session save so the current
                // layout survives reboot.  Fire-and-forget: we don't block shutdown.
                let home = std::env::var("HOME").unwrap_or_default();
                // Search order mirrors find_gmux_script: gmux_v4 first, then gmux-system.
                let candidates = [
                    format!("{}/projects/gmux_v4/backend/session/session_restore.py", home),
                    format!("{}/projects/gmux-system/backend/session/session_restore.py", home),
                ];
                if let Some(script) = candidates.iter().find(|p| std::path::Path::new(p).exists()) {
                    let _ = std::process::Command::new("python3.11")
                        .args([script.as_str(), "--save-names", "--session", "gmux"])
                        .spawn();
                    // Also trigger resurrect save via the helper script
                    let resurrect_save = format!(
                        "{}/.tmux/plugins/tmux-resurrect/scripts/save.sh",
                        home
                    );
                    if std::path::Path::new(&resurrect_save).exists() {
                        let _ = std::process::Command::new("tmux")
                            .args(["run-shell", &resurrect_save])
                            .spawn();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error running gmuxtest");
}

// ── PTY ───────────────────────────────────────────────────────────────────────

fn detect_tmux_session() -> String {
    if let Ok(s) = std::env::var("GMUX_ATTACH_SESSION") {
        if !s.is_empty() { return s; }
    }
    if let Ok(out) = Command::new("tmux")
        .args(["list-sessions", "-F", "#{session_last_attached} #{session_name}"])
        .output()
    {
        if let Ok(text) = String::from_utf8(out.stdout) {
            let mut rows: Vec<(u64, String)> = text.lines()
                .filter_map(|l| {
                    let mut p = l.splitn(2, ' ');
                    let ts   = p.next()?.parse::<u64>().ok()?;
                    let name = p.next()?.trim().to_string();
                    if name.is_empty() { return None; }
                    Some((ts, name))
                })
                .collect();
            rows.sort_by(|a, b| b.0.cmp(&a.0));
            if let Some((_, name)) = rows.into_iter().next() {
                eprintln!("[gmuxtest] Auto-detected session: '{name}'");
                return name;
            }
        }
    }
    eprintln!("[gmuxtest] No session found, using 'gmux'");
    "gmux".to_string()
}

fn start_pty(app: &AppHandle, state: &SharedState) {
    // v4 — Skip the legacy tmux PTY attach when:
    //   1. user opted into v4 PTY mode via env var (GMUX_V4_PTY=1), OR
    //   2. tmux is not installed on the host (cross-platform safe).
    //
    // In both cases we leave AppState.pty_writer = None. The legacy
    // open_agent / open_project / spawn_sub_agent commands that write
    // tmux prefix-c keystrokes will silently no-op (they all guard with
    // `if let Some(writer)` already). Users on the new path should be
    // using open_agent_v4 etc., which spawn fresh PTYs via the
    // ProcessManager — completely independent of this function.
    if std::env::var("GMUX_V4_PTY").as_deref() == Ok("1") {
        eprintln!("[gmuxtest] GMUX_V4_PTY=1 — skipping legacy tmux PTY attach. \
                   Use open_agent_v4 / spawn_sub_agent_v4 commands instead.");
        return;
    }
    if which::which("tmux").is_err() {
        eprintln!("[gmuxtest] tmux not found on PATH — skipping legacy PTY attach. \
                   v4 PTY mode is enabled by default; new agents will use \
                   ProcessManager (open_agent_v4).");
        return;
    }

    let session = detect_tmux_session();
    eprintln!("[gmuxtest] Attaching PTY to session '{session}'");

    let pty_system = native_pty_system();
    let pair = match pty_system.openpty(PtySize { rows:40, cols:200, pixel_width:0, pixel_height:0 }) {
        Ok(p)  => p,
        Err(e) => { eprintln!("[gmuxtest] PTY open failed: {e}"); return; }
    };

    let mut cmd = CommandBuilder::new("tmux");
    cmd.args(["new-session", "-A", "-s", &session]);

    let child = match pair.slave.spawn_command(cmd) {
        Ok(c)  => c,
        Err(e) => { eprintln!("[gmuxtest] tmux spawn failed: {e}"); return; }
    };
    eprintln!("[gmuxtest] tmux PID {}", child.process_id().unwrap_or(0));

    let reader = match pair.master.try_clone_reader() {
        Ok(r)  => r,
        Err(e) => { eprintln!("[gmuxtest] PTY reader failed: {e}"); return; }
    };

    {
        let mut s = state.lock().unwrap();
        s.pty_writer = Some(pair.master.take_writer().unwrap());
        s.pty_master = Some(pair.master);
    }
    let _ = child;

    let handle = app.clone();
    let mut reader: Box<dyn Read + Send> = reader;

    thread::spawn(move || {
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0)  => break,
                Ok(n)  => {
                    let data = String::from_utf8_lossy(&buf[..n]).into_owned();
                    if let Some(w) = handle.get_webview_window("main") {
                        let _ = w.emit("pty-data", &data);
                    }
                    if let Some(w) = handle.get_webview_window("aquarium") {
                        if w.is_visible().unwrap_or(false) {
                            let _ = w.emit("pty-tick", ());
                        }
                    }
                }
                Err(e) => { eprintln!("[gmuxtest] PTY read: {e}"); break; }
            }
        }
        eprintln!("[gmuxtest] PTY closed");
    });
}

// ── Sidecars ──────────────────────────────────────────────────────────────────

fn port_in_use(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

/// Find a Python sidecar script by name. Searches in priority order:
///   1. gmux-system (consolidated)              — production install location
///   2. gmuxtest                                — dev sandbox
///   3. gmux                                    — legacy / fallback
///
/// Returns the first existing path, or None if the script can't be located.
fn find_gmux_script(name: &str) -> Option<PathBuf> {
    let home = std::env::var("HOME").unwrap_or_default();
    // monitor.py + session_restore.py live under status/
    // gmux_voice_daemon.py lives under voice/
    //
    // Search order (highest priority first):
    //   1. gmux_v4   — this repo's own backend (used when running from source)
    //   2. gmux-system — consolidated install / stable reference
    //   3. Legacy paths (gmuxtest, gmux) — kept for backward compat on old setups
    [
        // gmux_v4 — this repo (highest priority — always prefer our own copy)
        PathBuf::from(&home).join(format!("projects/gmux_v4/backend/status/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux_v4/backend/voice/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux_v4/backend/session/{name}")),
        // gmux-system (consolidated, stable install location)
        PathBuf::from(&home).join(format!("projects/gmux-system/backend/status/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux-system/backend/voice/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux-system/backend/session/{name}")),
        // Legacy paths — kept for backward compat on old setups
        PathBuf::from(&home).join(format!("projects/gmuxtest/src-py/status/{name}")),
        PathBuf::from(&home).join(format!("projects/gmuxtest/src-py/voice/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux/src/status/{name}")),
        PathBuf::from(&home).join(format!("projects/gmux/src/voice/{name}")),
    ]
    .into_iter()
    .find(|p| p.exists())
}

/// Log directory for sidecar output. Ensures it exists before any spawn.
/// Uses /tmp because logs are ephemeral and only useful for debugging.
fn sidecar_log_dir() -> PathBuf {
    let dir = PathBuf::from("/tmp");
    let _ = std::fs::create_dir_all(&dir);
    dir
}

/// Spawn a sidecar Python script with stdout+stderr redirected to /tmp/<label>.log
/// Returns the child process if spawn succeeds.
fn spawn_one_sidecar(label: &str, script_path: &Path, args: &[&str]) -> Option<std::process::Child> {
    use std::process::Stdio;
    let log_path = sidecar_log_dir().join(format!("{}.log", label));
    let log_file = std::fs::File::create(&log_path).ok()?;
    let log_err  = log_file.try_clone().ok()?;

    let mut cmd = Command::new("python3.11");
    cmd.arg(script_path);
    for arg in args { cmd.arg(arg); }
    cmd.stdout(Stdio::from(log_file));
    cmd.stderr(Stdio::from(log_err));
    cmd.stdin(Stdio::null());

    match cmd.spawn() {
        Ok(c)  => {
            eprintln!("[gmux] {} started — PID {} — log {}", label, c.id(), log_path.display());
            Some(c)
        }
        Err(e) => {
            eprintln!("[gmux] {} spawn failed: {} — log {}", label, e, log_path.display());
            None
        }
    }
}

/// Try to start a sidecar, retrying once after 800ms if it exits immediately.
/// Returns true if a long-running process is now alive.
fn start_with_retry(
    label: &str,
    script_path: &Path,
    args: &[&str],
    port: Option<u16>,
    sidecars: &mut Vec<std::process::Child>,
) -> bool {
    // Attempt 1
    if let Some(mut child) = spawn_one_sidecar(label, script_path, args) {
        // Wait 1.5s — if it died, that's a config problem (missing deps etc)
        thread::sleep(std::time::Duration::from_millis(1500));
        match child.try_wait() {
            Ok(Some(status)) => {
                eprintln!("[gmux] {} died immediately (exit {}). Check /tmp/{}.log", label, status, label);
                // Don't retry — the issue will repeat. Surface error to user.
                return false;
            }
            Ok(None) => {
                // Still running. Verify port if we expect one.
                if let Some(p) = port {
                    // Give the python script up to 4s to bind (faster-whisper model load)
                    for _ in 0..40 {
                        thread::sleep(std::time::Duration::from_millis(100));
                        if port_in_use(p) {
                            eprintln!("[gmux] {} listening on :{}", label, p);
                            sidecars.push(child);
                            return true;
                        }
                    }
                    eprintln!("[gmux] {} did not bind :{} within 4s — process still alive, may need more time", label, p);
                }
                sidecars.push(child);
                return true;
            }
            Err(e) => {
                eprintln!("[gmux] {} wait failed: {}", label, e);
                return false;
            }
        }
    }
    false
}

fn spawn_sidecars(state: &SharedState) {
    struct Spec {
        script:  &'static str,
        label:   &'static str,
        port:    Option<u16>,
        args:    &'static [&'static str],
    }
    // Sidecars listed in startup order. monitor.py first (state file),
    // then voice (independent), then session_restore (background save loop).
    let specs: &[Spec] = &[
        Spec { script: "monitor.py",           label: "gmux-monitor", port: Some(8769), args: &[] },
        Spec { script: "gmux_voice_daemon.py", label: "gmux-voice",   port: Some(8770), args: &["--model", "tiny", "--port", "8770"] },
        Spec { script: "session_restore.py",   label: "gmux-saver",   port: None,        args: &["--daemon"] },
    ];

    let mut s = state.lock().unwrap();
    for spec in specs {
        // Skip if port is already bound (sidecar from a previous run / system service)
        if let Some(p) = spec.port {
            if port_in_use(p) {
                eprintln!("[gmux] {} :{} already bound — assuming healthy, skip spawn", spec.label, p);
                continue;
            }
        }
        // Locate the script
        let Some(path) = find_gmux_script(spec.script) else {
            eprintln!("[gmux] {} script '{}' not found in any search path — skipping", spec.label, spec.script);
            continue;
        };
        eprintln!("[gmux] starting {} from {}", spec.label, path.display());
        let ok = start_with_retry(spec.label, &path, spec.args, spec.port, &mut s.sidecars);
        if !ok {
            eprintln!("[gmux] {} startup failed — UI will run without it (statusbar will show '● mock' or '● live (poll)')", spec.label);
        }
    }
}

// ── Global shortcuts ──────────────────────────────────────────────────────────

fn setup_shortcuts(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let alt_g = Shortcut::new(Some(Modifiers::ALT), Code::KeyG);
    let _ = app.global_shortcut().unregister(alt_g);
    let _ = app.global_shortcut().on_shortcut(alt_g, |h, _, e| {
        if e.state == ShortcutState::Pressed {
            if let Some(w) = h.get_webview_window("main") { let _ = w.emit("gesture-toggle", ()); }
        }
    });

    let voice_key = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
    let _ = app.global_shortcut().unregister(voice_key);
    let _ = app.global_shortcut().on_shortcut(voice_key, |h, _, e| {
        if e.state == ShortcutState::Pressed {
            if let Some(w) = h.get_webview_window("main") { let _ = w.emit("voice-toggle", ()); }
        }
    });

    // Ctrl+Alt+D (Linux/Windows) / Cmd+Opt+D (macOS) — toggle the dashboard window.
    // On macOS, users expect Cmd (META) instead of Ctrl. Tauri's Modifiers::META
    // maps to the Command key on macOS and the Windows/Super key on Linux/Windows.
    // We branch at compile time using cfg! so no runtime overhead on either platform.
    let dash_modifiers = if cfg!(target_os = "macos") {
        Modifiers::META | Modifiers::ALT
    } else {
        Modifiers::CONTROL | Modifiers::ALT
    };
    let dash_key = Shortcut::new(Some(dash_modifiers), Code::KeyD);
    let _ = app.global_shortcut().unregister(dash_key);
    let _ = app.global_shortcut().on_shortcut(dash_key, |h, _, e| {
        if e.state == ShortcutState::Pressed {
            // v3.8.3 — match the open_dashboard command: explicitly set
            // size + centre + unminimize, NOT just .show() — otherwise the
            // WebKitGTK + Wayland combo creates the window at 10×10 px.
            if let Some(w) = h.get_webview_window("dashboard") {
                if w.is_visible().unwrap_or(false) {
                    let _ = w.hide();
                } else {
                    let _ = w.unminimize();
                    let _ = w.unmaximize();
                    let _ = w.set_size(tauri::Size::Logical(
                        tauri::LogicalSize { width: 1600.0, height: 1000.0 }
                    ));
                    let _ = w.center();
                    let _ = w.show();
                    let _ = w.set_focus();
                }
            }
        }
    });

    // (No global shortcut for aquarium — that lives inside the dashboard now)

    Ok(())
}
