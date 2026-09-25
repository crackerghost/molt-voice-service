"""Speakable-sentence pipeline for streamed LLM replies.

Moved verbatim out of server/app.py (Phase 1 of the god-file split):
- :func:`speech_sentence` — one streamed phrase -> TTS-ready text.
- :func:`clause_units` — sentence -> hard-capped TTS window pieces.
- :func:`convert_numbers_to_hindi` — ASCII digits -> spoken Hindi words.

Only dependency is :mod:`server.speech.normalization` (pure). The TTS
window cap travels as an explicit argument so this module never reads app
config — the caller owns tuning (``VOICE_WINDOW_CHARS``).
"""

import re

from server.speech.normalization import (
    _devanagari_only,
    _naturalize,
    _preserve_code_tokens,
    _speechify,
)

_HINDI_NUMS = {
    0: "शून्य", 1: "एक", 2: "दो", 3: "तीन", 4: "चार", 5: "पांच", 6: "छह", 7: "सात", 8: "आठ", 9: "नौ",
    10: "दस", 11: "ग्यारह", 12: "बारह", 13: "तेरह", 14: "चौदह", 15: "पंद्रह", 16: "सोलह", 17: "सत्रह",
    18: "अठारह", 19: "उन्नीस", 20: "बीस", 21: "इक्कीस", 22: "बाईस", 23: "तेईस", 24: "चौबीस", 25: "पच्चीस",
    26: "छब्बीस", 27: "सत्ताईस", 28: "अट्ठाइस", 29: "उनतीस", 30: "तीस", 31: "इकत्तीस", 32: "बत्तीस",
    33: "तैंतीस", 34: "चौंतीस", 35: "पैंतीस", 36: "छत्तीस", 37: "सैंतीस", 38: "अड़तीस", 39: "उनतालीस",
    40: "चालीस", 50: "पचास", 60: "साठ", 70: "सत्तर", 80: "अस्सी", 90: "नब्बे", 100: "सौ",
}


def convert_numbers_to_hindi(text: str) -> str:
    """Convert numeric digits to spoken Hindi words so OmniVoice never fails on ASCII numbers."""
    def _repl(m: re.Match) -> str:
        s = m.group(0)
        try:
            val = int(s)
            if val in _HINDI_NUMS:
                return _HINDI_NUMS[val]
            if val < 100:
                tens = (val // 10) * 10
                ones = val % 10
                return f"{_HINDI_NUMS.get(tens, '')} {_HINDI_NUMS.get(ones, '')}".strip()
            # Multi-digit numbers (like 404, 2024): pronounce digit-by-digit
            return " ".join(_HINDI_NUMS.get(int(d), d) for d in s)
        except Exception:
            return s

    # Skip digits glued to Latin letters (h1, html5) — _devanagari_only
    # speaks those as एच वन, एचटीएमएल फाइव. Standalone numbers convert here.
    return re.sub(r"(?<![A-Za-z])\d+", _repl, text)


def speech_sentence(sent: str, complete: bool = True) -> str:
    """Make one streamed phrase speakable (strip markup, convert numbers, Devanagari accent).

    complete=False leaves off the terminal danda/full-stop so a phrase that was
    flushed early (mid-sentence) doesn't get an artificial full stop.
    """
    sent = _preserve_code_tokens(sent)
    sent = _speechify(sent)
    sent = _naturalize(sent)
    sent = convert_numbers_to_hindi(sent)
    sent = _devanagari_only(sent)
    if not sent:
        return ""
    if complete and sent[-1] not in "।?!.":
        sent += "।" if any('ऀ' <= ch <= 'ॿ' for ch in sent) else "."
    return sent


def clause_units(sent: str, piece_max: int = 110) -> list[str]:
    """Split text into TTS-window-sized pieces (hard cap, word boundaries).

    Sentence enders (। ? ! . newline) are HARD boundaries — a piece never
    spans across one, so a danda-terminated sentence is always spoken as one
    intonation arc and never glued to the next sentence's opening words.
    Within one sentence, cuts land at clause punctuation first, then at
    spaces; short sentences pass through untouched.

    Tiny tails (<30 chars, e.g. "आदि।") merge into the previous piece so
    they never become a solo TTS generate with a prosody restart.

    Every returned piece is <= piece_max chars, so no single audio window can
    grow into a long uninterruptible frame (the #1 thing that kills the
    realtime feel — one giant run-on sentence used to stall TTS for 10s+).
    """
    # Cut at sentence enders FIRST — each sentence is spoken separately.
    sentences = [s.strip() for s in re.split(r"(?<=[।?!.\\n])\s*", sent) if s.strip()]
    if not sentences:
        return []
    out: list[str] = []
    for sentence in sentences:
        if len(sentence) <= piece_max:
            out.append(sentence)
            continue
        # first cut at clause punctuation so seams sit at natural pauses
        seps = [m.start() for m in re.finditer(r"[,;—–]", sentence)]
        if seps:
            last = 0
            for p in seps:
                if p - last > piece_max:
                    out.append(sentence[last : p + 1].strip())
                    last = p + 1
            tail = sentence[last:].strip()
            if tail:
                # Merge fragments shorter than a clause into the previous
                # piece instead of a solo robotic window.
                if len(tail) < 30 and out and len(out[-1]) + 1 + len(tail) <= piece_max + 30:
                    out[-1] = f"{out[-1]} {tail}".strip()
                else:
                    out.append(tail)
        else:
            out.append(sentence)
    # then hard-split anything still too long at word boundaries
    final: list[str] = []
    for u in out:
        if len(u) <= piece_max:
            final.append(u)
            continue
        words = u.split(" ")
        cur = ""
        for w in words:
            cand = ((cur + " " + w) if cur else w).strip()
            if len(cand) <= piece_max:
                cur = cand
                continue
            if cur:
                final.append(cur)
                cur = w
        if cur:
            # Avoid a dangling 1-2 word tail as its own window.
            if len(cur) < 30 and final and len(final[-1]) + 1 + len(cur) <= piece_max + 30:
                final[-1] = f"{final[-1]} {cur}".strip()
            else:
                final.append(cur)
    return [p for p in final if p]
