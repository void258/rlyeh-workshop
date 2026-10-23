---
name: rlyeh-voice
description: Use in an R'lyeh Workshop project to design voices, synthesize voice lines, read the voice QA report, decide on reading fixes or redos, and bleep profanity.
---

# Voices

## Flow

1. **Voice candidates** (`voice.design`): `replay voice design` makes 3 candidates per character from `voice.design` in cast.yaml.
2. **Pick voices** (`voice.pick`, a person): ask the user to audition them on the `/voices` page of `replay preview`. **Don't choose for them.**
3. **Synthesize** (`voice.build`): `replay voice build`, in the background (`rlyeh_run_stage voice.build`).
4. **QA** (`voice.qa`): `replay voice qa` recognizes each line back to text and compares it, and checks durations.
5. **Handle failures** (`voice.fix`, you): see below.
6. **Line review** (`voice.review`, a person): ask the user to listen on `/review/voice`; redo lines they mark with `replay voice redo --marked`.
7. **Bleep** (`voice.bleep`): `replay bleep` replaces the words in `{}` with a beep.

## Reading QA (voice.fix)

`replay voice qa` writes `build/voice_qa.json` (or use `rlyeh_qa_report stage=voice failed_only=true`): `sim` similarity, `heard` recognized text, `seconds`, `too_long`. For each failed line:

- **The recognizer misheard** (homophones, proper nouns, interjections): let it pass.
- **Actually misread**:
  - numbers, letters or nicknames misread → add a reading in `[readings]` of `replay.toml` (voice only, subtitles unchanged), then `replay voice redo --ids <id>`;
  - the line is too long or too repetitive → rewrite it in the script (fewer repetitions), then redo;
  - just a bad take → `replay voice redo --ids <id>` with new seeds, up to 5 seeds.
- **Too long** (`too_long`: the model couldn't stop): almost always needs a rewrite.

When the rest are acceptable, run `replay done voice.fix`.

## Rules

| Rule | Why |
|---|---|
| One fixed reference per character | Don't use earlier outputs as references for later lines: errors accumulate and the model reads on with the reference's words |
| Reference text must not repeat a script line | Otherwise the model continues with the rest of the reference on that line |
| A chosen reference is too slow or deep | Add extra references in the same voice with normal pacing (`replay voice extra <char>`, texts in `voice.extra_texts`); **keep the voice the user picked** |
| Whole lines in one pass | Tones become the model's bracketed directions; profanity is spoken and bleeped later |
| Numbers and letter abbreviations | Need readings in `[readings]` / `[spoken]` |
| QA thresholds | similarity ≥ 0.75, recognized length ≤ 1.4× the line, duration ≤ 2.5 s + 0.42 s per character |
| Cloning a real person's voice | Only with their consent; designed synthetic voices by default |
