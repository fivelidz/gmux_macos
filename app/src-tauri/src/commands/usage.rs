//! IPC commands for Claude Code usage tracking.
//!
//! Originally from https://github.com/its-maestro-baby/maestro
//! commit a10500d, MIT licensed by Maestro contributors.
//! Adapted for gmux-v4 by fivelidz (no functional changes).
//!
//!
//! Fetches real rate limit data from Anthropic's OAuth API.
//! Reads OAuth tokens from platform credential store (primary) or credentials file (fallback).

use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Instant;
use tokio::sync::Mutex as AsyncMutex;

/// Flag to skip credential store after first failure (prevents repeated prompts).
static CREDENTIAL_STORE_FAILED: AtomicBool = AtomicBool::new(false);

/// Minimum seconds between actual API calls. Requests within this window return cached data.
const CACHE_TTL_SECS: u64 = 30;

/// Anthropic OAuth client ID used by claude-code CLI (publicly known).
/// Same value the desktop CLI sends when refreshing its token.
const ANTHROPIC_OAUTH_CLIENT_ID: &str = "9d1c250a-e61b-44d9-88ed-5944d1962f5e";

/// OAuth token-refresh endpoint.
///
/// alpha.22 FIX — Anthropic migrated the OAuth domain from
/// `console.anthropic.com` to `platform.claude.com`. The old URL now returns
/// 404, which silently broke auto-refresh: the access_token expired (~8h),
/// refresh 404'd every poll, and the UI fell back to "Connect Claude / run
/// claude /login" even though valid credentials (with a working refresh_token)
/// were on disk. This is the same endpoint the working
/// @ex-machina/opencode-anthropic-auth plugin uses.
const OAUTH_TOKEN_URL: &str = "https://platform.claude.com/v1/oauth/token";

/// Async lock to ensure only one refresh attempt happens at a time even if
/// multiple frontend components call get_claude_usage() concurrently while
/// the cached token is expired.
static REFRESH_LOCK: AsyncMutex<()> = AsyncMutex::const_new(());

/// Latch — when set to true we've already tried to refresh in this process
/// and the refresh-token was rejected (invalid_grant). Don't keep hammering
/// the endpoint on every poll; require the user to re-login.
static REFRESH_GAVE_UP: AtomicBool = AtomicBool::new(false);

/// Cached usage response to prevent duplicate API calls from multiple frontend
/// components or rapid re-renders. Stores (fetch_time, ttl_secs, data).
static USAGE_CACHE: Mutex<Option<(Instant, u64, UsageData)>> = Mutex::new(None);

/// Usage data from Anthropic's OAuth API.
///
/// The real API response (May 2026) has these meaningful fields:
///   - five_hour:           rolling 5h window — all models combined
///   - seven_day:           7-day cap — all models combined (Sonnet + Opus + Haiku)
///   - seven_day_sonnet:    7-day cap — Sonnet only (sub-limit)
///   - seven_day_opus:      7-day cap — Opus only (often null if you haven't used Opus)
///   - several other experimental quotas we don't surface (omelette, cowork, ...)
///
/// Fields below are intentionally named after the page labels users see at
/// claude.ai/settings/usage so the cycle button can be self-explanatory.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UsageData {
    /// Session (5-hour window) usage percentage (0-100).
    pub session_percent: f64,
    /// When the session window resets (ISO 8601).
    pub session_resets_at: Option<String>,
    /// Weekly (7-day window) usage percentage for ALL models combined (0-100).
    /// Maps to the "All models" line on claude.ai/settings/usage.
    pub weekly_percent: f64,
    /// When the weekly (all models) window resets (ISO 8601).
    pub weekly_resets_at: Option<String>,
    /// Weekly Sonnet-only sub-limit (0-100). alpha.16.4 — added.
    /// Maps to the "Sonnet only" line on claude.ai/settings/usage.
    pub weekly_sonnet_percent: f64,
    /// When the Sonnet-only weekly window resets (ISO 8601).
    pub weekly_sonnet_resets_at: Option<String>,
    /// Weekly Opus-only sub-limit (0-100). Often 0 if the user hasn't used Opus.
    pub weekly_opus_percent: f64,
    /// When the Opus-only weekly window resets (ISO 8601).
    pub weekly_opus_resets_at: Option<String>,
    /// Error message if token is expired or unavailable.
    pub error_message: Option<String>,
    /// Whether authentication is needed (token expired or missing).
    pub needs_auth: bool,
}

impl Default for UsageData {
    fn default() -> Self {
        Self {
            session_percent: 0.0,
            session_resets_at: None,
            weekly_percent: 0.0,
            weekly_resets_at: None,
            weekly_sonnet_percent: 0.0,
            weekly_sonnet_resets_at: None,
            weekly_opus_percent: 0.0,
            weekly_opus_resets_at: None,
            error_message: None,
            needs_auth: false,
        }
    }
}

/// Response from Anthropic's /api/oauth/usage endpoint.
///
/// alpha.16.4 — added seven_day_sonnet which the API returns alongside
/// seven_day_opus. The page calls it "Sonnet only" and shows it as a
/// separate sub-limit. Other fields (seven_day_cowork, seven_day_omelette,
/// seven_day_oauth_apps, tangelo, iguana_necktie, omelette_promotional,
/// extra_usage) are intentionally ignored — they're experimental quotas
/// most users don't care about.
#[derive(Debug, Deserialize)]
struct ApiUsageResponse {
    five_hour: Option<UsageWindow>,
    seven_day: Option<UsageWindow>,
    seven_day_sonnet: Option<UsageWindow>,
    seven_day_opus: Option<UsageWindow>,
}

#[derive(Debug, Deserialize)]
struct UsageWindow {
    utilization: f64,
    resets_at: Option<String>,
}

/// Credentials structure (same format in file and keychain).
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CredentialsData {
    claude_ai_oauth: Option<OAuthCredentials>,
}

/// OAuth credentials structure.
///
/// `refresh_token` is optional because keychain entries on older versions
/// may not include it. When present, an expired access_token can be
/// transparently refreshed without prompting the user to run `claude /login`.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct OAuthCredentials {
    access_token: String,
    expires_at: u64,
    #[serde(default)]
    refresh_token: Option<String>,
}

/// JSON body returned by the OAuth refresh endpoint on success.
#[derive(Debug, Deserialize)]
struct OAuthRefreshResponse {
    access_token: String,
    /// Anthropic rotates refresh tokens — on every successful refresh you get
    /// a NEW refresh_token that must replace the old one in the credentials
    /// file, otherwise subsequent refreshes will fail with invalid_grant.
    #[serde(default)]
    refresh_token: Option<String>,
    expires_in: u64,
}

/// Check if token is expired (with 60 second buffer).
fn is_token_expired(expires_at: u64) -> bool {
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;

    expires_at < now_ms + 60_000
}

/// Get the current username for credential store access.
fn get_username() -> Option<String> {
    // USER (Unix) or USERNAME (Windows)
    std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .ok()
}

/// Read credentials from macOS Keychain using the `security` CLI.
/// This avoids permission prompts since `security` is Apple-signed.
#[cfg(target_os = "macos")]
async fn read_keychain_credentials() -> Result<CredentialsData, String> {
    let username = get_username().ok_or("Could not get username")?;

    let output = tokio::process::Command::new("security")
        .args([
            "find-generic-password",
            "-s", "Claude Code-credentials",
            "-a", &username,
            "-w",
        ])
        .output()
        .await
        .map_err(|e| format!("Failed to run security: {}", e))?;

    if !output.status.success() {
        return Err("No keychain entry found".to_string());
    }

    let data = String::from_utf8(output.stdout)
        .map_err(|_| "Invalid keychain data")?;

    serde_json::from_str(data.trim())
        .map_err(|e| format!("Failed to parse keychain data: {}", e))
}

/// Read credentials from platform credential store (Windows/Linux).
/// - Windows: Credential Manager
/// - Linux: Secret Service (D-Bus)
#[cfg(not(target_os = "macos"))]
async fn read_keychain_credentials() -> Result<CredentialsData, String> {
    let username = get_username().ok_or("Could not get username")?;

    let result = tokio::task::spawn_blocking(move || {
        let entry = keyring::Entry::new("Claude Code-credentials", &username)
            .map_err(|e| format!("Failed to create keyring entry: {}", e))?;

        entry.get_password().map_err(|e| match e {
            keyring::Error::NoEntry => "No credential entry found".to_string(),
            _ => format!("Credential store error: {}", e),
        })
    })
    .await
    .map_err(|e| format!("Task join error: {}", e))??;

    serde_json::from_str(&result)
        .map_err(|e| format!("Failed to parse credential data: {}", e))
}

/// Read credentials from file (fallback for non-macOS or if keychain fails).
async fn read_file_credentials() -> Result<CredentialsData, String> {
    let home = directories::UserDirs::new().map(|dirs| dirs.home_dir().to_path_buf())
        .ok_or("Could not get home directory")?;

    let creds_path = home.join(".claude").join(".credentials.json");

    if !creds_path.exists() {
        return Err("Credentials file not found".to_string());
    }

    let content = tokio::fs::read_to_string(&creds_path)
        .await
        .map_err(|e| format!("Failed to read file: {}", e))?;

    serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse file: {}", e))
}

/// Refresh an expired OAuth access token using the stored refresh_token.
///
/// On success:
///   - Writes the new tokens back to ~/.claude/.credentials.json so the
///     desktop Claude CLI also picks up the rotation
///   - Returns the new access_token string
///
/// On failure (HTTP 400 invalid_grant, network error, etc.):
///   - Sets REFRESH_GAVE_UP so subsequent polls don't keep hammering the
///     endpoint until the user re-logins (which resets the latch via a
///     re-read of the credentials file containing a fresh refresh_token).
///
/// alpha.17-dev2 — this is the qalcode2-style auto-refresh the user asked
/// about ("I was hoping it would just remember the token like qalcode2").
async fn refresh_oauth_token(refresh_token: &str) -> Result<String, String> {
    if REFRESH_GAVE_UP.load(Ordering::Relaxed) {
        // Use the word "expired" so the UI surfaces the "claude /login" hint
        // rather than the generic "Connect Claude" message.
        return Err("Session expired — refresh_token rejected. Run `claude /login`".to_string());
    }

    log::info!("[usage] access_token expired — attempting OAuth refresh");

    let client = reqwest::Client::builder()
        .user_agent("claude-cli/2.1.87 (external, cli)")
        .build()
        .map_err(|e| format!("Failed to build HTTP client: {}", e))?;

    let body = serde_json::json!({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
    });

    let response = client
        .post(OAUTH_TOKEN_URL)
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Network error during refresh: {}", e))?;

    let status = response.status();
    if !status.is_success() {
        // 400 invalid_grant means this refresh_token is no longer accepted.
        // Latch the failure so we don't retry every 30s — user must re-login.
        let body_text = response.text().await.unwrap_or_default();
        log::warn!("[usage] OAuth refresh returned {} — body: {}", status, body_text);
        if status.as_u16() == 400 {
            REFRESH_GAVE_UP.store(true, Ordering::Relaxed);
        }
        return Err(format!("Refresh rejected ({}): {}", status, body_text));
    }

    let parsed: OAuthRefreshResponse = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse refresh response: {}", e))?;

    let new_expires_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
        + parsed.expires_in.saturating_mul(1000);

    // Write the rotated tokens back to ~/.claude/.credentials.json so the
    // CLI and any sibling tool pick up the same refresh chain.
    let new_refresh = parsed
        .refresh_token
        .clone()
        .unwrap_or_else(|| refresh_token.to_string());
    if let Err(e) = write_credentials_file(&parsed.access_token, &new_refresh, new_expires_at).await
    {
        // Token refresh worked but writeback failed — log loudly and return
        // the token anyway so this poll succeeds, even though next gmux run
        // will see the old expired token on disk.
        log::warn!("[usage] OAuth refresh succeeded but writeback failed: {}", e);
    } else {
        log::info!("[usage] OAuth refresh ok — new expires_at={}ms", new_expires_at);
    }

    // Refresh worked → reset the give-up latch (e.g. user re-logged-in and
    // we want to allow refresh attempts again on the next expiry).
    REFRESH_GAVE_UP.store(false, Ordering::Relaxed);

    Ok(parsed.access_token)
}

/// Atomically write updated OAuth credentials to ~/.claude/.credentials.json.
/// Preserves any other fields in the file (defensive — the file may contain
/// other keys in future Claude CLI versions).
async fn write_credentials_file(
    access_token: &str,
    refresh_token: &str,
    expires_at_ms: u64,
) -> Result<(), String> {
    let home = directories::UserDirs::new().map(|d| d.home_dir().to_path_buf())
        .ok_or("Could not get home directory")?;
    let creds_path = home.join(".claude").join(".credentials.json");

    // Read existing content (may contain unknown keys we shouldn't drop)
    let existing = tokio::fs::read_to_string(&creds_path)
        .await
        .map_err(|e| format!("Failed to read creds: {}", e))?;
    let mut json: serde_json::Value = serde_json::from_str(&existing)
        .map_err(|e| format!("Failed to parse existing creds: {}", e))?;

    // Update the oauth subtree (Claude CLI camelCases on disk).
    if let Some(obj) = json.as_object_mut() {
        let oauth_entry = obj
            .entry("claudeAiOauth")
            .or_insert_with(|| serde_json::json!({}));
        if let Some(o) = oauth_entry.as_object_mut() {
            o.insert("accessToken".into(), serde_json::Value::String(access_token.to_string()));
            o.insert("refreshToken".into(), serde_json::Value::String(refresh_token.to_string()));
            o.insert("expiresAt".into(), serde_json::Value::Number(expires_at_ms.into()));
        }
    }

    let serialised = serde_json::to_string_pretty(&json)
        .map_err(|e| format!("Failed to serialise creds: {}", e))?;

    // Write atomically via temp-file + rename so a crash mid-write doesn't
    // leave the file in a half-written state.
    let tmp_path = creds_path.with_extension("json.tmp");
    tokio::fs::write(&tmp_path, &serialised)
        .await
        .map_err(|e| format!("Failed to write temp creds: {}", e))?;

    // Match the 0600 perms the CLI uses (Unix only).
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = tokio::fs::set_permissions(&tmp_path, std::fs::Permissions::from_mode(0o600)).await;
    }

    tokio::fs::rename(&tmp_path, &creds_path)
        .await
        .map_err(|e| format!("Failed to rename creds: {}", e))?;

    Ok(())
}

/// Get a valid access token, trying platform credential store first then file.
///
/// alpha.17-dev2 — if the access token is expired but a refresh_token is
/// available, automatically refresh against Anthropic's OAuth endpoint and
/// return the new access_token. This means the user no longer has to run
/// `claude /login` after every 8-hour expiry — the badge "just keeps working"
/// like qalcode2.
async fn get_access_token() -> Result<String, String> {
    // Try platform credential store first (skip if previously failed to avoid repeated prompts)
    if !CREDENTIAL_STORE_FAILED.load(Ordering::Relaxed) {
        match read_keychain_credentials().await {
            Ok(creds) => {
                if let Some(oauth) = creds.claude_ai_oauth {
                    if !is_token_expired(oauth.expires_at) {
                        log::debug!("Using token from platform credential store");
                        return Ok(oauth.access_token);
                    }
                    log::debug!("Credential store token expired — will try file (which is where refreshes get written back)");
                }
            }
            Err(e) => {
                log::debug!("Credential store failed, will use file fallback: {}", e);
                CREDENTIAL_STORE_FAILED.store(true, Ordering::Relaxed);
            }
        }
    }

    // Fall back to credentials file
    let creds = read_file_credentials().await?;
    let oauth = creds.claude_ai_oauth.ok_or("Not logged in")?;

    if !is_token_expired(oauth.expires_at) {
        log::debug!("Using token from file");
        return Ok(oauth.access_token);
    }

    // Token is expired — try to refresh transparently. Serialise via async
    // mutex so concurrent get_claude_usage() callers don't fire two refresh
    // requests in parallel (which would invalidate each other's tokens since
    // Anthropic rotates the refresh_token on each successful exchange).
    if let Some(rt) = oauth.refresh_token.as_deref() {
        let _guard = REFRESH_LOCK.lock().await;
        // Re-read credentials after acquiring the lock — another task may
        // have completed the refresh while we were waiting and the on-disk
        // token may now be fresh.
        let creds = read_file_credentials().await?;
        if let Some(oauth2) = &creds.claude_ai_oauth {
            if !is_token_expired(oauth2.expires_at) {
                log::debug!("Token refreshed by another caller while we waited");
                return Ok(oauth2.access_token.clone());
            }
        }
        return refresh_oauth_token(rt).await;
    }

    // No refresh_token available — user must re-login.
    Err("Session expired (no refresh_token — run `claude /login`)".to_string())
}

/// Fetch usage data from Anthropic's OAuth API.
/// Responses are cached for 30 seconds to prevent 429 errors when multiple
/// components or re-renders trigger concurrent requests.
#[tauri::command]
pub async fn get_claude_usage() -> Result<UsageData, String> {
    // Return cached response if still fresh
    if let Ok(guard) = USAGE_CACHE.lock() {
        if let Some((fetched_at, ttl, ref data)) = *guard {
            if fetched_at.elapsed().as_secs() < ttl {
                log::debug!("Returning cached usage data (age: {}s, ttl: {}s)", fetched_at.elapsed().as_secs(), ttl);
                return Ok(data.clone());
            }
        }
    }

    let result = fetch_usage_from_api().await;

    // Cache successful responses for 30s. For auth errors, use a SHORT TTL
    // (5s) so that when the user runs `claude /login` to refresh their
    // token, the badge updates within a few seconds instead of being stuck
    // showing "expired" for up to 30 seconds.
    // alpha.16 — added the short TTL for auth-error path.
    if let Ok(ref data) = result {
        if let Ok(mut guard) = USAGE_CACHE.lock() {
            let ttl = if data.needs_auth { 5 } else { CACHE_TTL_SECS };
            *guard = Some((Instant::now(), ttl, data.clone()));
        }
    }

    result
}

/// Actually fetch usage data from the API (uncached).
async fn fetch_usage_from_api() -> Result<UsageData, String> {
    let token = match get_access_token().await {
        Ok(t) => t,
        Err(e) => {
            log::debug!("No valid token: {}", e);
            return Ok(UsageData {
                error_message: Some(e),
                needs_auth: true,
                ..Default::default()
            });
        }
    };

    let client = reqwest::Client::new();
    let response = client
        .get("https://api.anthropic.com/api/oauth/usage")
        .header("Authorization", format!("Bearer {}", token))
        .header("anthropic-beta", "oauth-2025-04-20")
        .header("User-Agent", "claude-code/2.0.32")
        .send()
        .await
        .map_err(|e| format!("Network error: {}", e))?;

    // Handle auth errors
    if response.status() == reqwest::StatusCode::UNAUTHORIZED {
        log::debug!("Usage API returned 401");
        return Ok(UsageData {
            error_message: Some("Session expired".to_string()),
            needs_auth: true,
            ..Default::default()
        });
    }

    // Handle rate limiting (429) — extend cache TTL to avoid hammering the API
    if response.status() == reqwest::StatusCode::TOO_MANY_REQUESTS {
        let retry_after = response
            .headers()
            .get("retry-after")
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(60);
        log::warn!("Usage API returned 429, retry after {}s", retry_after);
        let data = UsageData {
            error_message: Some(format!("Rate limited, retrying in {}s", retry_after)),
            ..Default::default()
        };
        // Cache the 429 response using retry-after as TTL so we don't retry before the server allows
        if let Ok(mut guard) = USAGE_CACHE.lock() {
            *guard = Some((Instant::now(), retry_after, data.clone()));
        }
        return Ok(data);
    }

    if !response.status().is_success() {
        let status = response.status();
        log::warn!("Usage API returned {}", status);
        return Ok(UsageData {
            error_message: Some(format!("API error: {}", status)),
            ..Default::default()
        });
    }

    let api_response: ApiUsageResponse = response
        .json()
        .await
        .map_err(|e| format!("Parse error: {}", e))?;

    // Helper to convert utilization to percentage.
    // alpha.21 FIX — the API returns utilization on the 0-100 scale. The old
    // heuristic (`if val <= 1.0 multiply by 100`) blew up real low usage:
    // 1% came back as 1.0 → was shown as 100%. Confirmed against the
    // claude.ai usage page (Sonnet at 1% displayed as 100%). Use the value
    // as-is, clamped to [0, 100].
    let to_percent = |val: f64| val.clamp(0.0, 100.0);

    let usage = UsageData {
        session_percent: api_response
            .five_hour
            .as_ref()
            .map(|w| to_percent(w.utilization))
            .unwrap_or(0.0),
        session_resets_at: api_response.five_hour.and_then(|w| w.resets_at),
        weekly_percent: api_response
            .seven_day
            .as_ref()
            .map(|w| to_percent(w.utilization))
            .unwrap_or(0.0),
        weekly_resets_at: api_response.seven_day.and_then(|w| w.resets_at),
        // alpha.16.4 — Sonnet-only sub-limit (was previously missing)
        weekly_sonnet_percent: api_response
            .seven_day_sonnet
            .as_ref()
            .map(|w| to_percent(w.utilization))
            .unwrap_or(0.0),
        weekly_sonnet_resets_at: api_response.seven_day_sonnet.and_then(|w| w.resets_at),
        weekly_opus_percent: api_response
            .seven_day_opus
            .as_ref()
            .map(|w| to_percent(w.utilization))
            .unwrap_or(0.0),
        weekly_opus_resets_at: api_response.seven_day_opus.and_then(|w| w.resets_at),
        error_message: None,
        needs_auth: false,
    };

    log::info!(
        "Usage: session={:.1}%, weekly={:.1}% (sonnet={:.1}%, opus={:.1}%)",
        usage.session_percent,
        usage.weekly_percent,
        usage.weekly_sonnet_percent,
        usage.weekly_opus_percent,
    );

    Ok(usage)
}
