"""Streaming ``/ws/asr`` handler factory (local transcription of mic PCM).

Protocol:
  client -> {"type": "start"} / {"type": "end"} / {"type": "cancel"}
  client -> {"type": "early_end"} / {"type": "resume"}
  client -> {"type": "mode", "vad": "server"}  (opt into server Silero VAD)
  client -> {"type": "assistant", "active": bool}  (our TTS playing gate)
  client -> <binary>  float32 mono PCM @ 16 kHz
  server -> {"type": "partial"|"speculative"|"final"|"vad_start"|"vad_end"|...}

Built by :func:`make_ws_asr` — the blocking Whisper work stays in a worker
thread; only thin config flows through the container.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from collections import deque

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger("voice_api")


def make_ws_asr(services):
    from server import asr as A

    def _ws_asr_factory():
        async def ws_asr(websocket: WebSocket):
            await websocket.accept()
            log.info("ASR websocket connected from %s", websocket.client.host if websocket.client else "unknown")
            ctrl_q: queue.Queue = queue.Queue()
            pcm_q: queue.Queue = queue.Queue()
            out_q: queue.Queue = queue.Queue()
            stop_evt = threading.Event()

            async def reader():
                try:
                    while True:
                        raw = await websocket.receive()
                        if raw.get("bytes") is not None:
                            arr = np.frombuffer(raw["bytes"], dtype=np.float32).copy()
                            if arr.size:
                                pcm_q.put(arr)
                        elif raw.get("text") is not None:
                            try:
                                msg = json.loads(raw["text"])
                            except (ValueError, AttributeError):
                                msg = None
                            mtype = msg.get("type") if isinstance(msg, dict) else None
                            if mtype == "ping":
                                try:
                                    await websocket.send_text(json.dumps({"type": "pong"}))
                                except Exception:
                                    pass
                                continue
                            if mtype == "mode":
                                want = str((msg or {}).get("vad", "")).strip().lower()
                                log.info("ASR control: mode=%s", want or "client")
                                ctrl_q.put("__mode_server__" if want == "server" else "__mode_client__")
                                continue
                            if mtype == "assistant":
                                a = bool((msg or {}).get("active"))
                                log.info("ASR control: assistant_active=%s", a)
                                ctrl_q.put("__assistant_on__" if a else "__assistant_off__")
                                continue
                            if mtype in ("start", "end", "cancel", "early_end", "resume"):
                                log.info("ASR control: %s", mtype)
                            ctrl_q.put(mtype or "__close__" if mtype in ("start", "end", "cancel", "early_end", "resume") else "__noop__")
                except Exception:
                    ctrl_q.put("__close__")

            def worker():
                buf: list = []
                total = 0
                new_since = 0.0
                last_partial = 0.0
                open_utt = False
                early = False
                held = None
                total_at_early = 0
                early_thread = None
                in_trailing_silence = False
                spec_emitted = False
                server_mode = False
                vad = None
                speech_run = 0.0
                silence_run = 0.0
                pre_roll: deque = deque(maxlen=int(A.SERVER_PRE_ROLL_S * A.ASR_SR / 512))
                pending512 = np.zeros(0, dtype=np.float32)
                assistant_active = False

                def finish_utterance(reason: str):
                    nonlocal open_utt, early, held, total_at_early, buf, total, new_since, spec_emitted
                    open_utt = False
                    samples = np.concatenate(buf) if total else np.zeros(0, dtype=np.float32)
                    dur_s = total / A.ASR_SR
                    if early and held is None and early_thread is not None:
                        early_thread.join(timeout=0.5)
                    reused = early and held is not None and 0 <= total - total_at_early <= int(0.05 * A.ASR_SR)
                    held_text = held or ""
                    early = False; held = None; total_at_early = 0
                    buf = []; total = 0; new_since = 0.0
                    if len(samples) < int(max(0.25, A.MIN_UTT_MS / 1000.0) * A.ASR_SR):
                        log.info("ASR utterance discarded (%s): %.2fs audio too short", reason, dur_s)
                        out_q.put(("rejected", "blip"))
                        out_q.put(("final", ""))
                        return
                    if len(samples) >= int(1.8 * A.ASR_SR):
                        sim = A.speaker_similarity(samples)
                        if sim is not None and sim < A.SPEAKER_SIM_MIN:
                            log.info("Speaker gate: utterance REJECTED (%s): sim=%.2f < %.2f", reason, sim, A.SPEAKER_SIM_MIN)
                            out_q.put(("rejected", "speaker"))
                            out_q.put(("final", ""))
                            return
                    if A.ASR_FINAL_BEAM <= 1:
                        if reused:
                            final = held_text
                            log.info("ASR: reused early decode (0.00s on critical path)")
                        else:
                            try:
                                t = time.perf_counter()
                                final = A.transcribe(samples)
                                log.info("ASR: %.2fs for %.2fs audio (%s)", time.perf_counter() - t, dur_s, reason)
                            except Exception as e:  # noqa: BLE001
                                log.exception("ASR decode failed")
                                out_q.put(("error", f"ASR decode failed: {type(e).__name__}: {e}"))
                                return
                        if A.ASR_SPECULATIVE and final and not spec_emitted:
                            spec_emitted = True
                            out_q.put(("speculative", final))
                        out_q.put(("final", final))
                        return
                    if A.ASR_SPECULATIVE and not spec_emitted:
                        if reused:
                            spec = held_text
                            log.info("ASR greedy: reused early decode (0.00s on critical path)")
                        else:
                            try:
                                t = time.perf_counter()
                                spec = A.transcribe(samples)
                                log.info("ASR greedy: %.2fs for %.2fs audio", time.perf_counter() - t, dur_s)
                            except Exception:  # noqa: BLE001 — greedy is best-effort
                                spec = ""
                        if spec:
                            spec_emitted = True
                            out_q.put(("speculative", spec))
                    try:
                        t = time.perf_counter()
                        final = A.transcribe(samples, beam=A.ASR_FINAL_BEAM, vad=True)
                        log.info("ASR beam: %.2fs for %.2fs audio (%s)", time.perf_counter() - t, dur_s, reason)
                    except Exception as e:  # noqa: BLE001
                        log.exception("ASR final decode failed")
                        out_q.put(("error", f"ASR decode failed: {type(e).__name__}: {e}"))
                        return
                    out_q.put(("final", final))

                def start_early_decode():
                    nonlocal early, held, total_at_early, early_thread
                    if early or total < int(0.25 * A.ASR_SR):
                        return
                    early = True
                    held = None
                    snap = np.concatenate(buf)
                    total_at_early = total

                    def _run():
                        nonlocal held
                        t0 = time.perf_counter()
                        try:
                            result = A.transcribe(snap)
                        except Exception:  # noqa: BLE001 — best-effort pre-decode
                            result = None
                        held = result
                        if result:
                            log.info("ASR early decode: %.2fs for %.2fs audio (overlapped)",
                                     time.perf_counter() - t0, total_at_early / A.ASR_SR)

                    early_thread = threading.Thread(target=_run, daemon=True)
                    early_thread.start()

                while not stop_evt.is_set():
                    try:
                        ctl = ctrl_q.get(timeout=0.05)
                    except queue.Empty:
                        ctl = None
                    while True:
                        try:
                            arr = pcm_q.get_nowait()
                        except queue.Empty:
                            break
                        if server_mode:
                            pending512 = np.concatenate([pending512, arr])
                            while pending512.size >= 512:
                                frame, pending512 = pending512[:512], pending512[512:]
                                if vad is None:
                                    try:
                                        vad = A.get_silero()
                                    except Exception as e:  # noqa: BLE001
                                        log.error("Silero unavailable (%s) — falling back to client VAD", e)
                                        server_mode = False
                                        break
                                if open_utt and not in_trailing_silence:
                                    buf.append(frame)
                                    total += len(frame)
                                    new_since += len(frame) / A.ASR_SR
                                p_voice = vad.p(frame)
                                if p_voice >= A.SILERO_ON_THRESH:
                                    speech_run += 32.0; silence_run = 0.0
                                    if open_utt and in_trailing_silence:
                                        in_trailing_silence = False
                                        early = False
                                        held = None
                                        total_at_early = 0
                                elif p_voice < A.SILERO_HOLD_THRESH:
                                    speech_run = 0.0
                                    if open_utt:
                                        silence_run += 32.0
                                        if not in_trailing_silence:
                                            in_trailing_silence = True
                                            start_early_decode()
                                else:
                                    if open_utt:
                                        silence_run = 0.0
                                if open_utt and not spec_emitted and early and held:
                                    spec_emitted = True
                                    out_q.put(("speculative", held))
                                    log.info("ASR speculative sent at silence onset (%.0fms)", silence_run)
                                if not open_utt:
                                    if speech_run >= A.SILERO_ON_MS:
                                        # Keep VAD open while TTS is playing. The
                                        # browser's echo canceller removes Molt's
                                        # playback, and the client applies the
                                        # wake-word gate before interrupting. If
                                        # we suppress this here, saying “Molt”
                                        # can never barge-in during an answer.
                                        buf.extend(pre_roll)
                                        total += sum(len(f) for f in pre_roll)
                                        pre_roll.clear()
                                        open_utt = True
                                        in_trailing_silence = False
                                        early = False
                                        held = None
                                        total_at_early = 0
                                        spec_emitted = False
                                        speech_run = 0.0; silence_run = 0.0
                                        last_partial = time.monotonic()
                                        vad.reset()
                                        out_q.put(("vad_start", ""))
                                        log.info("Server VAD: utterance OPENED (assistant_active=%s)", assistant_active)
                                    else:
                                        pre_roll.append(frame)
                                elif silence_run >= A.SILERO_SILENCE_MIN_MS and held:
                                    log.info("Server VAD: utterance CLOSING early after %.0fms silence (early decode ready)", silence_run)
                                    silence_run = 0.0
                                    out_q.put(("vad_end", ""))
                                    finish_utterance("silence")
                                elif silence_run >= A.SILERO_SILENCE_MS:
                                    log.info("Server VAD: utterance CLOSING after %.0fms silence", silence_run)
                                    silence_run = 0.0
                                    out_q.put(("vad_end", ""))
                                    finish_utterance("silence")
                            continue
                        if open_utt:
                            buf.append(arr)
                            total += len(arr)
                            new_since += len(arr) / A.ASR_SR
                    if ctl == "__close__":
                        return
                    if ctl == "__mode_server__":
                        server_mode = True
                        log.info("/ws/asr: server-side Silero VAD engaged for this connection")
                        continue
                    if ctl == "__mode_client__":
                        server_mode = False
                        continue
                    if ctl == "__assistant_on__":
                        assistant_active = True
                        continue
                    if ctl == "__assistant_off__":
                        assistant_active = False
                        continue
                    if ctl == "start":
                        # In server-VAD mode, opening the push-to-talk socket is
                        # not the same as starting an utterance. Wait for
                        # Silero to detect real speech; otherwise the normal
                        # pre-speech silence is finalized as a fake `blip`.
                        buf.clear(); total = 0; new_since = 0.0; open_utt = not server_mode
                        last_partial = time.monotonic()
                        early = False; held = None; total_at_early = 0
                        in_trailing_silence = False
                        spec_emitted = False
                        continue
                    if ctl == "cancel":
                        buf.clear(); total = 0; new_since = 0.0; open_utt = False
                        early = False; held = None; total_at_early = 0
                        in_trailing_silence = False
                        spec_emitted = False
                        continue
                    if ctl == "early_end" and open_utt:
                        if total >= int(0.25 * A.ASR_SR):
                            snap = np.concatenate(buf)
                            t = time.perf_counter()
                            try:
                                held = A.transcribe(snap)
                            except Exception:  # noqa: BLE001 — best-effort pre-decode
                                held = None
                            log.info("ASR early decode: %.2fs for %.2fs audio (overlapped)",
                                     time.perf_counter() - t, total / A.ASR_SR)
                            total_at_early = total
                            early = True
                        continue
                    if ctl == "resume" and open_utt:
                        early = False; held = None; total_at_early = 0
                        continue
                    if ctl == "end":
                        if open_utt:
                            finish_utterance("client-vad end")
                        else:
                            # Empty push-to-talk releases are intentionally
                            # silent; they are not rejected user utterances.
                            out_q.put(("final", ""))
                        continue
                    if (ctl == "__noop__" or ctl is None) and open_utt and total >= int(0.5 * A.ASR_SR) \
                            and new_since >= A.ASR_PARTIAL_MIN_NEW \
                            and time.monotonic() - last_partial >= A.ASR_PARTIAL_MIN_GAP:
                        new_since = 0.0
                        last_partial = time.monotonic()
                        samples = np.concatenate(buf)
                        try:
                            out_q.put(("partial", A.transcribe(samples)))
                        except Exception:  # noqa: BLE001 — captions are best-effort
                            log.exception("ASR partial decode failed")

            reader_task = asyncio.create_task(reader())
            threading.Thread(target=worker, daemon=True).start()
            try:
                while not reader_task.done():
                    try:
                        kind, text = out_q.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.05)
                        continue
                    if kind in ("partial", "speculative", "final", "rejected", "error"):
                        log.info("ASR output: type=%s text=%r", kind, str(text or "")[:240])
                    try:
                        frame = (
                            {"type": kind, "message": text}
                            if kind == "error" else {"type": kind, "text": text}
                        )
                        await websocket.send_text(json.dumps(frame))
                    except Exception:  # noqa: BLE001 — client vanished mid-decode
                        break
            except WebSocketDisconnect:
                pass
            finally:
                stop_evt.set()
                reader_task.cancel()

        return ws_asr

    return _ws_asr_factory()
