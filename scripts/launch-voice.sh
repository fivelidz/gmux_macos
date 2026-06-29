#!/bin/bash
# gmux voice daemon launcher
# Starts faster-whisper STT daemon on ws://localhost:8770
# The gmux UI automatically connects to this when voice mode is active.
#
# Usage:
#   ./launch-voice.sh            # tiny model (fastest, loads in ~3s)
#   ./launch-voice.sh base       # base model (better accuracy, ~6s load)
#   ./launch-voice.sh small      # small model (best accuracy, ~10s load)
#   ./launch-voice.sh tiny 5     # device index 5 (SN6186 analog)
#   ./launch-voice.sh tiny 11    # device index 11 (pipewire)

MODEL=${1:-tiny}
DEVICE=${2:-11}
PORT=${3:-8770}

echo "[gmux-voice] Starting faster-whisper voice daemon"
echo "  Model:  $MODEL"
echo "  Device: $DEVICE (index — run with --list-devices to see options)"
echo "  Port:   ws://localhost:$PORT"
echo ""
echo "  The gmux UI will auto-connect when voice mode is toggled (V key)"
echo "  Speak naturally — transcription streams to the UI in real time"
echo "  Thumbs Up 👍 gesture sends the current draft to the selected agent"
echo ""
echo "  Ctrl+C to stop"
echo ""

exec python3.11 "$(dirname "$0")/src-py/voice/gmux_voice_daemon.py" \
  --model "$MODEL" \
  --device "$DEVICE" \
  --port "$PORT" \
  --lang en
