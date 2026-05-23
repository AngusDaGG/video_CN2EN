"""Shared SRT parsing, rendering, and chunking helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SubtitleBlock:
    index: int
    start: str
    end: str
    text: str


OLD_MA_SOURCE_TEXT = "\u6211\u662f\u8001\u9a6c"


def parse_srt(path: Path) -> list[SubtitleBlock]:
    return parse_srt_text(path.read_text(encoding="utf-8-sig", errors="replace"))


def parse_srt_text(content: str) -> list[SubtitleBlock]:
    content = content.strip()
    if not content:
        return []

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"\n\s*\n", normalized)
    blocks: list[SubtitleBlock] = []
    for chunk in chunks:
        lines = [line.rstrip() for line in chunk.splitlines() if line.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            index = len(blocks) + 1
        start, end = [part.strip() for part in lines[1].split("-->", 1)]
        text = "\n".join(line.strip() for line in lines[2:]).strip()
        blocks.append(SubtitleBlock(index=index, start=start, end=end, text=text))
    return blocks


def build_srt(blocks: list[SubtitleBlock]) -> str:
    rendered = []
    for block in blocks:
        rendered.append(f"{block.index}\n{block.start} --> {block.end}\n{block.text}")
    return "\n\n".join(rendered) + ("\n" if rendered else "")


def write_srt(path: Path, blocks: list[SubtitleBlock]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_srt(blocks), encoding="utf-8")


def remove_unwanted_chinese_subtitle_blocks(blocks: list[SubtitleBlock]) -> list[SubtitleBlock]:
    cleaned: list[SubtitleBlock] = []
    for block in blocks:
        if block.text.strip() == OLD_MA_SOURCE_TEXT:
            continue
        cleaned.append(SubtitleBlock(len(cleaned) + 1, block.start, block.end, block.text))
    return cleaned


def chunk_blocks(blocks: list[SubtitleBlock], max_chars: int) -> list[list[SubtitleBlock]]:
    chunks: list[list[SubtitleBlock]] = []
    current: list[SubtitleBlock] = []
    current_size = 0
    for block in blocks:
        block_size = len(build_srt([block]))
        if current and current_size + block_size > max_chars:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(block)
        current_size += block_size
    if current:
        chunks.append(current)
    return chunks


def plain_text_from_blocks(blocks: list[SubtitleBlock]) -> str:
    return "\n".join(block.text.replace("\n", " ").strip() for block in blocks if block.text.strip())
