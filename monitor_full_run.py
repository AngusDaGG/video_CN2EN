"""Run the full workflow while recording resource and API usage."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

import config
from gemini_translate import run_translation, translate_title_to_english
from google_cloud_tts import run_tts
from local_stt import run_stt
from run_metrics import ResourceSampler, RunMetrics
from slideshow_video import postprocess_voiceover, render_universe_video
from translation_review import write_translation_review
from utils import (
    WorkflowError,
    ensure_directories,
    find_input_audio,
    finish_input_audio,
    load_env_file,
    path_from_root,
    require_command,
    safe_stem,
    setup_logging,
    resolve_command,
    stage_next_input_audio,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the video workflow with resource and API monitoring.")
    parser.add_argument("--sample-interval", type=float, default=1.0, help="Resource sample interval in seconds.")
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)


def process_audio_with_metrics(audio_path: Path, metrics: RunMetrics, *, force_translation: bool = False) -> Path:
    logging.info("Starting monitored workflow: %s", audio_path.name)

    with metrics.step("stt"):
        chinese_srt = run_stt(audio_path)

    with metrics.step("gemini_subtitle_translation"):
        english_srt = run_translation(
            chinese_srt,
            audio_path.stem,
            force=force_translation,
            metrics=metrics,
        )

    with metrics.step("translation_review"):
        review_path = write_translation_review(chinese_srt, english_srt, audio_path.stem)
        logging.info("Review report: %s", review_path)

    with metrics.step("gemini_title_translation"):
        english_title = translate_title_to_english(
            audio_path.stem,
            safe_stem(audio_path),
            metrics=metrics,
        )

    with metrics.step("google_cloud_tts"):
        english_voiceover = run_tts(
            english_srt,
            audio_path.stem,
            english_video_title=english_title,
            metrics=metrics,
        )

    with metrics.step("asmr_postprocess"):
        asmr_voiceover = postprocess_voiceover(english_voiceover, audio_path.stem)

    with metrics.step("final_video_render"):
        return render_universe_video(asmr_voiceover, audio_path.stem)


def run_monitored_workflow(sample_interval: float = 1.0, *, force_translation: bool = False) -> RunMetrics:
    metrics = RunMetrics(output_dir=path_from_root(config.LOG_DIR, "resource_runs"))
    sampler = ResourceSampler(sample_interval_seconds=sample_interval)
    metrics.start()
    sampler.start()
    output_path: Path | None = None
    error = ""
    try:
        require_command("ffmpeg")
        require_command("ffprobe")

        stage_next_input_audio()
        audio_files = find_input_audio()
        if not audio_files:
            raise WorkflowError("No .mp3 files found in input_audio/ or input_audio_lining/.")
        completed = []
        for audio_path in audio_files:
            completed.append(process_audio_with_metrics(audio_path, metrics, force_translation=force_translation))
            finish_input_audio(audio_path)
        output_path = completed[-1] if completed else None
        metrics.finish(
            success=True,
            output_path=output_path,
            output_metadata=collect_output_metadata(output_path) if output_path else {},
        )
    except Exception as exc:
        error = str(exc)
        metrics.finish(success=False, output_path=output_path, error=error)
    finally:
        sampler.stop()
        for sample in sampler.samples:
            metrics.add_sample(sample)
        paths = metrics.write_reports()
        logging.info("Resource reports written: %s", ", ".join(str(path) for path in paths.values()))
        if error:
            logging.error("Monitored workflow failed: %s", error)
    return metrics


def collect_output_metadata(output_path: Path) -> dict[str, object]:
    metadata: dict[str, object] = {
        "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
    }
    ffprobe = resolve_command("ffprobe") or "ffprobe"
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        metadata["ffprobe_error"] = result.stderr.strip()
        return metadata
    try:
        metadata.update(json.loads(result.stdout))
    except json.JSONDecodeError:
        metadata["ffprobe_error"] = "Could not parse ffprobe JSON output."
    return metadata


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    load_env_file()
    setup_logging()
    ensure_directories()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    metrics = run_monitored_workflow(sample_interval=args.sample_interval)
    if not metrics.success:
        print(f"Monitored workflow failed: {metrics.error}")
        print(f"Run id: {metrics.run_id}")
        print(f"Summary: {metrics.report_paths.get('summary', '')}")
        print(f"Human report: {metrics.report_paths.get('report', '')}")
        return 1

    print("Monitored workflow completed.")
    print(f"Run id: {metrics.run_id}")
    print(f"Output: {metrics.output_path}")
    print(f"Summary: {metrics.report_paths.get('summary', '')}")
    print(f"Human report: {metrics.report_paths.get('report', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
