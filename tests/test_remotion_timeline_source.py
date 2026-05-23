from __future__ import annotations

import unittest
from pathlib import Path


class RemotionTimelineSourceTests(unittest.TestCase):
    def test_sequence_image_uses_relative_frame_without_subtracting_start_frame(self) -> None:
        source = Path("remotion/src/index.jsx").read_text(encoding="utf-8")

        self.assertNotIn("const localFrame = frame - startFrame;", source)
        self.assertNotIn("startFrame={startFrame}", source)


if __name__ == "__main__":
    unittest.main()
