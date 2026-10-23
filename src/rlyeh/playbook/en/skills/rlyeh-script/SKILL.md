---
name: rlyeh-script
description: Use in an R'lyeh Workshop project to write the script from the session log, polish lines, add tones and stage directions, and fix lint errors.
---

# Writing the script

Turn the imported log (`logs/events.jsonl`) into `script/*.md`. The full format is in [Script format](https://github.com/void258/rlyeh-workshop/blob/main/docs/en/script-format.md).

## When

`replay next` returns `script.write` (write or extend the script from the log) or `script.lint` (fix lint errors).

## Format at a glance

```markdown
---
chapter: 1
title: Fog Harbor Lighthouse
lang: en
---

[[chapter: Chapter 1 Fog Harbor Lighthouse]]
[[bgm: Harbor]]

## Act 1: The Dark Lamp

[[bg: Fog harbor pier | night | fog]]
Narrator: <with suspense> The lighthouse of Fog Harbor has been dark for three days.
Arlo[wary]: <hushed> The door is locked from the inside. *raises the lantern*
Ironhammer: <cursing> {damn} it, stand back!
> Yuzu: <laughing> Dwarves always take the direct route.
[[roll: Vera | Perception | 18 | success]]
```

- Lines: `Character[expression]: <tone> text *action* {bleep} text`. The expression is optional; **give every voiced line a <tone>**; actions are shown but not voiced; profanity is written as is inside `{}`.
- Narration: `Narrator: ...`; OOC chat: `> PlayerName: ...` (the player must be in `[players]`).
- Stage directions on their own line: chapter, chapter-end, credits, bg (scene | variants...), cg, cg-end, enter (char | left/center/right | hurt/ghost), exit, fx (shake / flash / dash / breath-fire / flames / chill / dawn-light / door-break), roll (char | skill | value | hit/miss/success/failure/critical/fumble), damage (target | amount), contest (A stat value | B stat value | result), battle-start, round, battle-end, item, bgm (cue name; empty fades out), sfx.
- Background variants: dusk, night, warm, dawn, mist, dormant, fog, shadows, siege.
- **Don't write line IDs by hand** (the trailing `^c1-0001`): run `replay ids` afterwards, and never change existing IDs.

## How

1. Read the log in pages (`rlyeh_read_log`, or line by line), one session at a time; list the main events, then split into chapters and acts.
2. Rewrite lines in each character's voice so they read as a script, not a chat log; turn GM narration into the narrator; keep the fun table talk (jokes, banter, rules chat) as OOC lines.
3. **Polish, don't change facts**: who did what, roll values and results and damage numbers stay as logged, written as directions (`[[roll: ...]]`, `[[damage: ...]]`, `[[contest: ...]]`); don't invent events.
4. Add stage directions: change the background when the place changes; use CGs for big moments; battle-start / round / battle-end for fights; change music at turns of mood (cue names go into `music.yaml`, see `rlyeh-music`).
5. Numbers, letters and nicknames with unclear pronunciation get a reading in `[readings]` of `replay.toml` (voice only, subtitles unchanged); spell out how bleeped abbreviations are spoken in `[spoken]`.
6. Trim very long repetitions (a name shouted eight times): the voice model can't stop.
7. When done: `replay lint` → fix errors → `replay ids` → `replay done script.write`.

## Lint

`replay lint` (or `rlyeh_lint`) errors must be fixed: speaker not in `cast.yaml` (have `rlyeh-cast` add the character), OOC speaker not in `[players]`, wrong direction names or arguments, duplicate IDs. Handle warnings where you can: no tone, unknown expression, numbers without readings.
