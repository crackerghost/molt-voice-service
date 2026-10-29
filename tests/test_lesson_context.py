import unittest
from server.llm.lesson_context import apply_lesson_context


class LessonContextTest(unittest.TestCase):
    def test_dedicated_record_is_pinned_to_system_prompt(self):
        messages = [{"role": "system", "content": "Tutor persona"}, {"role": "user", "content": "I did not understand the last question"}]
        apply_lesson_context(messages, '{"lastCheckpoint":{"question":"What is DNS?"}}', [])
        self.assertIn("Tutor persona", messages[0]["content"])
        self.assertIn("What is DNS?", messages[0]["content"])
        self.assertIn("last question", messages[0]["content"])
        self.assertIn("without revealing its answer", messages[0]["content"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1]["role"], "user")

    def test_legacy_boolean_context_is_supported(self):
        messages = [{"role": "system", "content": "Tutor"}]
        apply_lesson_context(messages, True, [{"role": "assistant", "content": "[LIVE LESSON CONTEXT] DNS maps names"}])
        self.assertIn("DNS maps names", messages[0]["content"])

    def test_empty_context_leaves_persona_unchanged(self):
        for raw in [None, False, {}, ""]:
            messages = [{"role": "system", "content": "Tutor"}]
            apply_lesson_context(messages, raw, [])
            self.assertEqual(messages[0]["content"], "Tutor")

    def test_record_is_bounded(self):
        messages = [{"role": "system", "content": "Tutor"}]
        apply_lesson_context(messages, "a" * 30000, [])
        self.assertLess(len(messages[0]["content"]), 20000)
