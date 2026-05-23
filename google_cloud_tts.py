"""Generate English voiceover with Google Cloud Text-to-Speech REST API."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import requests

import config
from srt_utils import parse_srt, plain_text_from_blocks
from utils import WorkflowError, path_from_root, run_command, safe_stem


def run_tts(
    english_srt_path: Path,
    audio_stem: str,
    *,
    english_video_title: str | None = None,
    force: bool = False,
    metrics: object | None = None,
) -> Path:
    output_path = path_from_root(config.VOICEOVER_DIR, f"{safe_stem(Path(audio_stem))}_english.wav")

    text = build_tts_narration_text(english_srt_path, audio_stem, english_video_title=english_video_title)
    if not text.strip():
        raise WorkflowError(f"No English narration text found in {english_srt_path}.")
    narration_hash = hash_narration_text(text)
    if not force and output_path.exists() and _voiceover_metadata_matches(output_path, narration_hash):
        logging.info("Reusing content-matched English voiceover: %s", output_path)
        return output_path
    if force and output_path.exists():
        logging.info("Force rebuilding Google Cloud TTS voiceover: %s", output_path)
    elif output_path.exists():
        logging.info(
            "Regenerating Google Cloud TTS voiceover because cached metadata is missing or changed: %s",
            output_path,
        )

    api_key = os.getenv("GOOGLE_CLOUD_TTS_API_KEY", "").strip()
    if not api_key:
        raise WorkflowError("GOOGLE_CLOUD_TTS_API_KEY is missing. Add it to .env before running TTS.")

    chunks = split_text_for_tts(text, config.GOOGLE_TTS_MAX_CHARS)
    segment_paths = []
    for index, chunk in enumerate(chunks, start=1):
        segment_path = path_from_root(
            config.TEMP_DIR,
            f"{safe_stem(Path(audio_stem))}_google_tts_{index:03d}.wav",
        )
        record_tts_usage(metrics, chunk)
        audio_content = synthesize_text(chunk, api_key)
        write_audio_content(audio_content, segment_path)
        segment_paths.append(segment_path)

    if len(segment_paths) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(segment_paths[0].read_bytes())
    else:
        _concat_audio_segments(segment_paths, output_path, audio_stem)
    write_voiceover_metadata(output_path, narration_hash)
    return output_path


def record_tts_usage(metrics: object | None, text: str) -> None:
    if metrics is None or not hasattr(metrics, "record_api_usage"):
        return
    metrics.record_api_usage(
        provider="google_tts",
        operation="synthesize",
        model=config.GOOGLE_TTS_VOICE_NAME,
        characters=len(text),
        requests=1,
    )


def synthesize_text(text: str, api_key: str) -> str:
    endpoint = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    payload = build_synthesize_payload(
        text=text,
        language_code=config.GOOGLE_TTS_LANGUAGE_CODE,
        voice_name=config.GOOGLE_TTS_VOICE_NAME,
        speaking_rate=config.GOOGLE_TTS_SPEAKING_RATE,
        pitch=config.GOOGLE_TTS_PITCH,
        volume_gain_db=config.GOOGLE_TTS_VOLUME_GAIN_DB,
        sample_rate_hertz=config.GOOGLE_TTS_SAMPLE_RATE_HERTZ,
    )
    try:
        response = requests.post(endpoint, json=payload, timeout=config.GOOGLE_TTS_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise WorkflowError(
            "Google Cloud TTS request failed before receiving a response. "
            "Check network access and GOOGLE_CLOUD_TTS_API_KEY."
        ) from exc
    if response.status_code != 200:
        raise WorkflowError(
            "Google Cloud TTS request failed. Check GOOGLE_CLOUD_TTS_API_KEY and "
            f"GOOGLE_TTS_VOICE_NAME. HTTP status: {response.status_code}."
        )
    data: dict[str, Any] = response.json()
    audio_content = data.get("audioContent")
    if not isinstance(audio_content, str) or not audio_content:
        raise WorkflowError("Google Cloud TTS response did not include audioContent.")
    return audio_content


def build_tts_narration_text(
    english_srt_path: Path,
    audio_stem: str,
    *,
    english_video_title: str | None = None,
) -> str:
    body = plain_text_from_blocks(parse_srt(english_srt_path)).strip()
    title = (english_video_title or Path(audio_stem).stem).strip()
    intro = config.TTS_INTRO_TEMPLATE.format(video_title=title).strip()
    outro = config.TTS_OUTRO_TEXT.strip()
    return "\n".join(part for part in [intro, body, outro] if part)


def hash_narration_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def metadata_path_for_voiceover(voiceover_path: Path) -> Path:
    return voiceover_path.with_suffix(f"{voiceover_path.suffix}.json")


def write_voiceover_metadata(voiceover_path: Path, narration_hash: str) -> None:
    metadata_path = metadata_path_for_voiceover(voiceover_path)
    metadata_path.write_text(
        json.dumps({"narration_sha256": narration_hash}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_synthesize_payload(
    *,
    text: str,
    language_code: str,
    voice_name: str,
    speaking_rate: float,
    pitch: float | None,
    volume_gain_db: float,
    sample_rate_hertz: int,
) -> dict[str, object]:
    audio_config: dict[str, object] = {
        "audioEncoding": "LINEAR16",
        "speakingRate": speaking_rate,
        "volumeGainDb": volume_gain_db,
        "sampleRateHertz": sample_rate_hertz,
    }
    if pitch is not None:
        audio_config["pitch"] = pitch

    return {
        "input": {"text": text},
        "voice": {
            "languageCode": language_code,
            "name": voice_name,
        },
        "audioConfig": audio_config,
    }


def split_text_for_tts(text: str, max_chars: int) -> list[str]:
    sentences = _tts_sentence_units(text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences or [text.strip()]:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(sentence, max_chars))
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _tts_sentence_units(text: str) -> list[str]:
    units: list[str] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for line in normalized.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", line)
        for part in parts:
            sentence = part.strip()
            if sentence:
                units.append(_ensure_sentence_punctuation(sentence))
    return units


def _ensure_sentence_punctuation(text: str) -> str:
    if text.endswith((".", "!", "?")):
        return text
    return f"{text}."


def write_audio_content(audio_content: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(audio_content))


def _split_long_text(text: str, max_chars: int) -> list[str]:
    chunks = []
    remaining = text.strip()
    while remaining:
        chunks.append(remaining[:max_chars].strip())
        remaining = remaining[max_chars:].strip()
    return chunks


def _concat_audio_segments(segment_paths: list[Path], output_path: Path, audio_stem: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_path = path_from_root(config.TEMP_DIR, f"{safe_stem(Path(audio_stem))}_google_tts_concat.txt")
    list_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"file '{_ffmpeg_concat_path(path)}'" for path in segment_paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ],
        f"Concatenating Google Cloud TTS segments for {audio_stem}",
    )


def _voiceover_metadata_matches(voiceover_path: Path, narration_hash: str) -> bool:
    metadata_path = metadata_path_for_voiceover(voiceover_path)
    if not metadata_path.exists():
        return False
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("narration_sha256") == narration_hash


def _ffmpeg_concat_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''")
