#!/usr/bin/env python3.11
"""
gmux_voice_daemon.py — Standalone faster-whisper STT daemon for gmux UI

Captures mic audio, transcribes with faster-whisper, streams results to
the gmux UI via WebSocket (ws://localhost:8770).

No silero VAD dependency — uses simple energy-based voice activity detection.

Pipeline:
  Mic → energy VAD → chunk buffer → faster-whisper → WebSocket → UI

WebSocket protocol (JSON messages sent to all connected clients):
  {"type":"partial", "text":"word so far"}
  {"type":"final",   "text":"complete utterance"}
  {"type":"status",  "state":"listening"|"processing"|"idle"}
  {"type":"error",   "msg":"..."}

Usage:
  python3.11 gmux_voice_daemon.py                    # default (tiny model)
  python3.11 gmux_voice_daemon.py --model base       # more accurate
  python3.11 gmux_voice_daemon.py --model small      # best balance
  python3.11 gmux_voice_daemon.py --device 0         # specific mic index
  python3.11 gmux_voice_daemon.py --port 8770        # WebSocket port
  python3.11 gmux_voice_daemon.py --lang en           # language (auto-detect if omitted)
  python3.11 gmux_voice_daemon.py --continuous        # transcribe everything (no silence gaps)

Connects to the gmux UI voice strip automatically when voice mode is active.
"""

import argparse
import asyncio
import json
import logging
import platform
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import websockets
from faster_whisper import WhisperModel

# ── Platform detection ────────────────────────────────────────────────────────
_IS_MACOS = platform.system() == "Darwin"


def _check_audio_backend() -> None:
    """Optional preflight: verify an audio backend is reachable.

    On Linux, PulseAudio / PipeWire is commonly verified via `pactl info`.
    On macOS, CoreAudio is always present — no equivalent check needed.
    sounddevice uses PortAudio which transparently wraps CoreAudio on macOS
    and PulseAudio/PipeWire/ALSA on Linux, so if sounddevice imports cleanly
    the audio backend is almost certainly functional.

    We run this check in a try/except so it NEVER prevents the daemon from
    starting. A failed pactl on Linux is just a warning; on macOS we skip it
    entirely.
    """
    if _IS_MACOS:
        # CoreAudio is built into macOS — no daemon/service to check.
        log.debug("[audio] macOS CoreAudio backend (via PortAudio) assumed present")
        return

    # Linux only: try pactl as an advisory check
    try:
        result = subprocess.run(
            ["pactl", "info"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            log.debug("[audio] PulseAudio/PipeWire confirmed via pactl")
        else:
            log.warning(
                "[audio] pactl info returned non-zero — PulseAudio may be unavailable. "
                "sounddevice will fall back to ALSA if present."
            )
    except FileNotFoundError:
        log.warning(
            "[audio] pactl not found — assuming PipeWire-native or ALSA. "
            "sounddevice will try to open the default device anyway."
        )
    except Exception as e:
        log.warning(f"[audio] pactl check failed: {e} — continuing anyway")


# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000  # whisper always expects 16kHz
CHUNK_MS = 200  # read from mic every 200ms
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)
SILENCE_THRESH = 0.008  # RMS energy threshold for voice activity
SILENCE_GAP_S = 0.8  # seconds of silence before we transcribe
MAX_BUFFER_S = 15.0  # max single utterance length before forced transcribe
MIN_SPEECH_S = 0.3  # minimum speech duration to bother transcribing

log = logging.getLogger("gmux-voice")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ── WebSocket server ──────────────────────────────────────────────────────────
_ws_clients: set = set()
_ws_loop: Optional[asyncio.AbstractEventLoop] = None


async def _ws_handler(ws):
    _ws_clients.add(ws)
    log.info(f"[ws] client connected ({len(_ws_clients)} total)")
    try:
        async for _ in ws:
            pass  # we don't read from clients, only push to them
    finally:
        _ws_clients.discard(ws)
        log.info(f"[ws] client disconnected ({len(_ws_clients)} remaining)")


def _broadcast(msg: dict):
    """Thread-safe broadcast to all connected WS clients."""
    if not _ws_clients or _ws_loop is None:
        return
    data = json.dumps(msg)
    asyncio.run_coroutine_threadsafe(_do_broadcast(data), _ws_loop)


async def _do_broadcast(data: str):
    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send(data)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


async def _run_ws_server(port: int):
    global _ws_loop
    _ws_loop = asyncio.get_event_loop()
    log.info(f"[ws] WebSocket server listening on ws://0.0.0.0:{port}")
    async with websockets.serve(_ws_handler, "0.0.0.0", port):
        await asyncio.Future()  # run forever


# ── Audio capture + VAD ───────────────────────────────────────────────────────


class VoiceCapture:
    def __init__(self, device: Optional[int], sample_rate: int):
        self.device = device
        self.sample_rate = sample_rate
        self._q: queue.Queue = queue.Queue()
        self._stream = None

    def start(self):
        self._stream = sd.InputStream(
            device=self.device,
            channels=1,
            samplerate=self.sample_rate,
            blocksize=CHUNK_SAMPLES,
            dtype="float32",
            callback=self._cb,
        )
        self._stream.start()
        log.info(
            f"[mic] started — device={self.device or 'default'} "
            f"rate={self.sample_rate}Hz chunk={CHUNK_MS}ms"
        )

    def _cb(self, indata, frames, time_info, status):
        if status:
            log.warning(f"[mic] {status}")
        self._q.put(indata[:, 0].copy())  # mono

    def read(self, timeout=0.5) -> Optional[np.ndarray]:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()


# ── Transcription worker ──────────────────────────────────────────────────────


def transcription_loop(
    model: WhisperModel, cap: VoiceCapture, lang: Optional[str], continuous: bool
):
    """
    Reads audio chunks from VoiceCapture, detects speech via energy VAD,
    accumulates speech into buffers, transcribes with faster-whisper.
    """
    speech_buf = []  # list of float32 chunks
    silence_secs = 0.0
    in_speech = False
    speech_secs = 0.0
    chunk_secs = CHUNK_MS / 1000.0

    _broadcast({"type": "status", "state": "listening"})

    while True:
        chunk = cap.read(timeout=0.5)
        if chunk is None:
            continue

        rms = float(np.sqrt(np.mean(chunk**2)))
        is_voice = rms > SILENCE_THRESH

        if is_voice:
            speech_buf.append(chunk)
            speech_secs += chunk_secs
            silence_secs = 0.0
            if not in_speech:
                in_speech = True
                log.debug(f"[vad] speech started (rms={rms:.4f})")
        else:
            if in_speech:
                silence_secs += chunk_secs
                speech_buf.append(chunk)  # keep trailing silence in buffer

                should_transcribe = (
                    silence_secs >= SILENCE_GAP_S or speech_secs >= MAX_BUFFER_S
                )
                if should_transcribe:
                    if speech_secs >= MIN_SPEECH_S:
                        _do_transcribe(model, speech_buf, lang)
                    speech_buf = []
                    speech_secs = 0.0
                    silence_secs = 0.0
                    in_speech = False
                    _broadcast({"type": "status", "state": "listening"})
            elif continuous:
                # Continuous mode: even silence chunks go to buffer
                speech_buf.append(chunk)
                speech_secs += chunk_secs
                if speech_secs >= 3.0:
                    if speech_secs >= MIN_SPEECH_S:
                        _do_transcribe(model, speech_buf, lang)
                    speech_buf = []
                    speech_secs = 0.0


def _do_transcribe(model: WhisperModel, chunks: list, lang: Optional[str]):
    """Run faster-whisper on accumulated audio chunks and broadcast result."""
    audio = np.concatenate(chunks).astype(np.float32)
    log.info(f"[whisper] transcribing {len(audio) / SAMPLE_RATE:.1f}s of audio…")
    _broadcast({"type": "status", "state": "processing"})

    try:
        segments, info = model.transcribe(
            audio,
            language=lang,
            beam_size=5,
            vad_filter=True,  # whisper's own VAD post-filter
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
            word_timestamps=False,
            condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        if text:
            log.info(f'[whisper] → "{text}"')
            _broadcast({"type": "final", "text": text, "lang": info.language})
        else:
            log.debug("[whisper] empty result (silence/noise)")
    except Exception as e:
        log.error(f"[whisper] error: {e}")
        _broadcast({"type": "error", "msg": str(e)})


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="gmux voice daemon — faster-whisper STT"
    )
    parser.add_argument(
        "--model",
        default="tiny",
        help="Whisper model: tiny/base/small/medium (default: tiny)",
    )
    parser.add_argument(
        "--device",
        default=None,
        type=int,
        help="Mic device index (default: system default)",
    )
    parser.add_argument(
        "--port", default=8770, type=int, help="WebSocket port (default: 8770)"
    )
    parser.add_argument(
        "--lang", default=None, help="Language code e.g. en (default: auto-detect)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Transcribe continuously without VAD gating",
    )
    parser.add_argument(
        "--compute",
        default="int8",
        help="Compute type: int8/float16/float32 (default: int8)",
    )
    parser.add_argument(
        "--list-devices", action="store_true", help="List audio devices and exit"
    )
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        sys.exit(0)

    # Advisory audio backend check — never fatal; macOS skips pactl entirely.
    _check_audio_backend()

    log.info(f"[gmux-voice] loading model '{args.model}' (compute={args.compute})…")
    model = WhisperModel(
        args.model,
        device="cpu",
        compute_type=args.compute,
    )
    log.info("[gmux-voice] model ready")

    cap = VoiceCapture(device=args.device, sample_rate=SAMPLE_RATE)
    cap.start()

    # Transcription in a background thread
    t = threading.Thread(
        target=transcription_loop,
        args=(model, cap, args.lang, args.continuous),
        daemon=True,
        name="transcription",
    )
    t.start()

    log.info(f"[gmux-voice] ready — ws://127.0.0.1:{args.port}")
    log.info(f"[gmux-voice] speak into mic (device={args.device or 'default'})")
    log.info("[gmux-voice] Ctrl+C to stop")

    try:
        asyncio.run(_run_ws_server(args.port))
    except KeyboardInterrupt:
        log.info("[gmux-voice] shutting down")
        cap.stop()


if __name__ == "__main__":
    main()
