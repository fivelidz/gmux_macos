//! Tauri command handlers for per-pane PTY operations.
//!
//! Patterns lifted from maestro's commands/terminal.rs (commit a10500d, MIT)
//! and trimmed to what gmux-v4 needs. Maestro shipped more (process trees,
//! pasted-image saving, status server registration) — we add those later.

use std::collections::HashMap;

use serde::Serialize;
use tauri::{AppHandle, State};

use crate::core::{BackendCapabilities, BackendType, ProcessManager, PtyError};

/// Backend information returned to the frontend.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackendInfo {
    pub backend_type: BackendType,
    pub capabilities: BackendCapabilitiesDto,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackendCapabilitiesDto {
    pub enhanced_state: bool,
    pub text_reflow: bool,
    pub kitty_graphics: bool,
    pub shell_integration: bool,
    pub backend_name: String,
}

impl From<BackendCapabilities> for BackendCapabilitiesDto {
    fn from(c: BackendCapabilities) -> Self {
        Self {
            enhanced_state: c.enhanced_state,
            text_reflow: c.text_reflow,
            kitty_graphics: c.kitty_graphics,
            shell_integration: c.shell_integration,
            backend_name: c.backend_name.to_string(),
        }
    }
}

/// Reports which terminal backend is active and its capabilities.
///
/// gmux-v4 ships with `xterm-passthrough` only. The trait abstraction
/// is here so a VT-parser backend can be added later without churn.
#[tauri::command]
pub fn get_backend_info() -> BackendInfo {
    let bt = BackendType::platform_default();
    let caps = match bt {
        BackendType::XtermPassthrough => BackendCapabilities {
            enhanced_state: false,
            text_reflow: false,
            kitty_graphics: false,
            shell_integration: false,
            backend_name: "xterm-passthrough",
        },
        BackendType::VteParser => BackendCapabilities {
            enhanced_state: true,
            text_reflow: false,
            kitty_graphics: false,
            shell_integration: false,
            backend_name: "vte-parser",
        },
    };
    BackendInfo { backend_type: bt, capabilities: caps.into() }
}

/// Spawn a login shell in a new PTY.
///
/// `cwd`: optional working directory (must exist and be a directory if set).
/// `env`: optional extra env vars (GMUX_SESSION_ID is auto-injected).
///
/// Returns the new session id. The frontend should listen on
/// `pty-output-{id}` for output.
#[tauri::command]
pub async fn spawn_shell(
    app_handle: AppHandle,
    state: State<'_, ProcessManager>,
    cwd: Option<String>,
    env: Option<HashMap<String, String>>,
) -> Result<u32, PtyError> {
    // Validate cwd if provided.
    let canonical_cwd = if let Some(ref dir) = cwd {
        let path = std::path::Path::new(dir);
        let canonical = path
            .canonicalize()
            .map_err(|e| PtyError::spawn_failed(format!("Invalid cwd '{dir}': {e}")))?;
        if !canonical.is_dir() {
            return Err(PtyError::spawn_failed(format!("cwd '{dir}' is not a directory")));
        }
        // Windows: strip the \\?\ extended-length prefix cmd.exe can't handle.
        #[cfg(windows)]
        let canonical = {
            let s = canonical.to_string_lossy();
            match s.strip_prefix(r"\\?\") {
                Some(stripped) => std::path::PathBuf::from(stripped),
                None => canonical,
            }
        };
        Some(canonical.to_string_lossy().into_owned())
    } else {
        None
    };
    let pm = state.inner().clone();
    pm.spawn_shell(app_handle, canonical_cwd, env)
}

/// Write raw bytes to the PTY stdin of a session.
/// `data` is sent verbatim — include `\r` etc. as needed.
#[tauri::command]
pub async fn write_stdin(
    state: State<'_, ProcessManager>,
    session_id: u32,
    data: String,
) -> Result<(), PtyError> {
    let pm = state.inner().clone();
    pm.write_stdin(session_id, &data)
}

/// Resize the PTY (propagates SIGWINCH to the child).
/// Rejects dimensions outside (0, 500].
#[tauri::command]
pub async fn resize_pty(
    state: State<'_, ProcessManager>,
    session_id: u32,
    rows: u16,
    cols: u16,
) -> Result<(), PtyError> {
    if rows == 0 || cols == 0 || rows > 500 || cols > 500 {
        return Err(PtyError::resize_failed("Invalid dimensions"));
    }
    let pm = state.inner().clone();
    pm.resize_pty(session_id, rows, cols)
}

/// Terminate a session (SIGTERM grace, then SIGKILL).
#[tauri::command]
pub async fn kill_session(
    state: State<'_, ProcessManager>,
    session_id: u32,
) -> Result<(), PtyError> {
    let pm = state.inner().clone();
    pm.kill_session(session_id).await
}

/// Kill every active session (used on app shutdown / hot reload).
#[tauri::command]
pub async fn kill_all_sessions(state: State<'_, ProcessManager>) -> Result<u32, PtyError> {
    let pm = state.inner().clone();
    pm.kill_all_sessions().await
}

/// Smoke-test ping command. Returns "pong" — used to verify the new
/// commands module is wired correctly before any UI work.
#[tauri::command]
pub fn pty_ping() -> &'static str {
    "pong"
}
