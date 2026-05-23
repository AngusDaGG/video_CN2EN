from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import remotion_renderer


class RemotionRendererTests(unittest.TestCase):
    def test_select_images_limits_count_and_uses_supported_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_dir = Path(temp_dir)
            supported = [
                image_dir / "a.png",
                image_dir / "b.jpg",
                image_dir / "c.webp",
            ]
            unsupported = image_dir / "notes.txt"
            for path in [*supported, unsupported]:
                path.write_text("x", encoding="utf-8")

            selected = remotion_renderer.select_remotion_images(image_dir, 2)

            self.assertEqual([path.name for path in selected], ["a.png", "b.jpg"])

    def test_build_props_uses_absolute_image_paths_and_expected_timing(self) -> None:
        images = [Path("image-a.png"), Path("nested/image-b.jpg")]

        props = remotion_renderer.build_remotion_props(
            images=images,
            duration_seconds=10,
            seconds_per_image=5,
            width=1920,
            height=1080,
            fps=30,
        )

        self.assertEqual(props["durationSeconds"], 10)
        self.assertEqual(props["secondsPerImage"], 5)
        self.assertEqual(props["width"], 1920)
        self.assertEqual(props["height"], 1080)
        self.assertEqual(props["fps"], 30)
        self.assertTrue(Path(props["images"][0]).is_absolute())
        self.assertTrue(Path(props["images"][1]).is_absolute())

    def test_write_props_file_creates_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "props.json"
            props = {"images": ["D:/image.png"], "durationSeconds": 10}

            remotion_renderer.write_props_file(output_path, props)

            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), props)

    def test_stage_remotion_images_copies_assets_and_returns_static_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            public_dir = Path(temp_dir) / "public"
            source_dir.mkdir()
            first = source_dir / "space image.png"
            second = source_dir / "moon.jpg"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")

            staged = remotion_renderer.stage_remotion_images([first, second], public_dir)

            self.assertEqual(staged, ["generated/image_001.png", "generated/image_002.jpg"])
            self.assertEqual((public_dir / "generated" / "image_001.png").read_text(encoding="utf-8"), "first")
            self.assertEqual((public_dir / "generated" / "image_002.jpg").read_text(encoding="utf-8"), "second")

    def test_build_props_can_keep_static_asset_paths_relative(self) -> None:
        props = remotion_renderer.build_remotion_props(
            images=[Path("generated/image_001.png")],
            duration_seconds=10,
            seconds_per_image=10,
            width=1920,
            height=1080,
            fps=30,
            resolve_images=False,
        )

        self.assertEqual(props["images"], ["generated/image_001.png"])

    def test_build_nvenc_command_uses_h264_nvenc_settings(self) -> None:
        command = remotion_renderer.build_nvenc_transcode_command(
            input_path=Path("temp/intermediate.mp4"),
            output_path=Path("output/final.mp4"),
        )

        self.assertIn("h264_nvenc", command)
        self.assertIn("-preset", command)
        self.assertIn("p7", command)
        self.assertIn("-tune", command)
        self.assertIn("hq", command)
        self.assertIn("-cq", command)
        self.assertIn("15", command)
        self.assertIn("-rc-lookahead", command)
        self.assertIn("-spatial-aq", command)
        self.assertIn("-temporal-aq", command)
        self.assertEqual(Path(command[-1]), Path("output/final.mp4"))

    def test_build_remotion_render_command_uses_png_prores_hq_intermediate(self) -> None:
        command = remotion_renderer.build_remotion_render_command(
            props_path=Path("temp/props.json"),
            output_path=Path("temp/intermediate.mov"),
        )

        self.assertIn("--image-format", command)
        self.assertIn("png", command)
        self.assertIn("--codec", command)
        self.assertIn("prores", command)
        self.assertIn("--prores-profile", command)
        self.assertIn("hq", command)

    def test_clip_path_uses_source_image_stem(self) -> None:
        clip_path = remotion_renderer.clip_path_for_image(
            Path("universe picture/space view.png"),
            Path("remotion_clips"),
        )

        self.assertEqual(clip_path, Path("remotion_clips/space view.mp4"))

    def test_missing_clip_plan_rebuilds_existing_clip_without_valid_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_dir = root / "images"
            clip_dir = root / "clips"
            image_dir.mkdir()
            clip_dir.mkdir()
            existing_image = image_dir / "existing.png"
            new_image = image_dir / "new.png"
            existing_image.write_text("existing", encoding="utf-8")
            new_image.write_text("new", encoding="utf-8")
            (clip_dir / "existing.mp4").write_text("clip", encoding="utf-8")

            plan = remotion_renderer.plan_missing_remotion_clips(image_dir, clip_dir, force=False)

            self.assertEqual(plan, [(existing_image, clip_dir / "existing.mp4"), (new_image, clip_dir / "new.mp4")])

    def test_missing_clip_plan_skips_existing_clip_when_metadata_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_dir = root / "images"
            clip_dir = root / "clips"
            image_dir.mkdir()
            clip_dir.mkdir()
            existing_image = image_dir / "existing.png"
            new_image = image_dir / "new.png"
            existing_image.write_text("existing", encoding="utf-8")
            new_image.write_text("new", encoding="utf-8")
            existing_clip = clip_dir / "existing.mp4"
            existing_clip.write_text("clip", encoding="utf-8")
            remotion_renderer.write_clip_cache_metadata(existing_image, existing_clip)

            plan = remotion_renderer.plan_missing_remotion_clips(image_dir, clip_dir, force=False)

            self.assertEqual(plan, [(new_image, clip_dir / "new.mp4")])

    def test_force_clip_plan_includes_all_supported_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_dir = root / "images"
            clip_dir = root / "clips"
            image_dir.mkdir()
            clip_dir.mkdir()
            first = image_dir / "first.png"
            second = image_dir / "second.jpg"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            (clip_dir / "first.mp4").write_text("clip", encoding="utf-8")

            plan = remotion_renderer.plan_missing_remotion_clips(image_dir, clip_dir, force=True)

            self.assertEqual(plan, [(first, clip_dir / "first.mp4"), (second, clip_dir / "second.mp4")])

    def test_build_single_clip_props_uses_one_image_and_clip_duration(self) -> None:
        props = remotion_renderer.build_single_clip_props(
            staged_image="generated/clip_source.png",
            duration_seconds=30,
            width=1920,
            height=1080,
            fps=30,
        )

        self.assertEqual(props["images"], ["generated/clip_source.png"])
        self.assertEqual(props["durationSeconds"], 30)
        self.assertEqual(props["secondsPerImage"], 30)

    def test_build_concat_file_text_uses_existing_clip_paths(self) -> None:
        text = remotion_renderer.build_concat_file_text([Path("clips/a.mp4"), Path("clips/b.mp4")])

        self.assertIn("file '", text)
        self.assertIn("clips/a.mp4", text.replace("\\", "/"))
        self.assertIn("clips/b.mp4", text.replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
