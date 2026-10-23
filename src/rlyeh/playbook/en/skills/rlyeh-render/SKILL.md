---
name: rlyeh-render
description: Use in an R'lyeh Workshop project to build the player, preview it, render the video frame by frame, remix the audio, and encode a share version.
---

# Build, render, encode

## Building the player

`replay build` → `build/player/`. The output lists missing voices, images, sounds and cues and unknown directions: fill gaps at the matching stage; fix unknown directions in the script. Then open `/player` in `replay preview` (or `rlyeh_preview_url page=player line=<line-id>` to start at a line) and show the user.

## Rendering

- **Try a stretch first**: `replay render --from <line-id> --seconds 30`; check pacing, sprites and effects before rendering everything.
- **Everything**: `replay render` (chapters render in parallel, then join); an hour of video takes about 1–2 hours. Run it in the background (`rlyeh_run_stage render`) and tell the user roughly how long first.
- **Only the mix changed** (levels, ducking, loudness in `[mix]`): `replay render --remix`; the picture isn't re-rendered.
- Needs playwright and ffmpeg; `replay doctor` checks them.

## Encoding

- `replay encode share`: AV1 share version, small (NVENC if the GPU supports it, CPU otherwise).
- `replay encode compat`: H.264 for older devices and the web.
- The master is what `replay render` writes, `build/video/<project-id>.mp4`.

## Rules

- **Never screen-record in real time**: it drops frames and takes as long as the video. Rendering is frame by frame; each frame depends only on the timeline.
- The video is the user's work: uploading and publishing are theirs to do.
- When non-commercial backends are in use (`replay doctor` says so, e.g. YuE2), remind the user the video can't be used commercially.
