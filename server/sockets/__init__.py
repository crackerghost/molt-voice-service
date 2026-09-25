"""Realtime socket factories (re-export)."""

from server.sockets.asr_socket import make_ws_asr
from server.sockets.tts_socket import make_ws_tts

__all__ = ["make_ws_asr", "make_ws_tts"]
