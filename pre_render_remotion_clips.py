"""Pre-render missing Remotion image clips for fast FFmpeg-only assembly."""

from __future__ import annotations

import argparse
import logging

import config
from remotion_renderer import (
    plan_missing_remotion_clips,
    pre_render_missing_remotion_clips,
)
from utils import WorkflowError, ensure_directories, load_env_file, path_from_root, setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-render missing Remotion image clips.")
    parser.add_argument("--force", action="store_true", help="Rebuild all clips even when same-name MP4 files exist.")
    args = parser.parse_args()

    load_env_file()
    setup_logging()
    ensure_directories()
    path_from_root(config.REMOTION_CLIP_DIR).mkdir(parents=True, exist_ok=True)

    image_dir = path_from_root(config.UNIVERSE_PICTURE_DIR)
    clip_dir = path_from_root(config.REMOTION_CLIP_DIR)
    planned = plan_missing_remotion_clips(image_dir, clip_dir, force=args.force)
    if not planned:
        message = "All Remotion clips already exist. Nothing to render."
        logging.info(message)
        print(message)
        return 0

    print(f"Rendering {len(planned)} Remotion clip(s).")
    for image_path, clip_path in planned:
        print(f"- {image_path.name} -> {clip_path.name}")

    try:
        rendered = pre_render_missing_remotion_clips(force=args.force)
    except WorkflowError as exc:
        logging.error("%s", exc)
        print(f"Could not render Remotion clips: {exc}")
        return 1

    print("Rendered clips:")
    for path in rendered:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
