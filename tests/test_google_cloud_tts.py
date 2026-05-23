from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import config
from google_cloud_tts import (
    build_synthesize_payload,
    build_tts_narration_text,
    metadata_path_for_voiceover,
    run_tts,
    split_text_for_tts,
    synthesize_text,
    write_audio_content,
)
from utils import WorkflowError


class GoogleCloudTtsTests(unittest.TestCase):
    def test_build_synthesize_payload_uses_linear16_and_voice_settings(self) -> None:
        payload = build_synthesize_payload(
            text="Hello.",
            language_code="en-US",
            voice_name="en-US-Chirp3-HD-Charon",
            speaking_rate=0.92,
            pitch=-2.0,
            volume_gain_db=1.5,
            sample_rate_hertz=24000,
        )

        self.assertEqual(payload["input"]["text"], "Hello.")
        self.assertEqual(payload["voice"]["languageCode"], "en-US")
        self.assertEqual(payload["voice"]["name"], "en-US-Chirp3-HD-Charon")
        self.assertEqual(payload["audioConfig"]["audioEncoding"], "LINEAR16")
        self.assertEqual(payload["audioConfig"]["sampleRateHertz"], 24000)

    def test_build_synthesize_payload_omits_pitch_when_none(self) -> None:
        payload = build_synthesize_payload(
            text="Hello.",
            language_code="en-US",
            voice_name="en-US-Chirp3-HD-Charon",
            speaking_rate=0.92,
            pitch=None,
            volume_gain_db=0.0,
            sample_rate_hertz=24000,
        )

        self.assertNotIn("pitch", payload["audioConfig"])

    def test_split_text_for_tts_prefers_sentence_boundaries(self) -> None:
        chunks = split_text_for_tts("First sentence. Second sentence. Third sentence.", max_chars=28)

        self.assertEqual(chunks, ["First sentence.", "Second sentence.", "Third sentence."])

    def test_split_text_for_tts_treats_subtitle_lines_as_sentence_boundaries(self) -> None:
        text = "\n".join(
            [
                "Musk says AGI arrives soon",
                "The old world starts changing",
                "Half the jobs may disappear",
            ]
        )

        chunks = split_text_for_tts(text, max_chars=80)

        self.assertEqual(
            chunks,
            [
                "Musk says AGI arrives soon. The old world starts changing.",
                "Half the jobs may disappear.",
            ],
        )

    def test_write_audio_content_decodes_base64(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "voice.wav"
            encoded = base64.b64encode(b"RIFFdata").decode("ascii")

            write_audio_content(encoded, output_path)

            self.assertEqual(output_path.read_bytes(), b"RIFFdata")

    def test_build_tts_narration_text_wraps_srt_with_fixed_intro_and_outro(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            srt_path = Path(temp_dir) / "sample_en.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nOriginal narration.\n",
                encoding="utf-8",
            )

            narration = build_tts_narration_text(srt_path, "sample video", english_video_title="Sample Video")

        self.assertTrue(narration.startswith("Believe it or not, I can make you fall asleep before this video ends."))
        self.assertIn("Welcome to Dreaming Universe", narration)
        self.assertNotIn("It is time to say good night.", narration)
        self.assertIn('"Sample Video"', narration)
        self.assertIn("Original narration.", narration)
        self.assertTrue(
            narration.endswith(
                "May you have a beautiful dream. Good night. "
                "If you're still not tired, tag me under your comment. "
                "I'll send you a little mystery gift."
            )
        )

    def test_build_tts_narration_text_uses_english_title_in_intro(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            srt_path = Path(temp_dir) / "sample_en.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nOriginal narration.\n",
                encoding="utf-8",
            )

            narration = build_tts_narration_text(
                srt_path,
                "\u4e2d\u6587\u6a94\u540d",
                english_video_title="The Titanic's Final 37 Seconds",
            )

        self.assertIn('"The Titanic\'s Final 37 Seconds"', narration)
        self.assertNotIn("\u4e2d\u6587\u6a94\u540d", narration)

    def test_run_tts_regenerates_existing_voiceover_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            srt_path = root / "sample_en.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nFresh narration.\n", encoding="utf-8")
            output_path = root / config.VOICEOVER_DIR / "sample_english.wav"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"old voice")

            def fake_path_from_root(*parts: str) -> Path:
                return root.joinpath(*parts)

            encoded = base64.b64encode(b"new google voice").decode("ascii")
            with patch.dict("google_cloud_tts.os.environ", {"GOOGLE_CLOUD_TTS_API_KEY": "test-key"}):
                with patch("google_cloud_tts.path_from_root", side_effect=fake_path_from_root):
                    with patch("google_cloud_tts.synthesize_text", return_value=encoded) as synthesize:
                        returned_path = run_tts(srt_path, "sample", english_video_title="Sample")

            self.assertEqual(returned_path, output_path)
            self.assertEqual(output_path.read_bytes(), b"new google voice")
            synthesize.assert_called_once()

    def test_run_tts_reuses_voiceover_when_narration_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            srt_path = root / "sample_en.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nCached narration.\n", encoding="utf-8")
            output_path = root / config.VOICEOVER_DIR / "sample_english.wav"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"cached voice")

            def fake_path_from_root(*parts: str) -> Path:
                return root.joinpath(*parts)

            with patch("google_cloud_tts.path_from_root", side_effect=fake_path_from_root):
                narration = build_tts_narration_text(srt_path, "sample", english_video_title="Sample")
                metadata_path_for_voiceover(output_path).write_text(
                    '{"narration_sha256": "' + __import__("hashlib").sha256(narration.encode("utf-8")).hexdigest() + '"}',
                    encoding="utf-8",
                )
                with patch("google_cloud_tts.synthesize_text") as synthesize:
                    returned_path = run_tts(srt_path, "sample", english_video_title="Sample")

            self.assertEqual(returned_path, output_path)
            self.assertEqual(output_path.read_bytes(), b"cached voice")
            synthesize.assert_not_called()

    def test_synthesize_text_sanitizes_request_errors(self) -> None:
        with patch("google_cloud_tts.requests.post") as post:
            post.side_effect = requests.exceptions.ConnectionError(
                "https://texttospeech.googleapis.com/v1/text:synthesize?key=secret-key"
            )

            with self.assertRaises(WorkflowError) as context:
                synthesize_text("Hello.", "secret-key")

        self.assertNotIn("secret-key", str(context.exception))

    def test_synthesize_text_sanitizes_non_200_response(self) -> None:
        response = Mock()
        response.status_code = 400
        response.text = "bad key secret-key"
        with patch("google_cloud_tts.requests.post", return_value=response):
            with self.assertRaises(WorkflowError) as context:
                synthesize_text("Hello.", "secret-key")

        self.assertNotIn("secret-key", str(context.exception))


if __name__ == "__main__":
    unittest.main()
