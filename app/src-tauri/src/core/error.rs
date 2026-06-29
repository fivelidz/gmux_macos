//! PTY error types.
//!
//! Originally from https://github.com/its-maestro-baby/maestro
//! commit a10500d, MIT licensed by Maestro contributors.
//! Adapted for gmux-v4 by fivelidz (no functional changes).

use serde::Serialize;
use std::fmt;

/// Discriminant for PTY errors, serialized to the frontend for programmatic
/// error handling (e.g., distinguishing "session gone" from "write failed").
#[derive(Debug, Clone, Serialize)]
pub enum PtyErrorCode {
    SpawnFailed,
    SessionNotFound,
    WriteFailed,
    ResizeFailed,
    KillFailed,
    IdOverflow,
}

/// Structured PTY error with a machine-readable code and human-readable message.
///
/// Serialized as JSON to the Tauri frontend. Implements `std::error::Error`
/// so it can be used with `?` in command handlers.
#[derive(Debug, Clone, Serialize)]
pub struct PtyError {
    pub code: PtyErrorCode,
    pub message: String,
}

impl fmt::Display for PtyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}: {}", self.code, self.message)
    }
}

impl std::error::Error for PtyError {}

impl PtyError {
    pub fn spawn_failed(msg: impl Into<String>) -> Self {
        Self { code: PtyErrorCode::SpawnFailed, message: msg.into() }
    }
    pub fn session_not_found(id: u32) -> Self {
        Self { code: PtyErrorCode::SessionNotFound, message: format!("Session {} not found", id) }
    }
    pub fn write_failed(msg: impl Into<String>) -> Self {
        Self { code: PtyErrorCode::WriteFailed, message: msg.into() }
    }
    pub fn resize_failed(msg: impl Into<String>) -> Self {
        Self { code: PtyErrorCode::ResizeFailed, message: msg.into() }
    }
    #[allow(dead_code)]
    pub fn kill_failed(msg: impl Into<String>) -> Self {
        Self { code: PtyErrorCode::KillFailed, message: msg.into() }
    }
    pub fn id_overflow() -> Self {
        Self {
            code: PtyErrorCode::IdOverflow,
            message: "Session ID counter overflowed u32::MAX".to_string(),
        }
    }
}
