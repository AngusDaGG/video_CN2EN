"""Render a GPU-encoded Remotion visual test from the image library."""

from __future__ import annotations

import argparse
import logging

from remotion_renderer import render_remotion_gpu_test, render_remotion_one_minute_test
from utils import WorkflowError, ensure_directories, load_env_file, setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Remotion image-animation GPU test.")
    parser.add_argument("--seconds", type=float, default=10.0, help="Total test duration in seconds.")
    parser.add_argument("--images", type=int, default=3, help="Number of images to use from the image library.")
    parser.add_argument(
        "--one-minute",
        action="store_true",
        help="Render the planned 1-minute test using 2 images at 30 seconds each.",
    )
    args = parser.parse_args()

    load_env_file()
    setup_logging()
    ensure_directories()

    try:
        if args.one_minute:
            output_path = render_remotion_one_minute_test()
        else:
            output_path = render_remotion_gpu_test(duration_seconds=args.seconds, image_count=args.images)
    except WorkflowError as exc:
        logging.error("%s", exc)
        return 1

    logging.info("Remotion GPU test video created: %s", output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
