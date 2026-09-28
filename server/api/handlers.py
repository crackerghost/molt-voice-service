"""HTTP handler factories: health, readiness, UI config, TTS, chat, vision.

Each ``make_*`` takes the :class:`Services` container and returns a plain
callable with a FastAPI-compatible signature. Mount them with::

    app.get("/health")(make_health(services))
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import HTTPException, Request

log = logging.getLogger("voice_api")


def make_health(services):
    cfg = services.config

    def health():
        return {"status": "ok", "device": cfg.device}

    return health


def make_ready(services):
    from server import asr as asr_facade
    from server import vision as vision_facade
    from server.llm.providers import llm_api_key

    def ready():
        runtime = services.runtime
        runtime.readiness.asr = bool(asr_facade.is_ready())
        runtime.readiness.vision = bool(vision_facade.is_ready())
        runtime.readiness.provider = bool(llm_api_key())
        return runtime.readiness.public()

    return ready


def make_api_config(services):
    import os as _os

    from server import asr as asr_facade
    from server import vision as vision_facade
    from server.llm.providers import providers_available

    cfg = services.config

    def api_config():
        """Every env-tunable knob in one JSON blob (drives the web UI)."""
        return {
            "model": cfg.model_name,
            "num_step": cfg.num_step,
            "step_min": cfg.step_min,
            "step_max": cfg.step_max,
            "temperature": cfg.tts_temperature,
            "speed": cfg.default_speed,
            "sample_rate": cfg.sample_rate,
            "device": cfg.device,
            "dtype": cfg.dtype,
            "asr_backend": asr_facade.pick_backend(),
            "asr_model": asr_facade.ASR_MODEL,
            "asr_lang": asr_facade.ASR_LANG or "",
            "asr_device": asr_facade.ASR_DEVICE,
            "asr_final_beam": asr_facade.ASR_FINAL_BEAM,
            "asr_initial_prompt": asr_facade.ASR_INITIAL_PROMPT or "",
            "asr_vad_mode": asr_facade.VAD_BACKEND,
            "silero_silence_ms": asr_facade.SILERO_SILENCE_MS,
            "speaker_gate": bool(asr_facade.get_speaker_ref() is not None),
            "speaker_sim_min": asr_facade.SPEAKER_SIM_MIN,
            "asr_speculative": asr_facade.ASR_SPECULATIVE,
            "spec_chat": asr_facade.ASR_SPECULATIVE,
            "speculative_ms": asr_facade.ASR_SPECULATIVE_MS,
            "asr_ready": asr_facade.is_ready(),
            "first_step": cfg.first_window_step,
            "stream_window": cfg.stream_window,
            "window_chars": cfg.window_char_cap,
            "min_window_chars": cfg.min_window_chars,
            "max_sentences": cfg.max_chat_sentences,
            "greeting_max": cfg.greeting_max,
            "vision_enabled": vision_facade.is_ready(),
            "vision_backend": vision_facade.ready_backend() or "off",
            "vision_model": (
                vision_facade.VISION_MODEL
                if vision_facade.ready_backend() == "api"
                else vision_facade.VISION_LOCAL_MODEL
            ),
            "screen_tick_ms": int(_os.environ.get("SCREEN_TICK_MS", "1200")),
            "screen_prefetch_ms": int(_os.environ.get("SCREEN_PREFETCH_MS", "4000")),
            "screen_push_mode": _os.environ.get("SCREEN_PUSH_MODE", "1") == "1",
            "screen_push_max_ms": int(_os.environ.get("SCREEN_PUSH_MAX_MS", "5000")),
            "screen_push_tick_ms": int(_os.environ.get("SCREEN_PUSH_TICK_MS", "400")),
            "llm_model": cfg.llm_model,
            "llm_temperature": cfg.llm_temperature,
            "llm_max_tokens": cfg.llm_max_tokens,
            "llm_provider": cfg.llm_provider_default,
            "llm_providers": providers_available(),
            "llm_models": {"groq": cfg.llm_model, "deepseek": cfg.deepseek_model},
            "deepseek_thinking": cfg.deepseek_thinking,
            "deepseek_reasoning_effort": cfg.deepseek_reasoning_effort or "",
            "diagram_enabled": cfg.diagram_enabled,
            "diagram_model": cfg.diagram_model,
            "diagram_max_tokens": cfg.diagram_max_tokens,
            "diagram_plan_mode": getattr(cfg, "diagram_plan_mode", "window"),
            "diagram_inline": getattr(cfg, "diagram_inline", True),
            "diagram_gate": _os.environ.get("DIAGRAM_GATE", "auto"),
            "diagram_done_grace_s": _os.environ.get("DIAGRAM_DONE_GRACE_S", "6"),
            "diagram_pace_gap_s": _os.environ.get("DIAGRAM_PACE_GAP_S", "3.5"),
            "os_director_enabled": cfg.os_director_enabled,
            "os_director_block_s": cfg.os_director_block_s,
            "chat_step": int(_os.environ.get("VOICE_CHAT_STEP", "8")),
            "jitter_frames": cfg.jitter_frames,
            "max_history": int(_os.environ.get("VOICE_MAX_HISTORY", "8")),
            "ws_reconnect_ms": int(_os.environ.get("VOICE_WS_RECONNECT_MS", "1500")),
            "rec_restart_ms": int(_os.environ.get("VOICE_REC_RESTART_MS", "400")),
            "vad_tick_ms": int(_os.environ.get("VOICE_VAD_TICK_MS", "50")),
            "auto_send_ms": int(_os.environ.get("VOICE_AUTO_SEND_MS", "750")),
            "send_min_chars": int(_os.environ.get("VOICE_SEND_MIN_CHARS", "2")),
            "vad_noise_floor": float(_os.environ.get("VOICE_VAD_NOISE", "0.005")),
            "vad_threshold_min": float(_os.environ.get("VOICE_VAD_THRESHOLD_MIN", "0.014")),
            "vad_gate_mult": float(_os.environ.get("VOICE_VAD_GATE_MULT", "3.4")),
            "vad_sustain_ms": int(_os.environ.get("VOICE_VAD_SUSTAIN_MS", "250")),
            "vad_text_ms": int(_os.environ.get("VOICE_VAD_TEXT_MS", "150")),
            "vad_failsafe_ms": int(_os.environ.get("VOICE_VAD_FAILSAFE_MS", "900")),
            "speak_tail_ms": int(_os.environ.get("VOICE_SPEAK_TAIL_MS", "700")),
            "vad_rec_active_ms": int(_os.environ.get("VOICE_VAD_REC_ACTIVE_MS", "400")),
            "barge_idle_ms": int(_os.environ.get("VOICE_BARGE_IDLE_MS", "900")),
            "filler_enabled": _os.environ.get("VOICE_FILLER_ENABLED", "1") != "0",
            "filler_threshold_ms": int(_os.environ.get("VOICE_FILLER_THRESHOLD_MS", "500")),
            "filler_mode": (_os.environ.get("VOICE_FILLER_MODE", "slow").strip().lower() or "slow"),
        }

    return api_config


def make_tts(services):
    import io

    import soundfile as sf
    from fastapi.responses import Response

    cfg = services.config
    engine = services.tts_engine

    def tts(req, request: Request):
        start = time.perf_counter()
        try:
            wav = engine.generate(req.text, req.nfe_step, req.speed, cfg.tts_temperature)
        except RuntimeError as e:
            log.exception("TTS inference failed")
            raise HTTPException(status_code=500, detail=str(e)) from e
        wav = engine.insert_pauses(wav, req.text)
        elapsed = time.perf_counter() - start
        log.info("Generated %.1fs of audio in %.2fs", wav.shape[-1] / cfg.sample_rate, elapsed)
        buf = io.BytesIO()
        sf.write(buf, wav, cfg.sample_rate, format="WAV")
        return Response(
            content=buf.getvalue(),
            media_type="audio/wav",
            headers={"Content-Disposition": 'attachment; filename="speech.wav"'},
        )

    return tts


def make_chat(services):
    import httpx

    from server.llm.providers import resolve_llm
    from server.speech.normalization import (
        _devanagari_only,
        _naturalize,
        _preserve_code_tokens,
        _speechify,
    )
    from server.speech.pacing import GREETING_RE, short_greeting

    cfg = services.config

    def chat(req, request: Request):
        llm_cfg = resolve_llm(getattr(req, "provider", None), cfg)
        key = llm_cfg["key"]
        if not key:
            missing = "DEEPSEEK_API_KEY" if llm_cfg["name"] == "deepseek" else "GROQ_API_KEY"
            raise HTTPException(
                status_code=503,
                detail=f"LLM API key not configured for {llm_cfg['name']}. Set {missing} in .env",
            )
        http_client = request.app.state.services.runtime.provider_clients.llm()

        def _call(messages: list[dict]) -> str:
            from server.llm.prompts import LLM_SYSTEM_PROMPT  # noqa: F401 (persona lives in prompts)

            payload = {
                "model": llm_cfg["model"],
                "messages": messages,
                "temperature": req.temperature,
                "max_tokens": cfg.llm_max_tokens,
            }
            if llm_cfg["reasoning_effort"] and (
                "gpt-oss" in llm_cfg["model"] or llm_cfg.get("thinking") is not None
            ):
                payload["reasoning_effort"] = llm_cfg["reasoning_effort"]
            if llm_cfg.get("thinking") is not None:
                payload["thinking"] = llm_cfg["thinking"]
            try:
                r = http_client.post(
                    llm_cfg["url"],
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=f"LLM request failed: {e}") from e
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail=f"{llm_cfg['name']} API {r.status_code}: {r.text[:300]}")
            try:
                return r.json()["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, ValueError) as e:
                raise HTTPException(status_code=502, detail=f"Unexpected LLM response: {e}") from e

        from server.llm.prompts import LLM_SYSTEM_PROMPT

        history = [{"role": m.role, "content": m.content} for m in req.messages]
        messages = [{"role": "system", "content": LLM_SYSTEM_PROMPT}, *history]
        reply = _call(messages)
        reply = _preserve_code_tokens(reply)
        reply = _speechify(reply)
        reply = _naturalize(reply)
        reply = _devanagari_only(reply)
        if reply and reply[-1] not in "।?!.":
            cut = max(reply.rfind("।"), reply.rfind("?"), reply.rfind("!"), reply.rfind("."))
            if cut > 0:
                reply = reply[: cut + 1]
        last_user = history[-1]["content"] if history else ""
        if GREETING_RE.search(last_user):
            reply = short_greeting(reply, cfg.greeting_max)
        log.info("LLM reply: %s", reply[:80])
        return {"reply": reply, "model": llm_cfg["model"], "provider": llm_cfg["name"]}

    return chat


def make_vision(services):
    from server import vision as vision_facade

    def api_vision(req):
        vision_facade.touch_screen_activity(time.monotonic())
        img = req.image.strip()
        if img.startswith("data:") and "," in img:
            img = img.split(",", 1)[1]
        if not req.force:
            with vision_facade.screen_lock:
                cache = vision_facade.screen_cache
                if (
                    cache["hash"] == req.hash
                    and cache["desc"]
                    and time.monotonic() - cache["ts"] < vision_facade.SCREEN_CACHE_TTL
                ):
                    return {
                        "description": cache["desc"],
                        "cached": True,
                        "model": cache["model"],
                        "backend": vision_facade.backend_choice(),
                    }
            vision_facade.warm_cache(img, req.hash, force=False)
            return {
                "description": "",
                "cached": False,
                "queued": True,
                "model": "",
                "backend": vision_facade.backend_choice(),
            }
        try:
            vision_client = services.runtime.provider_clients.vision()
            desc, cached, model = vision_facade.screen_context(img, req.hash, force=True, http_client=vision_client)
        except Exception as e:  # noqa: BLE001 — log the WHY, not just the 503
            log.exception("/api/vision failed: %s", e)
            raise HTTPException(status_code=503, detail=str(e)) from e
        return {"description": desc, "cached": cached, "model": model, "backend": vision_facade.backend_choice()}

    return api_vision
