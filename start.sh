#!/usr/bin/env bash
# राहुल वॉयस असिस्टेंट (OmniVoice) — start (or reuse running) server, then open the panel.
# Safe to re-run anytime: if a server already listens on :8000 it waits for it
# instead of spawning a duplicate. First run creates the omnivoice-env venv and
# installs dependencies (takes a few minutes the first time).
set -e
cd "$(dirname "$0")"

PORT="$(grep -E '^VOICE_PORT=' .env 2>/dev/null | head -1 | cut -d= -f2 | tr -d '\"\"')"
PORT="${PORT:-8000}"
URL="http://127.0.0.1:$PORT"
LOG="/tmp/voice-api.log"
PYTHON="./omnivoice-env/bin/python"

# hf_xet downloads stall on this network — always use classic HTTP for weights.
export HF_HUB_DISABLE_XET=1

# Install the OmniVoice runtime the first time (mirrors the Kaggle
# `!pip install -q omnivoice torchaudio`, plus the web-server deps).
if [ ! -x "$PYTHON" ]; then
  echo "🛠️  First run — creating omnivoice-env and installing OmniVoice..."
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 omnivoice-env
    uv pip install --python "$PYTHON" -r requirements.txt
  else
    python3 -m venv omnivoice-env
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r requirements.txt
  fi
fi

health_ok() { curl -s -m 3 "$URL/health" >/dev/null 2>&1; }

if health_ok; then
  echo "✅ Voice assistant already running — opening $URL"
  open "$URL"
  exit 0
fi

# Port busy but not healthy yet (e.g. model still loading)? Wait for it.
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "⏳ Server is starting on :8000 — waiting for it to become ready..."
  for _ in $(seq 1 60); do
    if health_ok; then
      echo "✅ Server ready — opening $URL"
      open "$URL"
      exit 0
    fi
    sleep 2
  done
  echo "❌ Port 8000 is busy but the server never became healthy." >&2
  echo "   Check the log: tail -f /tmp/voice-api.log" >&2
  exit 1
fi

echo "🚀 Starting voice assistant server (OmniVoice model load ~30-60s first time)..."
nohup "$PYTHON" voice_api.py >> "$LOG" 2>&1 &

for _ in $(seq 1 90); do
  if health_ok; then
    echo "✅ Server ready — opening $URL"
    open "$URL"
    exit 0
  fi
  sleep 2
done

echo "❌ Server failed to start. Last log lines:" >&2
tail -n 25 "$LOG" >&2
exit 1
