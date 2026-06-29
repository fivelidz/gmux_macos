#!/usr/bin/env python3.11
"""
gmux.py — Terminal stack entry point.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NAMING SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  gmux          — this file. Terminal stack: tmux + status bar +
                  Python services (monitor, voice, gesture).
                  Lives in your terminal. No window of its own.

  gmux-ui       — the Tauri desktop app (gmux-app/).
                  Full window with xterm.js terminal inside,
                  gesture overlay, sidebar, voice toggle.
                  Launch: cd gmux-app && npm run tauri dev

CAMERA OWNERSHIP RULE:
  gmux-ui running  →  gmux-ui owns gesture+camera (/dev/video2 via getUserMedia)
                       gmux SKIPS gesture engine entirely (no camera access)
  gmux-ui NOT running → gmux can launch gesture engine (reads /dev/video2)
  Neither should EVER open /dev/video0 directly — that's the broker's job.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Starts tmux with gmux config, then launches background services:
  1. Status monitor (pane state detection)
  2. Gesture engine — SKIPPED if gmux-ui is running
  3. Voice bridge (voice_daemon.py + phone integration) — optional
  4. Compositor daemon (spatial overlay hub) — optional
  5. Phone bridge (WS + HTTP for phone remote control) — optional
  6. Desktop bridge (KDE/GNOME gesture → desktop action) — optional

Usage:
  gmux                         # full mode (auto-detects gmux-ui)
  gmux --no-gesture            # skip webcam/gesture explicitly
  gmux --no-voice              # skip voice
  gmux --status-only           # just status bar, no gesture/voice
  gmux attach                  # attach to existing session
  gmux list                    # show sessions with AI states
  gmux status                  # show current pane states

  gmux-ui:
  cd ~/projects/gmux/gmux-app && npm run tauri dev
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

GMUX_DIR = Path(__file__).parent.parent  # ~/projects/gmuxtest
SRC_DIR = GMUX_DIR / "src-py"  # the Python stack lives here
SCRIPTS_DIR = GMUX_DIR / "scripts"
SESSION_NAME = os.environ.get("GMUX_SESSION", "gmuxtest")
TMUX_CONF = SCRIPTS_DIR / "gmuxtest.tmux.conf"

# Background process PIDs
_children: list[subprocess.Popen] = []
_shutdown = False  # set True on SIGINT/SIGTERM to stop watchdogs


def generate_tmux_conf():
    """
    Generate the gmux tmux config overlay.
    NOTE: user's .tmux.conf + TPM plugins override status-right/interval.
    We apply our status overrides as direct `tmux set` calls AFTER session
    creation (see apply_status_overrides()).
    """
    jump_script = SRC_DIR / "status" / "jump_red.py"
    config = f"""# gmux configuration — generated, do not edit manually
# Source user's existing config first (TPM plugins load here too)
if-shell "test -f ~/.tmux.conf" "source-file ~/.tmux.conf" ""

# gmux keybindings (safe — won't be overridden by plugins)
set -g mouse on
# Disable auto-rename so custom tab names don't get clobbered by process names.
# gmux manages names via monitor.py + session_restore.py.
set -g automatic-rename off
set -g allow-rename off
bind -n C-g   display-message "gmux: gesture mode"
bind -n C-M-v display-message "gmux: voice mode"
bind N   run-shell "python3.11 {jump_script}"
bind r   run-shell "python3.11 -c \\"
import subprocess; subprocess.run(['python3.11', '{__file__}', '_apply_status'])
\\"" \\; display-message "gmux status bar refreshed"

# prefix + C  →  toggle camera broker on/off
bind C run-shell "bash {SCRIPTS_DIR}/cam-toggle.sh toggle" \\; display-message "📷 Camera toggled (prefix+C again to check)"

# prefix + V  →  toggle voice on/off
bind V run-shell "bash {SCRIPTS_DIR}/voice-toggle.sh toggle" \\; display-message "🎤 Voice toggled"

# prefix + S  →  new session with popup name prompt
bind S command-prompt -p "New session name:" "new-session -s '%%'"

# prefix + ?  →  show gmux help cheatsheet
bind ? display-message "Sessions: S=new  s=list  d=detach | Windows: c=new  w=list  n/p=next/prev | Panes: %=vsplit  \"=hsplit  z=zoom  x=kill | gmux: N=jump-red  C=cam  V=voice  I=full-help"

# prefix + I  →  show full gmux info in a new window
bind I run-shell "tmux new-window -n '📖gmux-help' 'python3.11 {__file__} help-pane; echo \"  Press Enter to close...\"; read'"
"""
    TMUX_CONF.parent.mkdir(parents=True, exist_ok=True)
    TMUX_CONF.write_text(config)
    return TMUX_CONF


def apply_status_overrides(session: str = SESSION_NAME):
    """
    Apply gmux status bar settings directly to a running tmux session.
    Called AFTER session creation to override TPM plugins that hijack status-right.
    Also re-applies keybindings here so TPM cannot overwrite them.
    """
    jump_script = SRC_DIR / "status" / "jump_red.py"

    # Re-apply keybindings directly so they survive TPM plugin loading
    keybindings = [
        ["bind-key", "N", "run-shell", f"python3.11 {jump_script}"],
        [
            "bind-key",
            "S",
            "command-prompt",
            "-p",
            "New session name:",
            "new-session -s '%%'",
        ],
        ["bind-key", "C", "run-shell", f"bash {SCRIPTS_DIR}/cam-toggle.sh toggle"],
        ["bind-key", "V", "run-shell", f"bash {SCRIPTS_DIR}/voice-toggle.sh toggle"],
        [
            "bind-key",
            "?",
            "display-message",
            "Sessions: S=new  s=list  d=detach | Windows: c=new  w=list  n/p=next/prev | "
            'Panes: %=vsplit  "=hsplit  z=zoom  x=kill | gmux: N=jump-red  C=cam  V=voice  I=full-help',
        ],
        [
            "bind-key",
            "I",
            "run-shell",
            f"tmux new-window -n '📖gmux-help' 'python3.11 {__file__} help-pane; echo \"  Press Enter to close...\"; read'",
        ],
    ]
    for args in keybindings:
        subprocess.run(["tmux"] + args, capture_output=True)
    print("  ✓ keybindings re-applied (after TPM)")
    status_script = SRC_DIR / "status" / "pane_status.py"

    settings = [
        # ── Status bar ────────────────────────────────────────────────────────
        # status-right: shows ONLY attention items (permission/waiting/error)
        # plus gesture/voice live indicators.  Window names appear in tabs only.
        [
            "set",
            "-t",
            session,
            "-g",
            "status-right",
            f"#(python3.11 {status_script} right #{{session_name}})",
        ],
        ["set", "-t", session, "-g", "status-interval", "1"],
        ["set", "-t", session, "-g", "status-style", "bg=#0f172a,fg=#94a3b8"],
        [
            "set",
            "-t",
            session,
            "-g",
            "status-left",
            "#[fg=#f8fafc,bg=#6c5ce7,bold] gmux #[fg=#6c5ce7,bg=#1e293b,nobold]#[fg=#94a3b8] #S ",
        ],
        ["set", "-t", session, "-g", "status-left-length", "30"],
        ["set", "-t", session, "-g", "status-right-length", "200"],
        ["set", "-t", session, "-g", "status-position", "bottom"],
        ["set", "-t", session, "-g", "status", "on"],
        # ── Disable auto-rename so custom tab names persist ───────────────────
        # tmux auto-rename clobbers custom names whenever a new process starts
        # (e.g. launching bun replaces "doofing_phone_link" with "bun").
        # We handle naming ourselves via monitor.py + session_restore.py.
        ["set", "-t", session, "-g", "automatic-rename", "off"],
        ["set", "-t", session, "-g", "allow-rename", "off"],
        # ── Per-tab colouring ─────────────────────────────────────────────────
        # Pass #{session_name} so pane_status knows which session to look up.
        # This prevents window-index collisions across multiple tmux sessions.
        [
            "set",
            "-t",
            session,
            "-gw",
            "window-status-format",
            f" #(python3.11 {status_script} #{{session_name}} #{{window_index}}) ",
        ],
        [
            "set",
            "-t",
            session,
            "-gw",
            "window-status-current-format",
            f"#(python3.11 {status_script} #{{session_name}} #{{window_index}} active)",
        ],
        ["set", "-t", session, "-gw", "window-status-separator", ""],
        # ── Pane borders + messages ───────────────────────────────────────────
        ["set", "-t", session, "-g", "pane-border-style", "fg=#334155"],
        ["set", "-t", session, "-g", "pane-active-border-style", "fg=#6c5ce7"],
        ["set", "-t", session, "-g", "message-style", "bg=#1e293b,fg=#f8fafc"],
    ]

    for args in settings:
        result = subprocess.run(["tmux"] + args, capture_output=True)
        if result.returncode != 0:
            err = result.stderr.decode().strip()
            if err:
                print(f"  [status-override] warn: {err}", file=sys.stderr)

    print(f"  ✓ status bar overrides applied to session '{session}'")


def start_background(
    name: str, cmd: list[str], wait_secs: float = 0, restart: bool = False
) -> subprocess.Popen | None:
    """Start a background process, track it for cleanup.

    If restart=True, a watchdog thread will automatically restart the process
    if it exits unexpectedly (e.g. monitor.py crashing silently).
    """
    global _shutdown
    if wait_secs > 0:
        time.sleep(wait_secs)

    def _launch() -> subprocess.Popen | None:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                cwd=str(SRC_DIR),
            )
            _children.append(proc)
            return proc
        except FileNotFoundError:
            return None

    proc = _launch()
    if proc is None:
        print(f"  ✗ {name}: command not found")
        return None

    print(f"  ✓ {name} (PID {proc.pid})")

    if restart:

        def _watchdog():
            global _shutdown
            current = proc
            while not _shutdown:
                current.wait()  # block until process exits
                if _shutdown:
                    break
                time.sleep(2)  # brief pause before restart
                new = _launch()
                if new:
                    print(f"  ↺ {name} restarted (PID {new.pid})", flush=True)
                    current = new

        t = threading.Thread(target=_watchdog, daemon=True, name=f"watchdog-{name}")
        t.start()

    return proc


def cleanup(*_):
    """Kill all background processes."""
    global _shutdown
    _shutdown = True
    print("\n[gmux] Shutting down...")
    for proc in _children:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    sys.exit(0)


BANNER = r"""
 ██████╗ ███╗   ███╗██╗   ██╗██╗  ██╗
██╔════╝ ████╗ ████║██║   ██║╚██╗██╔╝
██║  ███╗██╔████╔██║██║   ██║ ╚███╔╝
██║   ██║██║╚██╔╝██║██║   ██║ ██╔██╗
╚██████╔╝██║ ╚═╝ ██║╚██████╔╝██╔╝ ██╗
 ╚═════╝ ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝
  gesture-aware terminal multiplexer
"""

HELP_TEXT = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                           gmux — Quick Reference                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  SESSIONS  (prefix = Ctrl+A)                                                  │
│                                                                               │
│  prefix + S          New session (prompts for name)                          │
│  prefix + s          List / switch sessions                                  │
│  prefix + $          Rename current session                                  │
│  prefix + d          Detach from session                                     │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  WINDOWS (tabs)                                                               │
│                                                                               │
│  prefix + c          New window                                              │
│  prefix + ,          Rename window                                           │
│  prefix + w          List / switch windows                                   │
│  prefix + n          Next window                                             │
│  prefix + p          Previous window                                         │
│  prefix + 0-9        Switch to window by number                              │
│  prefix + &          Kill window                                             │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  PANES (splits)                                                               │
│                                                                               │
│  prefix + %          Split vertically (side by side)                        │
│  prefix + "          Split horizontally (top / bottom)                       │
│  prefix + arrows     Move between panes                                      │
│  prefix + z          Zoom / unzoom pane (fullscreen toggle)                  │
│  prefix + x          Kill pane                                               │
│  prefix + space      Cycle pane layouts                                      │
│  prefix + { / }      Swap pane left / right                                  │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  GMUX-SPECIFIC                                                                │
│                                                                               │
│  prefix + N          Jump to next RED (waiting) AI pane                      │
│  prefix + C          Toggle camera broker on/off                             │
│  prefix + V          Toggle voice bridge on/off                              │
│  prefix + r          Reload gmux status bar                                  │
│  prefix + ?          Show quick help (status bar)                            │
│  prefix + I          Open this help window                                   │
│  Ctrl+G              Gesture mode                                            │
│  Ctrl+Alt+V          Voice mode                                              │
│  prefix + Ctrl+S     Save session (tmux-resurrect)                          │
│  prefix + Ctrl+R     Restore session (tmux-resurrect)                       │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  HAND GESTURES (requires camera + gesture engine)                            │
│                                                                               │
│  Open Palm + Swipe →   Next tmux window                                      │
│  Open Palm + Swipe ←   Previous tmux window                                  │
│  Open Palm + Swipe ↑↓  Switch pane up/down                                   │
│  ☝ One finger          Voice trigger                                         │
│  ✌ Two fingers         Scroll tmux pane                                      │
│  Three fingers         Jump to next RED (waiting) pane                       │
│  👍 Thumbs up          Send "y + Enter" (confirm)                            │
│  👎 Thumbs down        Send Ctrl+C (cancel)                                   │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  STATUS BAR INDICATORS                                                        │
│                                                                               │
│  🔴 RED     AI is waiting for your input → use prefix+N to jump to it       │
│  🟢 GREEN   AI is actively working                                            │
│  🟠 ORANGE  AI needs permission to run a tool                                │
│  🔵 BLUE    AI just completed a task                                          │
│  🟡 DIM     Plain shell / no AI in this pane                                 │
│  📷         Camera broker active                                             │
│  🎤         Voice bridge active                                              │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  COMMANDS                                                                     │
│                                                                               │
│  gmux status          Show current AI pane states                            │
│  gmux tui             Interactive dashboard                                   │
│  gmux restore         Re-launch AI agents from last saved session            │
│  gmux names           Rename windows to project names                        │
│  gmux attach          Re-attach to running session                           │
│  gmux calibrate       Projector corner calibration                           │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
  Press q or any key to close this window
"""


def cmd_help_pane(args):
    """Print help for use in a tmux pane (prefix+I)."""
    print(BANNER)
    print(HELP_TEXT)


def cmd_start(args):
    """Start a new gmux session."""
    conf = generate_tmux_conf()

    # Check if session already exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", SESSION_NAME],
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"gmux session '{SESSION_NAME}' already exists.")
        print(
            f"  Use 'gmux attach' to re-attach, or 'tmux kill-session -t {SESSION_NAME}' to kill it."
        )
        sys.exit(1)

    print(BANNER)
    print(f"Starting gmux session: {SESSION_NAME}")
    print()

    # Register cleanup BEFORE starting services
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("Starting services:")

    # 0. Session auto-save daemon (saves state every 30s so restore works)
    start_background(
        "session saver",
        ["python3.11", str(SRC_DIR / "status" / "session_restore.py"), "--daemon"],
    )

    # 1. Always start status monitor — restart=True so a crash doesn't silently kill status
    start_background(
        "status monitor",
        ["python3.11", str(SRC_DIR / "status" / "monitor.py")],
        restart=True,
    )

    # 2. Gesture engine + mapper
    # DEFAULT: OFF. Must explicitly pass --gesture to enable.
    # Reason: gesture/engine.py falls back to opening /dev/video0 directly
    # (exclusive lock) if PipeWire/GStreamer fails, which steals the camera
    # from the broker and breaks every other app using video.
    # When gmux-ui is running it handles gestures inside the Tauri WebView
    # using getUserMedia(gmux-virtual-cam) — much safer.
    _tauri_running = bool(
        subprocess.run(
            ["pgrep", "-f", "target/debug/gmux-app"],
            capture_output=True,
        ).stdout.strip()
    )
    _gesture_requested = getattr(args, "gesture", False)
    if _tauri_running:
        print(
            "  ⓘ  gesture engine skipped — gmux-ui is running (handles gestures internally)"
        )
    elif _gesture_requested and not args.status_only:
        print(
            "  ⚠  gesture engine: may grab /dev/video0 exclusively if PipeWire unavailable"
        )
        start_background(
            "gesture engine",
            ["python3.11", str(SRC_DIR / "gesture" / "engine.py")],
        )
        start_background(
            "gesture mapper",
            ["python3.11", str(SRC_DIR / "gesture" / "mapper.py")],
            wait_secs=1.0,
        )
    elif not args.status_only and not _tauri_running:
        print("  ⓘ  gesture engine OFF (default). Use gmux --gesture to enable.")

    # 3. Voice bridge (optional)
    if not args.no_voice and not args.status_only:
        start_background(
            "voice bridge",
            ["python3.11", str(SRC_DIR / "voice" / "bridge.py")],
        )

    # 4. Phone bridge (optional)
    if getattr(args, "phone", False):
        start_background(
            "phone bridge",
            ["python3.11", str(SRC_DIR / "voice" / "phone_bridge.py")],
        )
        print("    Phone WS:   ws://0.0.0.0:8767")
        print("    Phone HTTP: http://0.0.0.0:8768")

    # 5. Compositor + overlay (optional)
    if getattr(args, "overlay", False):
        start_background(
            "compositor daemon",
            ["python3.11", str(SRC_DIR / "compositor" / "daemon.py")],
        )
        # Launch overlay browser after short delay
        time.sleep(2)
        _launch_overlay()

    # 6. Desktop bridge — translates gestures to KDE/GNOME desktop actions
    if getattr(args, "desktop", False):
        start_background(
            "desktop bridge",
            ["python3.11", str(SRC_DIR / "desktop" / "kde_bridge.py")],
            wait_secs=1.5,  # gesture engine must be up first
        )

    print()
    print(f"  Config: {conf}")
    print()

    # ── Check for saved session (tmux-resurrect) ────────────────────────────
    sys.path.insert(0, str(SRC_DIR))
    try:
        from status.session_restore import latest_resurrect_file  # type: ignore

        saved_file = latest_resurrect_file()
        if saved_file:
            import os as _os

            age_s = time.time() - _os.path.getmtime(saved_file)
            age_m = int(age_s // 60)
            print(
                f"  Found resurrect save ({age_m}m old) — agents will re-launch after restore"
            )
            print(
                f"  → Use Ctrl+A Ctrl+R to restore layout, then `gmux restore` for agents"
            )
    except Exception:
        pass
    print()

    # Create tmux session detached first so we can apply overrides
    print("Creating tmux session (detached)...")
    subprocess.run(["tmux", "new-session", "-d", "-s", SESSION_NAME, "-f", str(conf)])
    # Wait a moment for TPM to finish loading (it runs async)
    time.sleep(2)

    # Apply gmux status overrides AFTER TPM has loaded
    print("Applying gmux status bar overrides...")
    apply_status_overrides(SESSION_NAME)

    # Now attach to the session (this blocks until user exits)
    print(f"Attaching to session '{SESSION_NAME}'...")
    subprocess.run(["tmux", "attach-session", "-t", SESSION_NAME])

    # After tmux exits, clean up
    cleanup()


def _launch_overlay():
    """Launch Chromium overlay browser."""
    overlay_url = f"http://localhost:9000"
    browsers = ["chromium", "chromium-browser", "google-chrome", "brave"]
    for browser in browsers:
        try:
            subprocess.Popen(
                [
                    browser,
                    f"--app={overlay_url}",
                    "--kiosk",
                    "--disable-infobars",
                    "--allow-insecure-localhost",
                    "--disable-web-security",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  ✓ overlay browser ({browser})")
            return
        except FileNotFoundError:
            continue
    print("  ✗ overlay browser: no browser found (tried chromium, brave)")


def cmd_attach(args):
    """Attach to existing gmux session."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", SESSION_NAME],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"No gmux session '{SESSION_NAME}'. Start one with 'gmux'.")
        sys.exit(1)
    subprocess.run(["tmux", "attach-session", "-t", SESSION_NAME])


def cmd_list(args):
    """List gmux sessions with AI pane states."""
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}: #{session_windows} windows"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("No tmux sessions running.")
        return

    print("Sessions:")
    print(result.stdout)

    # Show pane states if available
    state_file = Path("/tmp/gmuxtest-pane-state.json")
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            _print_pane_states(data)
        except (json.JSONDecodeError, KeyError):
            pass


def cmd_status(args):
    """Show current pane states (one-shot)."""
    state_file = Path("/tmp/gmuxtest-pane-state.json")
    if not state_file.exists():
        print("No status data. Is gmux running? (python3.11 src/status/monitor.py)")
        # Run once to get current state
        result = subprocess.run(
            ["python3.11", str(SRC_DIR / "status" / "monitor.py"), "--once"],
            capture_output=True,
            text=True,
            cwd=str(SRC_DIR),
        )
        print(result.stdout)
        return

    try:
        data = json.loads(state_file.read_text())
        _print_pane_states(data)
    except Exception as e:
        print(f"Error reading state: {e}")


def _print_pane_states(data: dict):
    """Pretty-print pane states."""
    icons = {
        "waiting": "🔴",
        "working": "🟢",
        "done": "🔵",
        "idle": "🟡",
        "error": "❌",
    }
    print("AI Pane States:")
    for pane_id, info in sorted(
        data.items(), key=lambda x: x[1].get("window_index", 0)
    ):
        state = info.get("state", "idle")
        icon = icons.get(state, "?")
        name = info.get("window_name", "?")
        cmd = info.get("foreground_cmd", "?")
        win = info.get("window_index", "?")
        last = info.get("last_line", "")[:60]
        print(f"  {icon} [{win}:{name}] {cmd} → {state}")
        if last:
            print(f"       {last}")


def cmd_calibrate(args):
    """Run projector calibration."""
    sys.path.insert(0, str(SRC_DIR))
    from projector.calibration import InteractiveCalibrator

    cal = InteractiveCalibrator()
    cal.run()


def cmd_tui(args):
    """Launch the interactive TUI dashboard."""
    sys.path.insert(0, str(SRC_DIR))
    from tui import run

    run()


def cmd_gesture_debug(args):
    """Launch the live gesture event terminal viewer."""
    sys.path.insert(0, str(SRC_DIR))
    from gesture.debug_view import run  # type: ignore[import]

    run()


def cmd_desktop(args):
    """Run the desktop gesture bridge standalone (KDE/GNOME/generic)."""
    sys.path.insert(0, str(SRC_DIR))
    from desktop.kde_bridge import main as _desktop_main  # type: ignore[import]

    _desktop_main()


def cmd_restore(args):
    """Re-launch qalcode2 agents from last tmux-resurrect save."""
    sys.path.insert(0, str(SRC_DIR))
    from status.session_restore import run_hook, show_check

    if getattr(args, "check", False):
        show_check()
    else:
        run_hook()


def cmd_names(args):
    """Rename all windows to their project directory names."""
    sys.path.insert(0, str(SRC_DIR))
    from status.session_restore import (
        latest_resurrect_file,
        parse_resurrect,
        rename_windows,
    )

    f = latest_resurrect_file()
    if not f:
        print("No resurrect save file found. Save with: Ctrl+A Ctrl+S")
        return
    panes = parse_resurrect(f)
    n = rename_windows(panes)
    print(f"Renamed {n} windows to project names.")


def main():
    parser = argparse.ArgumentParser(
        description="gmux — gesture-aware terminal multiplexer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  gmux tui                 # interactive dashboard (live agent states)
  gmux status              # quick pane state dump
  gmux restore             # re-launch agents from last saved session
  gmux restore --check     # preview what would be restored
  gmux names               # rename windows to project names
  gmux attach              # re-attach to running session
  gmux list                # list sessions + AI states
  gmux calibrate           # projector corner calibration

Start flags (no subcommand):
  gmux                     # full mode: gesture + voice + status bar
  gmux --status-only       # just the AI status bar (no webcam/mic)
  gmux --no-gesture        # voice + status only
  gmux --phone             # enable phone remote (WS :8767, HTTP :8768)
  gmux --desktop           # enable KDE/GNOME desktop gesture bridge
  gmux desktop             # run desktop bridge standalone (no tmux session)
""",
    )
    sub = parser.add_subparsers(dest="command")

    # ── start (default) ──────────────────────────────────────────────────────
    start_p = sub.add_parser("start", help="Start new gmux session")
    start_p.add_argument(
        "--gesture",
        action="store_true",
        help="Enable standalone Python gesture engine (CAUTION: may grab camera exclusively)",
    )
    start_p.add_argument(
        "--no-gesture",
        action="store_true",
        help="[deprecated — gesture is now OFF by default]",
    )
    start_p.add_argument("--no-voice", action="store_true")
    start_p.add_argument("--status-only", action="store_true")
    start_p.add_argument("--phone", action="store_true")
    start_p.add_argument("--overlay", action="store_true")
    start_p.add_argument("--projector", action="store_true")
    start_p.add_argument(
        "--desktop",
        action="store_true",
        help="Enable desktop gesture bridge (KDE/GNOME/generic)",
    )
    start_p.add_argument("--session", default=SESSION_NAME)

    # ── subcommands ──────────────────────────────────────────────────────────
    sub.add_parser("tui", help="Interactive TUI dashboard")
    sub.add_parser("attach", help="Attach to existing gmux session")
    sub.add_parser("list", help="List sessions with AI states")
    sub.add_parser("status", help="Show current pane states")
    sub.add_parser("names", help="Rename windows to project names")
    sub.add_parser("calibrate", help="Projector calibration")
    sub.add_parser("help-pane", help="Print full gmux help (for tmux pane display)")
    sub.add_parser("gesture-debug", help="Live gesture event terminal viewer")
    sub.add_parser(
        "desktop",
        help="Run desktop gesture bridge standalone (KDE/GNOME/generic)",
    )

    restore_p = sub.add_parser(
        "restore", help="Re-launch agents from last saved session"
    )
    restore_p.add_argument(
        "--check", action="store_true", help="Preview only, don't restore"
    )

    args = parser.parse_args()

    if args.command == "help-pane":
        cmd_help_pane(args)
    elif args.command == "gesture-debug":
        cmd_gesture_debug(args)
    elif args.command == "desktop":
        cmd_desktop(args)
    elif args.command == "tui":
        cmd_tui(args)
    elif args.command == "attach":
        cmd_attach(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "names":
        cmd_names(args)
    elif args.command == "calibrate":
        cmd_calibrate(args)
    elif args.command == "restore":
        cmd_restore(args)
    else:
        # Default: start (handle flags directly without 'start' subcommand)
        if not hasattr(args, "no_gesture"):
            start_p_args = argparse.Namespace(
                no_gesture="--no-gesture" in sys.argv,
                no_voice="--no-voice" in sys.argv,
                status_only="--status-only" in sys.argv,
                phone="--phone" in sys.argv,
                overlay="--overlay" in sys.argv,
                projector="--projector" in sys.argv,
                desktop="--desktop" in sys.argv,
                session=SESSION_NAME,
            )
            cmd_start(start_p_args)
        else:
            cmd_start(args)


if __name__ == "__main__":
    main()
