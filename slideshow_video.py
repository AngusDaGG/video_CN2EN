"""Create animated universe-picture videos from an English voiceover."""

from __future__ import annotations

import math
import logging
import random
from datetime import datetime
from pathlib import Path

import config
from remotion_renderer import build_concat_file_text, clip_path_for_image
from utils import WorkflowError, get_duration_seconds, path_from_root, require_command, run_command, safe_stem


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def postprocess_voiceover(voiceover_path: Path, audio_stem: str, *, force: bool = False) -> Path:
    output_path = path_from_root(config.VOICEOVER_DIR, f"{safe_stem(Path(audio_stem))}_english_asmr.wav")
    if not force and _is_fresh(output_path, voiceover_path):
        logging.info("Reusing ASMR-style English voiceover: %s", output_path)
        return output_path
    if force and output_path.exists():
        logging.info("Force rebuilding ASMR-style English voiceover: %s", output_path)

    filter_chain = (
        "acompressor=threshold=-18dB:ratio=2.2:attack=20:release=250,"
        "loudnorm=I=-18:LRA=7:TP=-2"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(voiceover_path),
            "-af",
            filter_chain,
            "-ar",
            str(config.AUDIO_SAMPLE_RATE),
            str(output_path),
        ],
        f"Creating ASMR-style English voiceover for {voiceover_path.name}",
    )
    return output_path


def render_universe_video(voiceover_path: Path, audio_stem: str) -> Path:
    require_command("ffmpeg")
    require_command("ffprobe")

    duration = get_duration_seconds(voiceover_path)
    if duration <= 0:
        raise WorkflowError(f"Could not read a valid voiceover duration for {voiceover_path.name}.")

    output_path = _build_output_path(audio_stem)
    _ensure_image_clip_cache_is_complete()
    clips = _select_cached_clips(math.ceil(duration / config.REMOTION_CLIP_SECONDS))
    bgm_inputs = _bgm_inputs(duration)
    logging.info("Selected cached Remotion clips: %s", " | ".join(clip.name for clip in clips))
    logging.info(
        "Selected BGM segments: %s",
        " | ".join(
            f"{music_path.name} ({clip_duration:.3f}s{' looped' if should_loop else ''})"
            for music_path, clip_duration, should_loop in bgm_inputs
        ),
    )

    visual_path = path_from_root(config.TEMP_DIR, f"{safe_stem(Path(audio_stem))}_cached_remotion_visual.mp4")
    clip_list_path = path_from_root(config.TEMP_DIR, f"{safe_stem(Path(audio_stem))}_cached_remotion_clips.txt")
    clip_list_path.parent.mkdir(parents=True, exist_ok=True)
    clip_list_path.write_text(build_concat_file_text(clips), encoding="utf-8")
    run_command(
        _build_clip_concat_command(clip_list_path, visual_path),
        f"Concatenating cached Remotion clips for {audio_stem}",
    )

    args = ["ffmpeg", "-y", "-i", str(visual_path), "-i", str(voiceover_path)]
    for music_path, clip_duration, should_loop in bgm_inputs:
        if should_loop:
            args.extend(["-stream_loop", "-1"])
        args.extend(["-t", f"{clip_duration:.3f}", "-i", str(music_path)])

    filter_complex = _build_audio_filter_complex(1, bgm_inputs)
    args.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    run_command(args, f"Rendering universe slideshow video for {audio_stem}")
    return output_path


def _build_output_path(audio_stem: str, timestamp: str | None = None) -> Path:
    output_dir = path_from_root(config.OUTPUT_DIR)
    base_name = f"{safe_stem(Path(audio_stem))}_universe_slideshow"
    output_path = output_dir / f"{base_name}.mp4"
    if not output_path.exists():
        return output_path

    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{base_name}_{stamp}.mp4"


def _build_clip_concat_command(clip_list_path: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(clip_list_path),
        "-c:v",
        "copy",
        "-an",
        str(output_path),
    ]


def _ensure_image_clip_cache_is_complete() -> None:
    image_dir = path_from_root(config.UNIVERSE_PICTURE_DIR)
    clip_dir = path_from_root(config.REMOTION_CLIP_DIR)
    images = sorted(path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    missing = [image.name for image in images if not clip_path_for_image(image, clip_dir).exists()]
    if missing:
        preview = ", ".join(missing[:5])
        if len(missing) > 5:
            preview += f", and {len(missing) - 5} more"
        raise WorkflowError(
            "Cached Remotion clips are missing for image files: "
            f"{preview}. Run: python pre_render_remotion_clips.py"
        )


def _select_cached_clips(count: int) -> list[Path]:
    clip_dir = path_from_root(config.REMOTION_CLIP_DIR)
    clips = sorted(path for path in clip_dir.glob("*.mp4") if path.is_file())
    if not clips:
        raise WorkflowError(
            f"No cached Remotion clips were found in {clip_dir}. Run: python pre_render_remotion_clips.py"
        )

    selected: list[Path] = []
    previous: Path | None = None
    while len(selected) < count:
        batch = clips[:]
        random.shuffle(batch)
        if previous is not None and len(batch) > 1 and batch[0] == previous:
            batch.append(batch.pop(0))
        needed = count - len(selected)
        selected.extend(batch[:needed])
        previous = selected[-1]
    return selected


def _build_audio_filter_complex(voice_index: int, bgm_inputs: list[tuple[Path, float, bool]]) -> str:
    filters: list[str] = [
        f"[{voice_index}:a]volume={config.VOICE_VOLUME},aresample={config.AUDIO_SAMPLE_RATE},"
        f"aformat=sample_fmts=fltp:sample_rates={config.AUDIO_SAMPLE_RATE}:channel_layouts=stereo[voice]"
    ]
    music_labels: list[str] = []
    for offset, _bgm in enumerate(bgm_inputs):
        input_index = voice_index + 1 + offset
        label = f"bgm{offset}"
        filters.append(
            f"[{input_index}:a]volume={config.BGM_VOLUME},aresample={config.AUDIO_SAMPLE_RATE},"
            f"aformat=sample_fmts=fltp:sample_rates={config.AUDIO_SAMPLE_RATE}:channel_layouts=stereo[{label}]"
        )
        music_labels.append(f"[{label}]")

    if len(music_labels) == 1:
        filters.append(f"{music_labels[0]}anull[bgm]")
    else:
        filters.append(f"{''.join(music_labels)}concat=n={len(music_labels)}:v=0:a=1[bgm]")
    filters.append("[voice][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]")
    return ";".join(filters)


def _bgm_inputs(duration: float) -> list[tuple[Path, float, bool]]:
    remaining = duration
    inputs: list[tuple[Path, float, bool]] = []
    music_paths = [path_from_root(config.MUSIC_DIR, name) for name in config.BGM_SEQUENCE]
    for path in music_paths:
        if not path.exists():
            raise WorkflowError(f"Background music file was not found: {path}")

    for path in music_paths:
        if remaining <= 0:
            break
        music_duration = get_duration_seconds(path)
        clip_duration = min(remaining, music_duration)
        inputs.append((path, clip_duration, False))
        remaining -= clip_duration

    if remaining > 0:
        inputs.append((music_paths[-1], remaining, True))
    return inputs


def _is_fresh(output_path: Path, input_path: Path) -> bool:
    if not output_path.exists():
        return False
    try:
        return output_path.stat().st_mtime >= input_path.stat().st_mtime
    except OSError:
        return False
