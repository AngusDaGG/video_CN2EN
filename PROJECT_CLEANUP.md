# Project Cleanup Inventory

This file records the current project shape after the Remotion clip-cache
workflow became the main path.

## Current Main Path

`python main.py` reaches these project modules:

- `main.py`
- `local_stt.py`
- `gemini_translate.py`
- `google_cloud_tts.py`
- `translation_review.py`
- `slideshow_video.py`
- `remotion_renderer.py`
- `srt_utils.py`
- `utils.py`
- `config.py`

`python pre_render_remotion_clips.py` is also active. It is the supported way to
fill `remotion_clips/` before running `main.py`.

`python render_remotion_test.py` is still useful as a standalone visual smoke
test, but it is not part of the normal production run.

## pyVideoTrans Status

The current workflow does not call the pyVideoTrans CLI.

The project now points to a faster-whisper model copied into this workspace:

```text
D:\AI\video_CN2EN\models\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo
```

That path is only used as a model directory by `local_stt.py`. The current
workflow is not using pyVideoTrans to translate, dub, render, or mix videos.

The old source model path was:

```text
D:\AI\pyvideotrans\models\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo
```

This project no longer needs that pyVideoTrans model path after `config.py` was
updated. Other tools outside this project may still depend on `D:\AI\pyvideotrans`,
so delete that folder manually only if you are sure nothing else uses it.

## Legacy Scripts

These scripts were moved to `legacy/`, reviewed, and then deleted after the
user approved removal. They were not reachable from `main.py` and belonged to
older experiments or earlier workflow shapes.

| File | Can delete for current main workflow? | Notes |
| --- | --- | --- |
| `legacy/extract_audio.py` | Deleted | Old `input_videos/` audio extraction helper. |
| `legacy/generate_subtitles.py` | Deleted | Old manual transcript-to-SRT helper. |
| `legacy/generate_voiceover.py` | Deleted | Old Edge TTS voiceover helper. |
| `legacy/manual_review.py` | Deleted | Old manual translation handoff helper. |
| `legacy/mix_audio.py` | Deleted | Old original-video audio mix helper. |
| `legacy/pyvideotrans_audio_runner.py` | Deleted | Old pyVideoTrans STT/translation/TTS wrapper. |
| `legacy/pyvideotrans_runner.py` | Deleted | Old pyVideoTrans full video wrapper. |
| `legacy/render_video.py` | Deleted | Old localized-video renderer with optional subtitle burn-in. |
| `legacy/rewrite_narration.py` | Deleted | Old manual narration text helper. |
| `legacy/transcribe.py` | Deleted | Old no-API/whisper.cpp placeholder transcription helper. |
| `legacy/translate.py` | Deleted | Old manual translation file path helper. |

They were deleted one explicit file path at a time; no bulk directory deletion
was used.

## Legacy Data Folders

These folders mostly support the older `input_videos/` or manual-translation
flow and are not required by the current MP3-to-Remotion main path:

- `input_videos/`
- `input_audio_lining/`
- `audio/`
- `transcripts/`
- `narration_scripts/`

Keep them if you still want their source media or history.

## Regenerated Intermediate Files

These are generally safe to recreate, but should be removed manually and
selectively if disk space is needed:

- `temp/*_remotion_clip_intermediate.mp4`
- `temp/*_remotion_clip_props.json`
- `temp/*_cached_remotion_visual.mp4`
- `temp/*_cached_remotion_clips.txt`
- `temp/*_google_tts_*.wav`
- `temp/*_google_tts_concat.txt`
- `temp/remotion_visual_intermediate.mp4`
- `temp/remotion_props.json`
- `temp/remotion_frame_*.jpg`
- `temp/verify_*.jpg`
- `__pycache__/`
- `tests/__pycache__/`

Do not remove `remotion_clips/` during normal cleanup. That folder is the
intentional Remotion animation cache.

## Historical Output Candidates

These can be reviewed manually if you want to reclaim space:

- Older timestamped MP4 files in `output_videos/`.
- Standalone experiment videos such as `output_videos/remotion_gpu_test.mp4`.
- Old Edge TTS smoke outputs in `voiceovers/edge_tts_test_*`.
- Old timestamped translation review CSV files in `translations/`.

Keep any file you may want to compare visually or audibly.

## CPU/GPU Notes

- New STT runs can hit CPU if faster-whisper cannot load CUDA runtime files.
  The observed warning mentions `cublas64_12.dll`.
- Remotion clip rendering is still partly CPU/Chromium work, but the clip cache
  prevents rerendering unchanged images.
- FFmpeg video encoding for clip creation uses NVENC when available.
- Final video assembly uses `-c:v copy`, which avoids video re-encoding and is
  cheaper than using GPU unnecessarily.
- FFmpeg audio filters such as `loudnorm`, `aresample`, `concat`, and `amix`
  are CPU work. The ASMR voiceover cache now avoids rerunning that step when
  the processed WAV is already fresh.
