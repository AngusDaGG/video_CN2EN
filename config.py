"""User-editable settings for the Chinese-to-English video workflow."""

FASTER_WHISPER_MODEL_PATH = r"D:\AI\video_CN2EN\models\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
FASTER_WHISPER_LANGUAGE = "zh"
FASTER_WHISPER_DEVICE = "cuda"
FASTER_WHISPER_COMPUTE_TYPE = "float16"
FASTER_WHISPER_VAD_FILTER = True

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_TRANSLATION_CHUNK_CHARS = 6000
GEMINI_TRANSLATION_RETRY_ATTEMPTS = 3
GEMINI_TRANSLATION_MIN_CHUNK_BLOCKS = 5
GEMINI_THINKING_LEVEL = "MEDIUM"
GEMINI_TRANSLATION_SYSTEM_INSTRUCTION = (
    "你是一位專業的天文學翻譯專家，負責將中文流暢地翻譯成英文，"
    "翻譯的英文結果要是正常母語者的講法，不要一個一個字照翻。"
)

GOOGLE_TTS_LANGUAGE_CODE = "en-US"
GOOGLE_TTS_VOICE_NAME = "en-US-Chirp3-HD-Charon"
GOOGLE_TTS_SPEAKING_RATE = 0.92
GOOGLE_TTS_PITCH = None
GOOGLE_TTS_VOLUME_GAIN_DB = 0.0
GOOGLE_TTS_SAMPLE_RATE_HERTZ = 24000
GOOGLE_TTS_MAX_CHARS = 1800
GOOGLE_TTS_TIMEOUT_SECONDS = 120
TTS_INTRO_TEMPLATE = (
    "Believe it or not, I can make you fall asleep before this video ends. "
    "You can leave a comment with the time right now before we start. "
    "Welcome to Dreaming Universe. "
    "If you've had a long day but you're still not tired, and you don't feel like resting yet, "
    "feel free to skip this video. Come back to this universe when you're ready. "
    "And to the remaining elite Earthlings still here. You made the Earth a little better today. "
    "Try placing your phone beside your pillow. You don't have to fall asleep right away. "
    "Just close your eyes. After everything you've been through today, you're allowed to rest now. "
    "Tonight we are gonna talk about \"{video_title}\"."
)
TTS_OUTRO_TEXT = (
    "May you have a beautiful dream. Good night. "
    "If you're still not tired, tag me under your comment. "
    "I'll send you a little mystery gift."
)

INPUT_DIR = "input_videos"
INPUT_AUDIO_DIR = "input_audio"
INPUT_AUDIO_LINING_DIR = "input_audio_lining"
INPUT_AUDIO_FINISH_DIR = "input_audio_finish"
OUTPUT_DIR = "output_videos"
AUDIO_DIR = "audio"
TRANSCRIPT_DIR = "transcripts"
TRANSLATION_DIR = "translations"
NARRATION_DIR = "narration_scripts"
SUBTITLE_DIR = "subtitles"
VOICEOVER_DIR = "voiceovers"
MUSIC_DIR = "music"
LOG_DIR = "logs"
UNIVERSE_PICTURE_DIR = "universe picture"
TEMP_DIR = "temp"

GLOSSARY_FILE = "glossary_terms.csv"

ORIGINAL_AUDIO_VOLUME = 0.0
VOICE_VOLUME = 1.0
BGM_FILE = ""
BGM_SEQUENCE = ["1 HOUR.mp3"]
BGM_VOLUME = 1.0
FADE_IN_SECONDS = 1.0
FADE_OUT_SECONDS = 2.0
ENABLE_AUTO_DUCKING = True
BURN_SUBTITLES = True

VOICEOVER_FORMAT = "mp3"
AUDIO_SAMPLE_RATE = 44100
SUBTITLE_MAX_CHARS_PER_LINE = 42
SUBTITLE_MAX_LINES = 2

SLIDESHOW_IMAGE_SECONDS = 30
SLIDESHOW_WIDTH = 1920
SLIDESHOW_HEIGHT = 1080

REMOTION_CLIP_DIR = "remotion_clips"
REMOTION_CLIP_SECONDS = 30
REMOTION_CLIP_FPS = 30
REMOTION_CLIP_VIDEO_ENCODER = "h264_nvenc"
REMOTION_CLIP_NVENC_PRESET = "p7"
REMOTION_CLIP_CQ = "15"
REMOTION_CLIP_NVENC_TUNE = "hq"
REMOTION_CLIP_NVENC_RC_LOOKAHEAD = "20"
REMOTION_CLIP_NVENC_SPATIAL_AQ = "1"
REMOTION_CLIP_NVENC_TEMPORAL_AQ = "1"
REMOTION_INTERMEDIATE_CODEC = "prores"
REMOTION_PRORES_PROFILE = "hq"
REMOTION_FRAME_IMAGE_FORMAT = "png"
REMOTION_CLIP_QUALITY_VERSION = "prores-png-nvenc-hq-v1"
TITLE_TRANSLATION_CACHE_SUFFIX = "_title_en.txt"
