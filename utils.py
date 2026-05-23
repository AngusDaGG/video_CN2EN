"""Shared helpers for logging, files, subprocesses, and simple media metadata."""

from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import config


PROJECT_ROOT = Path(__file__).resolve().parent


class WorkflowError(Exception):
    """A beginner-friendly error raised by the localization workflow."""


def path_from_root(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def ensure_directories() -> None:
    for folder in [
        config.INPUT_DIR,
        config.INPUT_AUDIO_DIR,
        config.INPUT_AUDIO_LINING_DIR,
        config.INPUT_AUDIO_FINISH_DIR,
        config.OUTPUT_DIR,
        config.AUDIO_DIR,
        config.TRANSCRIPT_DIR,
        config.TRANSLATION_DIR,
        config.NARRATION_DIR,
        config.SUBTITLE_DIR,
        config.VOICEOVER_DIR,
        config.MUSIC_DIR,
        config.LOG_DIR,
        config.UNIVERSE_PICTURE_DIR,
        config.REMOTION_CLIP_DIR,
        config.TEMP_DIR,
    ]:
        path_from_root(folder).mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    ensure_directories()
    log_path = path_from_root(config.LOG_DIR, "workflow.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def log_step(message: str) -> None:
    logging.info(message)


def require_command(command: str) -> None:
    if resolve_command(command) is None:
        raise WorkflowError(
            f"Cannot find '{command}'. Please install FFmpeg and make sure '{command}' is available in your PATH."
        )


def resolve_command(command: str) -> str | None:
    configured_bin = os.getenv("FFMPEG_BIN_DIR")
    if command in {"ffmpeg", "ffprobe"} and configured_bin:
        extension = ".exe" if os.name == "nt" else ""
        candidate = Path(configured_bin) / f"{command}{extension}"
        if candidate.exists():
            return str(candidate)
    return shutil.which(command)


def load_env_file(path: Path | None = None) -> None:
    env_path = path or path_from_root(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def run_command(args: list[str], description: str) -> None:
    logging.info("%s", description)
    resolved = resolve_command(args[0])
    if resolved:
        args = [resolved, *args[1:]]
    logging.debug("Command: %s", " ".join(args))
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        logging.error(result.stderr)
        raise WorkflowError(f"{description} failed. FFmpeg said: {result.stderr.strip()}")


def get_duration_seconds(media_path: Path) -> float:
    require_command("ffprobe")
    ffprobe = resolve_command("ffprobe") or "ffprobe"
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise WorkflowError(f"Could not read duration for {media_path.name}: {result.stderr.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise WorkflowError(f"Could not understand duration for {media_path.name}.") from exc


def find_input_videos() -> list[Path]:
    input_dir = path_from_root(config.INPUT_DIR)
    return sorted(input_dir.glob("*.mp4"))


def find_input_audio() -> list[Path]:
    input_dir = path_from_root(config.INPUT_AUDIO_DIR)
    return sorted(input_dir.glob("*.mp3"))


def find_lining_audio() -> list[Path]:
    lining_dir = path_from_root(config.INPUT_AUDIO_LINING_DIR)
    return sorted(lining_dir.glob("*.mp3"), key=lambda path: (path.stat().st_mtime, path.name.lower()))


def stage_next_input_audio() -> Path | None:
    existing_audio = find_input_audio()
    if existing_audio:
        return existing_audio[0]

    lining_audio = find_lining_audio()
    if not lining_audio:
        return None

    source = lining_audio[0]
    destination = path_from_root(config.INPUT_AUDIO_DIR, source.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    logging.info("Moved queued audio into input_audio: %s", destination.name)
    return destination


def finish_input_audio(audio_path: Path) -> Path:
    finish_dir = path_from_root(config.INPUT_AUDIO_FINISH_DIR)
    finish_dir.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(finish_dir / audio_path.name)
    shutil.move(str(audio_path), str(destination))
    logging.info("Moved processed audio to input_audio_finish: %s", destination.name)
    return destination


def _unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    for index in range(1, 1000):
        candidate = destination.with_name(f"{destination.stem}_{index:03d}{destination.suffix}")
        if not candidate.exists():
            return candidate
    raise WorkflowError(f"Could not choose a unique finished audio name for {destination.name}.")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_glossary() -> list[dict[str, str]]:
    glossary_path = path_from_root(config.GLOSSARY_FILE)
    if not glossary_path.exists():
        return []

    entries: list[dict[str, str]] = []
    with glossary_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            source = (row.get("中文詞") or row.get("source") or "").strip()
            english = (row.get("English term") or row.get("english") or "").strip()
            notes = (row.get("notes") or "").strip()
            if source and english:
                entries.append({"source": source, "english": english, "notes": notes})
    return entries


def format_glossary_for_prompt(entries: Iterable[dict[str, str]]) -> str:
    lines = []
    for item in entries:
        note = f" ({item['notes']})" if item.get("notes") else ""
        lines.append(f"- {item['source']} => {item['english']}{note}")
    return "\n".join(lines) if lines else "No glossary entries provided."


def seconds_to_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    secs = milliseconds // 1000
    millis = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def safe_stem(path: Path) -> str:
    return path.stem.replace(" ", "_")


def print_review_checklist() -> None:
    checklist = [
        "1. Check whether the English translation is accurate.",
        "2. Confirm all proper nouns and technical terms are correct.",
        "3. Check whether the English narration sounds natural.",
        "4. Check whether the voiceover is clear.",
        "5. Check whether the BGM is too loud.",
        "6. Check whether subtitles are readable.",
        "7. Check whether the final video has copyright or reused-content risks.",
        "8. Only upload manually after review.",
    ]
    print("\nHuman review checklist:")
    for item in checklist:
        print(item)
