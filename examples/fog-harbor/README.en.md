# Sample session: Fog Harbor Lighthouse

**English** | [中文](README.md)

A made-up one-shot: three players, a GM and a quarter of an hour of chat log, used to show R'lyeh Workshop's whole path from a session log to a finished video. The players, characters and log are all fictional. The script is in Chinese.

Everything uses **placeholder backends** by default, so it runs with no models installed: images are silhouettes, voices are tones and music is a chord pad. Once you have models, switch `[backends]` in `replay.toml` to real ones; `replay doctor` tells you what is still missing.

## What's inside

| File | Contents |
|---|---|
| `logs/raw/session-2024-05-18.txt` | The raw chat log (plain text with timestamps) |
| `script/01-雾港灯塔.md` | The script an AI wrote from the log: speech turned into lines, tones, expressions and stage directions added, table talk kept as OOC chat |
| `cast.yaml` | Cast sheet: looks, expressions, tone → expression rules, voice descriptions |
| `art/prompts/` | Image prompts for sprites, expressions, backgrounds, CGs and items, one file per image |
| `music.yaml` | Cue sheet: mood, instruments and tempo of each scene |
| `sfx.yaml` | The project's own sound (the wraith's wail, generated in its voice) |

Everything generated (voices, images, music, `build/`) is in `.gitignore` and stays out of version control.

## Run it

From the repository root:

```bash
uv run replay import -C examples/fog-harbor        # log → logs/events.jsonl
uv run replay lint -C examples/fog-harbor
uv run replay voice build -C examples/fog-harbor   # voices
uv run replay bleep -C examples/fog-harbor         # bleep the one line with profanity
uv run replay art run -C examples/fog-harbor       # images; expression variants are composited automatically
uv run replay sfx -C examples/fog-harbor
uv run replay music gen -C examples/fog-harbor
uv run replay preview -C examples/fog-harbor       # open http://127.0.0.1:8766/
```

In the preview pages, pick voices, review lines and art, and choose a take for each music cue (or `replay music pick harbor 1`). Then:

```bash
uv run replay build -C examples/fog-harbor         # build the player; open it from the preview home page
uv run replay render -C examples/fog-harbor        # render the video frame by frame (needs uv sync --extra render and ffmpeg)
uv run replay encode share -C examples/fog-harbor  # a small version for sharing
```

The video ends up in `build/video/fog-harbor.mp4`.

## Switching to real backends

| Capability | Placeholder | Real backend |
|---|---|---|
| Images | `image = "placeholder"` | `codex` (set model and effort in `[harness.codex]`) or `manual` |
| Voice design | `voice_design = "placeholder"` | `qwen3-tts` |
| Voices | `tts = "placeholder"` | `drama3` |
| Recognition QA | `asr = "none"` | `sensevoice` |
| Bleep alignment | `align = "estimate"` (estimated from length) | `funasr-fa` (Chinese, accurate) |
| Music | `music = "placeholder"` | `yue2-comfyui` (ComfyUI must be running) or `manual` |

The settings each backend needs are in [Project format](../../docs/en/project-format.md).
