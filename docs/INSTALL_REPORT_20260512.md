# Install Report — Sandbox VM, May 12 2026

Real-world install test on the agent-sandbox VM (CachyOS, no GUI displayed during test, all via SSH).

**Result: install succeeds end-to-end after two fixes.** Documented below.

---

## Pre-install VM state

| Component | Available? | Notes |
|---|---|---|
| Python 3.14.4 | ✅ | Symlink `python3.11` actually invokes 3.14 |
| Node 25.9.0, npm 11.13.0 | ✅ | |
| bun 1.3.13 | ✅ | |
| tmux | ✅ | Version detection cmd was wrong (`tmux -V` works, `tmux --version` does not) |
| ffmpeg n8.1 | ✅ | |
| **rust / cargo** | ❌ | Not installed by default |
| **WebKitGTK 4.1** | ❌ | Not installed by default — Tauri needs this |
| Python `sounddevice` | ❌ | Not installed by default; faster-whisper, websockets, numpy, psutil all already present |
| Pre-existing gmux-system | ✅ | Older copy in `~/projects/gmux-system/` — backed up before overwriting |

## Steps that worked first time

1. Step 0 — Pre-flight check ran cleanly
2. Step 1 — Copying gmux-system from `/mnt/host-drop/` to `~/projects/` — 9.2MB, fast
3. Step 3 — `pip install --user --break-system-packages sounddevice` — fast (already had deps cached)
4. Step 4 — `npm install` in `app/` — 10 seconds, 60MB node_modules
5. Step 5 — MediaPipe model — already in `models/` from earlier (7.5MB)
6. Step 6 — `python3.11 backend/status/monitor.py` started cleanly, bound :8769, returned real JSON for the live tmux pane

## Issues found

### Issue 1: Rust not installed by default

**Fix:** `sudo pacman -S --needed --noconfirm rust` — installed cargo 1.95.0, rustc 1.95.0 from the standard repos. Quick.

**Action for install.sh:** add `rust` to the pacman dependency check + install list.

### Issue 2: WebKitGTK not installed by default

**Symptom:** `cargo check` failed with:
```
The system library `javascriptcoregtk-4.1` required by crate `javascriptcore-rs-sys` was not found.
```

**Fix:** `sudo pacman -S --needed webkit2gtk-4.1 gtk3 libappindicator-gtk3 librsvg pkgconf base-devel` — pulled in webkit2gtk-4.1 v2.52.3 and dependencies.

**Action for install.sh:** add these to the pacman list. Also document the equivalent for Debian/Ubuntu (`libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev pkg-config`).

### Issue 3: **MISSING `build.rs` in gmux-system/app/src-tauri/** — real bug

**Symptom:** Even after WebKit installed, `cargo build` failed with:
```
error: OUT_DIR env var is not set, do you have a build script?
   --> src/lib.rs:569:14
569 |         .run(tauri::generate_context!())
```

**Root cause:** `Cargo.toml` has `[build-dependencies] tauri-build = "2"` but there's no `build.rs` to call `tauri_build::build()`. Tauri 2's `generate_context!` macro needs `tauri-build` to set OUT_DIR with the build context.

The sister project `~/projects/gmuxtest/src-tauri/build.rs` has the correct content:
```rust
fn main() {
    tauri_build::build()
}
```

**Fix applied:** added the same 3-line `build.rs` to `gmux-system/app/src-tauri/build.rs` on the host (so it's in the canonical source for next time).

**Action for the gmux-system repo:** commit the `build.rs` permanently. It must be present for any Tauri 2 cargo build.

### Issue 4: **MISSING `icons/` directory in gmux-system/app/src-tauri/**

**Symptom:** `tauri.conf.json` references icons at `icons/32x32.png`, `icons/128x128.png`, etc. but the directory wasn't present.

**Fix applied:** copied the full `icons/` directory from `~/projects/gmuxtest/src-tauri/icons/` (which has all required PNG/ICO/ICNS files).

**Action for the gmux-system repo:** commit `icons/` (it's small, ~200KB total). Without it, `tauri build` won't bundle the app icon.

## Build success

After applying issues 3 and 4, `cargo build --release` completed in 44 seconds (deps were already cached from earlier failed attempts) and produced:

```
target/release/gmuxtest               13 MB binary
target/release/libgmuxtest_lib.a      91 MB static library
target/release/libgmuxtest_lib.rlib   15 MB rust library
```

One harmless warning (unused `window` variable in `.on_window_event` handler).

## What was NOT tested

Reading the install plan, these steps were skipped or untestable in this environment:

- **Step 8 (Tauri dev mode in actual window)** — VM has no display; SSH-only test can't open Tauri window
- **Step 9 (browser mode at :5550)** — would need browser GUI in VM
- **Gesture detection** — VM has no camera
- **Voice STT round-trip** — VM has no microphone
- **End-to-end agent supervision** — would need OpenCode/qalcode2 actually running with real AI sessions

## Time breakdown

| Step | Time |
|---|---|
| Step 0 pre-flight | <1 min |
| Step 1 copy repo | <1 min |
| Step 2 install rust | ~30 sec (pacman + small package) |
| Step 3 install Python deps | ~1 min |
| Step 4 npm install | 10 sec (cached) |
| Step 5 MediaPipe model | already present |
| Step 6 start monitor | <5 sec |
| Step 7 install WebKitGTK | ~1 min |
| Step 8 cargo build first attempt (incl. compiling deps) | ~3 min |
| Step 8 cargo build with build.rs fix | 44 sec |
| **Total** | **~10 minutes** |

A fresh VM with no caches would be longer (5-10 min for the first cargo build downloading all crate deps).

## Confirmed working

- ✅ Backend monitor daemon spawns, binds :8769, returns real 27-field pane state JSON
- ✅ Tauri binary builds cleanly
- ✅ AGPL-3.0 LICENSE files present and correctly named
- ✅ All Python deps resolve under Python 3.14 (despite `python3.11` shebangs)

## Recommended changes to commit upstream

### High priority
1. **Add `app/src-tauri/build.rs`** with `fn main() { tauri_build::build() }` — without this the Tauri build cannot succeed
2. **Add `app/src-tauri/icons/`** — required by tauri.conf.json

### Medium priority — install documentation
3. Update `DEPENDENCIES.md` (if present) to list:
   - `rust cargo`
   - `webkit2gtk-4.1 gtk3 libappindicator-gtk3 librsvg pkgconf base-devel`
   - `python-sounddevice` (or via pip)
4. Note that `python3.11` may actually be Python 3.14+ on rolling-release distros — this is fine but worth flagging
5. Note the harmless unused-variable warning in `lib.rs:538` (or fix with `_window`)

### Lower priority
6. The Python install command on Arch needs `--break-system-packages` to use `--user` install (PEP 668)
7. Consider a `Dockerfile` or `flake.nix` for a reproducible build environment

## Conclusion

The install test caught two real bugs in the consolidated gmux-system repo (missing build.rs, missing icons/). Both were trivial to fix once identified. The backend works end-to-end. The Tauri binary builds. The install procedure documented in `INSTALL_GMUX_SYSTEM.md` is mostly accurate; minor updates needed for the rust + webkit + sounddevice dependencies.

**Total install time on a fresh VM: ~10-15 minutes** assuming network is fast.

Once Tauri can be run with a display (e.g. via SPICE or VNC into this VM, or building a release `.AppImage` and running on a machine with a GUI), Steps 8 and 9 will be testable.

---

**Test conducted by:** Claude (agent session, host-side, via SSH to agent-sandbox VM)
**VM:** agent-sandbox at 192.168.122.100 (libvirt NAT)
**Host:** superlocal
**Snapshot recommended:** `cachyos-gmux-system-installed-20260512` (after this session)
