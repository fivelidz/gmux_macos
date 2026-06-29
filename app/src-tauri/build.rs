use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

fn main() {
    // Embed the git tag at compile time so the binary knows its release
    // version without needing git available at runtime.
    // Falls back to an empty string when git or the .git dir is missing
    // (e.g. building from a tarball).
    let git_tag = Command::new("git")
        .args(["describe", "--tags", "--always", "--dirty"])
        .output()
        .ok()
        .and_then(|out| if out.status.success() {
            Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
        } else {
            None
        })
        .unwrap_or_default();

    // Embed the build time so the UI can show users when this binary
    // was compiled — makes it obvious when a new build has been loaded.
    let build_secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    // Format as ISO-8601 in local time (the UI will display it as-is).
    // We avoid pulling in chrono here — keep build deps minimal.
    let build_iso = {
        // Crude UTC formatter (good enough for a human-readable build stamp)
        let secs = build_secs as i64;
        let days = secs / 86400;
        let rem  = secs % 86400;
        let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
        // Days-since-epoch → date (Gregorian, simplified)
        // Reuse a tiny inline implementation to avoid dependencies.
        let (y, mo, d) = days_to_ymd(days);
        format!("{:04}-{:02}-{:02} {:02}:{:02}:{:02} UTC", y, mo, d, h, m, s)
    };

    println!("cargo:rustc-env=GMUX_GIT_TAG={}", git_tag);
    println!("cargo:rustc-env=GMUX_BUILD_TIME={}", build_iso);
    // Re-run build.rs when HEAD changes so the embedded tag stays accurate.
    println!("cargo:rerun-if-changed=../../.git/HEAD");
    println!("cargo:rerun-if-changed=../../.git/refs/tags");
    // Force a rerun whenever the build script itself touches the env var
    // we set. Using `rerun-if-env-changed=GMUX_FORCE_REBUILD` plus a CI
    // helper means devs can `GMUX_FORCE_REBUILD=$(date +%s) cargo build`
    // to bust the cache; otherwise the existing rerun-if-changed for the
    // git refs catches the common case (you tagged a new version).
    println!("cargo:rerun-if-env-changed=GMUX_FORCE_REBUILD");

    tauri_build::build()
}

/// Convert days-since-unix-epoch → (year, month, day) in Gregorian.
/// Algorithm: Howard Hinnant's date math, abridged.
fn days_to_ymd(days_since_epoch: i64) -> (i32, u32, u32) {
    let z = days_since_epoch + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = (if mp < 10 { mp + 3 } else { mp - 9 }) as u32;
    let y_adj = y + if m <= 2 { 1 } else { 0 };
    (y_adj as i32, m, d)
}
