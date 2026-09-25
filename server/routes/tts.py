"""TTS HTTP and realtime websocket route registration."""


def register(app, *, tts, ws_tts):
    app.post("/tts")(tts)
    app.websocket("/ws/tts")(ws_tts)
