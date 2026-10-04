"""OmniVoice model loading and audio generation service."""

import io
import logging
import os
import re
import sys
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable

# --- Windows DLL hardening (fixes intermittent libtorchaudio load failure) ---
# `torch.ops.load_library("libtorchaudio.pyd")` needs torch's bundled CUDA
# DLLs visible in the DLL search path. When launched via Start-Process
# hidden / supervision loops the PATH-based lookup can fail even though an
# interactive shell works. Register torch's lib dir explicitly, before any
# torch/torchaudio import below.
if os.name == "nt":
    try:
        import importlib.util as _ilu

        _spec = _ilu.find_spec("torch")
        if _spec and _spec.origin:
            _torch_lib = os.path.join(os.path.dirname(_spec.origin), "lib")
            if os.path.isdir(_torch_lib) and hasattr(os, "add_dll_directory"):
                os.add_dll_directory(_torch_lib)
    except Exception:
        pass

import numpy as np
import soundfile as sf
import torch

try:
    import torchaudio  # noqa: F401  (import early for a clear version check)
    from torch import __version__ as _torch_v
    from torchaudio import __version__ as _ta_v

    if _torch_v.split("+")[0].split(".")[:2] != _ta_v.split("+")[0].split(".")[:2]:
        print(
            f"WARNING: torch ({_torch_v}) / torchaudio ({_ta_v}) major versions "
            "differ — libtorchaudio may fail to load. Reinstall matched builds, e.g.: "
            "uv pip install --python .\\omnivoice-env\\Scripts\\python.exe "
            "'torch==2.11.0+cu126' 'torchaudio==2.11.0+cu126' "
            "--index-url https://download.pytorch.org/whl/cu126",
            file=sys.stderr,
        )
except OSError as exc:
    raise OSError(
        "Failed to load torchaudio native library (libtorchaudio.pyd). "
        "This is usually a torch/torchaudio version mismatch or missing CUDA DLLs. "
        f"Installed torch={getattr(torch, '__version__', '?')}. "
        "Fix: uv pip install --python .\\omnivoice-env\\Scripts\\python.exe "
        "'torch==<VER>+cu126' 'torchaudio==<VER>+cu126' with MATCHING <VER>, "
        "--index-url https://download.pytorch.org/whl/cu126"
    ) from exc

from omnivoice import OmniVoice

from server.gpu import gpu_generate_lock

log = logging.getLogger("voice_api")


@dataclass(frozen=True)
class TTSConfig:
    model_name: str
    device: str
    dtype: object
    sample_rate: int
    temperature: float
    default_speed: float
    stream_max_chars: int
    first_window_step: int
    pause_seconds: dict[str, float]
    # Realtime fluency knobs (env-tunable via TTSConfig build site in app.py):
    language: str = "hi"           # OmniVoice language id — "hi" gives better Hindi token stats + duration estimate
    pad_duration: float = 0.02     # per-window edge padding; default 0.1s is dead air on EVERY streamed window
    fade_duration: float = 0.02    # edge fades; same per-window cost as pad


class TTSEngine:
    def __init__(self, config: TTSConfig, pronunciation_fix: Callable[[str], str]):
        self.config = config
        self.pronunciation_fix = pronunciation_fix
        self.generate_lock = threading.Lock()
        self.gpu_warm = {"done": False}
        self.model = None
        self.voice_prompt = None

    def load(self, ref_audio, ref_text):
        # device_map=None on CPU: transformers' CUDA-allocator warmup runs
        # for ANY non-None device_map and crashes on CPU-only torch builds.
        device_map = None if self.config.device == "cpu" else self.config.device
        self.model = OmniVoice.from_pretrained(
            self.config.model_name,
            device_map=device_map,
            dtype=self.config.dtype,
        )
        self.voice_prompt = self.model.create_voice_clone_prompt(
            ref_audio=str(ref_audio),
            ref_text=ref_text,
        )
        log.info("OmniVoice loaded + voice prompt cached from %s", ref_audio.name)
        return self.model, self.voice_prompt

    def warm(self):
        """Two-stage warm-up so production windows never pay cold-start costs.

        Stage 1 (short): JITs kernels + fills the KV path on a tiny fragment —
        same as before. Stage 2 (full production window): the diffusion
        schedule, CUDA graphs / attention paths, and the audio-tokenizer decode
        are all shape-sensitive; a "नमस्ते"-only warm leaves the FIRST real
        window ~2x slower. Both run at the production first-window step.
        """
        try:
            self.generate("नमस्ते", self.config.first_window_step, 1.0)
            self.generate(
                "आज हम एक नया विषय सीखेंगे और हर कदम को ध्यान से समझेंगे।",
                self.config.first_window_step,
                self.config.default_speed,
            )
            self.gpu_warm["done"] = True
            log.info("TTS GPU warm-up complete (2 stages)")
        except Exception as exc:
            log.warning("TTS GPU warm-up failed: %s", exc)

    def generate(self, text, num_step, speed, temperature=None):
        if self.model is None or self.voice_prompt is None:
            raise RuntimeError("TTS engine is not loaded")
        kwargs = {
            "text": self.pronunciation_fix(text),
            "voice_clone_prompt": self.voice_prompt,
            "language": self.config.language,
            "num_step": num_step,
            "pad_duration": self.config.pad_duration,
            "fade_duration": self.config.fade_duration,
        }
        if speed is not None:
            kwargs["speed"] = speed
        if temperature is not None:
            kwargs["class_temperature"] = temperature

        # TTS and the local vision model share one accelerator. Vision already
        # uses gpu_generate_lock; TTS must take the same lock or CUDA kernels
        # from both models can overlap and intermittently fail (or OOM).
        accelerator_lock = (
            gpu_generate_lock
            if self.config.device.startswith("cuda") or self.config.device == "mps"
            else nullcontext()
        )
        with self.generate_lock:
            with accelerator_lock:
                if torch.cuda.is_available() and not self.gpu_warm["done"]:
                    torch.cuda.empty_cache()
                with torch.inference_mode():
                    outputs = self.model.generate(**kwargs)
                if not outputs:
                    raise RuntimeError("OmniVoice returned no audio")
                segments = []
                for segment in outputs:
                    if hasattr(segment, "detach"):
                        segment = segment.detach()
                    if hasattr(segment, "cpu"):
                        segment = segment.cpu()
                    segments.append(np.asarray(segment, dtype=np.float32))
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        return segments[0] if len(segments) == 1 else np.concatenate(segments)

    def wav_bytes(self, samples):
        buffer = io.BytesIO()
        sf.write(buffer, samples, self.config.sample_rate, format="WAV", subtype="PCM_16")
        return buffer.getvalue()

    def insert_pauses(self, wav, text):
        """Append a natural trailing pause; never splice mid-audio.

        Old proportional splicing estimated pause positions as
        total * index/n_chars, which lands inside words (clicks, robotic
        chops) because chars are not uniform duration. The TTS model already
        renders interior commas with its own prosody when fed full clauses,
        so we only add a short trailing breath for ending punctuation.
        Unfinished windows receive no synthetic silence; their fade/pad is
        already enough to join them without creating a perceptible gap.
        """
        total = len(wav)
        if total == 0 or not text:
            return wav
        t = text.strip()
        gap = self.config.pause_seconds.get(t[-1], 0.0) if t else 0.0
        n = int(gap * self.config.sample_rate)
        if n <= 0:
            return wav
        return np.concatenate(
            [wav, np.zeros(n, dtype=wav.dtype)]
        ) if total else wav

    def stream_chunks(self, text):
        # This is a character limit, not a UTF-8 byte limit. Hindi graphemes
        # commonly use 3+ bytes, so byte-counting at 75 split ordinary clauses
        # into 20-25 character clips and forced a fresh diffusion run mid-sentence.
        limit = max(1, int(self.config.stream_max_chars))
        clauses = re.split(r"(?<=[।?!.])\s*", text)
        chunks, current = [], ""
        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue
            candidate = f"{current} {clause}".strip() if current else clause
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = ""
            if len(clause) <= limit:
                current = clause
                continue
            for word in clause.split(" "):
                word = word.strip()
                if not word:
                    continue
                candidate = (current + " " + word).strip() if current else word
                if len(candidate) <= limit:
                    current = candidate
                    continue
                if current:
                    chunks.append(current)
                # Preserve whole Hindi words and their combining vowel marks.
                # A single unusually long token may exceed the soft cap, but
                # splitting its Unicode code points would corrupt pronunciation.
                current = word
        if current:
            chunks.append(current)
        return chunks
