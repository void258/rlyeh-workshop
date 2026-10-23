# Pipeline

> Specification v0.1 draft. Chinese edition: [`docs/zh/pipeline.md`](../zh/pipeline.md)

The pipeline is a series of **stages**. Each stage lists what it reads, what it produces, what the AI does, what the tools do, where a person must review, and the **defaults** learned in production.

## Tasks and state

- Each stage is broken into **tasks** of three kinds:
  - `agent`: work that needs judgment, done by the AI — e.g. polishing a chapter, writing a batch of image prompts;
  - `tool`: run to completion by the tools — e.g. voice synthesis, rendering;
  - `review`: waits for a person — e.g. picking voices, line-by-line listening.
- `replay next` returns the next thing to do (JSON); the AI does it and reports `replay done <task-id>`.
- Stage states: `todo` → `running` → `review` (waiting for a person) → `done`; when inputs change, `stale`. See [Project format · State](project-format.md#state-and-incremental-rebuilds-rlyehstatejson).
- Every stage can be re-run and only redoes stale or missing parts.

```json
{
  "id": "voice.qa.c1",
  "kind": "agent",
  "stage": "voice",
  "title": "Read the chapter 1 voice QA report; decide which lines need a reading fix or a redo",
  "inputs": ["build/voice_qa.json"],
  "playbook": "rlyeh-voice",
  "blocked_by": []
}
```

## 1. Import

- **Reads**: original exports in `logs/raw/`.
- **Produces**: `logs/events.jsonl`, one message or roll per line: time, speaker, character, text, OOC flag, roll result.
- **Tools**: parse per format; **merge overlapping exports and deduplicate** (production had several FVTT exports with overlapping time ranges); split into sessions.
- **Human**: confirm every player agrees to the replay being published; optionally replace player names with aliases (alias table in `replay.toml`).
- First importers: Foundry VTT chat export, plain text. Later: QQ dice-bot logs (e.g. SealDice), Discord, Roll20.

## 2. Script

- **Reads**: `logs/events.jsonl`, cast.yaml if present.
- **Produces**: `script/*.md`, see [Script format](script-format.md).
- **AI**:
  - Polish into a readable script; never paste the raw log. Split into chapters and scenes.
  - Rewrite character lines in each character's voice; narration covers actions and setting; table chatter is kept as OOC chat.
  - Give every voiced line a tone; keep profanity as written and mark it with `{}`.
  - Add stage directions: backgrounds, CGs, rolls, damage, battles, BGM, sound effects.
- **Tools**: `replay lint`; `replay ids`.
- **Human** (optional): review the script in Studio; notes go to `review/script-review.json`.

## 3. Cast

- **AI**: with no existing character sheets, infer appearance, age and gender from the story; give each character 3–6 expression variants (with descriptions), a name-plate color, tone→expression rules and a voice description.
- **Human**: confirm the designs. Production examples: "Guwa is female" and "make Bester an 11–12-year-old boy" were both changed at this step.

## 4. Voices

- **AI**: write a voice design prompt per character (gender, age, timbre, speaking habits).
- **Tools**: generate 3 audition candidates per character (e.g. Qwen3-TTS VoiceDesign).
- **Human**: pick one on Studio's voice page (`review/voice-pick.json`); the tools record it as that character's **fixed reference**.
- **Defaults**:
  - One fixed reference per character. **No rolling references** (using recent outputs as references for the next line): errors accumulate, voices grow more robotic over time, and the model reads on with lines from the reference.
  - The reference audio's text **must not duplicate any script line**, or the model reads on with the rest of the reference when it reaches that line.
  - If the chosen reference is too slow or too low (e.g. a narrator), add a few extra references in the same voice reading ordinary-paced sentences to dilute the delivery — **never swap out the voice the user picked**.
  - Voices match each character's gender; no dialect voices; characters are told apart by different voices, not pitch shifting.

## 5. Voice acting

- **Tools**:
  - Each line is **synthesized whole and continuous**: the tone becomes the model's bracketed direction; profanity is spoken (bleeping happens next).
  - QA: speech recognition transcribes every line; similarity to the script is compared syllable by syllable, and duration is checked for outliers.
  - Failing lines are retried with new seeds, up to 5.
- **AI**: read the QA report. Recognizer mistakes can pass; real misreadings get a reading fix (`[readings]`) or a rewording, then a redo.
- **Human**: listen line by line on Studio's review page; lines marked "redo" go back to the tools.
- **Defaults**:

| Rule | Default |
|---|---|
| Minimum QA similarity (per syllable) | 0.75 |
| Max recognized / scripted length ratio | 1.4 |
| Max duration | 2.5 s + 0.42 s per character + 0.5 s per ellipsis |
| Retry seeds | 123, 7, 42, 2026, 99 |
| Digits, letter abbreviations | Must have a reading in `[readings]` / `[spoken]` |
| Long repetitions (e.g. a name shouted eight times) | Shorten the reading; otherwise the model never stops (one take ran 65 seconds) |

## 6. Bleeping

- **Tools**: forced alignment (Chinese: FunASR fa-zh) gives each character's start and end; `{}` spans are replaced with a 1 kHz beep in `audio/voice-bleep/`.
- **Defaults**:
  - Pad 40 ms on each side.
  - When the word starts or ends the line, cover all the way to the start or end of the clip: aligners often place the start after an aspirated consonant, leaking half a syllable.
  - Transcribe again after bleeping to confirm the word is no longer audible.

## 7. Art

- **AI**: write image prompts from cast.yaml and the script: shared style + subject + composition; every prompt gets `[art] always_append` (default "no fake details or fake textures", which reduces noise).
- **Tools**: call the image backend; build overview sheets; composite expressions.
- **Human**: approve or reject each image on Studio's art page, with notes.
- **Defaults**:
  - Generate sprites **with transparent backgrounds directly**; don't generate on a solid color and key it out — the color reflects onto the character (a magenta background tinted an orc's skin purple).
  - Expression variants: edit the base sprite with a prompt that pins "head angle, size and position unchanged, change only the face"; then **paste only the face region back onto the base sprite**, keeping the base outline and alpha. Edited outputs have low-resolution alpha with jagged, hazy edges.
  - Keep designs consistent across scenes and CGs: settle on one reference image (e.g. the face-tree scene) and pass it to the image backend when generating related CGs.
  - Gore tends to trip image services' safety filters; rewrite it as bloodless horror.
  - When generating through Codex: the driving AI writes the prompt and Codex uses it verbatim; cap the model and effort; Codex must not research or look for references on its own (see [Agent integration](agents.md#generating-images-with-codex)).

## 8. Music

- **AI**: write a cue list per scene (mood, instrumentation, tempo) and place `[[bgm: …]]` in the script.
- **Tools**: generate, check, make loopable versions.
- **Human**: pick a take for each cue on the audition page.
- **Defaults**:
  - Music models tend to sing over "instrumental" tracks (YuE2 hummed English lyrics in production). Fix: **generate only the score first, change seeds until the vocal part has no notes at all, then render audio from that score.** Merely replacing vocal notes with rests doesn't reliably work.
  - Run speech recognition on the result; discard takes where it transcribes running text.
  - Limit generation to 2–3 minutes and crossfade-loop during playback.
  - The credits song may have lyrics, written by the AI about the adventure.
  - Battle cues switch automatically on battle start and back on battle end; scripts don't need to say so.

## 9. Sound effects

- **Tools**: a built-in procedurally synthesized SFX library (dice, hits, whooshes, fire breath, door break, gong, victory…), attached automatically to staging:
  - Rolls: rattle + a result sting; a miss adds a whoosh.
  - Damage: the hit sound follows the weapon of the preceding attack (blunt, blade, heavy, burn); with no attack, it's a monster hit.
  - Story effects (scream, growl, zombies) are triggered by `[[sfx: …]]` in the script and can be generated by the voice model in a character's voice.
- **Defaults**: give repeated effects a minimum gap (e.g. zombie groans at least 40 s apart); too much repetition gets tiresome.

## 10. Player

- **Tools**: `replay build` packages script, cast and assets into `build/player/` (open `index.html` in a browser, or `/player` in `replay preview`): images become WebP and avatars are cropped; audio is hard-linked or copied, never transcoded; directions are rewritten to their canonical English names and values, and character names to character IDs. Missing voice lines, images, sounds and cues are listed.
- Player features: title screen, chapter cards, scene titles, sprite staging, tone-driven expressions, OOC chat feed, rolls / damage / contests / battle banners, CGs, items, effects, credits, backlog, auto-play, skip, start from any line. The interface follows the project language (Chinese / English).
- **Defaults**:
  - Credits are generated: game master, players and their characters, the cast, any sections in `[credits] staff`, then art, voice design, voices, music (with license, e.g. YuE2's CC BY-NC 4.0), sound effects and session logs according to the backends actually used; attribution a backend requires (e.g. "Built with Fish Audio") always appears.
  - The hit sound for damage follows the skill of the previous roll (sword, dagger → slash; hammer, pick → heavy; fire → burn; club, staff, sling → blunt), heavy otherwise; change it in `[player] hit_sounds`.
  - Breath fire comes out of the mouth of the most recent speaker who has `sprite.mouth` in cast.yaml.
  - Background variants set the atmosphere: fog and mist bring fog, warm / dawn / dusk bring warm motes, dormant brings spores, and siege thumps the door every few seconds with dust falling from the beams (sounds marked `ambient: siege` in sfx.yaml join in).

## 11. Render

- **Tools**:
  - Load the player's record mode in a headless browser with an injected **virtual clock**: timers, animation frames, `performance.now` and randomness are all controlled by the renderer; CSS animations and transitions are paused and set to the exact virtual time each frame.
  - Advance 1/fps seconds, capture, hand to ffmpeg. Each frame depends only on the timeline; nothing is dropped, and every render is identical.
  - No audio plays in the browser: the player logs when each voice line, effect and BGM cue happens, and the mix is built offline from that log (BGM ducked under speech, crossfaded loop seams, loudness normalized to -16 LUFS).
  - Chapters render in parallel and are concatenated (chapters are separated by black, so there's no seam).
- **Commands**: `replay render` renders everything; `--from <line-id> --seconds 60` renders a preview stretch; `--chapter 2` one chapter; `--remix` redoes only the mix. Output in `build/video/`: `<name>.mp4` final, `<name>_video.mp4` silent picture, `<name>_events.json` event log, `<name>_audio.wav` mix.
- Requires playwright (`uv sync --extra render` or `pip install "rlyeh-workshop[render]"`, then `playwright install chromium`) and ffmpeg. `[render] browser = "msedge"` or `"chrome"` uses an installed browser instead.
- **Defaults**: **never screen-record in real time** — it drops frames and takes as long as the video. For audio-only changes use `replay render --remix` without re-rendering frames.
- **Human** (optional): watch the cut and send problems back to the relevant stage.

## 12. Encode

| Preset | Use | Defaults (measured on 40 min of 1080p60) |
|---|---|---|
| `master` | Master: the file `replay render` writes | H.264 NVENC cq19, ~4.6 GB |
| `share` | Sharing | Tuned AV1 NVENC cq37 (32-frame lookahead, 4 B-frames as references, temporal filtering, 10 s keyframes), ~500 MB; or CPU SVT-AV1 crf38, ~360 MB; audio copied |
| `compat` | Older devices, the web | H.264 cq26, AAC 160k |

`replay encode share` → `build/video/<name>_share.mp4`. The tools detect hardware encoders (NVENC / QSV / AMF), try each on a short clip first, and fall back to CPU. Presets can be changed or added under `[encode.<name>]` (see [Project format](project-format.md#replaytoml)).
