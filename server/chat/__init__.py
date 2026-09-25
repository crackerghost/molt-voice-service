"""Streaming chat text pipeline: speakable sentences and TTS window units.

Pure functions only — no app state, no GPU, no network. Importable and
unit-testable in isolation (see tests/test_phrases.py). The realtime
worker threads (:mod:`server.chat.pipeline`) take injected deps and build
on these primitives.
"""

from server.chat.phrases import clause_units, convert_numbers_to_hindi, speech_sentence

__all__ = ["clause_units", "convert_numbers_to_hindi", "speech_sentence"]
