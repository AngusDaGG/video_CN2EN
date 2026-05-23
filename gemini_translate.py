"""Translate Chinese SRT subtitles to English with Gemini API."""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

import config
from srt_utils import SubtitleBlock, build_srt, chunk_blocks, parse_srt, parse_srt_text, write_srt
from utils import WorkflowError, path_from_root, safe_stem


TitleGenerator = Callable[[str], str]


def run_translation(
    chinese_srt_path: Path,
    audio_stem: str,
    force: bool = False,
    *,
    metrics: object | None = None,
) -> Path:
    output_path = path_from_root(config.SUBTITLE_DIR, f"{safe_stem(Path(audio_stem))}_en.srt")
    if not force and _is_fresh(output_path, chinese_srt_path):
        logging.info("Reusing existing English subtitles: %s", output_path)
        return output_path
    if force and output_path.exists():
        logging.info("Force rebuilding English subtitles: %s", output_path)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise WorkflowError("GEMINI_API_KEY is missing. Add it to .env before running translation.")

    source_blocks = parse_srt(chinese_srt_path)
    if not source_blocks:
        raise WorkflowError(f"No subtitle blocks found in {chinese_srt_path}.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise WorkflowError("google-genai is not installed. Run: pip install -r requirements.txt") from exc

    client = genai.Client(api_key=api_key)
    generation_config = build_generation_config(types)
    translated: list[SubtitleBlock] = []
    for blocks in chunk_blocks(source_blocks, config.GEMINI_TRANSLATION_CHUNK_CHARS):
        translated.extend(translate_blocks_with_recovery(client, blocks, generation_config, metrics=metrics))

    write_srt(output_path, translated)
    return output_path


def translate_blocks_with_recovery(
    client: object,
    blocks: list[SubtitleBlock],
    generation_config: object,
    *,
    metrics: object | None = None,
    attempt_note: str = "",
) -> list[SubtitleBlock]:
    chunk_translated = try_translate_blocks(client, blocks, generation_config, metrics=metrics, attempt_note=attempt_note)
    if chunk_translated is not None:
        return chunk_translated

    if len(blocks) <= config.GEMINI_TRANSLATION_MIN_CHUNK_BLOCKS:
        raise WorkflowError(
            "Gemini translation returned a different number of subtitle blocks after retries. "
            f"Expected {len(blocks)} blocks covering indexes {blocks[0].index}-{blocks[-1].index}."
        )

    midpoint = len(blocks) // 2
    logging.warning(
        "Gemini translation chunk failed validation after retries. Splitting indexes %s-%s into smaller chunks.",
        blocks[0].index,
        blocks[-1].index,
    )
    return translate_blocks_with_recovery(
        client,
        blocks[:midpoint],
        generation_config,
        metrics=metrics,
        attempt_note="This is a smaller retry chunk after a previous response changed the block count.",
    ) + translate_blocks_with_recovery(
        client,
        blocks[midpoint:],
        generation_config,
        metrics=metrics,
        attempt_note="This is a smaller retry chunk after a previous response changed the block count.",
    )


def try_translate_blocks(
    client: object,
    blocks: list[SubtitleBlock],
    generation_config: object,
    *,
    metrics: object | None = None,
    attempt_note: str = "",
) -> list[SubtitleBlock] | None:
    mismatch_note = attempt_note
    for attempt in range(1, config.GEMINI_TRANSLATION_RETRY_ATTEMPTS + 1):
        prompt = build_translation_prompt(blocks, retry_note=mismatch_note)
        response = generate_content_with_retry(
            client,
            model=config.GEMINI_MODEL,
            contents=prompt,
            generation_config=generation_config,
        )
        record_gemini_usage(metrics, "subtitle_translation", response)
        text = extract_srt_from_response(getattr(response, "text", "") or "")
        chunk_translated = parse_srt_text(text)
        validation_error = validate_translated_blocks(blocks, chunk_translated)
        if not validation_error:
            return chunk_translated
        logging.warning(
            "Gemini translation validation failed for indexes %s-%s on attempt %s/%s: %s",
            blocks[0].index,
            blocks[-1].index,
            attempt,
            config.GEMINI_TRANSLATION_RETRY_ATTEMPTS,
            validation_error,
        )
        mismatch_note = (
            f"Previous response was invalid: {validation_error}. "
            f"Return exactly {len(blocks)} SRT blocks, with indexes {blocks[0].index} through {blocks[-1].index}, "
            "and keep every timestamp exactly unchanged."
        )
    return None


def validate_translated_blocks(source_blocks: list[SubtitleBlock], translated_blocks: list[SubtitleBlock]) -> str:
    if len(translated_blocks) != len(source_blocks):
        return f"expected {len(source_blocks)} blocks, got {len(translated_blocks)}"
    for source, translated in zip(source_blocks, translated_blocks):
        if translated.index != source.index:
            return f"expected index {source.index}, got {translated.index}"
        if translated.start != source.start or translated.end != source.end:
            return f"timestamp changed at index {source.index}"
    return ""


def build_translation_prompt(blocks: list[SubtitleBlock], retry_note: str = "") -> str:
    source_srt = build_srt(blocks).strip()
    note = f"{retry_note.strip()}\n" if retry_note.strip() else ""
    return (
        "Translate this Chinese SRT to natural native English narration subtitles.\n"
        f"{note}"
        f"This chunk contains exactly {len(blocks)} SRT blocks, indexes {blocks[0].index} through {blocks[-1].index}.\n"
        "Keep the same SRT indexes and timestamps exactly.\n"
        "Translate only the subtitle text.\n"
        "Use natural punctuation in every English subtitle text.\n"
        "Every subtitle text block should end with English sentence-ending punctuation: ., ?, or !.\n"
        "Do not add extra SRT blocks, merge blocks, split blocks, or change block order.\n"
        "Do not add commentary, markdown, notes, or extra blocks.\n"
        "Return valid SRT only.\n\n"
        f"{source_srt}"
    )


def build_title_translation_prompt(audio_stem: str) -> str:
    return (
        "Translate this source video filename into a short, natural plain English video title "
        "for spoken narration.\n"
        "Keep important names and concepts accurate.\n"
        "Remove file extensions, separators, hashtags, and upload clutter if present.\n"
        "Do not add quotes, markdown, labels, explanations, or alternatives.\n"
        "Return only the plain English video title.\n\n"
        f"Filename: {Path(audio_stem).stem}"
    )


def sanitize_translated_title(text: str) -> str:
    cleaned = (text or "").strip()
    fenced = re.match(r"^```(?:text)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    cleaned = lines[0] if lines else ""
    cleaned = re.sub(r"^(?:english\s+title|title)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip().strip("*_` ")
    while len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def translate_title_to_english(
    audio_stem: str,
    cache_stem: str,
    *,
    force: bool = False,
    metrics: object | None = None,
    generator: TitleGenerator | None = None,
) -> str:
    cache_path = path_from_root(config.TRANSLATION_DIR) / f"{cache_stem}{config.TITLE_TRANSLATION_CACHE_SUFFIX}"
    if not force and cache_path.exists():
        cached = sanitize_translated_title(cache_path.read_text(encoding="utf-8"))
        if cached:
            logging.info("Reusing cached English title: %s", cache_path)
            return cached
    if force and cache_path.exists():
        logging.info("Force rebuilding English title: %s", cache_path)

    prompt = build_title_translation_prompt(audio_stem)
    try:
        raw_title = generator(prompt) if generator else _generate_title_translation(prompt, metrics=metrics)
        title = sanitize_translated_title(raw_title)
        if not title:
            raise WorkflowError("Gemini title translation returned empty text.")
    except Exception as exc:
        fallback = sanitize_translated_title(Path(audio_stem).stem.replace("_", " ")) or "Untitled video"
        logging.warning("Gemini title translation failed; using fallback title %r: %s", fallback, exc)
        return fallback

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(f"{title}\n", encoding="utf-8")
    return title


def _generate_title_translation(prompt: str, *, metrics: object | None = None) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise WorkflowError("GEMINI_API_KEY is missing. Add it to .env before translating the title.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise WorkflowError("google-genai is not installed. Run: pip install -r requirements.txt") from exc

    client = genai.Client(api_key=api_key)
    response = generate_content_with_retry(
        client,
        model=config.GEMINI_MODEL,
        contents=prompt,
        generation_config=build_title_generation_config(types),
    )
    record_gemini_usage(metrics, "title_translation", response)
    return getattr(response, "text", "") or ""


def generate_content_with_retry(
    client: object,
    *,
    model: str,
    contents: str,
    generation_config: object,
    attempts: int = 3,
    delay_seconds: float = 15.0,
) -> object:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=generation_config,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _is_retryable_gemini_error(exc):
                raise
            logging.warning(
                "Gemini request failed with a retryable error. Retrying %s/%s in %.1f seconds: %s",
                attempt + 1,
                attempts,
                delay_seconds,
                exc,
            )
            time.sleep(delay_seconds)
    raise last_error or WorkflowError("Gemini request failed without an exception.")


def _is_retryable_gemini_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "503" in message or "unavailable" in message or "high demand" in message


def record_gemini_usage(metrics: object | None, operation: str, response: object) -> None:
    if metrics is None or not hasattr(metrics, "record_api_usage"):
        return
    usage = getattr(response, "usage_metadata", None)
    metrics.record_api_usage(
        provider="gemini",
        operation=operation,
        model=config.GEMINI_MODEL,
        prompt_tokens=getattr(usage, "prompt_token_count", None),
        candidates_tokens=getattr(usage, "candidates_token_count", None),
        total_tokens=getattr(usage, "total_token_count", None),
        thoughts_tokens=getattr(usage, "thoughts_token_count", None),
    )


def build_title_generation_config(types_module: object) -> object:
    thinking_level = getattr(config, "GEMINI_THINKING_LEVEL", "").strip()
    kwargs = {
        "system_instruction": [
            types_module.Part.from_text(
                text=(
                    "You translate source video filenames into short, natural English titles "
                    "that sound good when read aloud by an English narrator."
                )
            ),
        ],
    }
    if thinking_level:
        kwargs["thinking_config"] = types_module.ThinkingConfig(thinking_level=thinking_level)
    return types_module.GenerateContentConfig(**kwargs)


def build_generation_config(types_module: object) -> object:
    thinking_level = getattr(config, "GEMINI_THINKING_LEVEL", "").strip()
    kwargs = {
        "system_instruction": [
            types_module.Part.from_text(text=config.GEMINI_TRANSLATION_SYSTEM_INSTRUCTION),
        ],
    }
    if thinking_level:
        kwargs["thinking_config"] = types_module.ThinkingConfig(thinking_level=thinking_level)
    return types_module.GenerateContentConfig(**kwargs)


def extract_srt_from_response(text: str) -> str:
    stripped = text.strip()
    fenced = re.match(r"^```(?:srt)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return stripped


def _is_fresh(output_path: Path, input_path: Path) -> bool:
    if not output_path.exists():
        return False
    try:
        return output_path.stat().st_mtime >= input_path.stat().st_mtime
    except OSError:
        return False
