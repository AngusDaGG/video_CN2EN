from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import monitor_full_run


class MonitorFullRunTests(unittest.TestCase):
    def test_parse_args_defaults_to_one_second_sample_interval(self) -> None:
        args = monitor_full_run.parse_args([])

        self.assertEqual(args.sample_interval, 1.0)

    def test_help_does_not_expose_force_flags(self) -> None:
        help_text = monitor_full_run.build_arg_parser().format_help()

        self.assertNotIn("force", help_text.lower())

    def test_force_flags_are_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            monitor_full_run.parse_args(["--force-all"])

    def test_process_audio_with_metrics_uses_default_cache_policy(self) -> None:
        audio = Mock()
        audio.stem = "sample"
        audio.name = "sample.mp3"
        metrics = Mock()

        step_context = Mock()
        step_context.__enter__ = Mock(return_value=None)
        step_context.__exit__ = Mock(return_value=None)
        metrics.step.return_value = step_context

        with (
            patch("monitor_full_run.run_stt", return_value="zh.srt") as run_stt,
            patch("monitor_full_run.run_translation", return_value="en.srt") as run_translation,
            patch("monitor_full_run.write_translation_review", return_value="review.csv"),
            patch("monitor_full_run.translate_title_to_english", return_value="Sample Video") as translate_title,
            patch("monitor_full_run.run_tts", return_value="voice.wav") as run_tts,
            patch("monitor_full_run.postprocess_voiceover", return_value="asmr.wav") as postprocess,
            patch("monitor_full_run.render_universe_video", return_value="video.mp4") as render,
            patch("monitor_full_run.safe_stem", return_value="sample"),
        ):
            output = monitor_full_run.process_audio_with_metrics(audio, metrics)

        self.assertEqual(output, "video.mp4")
        run_stt.assert_called_once_with(audio)
        run_translation.assert_called_once_with("zh.srt", "sample", force=False, metrics=metrics)
        translate_title.assert_called_once_with("sample", "sample", metrics=metrics)
        run_tts.assert_called_once_with("en.srt", "sample", english_video_title="Sample Video", metrics=metrics)
        postprocess.assert_called_once_with("voice.wav", "sample")
        render.assert_called_once_with("asmr.wav", "sample")

    def test_run_monitored_workflow_stages_and_finishes_successful_audio(self) -> None:
        audio = Mock()
        audio.name = "sample.mp3"
        output = Mock()
        output.exists.return_value = True
        output.stat.return_value.st_size = 123

        with (
            patch("monitor_full_run.require_command"),
            patch("monitor_full_run.stage_next_input_audio", return_value=audio) as stage,
            patch("monitor_full_run.find_input_audio", return_value=[audio]),
            patch("monitor_full_run.process_audio_with_metrics", return_value=output) as process,
            patch("monitor_full_run.finish_input_audio") as finish,
            patch("monitor_full_run.collect_output_metadata", return_value={"size_bytes": 123}),
            patch("monitor_full_run.ResourceSampler") as sampler_class,
            patch("monitor_full_run.RunMetrics") as metrics_class,
        ):
            sampler = Mock()
            sampler.samples = []
            sampler_class.return_value = sampler
            metrics = Mock()
            metrics.write_reports.return_value = {}
            metrics_class.return_value = metrics

            result = monitor_full_run.run_monitored_workflow(force_translation=True)

        self.assertEqual(result, metrics)
        stage.assert_called_once_with()
        process.assert_called_once_with(audio, metrics, force_translation=True)
        finish.assert_called_once_with(audio)
        metrics.finish.assert_called_once_with(success=True, output_path=output, output_metadata={"size_bytes": 123})

    def test_run_monitored_workflow_keeps_audio_in_input_when_processing_fails(self) -> None:
        audio = Mock()
        audio.name = "sample.mp3"

        with (
            patch("monitor_full_run.require_command"),
            patch("monitor_full_run.stage_next_input_audio", return_value=audio),
            patch("monitor_full_run.find_input_audio", return_value=[audio]),
            patch("monitor_full_run.process_audio_with_metrics", side_effect=RuntimeError("boom")),
            patch("monitor_full_run.finish_input_audio") as finish,
            patch("monitor_full_run.ResourceSampler") as sampler_class,
            patch("monitor_full_run.RunMetrics") as metrics_class,
        ):
            sampler = Mock()
            sampler.samples = []
            sampler_class.return_value = sampler
            metrics = Mock()
            metrics.write_reports.return_value = {}
            metrics_class.return_value = metrics

            result = monitor_full_run.run_monitored_workflow()

        self.assertEqual(result, metrics)
        finish.assert_not_called()
        metrics.finish.assert_called_once_with(success=False, output_path=None, error="boom")

    def test_run_monitored_workflow_reports_when_input_and_lining_are_empty(self) -> None:
        with (
            patch("monitor_full_run.require_command"),
            patch("monitor_full_run.stage_next_input_audio", return_value=None),
            patch("monitor_full_run.find_input_audio", return_value=[]),
            patch("monitor_full_run.ResourceSampler") as sampler_class,
            patch("monitor_full_run.RunMetrics") as metrics_class,
        ):
            sampler = Mock()
            sampler.samples = []
            sampler_class.return_value = sampler
            metrics = Mock()
            metrics.write_reports.return_value = {}
            metrics_class.return_value = metrics

            monitor_full_run.run_monitored_workflow()

        metrics.finish.assert_called_once_with(
            success=False,
            output_path=None,
            error="No .mp3 files found in input_audio/ or input_audio_lining/.",
        )


if __name__ == "__main__":
    unittest.main()
