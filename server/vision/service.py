"""Screen vision, OCR, caching, and background warm-up services."""

import base64
import io
import logging
import os
import re
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import torch

from server.gpu import gpu_generate_lock as GPU_GENERATE_LOCK
from server.gpu import screen_busy as _screen_busy
from server.gpu import wait_for_screen_resume as _wait_for_screen_resume

log = logging.getLogger("voice_api")
HERE = Path(__file__).resolve().parent.parent

# ---------- Vision: Qwen2.5-VL screen understanding (/api/vision) ----------
#
# When the user shares their screen, the browser grabs a JPEG frame and sends
# it here. Qwen2.5-VL (any OpenAI-compatible host: DashScope, Together,
# OpenRouter, local vLLM) writes a compact Hindi description of what is on
# screen, which the chat LLM then uses as ground truth. The description is
# cached by the client's change-detection hash, so an unchanged screen costs
# ZERO vision calls — the tutor keeps answering at full voice speed.
VISION_BACKEND = os.environ.get("VISION_BACKEND", "auto").strip().lower()  # auto | api | local
VISION_BASE_URL = os.environ.get(
    "VISION_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
).rstrip("/")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen2.5-vl-7b-instruct")
# Local (in-process) vision model — Qwen2.5-VL-3B-Instruct fits a Kaggle T4
# (16 GB) next to OmniVoice + Whisper in fp16 (~7.5 GB weights) and needs NO
# API key. Loaded lazily on the first screen-share, so boot time is unchanged.
VISION_LOCAL_MODEL = os.environ.get("VISION_LOCAL_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
# 2-3 short Hindi sentences ≈ 60-80 tokens; 90 + the two-line early stop
# below cuts decode time dramatically
VISION_LOCAL_MAX_NEW_TOKENS = int(os.environ.get("VISION_LOCAL_MAX_NEW_TOKENS", "60"))
# Max image side before vision tower: 384px keeps the vision tower tiny (fast
# prefill AND decode) while OCR carries the exact text ground truth anyway.
VISION_LOCAL_MAX_SIDE = int(os.environ.get("VISION_LOCAL_MAX_SIDE", "384"))
# Attention kernel for the local VLM: "sdpa" (default, flash-path on CUDA)
# | "eager". SDPA alone is ~1.3-1.8x faster prefill+decode vs eager on GPU.
VISION_LOCAL_ATTN = os.environ.get("VISION_LOCAL_ATTN", "sdpa").strip().lower()
# 1 = load the local VLM in 4-bit (bitsandbytes): ~2 GB weights, noticeably
# faster decode on T4. Needs `pip install bitsandbytes`. Default off.
VISION_LOCAL_4BIT = os.environ.get("VISION_LOCAL_4BIT", "1") == "1"
VISION_TIMEOUT = float(os.environ.get("VISION_TIMEOUT", "25.0"))
# Cached descriptions older than this are considered stale and re-described
# when the same hash is sent again.
SCREEN_CACHE_TTL = float(os.environ.get("VISION_CACHE_TTL", "600"))


def _vision_api_key() -> str:
    """Vision API key: VISION_API_KEY -> DASHSCOPE_API_KEY, env or .env file."""
    for name in ("VISION_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            return key
        env_file = HERE / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{name}="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        return key
    return ""


VISION_DESC_PROMPT = (
    "Describe this screenshot for a Hindi tutor in exactly 2 lines of Hindi (Devanagari). "
    "Line 1: which app/page is open and what the main content is. "
    "Line 2: any visible error, warning, or code — quote exact English text as-is. "
    "No intro, no markdown, no bullets. If nothing notable: just 1 line."
)

_screen_lock = threading.Lock()
_screen_cache: dict = {"hash": None, "desc": "", "ts": 0.0, "model": ""}
# monotonic ts of the last proof the user is sharing (frame turn or warm-up)
# — lets the WS path fall back to recent cached context when a turn arrives
# without a frame (client bug, dropped field, stale bundle).
_last_screen_activity = 0.0


# RLock, held across load AND generate: model.generate() is NOT safe to run
# concurrently on one instance — three simultaneous calls (requests queued
# while the model loads) OOM/race and 503. Serializing them means the 2nd/3rd
# identical requests then hit the hash cache instead.
_vlm_lock = threading.RLock()
_local_vlm: dict = {"model": None, "processor": None}


def _local_vlm_available() -> bool:
    """True when the local transformers vision stack is importable (no GPU check —
    it also works on CPU, just slower). Cheap: never imports transformers."""
    if VISION_BACKEND == "api":
        return False
    import importlib.util

    return (
        importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("PIL") is not None
    )


def _vision_ready_backend() -> str | None:
    """Which vision engine would actually run right now: 'api' | 'local' | None."""
    if VISION_BACKEND == "api":
        return "api" if _vision_api_key() else None
    if VISION_BACKEND == "local":
        return "local" if _local_vlm_available() else None
    # auto: hosted API when a key exists, else the local model
    if _vision_api_key():
        return "api"
    return "local" if _local_vlm_available() else None


def _vision_ready() -> bool:
    return _vision_ready_backend() is not None


def _load_local_vlm():
    """Load Qwen2.5-VL-3B once (lazy, thread-safe). fp16 on CUDA, fp32 on
    MPS/CPU (fp16 MPS is broken on torch 2.x — same rule as the TTS model)."""
    if _local_vlm["model"] is not None:
        return _local_vlm["model"], _local_vlm["processor"]
    with _vlm_lock:
        if _local_vlm["model"] is not None:
            return _local_vlm["model"], _local_vlm["processor"]
        import torch as _torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        device = "cuda" if _torch.cuda.is_available() else (
            "mps" if _torch.backends.mps.is_available() else "cpu"
        )
        # auto: fp16 on CUDA (~4.5 GB for the 3B), fp32 on MPS/CPU (fp16 MPS
        # is broken on torch 2.x — same rule as the TTS model). VISION_LOCAL_DTYPE
        # overrides when MPS memory is tight (fp16 halves the 3B's ~12 GB).
        want = os.environ.get("VISION_LOCAL_DTYPE", "auto").strip().lower()
        if want in ("fp16", "float16", "half"):
            dtype = _torch.float16
        elif want in ("fp32", "float32", "float"):
            dtype = _torch.float32
        else:
            dtype = _torch.float16 if device == "cuda" else _torch.float32
        load_kwargs = {"torch_dtype": dtype}
        if VISION_LOCAL_4BIT:
            try:
                from transformers import BitsAndBytesConfig

                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True, bnb_4bit_compute_dtype=dtype, bnb_4bit_quant_type="nf4"
                )
                log.info("Vision: loading %s in 4-bit (nf4)…", VISION_LOCAL_MODEL)
            except Exception as e:  # noqa: BLE001 — bitsandbytes missing -> plain load
                log.warning("4-bit load unavailable (%s) — falling back to %s", e, dtype)
        log.info("Loading local vision model %s on %s (%s)…", VISION_LOCAL_MODEL, device, dtype)
        t0 = time.perf_counter()
        # SDPA attention: large decode speedup on CUDA, no quality change.
        # Older transformers versions reject the kwarg — degrade gracefully.
        load_kwargs["attn_implementation"] = VISION_LOCAL_ATTN
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            VISION_LOCAL_MODEL, **load_kwargs
        ).to(device).eval()
        processor = AutoProcessor.from_pretrained(VISION_LOCAL_MODEL)
        _local_vlm.update({"model": model, "processor": processor})
        log.info("Local vision model ready in %.1fs", time.perf_counter() - t0)
        return model, processor


def _screen_describe_local(image_b64: str) -> str:
    """Describe one screenshot with the LOCAL Qwen2.5-VL-3B (transformers).

    The whole call (load + generate) runs under _vlm_lock so only ONE
    generation touches the model at a time — concurrent generate() calls on
    the same weights OOM/race (the cause of the 503 storm after load).
    """
    import base64

    import torch as _torch
    from PIL import Image
    from transformers import StoppingCriteria, StoppingCriteriaList

    class _TwoLineStop(StoppingCriteria):
        """Stop the local VLM the moment the 2-line Hindi describe is done.

        The prompt demands 'exactly 2 lines', but greedy decode otherwise
        keeps going to the token cap. Cutting at the second newline saves
        ~30-50% of decode time with zero quality change (1-line 'nothing
        notable' answers still run to the cap — rare, accepted).
        """

        def __init__(self, tokenizer, prompt_len: int):
            self.eos = tokenizer.eos_token_id
            nl_ids = tokenizer("\n", add_special_tokens=False)["input_ids"]
            self.nl_id = nl_ids[0] if len(nl_ids) == 1 else None
            self.prompt_len = prompt_len

        def __call__(self, input_ids, scores, **kwargs) -> bool:
            gen = input_ids[0, self.prompt_len:]
            if gen.numel() < 4:
                return False
            if self.eos is not None and int(gen[-1]) == self.eos:
                return True
            if self.nl_id is not None and int((gen == self.nl_id).sum()) >= 2:
                return True
            return False

    with _vlm_lock:
        model, processor = _load_local_vlm()
        try:
            img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
            if max(img.size) > VISION_LOCAL_MAX_SIDE:  # vision tokens ~ (side/28)²
                img.thumbnail((VISION_LOCAL_MAX_SIDE, VISION_LOCAL_MAX_SIDE))
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": img},
                        {"type": "text", "text": VISION_DESC_PROMPT},
                    ],
                }
            ]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=[img], return_tensors="pt").to(model.device)
            t0 = time.perf_counter()
            stop = StoppingCriteriaList(
                [_TwoLineStop(processor.tokenizer, inputs["input_ids"].shape[1])]
            )
            with _torch.inference_mode():
                with GPU_GENERATE_LOCK:  # never compete with TTS for the GPU
                    out = model.generate(
                        **inputs,
                        max_new_tokens=VISION_LOCAL_MAX_NEW_TOKENS,
                        do_sample=False,
                        stopping_criteria=stop,
                    )
            resp = processor.batch_decode(
                out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
            )[0].strip()
        except Exception as e:  # noqa: BLE001 — surface as 503 detail + server log
            log.exception("Local vision generate failed (%s)", VISION_LOCAL_MODEL)
            raise RuntimeError(f"Local vision failed: {type(e).__name__}: {e}") from e
        if not resp:
            raise RuntimeError("Local vision model returned an empty description")
        log.info(
            "Vision(local): described in %.2fs (%d chars, %s)",
            time.perf_counter() - t0, len(resp), VISION_LOCAL_MODEL,
        )
        return resp


def _screen_describe_api(image_b64: str, key: str, http_client: httpx.Client | None = None) -> str:
    """Describe one screenshot with the hosted Qwen2.5-VL (OpenAI-compatible)."""
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                    {"type": "text", "text": VISION_DESC_PROMPT},
                ],
            }
        ],
        "max_tokens": 500,
        "temperature": 0.2,
    }
    client = http_client or httpx.Client(timeout=VISION_TIMEOUT, follow_redirects=True)
    try:
        r = client.post(
            f"{VISION_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
    except httpx.HTTPError as e:
        raise RuntimeError(f"Vision request failed: {e}") from e
    if r.status_code != 200:
        raise RuntimeError(f"Vision API {r.status_code}: {r.text[:200]!r}")
    try:
        desc = r.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Unexpected vision response: {e}") from e
    if not desc:
        raise RuntimeError("Vision model returned an empty description")
    return desc


def _screen_backend_choice() -> str:
    """Effective backend for THIS call: 'api' | 'local' | raises."""
    if VISION_BACKEND == "api":
        return "api"
    if VISION_BACKEND == "local":
        return "local"
    # auto: hosted API when a key exists (fastest first token), else local
    return "api" if _vision_api_key() else "local"


# Coalescing: while one (slow) local describe runs, newer requests for the
# SAME screen arrive and would each queue behind it. The winner of the race
# describes the LATEST frame; losers get that result instead of queueing a
# redundant generate of an already-stale screen.
_screen_pending: dict = {}  # hash -> threading.Event
_screen_pending_lock = threading.Lock()


def _evict_stale_pending(pending_dict: dict, lock: threading.Lock, max_age_s: float = 120) -> None:
    """Evict entries older than max_age_s from a pending dictionary.

    Each entry is a threading.Event with a _created_at timestamp attribute.
    This prevents unbounded memory growth from stale entries.
    """
    now = time.monotonic()
    with lock:
        stale_keys = [
            key for key, evt in pending_dict.items()
            if getattr(evt, '_created_at', now) < now - max_age_s
        ]
        for key in stale_keys:
            del pending_dict[key]


def _screen_context(
    image_b64: str,
    client_hash: str = "",
    force: bool = False,
    http_client: httpx.Client | None = None,
) -> tuple[str, bool, str]:
    """Describe one screenshot; cache-first by client hash.

    Returns (description, was_cached, model_name_actually_used).

    force=True ("check again") skips the cache AND coalescing so the screen
    is genuinely re-described even if this hash was described before.

    Engine: VISION_BACKEND=auto (default) uses the hosted API when a key is
    configured, otherwise the LOCAL Qwen2.5-VL-3B loaded in this process (no
    key needed — the Kaggle path). Raises on any error so the caller can
    decide whether to fall back to a text-only reply.

    Coalescing: concurrent requests with the same hash collapse into ONE
    generate — the first caller runs it, the rest piggyback on its result.
    """
    if client_hash and not force:
        with _screen_lock:
            if (
                _screen_cache["hash"] == client_hash
                and _screen_cache["desc"]
                and time.monotonic() - _screen_cache["ts"] < SCREEN_CACHE_TTL
            ):
                return _screen_cache["desc"], True, _screen_cache["model"]
    # ---- piggyback on an in-flight describe of THIS screen ----------------
    # (registered winner still running -> wait for its result instead of
    #  queueing a redundant generate of the same stale screen)
    if client_hash and not force:
        with _screen_pending_lock:
            evt = _screen_pending.get(client_hash)
        if evt is not None and evt.wait(timeout=90):
            with _screen_lock:
                if _screen_cache["hash"] == client_hash and _screen_cache["desc"]:
                    return _screen_cache["desc"], True, _screen_cache["model"]
        # timeout / winner failed -> fall through and describe ourselves
    # ---- register as the winner (or run unhashed) -------------------------
    is_winner = False
    evt = None
    if client_hash and not force:
        with _screen_pending_lock:
            existing = _screen_pending.get(client_hash)
            if existing is not None:
                # someone registered between our check and now — piggyback
                if existing.wait(timeout=90):
                    with _screen_lock:
                        if _screen_cache["hash"] == client_hash and _screen_cache["desc"]:
                            return _screen_cache["desc"], True, _screen_cache["model"]
                # winner failed/timed out — we take over as the new winner
            else:
                evt = threading.Event()
                evt._created_at = time.monotonic()  # type: ignore[attr-defined]
                _screen_pending[client_hash] = evt
                is_winner = True
    t0 = time.perf_counter()
    backend = _screen_backend_choice()
    try:
        if backend == "api":
            key = _vision_api_key()
            if not key:
                raise RuntimeError(
                    "Vision API key not configured (set VISION_API_KEY or DASHSCOPE_API_KEY in .env, "
                    "or set VISION_BACKEND=local to use the local Qwen2.5-VL-3B)"
                )
            desc = _screen_describe_api(image_b64, key, http_client)
            model_used = VISION_MODEL
        else:
            if not _local_vlm_available():
                raise RuntimeError(
                    "Local vision needs 'pip install transformers pillow' (or set VISION_API_KEY "
                    "to use the hosted Qwen2.5-VL API instead)"
                )
            desc = _screen_describe_local(image_b64)
            model_used = VISION_LOCAL_MODEL
        with _screen_lock:
            _screen_cache.update(
                {"hash": client_hash or None, "desc": desc, "ts": time.monotonic(), "model": model_used}
            )
        log.info(
            "Vision(%s/%s): screen described in %.2fs (%d chars)",
            backend, model_used, time.perf_counter() - t0, len(desc),
        )
        return desc, False, model_used
    finally:
        if is_winner and evt is not None:
            with _screen_pending_lock:
                if _screen_pending.get(client_hash) is evt:
                    del _screen_pending[client_hash]
            evt.set()  # wake piggybackers (cache now holds the result)
        # Evict stale entries (> 2 minutes) to prevent memory leaks
        _evict_stale_pending(_screen_pending, _screen_pending_lock, max_age_s=120)


# Cold-cache softener: if a describe for THIS screen is ALWAYS in flight
# when the user asks, wait up to this long for it. Keep small — OCR now
# carries the fresh ground truth, so stalling for the slow local VLM (5-7 s)
# is never worth it.
VISION_REPLY_WAIT_S = float(os.environ.get("VISION_REPLY_WAIT_S", "0.3"))
# Hard cap on how long a push-to-see turn may wait for the slow local VLM. The
# reply is OCR-first now, so a long wait only adds latency without improving
# accuracy. Keep this small (~500ms) so an in-flight describe can still land.
SCREEN_WAIT_MAX_S = float(os.environ.get("VOICE_SCREEN_WAIT_MAX_MS", "500")) / 1000.0
# How old a cached VLM description (of ANY screen) may be and still be used
# as the visual summary when the CURRENT screen's describe isn't ready. The
# current screen's exact OCR text still arrives inline in the same block, so
# the LLM sees today's screen truthfully; the stale summary just saves the
# "everything is pending / wait a minute" dead end. Set 0 to disable.
SCREEN_STALE_DESC_S = float(os.environ.get("SCREEN_STALE_DESC_S", "45"))


def _screen_cached_desc(client_hash: str = "", wait_s: float = 0.0) -> tuple[str, str]:
    """PEEK the screen cache without starting any compute — the reply path
    never waits for vision unless a describe is ALREADY running for this
    exact screen (then wait up to wait_s for it to land).
    Returns (description, model) or ("", "")."""
    if not client_hash:
        return "", ""
    deadline = time.monotonic() + max(0.0, wait_s)
    while True:
        with _screen_lock:
            if (
                _screen_cache["hash"] == client_hash
                and _screen_cache["desc"]
                and time.monotonic() - _screen_cache["ts"] < SCREEN_CACHE_TTL
            ):
                return _screen_cache["desc"], _screen_cache["model"]
        if time.monotonic() >= deadline:
            return "", ""
        with _screen_pending_lock:
            evt = _screen_pending.get(client_hash)
        if evt is None:
            return "", ""  # nothing in flight — waiting can never help
        evt.wait(timeout=0.3)  # poll; the in-flight describe may finish


_latest_vision_job: dict = {"img": None, "hash": "", "force": False}
_vision_job_lock = threading.Lock()
_vision_worker_running = False


def _vision_drain_worker() -> None:
    global _vision_worker_running
    while True:
        # PRIORITY PAUSE: while a chat turn is synthesizing, TTS windows are
        # grabbed first by GPU_GENERATE_LOCK and this VLM generate would spin
        # CPU + hold the GPU queue behind TTS — directly adding to the reply's
        # first-audio latency. When sharing is active the client keeps sending
        # fresh frames, so a deferred screen is NEVER stale: skip the deferred
        # one and describe the newest on resume.
        while _screen_busy():
            with _vision_job_lock:
                _latest_vision_job["img"] = None  # drop stale frame, keep latest wins
            _wait_for_screen_resume(timeout=1.0)
        with _vision_job_lock:
            img = _latest_vision_job.get("img")
            chash = _latest_vision_job.get("hash", "")
            force = _latest_vision_job.get("force", False)
            _latest_vision_job["img"] = None
        if not img:
            with _vision_job_lock:
                _vision_worker_running = False
            break
        try:
            _screen_context(img, chash, force=force)
        except Exception as e:
            log.warning("Background screen describe failed: %s", e)


def _warm_screen_cache(image_b64: str, client_hash: str = "", force: bool = False) -> None:
    """Queue a background describe, ALWAYS keeping ONLY the newest frame.

    Overwrites older pending frames so threads never queue up on the VLM,
    eliminating multi-minute backlogs and stale repeat descriptions.
    Single worker: the /api/vision warm-up POSTs and per-turn warm calls all
    collapse into one describe at a time.
    """
    global _vision_worker_running
    with _vision_job_lock:
        _latest_vision_job["img"] = image_b64
        _latest_vision_job["hash"] = client_hash
        _latest_vision_job["force"] = force
        if not _vision_worker_running:
            _vision_worker_running = True
            threading.Thread(target=_vision_drain_worker, daemon=True).start()


# ---------- Screen layer 1: fast OCR text (RapidOCR, ~100-300 ms) ----------
# The VLM summary (layer 2) is rich but slow, so its cache can be seconds
# stale. OCR is 30-50x cheaper, so the reply path can run it INLINE — text on
# screen is never more than ~1 turn old. Errors, code, file names, terminal
# output all arrive as exact text, which is exactly what a tutor quotes.
_ocr_lock = threading.Lock()
_ocr_engine = None
_ocr_cuda = False  # set by _load_ocr (CUDA build -> inline recheck OCR is affordable)
_ocr_disabled = False  # set once if rapidocr is not installed
_ocr_slow_detected = False  # circuit breaker: if OCR takes > 1.2s, never stall chat inline
_ocr_cache: dict = {"hash": None, "text": "", "ts": 0.0}
# Coalescing: only ONE OCR run per screen hash at a time. The inline reply path
# abandons its thread at the 300 ms deadline, but that thread keeps running and
# stays the winner; the background fallback for the SAME hash piggybacks on its
# result instead of re-running a second multi-second OCR (seen in the logs as
# two "OCR: N lines" lines seconds apart for one screen).
_ocr_pending: dict = {}  # hash -> threading.Event
_ocr_pending_lock = threading.Lock()
_OCR_COALESCE_TIMEOUT_S = 20.0
OCR_MAX_SIDE = int(os.environ.get("VISION_OCR_MAX_SIDE", "768"))
OCR_MAX_LINES = int(os.environ.get("VISION_OCR_MAX_LINES", "60"))

def _cuda_libs_loadable() -> bool:
    """True only if the CUDA runtime libs onnxruntime-gpu dlopens actually load.

    Merely having CUDAExecutionProvider in get_available_providers() is NOT
    enough — a CUDA-13 build on a CUDA-12 host (e.g. latest onnxruntime-gpu on
    Kaggle) lists the provider, then fails at session creation and silently
    falls back to CPU. Preloading the exact sonames with RTLD_GLOBAL both
    verifies them and satisfies the provider's later dlopen.
    """
    import ctypes
    import glob

    candidates: list[str] = []
    for soname in ("libcublasLt.so.12", "libcudnn.so.9"):
        found = ctypes.util.find_library(soname.removeprefix("lib").removesuffix(".so.12").removesuffix(".so.9"))
        paths = [soname]
        # pip-installed NVIDIA wheels keep libs outside the ld search path
        for pat in (
            f"/usr/lib/python3*/dist-packages/nvidia/*/lib/{soname}",
            f"/usr/local/lib/python3*/dist-packages/nvidia/*/lib/{soname}",
            f"/usr/lib/python3*/site-packages/nvidia/*/lib/{soname}",
        ):
            paths.extend(glob.glob(pat))
        loaded = False
        for p in paths:
            try:
                ctypes.CDLL(p, mode=ctypes.RTLD_GLOBAL)
                loaded = True
                break
            except OSError:
                continue
        if not loaded:
            log.warning("CUDA lib %s not loadable — GPU OCR disabled (CPU fallback)", soname)
            return False
        candidates.append(soname)
    return True


def _load_ocr():
    global _ocr_engine, _ocr_cuda
    if _ocr_engine is not None:
        return _ocr_engine
    with _ocr_lock:
        if _ocr_engine is not None:
            return _ocr_engine
        from rapidocr_onnxruntime import RapidOCR

        t0 = time.perf_counter()
        try:
            import onnxruntime as _ort

            use_cuda = "CUDAExecutionProvider" in _ort.get_available_providers() and _cuda_libs_loadable()
        except Exception:  # noqa: BLE001
            use_cuda = False
        if use_cuda:
            _ocr_cuda = True
            _ocr_engine = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
            log.info("RapidOCR ready on CUDA in %.1fs", time.perf_counter() - t0)
        else:
            _ocr_engine = RapidOCR()
            log.info(
                "RapidOCR ready on CPU in %.1fs — SLOW for dense screens; "
                "install onnxruntime-gpu for ~10x faster OCR",
                time.perf_counter() - t0,
            )
        return _ocr_engine


def _screen_ocr(image_b64: str, client_hash: str = "", force: bool = False) -> str:
    """Fast text layer: OCR one frame. Cached by hash; ~100-300 ms on GPU.
    force=True skips the cache read (user said 'check again')."""
    if client_hash and not force:
        with _ocr_lock:
            if (
                _ocr_cache["hash"] == client_hash
                and _ocr_cache["text"]
                and time.monotonic() - _ocr_cache["ts"] < SCREEN_CACHE_TTL
            ):
                return _ocr_cache["text"]
        # Atomic check-and-register: ONE OCR run per hash at a time. Late
        # callers (e.g. the background fallback spawned after the inline reply
        # path abandoned its 300 ms deadline) piggyback on the winner's result
        # instead of stacking a second multi-second run on the same engine.
        with _ocr_pending_lock:
            existing = _ocr_pending.get(client_hash)
            if existing is None:
                evt = threading.Event()
                evt._created_at = time.monotonic()  # type: ignore[attr-defined]
                _ocr_pending[client_hash] = evt
                registered = True
            else:
                registered = False
        if not registered:
            if existing.wait(timeout=_OCR_COALESCE_TIMEOUT_S):
                with _ocr_lock:
                    if (
                        _ocr_cache["hash"] == client_hash
                        and _ocr_cache["text"]
                        and time.monotonic() - _ocr_cache["ts"] < SCREEN_CACHE_TTL
                    ):
                        return _ocr_cache["text"]
            return ""  # winner still running or failed — the next turn will retry
    import base64

    from PIL import Image

    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    if max(img.size) > OCR_MAX_SIDE:
        img.thumbnail((OCR_MAX_SIDE, OCR_MAX_SIDE))
    engine = _load_ocr()
    t0 = time.perf_counter()
    try:
        result, _ = engine(np.asarray(img))
    finally:
        # signal piggybackers regardless of success/failure so they never hang
        if client_hash and not force:
            with _ocr_pending_lock:
                evt = _ocr_pending.pop(client_hash, None)
            if evt is not None:
                evt.set()
        # Evict stale entries (> 2 minutes) to prevent memory leaks
        _evict_stale_pending(_ocr_pending, _ocr_pending_lock, max_age_s=120)
    elapsed = time.perf_counter() - t0
    if elapsed > 1.2:
        global _ocr_slow_detected
        if not _ocr_slow_detected:
            _ocr_slow_detected = True
            log.warning("OCR took %.2fs (>1.2s threshold) — switching to background OCR to protect chat latency", elapsed)
    lines = [r[1].strip() for r in (result or []) if r[1] and r[1].strip()]
    text = "\n".join(lines[:OCR_MAX_LINES])
    with _ocr_lock:
        _ocr_cache.update({"hash": client_hash or None, "text": text, "ts": time.monotonic()})
    log.info("OCR: %d lines in %.2fs", len(lines), elapsed)
    return text


def _screen_layers(client_hash: str = "", image_b64: str = "", wait_s: float | None = None) -> dict:
    """ALWAYS-REALTIME screen context for the reply path (executor thread).

    The client captures the frame AT QUESTION TIME, so the hash is current:
      - hash in OCR cache  -> screen pixels are unchanged -> cached text IS
        the current screen (0 ms)
      - hash miss          -> screen changed -> OCR runs INLINE with a hard
        300 ms budget; slower environments fall through to background-only
    VLM summary: cache peek with bounded wait; on a miss, a RECENT describe
    (any screen, <SCREEN_STALE_DESC_S old) is used so the tutor never falls
    into the 'analysis pending / wait a minute' dead end mid-share.

    wait_s: how long to wait for an in-flight describe of THIS exact screen
    (push-to-see turns pass a larger budget — the client warmed the cache
    during the button hold, so the describe is usually already running and
    lands well inside the wait). Defaults to VISION_REPLY_WAIT_S.
    """
    global _ocr_disabled
    desc, model_used = _screen_cached_desc(
        client_hash, VISION_REPLY_WAIT_S if wait_s is None else max(0.0, wait_s)
    )
    if not desc and SCREEN_STALE_DESC_S > 0:
        # This EXACT screen was never (or not yet) described, but a recent
        # describe of a NEARLY IDENTICAL screen (client keeps streaming frames
        # while sharing; the user typically hasn't changed much since the last
        # tick) usually exists. Prefer it over the pending dead-end: the tutor
        # should lean on the freshest OCR text and never answer 'wait a
        # minute' when it described a screen seconds ago. Set
        # SCREEN_STALE_DESC_S=0 to restore the strict old behavior.
        with _screen_lock:
            if (_screen_cache["desc"]
                    and time.monotonic() - _screen_cache["ts"] < SCREEN_STALE_DESC_S):
                desc = _screen_cache["desc"]
                model_used = _screen_cache["model"]
    ocr = ""
    if client_hash:
        with _ocr_lock:
            if (
                _ocr_cache["hash"] == client_hash
                and _ocr_cache["text"]
                and time.monotonic() - _ocr_cache["ts"] < SCREEN_CACHE_TTL
            ):
                ocr = _ocr_cache["text"]
    if not ocr and image_b64 and not _ocr_disabled:
        # Inline OCR with a HARD 300 ms budget: run in a throwaway thread and
        # abandon it past the deadline (the chat reply NEVER waits longer —
        # the abandoned run's result still lands in the OCR cache for the
        # next turn). Cheap OCR carries the exact text ground truth inline;
        # slow environments fall through to background-only automatically.
        #
        # COLD-START RETRY: the FIRST OCR after boot pays the engine's lazy
        # init (~3-7 s), so the first inline attempt ALWAYS times out — but
        # the abandoned run warms the engine, and a SECOND immediate attempt
        # then completes in ~100-300 ms. IMPORTANT: the retry must never
        # BLOCK the reply on a genuinely slow engine (CPU OCR can take 3-7 s
        # per run even warm) — the whole inline path is capped well under a
        # second; anything slower falls through to background-only.
        result_holder: dict = {}
        _inline_ocr_deadline = time.monotonic() + 0.85  # total inline budget

        def _run_ocr() -> None:
            try:
                result_holder["text"] = _screen_ocr(image_b64, client_hash)
            except Exception:  # noqa: BLE001 — OCR must never break a reply
                pass

        t = threading.Thread(target=_run_ocr, daemon=True)
        t.start()
        t.join(timeout=0.3)  # 300 ms first attempt
        if t.is_alive():
            # Cold engine: a retry can't finish either — but if the FIRST run
            # lands shortly (engine warmed mid-flight), grab its result while
            # it is still fresh. NEVER join longer than the total budget.
            t.join(timeout=max(0.0, _inline_ocr_deadline - time.monotonic()))
            if result_holder.get("text"):
                ocr = result_holder["text"]
            elif not t.is_alive():
                ocr = result_holder.get("text", "")  # finished just past deadline
            else:
                log.warning("Inline OCR exceeded budget, falling back to background")
                threading.Thread(
                    target=_warm_screen_ocr, args=(image_b64, client_hash), daemon=True
                ).start()
        else:
            ocr = result_holder.get("text", "")
    return {"ocr": ocr, "desc": desc, "model": model_used}


def _warm_screen_ocr(image_b64: str, client_hash: str = "") -> None:
    """Fire-and-forget background OCR so the NEXT turn has fresh text."""
    global _ocr_disabled
    if _ocr_disabled:
        return
    try:
        _screen_ocr(image_b64, client_hash)
    except Exception as e:  # noqa: BLE001
        if isinstance(e, ImportError):
            _ocr_disabled = True
            log.warning("rapidocr_onnxruntime not installed — OCR layer disabled (pip install rapidocr-onnxruntime)")
        else:
            log.warning("Background OCR failed: %s", e)


# Appended to the system prompt on turns that carry screen context.
# The rules make the tutor ACTIVE: reference what is visible, quote exact
# text ("ये undefined दिख रहा है"), and direct the user's attention
# ("ये file खोलकर दिखाओ") — like a tutor sitting next to the student.

