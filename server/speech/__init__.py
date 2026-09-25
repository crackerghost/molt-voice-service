"""Speech subsystem: TTS engine, pacing, audio bytes, normalization.

Public surface for reuse::

    from server.speech import TTSEngine, TTSConfig, pick_speed, wav_bytes
"""

from server.speech.audio import wav_bytes
from server.speech.pacing import GREETING_RE, pick_speed, short_greeting
from server.speech.tts_engine import TTSConfig, TTSEngine

__all__ = [
    "TTSConfig",
    "TTSEngine",
    "GREETING_RE",
    "pick_speed",
    "short_greeting",
    "wav_bytes",
]
