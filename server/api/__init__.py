"""HTTP handler factories (re-export)."""

from server.api.handlers import make_api_config, make_chat, make_health, make_ready, make_tts, make_vision

__all__ = ["make_api_config", "make_chat", "make_health", "make_ready", "make_tts", "make_vision"]
