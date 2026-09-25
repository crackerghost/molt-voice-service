"""Board pipeline: qwen key-quirk survival, whole-turn prompt, plan mode.

No network — generate_for_step is only exercised with a set stop event
(must return None immediately) and prompt/config pure functions.
"""

import os
import threading
import unittest
from unittest.mock import patch

from server.chat import pipeline as _pipeline  # noqa: F401 (import must not explode)
from server.config import VoiceConfig
from server.llm.diagrams import _step_prompt, generate_for_step, normalize


class KeyStripTests(unittest.TestCase):
    def test_spaced_keys_survive_normalize(self):
        # Exact shape qwen returned live: keys padded with trailing spaces.
        raw = {"elements": [
            {"id ": "w1-a", "type ": "rectangle", "text ": "head: title",
             "trigger ": "head", "x ": 40, "y ": 40},
            {"id ": "w1-b", "type ": "rectangle", "text ": "body text",
             "trigger ": "body", "x ": 40, "y ": 140},
            {"id ": "w1-a1", "type ": "arrow",
             "startNodeId ": "w1-a", "endNodeId ": "w1-b"},
        ]}
        d = normalize(raw)
        self.assertIsNotNone(d)
        types = sorted(e["type"] for e in d["elements"])
        self.assertEqual(types, ["arrow", "rectangle", "rectangle"])
        self.assertTrue(all(e.get("trigger") for e in d["elements"] if e["type"] != "arrow"))

    def test_clean_payload_still_fine(self):
        raw = {"elements": [
            {"id": "w1-a", "type": "rectangle", "text": "head", "x": 1, "y": 2},
        ]}
        d = normalize(raw)
        self.assertEqual(len(d["elements"]), 1)


class PromptTests(unittest.TestCase):
    def test_window_prompt_unchanged(self):
        msgs = _step_prompt("s" * 900, "topic", "w1")
        self.assertIn("ONE step", msgs[0]["content"])
        self.assertIn("STEP:", msgs[1]["content"])
        self.assertLessEqual(len(msgs[1]["content"]), 200 + 600 + 64)

    def test_whole_prompt_covers_full_reply(self):
        msgs = _step_prompt("s" * 2000, "topic", "t", whole=True)
        self.assertIn("6-10", msgs[0]["content"])
        self.assertIn("FULL REPLY:", msgs[1]["content"])
        self.assertNotIn("ONE step", msgs[0]["content"])
        self.assertLessEqual(len(msgs[1]["content"]), 200 + 1500 + 64)


class PlanModeTests(unittest.TestCase):
    def test_default_is_turn(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DIAGRAM_PLAN_MODE", None)
            cfg = VoiceConfig.from_env(".")
        self.assertEqual(cfg.diagram_plan_mode, "turn")

    def test_window_override_and_bad_value(self):
        with patch.dict(os.environ, {"DIAGRAM_PLAN_MODE": "window"}, clear=False):
            self.assertEqual(VoiceConfig.from_env(".").diagram_plan_mode, "window")
        with patch.dict(os.environ, {"DIAGRAM_PLAN_MODE": "bogus"}, clear=False):
            self.assertEqual(VoiceConfig.from_env(".").diagram_plan_mode, "turn")


class PlannerGuardTests(unittest.TestCase):
    def test_set_stop_event_returns_none_without_network(self):
        evt = threading.Event()
        evt.set()
        self.assertIsNone(generate_for_step(
            "key", "some teaching step about html head and body", "topic",
            evt, client=None, url="http://127.0.0.1:1/", model="m"))


if __name__ == "__main__":
    unittest.main()
