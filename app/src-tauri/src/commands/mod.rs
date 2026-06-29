//! Tauri command modules for gmux-v4.
//!
//! New commands added during the v4 PTY swap (see docs/V4_PTY_SWAP.md).
//! Legacy v3 commands (open_agent, open_project, send_to_agent, etc.)
//! remain in `lib.rs` until they're migrated to use ProcessManager.

pub mod terminal;
pub mod usage;

// Phone pairing — companion to gmux-phone-bridge.
// See commands/pairing.rs and ~/projects/gmux_v4/gmux_phone_bridge_system/.
pub mod pairing;
