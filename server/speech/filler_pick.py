"""Cheap parallel filler picker: a tiny Groq call (~100ms) chooses which
pre-generated filler clip fits this turn. Never blocks voice — the caller
fires it in parallel with the main LLM turn and falls back to random on
timeout/failure.

Measured (Sep 2026, live): ``qwen/qwen3.8-27b`` answers a pick prompt in
~104ms wall (48ms queue + 6ms inference). ``openai/gpt-oss-120b`` takes
~500ms — too slow for a serial call, which is why this stays parallel.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("voice_api")

# Short gloss per clip so the picker can match intent -> clip.
# Keys mirror scripts/generate_fillers.py names.
FILLER_GLOSS = {
    "filler_01_theek_hai_ruko": "neutral hold-on",
    "filler_02_soch_raha": "thinking",
    "filler_03_hmm_dekhta": "looking at screen/code",
    "filler_04_ek_second": "neutral one-second",
    "filler_05_achha_ek_minute": "neutral one-minute",
    "filler_06_dekh_raha": "looking at screen/code",
    "filler_07_achha_sawaal": "good question",
    "filler_08_samajh_gaya": "got it / acknowledged",
    "filler_09_okay_one_minute": "neutral hinglish one-minute",
    "filler_10_okay_wait": "neutral hinglish wait",
    "filler_11_just_a_second": "neutral hinglish one-second",
    "filler_12_hold_on": "neutral hinglish hold-on",
    "filler_13_okay_dekhta": "hinglish looking at screen/code",
    "filler_14_yeah_one_second": "hinglish acknowledged",
    "filler_15_bas_ek_second": "neutral short one-second",
    "filler_16_laugh_ek_second": "light laugh, casual only",
    "filler_17_chuckle_haan": "warm chuckle, greeting/casual only",
    "filler_18_sigh_soch": "thoughtful, hard question",
}

PICK_SYSTEM = (
    "You pick a filler sound for a voice tutor. The user just spoke and the "
    "real answer needs a moment. Reply with ONLY the exact clip name that "
    "fits best (e.g. filler_07_achha_sawaal). No other text, no quotes."
)


def build_messages(text: str, clip_names: list[str]) -> list[dict]:
    """Prompt listing available clips + the user turn. Kept tiny on purpose
    (~100 prompt tokens -> ~3ms prompt_time on Groq)."""
    lines = []
    for n in clip_names:
        gloss = FILLER_GLOSS.get(n, "")
        lines.append(f"- {n}" + (f": {gloss}" if gloss else ""))
    user = "Clips:\n" + "\n".join(lines) + f"\n\nUser said: {text[:200]}\nBest clip name:"
    return [
        {"role": "system", "content": PICK_SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_pick(raw: str, clip_names: list[str]) -> str | None:
    """Extract a valid clip name from a model reply. Accepts exact names
    (case-insensitive, stray quotes/whitespace tolerated) and bare numbers
    (``12`` -> the clip numbered 12, e.g. filler_12_hold_on)."""
    if not raw or not clip_names:
        return None
    lookup = {n.lower(): n for n in clip_names}
    cleaned = raw.strip().strip("\"'").strip().lower()
    if cleaned in lookup:
        return lookup[cleaned]
    # first exact-name substring hit (model added a word or two anyway)
    for low, orig in lookup.items():
        if low in cleaned:
            return orig
    # bare number -> filler_NN_* prefix match
    m = re.search(r"\b(\d{1,2})\b", cleaned)
    if m:
        num = f"{int(m.group(1)):02d}"
        for orig in clip_names:
            if f"_{num}_" in orig or orig.endswith(f"_{num}"):
                return orig
    return None


def pick_name(
    text: str,
    clip_names: list[str],
    *,
    key: str,
    url: str,
    model: str,
    timeout_s: float = 2.0,
) -> str | None:
    """One cheap Groq call returning the chosen clip name, or None on any
    failure (auth, network, timeout, garbage reply). Sync — run in executor."""
    if not key or not clip_names or not text.strip():
        return None
    try:
        import httpx

        resp = httpx.Client(timeout=timeout_s, follow_redirects=True).post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": build_messages(text, clip_names),
                "temperature": 0,
                "max_tokens": 10,
                "stream": False,
            },
        )
        if resp.status_code != 200:
            log.info("filler pick %s -> HTTP %d", model, resp.status_code)
            return None
        content = (resp.json()["choices"][0]["message"].get("content") or "")
        name = parse_pick(content, clip_names)
        if name:
            log.info("filler smart pick: %r for %.40s...", name, text)
        return name
    except Exception as exc:  # noqa: BLE001 — best-effort, caller falls back to random
        log.info("filler smart pick skipped (%s: %s)", type(exc).__name__, exc)
        return None
