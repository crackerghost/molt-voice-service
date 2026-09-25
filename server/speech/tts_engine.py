"""OmniVoice model loading and audio generation service."""

import io
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice

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
        self.model = OmniVoice.from_pretrained(
            self.config.model_name,
            device_map=self.config.device,
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
        if torch.cuda.is_available() and not self.gpu_warm["done"]:
            torch.cuda.empty_cache()
        with self.generate_lock:
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
        so we only add: trailing breath for ending punctuation + small
        inter-window gap so back-to-back windows don't start instantly.
        """
        total = len(wav)
        if total == 0 or not text:
            return wav
        t = text.strip()
        gap = 0.08  # inter-window gap so next window never starts instantly
        if t:
            pause = self.config.pause_seconds.get(t[-1])
            if pause is not None:
                gap = max(pause, gap)
        n = int(gap * self.config.sample_rate)
        if n <= 0:
            return wav
        return np.concatenate(
            [wav, np.zeros(n, dtype=wav.dtype)]
        ) if total else wav

    def stream_chunks(self, text):
        clauses = re.split(r"(?<=[।?!.])\s*", text)
        chunks, current = [], ""
        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue
            if len((current + clause).encode("utf-8")) <= self.config.stream_max_chars:
                current += clause
                continue
            if current:
                chunks.append(current)
                current = ""
            for word in clause.split(" "):
                word = word.strip()
                if not word:
                    continue
                candidate = (current + " " + word).strip() if current else word
                if len(candidate.encode("utf-8")) <= self.config.stream_max_chars:
                    current = candidate
                    continue
                if current:
                    chunks.append(current)
                    current = ""
                buffer = ""
                for char in word:
                    if len((buffer + char).encode("utf-8")) <= self.config.stream_max_chars:
                        buffer += char
                    else:
                        chunks.append(buffer)
                        buffer = char
                current = buffer
        if current:
            chunks.append(current)
        return chunks
