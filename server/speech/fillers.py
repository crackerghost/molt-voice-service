"""Pre-generated filler-audio store (latency maskers).

Fillers are short cloned-voice wavs (assets/fillers/*.wav) played by the
client when the first real TTS frame hasn't arrived within
``VOICE_FILLER_THRESHOLD_MS`` (default 400ms). Server picks at random with
a shuffle-bag so the same filler never plays twice in a row.
"""

from __future__ import annotations

import logging
import random
import threading
from pathlib import Path

log = logging.getLogger("voice_api")


class FillerStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self._clips: list[dict] = []  # {name, path, bytes, duration_s}
        self._bag: list[int] = []  # shuffle-bag of indices (no repeat until exhausted)
        self._lock = threading.Lock()
        self.reload()

    def reload(self) -> int:
        clips = []
        if self.directory.exists():
            for wav in sorted(self.directory.glob("*.wav")):
                try:
                    data = wav.read_bytes()
                    # 24kHz mono PCM16 WAV: duration ≈ (len-44)/2/24000; parse properly when possible
                    duration = self._wav_seconds(wav)
                    clips.append({"name": wav.stem, "path": wav, "bytes": data, "duration_s": duration})
                except Exception as exc:  # noqa: BLE001 — one bad file must not kill the store
                    log.warning("Filler skip %s: %s", wav.name, exc)
        with self._lock:
            self._clips = clips
            self._bag = []
        log.info("Filler store: %d clip(s) in %s", len(clips), self.directory)
        return len(clips)

    @staticmethod
    def _wav_seconds(path: Path) -> float:
        try:
            import soundfile as sf

            info = sf.info(str(path))
            return round(info.frames / info.samplerate, 2) if info.samplerate else 0.0
        except Exception:
            return 0.0

    def __len__(self) -> int:
        return len(self._clips)

    def listing(self) -> list[dict]:
        return [
            {"name": c["name"], "url": f"/api/filler/file/{c['name']}", "duration_s": c["duration_s"]}
            for c in self._clips
        ]

    def pick_random(self) -> dict | None:
        """Shuffle-bag pick: every clip plays once before any repeats, and the
        same clip never plays twice in a row (even across bag refills)."""
        with self._lock:
            if not self._clips:
                return None
            if len(self._clips) == 1:
                return self._clips[0]
            if not self._bag:
                self._bag = list(range(len(self._clips)))
                random.shuffle(self._bag)
                # avoid boundary repeat: first of new bag != last played
                if hasattr(self, "_last") and self._bag and self._bag[-1] == getattr(self, "_last", -1):
                    if len(self._bag) > 1:
                        self._bag[0], self._bag[-1] = self._bag[-1], self._bag[0]
            idx = self._bag.pop()
            self._last = idx
            return self._clips[idx]

    def get(self, name: str) -> dict | None:
        for c in self._clips:
            if c["name"] == name:
                return c
        return None

    def names(self) -> list[str]:
        return [c["name"] for c in self._clips]

    def mark_played(self, clip: dict) -> None:
        """Record a smart-picked clip as played so the shuffle-bag won't
        replay it immediately and boundary-repeat logic still holds."""
        with self._lock:
            for i, c in enumerate(self._clips):
                if c["name"] == clip["name"]:
                    self._last = i
                    try:
                        self._bag.remove(i)
                    except ValueError:
                        pass
                    break
