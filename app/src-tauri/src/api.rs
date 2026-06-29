//! Embedded gmux HTTP API (alpha.22)
//!
//! A small axum server, started inside the Tauri app, so **other apps and
//! agents** can query gmux state and control its agents over HTTP — without
//! tmux, without the Python phone bridge, and seeing the live v4 PTY agents
//! the desktop app owns directly.
//!
//! Port: `:6310` (override with `GMUX_API_PORT`). Bind: `127.0.0.1` by default
//! (override with `GMUX_API_BIND=0.0.0.0` to expose on the LAN — only do this
//! behind Tailscale/VPN; control routes require a token).
//!
//! ## Auth model
//! Reuses the SAME token store as the phone bridge + desktop pairing:
//! `~/.config/gmux/auth_tokens.json`. A token issued by the desktop UI's
//! "Pair device" flow authenticates here too.
//!  - **Read** routes (`GET`) are open on localhost by default (set
//!    `GMUX_API_REQUIRE_AUTH=1` to require a token for reads too).
//!  - **Control** routes (`POST`) ALWAYS require `Authorization: Bearer <token>`.
//!
//! ## Routes
//!  GET  /api/health                      → { ok, service, version, agents }
//!  GET  /api/state                       → full merged pane-state JSON (v4 + file)
//!  GET  /api/agents                      → compact agent list
//!  GET  /api/agent/:id                   → one pane's full record
//!  GET  /api/usage                       → Claude usage (5h / 7d / sonnet / opus)
//!  POST /api/agent/spawn  {directory,agent_type?,model?,permission_mode?,prompt?}
//!                                        → { ok, session_id }
//!  POST /api/agent/:id/send  {text}      → { ok }   (writes text + Enter to PTY)
//!  POST /api/agent/:id/key   {key}       → { ok }   (Enter|Escape|C-c|Up|Down|y|n)
//!  POST /api/agent/:id/kill              → { ok }
//!
//! `:id` accepts either a v4 session id (`123` or `v4-123`) for PTY agents.

use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::AppHandle;
use tower_http::cors::CorsLayer;

use crate::core::ProcessManager;

#[derive(Clone)]
pub struct ApiState {
    pub app: AppHandle,
    pub pm: Arc<ProcessManager>,
}

const DEFAULT_PORT: u16 = 6310;

/// Spawn the API server on a background tokio task. Never blocks app startup;
/// logs and gives up quietly if the port is taken.
pub fn start(app: AppHandle, pm: Arc<ProcessManager>) {
    let port = std::env::var("GMUX_API_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .unwrap_or(DEFAULT_PORT);
    let bind = std::env::var("GMUX_API_BIND").unwrap_or_else(|_| "127.0.0.1".to_string());
    let addr = format!("{bind}:{port}");

    let state = ApiState { app, pm };

    tauri::async_runtime::spawn(async move {
        let router = Router::new()
            .route("/api/health", get(health))
            .route("/api/state", get(get_state))
            .route("/api/agents", get(list_agents))
            .route("/api/agent/:id", get(get_agent))
            .route("/api/usage", get(usage))
            .route("/api/agent/spawn", post(spawn_agent))
            .route("/api/agent/:id/send", post(send_text))
            .route("/api/agent/:id/key", post(send_key))
            .route("/api/agent/:id/kill", post(kill_agent))
            .layer(CorsLayer::permissive())
            .with_state(state);

        match tokio::net::TcpListener::bind(&addr).await {
            Ok(listener) => {
                log::info!("[gmux-api] listening on http://{addr}");
                if let Err(e) = axum::serve(listener, router).await {
                    log::warn!("[gmux-api] server error: {e}");
                }
            }
            Err(e) => {
                log::warn!("[gmux-api] could not bind {addr} ({e}) — API disabled this run");
            }
        }
    });
}

// ── Auth ──────────────────────────────────────────────────────────────────

/// Read the shared token store and check a Bearer token against it.
fn token_valid(token: &str) -> bool {
    if token.is_empty() {
        return false;
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let path = std::path::PathBuf::from(home).join(".config/gmux/auth_tokens.json");
    let Ok(text) = std::fs::read_to_string(&path) else {
        return false;
    };
    let Ok(store) = serde_json::from_str::<Value>(&text) else {
        return false;
    };
    store
        .get("tokens")
        .and_then(|t| t.as_array())
        .map(|arr| {
            arr.iter()
                .any(|rec| rec.get("token").and_then(|v| v.as_str()) == Some(token))
        })
        .unwrap_or(false)
}

fn bearer(headers: &HeaderMap) -> String {
    headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.strip_prefix("Bearer "))
        .unwrap_or("")
        .trim()
        .to_string()
}

/// Gate for control (POST) routes — always requires a valid token.
fn require_auth(headers: &HeaderMap) -> Result<(), (StatusCode, Json<Value>)> {
    if token_valid(&bearer(headers)) {
        Ok(())
    } else {
        Err((
            StatusCode::UNAUTHORIZED,
            Json(json!({"ok": false, "error": "missing or invalid Bearer token — pair a device in gmux Options to get one"})),
        ))
    }
}

/// Gate for read routes — open on localhost unless GMUX_API_REQUIRE_AUTH=1.
fn require_read_auth(headers: &HeaderMap) -> Result<(), (StatusCode, Json<Value>)> {
    if std::env::var("GMUX_API_REQUIRE_AUTH").as_deref() == Ok("1") {
        return require_auth(headers);
    }
    Ok(())
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/// Normalise an incoming id: accept "v4-123", "123", or any pane_id string.
/// Returns Some(u32) if it resolves to a v4 PTY session id.
fn v4_session_id_of(id: &str) -> Option<u32> {
    let stripped = id.strip_prefix("v4-").unwrap_or(id);
    stripped.parse::<u32>().ok()
}

fn merged_state(state: &ApiState) -> String {
    let file_json = std::fs::read_to_string("/tmp/gmuxtest-pane-state.json")
        .or_else(|_| std::fs::read_to_string("/tmp/gmux-pane-state.json"))
        .unwrap_or_else(|_| "{}".to_string());
    crate::merge_state_with_v4(&file_json, &state.pm)
}

// ── Read routes ─────────────────────────────────────────────────────────────

async fn health(State(state): State<ApiState>) -> impl IntoResponse {
    let n = state.pm.get_all_session_pids().len();
    Json(json!({
        "ok": true,
        "service": "gmux-api",
        "version": env!("CARGO_PKG_VERSION"),
        "v4_agents": n,
    }))
}

async fn get_state(
    headers: HeaderMap,
    State(state): State<ApiState>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_read_auth(&headers)?;
    let body = merged_state(&state);
    Ok(([("content-type", "application/json")], body))
}

async fn list_agents(
    headers: HeaderMap,
    State(state): State<ApiState>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_read_auth(&headers)?;
    let merged = merged_state(&state);
    let parsed: Value = serde_json::from_str(&merged).unwrap_or_else(|_| json!({}));
    let mut out = Vec::new();
    if let Some(obj) = parsed.as_object() {
        for (pid, p) in obj {
            out.push(json!({
                "pane_id":      pid,
                "window_name":  p.get("window_name"),
                "session_name": p.get("session_name"),
                "state":        p.get("state"),
                "agent_type":   p.get("agent_type"),
                "model":        p.get("model"),
                "cwd":          p.get("cwd"),
                "is_v4":        p.get("is_v4"),
                "v4_session_id":p.get("v4_session_id"),
                "todo_done":    p.get("todo_done"),
                "todo_total":   p.get("todo_total"),
            }));
        }
    }
    Ok(Json(json!({"ok": true, "count": out.len(), "agents": out})))
}

async fn get_agent(
    headers: HeaderMap,
    Path(id): Path<String>,
    State(state): State<ApiState>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_read_auth(&headers)?;
    let merged = merged_state(&state);
    let parsed: Value = serde_json::from_str(&merged).unwrap_or_else(|_| json!({}));
    // direct key, or match by v4_session_id
    if let Some(p) = parsed.get(&id) {
        return Ok(Json(json!({"ok": true, "agent": p})));
    }
    if let Some(sid) = v4_session_id_of(&id) {
        let key = format!("v4-{sid}");
        if let Some(p) = parsed.get(&key) {
            return Ok(Json(json!({"ok": true, "agent": p})));
        }
    }
    Err((
        StatusCode::NOT_FOUND,
        Json(json!({"ok": false, "error": format!("no agent '{id}'")})),
    ))
}

async fn usage(
    headers: HeaderMap,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_read_auth(&headers)?;
    match crate::commands::usage::get_claude_usage().await {
        Ok(u) => Ok(Json(json!({"ok": true, "usage": u}))),
        Err(e) => Err((
            StatusCode::BAD_GATEWAY,
            Json(json!({"ok": false, "error": e})),
        )),
    }
}

// ── Control routes ──────────────────────────────────────────────────────────

#[derive(Deserialize)]
struct SpawnReq {
    directory: String,
    #[serde(default)]
    agent_type: Option<String>,
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    permission_mode: Option<String>,
    #[serde(default)]
    prompt: Option<String>,
}

async fn spawn_agent(
    headers: HeaderMap,
    State(state): State<ApiState>,
    Json(req): Json<SpawnReq>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_auth(&headers)?;
    let dir = req.directory.trim().to_string();
    if dir.is_empty() {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "directory is required"})),
        ));
    }
    let agent_type = req.agent_type.unwrap_or_else(|| "qalcode".to_string());
    let model = req.model.unwrap_or_default();
    let perm = req.permission_mode.unwrap_or_default();
    let start_cmd = crate::build_agent_start_cmd_v4(&agent_type, &model, &perm);

    let session_id = state
        .pm
        .spawn_shell(state.app.clone(), Some(dir), None)
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": format!("spawn_shell: {e}")})),
            )
        })?;

    // Write the launch command, then optionally the first prompt.
    if !start_cmd.is_empty() {
        std::thread::sleep(std::time::Duration::from_millis(120));
        let _ = state.pm.write_stdin(session_id, &start_cmd);
    }
    if let Some(p) = req.prompt {
        let p = p.trim().to_string();
        if !p.is_empty() {
            // Give the agent TUI time to boot before delivering the prompt.
            let pm = state.pm.clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_millis(3500)).await;
                let _ = pm.write_stdin(session_id, &format!("{p}\r"));
            });
        }
    }

    Ok(Json(json!({
        "ok": true,
        "session_id": session_id,
        "pane_id": format!("v4-{session_id}"),
    })))
}

#[derive(Deserialize)]
struct SendReq {
    text: String,
}

async fn send_text(
    headers: HeaderMap,
    Path(id): Path<String>,
    State(state): State<ApiState>,
    Json(req): Json<SendReq>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_auth(&headers)?;
    let sid = v4_session_id_of(&id).ok_or((
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": "id must be a v4 session id (e.g. 'v4-12' or '12')"})),
    ))?;
    state
        .pm
        .write_stdin(sid, &format!("{}\r", req.text))
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": format!("write_stdin: {e}")})),
            )
        })?;
    Ok(Json(json!({"ok": true})))
}

#[derive(Deserialize)]
struct KeyReq {
    key: String,
}

/// Map a friendly key name to the bytes to write into the PTY.
fn key_bytes(key: &str) -> Option<&'static str> {
    match key {
        "Enter" | "enter" => Some("\r"),
        "Escape" | "escape" | "Esc" => Some("\x1b"),
        "C-c" | "ctrl-c" | "SIGINT" => Some("\x03"),
        "Up" | "up" => Some("\x1b[A"),
        "Down" | "down" => Some("\x1b[B"),
        "y" => Some("y"),
        "n" => Some("n"),
        _ => None,
    }
}

async fn send_key(
    headers: HeaderMap,
    Path(id): Path<String>,
    State(state): State<ApiState>,
    Json(req): Json<KeyReq>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_auth(&headers)?;
    let sid = v4_session_id_of(&id).ok_or((
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": "id must be a v4 session id"})),
    ))?;
    let bytes = key_bytes(&req.key).ok_or((
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": "unknown key — use Enter|Escape|C-c|Up|Down|y|n"})),
    ))?;
    state.pm.write_stdin(sid, bytes).map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": format!("write_stdin: {e}")})),
        )
    })?;
    Ok(Json(json!({"ok": true})))
}

async fn kill_agent(
    headers: HeaderMap,
    Path(id): Path<String>,
    State(state): State<ApiState>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    require_auth(&headers)?;
    let sid = v4_session_id_of(&id).ok_or((
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": "id must be a v4 session id"})),
    ))?;
    state.pm.kill_session(sid).await.map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": format!("kill_session: {e}")})),
        )
    })?;
    Ok(Json(json!({"ok": true})))
}
