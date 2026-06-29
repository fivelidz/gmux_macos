//! Agent-spawn smoke test — proves the exact `open_agent_v4` pipeline
//! headlessly: spawn a login shell in a PTY in a given directory, write
//! the agent launch command (`opencode\r`) into it, and verify the agent
//! TUI actually boots (its output contains opencode's UI markers).
//!
//! This is the same sequence the Tauri command performs:
//!   ProcessManager::spawn_shell(cwd) → write_stdin("opencode\r") → events
//!
//! Run with:
//!   cd app/src-tauri
//!   cargo run --release --example agent_spawn_smoke [workdir]
//!
//! Exits 0 when the agent TUI is detected, non-zero otherwise.

use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use std::io::{Read, Write};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

fn main() {
    println!("── gmux-v4 AGENT SPAWN smoke test (open_agent_v4 path, no Tauri) ──");

    let workdir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "/tmp/gmux-spawn-test".to_string());
    std::fs::create_dir_all(&workdir).ok();
    println!("   workdir: {workdir}");

    // 1. PTY — same size the app uses at spawn (resize comes later via UI).
    let pty_system = native_pty_system();
    let pair = match pty_system.openpty(PtySize { rows: 40, cols: 120, pixel_width: 0, pixel_height: 0 }) {
        Ok(p) => { println!("✅ PTY opened (120x40)"); p }
        Err(e) => { eprintln!("✗ openpty failed: {e}"); std::process::exit(1); }
    };

    // 2. Login shell in the workdir — mirrors ProcessManager::spawn_shell:
    //    $SHELL -l, TERM=xterm-256color, GMUX_SESSION_ID injected.
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let mut cmd = CommandBuilder::new(&shell);
    #[cfg(unix)]
    cmd.arg("-l");
    cmd.env("TERM", "xterm-256color");
    cmd.env("GMUX_SESSION_ID", "agent-smoke");
    cmd.cwd(&workdir);

    let mut child = match pair.slave.spawn_command(cmd) {
        Ok(c) => { println!("✅ shell spawned (pid {}, {})", c.process_id().unwrap_or(0), shell); c }
        Err(e) => { eprintln!("✗ spawn failed: {e}"); std::process::exit(1); }
    };

    // 3. Reader thread → channel (same pattern as ProcessManager).
    let mut reader = pair.master.try_clone_reader().expect("clone reader");
    let (tx, rx) = mpsc::channel::<Vec<u8>>();
    thread::spawn(move || {
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => break,
                Ok(n) => { if tx.send(buf[..n].to_vec()).is_err() { break; } }
            }
        }
    });

    let mut writer = pair.master.take_writer().expect("take writer");

    // Drain shell startup output for up to 2.5s.
    let mut total: Vec<u8> = Vec::new();
    let start = Instant::now();
    while start.elapsed() < Duration::from_millis(2500) {
        if let Ok(chunk) = rx.recv_timeout(Duration::from_millis(200)) {
            total.extend_from_slice(&chunk);
        }
    }
    println!("   shell startup output: {} bytes", total.len());

    // 4. Write the agent launch command — exactly what open_agent_v4 writes
    //    for agent_type "opencode"/"qalcode".
    let launch = "opencode\r";
    match writer.write_all(launch.as_bytes()).and_then(|_| writer.flush()) {
        Ok(_) => println!("✅ wrote {launch:?} ({} bytes)", launch.len()),
        Err(e) => { eprintln!("✗ write failed: {e}"); std::process::exit(1); }
    }

    // 5. Watch output for opencode TUI markers (up to 30s). The TUI draws
    //    box characters and shows its hint line; raw bytes are fine to scan.
    // NOTE: do not include "opencode" itself — the PTY echoes the typed
    // command back, which would false-positive instantly. These markers
    // only appear once the TUI has actually rendered.
    let markers = ["Ask anything", "switch agent", "ctrl+p commands", "/status"];
    let mut found: Option<&str> = None;
    let boot_start = Instant::now();
    total.clear();
    while boot_start.elapsed() < Duration::from_secs(30) {
        if let Ok(chunk) = rx.recv_timeout(Duration::from_millis(400)) {
            total.extend_from_slice(&chunk);
            let hay = String::from_utf8_lossy(&total);
            if let Some(m) = markers.iter().find(|m| hay.contains(**m)) {
                found = Some(m);
                break;
            }
        }
    }

    match found {
        Some(m) => println!("✅ agent TUI booted — marker {m:?} found in {} bytes after {:.1}s",
                            total.len(), boot_start.elapsed().as_secs_f32()),
        None => {
            eprintln!("✗ agent TUI not detected within 30s ({} bytes captured)", total.len());
            eprintln!("  last 400 bytes: {}", String::from_utf8_lossy(&total[total.len().saturating_sub(400)..]));
            let _ = child.kill();
            std::process::exit(1);
        }
    }

    // 6. Cleanly shut the agent down (Ctrl-C twice then kill shell).
    let _ = writer.write_all(b"\x03");
    thread::sleep(Duration::from_millis(400));
    let _ = writer.write_all(b"\x03");
    thread::sleep(Duration::from_millis(400));
    let _ = child.kill();
    println!("✅ cleaned up (agent + shell terminated)");
    println!("──────────────────────────────────────────────────────");
    println!("✅ ALL CHECKS PASSED — open_agent_v4 spawn path works");
}
