"""Resource and API usage reporting for monitored workflow runs."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator


SampleFn = Callable[[], dict[str, Any]]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@dataclass
class StepRecord:
    name: str
    start_time: str
    end_time: str = ""
    duration_seconds: float = 0.0
    status: str = "running"
    error: str = ""


@dataclass
class ApiUsageRecord:
    provider: str
    operation: str
    model: str = ""
    prompt_tokens: int | None = None
    candidates_tokens: int | None = None
    total_tokens: int | None = None
    thoughts_tokens: int | None = None
    characters: int | None = None
    requests: int = 1
    status: str = "ok"
    error: str = ""


@dataclass
class RunMetrics:
    run_id: str = field(default_factory=make_run_id)
    output_dir: Path = Path("logs/resource_runs")
    started_at: str = ""
    ended_at: str = ""
    duration_seconds: float = 0.0
    success: bool = False
    output_path: str = ""
    output_metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    steps: list[StepRecord] = field(default_factory=list)
    api_usage: list[ApiUsageRecord] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    report_paths: dict[str, Path] = field(default_factory=dict)
    _start_monotonic: float = 0.0

    def start(self) -> None:
        self.started_at = utc_now_iso()
        self._start_monotonic = time.perf_counter()

    def finish(
        self,
        *,
        success: bool,
        output_path: Path | str | None = None,
        output_metadata: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        self.success = success
        self.output_path = str(output_path) if output_path else ""
        self.output_metadata = output_metadata or {}
        self.error = error
        self.ended_at = utc_now_iso()
        if self._start_monotonic:
            self.duration_seconds = time.perf_counter() - self._start_monotonic

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        record = StepRecord(name=name, start_time=utc_now_iso())
        started = time.perf_counter()
        self.steps.append(record)
        try:
            yield
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            raise
        else:
            record.status = "ok"
        finally:
            record.end_time = utc_now_iso()
            record.duration_seconds = time.perf_counter() - started

    def record_api_usage(
        self,
        *,
        provider: str,
        operation: str,
        model: str = "",
        prompt_tokens: int | None = None,
        candidates_tokens: int | None = None,
        total_tokens: int | None = None,
        thoughts_tokens: int | None = None,
        characters: int | None = None,
        requests: int = 1,
        status: str = "ok",
        error: str = "",
    ) -> None:
        self.api_usage.append(
            ApiUsageRecord(
                provider=provider,
                operation=operation,
                model=model,
                prompt_tokens=prompt_tokens,
                candidates_tokens=candidates_tokens,
                total_tokens=total_tokens,
                thoughts_tokens=thoughts_tokens,
                characters=characters,
                requests=requests,
                status=status,
                error=error,
            )
        )

    def add_sample(self, sample: dict[str, Any]) -> None:
        self.samples.append(sample)

    def api_totals(self) -> dict[str, int]:
        return {
            "gemini_prompt_tokens": sum_int(record.prompt_tokens for record in self.api_usage if record.provider == "gemini"),
            "gemini_candidates_tokens": sum_int(
                record.candidates_tokens for record in self.api_usage if record.provider == "gemini"
            ),
            "gemini_total_tokens": sum_int(record.total_tokens for record in self.api_usage if record.provider == "gemini"),
            "gemini_thoughts_tokens": sum_int(
                record.thoughts_tokens for record in self.api_usage if record.provider == "gemini"
            ),
            "google_tts_characters": sum_int(
                record.characters for record in self.api_usage if record.provider == "google_tts"
            ),
            "google_tts_requests": sum_int(record.requests for record in self.api_usage if record.provider == "google_tts"),
        }

    def write_reports(self) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": self.output_dir / f"{self.run_id}_summary.json",
            "steps": self.output_dir / f"{self.run_id}_steps.csv",
            "samples": self.output_dir / f"{self.run_id}_samples.csv",
            "api_usage": self.output_dir / f"{self.run_id}_api_usage.csv",
            "report": self.output_dir / f"{self.run_id}_report.md",
        }
        paths["summary"].write_text(json.dumps(self._summary_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        write_csv(paths["steps"], [record.__dict__ for record in self.steps])
        write_csv(paths["samples"], self.samples)
        write_csv(paths["api_usage"], [record.__dict__ for record in self.api_usage])
        paths["report"].write_text(self.write_human_report(), encoding="utf-8")
        self.report_paths = paths
        return paths

    def write_human_report(self) -> str:
        totals = self.api_totals()
        lines = [
            f"# Resource Run {self.run_id}",
            "",
            f"- 狀態：{'成功' if self.success else '失敗'}",
            f"- 總耗時：{format_duration(self.duration_seconds)}",
            f"- 開始時間：{self.started_at or 'unknown'}",
            f"- 結束時間：{self.ended_at or 'unknown'}",
        ]
        if self.error:
            lines.append(f"- 錯誤：{self.error}")

        lines.extend(["", "## 耗時重點"])
        if self.steps:
            for step in sorted(self.steps, key=lambda record: record.duration_seconds, reverse=True):
                suffix = ""
                if step.status != "ok":
                    suffix = f"（{step.status}: {step.error}）"
                lines.append(f"- {step.name}：{format_duration(step.duration_seconds)}{suffix}")
        else:
            lines.append("- 沒有 step 紀錄")

        lines.extend(
            [
                "",
                "## API 使用量",
                f"- Gemini total tokens：{totals['gemini_total_tokens']:,}",
                f"- Gemini prompt tokens：{totals['gemini_prompt_tokens']:,}",
                f"- Gemini candidates tokens：{totals['gemini_candidates_tokens']:,}",
                f"- Gemini thoughts tokens：{totals['gemini_thoughts_tokens']:,}",
                f"- Google Cloud TTS requests：{totals['google_tts_requests']:,}",
                f"- Google Cloud TTS characters：{totals['google_tts_characters']:,}",
            ]
        )

        lines.extend(["", "## 資源摘要"])
        for label, key in [
            ("CPU", "cpu_percent"),
            ("GPU", "gpu_percent"),
            ("NVENC", "gpu_encoder_percent"),
            ("GPU VRAM MB", "gpu_memory_used_mb"),
            ("GPU Power W", "gpu_power_watts"),
            ("可用 RAM MB", "memory_available_mb"),
        ]:
            summary = numeric_sample_summary(self.samples, key)
            if summary:
                lines.append(f"- {label}：平均 {summary['avg']:.1f}，最高 {summary['max']:.1f}")
        if not any(numeric_sample_summary(self.samples, key) for key in ("cpu_percent", "gpu_percent", "gpu_encoder_percent")):
            lines.append("- 沒有可用的 CPU/GPU 取樣資料")

        lines.extend(["", "## 輸出影片"])
        lines.extend(output_video_lines(self.output_path, self.output_metadata))

        lines.extend(["", "## STT CUDA 診斷"])
        lines.extend(cuda_diagnostic_lines())
        return "\n".join(lines) + "\n"

    def _summary_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "output_path": self.output_path,
            "output_metadata": self.output_metadata,
            "error": self.error,
            "step_count": len(self.steps),
            "sample_count": len(self.samples),
            "api_call_count": len(self.api_usage),
            "api_totals": self.api_totals(),
        }


class ResourceSampler:
    def __init__(self, sample_interval_seconds: float = 1.0, sample_fn: SampleFn | None = None) -> None:
        self.sample_interval_seconds = sample_interval_seconds
        self.sample_fn = sample_fn or collect_resource_sample
        self.samples: list[dict[str, Any]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=max(self.sample_interval_seconds * 2, 1.0))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                sample = self.sample_fn()
            except Exception as exc:
                sample = {"timestamp": utc_now_iso(), "error": str(exc)}
            self.samples.append(sample)
            self._stop_event.wait(self.sample_interval_seconds)


def collect_resource_sample() -> dict[str, Any]:
    sample: dict[str, Any] = {"timestamp": utc_now_iso()}
    sample.update(_collect_windows_counters())
    sample.update(_collect_nvidia_smi())
    return sample


def _collect_windows_counters() -> dict[str, Any]:
    result: dict[str, Any] = {}
    cpu = _run_text(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples.CookedValue",
        ]
    )
    if cpu:
        result["cpu_percent"] = parse_float(cpu)
    available_mb = _run_text(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Counter '\\Memory\\Available MBytes').CounterSamples.CookedValue",
        ]
    )
    if available_mb:
        result["memory_available_mb"] = parse_float(available_mb)
    return result


def _collect_nvidia_smi() -> dict[str, Any]:
    output = _run_text(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,utilization.encoder,memory.used,power.draw",
            "--format=csv,noheader,nounits",
        ]
    )
    if not output:
        return {}
    parts = [part.strip() for part in output.splitlines()[0].split(",")]
    keys = ["gpu_percent", "gpu_encoder_percent", "gpu_memory_used_mb", "gpu_power_watts"]
    return {key: parse_float(value) for key, value in zip(keys, parts)}


def _run_text(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def parse_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def sum_int(values: Any) -> int:
    total = 0
    for value in values:
        if value is not None:
            total += int(value)
    return total


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown"
    total_seconds = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小時{minutes}分{secs}秒"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def numeric_sample_summary(samples: list[dict[str, Any]], key: str) -> dict[str, float] | None:
    values: list[float] = []
    for sample in samples:
        value = sample.get(key)
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    return {"avg": sum(values) / len(values), "max": max(values)}


def output_video_lines(output_path: str, metadata: dict[str, Any]) -> list[str]:
    if not output_path:
        return ["- 沒有輸出影片"]
    lines = [f"- 路徑：{output_path}"]
    size_bytes = metadata.get("size_bytes")
    if isinstance(size_bytes, int):
        lines.append(f"- 檔案大小：{format_bytes(size_bytes)}")

    streams = metadata.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            if stream.get("codec_type") == "video":
                fps = stream.get("r_frame_rate", "unknown")
                lines.append(
                    f"- 影像：{stream.get('codec_name', 'unknown')} "
                    f"{stream.get('width', '?')}x{stream.get('height', '?')} {fps} fps"
                )
            elif stream.get("codec_type") == "audio":
                lines.append(f"- 音訊：{stream.get('codec_name', 'unknown')}")

    format_info = metadata.get("format")
    if isinstance(format_info, dict):
        duration = parse_float(str(format_info.get("duration", "")))
        if duration is not None:
            lines.append(f"- 時長：{format_duration(duration)}")
    if metadata.get("ffprobe_error"):
        lines.append(f"- ffprobe 錯誤：{metadata['ffprobe_error']}")
    return lines


def format_bytes(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "bytes" else f"{int(value)} bytes"
        value /= 1024
    return f"{size_bytes} bytes"


def cuda_diagnostic_lines() -> list[str]:
    diagnostics = collect_cuda_runtime_diagnostics()
    lines = [
        f"- cublas64_12.dll：{diagnostics['cublas64_12.dll']}",
        f"- cudnn64_9.dll：{diagnostics['cudnn64_9.dll']}",
        f"- ctranslate2 CUDA devices：{diagnostics['ctranslate2_cuda_devices']}",
        f"- nvidia-cublas-cu12：{diagnostics['nvidia-cublas-cu12']}",
        f"- nvidia-cudnn-cu12：{diagnostics['nvidia-cudnn-cu12']}",
        "- 建議官方安裝命令：`py -m pip install --upgrade nvidia-cublas-cu12 nvidia-cudnn-cu12`",
    ]
    if diagnostics["cublas64_12.dll"] == "missing" or diagnostics["cudnn64_9.dll"] == "missing":
        lines.append("- 不建議從第三方 DLL 網站下載單顆 DLL；優先用 NVIDIA 官方 pip wheels 或官方 CUDA/cuDNN 安裝來源。")
    return lines


def collect_cuda_runtime_diagnostics() -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "cublas64_12.dll": find_nvidia_runtime_dll("cublas64_12.dll") or "missing",
        "cudnn64_9.dll": find_nvidia_runtime_dll("cudnn64_9.dll") or "missing",
        "ctranslate2_cuda_devices": "unknown",
        "nvidia-cublas-cu12": installed_distribution_version("nvidia-cublas-cu12"),
        "nvidia-cudnn-cu12": installed_distribution_version("nvidia-cudnn-cu12"),
    }
    try:
        import ctranslate2

        diagnostics["ctranslate2_cuda_devices"] = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        diagnostics["ctranslate2_cuda_devices"] = f"unavailable: {exc}"
    return diagnostics


def find_nvidia_runtime_dll(dll_name: str) -> str:
    found = shutil.which(dll_name)
    if found:
        return found
    spec = importlib.util.find_spec("nvidia")
    search_locations = getattr(spec, "submodule_search_locations", None) if spec else None
    if not search_locations:
        return ""
    for package_root in search_locations:
        for dll_path in Path(package_root).rglob(dll_name):
            if dll_path.exists():
                return str(dll_path)
    return ""


def installed_distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames or ["empty"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
