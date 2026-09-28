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
import os
import queue
import threading
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger("voice_api")

# Planners lag TTS: chalk for the last windows is often still being drawn
# when the audio finishes. Grace seconds after `done` to forward trailing
# diagram deltas instead of abandoning them with the turn queue (which left
# the board empty despite "board par dekho"). 0 disables.
_DONE_GRACE_S = max(0.0, float(os.environ.get("DIAGRAM_DONE_GRACE_S", "6") or 6))


def make_ws_tts(services):
    from server import vision as vision_facade
    from server.chat.pipeline import chat_worker, synth_worker
    from server.llm.diagrams import EXPLICIT_DIAGRAM_RE, should_generate as should_generate_diagram
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
    from server.llm.providers import groq_api_key, resolve_llm
    from server.screen.context import (
        SCREEN_PENDING_TMPL,
        recent_screen_block,
        screen_context_block,
        should_include_screen_context,
    )

    cfg = services.config
    pipeline = services.pipeline
    from server.speech import filler_pick as filler_picker

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
                    speaker = data.get("speaker_profile")
                    if isinstance(speaker, dict):
                        speaker_name = str(speaker.get("name") or "").strip()[:80]
                        speaker_pronunciation = str(speaker.get("pronunciation") or "").strip()[:80]
                        if speaker_name:
                            system_prompt += (
                                "\n\nSTUDENT NAME: The learner's exact display name is "
                                + speaker_name
                                + ". Address them with this exact name when appropriate."
                            )
                            if speaker_pronunciation:
                                system_prompt += (
                                    " For speech, pronounce that name as "
                                    + speaker_pronunciation
                                    + ". Never spell out or repeat the word 'name'."
                                )
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
                             "required": bool(EXPLICIT_DIAGRAM_RE.search(text)),
                             "diagram_model": llm_cfg.get("diagram_model"),
                             "diagram_url": llm_cfg.get("url"),
                             "diagram_thinking": llm_cfg.get("diagram_thinking")}
                            if should_diagram else None
                        )
                        # Single brain: when this turn may draw, the answer call
                        # itself carries the draw tool — words and visuals come
                        # from one decision-maker and can never disagree.
                        inline_board = bool(should_diagram) and bool(getattr(cfg, "diagram_inline", False))
                        if inline_board:
                            log.info("WS chat request: inline board on (single brain)")
                            base = messages[0].get("content", "") if isinstance(messages[0], dict) else ""
                            messages[0] = {"role": "system", "content": base + (
                                "\n\nBOARD TOOL RULE: You own the board decision in this same response. "
                                "Call draw_flowchart_or_diagram only when a visual materially helps, or whenever "
                                "the learner explicitly asks to draw/show a visual. If you say board, screen, "
                                "diagram, or ask the learner to look at it, you MUST emit the draw tool call in "
                                "this response. If you do not call the tool, do not mention or point at the board."
                            )}
                        threading.Thread(
                            target=chat_worker,
                            args=(pipeline, key, messages, temperature, num_step, speed, out_q, stop_evt, start,
                                  llm_client, diagram_ctx, llm_cfg, os_ctx),
                            kwargs={"provider_clients": services.runtime.provider_clients,
                                    "inline_board": inline_board},
                            daemon=True,
                        ).start()

                        await websocket.send_text(json.dumps({"type": "start", "sample_rate": cfg.sample_rate, "text": text,
                                                              "turn_id": turn_id, "client_turn_id": client_turn_id}))
                        frames = 0
                        board_announced = False

                        async def _send_diagram(diagram_payload: dict) -> None:
                            """Open the board only after the agent actually drew.

                            `should_diagram` only means the visual judge should run;
                            it is not a decision to show a screen.  Announcing here
                            prevents an empty preview on ordinary voice-only turns.
                            """
                            nonlocal board_announced
                            if stop_evt.is_set():
                                return
                            if not board_announced:
                                await websocket.send_text(json.dumps({
                                    "type": "board_ready",
                                    "status": "drawing",
                                    "turn_id": diagram_payload.get("turn_id", turn_id),
                                    "client_turn_id": diagram_payload.get("client_turn_id", client_turn_id),
                                }))
                                board_announced = True
                            await websocket.send_text(json.dumps({"type": "diagram", **diagram_payload}))

                        # Filler masker: a random pre-generated "ruko" clip goes out FIRST
                        # on every chat turn, so any client (bundled UI or external)
                        # plays something instantly while the LLM+TTS catches up.
                        # mode=slow: only if no real frame within threshold_ms.
                        filler_mode = (getattr(cfg, "filler_mode", "always") or "always").strip().lower()
                        filler_store = getattr(websocket.app.state, "fillers", None)
                        # Cheap smart pick: qwen (~100ms) chooses the clip in
                        # PARALLEL with the main turn — never serial, never blocking.
                        # Falls back to random on timeout/failure.
                        filler_pick_future = None
                        if (
                            getattr(cfg, "filler_pick_enabled", True)
                            and getattr(cfg, "filler_enabled", True)
                            and filler_mode != "off"
                            and filler_store
                            and len(filler_store) > 1
                        ):
                            try:
                                _pick_key = groq_api_key()
                                _pick_names = filler_store.names()
                                _pick_timeout = max(0.05, float(getattr(cfg, "filler_pick_timeout_s", 0.3)))
                                if _pick_key and _pick_names:
                                    filler_pick_future = asyncio.get_running_loop().run_in_executor(
                                        None,
                                        lambda: filler_picker.pick_name(
                                            text,
                                            _pick_names,
                                            key=_pick_key,
                                            url=cfg.llm_url,
                                            model=getattr(cfg, "filler_pick_model", "qwen/qwen3.8-27b"),
                                            timeout_s=_pick_timeout + 1.0,
                                        ),
                                    )
                            except Exception as exc:  # noqa: BLE001 — random fallback below
                                log.info("filler smart pick not started (%s)", exc)
                                filler_pick_future = None

                        async def _send_filler() -> bool:
                            if stop_evt.is_set():
                                return False
                            clip = None
                            if filler_pick_future is not None:
                                try:
                                    name = await asyncio.wait_for(
                                        filler_pick_future,
                                        timeout=max(0.05, float(getattr(cfg, "filler_pick_timeout_s", 0.3))),
                                    )
                                    if name:
                                        clip = filler_store.get(name)
                                    if clip is not None:
                                        filler_store.mark_played(clip)
                                except Exception as exc:  # noqa: BLE001 — timeout/failure: random below
                                    log.info("filler smart pick fallback (%s)", type(exc).__name__)
                                    clip = None
                            if clip is None:
                                clip = filler_store.pick_random() if filler_store else None
                            if clip is None:
                                return False
                            try:
                                await websocket.send_text(json.dumps({"type": "filler", "name": clip["name"]}))
                                await websocket.send_bytes(clip["bytes"])
                            except Exception:
                                stop_evt.set()
                                return False
                            log.info("WS chat filler [%s] sent first (%.2fs)", clip["name"], clip.get("duration_s") or 0)
                            return True

                        filler_task = None
                        if getattr(cfg, "filler_enabled", True) and filler_mode != "off" and filler_store:
                            if filler_mode == "slow":
                                async def _slow_filler() -> None:
                                    await asyncio.sleep(getattr(cfg, "filler_threshold_ms", 400) / 1000.0)
                                    if frames == 0 and not stop_evt.is_set():
                                        await _send_filler()
                                filler_task = asyncio.create_task(_slow_filler())
                            else:  # always
                                await _send_filler()
                        while True:
                            kind, payload = await asyncio.get_running_loop().run_in_executor(None, out_q.get)
                            if kind == "text":
                                await websocket.send_text(json.dumps({"type": "text", "text": payload}))
                            elif kind == "window":
                                await websocket.send_text(json.dumps({"type": "window", **payload}))
                            elif kind == "diagram":
                                await _send_diagram(payload)
                            elif kind == "board_status":
                                await websocket.send_text(json.dumps({"type": "board_status", **payload}))
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
                                # Grace drain: forward trailing chalk before closing
                                # the turn (see _DONE_GRACE_S). Late planner deltas
                                # otherwise die in the abandoned queue.
                                if _DONE_GRACE_S > 0 and not (stop_evt is not None and stop_evt.is_set()):
                                    running_loop = asyncio.get_running_loop()

                                    def _grab(timeout_s):
                                        try:
                                            return out_q.get(True, timeout_s)
                                        except queue.Empty:
                                            return (None, None)

                                    grace_until = time.monotonic() + _DONE_GRACE_S
                                    while True:
                                        remaining = grace_until - time.monotonic()
                                        if remaining <= 0:
                                            break
                                        kind2, payload2 = await running_loop.run_in_executor(None, _grab, remaining)
                                        if kind2 is None:
                                            break  # timeout — no more chalk coming
                                        if kind2 == "diagram":
                                            await _send_diagram(payload2)
                                            continue
                                        if kind2 == "done":
                                            break
                                        if kind2 == "error":
                                            await websocket.send_text(json.dumps({"type": "error", "message": payload2}))
                                            break
                                        if kind2 == "text" or kind2 == "board_status":
                                            key2 = "text" if kind2 == "text" else "board_status"
                                            await websocket.send_text(json.dumps({"type": key2, **payload2} if isinstance(payload2, dict) else {"type": key2, "text": payload2}))
                                            continue
                                        # window/audio/os_action after done: ignore, keep draining
                                await websocket.send_text(json.dumps({
                                    "type": "done", "frames": frames, "elapsed": elapsed,
                                    "first_audio": extra.get("first_audio", 0), "rtf": extra.get("rtf", 0),
                                }))
                                break
                            else:
                                log.error("WS chat error: %s", payload)
                                await websocket.send_text(json.dumps({"type": "error", "message": payload}))
                                break
                    if filler_task is not None and not filler_task.done():
                        filler_task.cancel()
                    if filler_pick_future is not None and not filler_pick_future.done():
                        filler_pick_future.cancel()
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
