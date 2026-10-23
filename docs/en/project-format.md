# Project format

> Specification v0.1 draft. Chinese edition: [`docs/zh/project-format.md`](../zh/project-format.md)

A replay is a project folder. Studio, the CLI and the AI all read and write it; there is no hidden database.

## Layout

```
my-replay/
├── replay.toml          project config
├── cast.yaml            cast sheet
├── music.yaml           cue sheet (BGM)
├── sfx.yaml             the project's own sound effects (optional)
├── logs/                original logs (read-only once imported)
│   ├── raw/             exported files, kept as-is
│   └── events.jsonl     normalized event stream
├── script/              one file per chapter
│   ├── 01-rams-horn-inn.md
│   └── 02-treant-forest.md
├── voices/              voice candidates and chosen fixed references
├── art/
│   ├── prompts/         image prompts, one file per image (written by the AI, editable by people)
│   ├── sprites/<char-id>/<char-id>_<expression>.png
│   ├── backgrounds/  cg/  items/
│   ├── _raw/            raw edit outputs (before expression compositing); history/ keeps images replaced by redraws
│   └── _overview/       overview sheets for review
├── audio/
│   ├── voice/<line-id>.wav        voice as generated
│   ├── voice-bleep/<line-id>.wav  bleeped versions (only lines with profanity)
│   ├── bgm/<cue-id>.flac          chosen BGM; takes/ holds the generated takes
│   └── sfx/<sfx-id>.wav           sound effects; index.json lists names, aliases and durations
├── review/              human review results (written by Studio, read by the AI)
├── build/               regenerable outputs: player/ the player, video/ rendered pictures and final videos
└── .rlyeh/              state and caches: state.json, task records, logs
```

Rules:

- **File names and IDs are ASCII only.** Non-ASCII paths break a surprising number of tools (production hit this with audio.cpp and the Windows console encoding). Characters, cues and scenes have ASCII IDs in the config; display names can be in any language.
  - Exception: script file names and human-facing docs may use any language; tools don't depend on those names.
  - File names the tools derive turn Chinese into pinyin: the expression 平静 → `pingjing`, the scene 羊角旅馆 → `yangjiaolvguan`.
- `logs/raw/` is read-only after the import stage.
- `build/` and `.rlyeh/` can be deleted and rebuilt at any time; keep them out of git.
- Large files (audio, images, video) should use Git LFS or stay out of version control. Studio writes a suitable `.gitignore` when creating a project.

## replay.toml

The project config. A complete example; see the comments for meaning.

```toml
spec = "0.1"                      # spec version

[project]
id = "yangjiao"                   # ASCII, used in file names
title = "Shadow of the Demon Lord"
subtitle = "Ram's Horn Inn"       # optional: subtitle on the title screen and in the credits
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
image = "codex"                   # codex | manual | placeholder (comfyui and openai planned)
voice_design = "qwen3-tts"
tts = "drama3"
asr = "sensevoice"
align = "funasr-fa"
music = "yue2-comfyui"            # yue2-comfyui | manual | placeholder (ace-step planned)

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
browser = "chromium"              # chromium (bundled with playwright) | msedge | chrome
jobs = 2                          # chapters rendered at the same time

[player]
title_bg = "Inn exterior"         # title screen background; defaults to the script's first background (with its variants)
title_bgm = "title"               # title screen cue; defaults to the cue called title, or the first one
die = 20                          # die size: with 20, natural 20 / 1 show NATURAL 20 / 1; 0 hides it
# hit_sounds = [["hit_slash", "sword|dagger"], ["burn", "fire"]]   damage sounds by the previous roll's skill; first match wins

[credits]
staff = [["Script & staging", "Aoi"]]   # extra sections: [heading, name, name...]
end = "To be continued"           # last line of the credits, "Fin" by default
background = "Face tree"          # credits background, the last background by default

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
codec = "av1"                     # h264 | hevc | av1
quality = 37                      # NVENC cq; mapped to a crf when encoding on CPU
encoder = "auto"                  # auto | nvenc | qsv | amf | cpu
audio = "copy"                    # copy | aac (then audio_bitrate = "160k")
# height = 720                    # scale down to this height
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

### Voice settings

```toml
[voice]
candidates = 3                    # voice candidates per character
seeds = [123, 7, 42, 2026, 99]    # the first is the default seed; the rest are for redos
min_similarity = 0.75             # QA: minimum similarity between recognized text and the line
max_extra = 1.4                   # QA: maximum ratio of recognized length to line length

# Model backends run in the user's own Python environment (R'lyeh Workshop itself doesn't install torch)
[backends.qwen3-tts]
python = "D:/qwen3-tts/env/python.exe"
design_model = "D:/qwen3-tts/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
base_model = "D:/qwen3-tts/models/Qwen3-TTS-12Hz-1.7B-Base"

[backends.sensevoice]
python = "C:/python311/python.exe"      # a Python with funasr installed
model = "D:/models/SenseVoiceSmall"

[backends.funasr-fa]
python = "C:/python311/python.exe"
```

`tts = "placeholder"`, `voice_design = "placeholder"` and `asr = "none"` are placeholder backends: the pipeline runs end to end with no models installed, with a tone of suitable length standing in for each voice line. `align = "estimate"` needs no model and estimates where to bleep from length. `replay doctor` checks whether each backend works.

Voice files:

| File | Contents |
|---|---|
| `voices/candidates/<char-id>_<n>.wav` + `voices/candidates.json` | Voice candidates and the text they read |
| `voices/extra/` + `voices/extra.json` | Extra references in the same voice (`replay voice extra`; texts in `voice.extra_texts` in cast.yaml) |
| `review/voice-pick.json` | Which candidate each character uses (written by the voice page; `voice.reference` in cast.yaml takes precedence) |
| `build/voice_qa.json` | Per-line QA: similarity, recognized text, duration, pass/fail |

### Art and music settings

```toml
[backends.codex]                  # all optional. Model and effort come from [harness.codex]; if missing it's an error,
bin = "codex"                     #   never a fallback to Codex's own defaults. bin may also be a list, e.g. ["node", "codex.js"]
timeout = 900                     # seconds to wait per image

[backends.yue2-comfyui]
url = "http://127.0.0.1:8188"     # ComfyUI must be running with the ComfyUI-YuE2 nodes installed
vram = "16 GB"                    # 12 GB | 16 GB | 24 GB | 32 GB | 48 GB

[music]
search_from = 3001                # vocal-free score search for instrumentals starts at this seed
search_limit = 12                 # and tries at most this many seeds
seconds = 160                     # default length when a cue doesn't say
check_chunk = 20                  # seconds per recognition chunk in the vocal check
```

`image = "placeholder"` and `music = "placeholder"` are placeholder backends too: simple silhouettes and gradients, and a soft chord pad, so the pipeline runs end to end.

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
      state_faces: { ghost: ghost }  # expression used in a state such as [[enter: ... | ghost]]
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

## Image prompts: art/prompts/

One markdown file per image: the front matter says what the image is, where it goes and which base and reference images it uses; the body is the prompt. `replay art jobs` writes a starter prompt for every image that has none yet, from cast.yaml and the script: sprites are assembled from `appearance` and the expression descriptions, while backgrounds, CGs and items get a `<!-- TODO -->` for the AI to fill in. Existing files are never overwritten.

```markdown
---
kind: expression
name: furious
char: nongtan
out: art/sprites/nongtan/nongtan_furious.png
base: art/sprites/nongtan/nongtan_cocky.png
refs: []
transparent: true
---

Edit this image and change only the facial expression; keep everything else exactly the same: ...

New expression: brows knotted, roaring with the mouth wide open

no fake details or fake textures; no text, watermark, signature or border; do not change the canvas size or the character position.
```

| Field | Meaning |
|---|---|
| `kind` | `sprite` base sprite · `expression` expression variant · `background` · `cg` event CG · `item` |
| `name` | The expression name, or the scene / CG / item name as written in the script (the player finds images by it) |
| `char` | The character a sprite or variant belongs to |
| `out` | Output image |
| `base` | The variant's base image (the base sprite) |
| `refs` | Reference images that keep designs consistent (e.g. a CG referencing the final scene image) |
| `transparent` | Whether a transparent background is required (default for sprites, variants and items) |
| `skip` | `true` means don't generate this one |
| `full_redraw` | `true` when a variant changes the whole character (e.g. turns into a ghost): no face compositing |

Rules:

- The body goes to the image backend verbatim, minus `<!-- comments -->`; `[art] always_append` is added at the end if it isn't there.
- Bodies that still contain `<!-- TODO` are not generated.
- The base sprite is the character's `default_expression`; every other expression is a variant edited from it.
- When the prompt, base or a reference changes, the image is stale and the next `replay art run` redraws it; the replaced image goes to `art/_raw/history/`.
- An image already at the output path that the tools didn't make (placed by hand) is adopted, never overwritten.

## Cue sheet: music.yaml

```yaml
battle: battle                    # cue switched to when a battle starts; the previous cue returns when it ends
cues:
  tavern:
    name: { en: Tavern, zh-CN: 酒馆 }
    style: Instrumental, no vocals, medieval fantasy tavern folk music, lute, fiddle, hand drum, cheerful, 112 BPM
    seconds: 160
  ending:
    name: Ending theme
    style: English, dark fantasy anime ending theme, warm clear female vocal, acoustic guitar, piano, 88 BPM
    lyrics: |
      [Verse]
      The mist has not yet lifted as we push the door
      ...
```

| Field | Meaning |
|---|---|
| `battle` | Cue switched to when a battle starts (defaults to the cue called `battle`) |
| `name` | Display name; the script's `[[bgm: ...]]` may use the display name or the cue ID |
| `style` | Genre, instruments, mood, tempo; write `Instrumental, no vocals` for instrumentals |
| `lyrics` | Lyrics with section tags such as `[Verse]`; without lyrics the cue is instrumental |
| `seconds` | Length to generate, 160 by default |

| File | Contents |
|---|---|
| `audio/bgm/takes/<cue-id>_s<seed>.flac` + `audio/bgm/takes.json` | Generated takes; files you put there as `<cue-id>_<anything>.flac` count as takes too |
| `audio/bgm/takes/<cue-id>_s<seed>.abc` | The score an instrumental was rendered from |
| `build/music_plans.json` | Seeds tried and how many notes each score had in its vocal part |
| `build/music_check.json` | Vocal check per take: recognized text, where, loudness |
| `audio/bgm/<cue-id>.flac` | The chosen take (copied by the music page or `replay music pick`) |

## Sound effects: sfx.yaml

Built-in synthesized sounds need no entry; this file is for the project's own.

```yaml
sounds:
  scream:
    name: scream
    voice: kent                   # in this character's voice
    tone: a bloodcurdling, piercing scream
    text: Aaaaaah!!
    max_seconds: 2.5
    space: upstairs
  zombie:
    name: zombies
    min_gap: 40
    space: behind-door
    layers:
      - { voice: hovat, tone: a slurred zombie moan, text: Uhh... ahh..., pitch: -4 }
      - { voice: oldnok, tone: a low zombie growl, text: Hrrr... ghh..., pitch: -3, at: 0.5, gain: 0.8 }
  creak:
    name: creak
    file: assets/creak.wav
```

| Field | Meaning |
|---|---|
| `name` / `aliases` | Names used in the script's `[[sfx: ...]]` |
| `voice` · `tone` · `text` | Whose voice, which delivery, what is shouted (generated by the voice backend) |
| `seeds` | Takes to generate; the loudest is used. Default `[11, 12]` |
| `max_seconds` | Keep only the loudest stretch of this length, 3 by default |
| `pitch` | Pitch shift in semitones; done by resampling, so lowering also slows down |
| `layers` | Several voices layered with offsets: each layer takes the fields above plus `at` (start second) and `gain` |
| `space` | Where the sound comes from: `dry` as is · `room` · `next-room` · `behind-door` muffled · `upstairs` through the floor |
| `min_gap` | Minimum seconds between two plays |
| `file` | Your own sound file |

`replay sfx` writes `audio/sfx/<sfx-id>.wav`; `audio/sfx/index.json` records each sound's file, aliases, duration and minimum gap, and the player looks sounds up there. `replay sfx --list` lists every sound and alias.

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
| `music-review.json` | Which take each BGM cue uses (`choice` is the chosen file) | cue ID |
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
