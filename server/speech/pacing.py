"""Expressive pacing + greeting helpers (pure functions, config-injected).

OmniVoice v1 has no emotion control, so delivery "life" comes from text
energy + per-sentence speed variation. All tunables travel explicitly —
this module never reads ``os.environ`` or app globals.
"""

from __future__ import annotations

import re


GREETING_RE = re.compile(
    r"^(नमस्ते|हेलो|हाय|हैलो|नमस्कार|कैसे\s+हो|क्या\s+हाल|क्या\s+चल|हाय\s+|तुम\s+कौन|तुम्हारा\s+नाम|तुम्हारे\s+बारे|क्या\s+कर\s+सकते|क्या\s+कर\s+सकता|क्या\s+कर\s+सकती|hello|hi|hey|good\s+(morning|afternoon|evening|night)|how\s+are\s+you|who\s+are\s+you|what\s+can\s+you\s+do)",
    re.IGNORECASE,
)

_EXCITED_RE = re.compile(r"[!]{1,}|(?:वाह|अरे|ओहो|कमाल|हा\s*हा)")
_DRAMATIC_RE = re.compile(r"\.\.\.|…")


def short_greeting(reply: str, max_sentences: int = 2) -> str:
    """Cut a greeting reply to the first few sentences (no rambling)."""
    if max_sentences <= 1:
        return reply
    stops = ["?", "!", "।", "."]
    positions = sorted(p for s in stops if s in reply for p in [reply.find(s)] if p >= 0)
    if not positions:
        return reply
    last = positions[min(max_sentences - 1, len(positions) - 1)]
    return reply[: last + 1].strip()


def pick_speed(
    sent: str,
    base: float = 1.2,
    *,
    excited_mult: float = 1.12,
    dramatic_mult: float = 0.92,
    long_mult: float = 0.96,
    long_chars: int = 110,
    speed_min: float = 0.3,
    speed_max: float = 2.0,
) -> float:
    """Per-sentence pace: excited lines speed up, thoughtful ones slow down."""
    s = float(base)
    if _EXCITED_RE.search(sent):
        s *= excited_mult
    if _DRAMATIC_RE.search(sent):
        s *= dramatic_mult
    if len(sent) > long_chars:
        s *= long_mult
    return max(speed_min, min(speed_max, round(s, 3)))
