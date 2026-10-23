---
name: rlyeh-music
description: Use in an R'lyeh Workshop project to write the cue sheet music.yaml and project sound effects sfx.yaml, and to generate and check music.
---

# Music and sound effects

## Cue sheet (music.sheet)

Every name the script uses in `[[bgm: Harbor]]` needs a cue in `music.yaml`:

```yaml
battle: battle                    # cue switched to when a battle starts
cues:
  harbor:                         # cue ID, ASCII only
    name: { en: Harbor, zh-CN: 港口 }
    style: Instrumental, no vocals, foggy night harbor, celesta and harp ostinato, low cello drone, mysterious and lonely, 76 BPM
    seconds: 150
  ending:
    name: Ending theme
    style: English, dark fantasy anime ending theme, warm clear female vocal, acoustic guitar, piano, 88 BPM
    lyrics: |
      [Verse]
      ...
```

- Write each cue from the mood of its scenes: genre, instruments, mood, tempo (BPM). YuE2 works best with English.
- Instrumentals say `Instrumental, no vocals` and have no `lyrics`.
- The ending theme can be a song: write lyrics about this adventure in `[Verse]`, `[Chorus]` sections.
- The battle cue is `battle` (or named by `battle:`); it plays automatically at battle start, no need to write it in the script.

## Generating and choosing

1. `replay music gen` (background, minutes per cue): instrumentals first get a score only, retrying seeds until the vocal part has no notes, then render. **Tell the user how many cues and roughly how long first**; YuE2 needs ComfyUI running.
2. `replay music check`: speech recognition checks for sung words; don't use takes with `clean: false` in `build/music_check.json`.
3. **Choose takes** (`music.pick`, a person): ask the user to audition them on `/review/music`.

## Sound effects (sfx.yaml)

Built-in synthesized sounds (dice, hits, door break, gong, ghost, flames...) need no entry; `replay sfx --list` shows every name. Project sounds used in `[[sfx: ...]]` go in `sfx.yaml`:

```yaml
sounds:
  wail:
    name: wraith wail
    voice: wraith                 # generated in this character's voice
    tone: a piercing wail, like wind through a broken window
    text: Aaah... ooooh...
    max_seconds: 2.5
    space: room                   # dry · room · next-room · behind-door · upstairs
    min_gap: 0                    # minimum seconds between plays
```

## Rules

- YuE2's weights are CC BY-NC 4.0: **non-commercial only**, credited automatically; for commercial use, switch to the manual backend with music the user has rights to.
- Repeating a sound too often gets tiresome: give sieges, zombie moans and the like a `min_gap` (e.g. 40 seconds).
