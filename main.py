"""Chinese MP3 to English ASMR universe-picture video workflow."""

from __future__ import annotations

import argparse
import sys

import config
from monitor_full_run import run_monitored_workflow
from utils import (
    ensure_directories,
    load_env_file,
    path_from_root,
    setup_logging,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    load_env_file()
    setup_logging()
    ensure_directories()
    args = parse_args(sys.argv[1:])

    metrics = run_monitored_workflow(force_translation=args.force_translation)
    print("\nWorkflow completed." if metrics.success else "\nWorkflow failed.")
    print(f"Run id: {metrics.run_id}")
    print(f"Rendered videos: {1 if metrics.success and metrics.output_path else 0}")
    print(f"Failed audio files: {0 if metrics.success else 1}")
    if metrics.output_path:
        print("Output files:")
        print(f"- {metrics.output_path}")
    if metrics.error:
        print(f"Error: {metrics.error}")
    print(f"Summary: {metrics.report_paths.get('summary', '')}")
    print(f"Human report: {metrics.report_paths.get('report', path_from_root(config.LOG_DIR, 'resource_runs'))}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render English ASMR universe videos from Chinese MP3 files.")
    parser.add_argument(
        "--force-translation",
        action="store_true",
        help="Rebuild English subtitles with Gemini even when an existing *_en.srt file is fresh.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
