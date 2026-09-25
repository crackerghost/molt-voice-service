"""Pre-generate high-quality filler utterances in the cloned voice.

Fillers mask LLM+TTS latency: the client plays one at random if the first
real audio frame hasn't arrived within ~400ms ("theek hai, ruko" effect).

Usage:
    .\\omnivoice-env\\Scripts\\python.exe scripts/generate_fillers.py
    .\\omnivoice-env\\Scripts\\python.exe scripts/generate_fillers.py --steps 32 --speed 1.15

Quality: same OmniVoice checkpoint + voice-clone prompt as production,
high diffusion steps (default 32), so fillers sound identical to replies.
Keep each text SHORT (0.6-1.3s) — long fillers add latency instead of hiding it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

# Short, neutral Hinglish/Hindi acknowledgements. No promises, no questions,
# no content — safe to play before ANY reply. All render < ~1.3s at 1.15x.
#
# Emotion tags are OmniVoice inline non-verbal controls ([laughter], [sigh],
# [surprise-oh], ...) — they render inside the cloned voice. Kept rare
# (3 of 18) so a laugh never lands on a serious question too often.
FILLER_TEXTS = [
    ("filler_01_theek_hai_ruko", "ठीक है, रुको एक सेकंड।"),
    ("filler_02_soch_raha", "हाँ, सोच रहा हूँ।"),
    ("filler_03_hmm_dekhta", "हम्म, देखता हूँ।"),
    ("filler_04_ek_second", "एक सेकंड रुको।"),
    ("filler_05_achha_ek_minute", "अच्छा, एक मिनट।"),
    ("filler_06_dekh_raha", "ठीक है, देख रहा हूँ।"),
    ("filler_07_achha_sawaal", "हम्म, अच्छा सवाल है।"),
    ("filler_08_samajh_gaya", "हाँ हाँ, समझ गया।"),
    # ---- Hinglish mix (English-Hindi code-mix, same Hindi-accent voice) ----
    ("filler_09_okay_one_minute", "ओके, वन मिनट।"),
    ("filler_10_okay_wait", "ओके, वेट।"),
    ("filler_11_just_a_second", "जस्ट अ सेकंड।"),
    ("filler_12_hold_on", "होल्ड ऑन।"),
    ("filler_13_okay_dekhta", "ओके, देखता हूँ।"),
    ("filler_14_yeah_one_second", "या या, वन सेकंड।"),
    ("filler_15_bas_ek_second", "बस एक सेकंड।"),
    # ---- emotion variants (inline non-verbal tags, cloned voice) ----
    ("filler_16_laugh_ek_second", "[laughter] एक सेकंड।"),
    ("filler_17_chuckle_haan", "हाँ हाँ [laughter]"),
    ("filler_18_sigh_soch", "हम्म [sigh] सोच रहा हूँ।"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=32, help="diffusion steps (high = best quality)")
    ap.add_argument("--speed", type=float, default=1.15)
    ap.add_argument("--out", default="assets/fillers", help="output dir relative to repo root")
    ap.add_argument("--force", action="store_true", help="regenerate even if wav exists")
    args = ap.parse_args()

    from server.config import VoiceConfig, load_dotenv
    from server.services import build_services

    load_dotenv(HERE / ".env")
    config = VoiceConfig.from_env(HERE)
    services = build_services(config)
    engine = services.tts_engine
    engine.load(config.reference_audio, config.reference_text)

    out_dir = HERE / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    import soundfile as sf

    made = 0
    for name, text in FILLER_TEXTS:
        wav_path = out_dir / f"{name}.wav"
        if wav_path.exists() and not args.force:
            print(f"skip (exists): {wav_path.name}")
            continue
        wav = engine.generate(text, args.steps, args.speed, config.tts_temperature)
        wav = engine.insert_pauses(wav, text)
        dur = wav.shape[-1] / config.sample_rate
        sf.write(str(wav_path), wav, config.sample_rate, subtype="PCM_16")
        print(f"wrote {wav_path.name} ({dur:.2f}s)", flush=True)
        made += 1
    print(f"done: {made} generated in {out_dir}")


if __name__ == "__main__":
    main()
