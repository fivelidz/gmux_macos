//! Phone-pairing Tauri commands.
//!
//! Companion to the Python bridge at
//! https://github.com/fivelidz/gmux-phone-bridge — these commands read
//! and write the *same* token store (`~/.config/gmux/auth_tokens.json`)
//! that `bridge/auth.py` uses, so a token issued by the desktop UI
//! authenticates phone connections to the bridge without any extra
//! sync step.
//!
//! Token store schema (matches bridge/auth.py exactly):
//!
//! ```json
//! {
//!   "tokens": [
//!     { "token": "<64 hex chars>",
//!       "name":  "fivelidz pixel",
//!       "created":   1736000000,
//!       "last_seen": 1736003000 }
//!   ]
//! }
//! ```
//!
//! Three commands are exposed to JS:
//!   * `gmux_pair_start(name?)` — generate a fresh token if none exists
//!     for that name, return the QR-payload JSON the phone will scan.
//!   * `gmux_pair_list()` — return the paired-device list (token value
//!     omitted for safety).
//!   * `gmux_pair_revoke(name)` — remove every token associated with a
//!     given device name.
//!
//! The bridge port (6301) is hard-coded here for now; if the user has
//! overridden it via `GMUX_BRIDGE_WS_PORT` we honour that too.
//!
//! No new crate dependencies are added: we use `/dev/urandom` for
//! entropy (32 bytes → 64-hex token) and shell out to `tailscale ip -4`
//! / `hostname -I` for IP detection. That mirrors the Python side
//! one-for-one, keeping the two implementations easy to keep in sync.

use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Read;
use std::path::PathBuf;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

// ── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_WS_PORT: u16 = 6301;
const PAIR_PROTOCOL_VERSION: u32 = 1;

// ── On-disk record ───────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone, Debug)]
struct TokenRecord {
    token: String,
    name: String,
    created: u64,
    #[serde(default)]
    last_seen: Option<u64>,
}

#[derive(Serialize, Deserialize, Default, Debug)]
struct TokenStore {
    tokens: Vec<TokenRecord>,
}

fn token_store_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home).join(".config/gmux/auth_tokens.json")
}

fn load_store() -> TokenStore {
    let path = token_store_path();
    let Ok(text) = fs::read_to_string(&path) else {
        return TokenStore::default();
    };
    serde_json::from_str::<TokenStore>(&text).unwrap_or_default()
}

fn save_store(store: &TokenStore) -> Result<(), String> {
    let path = token_store_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir {parent:?}: {e}"))?;
    }
    let text =
        serde_json::to_string_pretty(store).map_err(|e| format!("json encode: {e}"))?;
    fs::write(&path, text).map_err(|e| format!("write {path:?}: {e}"))?;
    // tighten perms; if chmod fails we still succeeded at writing the file
    let _ = chmod_600(&path);
    Ok(())
}

#[cfg(unix)]
fn chmod_600(path: &std::path::Path) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
}

#[cfg(not(unix))]
fn chmod_600(_path: &std::path::Path) -> std::io::Result<()> {
    Ok(())
}

// ── Helpers ──────────────────────────────────────────────────────────────────

fn now_unix() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// 32 bytes from /dev/urandom → 64-char hex string. Matches Python's
/// `secrets.token_hex(32)`.
fn generate_hex_token() -> Result<String, String> {
    let mut buf = [0u8; 32];
    let mut f = fs::File::open("/dev/urandom")
        .map_err(|e| format!("open /dev/urandom: {e}"))?;
    f.read_exact(&mut buf)
        .map_err(|e| format!("read /dev/urandom: {e}"))?;
    Ok(buf.iter().map(|b| format!("{:02x}", b)).collect())
}

/// Tailscale → LAN → localhost. Mirrors `detect_best_ip()` in `bridge.py`.
fn detect_best_ip() -> (String, &'static str) {
    // Tailscale
    if let Ok(out) = Command::new("tailscale").args(["ip", "-4"]).output() {
        if out.status.success() {
            let ip = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if !ip.is_empty() {
                return (ip, "tailscale");
            }
        }
    }
    // LAN via hostname -I (Linux). Pick the first non-loopback token.
    if let Ok(out) = Command::new("hostname").arg("-I").output() {
        if out.status.success() {
            let raw = String::from_utf8_lossy(&out.stdout);
            if let Some(ip) = raw.split_whitespace().find(|s| !s.starts_with("127.")) {
                return (ip.to_string(), "local");
            }
        }
    }
    ("127.0.0.1".to_string(), "local")
}

fn host_name() -> String {
    Command::new("hostname")
        .output()
        .ok()
        .and_then(|o| {
            if o.status.success() {
                Some(String::from_utf8_lossy(&o.stdout).trim().to_string())
            } else {
                None
            }
        })
        .unwrap_or_else(|| "gmux-desktop".into())
}

fn bridge_ws_port() -> u16 {
    std::env::var("GMUX_BRIDGE_WS_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .or_else(|| {
            // legacy env var name still honoured by the Python side
            std::env::var("GMUX_BRIDGE_PORT")
                .ok()
                .and_then(|s| s.parse::<u16>().ok())
        })
        .unwrap_or(DEFAULT_WS_PORT)
}

// ── Public-facing return types ──────────────────────────────────────────────

/// The JSON payload encoded into the QR code — schema matches
/// `gmux-phone/docs/BACKEND_CONTRACT.md` (frozen v1).
#[derive(Serialize, Debug)]
pub struct PairPayload {
    #[serde(rename = "type")]
    pub kind: &'static str,
    pub version: u32,
    pub host: String,
    pub port: u16,
    pub token: String,
    pub name: String,
    pub transport: &'static str,
    pub relay_url: Option<String>,
}

/// Safe view of a paired device — `token` is deliberately omitted so a
/// rogue webview can't read it back.
#[derive(Serialize, Debug)]
pub struct PairedDevice {
    pub name: String,
    pub created: u64,
    pub last_seen: Option<u64>,
    /// First 8 hex chars of the token, for visual confirmation when
    /// revoking. Never enough on its own to authenticate.
    pub token_preview: String,
}

// ── Tauri commands ───────────────────────────────────────────────────────────

/// Generate (or look up) a token for the given device name and return
/// the full QR payload. If a token with the same name already exists
/// we reuse it — pairing is idempotent so showing the QR twice produces
/// the same code, which keeps existing phones working.
///
/// Pass `name = ""` (or omit it on the JS side) for the default unnamed
/// device — useful for the very first pair.
#[tauri::command]
pub fn gmux_pair_start(name: Option<String>) -> Result<PairPayload, String> {
    let name = name.unwrap_or_default();
    let device_name = if name.trim().is_empty() {
        "default".to_string()
    } else {
        name.trim().to_string()
    };

    let mut store = load_store();

    // Idempotent: if there's already a token for this name, reuse it.
    let existing = store
        .tokens
        .iter()
        .find(|t| t.name == device_name)
        .cloned();

    let token = if let Some(rec) = existing {
        rec.token
    } else {
        let new_token = generate_hex_token()?;
        store.tokens.push(TokenRecord {
            token: new_token.clone(),
            name: device_name.clone(),
            created: now_unix(),
            last_seen: None,
        });
        save_store(&store)?;
        new_token
    };

    let (host, transport) = detect_best_ip();

    Ok(PairPayload {
        kind: "gmux-pair",
        version: PAIR_PROTOCOL_VERSION,
        host,
        port: bridge_ws_port(),
        token,
        name: host_name(),
        transport,
        relay_url: None,
    })
}

/// List paired devices for the "Paired devices" UI. Token value is
/// withheld; only an 8-char preview is returned.
#[tauri::command]
pub fn gmux_pair_list() -> Vec<PairedDevice> {
    let store = load_store();
    store
        .tokens
        .into_iter()
        .map(|r| PairedDevice {
            name: r.name,
            created: r.created,
            last_seen: r.last_seen,
            token_preview: r.token.chars().take(8).collect(),
        })
        .collect()
}

/// Remove every token whose `name` matches. Returns the number of
/// records that were dropped (so the UI can say "Revoked 1 device").
#[tauri::command]
pub fn gmux_pair_revoke(name: String) -> Result<u32, String> {
    let mut store = load_store();
    let before = store.tokens.len();
    store.tokens.retain(|t| t.name != name);
    let removed = (before - store.tokens.len()) as u32;
    if removed > 0 {
        save_store(&store)?;
    }
    Ok(removed)
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_token_is_64_chars() {
        let t = generate_hex_token().unwrap();
        assert_eq!(t.len(), 64);
        assert!(t.chars().all(|c| c.is_ascii_hexdigit()));
    }
}
