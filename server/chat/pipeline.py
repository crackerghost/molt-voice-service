"""Realtime 3-thread chat pipeline: LLM producer -> windowing -> audio synth.

Moved verbatim out of ``server/app.py``; the only change is that every
tunable/callable arrives explicitly via :class:`ChatPipelineDeps` instead
of module globals, so the pipeline is reusable outside this repo::

    from server.chat.pipeline import ChatPipelineDeps, chat_worker

Pipeline (three threads run concurrently, nothing serializes):

  1. llm_producer thread — streams the LLM, yields cleaned sentences.
  2. main thread (here) — emits ("text", sent) immediately, groups sentences
     into audio windows.
  3. audio thread — runs OmniVoice generate() per window while the LLM still
     writes later sentences.
  4. watcher threads — one best-effort diagram planner per audio window.

Events on out_q: ("text", s)... ("audio", wav)... ("diagram", {...})
best-effort, ("os_action", {...}) best-effort, ending ("done", {...}).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger("voice_api")


@dataclass
class ChatPipelineDeps:
    """Everything the pipeline needs, injected by the composition root."""

    config: Any  # VoiceConfig
    tts_engine: Any  # TTSEngine
    llm_stream_phrases: Callable  # (key, messages, temp, client, **kw) -> Iterable[(text, complete)]
    speech_sentence: Callable[[str, bool], str]
    clause_units: Callable[[str, int], list[str]]
    pick_speed: Callable[..., float]
    wav_bytes: Callable[[Any, int], bytes]
    diagram_generate: Callable[..., Any]  # generate_for_step
    os_plan: Callable[..., Any]  # plan_os_actions


def _ship_window_factory(win_q: queue.Queue, watch_fn) -> Callable:
    seq = [0]

    def _ship(win_text: str, steps: int, watch: bool = True, raw_text: str = "") -> None:
        seq[0] += 1
        win_q.put({"text": win_text, "steps": steps, "n": seq[0]})
        if watch:
            watch_fn(seq[0], win_text, raw_text)

    _ship.seq = seq  # type: ignore[attr-defined]
    return _ship


def stream_batches(deps: ChatPipelineDeps, text, num_step, speed, stop_evt, t0=None):
    """Yield playable WAV bytes per generated sentence chunk, in order."""
    cfg = deps.config
    batches = deps.tts_engine.stream_chunks(text)
    if not batches:
        return
    first = True
    n_win, total_gen, total_dur = 0, 0.0, 0.0
    for gen_text in batches:
        if stop_evt is not None and stop_evt.is_set():
            return
        steps = min(num_step, cfg.first_window_step) if first else num_step
        t_gen = time.perf_counter()
        w = deps.tts_engine.generate(gen_text, steps, deps.pick_speed(gen_text, speed), cfg.tts_temperature)
        gen_s = time.perf_counter() - t_gen
        w = deps.tts_engine.insert_pauses(w, gen_text)
        dur_s = w.shape[-1] / cfg.sample_rate
        n_win += 1
        total_gen += gen_s
        total_dur += dur_s
        rtf = gen_s / dur_s if dur_s > 0 else 0.0
        if first:
            first_audio = (time.perf_counter() - t0) if t0 else 0.0
            log.info(
                "TTS window #1: %d ch, step %d -> %.2fs audio in %.2fs (RTF %.2f)%s",
                len(gen_text), steps, dur_s, gen_s, rtf,
                f" | first audio {first_audio:.2f}s after request" if t0 else "",
            )
        else:
            log.info(
                "TTS window #%d: %d ch, step %d -> %.2fs audio in %.2fs (RTF %.2f)",
                n_win, len(gen_text), steps, dur_s, gen_s, rtf,
            )
        first = False
        yield deps.wav_bytes(w, cfg.sample_rate)
    avg_rtf = total_gen / total_dur if total_dur else 0.0
    log.info("TTS total: %d window(s), %.2fs audio in %.2fs gen (avg RTF %.2f)", n_win, total_dur, total_gen, avg_rtf)


def synth_worker(deps: ChatPipelineDeps, text, num_step, speed, out_q, stop_evt, t0=None):
    try:
        for chunk in stream_batches(deps, text, num_step, speed, stop_evt, t0):
            out_q.put(("audio", chunk))
        out_q.put(("done", None))
    except Exception as e:  # noqa: BLE001 — report to the client
        log.exception("WS synthesis failed")
        out_q.put(("error", f"{type(e).__name__}: {e}"))


def chat_worker(
    deps: ChatPipelineDeps,
    key,
    messages,
    temperature,
    num_step,
    speed,
    out_q,
    stop_evt,
    t0=None,
    http_client=None,
    diagram_ctx: dict | None = None,
    llm_cfg: dict | None = None,
    os_ctx: dict | None = None,
    provider_clients=None,
):
    """Full chat-turn pipeline (see module docstring)."""
    from server.speech.pacing import GREETING_RE

    cfg = deps.config
    if http_client is None:
        http_client = provider_clients.llm()
    llm_cfg = llm_cfg or {}
    cfg_model = llm_cfg.get("model") or cfg.llm_model
    cfg_url = llm_cfg.get("url") or cfg.llm_url
    cfg_reasoning = llm_cfg.get("reasoning_effort", cfg.llm_reasoning_effort)
    cfg_diagram_model = llm_cfg.get("diagram_model") or cfg.diagram_model
    last_user = messages[-1]["content"] if messages else ""
    is_greeting = bool(GREETING_RE.search(last_user))
    sent_count = 0
    if t0 is None:
        t0 = time.perf_counter()
    timing = {"first_audio": 0.0, "windows": 0, "total_gen": 0.0, "total_dur": 0.0}

    sent_q: queue.Queue = queue.Queue()
    win_q: queue.Queue = queue.Queue()
    llm_error: list[str] = []
    audio_done = threading.Event()
    producer_stop = threading.Event()

    def llm_producer():
        try:
            for raw, complete in deps.llm_stream_phrases(
                key, messages, temperature, http_client,
                max_tokens=cfg.llm_max_tokens,
                retries=cfg.llm_retries,
                phrase_chars=cfg.first_window_chars,
                model=cfg_model, url=cfg_url, reasoning_effort=cfg_reasoning,
                thinking=llm_cfg.get("thinking"),
            ):
                if stop_evt is not None and stop_evt.is_set():
                    return
                if producer_stop.is_set():
                    return
                sent = deps.speech_sentence(raw, complete)
                if not sent or len(sent) <= 2:
                    continue
                sent_q.put((raw.strip(), sent, complete))
        except Exception as e:  # noqa: BLE001 — reported at the consumer end
            llm_error.append(f"{type(e).__name__}: {e}")
        finally:
            sent_q.put(None)

    def audio_synth():
        try:
            while True:
                win = win_q.get()
                if win is None:
                    return
                if stop_evt is not None and stop_evt.is_set():
                    continue
                t_gen = time.perf_counter()
                w = deps.tts_engine.generate(win["text"], win["steps"], deps.pick_speed(win["text"], speed), cfg.tts_temperature)
                gen_s = time.perf_counter() - t_gen
                w = deps.tts_engine.insert_pauses(w, win["text"])
                dur_s = w.shape[-1] / cfg.sample_rate
                rtf = gen_s / dur_s if dur_s > 0 else 0.0
                timing["windows"] += 1
                timing["total_gen"] += gen_s
                timing["total_dur"] += dur_s
                out_q.put(("window", {
                    "n": timing["windows"],
                    "chars": len(win["text"]),
                    "steps": win["steps"],
                    "speed": deps.pick_speed(win["text"], speed),
                    "audio_s": round(dur_s, 2),
                    "gen_s": round(gen_s, 2),
                    "rtf": round(rtf, 2) if rtf else 0,
                    "text": win["text"],
                }))
                if timing["first_audio"] == 0.0:
                    timing["first_audio"] = time.perf_counter() - t0
                    log.info(
                        "TTS window #1: %d ch, step %d -> %.2fs audio in %.2fs (RTF %.2f) | first audio %.2fs after request",
                        len(win["text"]), win["steps"], dur_s, gen_s, rtf, timing["first_audio"],
                    )
                else:
                    log.info(
                        "TTS window #%d: %d ch, step %d -> %.2fs audio in %.2fs (RTF %.2f)",
                        timing["windows"], len(win["text"]), win["steps"], dur_s, gen_s, rtf,
                    )
                out_q.put(("audio", deps.wav_bytes(w, cfg.sample_rate)))
        except Exception as e:  # noqa: BLE001 — reported by the main thread
            llm_error.append(f"audio: {type(e).__name__}: {e}")
        finally:
            audio_done.set()

    threading.Thread(target=llm_producer, daemon=True).start()
    threading.Thread(target=audio_synth, daemon=True).start()

    win_seq = [0]
    turn_texts: list[str] = []  # whole-turn board plan: 1 rich call/turn
    plan_mode = getattr(cfg, "diagram_plan_mode", "turn") or "turn"

    def _diagram_watch(n: int, win_text: str, raw_text: str = "") -> None:
        try:
            if stop_evt is not None and stop_evt.is_set():
                return
            d = deps.diagram_generate(
                diagram_ctx["key"], raw_text or win_text, diagram_ctx.get("topic", ""),
                stop_evt, client=http_client, url=diagram_ctx.get("diagram_url") or cfg_url,
                model=diagram_ctx.get("diagram_model") or cfg_diagram_model,
                max_tokens=cfg.diagram_max_tokens,
                thinking=diagram_ctx.get("diagram_thinking"),
                id_prefix=f"w{n}", turn_id=diagram_ctx.get("turn_id", ""),
            )
            if not d or (stop_evt is not None and stop_evt.is_set()):
                return
            out_q.put(("diagram", {
                "window_n": n, "mode": "append",
                "elements": d["elements"],
                "turn_id": diagram_ctx.get("turn_id", ""),
                "client_turn_id": diagram_ctx.get("client_turn_id", ""),
            }))
            _labels = [str(e.get("text", "") or e.get("code", "") or e.get("type", ""))[:28] for e in d["elements"] if e.get("type") != "arrow"][:4]
            log.info("Diagram watcher: window #%d -> %d element(s) [%s]", n, len(d["elements"]), " | ".join(_labels))
        except Exception as e:  # noqa: BLE001 — board must never break voice
            log.warning("Diagram watcher window #%d skipped: %s", n, e)

    def _ship_window(win_text: str, steps: int, watch: bool = True, raw_text: str = "") -> None:
        win_seq[0] += 1
        n = win_seq[0]
        win_q.put({"text": win_text, "steps": steps, "n": n})
        if (win_text or "").strip():
            turn_texts.append(win_text.strip())
        if watch and diagram_ctx and plan_mode == "window":
            threading.Thread(target=_diagram_watch, args=(n, win_text, raw_text), daemon=True).start()

    def _os_director() -> None:
        try:
            if stop_evt is not None and stop_evt.is_set():
                return
            if not os_ctx:
                return
            actions = deps.os_plan(
                os_ctx["key"], os_ctx.get("text", ""), os_ctx.get("snapshot") or {},
                stop_evt=stop_evt, client=http_client,
                url=os_ctx.get("url") or cfg_url,
                model=os_ctx.get("model") or cfg_diagram_model,
                thinking=os_ctx.get("thinking"),
                max_tokens=os_ctx.get("max_tokens") or 400,
            )
            for a in actions or []:
                if stop_evt is not None and stop_evt.is_set():
                    return
                out_q.put(("os_action", {**a, "client_turn_id": os_ctx.get("client_turn_id", "")}))
            if actions:
                log.info("OS director: %d action(s) [%s]", len(actions), ", ".join(str(x.get("op", "?")) for x in actions))
        except Exception as e:  # noqa: BLE001 — director must never break voice
            log.warning("OS director skipped: %s", e)

    threading.Thread(target=_os_director, daemon=True).start()

    try:
        from server.chat.phrases import clause_units as _default_units  # noqa: F401 (kept for parity)

        piece_max = max(60, min(150, cfg.window_char_cap))
        window: list[str] = []
        raw_window: list[str] = []
        window_chars = 0
        emitted_audio = False
        emitted_text = False
        text_buf = ""

        def _take_raw() -> str:
            raw_text = " ".join(raw_window).strip()
            raw_window.clear()
            return raw_text

        while True:
            item = sent_q.get()
            if item is None:
                break
            if stop_evt is not None and stop_evt.is_set():
                break
            raw, text, complete = item
            if raw:
                raw_window.append(raw)
            if complete:
                sent_count += 1
                if sent_count > cfg.max_chat_sentences:
                    break
                caption = (text_buf + " " + text).strip() if text_buf else text
                out_q.put(("text", caption))
                emitted_text = True
                text_buf = ""
            else:
                text_buf = (text_buf + " " + text).strip()
            sentence_done = complete and not text_buf
            for piece in deps.clause_units(text, piece_max):
                if window and window_chars + len(piece) > cfg.window_char_cap:
                    steps = min(num_step, cfg.first_window_step) if not emitted_audio else num_step
                    _ship_window(" ".join(window), steps, raw_text=_take_raw())
                    window, window_chars = [], 0
                    emitted_audio = True
                window.append(piece)
                window_chars += len(piece)
                if not emitted_audio:
                    if window_chars >= cfg.first_window_chars:
                        text_to_speak = " ".join(window)
                        if sentence_done or len(text_to_speak) <= cfg.first_window_chars:
                            window, window_chars = [], 0
                        elif len(text_to_speak) > cfg.first_window_chars:
                            words = text_to_speak.split()
                            cut_text = ""
                            for w in words:
                                if len(cut_text) + len(w) + 1 <= cfg.first_window_chars:
                                    cut_text = (cut_text + " " + w).strip()
                                else:
                                    break
                            if not cut_text:
                                cut_text = words[0]
                            remainder = text_to_speak[len(cut_text):].strip()
                            window = remainder.split() if remainder else []
                            window_chars = sum(len(w) for w in window)
                            text_to_speak = cut_text
                        else:
                            window, window_chars = [], 0
                        _ship_window(text_to_speak, min(num_step, cfg.first_window_step), raw_text=_take_raw())
                        emitted_audio = True
                else:
                    if window_chars >= cfg.min_window_chars and (
                        sentence_done or window_chars >= cfg.min_window_chars * 2
                    ):
                        _ship_window(" ".join(window), num_step, raw_text=_take_raw())
                        window, window_chars = [], 0
                        emitted_audio = True
            if (is_greeting and sent_count >= cfg.greeting_max) or sent_count >= cfg.max_chat_sentences:
                producer_stop.set()
                break
        if (not emitted_text or (llm_error and not emitted_audio)) and not (stop_evt is not None and stop_evt.is_set()):
            fallback = "अरे, आवाज़ साफ़ नहीं आ पाई। एक बार फिर से बोल दो।"
            out_q.put(("text", fallback))
            _ship_window(fallback, min(num_step, cfg.first_window_step), watch=False)
            emitted_audio = True
        if window and not (stop_evt is not None and stop_evt.is_set()):
            steps = min(num_step, cfg.first_window_step) if not emitted_audio else num_step
            _ship_window(" ".join(window), steps, raw_text=_take_raw())
        # Whole-turn board: ONE rich planner call on the full reply, fired
        # while audio still drains so its ~1s hides inside playback.
        turn_plan: dict = {}
        turn_thread = None
        if (
            diagram_ctx
            and plan_mode == "turn"
            and not llm_error
            and not (stop_evt is not None and stop_evt.is_set())
        ):
            def _turn_diagram() -> None:
                try:
                    if stop_evt is not None and stop_evt.is_set():
                        return
                    full = " ".join(turn_texts).strip()
                    if len(full) < 40:
                        return
                    d = deps.diagram_generate(
                        diagram_ctx["key"], full[:1500], diagram_ctx.get("topic", ""),
                        stop_evt, client=http_client, url=diagram_ctx.get("diagram_url") or cfg_url,
                        model=diagram_ctx.get("diagram_model") or cfg_diagram_model,
                        max_tokens=cfg.diagram_max_tokens,
                        thinking=diagram_ctx.get("diagram_thinking"),
                        id_prefix="t", turn_id=diagram_ctx.get("turn_id", ""),
                        whole=True,
                    )
                    if d and not (stop_evt is not None and stop_evt.is_set()):
                        turn_plan["d"] = d
                        _labels = [str(e.get("text", "") or e.get("code", "") or e.get("type", ""))[:28] for e in d["elements"] if e.get("type") != "arrow"][:6]
                        log.info("Diagram turn-plan -> %d element(s) [%s]", len(d["elements"]), " | ".join(_labels))
                except Exception as e:  # noqa: BLE001 — board must never break voice
                    log.warning("Diagram turn-plan skipped: %s", e)

            turn_thread = threading.Thread(target=_turn_diagram, daemon=True)
            turn_thread.start()
        win_q.put(None)
        audio_done.wait(timeout=180)
        if llm_error and not emitted_audio:
            raise RuntimeError(llm_error[0])
        rtf = timing["total_gen"] / timing["total_dur"] if timing["total_dur"] else 0.0
        log.info(
            "TTS total: %d window(s), %.2fs audio in %.2fs gen (avg RTF %.2f) | first audio %.2fs after request",
            timing["windows"], timing["total_dur"], timing["total_gen"], rtf, timing["first_audio"],
        )
        if turn_thread is not None:
            turn_thread.join(timeout=10)
            d = turn_plan.get("d")
            if d and not (stop_evt is not None and stop_evt.is_set()):
                out_q.put(("diagram", {
                    "window_n": win_seq[0], "mode": "append",
                    "elements": d["elements"],
                    "turn_id": diagram_ctx.get("turn_id", ""),
                    "client_turn_id": diagram_ctx.get("client_turn_id", ""),
                }))
        out_q.put(("done", {"first_audio": round(timing["first_audio"], 2), "rtf": round(rtf, 2)}))
    except Exception as e:  # noqa: BLE001 — report to the client
        log.exception("WS chat synthesis failed")
        out_q.put(("error", f"{type(e).__name__}: {e}"))
