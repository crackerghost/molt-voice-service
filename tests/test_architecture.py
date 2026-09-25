import os
import unittest
from pathlib import Path
from unittest.mock import patch

from server.runtime import Readiness, VoiceRuntime
from server.settings import Settings
from server.llm.diagrams import normalize, should_generate


class ArchitectureTests(unittest.TestCase):
    def test_readiness_requires_tts_and_provider(self):
        readiness = Readiness(tts=True, provider=False)
        self.assertFalse(readiness.ready)
        readiness.provider = True
        self.assertTrue(readiness.ready)

    def test_runtime_owns_provider_clients(self):
        runtime = VoiceRuntime(llm_timeout=10, vision_timeout=10)
        self.assertIsNotNone(runtime.provider_clients)
        self.assertFalse(runtime.readiness.ready)

    def test_settings_resolve_reference_audio_relative_to_root(self):
        root = Path("/workspace/Voice_Cloning")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOICE_REF_AUDIO", None)
            settings = Settings.from_environment(root)
        self.assertEqual(settings.reference_audio, root / "my_voice.wav")

    def test_diagram_intent_and_normalization_are_bounded(self):
        self.assertTrue(should_generate("draw a flowchart", [], True))
        diagram = normalize({
            "elements": [
                {"id": "node", "type": "rectangle", "x": 0, "y": 0, "text": "x"},
                {"id": "edge", "type": "arrow", "x": 0, "y": 0, "startNodeId": "node", "endNodeId": "missing"},
            ]
        })
        self.assertEqual([item["id"] for item in diagram["elements"]], ["node"])

    def test_table_and_quiz_normalization_are_bounded(self):
        diagram = normalize({
            "elements": [
                {"id": "t1", "type": "table", "text": "Var vs Let",
                 "headers": ["a", "b", "c", "d", "e"],
                 "rows": [["1"], "not-a-row", [], ["1", "2", "3", "4", "5", "6"]]},
                {"id": "q1", "type": "quiz", "text": "Which tag is biggest?",
                 "options": ["h1", "h6", "", "h1"],
                 "answer": 7, "explanation": "h1 is the largest heading."},
                {"id": "q2", "type": "quiz", "text": "Reflect on this."},
                {"id": "bad", "type": "mermaid", "text": "x"},
            ]
        })
        by_id = {item["id"]: item for item in diagram["elements"]}
        self.assertNotIn("bad", by_id)  # unknown types still dropped
        table = by_id["t1"]
        self.assertLessEqual(len(table["headers"]), 4)
        self.assertLessEqual(len(table["rows"]), 6)
        self.assertTrue(all(len(r) == len(table["headers"]) for r in table["rows"]))
        quiz = by_id["q1"]
        self.assertLessEqual(len(quiz["options"]), 4)
        self.assertIsNone(quiz["answer"])  # out-of-range -> reflection mode
        self.assertIn("explanation", quiz)
        self.assertNotIn("q2", by_id)  # quiz without options is dropped


if __name__ == "__main__":
    unittest.main()
