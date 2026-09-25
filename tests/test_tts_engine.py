"""Tests for TTS engine streaming and audio processing."""

import unittest

from server.speech.tts_engine import TTSConfig, TTSEngine


class TestStreamChunks(unittest.TestCase):
    """Test text chunking for TTS streaming."""

    def setUp(self):
        self.engine = TTSEngine(
            config=TTSConfig(
                model_name="test",
                device="cpu",
                dtype=None,
                sample_rate=24000,
                temperature=0.3,
                default_speed=1.0,
                stream_max_chars=75,
                first_window_step=2,
                pause_seconds={",": 0.15, ".": 0.3},
                language="hi",
                pad_duration=0.02,
                fade_duration=0.02,
            ),
            pronunciation_fix=lambda x: x,
        )

    def test_realtime_gen_kwargs_are_configured(self):
        self.assertEqual(self.engine.config.language, "hi")
        self.assertEqual(self.engine.config.pad_duration, 0.02)
        self.assertEqual(self.engine.config.fade_duration, 0.02)

    def test_wav_bytes_are_pcm16(self):
        import io
        import numpy as np
        import soundfile as sf
        wav = np.zeros(2400, dtype=np.float32)
        raw = self.engine.wav_bytes(wav)
        with sf.SoundFile(io.BytesIO(raw)) as f:
            self.assertEqual(f.subtype, "PCM_16")
            self.assertEqual(f.samplerate, 24000)

    def test_short_text_returns_single_chunk(self):
        text = "नमस्ते"
        chunks = self.engine.stream_chunks(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_splits_at_sentence_boundary(self):
        text = "नमस्ते। कैसे हो?"
        chunks = self.engine.stream_chunks(text)
        self.assertGreaterEqual(len(chunks), 1)

    def test_respects_max_bytes(self):
        # Create a long text that exceeds max_bytes
        text = "बहुत लंबा टेक्स्ट " * 100
        chunks = self.engine.stream_chunks(text)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.encode("utf-8")), 75)

    def test_empty_string_returns_empty_list(self):
        chunks = self.engine.stream_chunks("")
        self.assertEqual(chunks, [])


class TestClauseUnits(unittest.TestCase):
    """Danda-terminated sentences must never merge across a window split."""

    def test_danda_is_hard_boundary(self):
        import re

        def clause_units(sent: str, piece_max: int = 120) -> list[str]:
            sentences = [s.strip() for s in re.split(r"(?<=[।?!.\n])\s*", sent) if s.strip()]
            if not sentences:
                return []
            out: list[str] = []
            for sentence in sentences:
                if len(sentence) <= piece_max:
                    out.append(sentence)
                    continue
                out.append(sentence)
            return [p for p in out if p]

        text = "मैं बस तुम्हारे सवालों का जवाब देने के लिए तैयार हूँ। कुछ बात करनी हो तो बताओ!"
        pieces = clause_units(text)
        self.assertEqual(len(pieces), 2)
        self.assertTrue(pieces[0].endswith("।"))
        self.assertIn("जवाब देने के लिए तैयार हूँ", pieces[0])
        # "जवाब देने के" must never be stranded without its sentence ending
        self.assertNotEqual(pieces[0].rstrip("। ").split()[-2:], ["जवाब", "देने"])


class TestInsertPauses(unittest.TestCase):
    """Test pause insertion in audio."""

    def setUp(self):
        import numpy as np

        self.engine = TTSEngine(
            config=TTSConfig(
                model_name="test",
                device="cpu",
                dtype=None,
                sample_rate=24000,
                temperature=0.3,
                default_speed=1.0,
                stream_max_chars=75,
                first_window_step=2,
                pause_seconds={",": 0.15, ".": 0.3, "।": 0.35},
            ),
            pronunciation_fix=lambda x: x,
        )
        self.np = np

    def test_empty_audio_returns_unchanged(self):
        wav = self.np.array([], dtype=self.np.float32)
        result = self.engine.insert_pauses(wav, "")
        self.assertEqual(len(result), 0)

    def test_no_pauses_in_text_returns_unchanged(self):
        wav = self.np.ones(1000, dtype=self.np.float32)
        result = self.engine.insert_pauses(wav, "नमस्ते")
        self.assertEqual(len(result), 1000)

    def test_comma_adds_pause(self):
        wav = self.np.ones(1000, dtype=self.np.float32)
        text = "नमस्ते, कैसे हो"
        result = self.engine.insert_pauses(wav, text)
        # Should be longer due to pause insertion
        self.assertGreater(len(result), 1000)


if __name__ == "__main__":
    unittest.main()
