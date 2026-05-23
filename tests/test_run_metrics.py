from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from run_metrics import ResourceSampler, RunMetrics


class RunMetricsTests(unittest.TestCase):
    def test_run_metrics_writes_summary_steps_samples_and_api_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            metrics = RunMetrics(run_id="test-run", output_dir=output_dir)
            metrics.start()
            with metrics.step("translation"):
                pass
            metrics.record_api_usage(
                provider="gemini",
                operation="subtitle_translation",
                model="gemini-test",
                prompt_tokens=10,
                candidates_tokens=5,
                total_tokens=15,
            )
            metrics.record_api_usage(
                provider="google_tts",
                operation="voiceover",
                model="test-voice",
                characters=200,
                requests=2,
            )
            metrics.add_sample(
                {
                    "timestamp": "now",
                    "cpu_percent": 12.5,
                    "gpu_percent": 80,
                    "gpu_encoder_percent": 15,
                }
            )
            metrics.finish(
                success=True,
                output_path=Path("output.mp4"),
                output_metadata={
                    "size_bytes": 1024,
                    "format": {"duration": "30.0"},
                    "streams": [
                        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "30/1"},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                },
            )

            paths = metrics.write_reports()

            self.assertTrue(paths["summary"].exists())
            self.assertTrue(paths["steps"].exists())
            self.assertTrue(paths["samples"].exists())
            self.assertTrue(paths["api_usage"].exists())
            self.assertTrue(paths["report"].exists())

            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
            self.assertTrue(summary["success"])
            self.assertEqual(summary["output_path"], "output.mp4")
            self.assertEqual(summary["api_totals"]["gemini_total_tokens"], 15)

            with paths["api_usage"].open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["provider"], "gemini")
            self.assertEqual(rows[0]["total_tokens"], "15")

            report = paths["report"].read_text(encoding="utf-8")
            self.assertIn("耗時重點", report)
            self.assertIn("API 使用量", report)
            self.assertIn("資源摘要", report)
            self.assertIn("輸出影片", report)
            self.assertIn("STT CUDA 診斷", report)

    def test_resource_sampler_does_not_fail_when_sample_function_errors(self) -> None:
        sampler = ResourceSampler(sample_interval_seconds=0.01, sample_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        sampler.start()
        sampler.stop()

        self.assertGreaterEqual(len(sampler.samples), 1)
        self.assertIn("error", sampler.samples[0])


if __name__ == "__main__":
    unittest.main()
