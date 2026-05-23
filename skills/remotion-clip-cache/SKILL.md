---
name: remotion-clip-cache
description: Pre-render still images into reusable Remotion MP4 clips and assemble final videos with FFmpeg. Use when working in this project with `universe picture/`, `remotion_clips/`, Remotion animation clips, FFmpeg concat, NVENC/GPU video encoding, or requests to avoid rerunning Remotion for unchanged image filenames.
---

# Remotion Clip Cache

Use this skill for the `D:\AI\video_CN2EN` workflow when still images should become reusable animated clips before final video assembly.

## Core Rule

Treat the image filename stem as the cache key:

- `universe picture/abc.png` maps to `remotion_clips/abc.mp4`.
- If the same-name `.mp4` exists, skip it.
- If the same-name `.mp4` is missing, render only that image with Remotion.
- Do not compare mtime, size, hashes, or image content.
- Do not bulk-delete clips. To refresh one clip, ask the user to delete that one explicit `.mp4` or use `--force`.

## Commands

Pre-render only missing clips:

```powershell
python pre_render_remotion_clips.py
```

Force rebuild every image clip:

```powershell
python pre_render_remotion_clips.py --force
```

Run the full video workflow after clips exist:

```powershell
python main.py
```

## Clip Contract

Every cached clip should be:

- 30 seconds
- 1920x1080
- 30fps
- silent
- H.264 MP4
- `yuv420p`
- encoded through FFmpeg NVENC when available: `h264_nvenc -preset p4 -cq 19`

The Remotion animation should preserve the established look: slow zoom, gentle rotation, fade in/out, and vignette.

## Final Assembly

Use FFmpeg concat demuxer with cached clips and prefer video stream copy:

- Concatenate cached clips with `-f concat -safe 0`.
- Use `-c:v copy` when assembling visual-only cached clips.
- Mix narration and BGM as audio filters.
- Keep final video at 1080p.
- Fall back to `h264_nvenc` only if stream copy cannot satisfy the final output.

## Validation

After changes, verify:

```powershell
python -m unittest tests -v
python pre_render_remotion_clips.py
```

Run `python pre_render_remotion_clips.py` twice. The second run should report that all clips already exist and should not invoke Remotion.

Use `ffprobe` to confirm representative clips:

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate,duration:stream_tags=encoder -of default=noprint_wrappers=1 remotion_clips/<clip>.mp4
```
