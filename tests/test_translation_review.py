from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import translation_review


class TranslationReviewTests(unittest.TestCase):
    def test_review_output_path_reuses_plain_name_when_target_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            existing = output_dir / "sample_translation_review.csv"
            existing.write_text("open elsewhere", encoding="utf-8")

            with patch("translation_review.path_from_root", return_value=output_dir):
                output_path = translation_review._review_output_path("sample", timestamp="20260520_083600")

            self.assertEqual(output_path.name, "sample_translation_review.csv")

    def test_write_translation_review_uses_timestamp_when_plain_output_is_locked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            zh_srt = root / "sample_zh.srt"
            en_srt = root / "sample_en.srt"
            zh_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n測試\n", encoding="utf-8")
            en_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest.\n", encoding="utf-8")
            output_dir = root / "translations"
            output_dir.mkdir()

            def fake_open(path, *args, **kwargs):
                if path.name == "sample_translation_review.csv":
                    raise PermissionError("locked")
                return original_open(path, *args, **kwargs)

            original_open = translation_review.Path.open
            with patch("translation_review.path_from_root", return_value=output_dir):
                with patch("translation_review.datetime") as datetime:
                    datetime.now.return_value.strftime.return_value = "20260520_083600"
                    with patch("translation_review._load_glossary_rows", return_value=[]):
                        with patch("translation_review.Path.open", fake_open):
                            output_path = translation_review.write_translation_review(zh_srt, en_srt, "sample")

            self.assertEqual(output_path.name, "sample_translation_review_20260520_083600.csv")


if __name__ == "__main__":
    unittest.main()
