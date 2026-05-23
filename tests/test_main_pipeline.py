from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import main


class MainPipelineTests(unittest.TestCase):
    def test_main_runs_monitored_workflow_by_default(self) -> None:
        metrics = Mock()
        metrics.success = True
        metrics.run_id = "run-1"
        metrics.output_path = "video.mp4"
        metrics.error = ""
        metrics.report_paths = {"summary": "summary.json", "report": "report.md"}

        with (
            patch("main.load_env_file"),
            patch("main.setup_logging"),
            patch("main.ensure_directories"),
            patch("main.run_monitored_workflow", return_value=metrics) as run_monitored_workflow,
            patch("main.sys.argv", ["main.py"]),
        ):
            main.main()

        run_monitored_workflow.assert_called_once_with(force_translation=False)

    def test_main_passes_force_translation_to_monitored_workflow(self) -> None:
        metrics = Mock()
        metrics.success = True
        metrics.run_id = "run-1"
        metrics.output_path = "video.mp4"
        metrics.error = ""
        metrics.report_paths = {"summary": "summary.json", "report": "report.md"}

        with (
            patch("main.load_env_file"),
            patch("main.setup_logging"),
            patch("main.ensure_directories"),
            patch("main.run_monitored_workflow", return_value=metrics) as run_monitored_workflow,
            patch("main.sys.argv", ["main.py", "--force-translation"]),
        ):
            main.main()

        run_monitored_workflow.assert_called_once_with(force_translation=True)


if __name__ == "__main__":
    unittest.main()
