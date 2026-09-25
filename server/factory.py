"""Application factory — the single composition root.

``create_app`` wires config -> services -> handlers -> routes with no
import-time side effects, so the package embeds cleanly in any project::

    from server import create_app
    app = create_app()  # reads .env + env vars

    # ...or fully explicit (twelve-factor style):
    from server.config import VoiceConfig
    app = create_app(VoiceConfig.from_env("/data/voice"))
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

log = logging.getLogger("voice_api")


def create_app(config=None) -> FastAPI:
    """Build and return the FastAPI app (loading models on lifespan startup)."""
    from server.config import VoiceConfig, load_dotenv
    from server.services import build_services

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    if config is None:
        here = Path(__file__).resolve().parent.parent
        load_dotenv(here / ".env")
        config = VoiceConfig.from_env(here)
    services = build_services(config)

    from server.api import (
        make_api_config,
        make_chat,
        make_health,
        make_ready,
        make_tts,
        make_vision,
    )
    from server.routes import asr as asr_routes
    from server.routes import chat as chat_routes
    from server.routes import system as system_routes
    from server.routes import tts as tts_routes
    from server.routes import vision as vision_routes
    from server.schemas import make_schemas
    from server.sockets import make_ws_asr, make_ws_tts

    TTSRequest, ChatMsg, ChatRequest, VisionRequest = make_schemas(
        default_speed=config.default_speed,
        step_min=config.step_min,
        step_max=config.step_max,
        default_step=config.num_step,
    )

    tts_handler = make_tts(services)
    chat_handler = make_chat(services)
    vision_handler = make_vision(services)
    ws_tts_handler = make_ws_tts(services)
    ws_asr_handler = make_ws_asr(services)

    # FastAPI validates response models from annotations — the factories
    # return un-annotated closures, so wrap with the schema types here.
    # NOTE: keep the original (request: Request) second arg — FastAPI injects it.
    def _tts_route_with_request(req: TTSRequest, request):  # type: ignore[no-untyped-def]
        return tts_handler(req, request)

    def _chat_route(req: ChatRequest, request):  # type: ignore[no-untyped-def]
        return chat_handler(req, request)

    def _vision_route(req: VisionRequest):  # type: ignore[no-untyped-def]
        return vision_handler(req)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from server import vision as vision_facade
        from server.llm.providers import llm_api_key

        log.info("Device: %s | dtype: %s", config.device, config.dtype)
        ov_model, voice_prompt = services.tts_engine.load(config.reference_audio, config.reference_text)
        threading.Thread(target=services.tts_engine.warm, daemon=True).start()
        app.state.services = services
        app.state.ov_model = ov_model
        app.state.voice_prompt = voice_prompt
        app.state.tts_engine = services.tts_engine
        app.state.gen_lock = asyncio.Lock()
        app.state.runtime = services.runtime
        services.runtime.readiness.tts = True
        services.runtime.readiness.provider = bool(llm_api_key())

        from server import asr as asr_facade

        threading.Thread(target=asr_facade.warmup, daemon=True).start()
        threading.Thread(
            target=lambda: (vision_facade.load_ocr(), None)[-1] if not vision_facade.is_ocr_disabled() else None,
            daemon=True,
        ).start()
        if vision_facade.ready_backend() == "local":
            threading.Thread(target=vision_facade.load_local_vlm, daemon=True).start()
        yield

    app = FastAPI(title="Voice API — Hindi TTS (voice cloning)", lifespan=lifespan)
    # Cross-origin access for the split deploy: frontend (Vercel/localhost)
    # talks to the GPU box at http://<GPU-IP>:8000. WS (/ws/tts, /ws/asr)
    # needs no CORS, but fetch (POST /tts, /api/chat, ...) does.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins or ("*",)),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Available pre-startup too (handlers/tests read app.state directly).
    app.state.services = services
    app.state.runtime = services.runtime
    app.state.tts_engine = services.tts_engine
    app.state.gen_lock = None  # created in lifespan (asyncio needs a running loop)
    app.state.schemas = {
        "TTSRequest": TTSRequest,
        "ChatMsg": ChatMsg,
        "ChatRequest": ChatRequest,
        "VisionRequest": VisionRequest,
    }

    tts_routes.register(app, tts=_tts_route_with_request, ws_tts=ws_tts_handler)
    asr_routes.register(app, ws_asr=ws_asr_handler)
    vision_routes.register(app, api_vision=_vision_route)
    chat_routes.register(app, chat=_chat_route)
    system_routes.register(
        app,
        health=make_health(services),
        ready=make_ready(services),
        api_config=make_api_config(services),
        web_dir=config.web_dir,
        serve_ui=config.serve_ui,
    )
    return app
