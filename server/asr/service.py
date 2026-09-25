"""Whisper, VAD, and speaker verification services."""

import importlib.util
import logging
import os
import re
import sys
import threading

import numpy as np
import torch

from pathlib import Path

log = logging.getLogger("voice_api")
HERE = Path(__file__).resolve().parent.parent
REF_AUDIO = Path(os.environ.get("VOICE_REF_AUDIO", HERE / "my_voice.wav")).expanduser()
if not REF_AUDIO.is_absolute():
    REF_AUDIO = HERE / REF_AUDIO

# ---------- Streaming ASR — the voice-input path ----------
# The browser streams the AEC-processed 16 kHz mic PCM here over /ws/asr and
# we transcribe it locally — the same pattern OpenAI/Gemini realtime use:
# recognize the getUserMedia stream AFTER the browser's acoustic echo
# canceller has removed the assistant's own output, instead of the Web Speech
# API (whose separate capture path never gets that echo reference). Partial
# transcripts stream back as live captions; the client signals utterance
# boundaries with "start" / "end" JSON messages.
#
# Two switchable local backends (ASR_BACKEND):
#   * "mlx"            — mlx-whisper on Apple Silicon (Neural Engine). ~10x
#                        faster than CPU Whisper on an M4. Apple-only.
#   * "faster-whisper" — CTranslate2: CUDA fp16 (realtime — the Kaggle/NVIDIA
#                        GPU path) or CPU int8.
# ASR_BACKEND=auto picks mlx when running on Apple Silicon with mlx-whisper
# installed, else faster-whisper — so this exact code runs on the M4 Mac AND
# on Kaggle's Linux GPU with no edits.
ASR_BACKEND = (os.environ.get("ASR_BACKEND", "") or "auto").strip().lower()
# faster-whisper tuning (ignored by the mlx backend): device auto-selects CUDA
# when available, else CPU; compute auto-follows.
ASR_DEVICE = (os.environ.get("ASR_DEVICE", "").strip().lower()
              or ("cuda" if torch.cuda.is_available() else "cpu"))
ASR_COMPUTE = (os.environ.get("ASR_COMPUTE", "").strip().lower()
               or ("float16" if ASR_DEVICE.startswith("cuda") else "int8"))
# Model size (shared by both backends): "small" is the smallest Whisper size
# that transcribes Hindi well (base/tiny mangle it). On CUDA small is
# realtime; on the M4 the mlx backend makes it ~10x realtime.
ASR_MODEL = os.environ.get("ASR_MODEL", "") or "large-v3-turbo"
# CPU threads for the CTranslate2 (faster-whisper) decode. CTranslate2's own
# default (4) has been observed to corrupt the glibc heap on some Linux
# boxes ("malloc(): unaligned tcache chunk detected" kills the whole server
# after the second decode) — 2 threads avoids that OpenMP path and is still
# comfortably realtime for 3-10 s utterances. Raise via .env if you need more.
ASR_CPU_THREADS = int(os.environ.get("ASR_CPU_THREADS", "2"))
# Spoken language: "hi" = Hindi/Hinglish, accurate and fast (no detection
# pass). LEAVE EMPTY only for true multilingual mode — auto-detect is great
# for English but routinely mislabels SHORT Hindi clips (es/ru/ur/si).
ASR_LANG = os.environ.get("ASR_LANG", "hi") or None
ASR_SR = 16000
# faster-whisper only: the AUTHORITATIVE final after "end" gets a beam-search
# decode + VAD trimming (better Hinglish accuracy for ~1.5x the cost of one
# greedy pass, once per utterance). Live captions stay greedy/beam-1.
# mlx-whisper 0.4.x has no beam decoder, so it always decodes greedily.
ASR_FINAL_BEAM = int(os.environ.get("ASR_FINAL_BEAM", "1"))
# Anti-repetition loops ("अगर अगर अगर…"): every transcript passes through
# _collapse_repeats(), the mlx decoder keeps Whisper's temperature fallback
# ladder (we used to force temperature=0.0, which DISABLED loop detection),
# and faster-whisper additionally blocks repeated 3-word n-grams.
ASR_NO_REPEAT_NGRAM = int(os.environ.get("VOICE_ASR_NO_REPEAT_NGRAM", "3"))  # fw only; 0 = off
ASR_MAX_DUP = int(os.environ.get("VOICE_ASR_MAX_DUP", "2"))  # keep at most N identical neighbours
# Whisper partials cost ~linear in buffered audio, so only re-run when this
# much NEW audio arrived since the last partial AND at least this long passed.
ASR_PARTIAL_MIN_NEW = float(os.environ.get("VOICE_ASR_PARTIAL_NEW_SECONDS", "0.45"))
ASR_PARTIAL_MIN_GAP = float(os.environ.get("VOICE_ASR_PARTIAL_GAP_SECONDS", "0.9"))
# Speculative turn trigger: at "end" we first decode GREEDY (fast) and send it
# to the browser as a "speculative" transcript so the LLM reply starts right
# away — the slower beam+VAD decode then follows as the authoritative "final"
# and the client reconciles the two (replace only if they meaningfully differ).
# This removes the beam decode (~0.3-1.5 s on CPU) from the front of the
# reply latency. VOICE_SPECULATIVE_MS bounds how long the client waits for the
# final before releasing the mic anyway.
ASR_SPECULATIVE = os.environ.get("VOICE_ASR_SPECULATIVE", "1").strip().lower() not in ("0", "false", "no")
ASR_SPECULATIVE_MS = int(os.environ.get("VOICE_SPECULATIVE_MS", "5000"))
ASR_INITIAL_PROMPT = os.environ.get(
    "ASR_INITIAL_PROMPT",
    "नमस्ते, क्या हाल है? कोडिंग, एआई, कंप्यूटर, प्रोग्रामिंग, ऐप, डेटा, सवाल, जवाब।"
).strip() or None

# ---------- Server-side neural VAD (Silero) — the noise-immune turn-taker ----------
#
# The browser's energy VAD cannot tell VOICE from NOISE — a fan, door slam or
# keyboard burst crosses the loudness gate, opens an utterance, and Whisper
# transcribes garbage into a phantom reply. Silero is a tiny neural net that
# classifies speech vs non-speech per 32 ms frame, so noise never opens a turn.
#
# Architecture (what LiveKit/Pipecat-class stacks do):
#   browser  -> streams AEC mic PCM continuously (a thin dumb streamer)
#   server   -> Silero decides open/close; pre-roll ring keeps first words;
#               utterance close triggers the decode pipeline (early decode
#               overlapped while silence is being confirmed, as before)
#   legacy   -> ASR_VAD_MODE=client keeps the old browser-energy behavior
#
# "auto": Silero if the package is installed, else client VAD (graceful).
VAD_MODE = (os.environ.get("ASR_VAD_MODE", "auto").strip().lower() or "auto")
SILERO_ON_THRESH = float(os.environ.get("VOICE_SILERO_ON", "0.55"))     # p(voice) to OPEN (high = noise-proof)
SILERO_HOLD_THRESH = float(os.environ.get("VOICE_SILERO_HOLD", "0.35"))  # p(voice) to STAY open (hysteresis)
SILERO_ON_MS = int(os.environ.get("VOICE_SILERO_ON_MS", "150"))          # speech this long opens the turn
# Silence this long closes it. 550ms balances conversational speed and natural
# pauses without splitting utterances.
SILERO_SILENCE_MS = int(os.environ.get("VOICE_SILERO_SILENCE_MS", "500"))
# Once silence has lasted this long AND the overlapped early decode has already
# produced a transcript, close the utterance early instead of waiting the full
# 550ms. This is the sub-second endpointing lever: the early decode (P2) runs
# during silence, so its result is usually ready by ~250ms.
SILERO_SILENCE_MIN_MS = int(os.environ.get("VOICE_SILERO_SILENCE_MIN_MS", "250"))
SERVER_PRE_ROLL_S = float(os.environ.get("VOICE_SERVER_PRE_ROLL_S", "0.4"))  # kept before the open decision
MIN_UTT_MS = int(os.environ.get("VOICE_MIN_UTT_MS", "300"))              # shorter utterances are discarded as blips
# Client self-barge guard: right after a new turn is submitted, the browser can
# still fire a stale hardStop() from the PREVIOUS turn's VAD burst, which sends
# "stop" and kills the fresh reply (0 frames). Ignore "stop" for this long after
# a turn starts; real user barge-in happens after the first audio, later.
STOP_GRACE_S = float(os.environ.get("VOICE_STOP_GRACE_MS", "250")) / 1000.0


def _pick_vad_mode() -> str:
    if VAD_MODE == "server":
        return "server"
    if VAD_MODE in ("client", "browser"):
        return "client"
    try:
        import silero_vad  # noqa: F401
        return "server"
    except ImportError:
        return "client"


VAD_BACKEND = _pick_vad_mode()  # resolved once at boot; logged + served via /api/config


class _Silero:
    """Lazy-loaded Silero VAD (ONNX/JIT, CPU) shared by all /ws/asr workers.

    The model is stateful per stream: each worker calls reset() when an
    utterance opens so hidden state never bleeds across turns. Feed exactly
    512-sample float32 chunks @16 kHz; returns p(speech) in [0, 1].
    """

    def __init__(self):
        import warnings
        from silero_vad import load_silero_vad
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model = load_silero_vad()

    def p(self, frame512: np.ndarray) -> float:
        import torch
        with torch.no_grad():
            return float(self.model(torch.from_numpy(frame512), 16000).item())

    def reset(self) -> None:
        """Clear the internal LSTM hidden state (JIT model keeps _h/_c).

        Called when an utterance opens so state from the previous turn can't
        bleed into the new one. Best-effort across silero-vad versions: if the
        attributes move, skipping the reset must never crash the worker.
        """
        import torch
        for attr in ("_h", "_c"):
            try:
                t = getattr(self.model, attr, None)
                if isinstance(t, torch.Tensor):
                    setattr(self.model, attr, torch.zeros_like(t))
            except Exception:  # noqa: BLE001 — hygiene only, never fatal
                pass


_silero: _Silero | None = None
_silero_lock = threading.Lock()


def _get_silero() -> _Silero:
    global _silero
    if _silero is None:
        with _silero_lock:
            if _silero is None:
                _silero = _Silero()
    return _silero


# ---------- Speaker-identity gate (whose voice is it?) ----------
#
# Neither a denoiser nor Silero can reject a SECOND HUMAN VOICE (a phone
# playing a video next to the mic): noise-cancelers remove stationary noise,
# and Silero classifies speech vs non-speech — a video's speech is speech.
# A single microphone also cannot measure distance, so "only the closest
# voice" is not physically available.
#
# The professional answer (the same trick as "Hey Siri" / "OK Google"):
# SPEAKER VERIFICATION. Enroll the primary speaker's voiceprint once (the
# voice-clone reference clip already on disk), and before transcribing an
# utterance verify it actually sounds like that speaker. Cosine similarity
# of d-vector embeddings: same speaker ~0.75-0.95, other voices/noise ~0.4-0.6
# -> a tunable threshold rejects the TV/phone/roommate no matter how loud.
#
# Tunables (.env):
#   VOICE_SPEAKER_GATE   auto (default) = on when resemblyzer + ref clip exist
#                        0/off = disable entirely
#   VOICE_SPEAKER_SIM_MIN  cosine threshold (default 0.62); raise for stricter
SPEAKER_GATE = (os.environ.get("VOICE_SPEAKER_GATE", "auto").strip().lower() or "auto")
# 0.45, not 0.62: the reference clip is a clean recording, but the LIVE voice
# arrives through Chrome's AEC/NS/AGC, and that channel difference alone drops
# the SAME speaker's cosine similarity to ~0.49-0.55 (observed on this setup).
# 0.62 rejected the user's own voice on every utterance; 0.45 still separates
# a clearly-different voice (phone/video/TV ~0.30-0.45) from the primary user.
SPEAKER_SIM_MIN = float(os.environ.get("VOICE_SPEAKER_SIM_MIN", "0.45"))
_speaker_emb: np.ndarray | None = None
_speaker_enc = None
_speaker_lock = threading.Lock()


def _get_speaker_ref() -> np.ndarray | None:
    """Lazily build the primary-speaker voiceprint from the reference clip."""
    global _speaker_emb, _speaker_enc
    if SPEAKER_GATE in ("0", "off", "false", "no"):
        return None
    if _speaker_emb is None:
        with _speaker_lock:
            if _speaker_emb is None:
                if not REF_AUDIO.exists():
                    log.warning("Speaker gate: reference clip %s missing — gate disabled", REF_AUDIO.name)
                    _speaker_emb = np.zeros(0, dtype=np.float32)  # sentinel: unavailable
                    return None
                try:
                    from resemblyzer import VoiceEncoder, preprocess_wav
                    if _speaker_enc is None:
                        _speaker_enc = VoiceEncoder()
                    wav = preprocess_wav(str(REF_AUDIO))
                    if len(wav) < int(1.0 * 16000):
                        log.warning("Speaker gate: reference clip too short — gate disabled")
                        _speaker_emb = np.zeros(0, dtype=np.float32)
                        return None
                    _speaker_emb = _speaker_enc.embed_utterance(wav)
                    log.info("Speaker gate enrolled from %s (%.1fs of voice)", REF_AUDIO.name, len(wav) / 16000)
                except ImportError:
                    log.warning("Speaker gate: resemblyzer not installed (uv pip install resemblyzer) — gate disabled")
                    _speaker_emb = np.zeros(0, dtype=np.float32)
                    return None
                except Exception as e:  # noqa: BLE001 — gate must never kill ASR
                    log.warning("Speaker gate enrollment failed (%s) — gate disabled", e)
                    _speaker_emb = np.zeros(0, dtype=np.float32)
                    return None
    if _speaker_emb is not None and _speaker_emb.size == 0:
        return None
    return _speaker_emb


def _speaker_similarity(samples: np.ndarray) -> float | None:
    """Cosine similarity of an utterance against the enrolled voiceprint.

    Uses only the loudest ~6 s of speech (embed_utterance is O(seconds) and
    utterances are short anyway). None = gate unavailable/disabled.
    """
    ref = _get_speaker_ref()
    if ref is None:
        return None
    try:
        from resemblyzer import preprocess_wav
        if samples.size > 6 * ASR_SR:
            samples = samples[-6 * ASR_SR:]  # most recent speech carries the ID
        emb = _speaker_enc.embed_utterance(preprocess_wav(samples, ASR_SR))
        return float(np.dot(ref, emb))
    except Exception as e:  # noqa: BLE001 — fail open: decode proceeds
        log.warning("Speaker gate check failed (%s) — allowing utterance", e)
        return None

# HF repo ids of the MLX-converted Whisper checkpoints per size. A full repo id
# (containing "/") in ASR_MODEL is passed through untouched.
# NOTE: the turbo checkpoint on HF is "whisper-large-v3-turbo" (no -mlx suffix) —
# guessing the suffix produced a 404 that silently killed ASR.
_MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-turbo": "mlx-community/whisper-large-v3-turbo",  # alias
    "turbo": "mlx-community/whisper-turbo",
}


def _mlx_repo(model_name: str) -> str:
    if "/" in model_name:
        return model_name
    return _MLX_REPOS.get(model_name.lower(), f"mlx-community/whisper-{model_name}-mlx")


def _pick_asr_backend() -> str:
    """Which backend will run (no heavy imports): auto prefers mlx on the Mac."""
    if ASR_BACKEND == "mlx":
        return "mlx"
    if ASR_BACKEND in ("faster-whisper", "faster_whisper", "fw"):
        return "faster-whisper"
    if sys.platform == "darwin":  # auto: Apple Silicon + mlx installed -> mlx
        import importlib.util
        if importlib.util.find_spec("mlx_whisper") is not None:
            return "mlx"
    return "faster-whisper"


_asr_backend = None   # one loaded backend object, reused for every call
_asr_lock = threading.Lock()  # one Whisper call at a time (single device)
_asr_ready_event = threading.Event()  # Set once the ASR backend finished its warmup load


class _MlxAsr:
    """mlx-whisper (Apple Neural Engine). Greedy decode only; the library caches
    the loaded model in memory, so repeated calls stay fast."""

    name = "mlx"

    def __init__(self):
        try:
            import mlx_whisper  # noqa: F401 — Apple-only import
        except ImportError:
            raise RuntimeError(
                "ASR_BACKEND=mlx needs mlx-whisper (Apple Silicon only): run "
                "'uv pip install -p omnivoice-env/bin/python mlx-whisper'. "
                "On Kaggle/NVIDIA leave ASR_BACKEND=auto to use faster-whisper on CUDA."
            ) from None
        self._transcribe = mlx_whisper.transcribe
        self._repo = _mlx_repo(ASR_MODEL)
        # Fail fast + load at boot, not on the user's first utterance: a wrong
        # ASR_MODEL used to surface as an HF 404 INSIDE the /ws/asr worker and
        # silently kill transcription while /api/config still said asr_ready.
        from huggingface_hub import model_info
        model_info(self._repo)  # raises RepositoryNotFoundError for a bad repo id
        try:
            import numpy as _np
            self.transcribe(_np.zeros(ASR_SR, dtype=_np.float32))  # warm the weights
        except Exception as e:  # noqa: BLE001 — warm decode is best-effort
            log.warning("mlx ASR warm decode failed (first utterance may be slower): %s", e)

    def transcribe(self, samples: np.ndarray, beam: int = 1, vad: bool = False) -> str:
        # Keep mlx-whisper's temperature fallback ladder (we used to pin
        # temperature=0.0, which disabled Whisper's own repetition-loop
        # detection — the cause of "अगर अगर अगर…" transcripts).
        kwargs: dict = {
            "condition_on_previous_text": False,
            "verbose": None,
            "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        }
        if ASR_LANG:
            kwargs["language"] = ASR_LANG
        if ASR_INITIAL_PROMPT:
            kwargs["initial_prompt"] = ASR_INITIAL_PROMPT
        try:
            res = self._transcribe(samples, path_or_hf_repo=self._repo, **kwargs)
        except TypeError:
            # older mlx-whisper without the tuple-temperature API -> plain greedy
            kwargs = {k: v for k, v in kwargs.items() if k != "temperature"}
            res = self._transcribe(samples, path_or_hf_repo=self._repo, **kwargs)
        return (res.get("text") or "").strip()


class _FasterWhisperAsr:
    """faster-whisper (CTranslate2): CUDA fp16 or CPU int8."""

    name = "faster-whisper"

    def __init__(self):
        from faster_whisper import WhisperModel  # lazy: non-voice users never load it
        self._model = WhisperModel(
            ASR_MODEL,
            device=ASR_DEVICE,
            compute_type=ASR_COMPUTE,
            cpu_threads=ASR_CPU_THREADS,  # see ASR_CPU_THREADS note (heap-corruption workaround)
        )

    def transcribe(self, samples: np.ndarray, beam: int = 1, vad: bool = False) -> str:
        # Normalize audio peak so soft speech doesn't drop into silence hallucinations
        peak = float(np.abs(samples).max()) if samples.size else 0.0
        if peak > 0.005:
            samples = samples * (0.8 / max(peak, 0.15))

        segs, _info = self._model.transcribe(
            samples,
            language=ASR_LANG or "hi",
            task="transcribe",  # Explicitly enforce transcription (never translation into English)
            beam_size=beam,
            temperature=0.0,  # Strictly deterministic: prevents hallucination ladders
            condition_on_previous_text=False,
            vad_filter=True,  # Strip trailing/leading silence so Whisper decodes actual speech
            vad_parameters=dict(min_silence_duration_ms=200),
            initial_prompt=ASR_INITIAL_PROMPT or "नमस्ते राहुल भाई, आप कैसे हैं? हाँ, मैं पूछ रहा हूँ कि मेरी आवाज़ आपको आ रही है या नहीं?",
            no_repeat_ngram_size=max(0, ASR_NO_REPEAT_NGRAM),  # 0 disables (CTranslate2 convention)
        )
        return "".join(s.text for s in segs).strip()


def _get_asr():
    """Load (once) the backend selected by ASR_BACKEND and reuse it for all calls."""
    global _asr_backend
    if _asr_backend is None:
        with _asr_lock:  # serialize construction — never load the model twice
            if _asr_backend is None:
                chosen = _pick_asr_backend()
                log.info("Loading ASR backend '%s' (model '%s')...", chosen, ASR_MODEL)
                _asr_backend = _MlxAsr() if chosen == "mlx" else _FasterWhisperAsr()
                _asr_ready_event.set()
                log.info("ASR backend '%s' ready (model '%s').", chosen, ASR_MODEL)
    return _asr_backend


def _asr_ready() -> bool:
    """True once the ASR backend finished its warmup load."""
    return _asr_ready_event.is_set()


def _warmup_asr():
    """Background warmup: preload the ASR model at startup so the FIRST
    utterance isn't delayed by the model download/load. Never crashes boot."""
    try:
        _get_asr()
        log.info("ASR warmup complete.")
    except Exception as e:  # noqa: BLE001 — warmup must never kill the server
        log.error("ASR warmup failed (will retry lazily on first use): %s", e)


_HALLUCINATION_PHRASES = {
    "सब्सक्राइब करें", "सब्सक्राइब", "thank you for watching", "thanks for watching",
    "subtitles by", "please subscribe", "like share subscribe",
}


def _collapse_repeats(text: str) -> str:
    """Fix Whisper repetition loops and filter known YouTube/movie subtitle hallucinations."""
    t = (text or "").strip()
    if not t:
        return t
    norm_check = re.sub(r"[^\w\s\u0900-\u097F]", "", t).strip().lower()
    if norm_check in _HALLUCINATION_PHRASES:
        log.warning("ASR hallucination dropped: '%s'", t)
        return ""
    t = t.replace("\ufffd", " ")
    words = t.split()
    out: list[str] = []
    run_word, run_len = None, 0
    for w in words:
        if w == run_word:
            run_len += 1
            if run_len > max(1, ASR_MAX_DUP):
                continue  # collapse the (N+1)-th identical neighbour
        else:
            run_word, run_len = w, 1
        out.append(w)
    if len(out) >= 4:
        counts: dict[str, int] = {}
        for w in out:
            counts[w] = counts.get(w, 0) + 1
        hot, n = max(counts.items(), key=lambda kv: kv[1])
        if n >= 4 and n * 5 >= len(out) * 2:  # hot word is >= 40% of the utterance
            seen, kept = 0, []
            for w in out:
                if w == hot:
                    seen += 1
                    if seen > 2:
                        continue
                kept.append(w)
            out = kept
    # loops often leave an orphan single-char Devanagari fragment ("अ") at the
    # end — drop it (real standalone words are never 1 Devanagari char except न)
    while len(out) >= 2 and len(out[-1]) == 1 and out[-1] != "न" \
            and "\u0900" <= out[-1][0] <= "\u097F":
        out.pop()
    result = " ".join(out)

    # Clean colloquial fast-speech phonetic contractions common in Whisper Hindi
    result = re.sub(r"\bपूष्रा(?:ओं)?\b", "पूछ रहा हूँ", result)
    result = re.sub(r"\bपूछरा\b", "पूछ रहा", result)
    result = re.sub(r"\bआरी\s+है\b", "आ रही है", result)
    result = re.sub(r"\bआवाद\b", "आवाज़", result)
    result = re.sub(r"\bकिनी\b", "कि नहीं", result)
    result = re.sub(r"\bरुग\b", "रुको", result)
    result = re.sub(r"\bकुչ\b", "कुछ", result)
    return result


def _whisper_text(samples: np.ndarray, beam: int = 1, vad: bool = False) -> str:
    """Transcribe one utterance buffer -> trimmed text (calls serialized).

    beam>1 / vad=True are applied only by the faster-whisper backend for the
    authoritative "final"; live partial captions stay greedy/raw everywhere.
    The mlx backend has no beam decoder and ignores both.
    """
    if samples.size == 0:
        return ""
    asr = _get_asr()
    with _asr_lock:
        text = asr.transcribe(np.ascontiguousarray(samples, dtype=np.float32), beam=beam, vad=vad)
    return _collapse_repeats(text)

