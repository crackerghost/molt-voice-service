"""Backward-compatible application entrypoint.

The 2255-line god file that lived here is now split into focused modules::

    server/config.py          env/.env/device configuration (VoiceConfig)
    server/services.py        DI container (config + runtime + TTS engine)
    server/factory.py         create_app() composition root
    server/api/handlers.py    HTTP handler factories
    server/sockets/           realtime WS handler factories
    server/chat/pipeline.py   3-thread LLM->TTS pipeline
    server/llm/providers.py   groq/deepseek resolution + keys
    server/llm/streaming.py   streaming phrase generator + retries
    server/speech/pacing.py   per-sentence speed + greetings
    server/speech/audio.py    wav_bytes
    server/screen/context.py  screen blocks + intent routing

New code should use ``from server.factory import create_app`` (or
``from server import create_app``). This module keeps ``from server.app
import app`` working for existing deploys (``voice_api.py``).
"""

from __future__ import annotations

from server.factory import create_app

app = create_app()

# Handy handles for operability (same objects the handlers use).
config = app.state.services.config
services = app.state.services

__all__ = ["app", "config", "create_app", "services"]
