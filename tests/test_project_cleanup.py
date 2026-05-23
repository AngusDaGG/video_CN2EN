from __future__ import annotations

import unittest
from pathlib import Path

import config


LEGACY_SCRIPT_NAMES = [
    "extract_audio.py",
    "generate_subtitles.py",
    "generate_voiceover.py",
    "manual_review.py",
    "mix_audio.py",
    "pyvideotrans_audio_runner.py",
    "pyvideotrans_runner.py",
    "render_video.py",
    "rewrite_narration.py",
    "transcribe.py",
    "translate.py",
]


class ProjectCleanupTests(unittest.TestCase):
    def test_legacy_scripts_have_been_removed_after_review(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        legacy_dir = project_root / "legacy"

        for script_name in LEGACY_SCRIPT_NAMES:
            with self.subTest(script_name=script_name):
                self.assertFalse((project_root / script_name).exists())
                self.assertFalse((legacy_dir / script_name).exists())

    def test_faster_whisper_model_path_is_project_local(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        model_path = Path(config.FASTER_WHISPER_MODEL_PATH)

        self.assertTrue(model_path.is_relative_to(project_root))
        self.assertEqual(model_path.parts[-2], "models")


if __name__ == "__main__":
    unittest.main()
