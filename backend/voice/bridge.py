#!/usr/bin/env python3.11
"""
voice/bridge.py — Bridges voice_daemon.py to gmux/tmux.

Connects to voice daemon WebSocket (ws://localhost:8770).
Routes transcripts and commands to the focused tmux pane.

PHONE INTEGRATION:
  This bridge also listens on a second WebSocket port (:8767) for incoming
  voice commands from the phone bridge (phone_bridge.py).
  This allows you to control tmux/AI from your phone's microphone.

  Phone flow:
    Phone mic → WhatsApp/Signal → minirig → phone_bridge.py → ws://superlocal:8767
    → voice bridge → tmux → AI pane

  Or direct:
    Phone → HTTP POST /voice  → voice bridge → tmux

Voice commands for tmux navigation:
  "next window"      → tmux select-window -n
  "previous window"  → tmux select-window -p
  "split horizontal" → tmux split-window -h
  "split vertical"   → tmux split-window -v
  "close pane"       → tmux kill-pane
  "next red"         → jump to next pane waiting for input
  "zoom"             → tmux resize-pane -Z (toggle zoom)
  "cancel" / "stop"  → tmux send-keys C-c
  "window 1" ... "window 9" → switch to numbered window

AI commands:
  "kalarc [query]"   → types query into focused AI pane
  "kal arc [query]"  → same (whisper sometimes hears it this way)
  "qalarc [query]"   → same

Editor commands (when editor pane is active):
  "save"             → :w
  "undo"             → u
  "go to line N"     → :NEnter

Terminal commands:
  "run"              → Enter
  "run tests"        → pytest -xvs
  "clear"            → Ctrl+L
"""

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

# Ensure src/ is on path so sibling modules import correctly
_SRC = Path(__file__).parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Voice daemon WS (existing voice pipeline)
VOICE_WS_URL = "ws://localhost:8770"  # alpha.20: was :8765 — wrong port; daemon listens on :8770 (see gmux_voice_daemon.py:304)

# Phone bridge WS (we listen on this for phone commands)
PHONE_BRIDGE_PORT = 8767

# HTTP port for phone UI
HTTP_PORT = 8768

# State file for pane state
STATE_FILE = Path("/tmp/gmuxtest-pane-state.json")

# Path to the phone PWA UI
PHONE_HTML = Path(__file__).parent.parent / "overlay" / "phone.html"

# Connected WS clients — we push state to all of them live
_ws_clients: set = set()

# Wake words (all phonetic variations whisper/people use)
WAKE_WORDS = {
    "kalarc",
    "kal arc",
    "cal arc",
    "qalarc",
    "qal arc",
    "kalarck",
    "kalark",
    "calarc",
    "kal-arc",
}

# Voice → tmux command mapping (longest match wins)
TMUX_COMMANDS = {
    "next window": ["tmux", "select-window", "-n"],
    "next": ["tmux", "select-window", "-n"],
    "previous window": ["tmux", "select-window", "-p"],
    "previous": ["tmux", "select-window", "-p"],
    "split horizontal": ["tmux", "split-window", "-h"],
    "split vertical": ["tmux", "split-window", "-v"],
    "split": ["tmux", "split-window", "-h"],
    "close pane": ["tmux", "kill-pane"],
    "close": ["tmux", "kill-pane"],
    "zoom": ["tmux", "resize-pane", "-Z"],
    "focus left": ["tmux", "select-pane", "-L"],
    "focus right": ["tmux", "select-pane", "-R"],
    "focus up": ["tmux", "select-pane", "-U"],
    "focus down": ["tmux", "select-pane", "-D"],
    "new window": ["tmux", "new-window"],
    "clear": ["tmux", "send-keys", "C-l"],
    "cancel": ["tmux", "send-keys", "C-c"],
    "stop": ["tmux", "send-keys", "C-c"],
    "run": ["tmux", "send-keys", "Enter"],
    "run it": ["tmux", "send-keys", "Enter"],
    "run tests": ["tmux", "send-keys", "pytest -xvs", "Enter"],
    "save": None,  # handled in code (context-aware)
    "undo": None,
    "redo": None,
    "scroll up": ["tmux", "send-keys", "-X", "scroll-up"],
    "scroll down": ["tmux", "send-keys", "-X", "scroll-down"],
}

# "window N" pattern
WINDOW_PATTERN = re.compile(r"^window\s+([1-9])$", re.IGNORECASE)

# "go to line N" pattern
GOTO_LINE_PATTERN = re.compile(r"go to line\s+(\d+)", re.IGNORECASE)


def run_tmux(args: list[str]):
    """Execute tmux command."""
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_focused_pane() -> tuple[str, str]:
    """Returns (pane_id, pane_cmd) for the currently focused tmux pane."""
    try:
        out = subprocess.check_output(
            ["tmux", "display-message", "-p", "#{pane_id}|#{pane_current_command}"],
            text=True,
            timeout=1,
        ).strip()
        pane_id, cmd = out.split("|", 1)
        return pane_id, cmd
    except Exception:
        return "", ""


def get_ai_pane() -> str:
    """Find the pane_id of an AI agent pane (qalcode, claude, etc.)."""
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        return ""

    # Prefer WAITING (needs input) then WORKING
    for priority_state in ("waiting", "working", "done"):
        for pane_id, info in data.items():
            if info.get("has_ai") and info.get("state") == priority_state:
                return pane_id

    # Fallback: any pane with AI
    for pane_id, info in data.items():
        if info.get("has_ai"):
            return pane_id

    return ""


def find_next_red_pane() -> str:
    """Return window_index of the next WAITING (RED) pane."""
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        return ""

    try:
        current = int(
            subprocess.check_output(
                ["tmux", "display-message", "-p", "#{window_index}"],
                text=True,
                timeout=1,
            ).strip()
        )
    except Exception:
        current = 0

    waiting = sorted(
        [i for i in data.values() if i.get("state") == "waiting"],
        key=lambda x: x.get("window_index", 0),
    )
    if not waiting:
        return ""

    for w in waiting:
        if w.get("window_index", 0) > current:
            return str(w["window_index"])
    return str(waiting[0]["window_index"])  # wrap around


def type_into_pane(text: str, pane_id: str = ""):
    """Type text into a tmux pane, sending it as literal keystrokes."""
    target = ["-t", pane_id] if pane_id else []
    subprocess.run(
        ["tmux", "send-keys"] + target + ["--", text, "Enter"],
        capture_output=True,
    )


def handle_transcript(text: str, source: str = "voice") -> bool:
    """
    Route a voice transcript to the right action.
    Returns True if handled, False if not recognised.
    """
    text_lower = text.lower().strip()
    print(f'[gmux-voice] [{source}] "{text}"', flush=True)

    # ── Wake word → AI query ────────────────────────────────────────────────
    for wake in sorted(WAKE_WORDS, key=len, reverse=True):
        if text_lower.startswith(wake):
            query = text[len(wake) :].strip().lstrip(",:; ")
            if query:
                pane = get_ai_pane()
                if pane:
                    print(f'  → AI pane {pane}: "{query}"', flush=True)
                    type_into_pane(query, pane)
                else:
                    # No dedicated AI pane — type into focused pane
                    print(f'  → focused pane: "{query}"', flush=True)
                    type_into_pane(query)
            return True

    # ── "next red" / "next waiting" ─────────────────────────────────────────
    if text_lower in ("next red", "next waiting", "next input", "jump to waiting"):
        target = find_next_red_pane()
        if target:
            run_tmux(["tmux", "select-window", "-t", target])
            print(f"  → jump to RED window {target}", flush=True)
        else:
            print("  → no RED/waiting panes", flush=True)
        return True

    # ── "window N" ──────────────────────────────────────────────────────────
    m = WINDOW_PATTERN.match(text_lower)
    if m:
        run_tmux(["tmux", "select-window", "-t", m.group(1)])
        print(f"  → window {m.group(1)}", flush=True)
        return True

    # ── "go to line N" ──────────────────────────────────────────────────────
    m = GOTO_LINE_PATTERN.search(text_lower)
    if m:
        pane_id, cmd = get_focused_pane()
        line = m.group(1)
        run_tmux(["tmux", "send-keys", f":{line}", "Enter"])
        print(f"  → go to line {line}", flush=True)
        return True

    # ── Tmux navigation commands ─────────────────────────────────────────────
    for phrase in sorted(TMUX_COMMANDS.keys(), key=len, reverse=True):
        if text_lower == phrase or text_lower.startswith(phrase + " "):
            cmd = TMUX_COMMANDS[phrase]
            if cmd is None:
                # Context-aware commands
                pane_id, pane_cmd = get_focused_pane()
                if phrase == "save":
                    run_tmux(["tmux", "send-keys", ":w", "Enter"])
                elif phrase == "undo":
                    run_tmux(["tmux", "send-keys", "u", ""])
                elif phrase == "redo":
                    run_tmux(["tmux", "send-keys", "C-r"])
                print(f"  → {phrase}", flush=True)
            else:
                subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                print(f"  → tmux: {' '.join(cmd[1:])}", flush=True)
            return True

    return False  # Not recognised


# ── Voice daemon connection ───────────────────────────────────────────────────


async def connect_voice_daemon():
    """Connect to voice daemon and process transcript events."""
    try:
        import websockets
    except ImportError:
        print(
            "[gmux-voice] websockets not installed. pip install websockets",
            file=sys.stderr,
        )
        return

    print(f"[gmux-voice] Connecting to voice daemon at {VOICE_WS_URL}", flush=True)

    _logged_unavailable = False
    while True:
        try:
            async with websockets.connect(VOICE_WS_URL) as ws:
                _logged_unavailable = False
                print("[gmux-voice] Connected to voice daemon.", flush=True)

                async for message in ws:
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")

                        if msg_type == "transcript":
                            text = data.get("text", "").strip()
                            if text:
                                handle_transcript(text, source="mic")

                        elif msg_type == "response_chunk":
                            pass  # AI response streaming

                        elif msg_type == "response_done":
                            pass  # AI finished — status monitor picks this up

                    except json.JSONDecodeError:
                        continue

        except (ConnectionRefusedError, OSError):
            if not _logged_unavailable:
                print(
                    "[gmux-voice] Voice daemon not running — will retry silently.",
                    flush=True,
                )
                print(
                    "[gmux-voice] Start it: python3.11 ~/projects/claude_TUI/voice_daemon.py",
                    flush=True,
                )
                _logged_unavailable = True
            await asyncio.sleep(10)
        except Exception as e:
            err = str(e)
            # Don't spam 403 from unrelated servers on same port
            if "403" not in err and "rejected" not in err:
                print(f"[gmux-voice] Error: {e}", flush=True)
            elif not _logged_unavailable:
                print(
                    f"[gmux-voice] Port {VOICE_WS_URL} has wrong service (403) — voice daemon not started",
                    flush=True,
                )
                _logged_unavailable = True
            await asyncio.sleep(10)


# ── WS broadcast helpers ──────────────────────────────────────────────────────


def _pane_summary() -> list[dict]:
    """Return phone-friendly pane summary list."""
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        return []
    icons = {
        "waiting": "🔴",
        "working": "🟢",
        "permission": "🟠",
        "done": "🔵",
        "error": "❌",
        "not_started": "─",
        "idle": "🟡",
    }
    summary = []
    for pane_id, info in sorted(
        data.items(), key=lambda x: x[1].get("window_index", 0)
    ):
        state = info.get("state", "idle")
        summary.append(
            {
                "pane_id": pane_id,
                "window": info.get("window_index", "?"),
                "name": info.get("window_name", "?"),
                "state": state,
                "icon": icons.get(state, "?"),
                "has_ai": info.get("has_ai", False),
                "last_line": info.get("last_line", ""),
                "todo_done": info.get("todo_done", 0),
                "todo_total": info.get("todo_total", 0),
                "current_tool": info.get("current_tool", ""),
            }
        )
    return summary


# ── Gesture event routing (from browser HUD) ─────────────────────────────────

import time as _time

_gesture_last_fired: dict[str, float] = {}  # gesture_key → last fire timestamp
_GESTURE_COOLDOWN = 0.8  # seconds between same gesture firing

# Confidence thresholds per mode
_THRESHOLDS = {
    "active": 0.72,  # deliberate gesture mode — responsive
    "passive": 0.90,  # typing/idle — only very clear gestures
}


def _handle_gesture_event(
    static: str,
    motion: str,
    confidence: float,
    mode: str,
    index_x: float,
    index_y: float,
) -> str | None:
    """
    Route a gesture event from the browser HUD to a tmux action.

    Returns a description of the action taken, or None if ignored.

    Two-mode system:
      passive — high threshold, only thumbs/hold gestures (not swipes)
      active  — normal threshold, all gestures
    """
    threshold = _THRESHOLDS.get(mode, 0.90)
    if confidence < threshold:
        return None

    # Cooldown: don't fire same gesture twice in quick succession
    gesture_key = f"{static}_{motion}"
    now = _time.time()
    last = _gesture_last_fired.get(gesture_key, 0)
    if now - last < _GESTURE_COOLDOWN:
        return None

    # In passive mode, ignore swipes (too easy to trigger accidentally)
    if mode == "passive" and motion in (
        "swipe_left",
        "swipe_right",
        "swipe_up",
        "swipe_down",
    ):
        return None

    action = None

    # ── Motion gestures (swipes) ──
    if motion == "swipe_right":
        subprocess.run(["tmux", "select-window", "-n"], capture_output=True)
        action = "win:next"
    elif motion == "swipe_left":
        subprocess.run(["tmux", "select-window", "-p"], capture_output=True)
        action = "win:prev"
    elif motion == "swipe_up":
        subprocess.run(["tmux", "select-pane", "-U"], capture_output=True)
        action = "pane:up"
    elif motion == "swipe_down":
        subprocess.run(["tmux", "select-pane", "-D"], capture_output=True)
        action = "pane:down"

    # ── Static gestures ──
    elif static == "three" and motion == "none":
        # Jump to next waiting (RED) agent
        subprocess.run(
            [
                "python3.11",
                str(Path(__file__).parent.parent / "status" / "jump_red.py"),
            ],
            capture_output=True,
        )
        action = "jump:RED"

    elif static == "thumbs_up" and motion == "none":
        subprocess.run(["tmux", "send-keys", "y", "Enter"], capture_output=True)
        action = "confirm:y"

    elif static == "thumbs_down" and motion == "none":
        subprocess.run(["tmux", "send-keys", "C-c", ""], capture_output=True)
        action = "cancel:ctrl-c"

    elif static == "peace" and motion == "none":
        # Toggle voice listening
        action = "voice:toggle"
        # Broadcast toggle to all WS clients
        # (handled async — can't await here, fire-and-forget)

    elif static == "open_palm" and motion == "none":
        # Open palm held = gesture mode activation signal
        # The HUD handles the mode switch itself, we just ack
        action = "mode:active"

    if action:
        _gesture_last_fired[gesture_key] = now
        print(
            f"[gmux-gesture] {static}/{motion} ({confidence:.2f}) → {action}",
            flush=True,
        )

    return action


def _get_pane_layout() -> list[dict]:
    """
    Return pixel rectangles for every visible tmux pane.
    Uses tmux list-panes for character positions, xdotool for terminal pixel size.
    Falls back to a full-screen estimate if xdotool can't find the window.
    """
    import re, shutil

    # ── Get panes in character coords ────────────────────────────────────────
    try:
        raw = subprocess.check_output(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{pane_id} #{pane_left} #{pane_top} #{pane_width} #{pane_height} "
                "#{window_index} #{pane_current_command} #{?pane_active,active,}",
            ],
            text=True,
            timeout=2,
        ).strip()
    except Exception:
        return []

    lines = [l for l in raw.splitlines() if l.strip()]
    if not lines:
        return []

    # ── Get terminal window pixel size ────────────────────────────────────────
    cols, rows = shutil.get_terminal_size((220, 50))
    win_w, win_h = 1920, 1080  # safe fallback

    # Try xdotool — search for common terminal window titles
    try:
        search_terms = [
            "Konsole",
            "kitty",
            "Alacritty",
            "foot",
            "wezterm",
            "gnome-terminal",
            "xterm",
        ]
        for term in search_terms:
            r = subprocess.run(
                ["xdotool", "search", "--name", term],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if r.returncode == 0 and r.stdout.strip():
                wid = r.stdout.strip().split()[0]
                geo = subprocess.check_output(
                    ["xdotool", "getwindowgeometry", "--shell", wid],
                    text=True,
                    timeout=1,
                )
                wm = re.search(r"WIDTH=(\d+)", geo)
                hm = re.search(r"HEIGHT=(\d+)", geo)
                if wm and hm:
                    win_w = int(wm.group(1))
                    win_h = int(hm.group(1))
                    break
    except Exception:
        pass  # use fallback

    char_w = win_w / max(cols, 1)
    char_h = win_h / max(rows, 1)

    # ── Load agent state for colour info ─────────────────────────────────────
    state_map = _load_state_file()

    # ── Build pixel layout list ───────────────────────────────────────────────
    layout = []
    for line in lines:
        parts = line.split()
        if len(parts) < 7:
            continue
        pane_id, left, top, pw, ph, win = parts[:6]
        active = len(parts) > 7 and parts[7] == "active"
        state = state_map.get(pane_id, {}).get("state", "idle")
        name = state_map.get(pane_id, {}).get(
            "window_name", parts[6] if len(parts) > 6 else "?"
        )
        layout.append(
            {
                "pane_id": pane_id,
                "window": int(win),
                "name": name,
                "state": state,
                "is_active": active,
                "x": int(left) * char_w,
                "y": int(top) * char_h,
                "w": int(pw) * char_w,
                "h": int(ph) * char_h,
                "todo_done": state_map.get(pane_id, {}).get("todo_done", 0),
                "todo_total": state_map.get(pane_id, {}).get("todo_total", 0),
            }
        )

    return layout


def _load_state_file() -> dict:
    """Load /tmp/gmuxtest-pane-state.json safely."""
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


async def _ws_broadcast(msg: dict):
    """Push a message to all connected phone WS clients."""
    if not _ws_clients:
        return
    raw = json.dumps(msg)
    dead = set()
    for client in list(_ws_clients):
        try:
            await client.send(raw)
        except Exception:
            dead.add(client)
    _ws_clients.difference_update(dead)


async def _ws_push_loop():
    """Push pane state to all connected phone clients every 1.5 s."""
    while True:
        await asyncio.sleep(1.5)
        if _ws_clients:
            await _ws_broadcast(
                {
                    "type": "status",
                    "panes": _pane_summary(),
                }
            )


# ── Phone bridge WebSocket server ─────────────────────────────────────────────


async def phone_bridge_server():
    """
    Listen for voice commands from phone (WS :8767).
    Pushes live pane state to all connected clients.
    """
    try:
        import websockets
    except ImportError:
        return

    print(f"[gmux-phone] WS on ws://0.0.0.0:{PHONE_BRIDGE_PORT}", flush=True)

    async def handle_phone(ws, path=""):
        client_ip = getattr(ws, "remote_address", ("?",))[0]
        print(f"[gmux-phone] connected: {client_ip}", flush=True)
        _ws_clients.add(ws)

        # Send welcome + current state immediately
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "welcome",
                        "msg": "gmux phone bridge ready",
                        "panes": _pane_summary(),
                    }
                )
            )
        except Exception:
            pass

        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "voice_command":
                        text = data.get("text", "").strip()
                        window = data.get("window")  # optional target window idx
                        if text:
                            if window is not None:
                                # Direct send to specific window
                                try:
                                    subprocess.run(
                                        [
                                            "tmux",
                                            "send-keys",
                                            "-t",
                                            f":{window}",
                                            "--",
                                            text,
                                            "Enter",
                                        ],
                                        capture_output=True,
                                        timeout=3,
                                    )
                                    handled = True
                                    print(
                                        f"[gmux-phone] → win:{window} {text!r}",
                                        flush=True,
                                    )
                                except Exception:
                                    handled = False
                            else:
                                handled = handle_transcript(
                                    text, source=f"phone:{client_ip}"
                                )
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "ack",
                                        "text": text,
                                        "handled": handled,
                                    }
                                )
                            )

                    elif msg_type == "gesture_event":
                        # From browser HUD — MediaPipe ran in the browser
                        # { type:"gesture_event", static:"open_palm", motion:"swipe_right",
                        #   confidence:0.88, index_x:0.45, index_y:0.52,
                        #   mode:"active"|"passive" }
                        static_g = data.get("static", "none")
                        motion_g = data.get("motion", "none")
                        conf = float(data.get("confidence", 0))
                        mode = data.get("mode", "passive")
                        index_x = float(data.get("index_x", 0.5))
                        index_y = float(data.get("index_y", 0.5))

                        action = _handle_gesture_event(
                            static_g, motion_g, conf, mode, index_x, index_y
                        )
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "gesture_ack",
                                    "action": action,
                                    "static": static_g,
                                    "motion": motion_g,
                                }
                            )
                        )

                    elif msg_type == "request_layout":
                        # HUD asking for pixel positions of all panes
                        layout = _get_pane_layout()
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "pane_layout",
                                    "panes": layout,
                                }
                            )
                        )

                    elif msg_type == "ping":
                        await ws.send(json.dumps({"type": "pong"}))

                    elif msg_type == "status":
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "status",
                                    "panes": _pane_summary(),
                                }
                            )
                        )

                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            _ws_clients.discard(ws)
            print(f"[gmux-phone] disconnected: {client_ip}", flush=True)

    server = await websockets.serve(handle_phone, "0.0.0.0", PHONE_BRIDGE_PORT)
    print(f"[gmux-phone] Ready.", flush=True)
    await server.wait_closed()


# ── HTTP endpoint for phone (simpler than WS for some use cases) ──────────────


async def http_phone_server():
    """
    Simple HTTP server for phone commands.

    POST /voice   body: {"text": "kalarc what is this?"}
    GET  /status  returns: pane states JSON

    Useful when the phone can't maintain a WebSocket connection.
    """
    try:
        from aiohttp import web
    except ImportError:
        print(
            "[gmux-phone-http] aiohttp not installed — HTTP endpoint disabled",
            flush=True,
        )
        return

    HTTP_PORT = 8768

    async def handle_voice_post(request):
        try:
            data = await request.json()
            text = data.get("text", "").strip()
            window = data.get("window")
            if not text:
                return web.json_response({"ok": False, "error": "no text"}, status=400)
            if window is not None:
                subprocess.run(
                    ["tmux", "send-keys", "-t", f":{window}", "--", text, "Enter"],
                    capture_output=True,
                    timeout=3,
                )
                return web.json_response(
                    {"ok": True, "handled": True, "text": text, "window": window}
                )
            handled = handle_transcript(text, source="phone-http")
            return web.json_response({"ok": True, "handled": handled, "text": text})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_status_get(request):
        return web.json_response({"panes": _pane_summary()})

    async def handle_phone_get(request):
        """Serve the phone PWA — open http://HOST:8768/phone on your phone."""
        if PHONE_HTML.exists():
            return web.Response(text=PHONE_HTML.read_text(), content_type="text/html")
        return web.Response(
            text="phone.html not found — check gmux installation", status=404
        )

    async def handle_permission_respond(request):
        """Accept/deny a permission prompt from the phone."""
        try:
            pane_id = request.match_info["pane_id"]
            data = await request.json()
            response = data.get("response", "once")
            key_map = {"once": "Enter", "always": "a", "reject": "d"}
            key = key_map.get(response, "Enter")
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, key, ""], capture_output=True
            )
            return web.json_response({"ok": True, "response": response})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_manifest(request):
        return web.json_response(
            {
                "name": "gmux",
                "short_name": "gmux",
                "description": "AI agent mission control",
                "start_url": "/phone",
                "display": "standalone",
                "background_color": "#0a0f1e",
                "theme_color": "#6c5ce7",
                "icons": [
                    {"src": "/icon.png", "sizes": "192x192", "type": "image/png"}
                ],
            }
        )

    async def handle_index(request):
        """Redirect / to /phone."""
        raise web.HTTPFound("/phone")

    app = web.Application()
    app.router.add_post("/voice", handle_voice_post)
    app.router.add_get("/status", handle_status_get)
    app.router.add_get("/phone", handle_phone_get)
    app.router.add_post("/permission/{pane_id}/respond", handle_permission_respond)
    app.router.add_get("/manifest.json", handle_manifest)
    app.router.add_get("/", handle_index)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    print(f"[gmux-phone-http] HTTP on http://0.0.0.0:{HTTP_PORT}", flush=True)
    print(
        f"  → Phone UI: http://$(hostname -I | cut -d' ' -f1):{HTTP_PORT}/phone",
        flush=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────


async def main():
    tasks = [
        asyncio.create_task(connect_voice_daemon()),
        asyncio.create_task(phone_bridge_server()),
        asyncio.create_task(http_phone_server()),
        asyncio.create_task(_ws_push_loop()),
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    # Set process name so it shows as gmux-voice in htop/system monitor
    try:
        from config import set_process_name  # type: ignore

        set_process_name("gmux-voice")
    except Exception:
        pass

    print("[gmux-voice] Voice bridge starting...", flush=True)
    print(f"  Voice daemon: {VOICE_WS_URL}")
    print(f"  Phone WS:     ws://0.0.0.0:{PHONE_BRIDGE_PORT}")
    print(f"  Phone HTTP:   http://0.0.0.0:8768")
    print()
    asyncio.run(main())
