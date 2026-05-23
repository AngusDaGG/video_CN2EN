"""Generate Chinese subtitles with local faster-whisper."""

from __future__ import annotations

import logging
import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

import config
from srt_utils import SubtitleBlock, parse_srt, remove_unwanted_chinese_subtitle_blocks, write_srt
from utils import WorkflowError, path_from_root, safe_stem


_NVIDIA_DLL_HANDLES: list[Any] = []
_NVIDIA_DLL_PATHS_ADDED: set[str] = set()


def run_stt(audio_path: Path, *, force: bool = False) -> Path:
    output_path = path_from_root(config.SUBTITLE_DIR, f"{safe_stem(audio_path)}_zh.srt")
    if not force and _is_fresh(output_path, audio_path):
        clean_chinese_subtitle_file(output_path)
        logging.info("Reusing existing Chinese subtitles: %s", output_path)
        return output_path
    if force and output_path.exists():
        logging.info("Force rebuilding Chinese subtitles: %s", output_path)

    model_path = Path(config.FASTER_WHISPER_MODEL_PATH)
    if not model_path.exists():
        raise WorkflowError(f"faster-whisper model was not found at {model_path}.")

    try:
        ensure_nvidia_runtime_dll_paths()
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise WorkflowError("faster-whisper is not installed. Run: pip install -r requirements.txt") from exc

    logging.info("Running faster-whisper STT for %s", audio_path.name)
    blocks = transcribe_blocks(
        audio_path=audio_path,
        model_path=model_path,
        device=config.FASTER_WHISPER_DEVICE,
        compute_type=config.FASTER_WHISPER_COMPUTE_TYPE,
        model_class=WhisperModel,
    )
    if not blocks:
        raise WorkflowError(f"faster-whisper did not produce any subtitle text for {audio_path.name}.")
    write_srt(output_path, remove_unwanted_chinese_subtitle_blocks(blocks))
    return output_path


def clean_chinese_subtitle_file(srt_path: Path) -> None:
    blocks = parse_srt(srt_path)
    cleaned = remove_unwanted_chinese_subtitle_blocks(blocks)
    if cleaned != blocks:
        write_srt(srt_path, cleaned)
        logging.info("Removed unwanted Chinese subtitle branding line in %s", srt_path)


def transcribe_blocks(
    *,
    audio_path: Path,
    model_path: Path,
    device: str,
    compute_type: str,
    model_class: object,
) -> list[SubtitleBlock]:
    try:
        return _transcribe_blocks_once(audio_path, model_path, device, compute_type, model_class)
    except RuntimeError as exc:
        if device != "cuda" or not _is_cuda_runtime_error(exc):
            raise
        logging.warning(
            "CUDA faster-whisper failed, retrying on CPU with int8: %s\n%s",
            exc,
            build_cuda_runtime_help(exc),
        )
        return _transcribe_blocks_once(audio_path, model_path, "cpu", "int8", model_class)


def _transcribe_blocks_once(
    audio_path: Path,
    model_path: Path,
    device: str,
    compute_type: str,
    model_class: object,
) -> list[SubtitleBlock]:
    model = model_class(str(model_path), device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio_path),
        language=config.FASTER_WHISPER_LANGUAGE,
        vad_filter=config.FASTER_WHISPER_VAD_FILTER,
    )
    blocks: list[SubtitleBlock] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.text.strip()
        if not text:
            continue
        blocks.append(
            SubtitleBlock(
                index=index,
                start=_seconds_to_srt_time(segment.start),
                end=_seconds_to_srt_time(segment.end),
                text=text,
            )
        )
    return blocks


def _seconds_to_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    secs = milliseconds // 1000
    millis = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _is_cuda_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return "cuda" in message or "cublas" in message or "cudnn" in message


def build_cuda_runtime_help(exc: RuntimeError) -> str:
    diagnostics = collect_cuda_runtime_diagnostics()
    return (
        "GPU STT diagnostic: faster-whisper on CUDA needs CUDA 12 cuBLAS and cuDNN 9 runtime DLLs. "
        f"Current error: {exc}. "
        f"cublas64_12.dll={diagnostics['cublas64_12.dll']}; "
        f"cudnn64_9.dll={diagnostics['cudnn64_9.dll']}; "
        f"ctranslate2_cuda_devices={diagnostics['ctranslate2_cuda_devices']}. "
        "Install the NVIDIA CUDA 12/cuDNN 9 pip wheels or add their DLL folders to PATH to keep STT on the NVIDIA GPU."
    )


def ensure_nvidia_runtime_dll_paths() -> list[str]:
    if os.name != "nt":
        return []
    dll_dirs = discover_nvidia_runtime_dll_dirs()
    for dll_dir in dll_dirs:
        if dll_dir in _NVIDIA_DLL_PATHS_ADDED:
            continue
        if hasattr(os, "add_dll_directory"):
            _NVIDIA_DLL_HANDLES.append(os.add_dll_directory(dll_dir))
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        if dll_dir not in path_entries:
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        _NVIDIA_DLL_PATHS_ADDED.add(dll_dir)
    return dll_dirs


def discover_nvidia_runtime_dll_dirs() -> list[str]:
    spec = importlib.util.find_spec("nvidia")
    search_locations = getattr(spec, "submodule_search_locations", None) if spec else None
    if not search_locations:
        return []
    required_dlls = {
        "cublas": "cublas64_12.dll",
        "cudnn": "cudnn64_9.dll",
    }
    dll_dirs: list[str] = []
    for package_root in search_locations:
        root = Path(package_root)
        for package_name, dll_name in required_dlls.items():
            dll_dir = root / package_name / "bin"
            if (dll_dir / dll_name).exists():
                dll_dirs.append(str(dll_dir))
    return dll_dirs


def collect_cuda_runtime_diagnostics() -> dict[str, Any]:
    ensure_nvidia_runtime_dll_paths()
    diagnostics: dict[str, Any] = {
        "cublas64_12.dll": find_runtime_dll("cublas64_12.dll") or "missing",
        "cudnn64_9.dll": find_runtime_dll("cudnn64_9.dll") or "missing",
        "ctranslate2_cuda_devices": "unknown",
    }
    try:
        import ctranslate2

        diagnostics["ctranslate2_cuda_devices"] = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        diagnostics["ctranslate2_cuda_devices"] = f"unavailable: {exc}"
    return diagnostics


def find_runtime_dll(dll_name: str) -> str:
    found = shutil.which(dll_name)
    if found:
        return found
    for dll_dir in discover_nvidia_runtime_dll_dirs():
        dll_path = Path(dll_dir) / dll_name
        if dll_path.exists():
            return str(dll_path)
    return ""


def _is_fresh(output_path: Path, input_path: Path) -> bool:
    if not output_path.exists():
        return False
    try:
        return output_path.stat().st_mtime >= input_path.stat().st_mtime
    except OSError:
        return False
