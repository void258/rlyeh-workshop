# Project format

> Specification v0.1 draft. Chinese edition: [`docs/zh/project-format.md`](../zh/project-format.md)

A replay is a project folder. Studio, the CLI and the AI all read and write it; there is no hidden database.

## Layout

```
my-replay/
├── replay.toml          project config
├── cast.yaml            cast sheet
├── logs/                original logs (read-only once imported)
│   ├── raw/             exported files, kept as-is
│   └── events.jsonl     normalized event stream
├── script/              one file per chapter
│   ├── 01-rams-horn-inn.md
│   └── 02-treant-forest.md
├── voices/              voice candidates and chosen fixed references
├── art/
│   ├── prompts/         image prompts (written by the AI, editable by people)
│   ├── sprites/<char-id>/<char-id>_<expression>.png
│   ├── backgrounds/  cg/  items/
│   ├── _raw/            raw generations (before expression compositing)
│   └── _overview/       overview sheets for review
├── audio/
│   ├── voice/<line-id>.wav        voice as generated
│   ├── voice-bleep/<line-id>.wav  bleeped versions (only lines with profanity)
│   ├── bgm/<cue-id>.flac
│   └── sfx/
├── review/              human review results (written by Studio, read by the AI)
├── build/               regenerable outputs: player data, rendered frames, final videos
└── .rlyeh/              state and caches: state.json, task records, logs
```

Rules:

- **File names and IDs are ASCII only.** Non-ASCII paths break a surprising number of tools (production hit this with audio.cpp and the Windows console encoding). Characters, cues and scenes have ASCII IDs in the config; display names can be in any language.
  - Exception: script file names and human-facing docs may use any language; tools don't depend on those names.
- `logs/raw/` is read-only after the import stage.
- `build/` and `.rlyeh/` can be deleted and rebuilt at any time; keep them out of git.
- Large files (audio, images, video) should use Git LFS or stay out of version control. Studio writes a suitable `.gitignore` when creating a project.

## replay.toml

The project config. A complete example; see the comments for meaning.

```toml
spec = "0.1"                      # spec version

[project]
id = "yangjiao"                   # ASCII, used in file names
title = "Shadow of the Demon Lord · Ram's Horn Inn"
language = "zh-CN"                # script language: zh-CN / en
session_dates = ["2022-07-20", "2022-07-21"]

# OOC players → the character they play (character IDs from cast.yaml). Mark the GM separately
[players]
"Kobayashi" = "nongtan"
"Jay" = "dirk"
"Yuzu" = "yc116"
"Mia" = "guwa"
"GM:void" = { role = "gm" }

[harness]
default = "claude-code"           # claude-code | codex | dsh

# Caps per harness, so nothing silently defaults to the most expensive model and highest effort
[harness.codex]
model = "gpt-6.1-sol"
effort = "low"

[harness.dsh]
model = "deepseek-v4-flash"

[backends]                        # which backend each capability uses; see backends.md
import = "fvtt"
image = "codex"                   # codex | comfyui | openai | manual
voice_design = "qwen3-tts"
tts = "drama3"
asr = "sensevoice"
align = "funasr-fa"
music = "yue2-comfyui"            # yue2-comfyui | ace-step | manual

[backends.drama3]                 # per-backend settings
cli = "D:/vtts/audio.cpp/build/bin/audiocpp_cli.exe"
model = "D:/vtts/drama3/drama-3-backbone-Q4_K_S.gguf"

[art]
style = "Japanese anime style, clean cel shading, muted dark palette, dark fantasy mood"
always_append = "no fake details or fake textures"   # appended to every image prompt

# Changes only what the TTS reads, never the subtitles
[readings]
"116" = "幺幺六"
"d4" = "滴四"

# How bleeped words are spoken before being beeped out
[spoken]
"cnm" = "操你妈"
"sb" = "傻逼"

[render]
width = 1920
height = 1080
fps = 60

[mix]
voice_rms = 0.1                   # RMS each voice line is normalized to
bgm_level = 0.3                   # relative to voice
duck = 0.5                        # BGM level while someone speaks
sfx_level = 0.55
loudness = -16                    # final loudness (LUFS)

[encode.master]
codec = "h264"
quality = 19

[encode.share]
codec = "av1"
quality = 37                      # NVENC cq; mapped to an SVT-AV1 crf when encoding on CPU
```

### Import settings

```toml
[import]
system = "demonlord"              # which game system's roll cards to parse; omit to try all
gm = ["void"]                     # GM account names
observers = ["ob1"]               # spectators
renamed = { "Shiro" = "Shark" }   # accounts renamed mid-campaign, unified under one name
session_gap_hours = 3             # a gap this long starts a new session
min_session_messages = 20         # shorter sessions are treated as tests and dropped

# Anonymization: real name → alias, replaced in speakers and text on import
[aliases]
"John" = "Kobayashi"
```

## Imported logs

`replay import` merges every export in `logs/raw/` (txt, zip) into `logs/events.jsonl`, one event per line:

```json
{"id": "e000042", "ts": "2022-07-20T21:12:05", "speaker": "Phlegm", "text": "19\n1d20 + 3 = 16 + 3 = 19",
 "kind": "roll", "role": "character", "data": {"formula": "1d20 + 3", "total": "19", "detail": "16 + 3"},
 "source": "log.zip/fvtt-log-Wed-Jul-20-2022.txt", "session": 1}
```

| Field | Meaning |
|---|---|
| `id` | Event ID, numbered in time order |
| `ts` | Time (ISO 8601); `null` when a plain-text log has no times |
| `speaker` | Speaker (after `renamed` and `[aliases]`) |
| `text` | Original text |
| `kind` | `message` · `ooc` (out-of-character, starting with a parenthesis) · `roll` · `card` (system card) |
| `role` | `gm` · `player` (an account in `[players]`) · `observer` · `character` (everyone else, usually characters or monsters) |
| `data` | Roll formula and result, or fields parsed from a system card (attack, check, damage, spell…) |
| `source` | Which export it came from |
| `session` | Session number |

`logs/sessions.json` is written alongside: each session's start, end, event count and speakers, dropped test stretches, and possible private details found (phone numbers, emails, QQ numbers, links).

## cast.yaml

The cast sheet. Character IDs are ASCII; `name` is the display name, per language.

```yaml
characters:
  nongtan:
    name: { zh-CN: 浓痰, en: Phlegm }
    kind: pc                       # pc | npc | narrator | gm
    player: Kobayashi
    color: "#7d9a3c"               # name plate color
    appearance: >                  # used when writing image prompts
      A hulking orc veteran with grey-green skin and two stubby tusks...
    expressions:                   # expression variants: name → description
      cocky: grinning arrogantly, tusks bared, looking down at others
      furious: brows knotted, roaring with the mouth wide open
      laughing: head thrown back, laughing out loud
    default_expression: cocky
    face_rules:                    # if the script has no [expression], pick one by tone keywords; first match wins
      - [laughing, "laugh"]
      - [furious, "roar|furious|yell"]
    sprite:                        # placement on screen (ratios of the sprite's width/height)
      scale: 1.0                   # sprites fill their canvas; shorter characters need a smaller scale
      head: [0.55, 0.115]          # avatar crop center
      mouth: [0.542, 0.13]         # mouth position (effects like breath-fire start here)
    voice:
      gender: male
      design: gruff, hoarse middle-aged orc voice, loud and overbearing
      reference: voices/nongtan_2.wav        # written by Studio once chosen
      reference_text: I'm in a good mood today, so I'll let it slide...

  narrator:
    name: { zh-CN: 旁白, en: Narrator }
    kind: narrator
    voice: { gender: male, reference: voices/narrator_1.wav, extra_references: [voices/narrator_x1.wav] }

  gm:
    name: { zh-CN: "GM:void", en: "GM:void" }
    kind: gm
    voice: { gender: male, reference: voices/gm_2.wav }
```

## Review files: review/

Studio's review pages write these files; the AI and tools only read them. Every record has the same shape:

```json
{
  "c1-0054": { "status": "redo", "note": "only moaning, no words", "by": "void", "at": "2026-10-22T19:43:45+08:00" }
}
```

`status` is one of `pending`, `approved`, `redo`, `skip`.

| File | Contents | Key |
|---|---|---|
| `voice-pick.json` | Which voice candidate each character uses | character ID |
| `voice-review.json` | Line-by-line listening marks | line ID |
| `art-review.json` | Approval of sprites, backgrounds, CGs, items | asset path |
| `music-review.json` | Which take each BGM cue uses | cue ID |
| `script-review.json` | Optional: script review notes | line ID or scene name |

## State and incremental rebuilds: .rlyeh/state.json

Every artifact records which inputs produced it (a hash of the input content). When an input changes, the artifact becomes **stale** and only stale parts are redone. For example:

- A line's text, tone or the character's voice reference changes → that line's voice is stale, and so is its bleeped version.
- A sprite is redrawn → player data and render are stale.
- Only a stage direction changes → voices are untouched; player data and render are stale.

`replay status` lists, per stage: done, stale, waiting for review, not started.

```json
{
  "stages": { "voice": { "done": 528, "stale": 3, "review": 1, "todo": 0 } },
  "artifacts": {
    "audio/voice/c1-0054.wav": { "inputs": "sha256:9f2c…", "seed": 7, "qa": { "sim": 0.91, "ok": true } }
  }
}
```

Incremental rebuilds depend on **stable line IDs**; see [Script format · Line IDs](script-format.md#line-ids).
