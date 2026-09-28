"""Regression tests for natural tutor delivery."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from server.config import VoiceConfig
from server.llm.streaming import natural_stream_cut
from server.speech.pacing import pick_speed


class TestNaturalStreaming(unittest.TestCase):
    def test_waits_for_a_natural_clause_boundary(self):
        text = (
            "यह पहला विचार थोड़ा विस्तार से और बिल्कुल साफ तरीके से समझते हैं, "
            "अब इसका अगला हिस्सा देखते हैं"
        )
        phrase, remainder = natural_stream_cut(text, 40)
        self.assertTrue(phrase.endswith(","))
        self.assertTrue(remainder.startswith("अब"))
        self.assertGreaterEqual(len(phrase), 64)

    def test_hard_fallback_still_cuts_on_a_word(self):
        text = "शिक्षक विद्यार्थियों को धीरे और साफ तरीके से पूरा विषय समझाता रहता है " * 3
        phrase, remainder = natural_stream_cut(text, 40)
        self.assertTrue(phrase)
        self.assertTrue(remainder)
        self.assertFalse(phrase.endswith(" "))
        self.assertNotEqual(phrase[-1], remainder[0])


class TestNaturalProfile(unittest.TestCase):
    def test_old_gpu_env_is_clamped_after_restart(self):
        env = {
            "VOICE_API_DEVICE": "cpu",
            "VOICE_DELIVERY_PROFILE": "natural",
            "VOICE_SPEED": "1.15",
            "VOICE_NUM_STEP": "32",
            "VOICE_EXCITED_SPEED": "1.12",
            "VOICE_DRAMATIC_SPEED": "0.92",
            "VOICE_LONG_SPEED": "0.96",
            "VOICE_FIRST_WINDOW_CHARS": "40",
            "VOICE_MIN_WINDOW_CHARS": "28",
            "VOICE_FIRST_STEP": "4",
            "VOICE_FILLER_THRESHOLD_MS": "500",
            "VOICE_FILLER_ENABLED": "1",
            "VOICE_FILLER_MODE": "slow",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = VoiceConfig.from_env(Path("."))
        self.assertEqual(cfg.default_speed, 1.08)
        self.assertEqual(cfg.num_step, 8)
        self.assertEqual(cfg.speed_excited, 1.03)
        self.assertEqual(cfg.speed_dramatic, 0.97)
        self.assertEqual(cfg.speed_long, 0.98)
        self.assertEqual(cfg.first_window_chars, 64)
        self.assertEqual(cfg.min_window_chars, 55)
        self.assertEqual(cfg.first_window_step, 5)
        self.assertEqual(cfg.filler_threshold_ms, 900)
        self.assertFalse(cfg.filler_enabled)
        self.assertEqual(cfg.filler_mode, "off")

    def test_natural_profile_allows_explicit_filler_opt_in(self):
        env = {
            "VOICE_API_DEVICE": "cpu",
            "VOICE_DELIVERY_PROFILE": "natural",
            "VOICE_FILLER_ENABLED": "1",
            "VOICE_FILLER_MODE": "slow",
            "VOICE_NATURAL_FILLER": "1",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = VoiceConfig.from_env(Path("."))
        self.assertTrue(cfg.filler_enabled)
        self.assertEqual(cfg.filler_mode, "slow")

    def test_natural_profile_caps_slow_first_window(self):
        env = {
            "VOICE_API_DEVICE": "cpu",
            "VOICE_DELIVERY_PROFILE": "natural",
            "VOICE_FIRST_STEP": "8",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = VoiceConfig.from_env(Path("."))
        self.assertEqual(cfg.first_window_step, 6)

    def test_excited_line_stays_within_natural_range(self):
        self.assertLessEqual(pick_speed("बहुत अच्छा!", 1.08, excited_mult=1.03), 1.12)


if __name__ == "__main__":
    unittest.main()
