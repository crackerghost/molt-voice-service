"""Board pipeline: qwen key-quirk survival, whole-turn prompt, plan mode.

No network — generate_for_step is only exercised with a set stop event
(must return None immediately) and prompt/config pure functions.
"""

import os
import threading
import unittest
from unittest.mock import patch

from server.chat import pipeline as _pipeline
from server.chat.pipeline import needs_turn_board_fallback
from server.config import VoiceConfig
from server.llm.diagrams import EXPLICIT_DIAGRAM_RE, _step_prompt, generate_for_step, normalize, should_generate
from server.llm.os_control import wants_desktop_move, wants_os_action


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
        self.assertIn("DECISION GATE", msgs[0]["content"])
        self.assertIn("return no tool call", msgs[0]["content"])
        self.assertNotIn("When in doubt, DRAW", msgs[0]["content"])
        self.assertIn("STEP:", msgs[1]["content"])
        self.assertLessEqual(len(msgs[1]["content"]), 200 + 600 + 64)

    def test_whole_prompt_covers_full_reply(self):
        msgs = _step_prompt("s" * 2000, "topic", "t", whole=True)
        self.assertIn("6-10", msgs[0]["content"])
        self.assertIn("FULL REPLY:", msgs[1]["content"])
        self.assertNotIn("ONE step", msgs[0]["content"])
        self.assertLessEqual(len(msgs[1]["content"]), 200 + 1500 + 64)


class PlanModeTests(unittest.TestCase):
    def test_inline_agent_falls_back_when_board_promise_was_not_kept(self):
        self.assertTrue(needs_turn_board_fallback("window", True, 0, True))
        self.assertFalse(needs_turn_board_fallback("window", True, 1, True))
        self.assertFalse(needs_turn_board_fallback("window", True, 0, False))

    def test_single_brain_board_is_default_and_legacy_zero_is_ignored(self):
        with patch.dict(os.environ, {"DIAGRAM_INLINE": "0"}, clear=False):
            os.environ.pop("DIAGRAM_SIDECAR", None)
            self.assertTrue(VoiceConfig.from_env(".").diagram_inline)

    def test_sidecar_has_explicit_emergency_opt_out(self):
        with patch.dict(os.environ, {"DIAGRAM_SIDECAR": "1"}, clear=False):
            self.assertFalse(VoiceConfig.from_env(".").diagram_inline)

    def test_default_is_window_for_live_speech_sync(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DIAGRAM_PLAN_MODE", None)
            cfg = VoiceConfig.from_env(".")
        self.assertEqual(cfg.diagram_plan_mode, "window")

    def test_turn_override_and_bad_value(self):
        with patch.dict(os.environ, {"DIAGRAM_PLAN_MODE": "turn"}, clear=False):
            self.assertEqual(VoiceConfig.from_env(".").diagram_plan_mode, "turn")
        with patch.dict(os.environ, {"DIAGRAM_PLAN_MODE": "bogus"}, clear=False):
            self.assertEqual(VoiceConfig.from_env(".").diagram_plan_mode, "window")


class PlannerGuardTests(unittest.TestCase):
    def test_set_stop_event_returns_none_without_network(self):
        evt = threading.Event()
        evt.set()
        self.assertIsNone(generate_for_step(
            "key", "some teaching step about html head and body", "topic",
            evt, client=None, url="http://127.0.0.1:1/", model="m"))


class GateTests(unittest.TestCase):
    def test_only_actual_visual_requests_force_a_board(self):
        self.assertIsNotNone(EXPLICIT_DIAGRAM_RE.search("board pe diagram bana ke samjhao"))
        self.assertIsNotNone(EXPLICIT_DIAGRAM_RE.search("draw a flowchart"))
        self.assertIsNone(EXPLICIT_DIAGRAM_RE.search("explain photosynthesis"))
        self.assertIsNone(EXPLICIT_DIAGRAM_RE.search("flexbox samjhao"))

    def test_teaching_turns_get_board(self):
        with patch.dict(os.environ, {"DIAGRAM_GATE": "auto"}, clear=False):
            for t in ("HTML सिखाओ", "पेंटिंग बनाना सिखाओ",
                      "React lesson shuru karo", "flexbox samjhao"):
                self.assertTrue(should_generate(t, [], True), t)
        for t in ("HTML सिखाओ", "पेंटिंग बनाना सिखाओ",
                  "React lesson shuru karo", "flexbox samjhao"):
            self.assertFalse(wants_desktop_move(t), t)

    def test_desktop_moves_suppress_board(self):
        for t in ("नोट्स खोलो", "browser kholo aur youtube dikhao"):
            self.assertTrue(wants_desktop_move(t), t)
            self.assertFalse(should_generate(t, [], True), t)

    def test_explicit_draw_wins_over_desktop_words(self):
        # ASR emits Devanagari: बोर्ड पर दिखाओ carries दिखाओ intent and must
        # draw even though "board" is a desktop word.
        self.assertTrue(should_generate("बोर्ड पर दिखाओ", [], True))
        self.assertTrue(should_generate("draw a diagram of computer", [], True))

    def test_greetings_and_smalltalk_still_skipped(self):
        for t in ("hii", "namaste", "heasds"):
            self.assertFalse(should_generate(t, [], True), t)

    def test_blocking_fast_path_unchanged_for_lessons(self):
        # Lessons still reach the OS director (may open code/browser);
        # only the diagram suppression narrowed.
        self.assertTrue(wants_os_action("React lesson shuru karo"))
        self.assertTrue(wants_os_action("नोट्स खोलो"))


if __name__ == "__main__":
    unittest.main()
