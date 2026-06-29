//! Cross-platform PTY core lifted from maestro (MIT, commit a10500d).
//! See individual files for per-file attribution.
//!
//! This module is **additive** alongside the legacy v3 single-PTY logic
//! that lives in `lib.rs::start_pty`. The legacy path remains the default
//! until per-pane PTY spawning is wired into the UI (`V4_PTY_SWAP.md`).

pub mod error;
pub mod process_manager;
pub mod terminal_backend;
pub mod windows_process;

pub use error::{PtyError, PtyErrorCode};
pub use process_manager::ProcessManager;
pub use terminal_backend::{BackendCapabilities, BackendType, TerminalConfig, TerminalState};
