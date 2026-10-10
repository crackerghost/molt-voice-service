"""Route registration helpers (thin registrars — logic lives in factories)."""


def register_all(app, *, health, ready, api_config, tts, ws_tts, ws_asr, api_vision, chat, fillers):
    from server.routes import asr as _asr
    from server.routes import chat as _chat
    from server.routes import fillers as _fillers
    from server.routes import system as _system
    from server.routes import tts as _tts
    from server.routes import vision as _vision

    _tts.register(app, tts=tts, ws_tts=ws_tts)
    _asr.register(app, ws_asr=ws_asr)
    _vision.register(app, api_vision=api_vision)
    _chat.register(app, chat=chat)
    _fillers.register(app, **fillers)
    _system.register(app, health=health, ready=ready, api_config=api_config)
