"""Streaming ASR websocket route registration."""


def register(app, *, ws_asr):
    app.websocket("/ws/asr")(ws_asr)
