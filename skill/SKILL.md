---
name: chinese-video-to-english-localized-video
description: Semi-automatic Chinese video to English localized video workflow with local FFmpeg media processing, manually translated ChatGPT Plus handoff files, Edge TTS English narration, subtitles, optional BGM, terminology safeguards, and a required human review step. Use when OpenAI API keys must not be used.
---

# Chinese Video to English Localized Video

Use this skill to run a semi-automatic workflow for Chinese videos without OpenAI API calls.

## Required Inputs

- `.mp4` files in `input_videos/`.
- FFmpeg and ffprobe.
- Optional local whisper.cpp executable and model for local transcription.
- Manual English translation saved as `transcript_en.txt` or `subtitles_en.srt`.
- `edge-tts` installed for Microsoft Edge TTS voiceover generation.
- Optional licensed BGM in `music/`.

## Expected Outputs

- Extracted audio in `audio/`.
- Chinese review transcript in `transcripts/`.
- Chinese review SRT in `subtitles/`.
- Manual English transcript or English SRT read from `translations/` or `subtitles/`.
- Edge TTS voiceover in `voiceovers/`.
- Final video in `output_videos/`.

## Workflow

1. Detect `.mp4` files in `input_videos/`.
2. Extract original audio with FFmpeg.
3. Create `transcript_zh.txt` and `subtitles_zh.srt`.
4. Pause if English files are missing.
5. Ask the user to paste the Chinese content into ChatGPT Plus manually.
6. Read `transcript_en.txt` or `subtitles_en.srt`.
7. Generate English subtitles if only transcript text was provided.
8. Generate Edge TTS English voiceover.
9. Mix optional BGM.
10. Render final video and print the human review checklist.

## Terminology Rules

- Treat proper nouns and technical terms as high risk.
- Use `glossary_terms.csv` during manual translation.
- Do not guess English names for brands, people, places, games, anime, companies, products, IP names, or technical terms.
- If uncertain, keep the original term or mark `[VERIFY TERM: original term]`.
- Prioritize terminology accuracy over smoothness.

## Voiceover Rules

- Use `edge-tts`.
- Default to a male English voice such as `en-US-GuyNeural`.
- Aim for deep, calm, mature, cinematic narration.
- Use slower rate and lower pitch settings for a deeper narrator feel.
- Do not clone voices.
- Do not imitate real people or celebrities.

## Subtitle Rules

- Use `.srt`.
- Prefer 1-2 readable lines per block.
- Keep English subtitle terminology consistent with the glossary.
- If only `transcript_en.txt` is provided, reuse Chinese SRT timing as a simple timing guide.

## BGM Rules

- Use only manually provided licensed music.
- If `BGM_FILE` is empty, render without BGM.
- Keep BGM below narration.
- Loop or trim BGM to video duration.
- Add fade-in/fade-out and optional auto-ducking.

## Copyright and Review

- Process only videos the user owns, has permission to use, or is transforming with proper commentary or educational value.
- Do not upload automatically.
- Do not delete source or intermediate files.
- Review translation, terminology, voiceover, subtitles, BGM volume, and reused-content risk before publishing.
