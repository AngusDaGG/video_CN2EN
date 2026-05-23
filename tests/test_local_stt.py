from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from local_stt import build_cuda_runtime_help, discover_nvidia_runtime_dll_dirs, ensure_nvidia_runtime_dll_paths, transcribe_blocks


class FakeSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


class FailingCudaModel:
    def __init__(self, _model_path: str, *, device: str, compute_type: str) -> None:
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, _audio_path: str, *, language: str, vad_filter: bool):
        def raise_when_iterated():
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            yield

        return raise_when_iterated(), None


class CpuModel:
    def __init__(self, _model_path: str, *, device: str, compute_type: str) -> None:
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, _audio_path: str, *, language: str, vad_filter: bool):
        return iter([FakeSegment(0.0, 1.25, "  \u4f60\u597d  ")]), None


class LocalSttTests(unittest.TestCase):
    def test_transcribe_blocks_formats_segment_times(self) -> None:
        blocks = transcribe_blocks(
            audio_path=Path("audio.mp3"),
            model_path=Path("model"),
            device="cpu",
            compute_type="int8",
            model_class=CpuModel,
        )

        self.assertEqual(blocks[0].start, "00:00:00,000")
        self.assertEqual(blocks[0].end, "00:00:01,250")
        self.assertEqual(blocks[0].text, "\u4f60\u597d")

    def test_transcribe_blocks_falls_back_to_cpu_when_cuda_runtime_is_missing(self) -> None:
        calls = []

        class Model:
            def __new__(cls, model_path: str, *, device: str, compute_type: str):
                calls.append((device, compute_type))
                if device == "cuda":
                    return FailingCudaModel(model_path, device=device, compute_type=compute_type)
                return CpuModel(model_path, device=device, compute_type=compute_type)

        blocks = transcribe_blocks(
            audio_path=Path("audio.mp3"),
            model_path=Path("model"),
            device="cuda",
            compute_type="float16",
            model_class=Model,
        )

        self.assertEqual(calls, [("cuda", "float16"), ("cpu", "int8")])
        self.assertEqual(blocks[0].text, "\u4f60\u597d")

    def test_cuda_runtime_help_names_required_windows_dlls(self) -> None:
        message = build_cuda_runtime_help(RuntimeError("Library cublas64_12.dll is not found"))

        self.assertIn("cublas64_12.dll", message)
        self.assertIn("cudnn64_9.dll", message)
        self.assertIn("CUDA 12", message)
        self.assertIn("cuDNN 9", message)

    def test_discover_nvidia_runtime_dll_dirs_finds_pip_wheel_bins(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cublas_bin = root / "cublas" / "bin"
            cudnn_bin = root / "cudnn" / "bin"
            cublas_bin.mkdir(parents=True)
            cudnn_bin.mkdir(parents=True)
            (cublas_bin / "cublas64_12.dll").write_text("", encoding="utf-8")
            (cudnn_bin / "cudnn64_9.dll").write_text("", encoding="utf-8")

            spec = SimpleNamespace(submodule_search_locations=[str(root)])
            with patch("local_stt.importlib.util.find_spec", return_value=spec):
                dll_dirs = discover_nvidia_runtime_dll_dirs()

        self.assertEqual(dll_dirs, [str(cublas_bin), str(cudnn_bin)])

    def test_ensure_nvidia_runtime_dll_paths_adds_discovered_dirs(self) -> None:
        with (
            patch("local_stt.os.name", "nt"),
            patch("local_stt.discover_nvidia_runtime_dll_dirs", return_value=[r"C:\cuda\bin"]),
            patch("local_stt.os.add_dll_directory", Mock(return_value=object())) as add_dll_directory,
            patch.dict("local_stt.os.environ", {"PATH": r"C:\Windows"}, clear=True),
            patch("local_stt._NVIDIA_DLL_PATHS_ADDED", set()),
            patch("local_stt._NVIDIA_DLL_HANDLES", []),
        ):
            dll_dirs = ensure_nvidia_runtime_dll_paths()

        self.assertEqual(dll_dirs, [r"C:\cuda\bin"])
        add_dll_directory.assert_called_once_with(r"C:\cuda\bin")


if __name__ == "__main__":
    unittest.main()
