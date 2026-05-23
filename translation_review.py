"""SRT parsing and terminology review report generation."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import config
from utils import path_from_root, safe_stem


@dataclass
class SubtitleBlock:
    index: int
    start: str
    end: str
    text: str


def parse_srt(path: Path) -> list[SubtitleBlock]:
    content = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not content:
        return []

    blocks: list[SubtitleBlock] = []
    chunks = re.split(r"\n\s*\n", content.replace("\r\n", "\n"))
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        try:
            index = int(lines[0])
        except ValueError:
            index = len(blocks) + 1
        start, end = [part.strip() for part in lines[1].split("-->", 1)]
        text = " ".join(lines[2:]).strip()
        blocks.append(SubtitleBlock(index=index, start=start, end=end, text=text))
    return blocks


def write_translation_review(chinese_srt: Path, english_srt: Path, audio_stem: str) -> Path:
    zh_blocks = parse_srt(chinese_srt)
    en_blocks = parse_srt(english_srt)
    glossary = _load_glossary_rows()
    output_path = _review_output_path(audio_stem)

    rows: list[dict[str, str]] = []
    max_len = max(len(zh_blocks), len(en_blocks))
    for index in range(max_len):
        zh = zh_blocks[index] if index < len(zh_blocks) else None
        en = en_blocks[index] if index < len(en_blocks) else None
        source_text = zh.text if zh else ""
        english_text = en.text if en else ""
        matches = _match_glossary(source_text, english_text, glossary)
        if matches:
            rows.extend(
                {
                    "start": zh.start if zh else (en.start if en else ""),
                    "end": zh.end if zh else (en.end if en else ""),
                    "source_zh": source_text,
                    "english": english_text,
                    "matched_term": source,
                    "expected_english": expected,
                    "status": status,
                }
                for source, expected, status in matches
            )
        else:
            rows.append(
                {
                    "start": zh.start if zh else (en.start if en else ""),
                    "end": zh.end if zh else (en.end if en else ""),
                    "source_zh": source_text,
                    "english": english_text,
                    "matched_term": "",
                    "expected_english": "",
                    "status": "ok",
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_review_rows(output_path, rows)
    except PermissionError:
        output_path = _timestamped_review_output_path(audio_stem)
        _write_review_rows(output_path, rows)
    return output_path


def _review_output_path(audio_stem: str, timestamp: str | None = None) -> Path:
    output_dir = path_from_root(config.TRANSLATION_DIR)
    base_name = f"{safe_stem(Path(audio_stem))}_translation_review"
    return output_dir / f"{base_name}.csv"


def _timestamped_review_output_path(audio_stem: str, timestamp: str | None = None) -> Path:
    output_dir = path_from_root(config.TRANSLATION_DIR)
    base_name = f"{safe_stem(Path(audio_stem))}_translation_review"
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{base_name}_{stamp}.csv"


def _write_review_rows(output_path: Path, rows: list[dict[str, str]]) -> None:
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["start", "end", "source_zh", "english", "matched_term", "expected_english", "status"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _load_glossary_rows() -> list[tuple[str, str]]:
    path = path_from_root(config.GLOSSARY_FILE)
    if not path.exists():
        return []

    rows: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            source = _first_nonempty(row, ["source", "中文", "Chinese", "term", "銝剜?閰?"])
            english = _first_nonempty(row, ["english", "English term", "English", "target"])
            if source and english:
                rows.append((source, english))
    return rows


def _first_nonempty(row: dict[str, str], keys: list[str]) -> str:
    lower_lookup = {key.lower(): value for key, value in row.items() if key}
    for key in keys:
        value = row.get(key) or lower_lookup.get(key.lower())
        if value and value.strip():
            return value.strip()
    return ""


def _match_glossary(source_text: str, english_text: str, glossary: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    matches: list[tuple[str, str, str]] = []
    english_lower = english_text.lower()
    for source, expected in glossary:
        if source not in source_text:
            continue
        status = "ok" if expected.lower() in english_lower else "needs_review"
        matches.append((source, expected, status))
    return matches
