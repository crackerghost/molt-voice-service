"""Realtime ``/ws/tts`` handler factory (chat + plain TTS over one socket).

Protocol (one connection = one conversation):
  client -> {"type": "chat", "text": ..., "history": [...], "nfe_step"?: 8}
  client -> {"text": "...", "nfe_step"?: 16, "speed"?: 1.0, ...}  (plain TTS)
  server -> {"type": "start", ...} {"type": "text", ...} <binary WAV>*
            {"type": "done", ...} / {"type": "error", ...}
  client -> {"type": "stop"}  (barge-in / abort)

Built by :func:`make_ws_tts` from the :class:`Services` container — no
module globals, so it can be mounted in any FastAPI app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger("voice_api")


def make_ws_tts(services):
    from server import vision as vision_facade
    from server.chat.pipeline import chat_worker, synth_worker
    from server.llm.diagrams import should_generate as should_generate_diagram
    from server.llm.os_control import (
        CODE_DIRECTOR_TOKENS,
        ack_block as os_ack_block,
        plan_os_actions as plan_os,
        sanitize_os_snapshot as sanitize_os,
        should_direct as should_direct,
        wants_code_action as wants_code_action,
        wants_os_action as wants_os_action,
    )
    from server.llm.prompts import (
        LLM_SYSTEM_PROMPT,
        LLM_SYSTEM_SHORT,
        _LLM_PERSONA_CUSTOM,
        _screen_system_prompt,
    )
    from server.llm.providers import resolve_llm
    from server.screen.context import (
        SCREEN_PENDING_TMPL,
        recent_screen_block,
        screen_context_block,
        should_include_screen_context,
    )

    cfg = services.config
    pipeline = services.pipeline

    async def ws_tts(websocket: WebSocket):
        await websocket.accept()
        gen_lock = websocket.app.state.gen_lock
        stop_evt = threading.Event()
        ctrl: asyncio.Queue = asyncio.Queue()
        busy = [False]
        turn_started = [0.0]

        async def reader():
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        data = json.loads(raw)
                    except (ValueError, AttributeError):
                        data = None
                    mtype = data.get("type") if isinstance(data, dict) else None
                    if mtype == "ping":
                        try:
                            await websocket.send_text(json.dumps({"type": "pong"}))
                        except Exception:
                            pass
                        continue
                    if mtype == "stop":
                        from server import asr as asr_facade

                        if busy[0] and time.monotonic() - turn_started[0] < asr_facade.STOP_GRACE_S:
                            continue
                        stop_evt.set()
                        continue
                    if busy[0] and (mtype == "chat" or (isinstance(data, dict) and data.get("text"))):
                        stop_evt.set()
                    await ctrl.put(raw)
            except Exception:
                await ctrl.put(None)

        def _peek_desc():
            with vision_facade.screen_lock:
                c = vision_facade.screen_cache
                if c["desc"] and time.monotonic() - c["ts"] < vision_facade.SCREEN_CACHE_TTL:
                    return c["desc"]
            return ""

        def _peek_ocr():
            with vision_facade.ocr_lock:
                c = vision_facade.ocr_cache
                if c["text"] and time.monotonic() - c["ts"] < vision_facade.SCREEN_CACHE_TTL:
                    return c["text"]
            return ""

        reader_task = asyncio.create_task(reader())
        try:
            while True:
                raw = await ctrl.get()
                if raw is None:
                    break
                try:
                    data = json.loads(raw)
                except ValueError:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                if data.get("type") == "chat":
                    text = str(data.get("text", "")).strip()
                    if not text:
                        await websocket.send_text(json.dumps({"type": "error", "message": "text is required"}))
                        continue
                    try:
                        nfe = int(data.get("nfe_step", data.get("nstep", cfg.num_step)))
                        num_step = max(cfg.step_min, min(cfg.step_max, nfe))
                        speed = float(data.get("speed", cfg.default_speed))
                        temperature = float(data.get("temperature", cfg.llm_temperature))
                    except (TypeError, ValueError):
                        await websocket.send_text(json.dumps({"type": "error", "message": "bad numeric params"}))
                        continue
                    llm_cfg = resolve_llm(data.get("provider") or data.get("llm_provider"), cfg)
                    key = llm_cfg["key"]
                    if not key:
                        missing = "DEEPSEEK_API_KEY" if llm_cfg["name"] == "deepseek" else "GROQ_API_KEY"
                        await websocket.send_text(
                            json.dumps({"type": "error", "message": f"LLM API key not configured for {llm_cfg['name']} (set {missing} in .env)"})
                        )
                        continue
                    history = [
                        {"role": m["role"], "content": str(m["content"])}
                        for m in (data.get("history") or [])
                        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                    ]
                    if not history or history[-1]["role"] != "user":
                        history.append({"role": "user", "content": text})
                    need_screen = should_include_screen_context(text, history, routing_mode=cfg.screen_routing_mode)
                    screen = data.get("screen") if isinstance(data.get("screen"), dict) else None
                    if screen and str(screen.get("image") or screen.get("b64") or "").strip():
                        need_screen = True
                    system_prompt = LLM_SYSTEM_PROMPT if _LLM_PERSONA_CUSTOM else LLM_SYSTEM_SHORT
                    messages = [{"role": "system", "content": system_prompt}, *history]

                    if screen:
                        vision_facade.touch_screen_activity(time.monotonic())
                        img = str(screen.get("image") or screen.get("b64") or "").strip()
                        if img.startswith("data:") and "," in img:
                            img = img.split(",", 1)[1]
                        try:
                            screen_wait_s = min(
                                max(float(screen.get("wait_ms", 0) or 0) / 1000.0, 0.0),
                                vision_facade.SCREEN_WAIT_MAX_S,
                            )
                        except (TypeError, ValueError):
                            screen_wait_s = 0.0
                        if img:
                            if need_screen:
                                _screen_t0 = time.perf_counter()
                                layers = await asyncio.get_running_loop().run_in_executor(
                                    None, vision_facade.describe_layers,
                                    str(screen.get("hash") or ""), img,
                                    screen_wait_s if screen_wait_s > 0 else None,
                                )
                                log.info(
                                    "WS chat: screen context ready in %.2fs (OCR %d chars, VLM %d chars%s)",
                                    time.perf_counter() - _screen_t0,
                                    len(layers.get("ocr") or ""), len(layers.get("desc") or ""),
                                    ", waited for in-flight describe" if screen_wait_s > 0 else "",
                                )
                                block = screen_context_block(layers)
                                if block:
                                    messages[0] = {"role": "system", "content": _screen_system_prompt(block)}
                                else:
                                    recent = await asyncio.get_running_loop().run_in_executor(
                                        None,
                                        lambda: recent_screen_block(
                                            last_activity=vision_facade.last_screen_activity(),
                                            recent_s=cfg.screen_recent_s,
                                            peek_desc=_peek_desc,
                                            peek_ocr=_peek_ocr,
                                        ),
                                    )
                                    if recent:
                                        log.info("WS chat: frame layers empty — using recent cached screen context")
                                        messages[0] = {"role": "system", "content": _screen_system_prompt(recent)}
                                    else:
                                        log.info("WS chat: screen frame received but analysis pending")
                                        messages[0] = {"role": "system", "content": _screen_system_prompt(SCREEN_PENDING_TMPL)}
                                threading.Thread(
                                    target=vision_facade.warm_cache,
                                    args=(img, str(screen.get("hash") or "")),
                                    daemon=True,
                                ).start()
                            else:
                                log.info("WS chat: screen sharing active, but query does not require screen context (saved tokens)")
                                threading.Thread(
                                    target=vision_facade.warm_cache,
                                    args=(img, str(screen.get("hash") or "")),
                                    daemon=True,
                                ).start()
                                threading.Thread(
                                    target=vision_facade.warm_ocr,
                                    args=(img, str(screen.get("hash") or "")),
                                    daemon=True,
                                ).start()
                    else:
                        if need_screen:
                            recent = await asyncio.get_running_loop().run_in_executor(
                                None,
                                lambda: recent_screen_block(
                                    last_activity=vision_facade.last_screen_activity(),
                                    recent_s=cfg.screen_recent_s,
                                    peek_desc=_peek_desc,
                                    peek_ocr=_peek_ocr,
                                ),
                            )
                            if recent:
                                log.info(
                                    "WS chat: using recent cached screen context (activity %.1fs ago)",
                                    time.monotonic() - vision_facade.last_screen_activity(),
                                )
                                messages[0] = {"role": "system", "content": _screen_system_prompt(recent)}

                    turn_started[0] = time.monotonic()
                    stop_evt.clear()
                    start = time.perf_counter()
                    turn_id = uuid.uuid4().hex
                    client_turn_id = str(data.get("client_turn_id", ""))[:80]
                    busy[0] = True
                    async with gen_lock, screen_paused_async():
                        out_q: queue.Queue = queue.Queue()
                        llm_client = services.runtime.provider_clients.llm()
                        os_snapshot = sanitize_os(data.get("os") if isinstance(data.get("os"), dict) else None)
                        os_ctx = None
                        actions_done: list = []
                        if cfg.os_director_enabled and key and wants_os_action(text):
                            try:
                                loop = asyncio.get_running_loop()
                                actions_done = await asyncio.wait_for(
                                    loop.run_in_executor(
                                        None,
                                        lambda: plan_os(
                                            key, text, os_snapshot, stop_evt=stop_evt,
                                            client=llm_client,
                                            url=llm_cfg.get("url"),
                                            model=llm_cfg.get("diagram_model"),
                                            thinking=llm_cfg.get("diagram_thinking"),
                                            max_tokens=CODE_DIRECTOR_TOKENS if wants_code_action(text) else 400,
                                        ),
                                    ),
                                    timeout=cfg.os_director_block_s,
                                ) or []
                            except Exception as e:  # noqa: BLE001 — timeout/failure: honest ack, no moves
                                log.info("OS director blocking call skipped (%s)", e)
                                actions_done = []
                            if stop_evt.is_set():
                                actions_done = []
                            else:
                                for a in actions_done:
                                    await websocket.send_text(json.dumps({
                                        "type": "os_action",
                                        "action": {**a, "client_turn_id": client_turn_id},
                                    }))
                                if actions_done:
                                    log.info("OS director (blocking): %d action(s) [%s]",
                                             len(actions_done), ", ".join(str(x.get("op", "?")) for x in actions_done))
                            base = messages[0].get("content", "") if isinstance(messages[0], dict) else ""
                            messages[0] = {"role": "system", "content": base + "\n\n" + os_ack_block(actions_done)}
                        else:
                            os_ctx = (
                                {"key": key, "text": text, "snapshot": os_snapshot,
                                 "client_turn_id": client_turn_id,
                                 "model": llm_cfg.get("diagram_model"),
                                 "url": llm_cfg.get("url"),
                                 "thinking": llm_cfg.get("diagram_thinking"),
                                 "max_tokens": CODE_DIRECTOR_TOKENS if wants_code_action(text) else 400}
                                if (cfg.os_director_enabled and key and should_direct(text)) else None
                            )
                        should_diagram = (
                            not actions_done
                            and should_generate_diagram(text, history, cfg.diagram_enabled)
                        )
                        log.info("WS chat request [%s/%s]: %s%s", llm_cfg["name"], llm_cfg["model"], text[:50],
                                 " [diagram candidate]" if should_diagram else "")
                        diagram_ctx = (
                            {"key": key, "topic": text, "turn_id": turn_id,
                             "client_turn_id": client_turn_id,
                             "diagram_model": llm_cfg.get("diagram_model"),
                             "diagram_url": llm_cfg.get("url"),
                             "diagram_thinking": llm_cfg.get("diagram_thinking")}
                            if should_diagram else None
                        )
                        threading.Thread(
                            target=chat_worker,
                            args=(pipeline, key, messages, temperature, num_step, speed, out_q, stop_evt, start,
                                  llm_client, diagram_ctx, llm_cfg, os_ctx),
                            kwargs={"provider_clients": services.runtime.provider_clients},
                            daemon=True,
                        ).start()

                        await websocket.send_text(json.dumps({"type": "start", "sample_rate": cfg.sample_rate, "text": text}))
                        frames = 0
                        while True:
                            kind, payload = await asyncio.get_running_loop().run_in_executor(None, out_q.get)
                            if kind == "text":
                                await websocket.send_text(json.dumps({"type": "text", "text": payload}))
                            elif kind == "window":
                                await websocket.send_text(json.dumps({"type": "window", **payload}))
                            elif kind == "diagram":
                                if not stop_evt.is_set():
                                    await websocket.send_text(json.dumps({"type": "diagram", **payload}))
                            elif kind == "os_action":
                                if not stop_evt.is_set():
                                    await websocket.send_text(json.dumps({"type": "os_action", "action": payload}))
                            elif kind == "audio":
                                frames += 1
                                if frames == 1:
                                    log.info("WS chat first audio frame sent %.2fs after request", time.perf_counter() - start)
                                try:
                                    await websocket.send_bytes(payload)
                                except Exception:
                                    stop_evt.set()
                                    return
                            elif kind == "done":
                                elapsed = round(time.perf_counter() - start, 2)
                                extra = payload if isinstance(payload, dict) else {}
                                log.info("WS chat done: %d frame(s) in %.2fs | first audio %.2fs | TTS RTF %.2f",
                                         frames, elapsed, extra.get("first_audio", 0), extra.get("rtf", 0))
                                await websocket.send_text(json.dumps({
                                    "type": "done", "frames": frames, "elapsed": elapsed,
                                    "first_audio": extra.get("first_audio", 0), "rtf": extra.get("rtf", 0),
                                }))
                                break
                            else:
                                log.error("WS chat error: %s", payload)
                                await websocket.send_text(json.dumps({"type": "error", "message": payload}))
                                break
                    busy[0] = False
                    continue

                text = str(data.get("text", "")).strip()
                if not text:
                    await websocket.send_text(json.dumps({"type": "error", "message": "text is required"}))
                    continue
                try:
                    nfe = int(data.get("nfe_step", data.get("nstep", cfg.num_step)))
                    num_step = max(cfg.step_min, min(cfg.step_max, nfe))
                    speed = float(data.get("speed", cfg.default_speed))
                except (TypeError, ValueError):
                    await websocket.send_text(json.dumps({"type": "error", "message": "bad numeric params"}))
                    continue

                turn_started[0] = time.monotonic()
                stop_evt.clear()
                start = time.perf_counter()
                log.info("WS synth request: %s (num_step=%d, speed=%.2f)", text[:50], num_step, speed)
                busy[0] = True
                async with gen_lock, screen_paused_async():
                    out_q: queue.Queue = queue.Queue()
                    threading.Thread(
                        target=synth_worker,
                        args=(pipeline, text, num_step, speed, out_q, stop_evt, start),
                        daemon=True,
                    ).start()
                    await websocket.send_text(json.dumps({"type": "start", "sample_rate": cfg.sample_rate, "text": text}))
                    frames = 0
                    while True:
                        kind, payload = await asyncio.get_running_loop().run_in_executor(None, out_q.get)
                        if kind == "audio":
                            frames += 1
                            if frames == 1:
                                log.info("WS synth first audio frame sent %.2fs after request", time.perf_counter() - start)
                            try:
                                await websocket.send_bytes(payload)
                            except Exception:
                                stop_evt.set()
                                return
                        elif kind == "done":
                            elapsed = round(time.perf_counter() - start, 2)
                            log.info("WS synth done: %d frame(s) in %.2fs", frames, elapsed)
                            await websocket.send_text(json.dumps({"type": "done", "frames": frames, "elapsed": elapsed}))
                            break
                        else:
                            log.error("WS synth error: %s", payload)
                            await websocket.send_text(json.dumps({"type": "error", "message": payload}))
                            break
                busy[0] = False
        except WebSocketDisconnect:
            pass
        finally:
            reader_task.cancel()

    return ws_tts


def screen_paused_async():
    """Async view of the sync screen-pause gate (unwinds on disconnect)."""
    from contextlib import asynccontextmanager

    from server.gpu import screen_pause_begin, screen_pause_end

    @asynccontextmanager
    async def _cm():
        screen_pause_begin()
        try:
            yield
        finally:
            screen_pause_end()

    return _cm()
