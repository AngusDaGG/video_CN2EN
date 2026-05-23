from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

import config
import slideshow_video
from utils import WorkflowError


class SlideshowClipCacheTests(unittest.TestCase):
    def test_select_cached_clips_repeats_until_count_is_met(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            clip_dir = Path(temp_dir)
            first = clip_dir / "a.mp4"
            second = clip_dir / "b.mp4"
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")

            with patch("slideshow_video.path_from_root", return_value=clip_dir):
                selected = slideshow_video._select_cached_clips(3)

            self.assertEqual(len(selected), 3)
            self.assertEqual({path.name for path in selected}, {"a.mp4", "b.mp4"})

    def test_select_cached_clips_raises_with_pre_render_command_when_none_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            clip_dir = Path(temp_dir)

            with patch("slideshow_video.path_from_root", return_value=clip_dir):
                with self.assertRaises(WorkflowError) as raised:
                    slideshow_video._select_cached_clips(1)

            self.assertIn("python pre_render_remotion_clips.py", str(raised.exception))

    def test_build_clip_concat_command_uses_concat_demuxer_and_copy_video(self) -> None:
        command = slideshow_video._build_clip_concat_command(
            clip_list_path=Path("temp/clips.txt"),
            output_path=Path("temp/visual.mp4"),
        )

        self.assertIn("-f", command)
        self.assertIn("concat", command)
        self.assertIn("-c:v", command)
        self.assertIn("copy", command)

    def test_bgm_uses_one_hour_track_at_seventy_percent_volume(self) -> None:
        self.assertEqual(config.BGM_SEQUENCE, ["1 HOUR.mp3"])
        self.assertEqual(config.BGM_VOLUME, 0.7)

    def test_build_output_path_adds_timestamp_when_target_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            existing = output_dir / "sample_universe_slideshow.mp4"
            existing.write_text("locked or existing output", encoding="utf-8")

            with patch("slideshow_video.path_from_root", return_value=output_dir):
                output_path = slideshow_video._build_output_path("sample", timestamp="20260520_083500")

            self.assertEqual(output_path.name, "sample_universe_slideshow_20260520_083500.mp4")

    def test_postprocess_voiceover_reuses_fresh_asmr_voiceover(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            voiceover_path = root / "sample_english.wav"
            voiceover_path.write_bytes(b"google voice")
            output_path = root / config.VOICEOVER_DIR / "sample_english_asmr.wav"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"cached asmr")
            os.utime(voiceover_path, (100, 100))
            os.utime(output_path, (200, 200))

            def fake_path_from_root(*parts: str) -> Path:
                return root.joinpath(*parts)

            with patch("slideshow_video.path_from_root", side_effect=fake_path_from_root):
                with patch("slideshow_video.run_command") as run_command:
                    returned_path = slideshow_video.postprocess_voiceover(voiceover_path, "sample")

            self.assertEqual(returned_path, output_path)
            run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
