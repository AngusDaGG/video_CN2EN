from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os

import config
from utils import finish_input_audio, find_input_audio, stage_next_input_audio


class AudioFlowTests(unittest.TestCase):
    def test_stage_next_input_audio_moves_oldest_lining_file_when_input_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / config.INPUT_AUDIO_DIR
            lining_dir = root / config.INPUT_AUDIO_LINING_DIR
            input_dir.mkdir()
            lining_dir.mkdir()
            newer = lining_dir / "newer.mp3"
            older = lining_dir / "older.mp3"
            newer.write_bytes(b"newer")
            older.write_bytes(b"older")
            os.utime(newer, (2000, 2000))
            os.utime(older, (1000, 1000))

            with patch("utils.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                staged = stage_next_input_audio()

            self.assertEqual(staged, input_dir / "older.mp3")
            self.assertTrue((input_dir / "older.mp3").exists())
            self.assertTrue((lining_dir / "newer.mp3").exists())
            self.assertFalse((lining_dir / "older.mp3").exists())

    def test_stage_next_input_audio_prefers_existing_input_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / config.INPUT_AUDIO_DIR
            lining_dir = root / config.INPUT_AUDIO_LINING_DIR
            input_dir.mkdir()
            lining_dir.mkdir()
            existing = input_dir / "existing.mp3"
            waiting = lining_dir / "waiting.mp3"
            existing.write_bytes(b"existing")
            waiting.write_bytes(b"waiting")

            with patch("utils.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                staged = stage_next_input_audio()

            self.assertEqual(staged, existing)
            self.assertTrue(existing.exists())
            self.assertTrue(waiting.exists())

    def test_stage_next_input_audio_returns_none_when_no_audio_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / config.INPUT_AUDIO_DIR).mkdir()
            (root / config.INPUT_AUDIO_LINING_DIR).mkdir()

            with patch("utils.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                staged = stage_next_input_audio()

            self.assertIsNone(staged)

    def test_finish_input_audio_moves_processed_file_without_overwriting_existing_finish(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / config.INPUT_AUDIO_DIR
            finish_dir = root / config.INPUT_AUDIO_FINISH_DIR
            input_dir.mkdir()
            finish_dir.mkdir()
            processed = input_dir / "sample.mp3"
            existing = finish_dir / "sample.mp3"
            processed.write_bytes(b"processed")
            existing.write_bytes(b"existing")

            with patch("utils.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                finished = finish_input_audio(processed)

            self.assertEqual(finished, finish_dir / "sample_001.mp3")
            self.assertFalse(processed.exists())
            self.assertEqual(existing.read_bytes(), b"existing")
            self.assertEqual(finished.read_bytes(), b"processed")

    def test_find_input_audio_returns_single_staged_file_after_lining_move(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / config.INPUT_AUDIO_DIR).mkdir()
            lining_dir = root / config.INPUT_AUDIO_LINING_DIR
            lining_dir.mkdir()
            (lining_dir / "queued.mp3").write_bytes(b"queued")

            with patch("utils.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                staged = stage_next_input_audio()
                audio_files = find_input_audio()

            self.assertEqual(audio_files, [staged])


if __name__ == "__main__":
    unittest.main()
