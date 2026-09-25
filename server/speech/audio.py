"""Audio byte helpers (pure, no globals)."""

from __future__ import annotations

import io

import numpy as np
import soundfile as sf


def wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()
