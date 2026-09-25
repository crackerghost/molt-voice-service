"""Cheap smart filler pick: parsing, prompt building, and safe fallback.

No network, no models, no API keys — pick_name is only exercised against
a refused localhost port and empty inputs (must return None, never raise).
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.config import VoiceConfig
from server.speech.filler_pick import build_messages, parse_pick, pick_name
from server.speech.fillers import FillerStore

NAMES = [
    "filler_01_theek_hai_ruko",
    "filler_07_achha_sawaal",
    "filler_12_hold_on",
]


class ParsePickTests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(parse_pick("filler_07_achha_sawaal", NAMES), "filler_07_achha_sawaal")

    def test_case_and_quotes_tolerated(self):
        self.assertEqual(parse_pick('  "Filler_12_Hold_On"  ', NAMES), "filler_12_hold_on")

    def test_embedded_in_chatter(self):
        self.assertEqual(
            parse_pick("I think filler_01_theek_hai_ruko fits", NAMES),
            "filler_01_theek_hai_ruko",
        )

    def test_bare_number_maps_to_prefix(self):
        self.assertEqual(parse_pick("12", NAMES), "filler_12_hold_on")
        self.assertEqual(parse_pick("7", NAMES), "filler_07_achha_sawaal")

    def test_garbage_and_empty_give_none(self):
        self.assertIsNone(parse_pick("hello world", NAMES))
        self.assertIsNone(parse_pick("", NAMES))
        self.assertIsNone(parse_pick("filler_07_achha_sawaal", []))


class PromptTests(unittest.TestCase):
    def test_prompt_lists_clips_and_user_text(self):
        msgs = build_messages("mera code me error hai", NAMES)
        self.assertEqual(len(msgs), 2)
        blob = msgs[1]["content"]
        for n in NAMES:
            self.assertIn(n, blob)
        self.assertIn("mera code me error hai", blob)
        self.assertTrue(len(blob) < 2000)  # tiny by design (~100 prompt tokens)


class PickFallbackTests(unittest.TestCase):
    def test_empty_key_or_clips_never_calls_network(self):
        self.assertIsNone(pick_name("hi", [], key="x", url="http://127.0.0.1:1/", model="m"))
        self.assertIsNone(pick_name("hi", NAMES, key="", url="http://127.0.0.1:1/", model="m"))
        self.assertIsNone(pick_name("  ", NAMES, key="x", url="http://127.0.0.1:1/", model="m"))

    def test_refused_port_returns_none(self):
        self.assertIsNone(
            pick_name("hi", NAMES, key="x", url="http://127.0.0.1:1/", model="m", timeout_s=1.0)
        )


class StoreSmartTests(unittest.TestCase):
    def _store(self, n=3):
        tmp = tempfile.mkdtemp()
        for i in range(n):
            Path(tmp, f"filler_{i:02d}_x.wav").write_bytes(b"RIFF" + bytes(100))
        return FillerStore(Path(tmp))

    def test_names_lists_clips(self):
        store = self._store(3)
        self.assertEqual(len(store.names()), 3)

    def test_mark_played_avoids_immediate_replay(self):
        store = self._store(3)
        clip = store.get(store.names()[0])
        store.mark_played(clip)
        # played clip is dropped from the current bag when present
        self.assertNotIn(0, store._bag)
        self.assertEqual(store._last, 0)


class ConfigTests(unittest.TestCase):
    def test_filler_pick_knobs_from_env(self):
        env = {
            "VOICE_FILLER_PICK": "0",
            "VOICE_FILLER_PICK_MODEL": "qwen/qwen3.8-27b",
            "VOICE_FILLER_PICK_TIMEOUT_S": "0.25",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = VoiceConfig.from_env(".")
        self.assertFalse(cfg.filler_pick_enabled)
        self.assertEqual(cfg.filler_pick_model, "qwen/qwen3.8-27b")
        self.assertAlmostEqual(cfg.filler_pick_timeout_s, 0.25)

    def test_defaults_enable_smart_pick(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOICE_FILLER_PICK", None)
            os.environ.pop("VOICE_FILLER_PICK_MODEL", None)
            os.environ.pop("VOICE_FILLER_PICK_TIMEOUT_S", None)
            cfg = VoiceConfig.from_env(".")
        self.assertTrue(cfg.filler_pick_enabled)
        self.assertTrue(cfg.filler_pick_model)
        self.assertGreater(cfg.filler_pick_timeout_s, 0)


if __name__ == "__main__":
    unittest.main()
