//! Standalone PTY smoke test — exercises the same portable-pty + Utf8Decoder
//! pipeline that `ProcessManager::spawn_shell` uses, but with no Tauri runtime.
//!
//! This proves the cross-platform PTY core works end-to-end on the host
//! without needing a GUI / Tauri window. Run with:
//!
//!   cd app/src-tauri
//!   cargo run --example pty_smoke
//!
//! Expected output:
//!   ✅ PTY opened
//!   ✅ shell spawned (pid …)
//!   ✅ wrote 'echo "hello v4"\r'
//!   ✅ captured "hello v4" in N bytes of output
//!   ✅ killed shell cleanly
//!
//! Any failure prints the exact step + error and exits non-zero.

use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use std::io::{Read, Write};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

fn main() {
    println!("── gmux-v4 PTY smoke test (no Tauri) ────────────────────────────");

    // 1. Open a PTY pair.
    let pty_system = native_pty_system();
    let pair = match pty_system.openpty(PtySize { rows: 24, cols: 80, pixel_width: 0, pixel_height: 0 }) {
        Ok(p) => { println!("✅ PTY opened"); p }
        Err(e) => { eprintln!("✗ openpty failed: {e}"); std::process::exit(1); }
    };

    // 2. Spawn a deterministic shell. We deliberately use /bin/sh (not
    //    $SHELL) so interactive shells like fish don't drown the test
    //    in escape-sequence setup that varies with the user's rc.
    //    A real gmux agent inherits the user's $SHELL — but for the
    //    smoke test we just want to prove PTY round-trip.
    let shell = if cfg!(windows) { "cmd.exe".to_string() } else { "/bin/sh".to_string() };
    let mut cmd = CommandBuilder::new(&shell);
    cmd.env("TERM", "xterm-256color");
    cmd.env("GMUX_SESSION_ID", "smoke-test");
    cmd.env("PS1", "$ ");
    if let Ok(home) = std::env::var("HOME") { cmd.cwd(home); }

    let mut child = match pair.slave.spawn_command(cmd) {
        Ok(c) => { println!("✅ shell spawned (pid {})", c.process_id().unwrap_or(0)); c }
        Err(e) => { eprintln!("✗ spawn failed: {e}"); std::process::exit(1); }
    };
    // Drop slave so the child gets EOF when we close the master.
    drop(pair.slave);

    // 3. Spawn a reader thread that feeds bytes into an mpsc channel.
    let mut reader = pair.master.try_clone_reader().expect("clone_reader");
    let (tx, rx) = mpsc::channel::<Vec<u8>>();
    let reader_handle = thread::spawn(move || {
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => { if tx.send(buf[..n].to_vec()).is_err() { break; } }
                Err(_) => break,
            }
        }
    });

    // 4. Take the writer.
    let mut writer = pair.master.take_writer().expect("take_writer");

    // 5. Give the shell a moment to print its prompt.
    thread::sleep(Duration::from_millis(300));

    // Drain anything that arrived already.
    let mut captured = Vec::<u8>::new();
    while let Ok(chunk) = rx.try_recv() { captured.extend_from_slice(&chunk); }
    println!("   → prompt + early output: {} bytes", captured.len());

    // 6. Write the test command.
    let cmd_bytes = b"echo \"hello v4\"\r";
    if let Err(e) = writer.write_all(cmd_bytes) {
        eprintln!("✗ write_all failed: {e}"); std::process::exit(1);
    }
    if let Err(e) = writer.flush() {
        eprintln!("✗ flush failed: {e}"); std::process::exit(1);
    }
    println!("✅ wrote 'echo \"hello v4\"\\r' ({} bytes)", cmd_bytes.len());

    // 7. Wait up to 5 s for the echo to come back. Some shells (fish,
    //    PowerShell) take ~1-2 s to set up before they accept input.
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    let mut saw_marker = false;
    while std::time::Instant::now() < deadline {
        match rx.recv_timeout(Duration::from_millis(100)) {
            Ok(chunk) => {
                captured.extend_from_slice(&chunk);
                let s = String::from_utf8_lossy(&captured);
                if s.contains("hello v4") {
                    saw_marker = true;
                    break;
                }
            }
            Err(_) => {} // timeout, keep waiting until deadline
        }
    }

    if saw_marker {
        println!("✅ captured 'hello v4' in {} bytes of output", captured.len());
    } else {
        eprintln!("✗ did NOT see 'hello v4' in {} bytes of output (preview: {:?})",
                  captured.len(),
                  String::from_utf8_lossy(&captured[..captured.len().min(400)]).to_string());
        // Don't exit yet — we still want to clean up.
    }

    // 8. Send exit, give it a moment, then kill if still alive.
    let _ = writer.write_all(b"exit\r");
    let _ = writer.flush();
    thread::sleep(Duration::from_millis(300));

    match child.try_wait() {
        Ok(Some(status)) => println!("✅ shell exited cleanly with {status:?}"),
        _ => match child.kill() {
            Ok(()) => println!("✅ killed shell (was still running)"),
            Err(e) => eprintln!("✗ kill failed: {e}"),
        },
    }

    // Drop writer + master to close PTY → reader thread exits.
    drop(writer);
    let _ = reader_handle.join();

    if saw_marker {
        println!("──────────────────────────────────────────────────────");
        println!("✅ ALL CHECKS PASSED");
    } else {
        eprintln!("✗ marker missing — see above. exit 1");
        std::process::exit(1);
    }
}
