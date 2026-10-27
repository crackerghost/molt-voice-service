"""Quality settings must not silently under-budget OmniVoice decoding."""

import os
import unittest
from unittest.mock import patch

from server.config import VoiceConfig


class VoiceQualityConfigTests(unittest.TestCase):
    def config(self, **environment):
        with patch.dict(os.environ, {"VOICE_API_DEVICE": "cpu", **environment}, clear=True):
            return VoiceConfig.from_env("/tmp")

    def test_old_modal_secret_cannot_reduce_natural_decode_budget(self):
        cfg = self.config(VOICE_NUM_STEP="8", VOICE_FIRST_STEP="6", VOICE_TEMPERATURE="0.3")
        self.assertEqual(cfg.num_step, 16)
        self.assertEqual(cfg.first_window_step, 16)
        self.assertGreaterEqual(cfg.step_min, 16)
        self.assertEqual(cfg.tts_temperature, 0.0)

    def test_higher_quality_is_not_silently_downgraded(self):
        cfg = self.config(VOICE_NUM_STEP="32", VOICE_FIRST_STEP="24")
        self.assertEqual(cfg.num_step, 32)
        self.assertEqual(cfg.first_window_step, 24)

    def test_speed_and_window_tuning_are_preserved(self):
        cfg = self.config(VOICE_SPEED="0.95", VOICE_WINDOW_CHARS="150")
        self.assertEqual(cfg.default_speed, 0.95)
        self.assertEqual(cfg.window_char_cap, 150)

    def test_opening_window_does_not_exceed_full_decode_budget(self):
        cfg = self.config(VOICE_NUM_STEP="16", VOICE_FIRST_STEP="32")
        self.assertEqual(cfg.first_window_step, 16)

    def test_legacy_profile_remains_explicit_fast_mode(self):
        cfg = self.config(VOICE_DELIVERY_PROFILE="legacy", VOICE_NUM_STEP="6",
                          VOICE_FIRST_STEP="4", VOICE_SPEED="0.9", VOICE_TEMPERATURE="0.3")
        self.assertEqual(cfg.num_step, 6)
        self.assertEqual(cfg.first_window_step, 4)
        self.assertEqual(cfg.default_speed, 0.9)
        self.assertEqual(cfg.tts_temperature, 0.3)


if __name__ == "__main__":
    unittest.main()
