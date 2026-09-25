"""Tests for server/chat/phrases.py — the extracted speech-text pipeline."""

import unittest

from server.chat.phrases import (
    clause_units,
    convert_numbers_to_hindi,
    speech_sentence,
)


class TestSpeechSentence(unittest.TestCase):
    def test_complete_adds_danda_for_hindi(self):
        self.assertTrue(speech_sentence("नमस्ते दुनिया").endswith("।"))

    def test_incomplete_adds_no_terminal_mark(self):
        self.assertFalse(speech_sentence("नमस्ते", complete=False).endswith("।"))

    def test_empty_stays_empty(self):
        self.assertEqual(speech_sentence("   "), "")

    def test_code_terms_speak_naturally(self):
        out = speech_sentence("let const document.getElementById")
        self.assertIn("लेट", out)
        self.assertIn("डॉक्यूमेंट", out)
        self.assertNotIn("एल ई टी", out)

    def test_numbers_convert(self):
        out = speech_sentence("error 404 mila")
        self.assertIn("चार", out)


class TestClauseUnits(unittest.TestCase):
    def test_danda_is_hard_boundary(self):
        pieces = clause_units(
            "मैं बस तुम्हारे सवालों का जवाब देने के लिए तैयार हूँ। कुछ बात करनी हो तो बताओ!",
            piece_max=120,
        )
        self.assertEqual(len(pieces), 2)
        self.assertTrue(pieces[0].endswith("।"))

    def test_empty_returns_empty(self):
        self.assertEqual(clause_units("   "), [])

    def test_respects_piece_max(self):
        text = "बहुत लंबा वाक्य है यह " * 30
        for piece in clause_units(text, piece_max=60):
            self.assertLessEqual(len(piece), 60)

    def test_default_cap_matches_production(self):
        # Production _PIECE_MAX = max(40, min(120, WINDOW_CHAR_CAP=110)).
        text = "शब्द " * 200
        for piece in clause_units(text):
            self.assertLessEqual(len(piece), 110)


class TestConvertNumbers(unittest.TestCase):
    def test_known_number(self):
        self.assertEqual(convert_numbers_to_hindi("5"), "पांच")

    def test_glued_to_latin_left_alone(self):
        # h1 is spoken by _devanagari_only as एच वन — not here.
        self.assertEqual(convert_numbers_to_hindi("h1"), "h1")


if __name__ == "__main__":
    unittest.main()
