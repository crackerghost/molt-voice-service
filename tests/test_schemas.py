"""Tests for input validation schemas."""

import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from server.schemas import make_schemas
from server.config import VoiceConfig


TTSRequest, ChatMsg, ChatRequest, VisionRequest = make_schemas(
    default_speed=1.0,
    step_min=4,
    step_max=64,
    default_step=8,
)


class TestTTSRequestValidation(unittest.TestCase):
    """Test TTS request input validation."""

    def test_valid_request(self):
        req = TTSRequest(text="नमस्ते")
        self.assertEqual(req.text, "नमस्ते")
        self.assertEqual(req.speed, 1.0)
        self.assertEqual(req.nfe_step, 8)

    def test_empty_text_rejected(self):
        with self.assertRaises(ValidationError):
            TTSRequest(text="")

    def test_text_too_long_rejected(self):
        with self.assertRaises(ValidationError):
            TTSRequest(text="a" * 2001)

    def test_speed_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            TTSRequest(text="नमस्ते", speed=3.0)

    def test_nfe_step_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            TTSRequest(text="नमस्ते", nfe_step=100)

    def test_nstep_alias_works(self):
        req = TTSRequest(text="नमस्ते", nstep=16)
        self.assertEqual(req.nfe_step, 16)

    def test_natural_profile_rejects_legacy_low_step_http_requests(self):
        with patch.dict(os.environ, {"VOICE_API_DEVICE": "cpu", "VOICE_NUM_STEP": "8"}, clear=True):
            cfg = VoiceConfig.from_env("/tmp")
        QualityTTS, *_ = make_schemas(
            default_speed=cfg.default_speed, step_min=cfg.step_min,
            step_max=cfg.step_max, default_step=cfg.num_step,
        )
        self.assertEqual(QualityTTS(text="नमस्ते").nfe_step, 16)
        with self.assertRaises(ValidationError):
            QualityTTS(text="नमस्ते", nfe_step=8)


class TestChatRequestValidation(unittest.TestCase):
    """Test chat request input validation."""

    def test_valid_request(self):
        req = ChatRequest(messages=[ChatMsg(role="user", content="नमस्ते")])
        self.assertEqual(len(req.messages), 1)

    def test_empty_messages_rejected(self):
        with self.assertRaises(ValidationError):
            ChatRequest(messages=[])

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValidationError):
            ChatRequest(messages=[ChatMsg(role="system", content="test")])

    def test_message_content_too_long_rejected(self):
        with self.assertRaises(ValidationError):
            ChatRequest(messages=[ChatMsg(role="user", content="a" * 5001)])

    def test_too_many_messages_rejected(self):
        with self.assertRaises(ValidationError):
            ChatRequest(messages=[ChatMsg(role="user", content="hi")] * 51)


class TestVisionRequestValidation(unittest.TestCase):
    """Test vision request input validation."""

    def test_valid_request(self):
        req = VisionRequest(image="a" * 100)
        self.assertEqual(len(req.image), 100)

    def test_image_too_short_rejected(self):
        with self.assertRaises(ValidationError):
            VisionRequest(image="short")

    def test_image_too_long_rejected(self):
        with self.assertRaises(ValidationError):
            VisionRequest(image="a" * 10_000_001)


if __name__ == "__main__":
    unittest.main()
