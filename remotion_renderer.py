"""Helpers for rendering a Remotion visual test and NVENC final MP4."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import config
from utils import WorkflowError, path_from_root, require_command, resolve_command


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
REMOTION_DIR = path_from_root("remotion")
PROPS_PATH = path_from_root(config.TEMP_DIR, "remotion_props.json")
INTERMEDIATE_OUTPUT = path_from_root(config.TEMP_DIR, "remotion_visual_intermediate.mov")
FINAL_OUTPUT = path_from_root(config.OUTPUT_DIR, "remotion_gpu_test.mp4")


def select_remotion_images(image_dir: Path, count: int) -> list[Path]:
    images = sorted(
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        raise WorkflowError(f"No images were found in {image_dir}.")
    if count <= 0:
        raise WorkflowError("Image count must be greater than zero.")
    return images[: min(count, len(images))]


def build_remotion_props(
    *,
    images: list[Path],
    duration_seconds: float,
    seconds_per_image: float,
    width: int,
    height: int,
    fps: int,
    resolve_images: bool = True,
) -> dict[str, Any]:
    if not images:
        raise WorkflowError("At least one image is required for the Remotion visual test.")
    return {
        "images": [str(path.resolve()) if resolve_images else path.as_posix() for path in images],
        "durationSeconds": duration_seconds,
        "secondsPerImage": seconds_per_image,
        "width": width,
        "height": height,
        "fps": fps,
    }


def write_props_file(output_path: Path, props: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")


def clip_path_for_image(image_path: Path, clip_dir: Path) -> Path:
    return clip_dir / f"{image_path.stem}.mp4"


def metadata_path_for_clip(clip_path: Path) -> Path:
    return clip_path.with_suffix(f"{clip_path.suffix}.json")


def build_clip_cache_metadata(image_path: Path) -> dict[str, Any]:
    stat = image_path.stat()
    return {
        "quality_version": config.REMOTION_CLIP_QUALITY_VERSION,
        "source_name": image_path.name,
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "width": config.SLIDESHOW_WIDTH,
        "height": config.SLIDESHOW_HEIGHT,
        "fps": config.REMOTION_CLIP_FPS,
        "seconds": config.REMOTION_CLIP_SECONDS,
        "encoder": config.REMOTION_CLIP_VIDEO_ENCODER,
        "nvenc_preset": config.REMOTION_CLIP_NVENC_PRESET,
        "nvenc_cq": str(config.REMOTION_CLIP_CQ),
        "nvenc_tune": config.REMOTION_CLIP_NVENC_TUNE,
        "intermediate_codec": config.REMOTION_INTERMEDIATE_CODEC,
        "prores_profile": config.REMOTION_PRORES_PROFILE,
        "frame_image_format": config.REMOTION_FRAME_IMAGE_FORMAT,
    }


def write_clip_cache_metadata(image_path: Path, clip_path: Path) -> None:
    metadata_path = metadata_path_for_clip(clip_path)
    metadata_path.write_text(
        json.dumps(build_clip_cache_metadata(image_path), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_clip_cache_valid(image_path: Path, clip_path: Path, metadata_path: Path | None = None) -> bool:
    if not clip_path.exists():
        return False
    metadata_path = metadata_path or metadata_path_for_clip(clip_path)
    if not metadata_path.exists():
        return False
    try:
        cached = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    expected = build_clip_cache_metadata(image_path)
    return all(cached.get(key) == value for key, value in expected.items())


def plan_missing_remotion_clips(image_dir: Path, clip_dir: Path, *, force: bool = False) -> list[tuple[Path, Path]]:
    images = sorted(
        path
        for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    planned: list[tuple[Path, Path]] = []
    for image in images:
        clip_path = clip_path_for_image(image, clip_dir)
        if force or not is_clip_cache_valid(image, clip_path):
            planned.append((image, clip_path))
    return planned


def build_single_clip_props(
    *,
    staged_image: str,
    duration_seconds: float,
    width: int,
    height: int,
    fps: int,
) -> dict[str, Any]:
    return build_remotion_props(
        images=[Path(staged_image)],
        duration_seconds=duration_seconds,
        seconds_per_image=duration_seconds,
        width=width,
        height=height,
        fps=fps,
        resolve_images=False,
    )


def build_concat_file_text(clip_paths: list[Path]) -> str:
    lines = [f"file '{_ffmpeg_concat_path(path)}'" for path in clip_paths]
    return "\n".join(lines) + ("\n" if lines else "")


def stage_remotion_images(images: list[Path], public_dir: Path) -> list[str]:
    generated_dir = public_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    staged: list[str] = []
    for index, image in enumerate(images, start=1):
        relative_path = Path("generated") / f"image_{index:03d}{image.suffix.lower()}"
        destination = public_dir / relative_path
        shutil.copyfile(image, destination)
        staged.append(relative_path.as_posix())
    return staged


def build_remotion_render_command(props_path: Path, output_path: Path) -> list[str]:
    command = [
        _resolve_npx(),
        "remotion",
        "render",
        "src/index.jsx",
        "ImageTimeline",
        str(output_path),
        "--props",
        str(props_path),
        "--codec",
        config.REMOTION_INTERMEDIATE_CODEC,
        "--image-format",
        config.REMOTION_FRAME_IMAGE_FORMAT,
        "--overwrite",
    ]
    if config.REMOTION_INTERMEDIATE_CODEC == "prores":
        command.extend(["--prores-profile", config.REMOTION_PRORES_PROFILE])
    return command


def build_nvenc_transcode_command(input_path: Path, output_path: Path) -> list[str]:
    ffmpeg = resolve_command("ffmpeg") or "ffmpeg"
    return [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-an",
        "-c:v",
        config.REMOTION_CLIP_VIDEO_ENCODER,
        "-preset",
        config.REMOTION_CLIP_NVENC_PRESET,
        "-tune",
        config.REMOTION_CLIP_NVENC_TUNE,
        "-cq",
        str(config.REMOTION_CLIP_CQ),
        "-rc-lookahead",
        str(config.REMOTION_CLIP_NVENC_RC_LOOKAHEAD),
        "-spatial-aq",
        str(config.REMOTION_CLIP_NVENC_SPATIAL_AQ),
        "-temporal-aq",
        str(config.REMOTION_CLIP_NVENC_TEMPORAL_AQ),
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def render_single_remotion_clip(image_path: Path, clip_path: Path) -> Path:
    require_command("ffmpeg")
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    staged_image = stage_remotion_images([image_path], REMOTION_DIR / "public")[0]
    props = build_single_clip_props(
        staged_image=staged_image,
        duration_seconds=float(config.REMOTION_CLIP_SECONDS),
        width=config.SLIDESHOW_WIDTH,
        height=config.SLIDESHOW_HEIGHT,
        fps=config.REMOTION_CLIP_FPS,
    )
    props_path = path_from_root(config.TEMP_DIR, f"{image_path.stem}_remotion_clip_props.json")
    intermediate_path = path_from_root(config.TEMP_DIR, f"{image_path.stem}_remotion_clip_intermediate.mov")
    write_props_file(props_path, props)
    _run(build_remotion_render_command(props_path, intermediate_path), REMOTION_DIR)
    _run(build_nvenc_transcode_command(intermediate_path, clip_path), path_from_root())
    write_clip_cache_metadata(image_path, clip_path)
    if intermediate_path.exists():
        intermediate_path.unlink()
    return clip_path


def pre_render_missing_remotion_clips(*, force: bool = False) -> list[Path]:
    image_dir = path_from_root(config.UNIVERSE_PICTURE_DIR)
    clip_dir = path_from_root(config.REMOTION_CLIP_DIR)
    planned = plan_missing_remotion_clips(image_dir, clip_dir, force=force)
    rendered: list[Path] = []
    for image_path, clip_path in planned:
        rendered.append(render_single_remotion_clip(image_path, clip_path))
    return rendered


def render_remotion_gpu_test(duration_seconds: float = 10.0, image_count: int = 3) -> Path:
    require_command("ffmpeg")
    image_dir = path_from_root(config.UNIVERSE_PICTURE_DIR)
    images = select_remotion_images(image_dir, image_count)
    staged_images = stage_remotion_images(images, REMOTION_DIR / "public")
    props = build_remotion_props(
        images=[Path(image) for image in staged_images],
        duration_seconds=duration_seconds,
        seconds_per_image=max(duration_seconds / len(images), 1.0),
        width=config.SLIDESHOW_WIDTH,
        height=config.SLIDESHOW_HEIGHT,
        fps=30,
        resolve_images=False,
    )
    write_props_file(PROPS_PATH, props)

    INTERMEDIATE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FINAL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _run(build_remotion_render_command(PROPS_PATH, INTERMEDIATE_OUTPUT), REMOTION_DIR)
    _run(build_nvenc_transcode_command(INTERMEDIATE_OUTPUT, FINAL_OUTPUT), path_from_root())
    return FINAL_OUTPUT


def render_remotion_one_minute_test() -> Path:
    seconds_per_image = float(config.SLIDESHOW_IMAGE_SECONDS)
    image_count = 2
    return render_remotion_gpu_test(
        duration_seconds=seconds_per_image * image_count,
        image_count=image_count,
    )


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise WorkflowError(result.stderr.strip() or result.stdout.strip())


def _resolve_npx() -> str:
    executable = "npx.cmd" if os.name == "nt" else "npx"
    resolved = shutil.which(executable)
    if resolved:
        return resolved
    fallback = shutil.which("npx")
    if fallback:
        return fallback
    raise WorkflowError("Cannot find npx. Install Node.js/npm before running the Remotion test.")


def _ffmpeg_concat_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "'\\''")
