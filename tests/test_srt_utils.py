from __future__ import annotations

import unittest

from srt_utils import (
    SubtitleBlock,
    build_srt,
    chunk_blocks,
    remove_unwanted_chinese_subtitle_blocks,
    parse_srt_text,
    plain_text_from_blocks,
)


class SrtUtilsTests(unittest.TestCase):
    def test_parse_and_build_srt_preserves_multiline_text(self) -> None:
        srt = (
            "1\n"
            "00:00:00,000 --> 00:00:02,000\n"
            "第一行\n"
            "第二行\n\n"
            "2\n"
            "00:00:02,000 --> 00:00:04,000\n"
            "下一句\n"
        )

        blocks = parse_srt_text(srt)

        self.assertEqual(blocks[0].text, "第一行\n第二行")
        self.assertEqual(build_srt(blocks), srt)

    def test_chunk_blocks_respects_character_budget(self) -> None:
        blocks = [
            SubtitleBlock(1, "00:00:00,000", "00:00:01,000", "abcd"),
            SubtitleBlock(2, "00:00:01,000", "00:00:02,000", "efgh"),
            SubtitleBlock(3, "00:00:02,000", "00:00:03,000", "ijkl"),
        ]

        chunks = chunk_blocks(blocks, max_chars=8)

        self.assertEqual([[block.index for block in chunk] for chunk in chunks], [[1], [2], [3]])

    def test_plain_text_from_blocks_joins_without_srt_metadata(self) -> None:
        blocks = [
            SubtitleBlock(1, "00:00:00,000", "00:00:01,000", "Hello world."),
            SubtitleBlock(2, "00:00:01,000", "00:00:02,000", "Next line."),
        ]

        self.assertEqual(plain_text_from_blocks(blocks), "Hello world.\nNext line.")

    def test_remove_unwanted_chinese_subtitle_blocks_removes_old_ma_brand_line(self) -> None:
        blocks = [
            SubtitleBlock(1, "00:00:00,000", "00:00:01,000", "\u6211\u662f\u8001\u9a6c"),
            SubtitleBlock(2, "00:00:01,000", "00:00:02,000", "\u5176\u4ed6\u53e5\u5b50"),
        ]

        normalized = remove_unwanted_chinese_subtitle_blocks(blocks)

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].index, 1)
        self.assertEqual(normalized[0].text, "\u5176\u4ed6\u53e5\u5b50")


if __name__ == "__main__":
    unittest.main()
