from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import config as app_config
from gemini_translate import (
    build_generation_config,
    build_title_translation_prompt,
    build_translation_prompt,
    extract_srt_from_response,
    generate_content_with_retry,
    run_translation,
    sanitize_translated_title,
    translate_blocks_with_recovery,
    translate_title_to_english,
    validate_translated_blocks,
)
from srt_utils import SubtitleBlock


class GeminiTranslateTests(unittest.TestCase):
    def test_prompt_requires_preserving_srt_timing(self) -> None:
        prompt = build_translation_prompt(
            [
                SubtitleBlock(
                    1,
                    "00:00:00,000",
                    "00:00:01,500",
                    "\u4f60\u597d",
                )
            ]
        )

        self.assertIn("00:00:00,000 --> 00:00:01,500", prompt)
        self.assertIn("Keep the same SRT indexes and timestamps", prompt)
        self.assertIn("Translate only the subtitle text", prompt)
        self.assertIn("natural native English", prompt)

    def test_prompt_requires_natural_sentence_ending_punctuation(self) -> None:
        prompt = build_translation_prompt(
            [
                SubtitleBlock(
                    1,
                    "00:00:00,000",
                    "00:00:01,500",
                    "\u9019\u662f\u6e2c\u8a66",
                )
            ]
        )

        self.assertIn("natural punctuation", prompt)
        self.assertIn("sentence-ending punctuation", prompt)
        self.assertIn("Do not add extra SRT blocks", prompt)

    def test_prompt_includes_exact_chunk_block_count(self) -> None:
        prompt = build_translation_prompt(
            [
                SubtitleBlock(7, "00:00:00,000", "00:00:01,000", "\u7b2c\u4e00\u53e5"),
                SubtitleBlock(8, "00:00:01,000", "00:00:02,000", "\u7b2c\u4e8c\u53e5"),
            ],
            retry_note="Previous response was invalid.",
        )

        self.assertIn("Previous response was invalid.", prompt)
        self.assertIn("exactly 2 SRT blocks", prompt)
        self.assertIn("indexes 7 through 8", prompt)

    def test_extract_srt_from_response_strips_markdown_fence(self) -> None:
        response = "```srt\n1\n00:00:00,000 --> 00:00:01,000\nHello.\n```"

        self.assertEqual(
            extract_srt_from_response(response),
            "1\n00:00:00,000 --> 00:00:01,000\nHello.",
        )

    def test_title_translation_prompt_requests_plain_english_title(self) -> None:
        chinese_title = "\u6cf0\u5766\u5c3c\u514b\u53f7\u6700\u540e\u768437\u79d2"
        prompt = build_title_translation_prompt(chinese_title)

        self.assertIn("plain English video title", prompt)
        self.assertIn("Do not add quotes", prompt)
        self.assertIn(chinese_title, prompt)

    def test_sanitize_translated_title_removes_wrapping_quotes_and_markdown(self) -> None:
        title = sanitize_translated_title('**"The Titanic\'s Final 37 Seconds"**')

        self.assertEqual(title, "The Titanic's Final 37 Seconds")

    def test_translate_title_to_english_uses_cache_before_generator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / "translations"
            cache_dir.mkdir()
            (cache_dir / "sample_title_en.txt").write_text("Cached English Title\n", encoding="utf-8")

            with patch("gemini_translate.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                title = translate_title_to_english(
                    "\u4e2d\u6587\u6a94\u540d",
                    "sample",
                    generator=Mock(side_effect=AssertionError("generator should not run")),
                )

        self.assertEqual(title, "Cached English Title")

    def test_translate_title_to_english_writes_generated_title_to_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch("gemini_translate.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                title = translate_title_to_english(
                    "\u6cf0\u5766\u5c3c\u514b\u53f7\u6700\u540e\u768437\u79d2",
                    "titanic",
                    generator=Mock(return_value='"The Titanic\'s Final 37 Seconds"'),
                )

            self.assertEqual(title, "The Titanic's Final 37 Seconds")
            self.assertEqual(
                (root / "translations" / "titanic_title_en.txt").read_text(encoding="utf-8"),
                "The Titanic's Final 37 Seconds\n",
            )

    def test_translate_title_to_english_falls_back_to_clean_original_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch("gemini_translate.path_from_root", side_effect=lambda *parts: root.joinpath(*parts)):
                title = translate_title_to_english(
                    "\u4e2d\u6587 \u6a94\u540d",
                    "sample",
                    generator=Mock(side_effect=RuntimeError("api unavailable")),
                )

        self.assertEqual(title, "\u4e2d\u6587 \u6a94\u540d")

    def test_generate_content_with_retry_retries_temporary_503_errors(self) -> None:
        client = Mock()
        client.models.generate_content.side_effect = [
            RuntimeError("503 UNAVAILABLE high demand"),
            Mock(text="ok"),
        ]

        with patch("gemini_translate.time.sleep") as sleep:
            response = generate_content_with_retry(
                client,
                model="gemini-test",
                contents="prompt",
                generation_config={"config": "ok"},
                attempts=2,
                delay_seconds=0.01,
            )

        self.assertEqual(response.text, "ok")
        self.assertEqual(client.models.generate_content.call_count, 2)
        sleep.assert_called_once()

    def test_run_translation_does_not_reuse_existing_subtitle_when_forced(self) -> None:
        with patch("gemini_translate._is_fresh", return_value=True):
            with patch.dict("gemini_translate.os.environ", {}, clear=True):
                with self.assertRaisesRegex(Exception, "GEMINI_API_KEY"):
                    run_translation(Mock(), "sample", force=True)

    def test_build_generation_config_uses_translation_system_instruction(self) -> None:
        fake_types = Mock()
        fake_types.Part.from_text.side_effect = lambda text: {"text": text}
        fake_types.ThinkingConfig.return_value = {"thinking": "MEDIUM"}
        fake_types.GenerateContentConfig.return_value = {"config": "ok"}

        with patch("gemini_translate.config.GEMINI_THINKING_LEVEL", "MEDIUM"):
            generation_config = build_generation_config(fake_types)

        self.assertEqual(generation_config, {"config": "ok"})
        fake_types.Part.from_text.assert_called_once_with(text=app_config.GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)
        fake_types.ThinkingConfig.assert_called_once_with(thinking_level="MEDIUM")

    def test_validate_translated_blocks_rejects_block_count_mismatch(self) -> None:
        source = [
            SubtitleBlock(1, "00:00:00,000", "00:00:01,000", "\u4f60\u597d"),
            SubtitleBlock(2, "00:00:01,000", "00:00:02,000", "\u4e16\u754c"),
        ]
        translated = [SubtitleBlock(1, "00:00:00,000", "00:00:01,000", "Hello.")]

        self.assertIn("expected 2 blocks, got 1", validate_translated_blocks(source, translated))

    def test_translate_blocks_with_recovery_retries_after_block_count_mismatch(self) -> None:
        blocks = [
            SubtitleBlock(1, "00:00:00,000", "00:00:01,000", "\u4f60\u597d"),
            SubtitleBlock(2, "00:00:01,000", "00:00:02,000", "\u4e16\u754c"),
        ]
        client = Mock()
        client.models.generate_content.side_effect = [
            Mock(text="1\n00:00:00,000 --> 00:00:01,000\nHello."),
            Mock(
                text=(
                    "1\n00:00:00,000 --> 00:00:01,000\nHello.\n\n"
                    "2\n00:00:01,000 --> 00:00:02,000\nWorld."
                )
            ),
        ]

        translated = translate_blocks_with_recovery(client, blocks, {"config": "ok"})

        self.assertEqual([block.text for block in translated], ["Hello.", "World."])
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_translate_blocks_with_recovery_splits_chunk_after_retries_fail(self) -> None:
        blocks = [
            SubtitleBlock(index, f"00:00:0{index},000", f"00:00:0{index + 1},000", f"\u7b2c{index}\u53e5")
            for index in range(1, 11)
        ]
        client = Mock()

        def generate_content(*, model: str, contents: str, config: object) -> Mock:
            parsed = []
            for block in blocks:
                if f"\n{block.index}\n" in f"\n{contents}\n":
                    parsed.append(block)
            if len(parsed) == len(blocks):
                return Mock(text="1\n00:00:01,000 --> 00:00:02,000\nOnly one block.")
            return Mock(
                text="\n\n".join(
                    f"{block.index}\n{block.start} --> {block.end}\nTranslated {block.index}."
                    for block in parsed
                )
            )

        client.models.generate_content.side_effect = generate_content

        with patch("gemini_translate.config.GEMINI_TRANSLATION_RETRY_ATTEMPTS", 1):
            translated = translate_blocks_with_recovery(client, blocks, {"config": "ok"})

        self.assertEqual(len(translated), 10)
        self.assertEqual(translated[0].text, "Translated 1.")
        self.assertGreater(client.models.generate_content.call_count, 1)


if __name__ == "__main__":
    unittest.main()
