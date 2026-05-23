# Chinese MP3 to English ASMR Remotion Video

This project turns Chinese narration MP3 files into English ASMR-style videos
using local faster-whisper transcription, Gemini translation, Google Cloud
Text-to-Speech, cached Remotion image clips, and FFmpeg final assembly.

## Current Main Workflow

Put Chinese `.mp3` files in `input_audio_lining/`, put source images in
`universe picture/`, then run:

```powershell
python main.py
```

The current `main.py` workflow:

1. Moves the oldest queued MP3 from `input_audio_lining/` into `input_audio/`
   when `input_audio/` is empty.
2. Transcribes Chinese MP3 audio locally with faster-whisper.
3. Translates Chinese SRT subtitles to English with Gemini.
4. Writes a terminology review CSV in `translations/`.
5. Builds English narration text with a fixed intro/outro and calls Google
   Cloud Text-to-Speech.
6. Post-processes the voiceover for a softer ASMR sound, reusing the cached
   ASMR WAV when it is already fresh.
7. Concatenates pre-rendered Remotion image clips from `remotion_clips/`.
8. Mixes narration and background music, then writes the final MP4 to
   `output_videos/`.
9. Moves the successfully processed source MP3 into `input_audio_finish/`.

The main workflow does not call pyVideoTrans, Edge TTS, subtitles burn-in, or
the old `input_videos/` localization path.

## Remotion Clip Cache

The final video expects each source image to already have a matching cached
Remotion clip:

```text
universe picture/example.png -> remotion_clips/example.mp4
```

Render only missing clips:

```powershell
python pre_render_remotion_clips.py
```

Force rebuild every clip manually:

```powershell
python pre_render_remotion_clips.py --force
```

Each clip is intended to be silent 1080p, 30 FPS, 30 seconds, H.264 MP4,
encoded through FFmpeg NVENC with `h264_nvenc -preset p4 -cq 19`.

Final assembly uses FFmpeg concat demuxer and `-c:v copy` for the visual stream,
so normal `python main.py` runs should not rerender Remotion or re-encode video
unless clips are missing or you explicitly rebuild them.

## Useful Commands

Run the full workflow:

```powershell
python main.py
```

Force Gemini to rebuild English subtitles:

```powershell
python main.py --force-translation
```

Run the standalone Remotion visual test:

```powershell
python render_remotion_test.py --seconds 10 --images 3
```

Run tests:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

## Folders

- `input_audio_lining/`: queued Chinese MP3 files; the oldest file is staged
  first.
- `input_audio/`: currently staged Chinese MP3 file for the current workflow.
- `input_audio_finish/`: source MP3 files after a successful render.
- `universe picture/`: source images for Remotion clip rendering.
- `remotion_clips/`: reusable animated MP4 clips, keyed by image filename stem.
- `legacy/`: empty after the old helper scripts were reviewed and removed.
- `subtitles/`: Chinese and English SRT files.
- `voiceovers/`: Google Cloud TTS WAV files and ASMR post-processed WAV files.
- `translations/`: translation review CSV reports.
- `music/`: background music files used by `BGM_SEQUENCE`.
- `output_videos/`: final rendered MP4 files.
- `temp/`: regenerated intermediate files, concat lists, and visual tests.
- `logs/workflow.log`: workflow log output.

## Main Settings

Edit `config.py` for the main controls:

```python
INPUT_AUDIO_DIR = "input_audio"
INPUT_AUDIO_LINING_DIR = "input_audio_lining"
INPUT_AUDIO_FINISH_DIR = "input_audio_finish"
UNIVERSE_PICTURE_DIR = "universe picture"
REMOTION_CLIP_DIR = "remotion_clips"

FASTER_WHISPER_MODEL_PATH = r"D:\AI\video_CN2EN\models\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
FASTER_WHISPER_DEVICE = "cuda"
FASTER_WHISPER_COMPUTE_TYPE = "float16"

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_THINKING_LEVEL = "MEDIUM"

GOOGLE_TTS_LANGUAGE_CODE = "en-US"
GOOGLE_TTS_VOICE_NAME = "en-US-Chirp3-HD-Charon"
GOOGLE_TTS_SPEAKING_RATE = 0.92
GOOGLE_TTS_MAX_CHARS = 1800

BGM_SEQUENCE = ["Titanic.mp3", "1 HOUR.mp3"]
BGM_VOLUME = 0.5

REMOTION_CLIP_SECONDS = 30
REMOTION_CLIP_FPS = 30
REMOTION_CLIP_VIDEO_ENCODER = "h264_nvenc"
REMOTION_CLIP_NVENC_PRESET = "p4"
REMOTION_CLIP_CQ = "19"
```

The Remotion animation itself lives in `remotion/src/index.jsx`.

## Requirements

- Python dependencies installed with `pip install -r requirements.txt`.
- Remotion dependencies installed once with `npm.cmd install` inside
  `remotion/`.
- A local faster-whisper model at `FASTER_WHISPER_MODEL_PATH`.
- `GEMINI_API_KEY` in `.env` for Gemini translation.
- `GOOGLE_CLOUD_TTS_API_KEY` in `.env` for Google Cloud Text-to-Speech.
- FFmpeg and ffprobe available in PATH, or `FFMPEG_BIN_DIR` set in `.env`.
- Internet access for Gemini and Google Cloud TTS.

The faster-whisper model now lives inside this project under `models/`. The
current workflow uses it directly through the `faster-whisper` Python package.
It does not run the pyVideoTrans CLI.

## Legacy Files

Older helper scripts for the previous video-input, manual-translation, Edge TTS,
and pyVideoTrans experiments were reviewed and removed from `legacy/`. They are
not part of the current `python main.py` path. See `PROJECT_CLEANUP.md` for the
cleanup inventory.

This wrapper does not bulk-delete files or directories.
