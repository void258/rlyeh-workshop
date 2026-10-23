# Script format

> Specification v0.1 draft. Chinese edition: [`docs/zh/script-format.md`](../zh/script-format.md)

A script is Markdown meant to be read by people, written by the AI and parsed by tools. One file per chapter, under `script/`, sorted by file name.

Every element has a **Chinese syntax** (full-width punctuation) and an **English syntax** (ASCII punctuation); both can be mixed in one file. In the tables below the Chinese syntax is on the left, the English one on the right.

## Front matter

Optional YAML front matter:

```markdown
---
chapter: 1
title: The Ram's Horn Inn
lang: en
---
```

Without front matter, the chapter number comes from the leading digits of the file name and the title from the first `# heading`.

## Elements

| Element | Chinese syntax | English syntax | Notes |
|---|---|---|---|
| Chapter title | `# 第一章　羊角旅馆` | `# Chapter 1: The Ram's Horn Inn` | Optional when there is front matter |
| Scene | `## 第一幕　迷雾边缘` | `## Act 1: Edge of the Mist` | Clears the stage and shows the scene title |
| Character line | `浓痰：台词` | `Phlegm: line` | The line follows the colon |
| Expression | `浓痰［暴怒］：台词` | `Phlegm[furious]: line` | Brackets directly after the name |
| Tone | `浓痰：〔怒吼〕台词` | `Phlegm: <roaring> line` | Voice only, never shown |
| Action | `（拍桌）` | `*slams the table*` | Shown, not voiced |
| Bleep | `{tm}` | `{damn}` | Shown as written; the line is voiced whole, then this span is replaced by a beep |
| Narration | `旁白：……` | `Narrator: ...` | The narrator's names are set in cast.yaml |
| OOC chat | `> 小林：……` | `> Kobayashi: ...` | Blockquote; voiced with the voice of the character that player plays |
| Stage direction | `【骰子：浓痰｜吐火｜19｜命中】` | `[[roll: phlegm \| breath-fire \| 19 \| hit]]` | On its own line |
| Line ID | trailing ` ^c1-0001` | same | Stable ID, see below |

A speaker can be written as the **display name** (`Phlegm`) or the **character ID** (`nongtan`); tools resolve both through cast.yaml. OOC speakers are player names (`Kobayashi`, `GM:void`), resolved through `[players]` in `replay.toml`.

### A full line

```
Name[expression]: <tone> text *action* {bleeped} text ^c1-0042
```

- The **tone** goes at the start of the text and becomes the voice model's bracketed direction (e.g. Drama 3's `[roaring]`). **Every voiced line should have a tone.** Without one the model guesses and often reads it flat or with the wrong emotion.
- The **expression** is optional. When omitted, the character's `face_rules` in cast.yaml pick one from tone keywords; if nothing matches, the default expression is used.
- **Actions** are shown but stripped before voicing.
- **Bleeped words** are shown normally (highlighted in the player). The whole line is voiced continuously, then forced alignment locates those words and replaces them with a beep. Letter abbreviations need a spoken form in `[spoken]` in `replay.toml`, otherwise the voice model can't pronounce them.

## Stage directions

Format: `【指令：参数｜参数｜…】`, or in English `[[command: arg | arg | ...]]`. Arguments are separated by `｜` or `|`.

| Chinese | English | Arguments | Effect |
|---|---|---|---|
| 章节 | `chapter` | title | Full-screen chapter card; clears the previous chapter's stage |
| 章节结束 | `chapter-end` | — | "The End" card; BGM fades out, the screen dims |
| 片尾 | `credits` | — | Credits roll (attribution generated automatically, see [Backends & licensing](backends.md)) |
| 背景 | `bg` | scene \| variant… | Change background; changing location clears the stage. Variants below |
| CG | `cg` | CG name | Full-screen CG with letterbox bars; sprites hidden |
| CG结束 | `cg-end` | — | Dismiss the CG |
| 登场 | `enter` | character \| position \| state | Brings a character on stage and keeps them there until `exit`. Position: `left/center/right` (`左/中/右`); state: `hurt` (`受伤`), `ghost` (`灵体`) |
| 退场 | `exit` | character | Leaves the stage; clears the state |
| 特效 | `fx` | effect | See below |
| 骰子 | `roll` | character \| skill \| value \| result | d20 roll animation; consecutive rolls merge into one group roll |
| 伤害 | `damage` | target \| amount | Damage number; a target with a sprite is brought on stage first |
| 对抗 | `contest` | A stat value \| B stat value \| result | Head-to-head panel, counting numbers, winner highlighted |
| 战斗开始 | `battle-start` | — | Battle banner; BGM switches to the battle cue |
| 回合 | `round` | name | Round banner |
| 战斗结束 | `battle-end` | — | End banner; BGM returns to the pre-battle cue |
| 道具 | `item` | item name | Item showcase |
| BGM | `bgm` | cue | Crossfade to a cue; empty (`[[bgm:]]`) fades out |
| 音效 | `sfx` | sound | Play a story sound effect (scream, growl…) |

**Roll results**: `hit / miss / success / failure / critical / fumble` (`命中 / 未中 / 成功 / 失败 / 大成功 / 大失败`). Values of 20 and 1 also show NATURAL 20 / NATURAL 1.

**Background variants** (combinable):

| Chinese | English | Effect |
|---|---|---|
| 黄昏 / 夜 / 暖光 / 黎明 / 晨雾 / 沉睡 | `dusk / night / warm / dawn / mist / dormant` | Color grading |
| 雾 | `fog` | Foreground fog particles |
| 窗外人影 | `shadows` | Figures moving outside the window |
| 围城 | `siege` | A pounding on the door every few seconds, dust falling from the beams |

**Effects**:

| Chinese | English | Effect |
|---|---|---|
| 震屏 | `shake` | Screen shake + low rumble |
| 闪白 | `flash` | White flash |
| 冲刺 | `dash` | Speed lines + push-in |
| 喷火 | `breath-fire` | Fire from the speaking character's mouth (position from `mouth` in cast.yaml) |
| 火焰 | `flames` | Flames rise along the bottom of the screen |
| 寒气 | `chill` | Frost border, until the next `exit` or background change |
| 晨光 | `dawn-light` | Light rays |
| 破门 | `door-break` | Heavy shake + flying splinters |

Unknown directions produce a lint warning and are skipped by the player. Backends and themes can register new directions and effects.

## Staging rules

Scripts don't say who stands where; the player stages automatically:

1. Whoever speaks comes on stage; at most three at once. When full, the one who has been silent longest leaves (characters placed with `enter` are never pushed off).
2. The speaker is lit, others are dimmed; during narration everyone is half-lit.
3. A new scene or location clears the stage; changing only a variant at the same location (e.g. adding `shadows`) does not.
4. On a single roll the roller comes on stage; a damage target with a sprite comes on stage before taking the hit.
5. Tones containing words like "roar, shout, scream, laugh…" make the sprite hop and the dialogue box shake.

## Line IDs

Every line, narration and OOC message has an ID. Voice files, review records and incremental rebuilds all rely on it.

- Default format `c<chapter>-<4-digit number>`, e.g. `c1-0042`.
- The ID sits at the end of the line: ` ^c1-0042` (space + `^` + ID). Studio and the player hide it.
- `replay ids` assigns IDs to lines without one and **never changes existing IDs**, so inserting a line doesn't shift every voice file after it.
- Scripts without IDs still work (lines are numbered in order), but then inserting a line in the middle misaligns every later voice file. Lint warns about this.

## Lint rules (replay lint)

**Errors** (must fix):
- Unparseable lines.
- Speaker not found in cast.yaml / `[players]`.
- Duplicate line IDs.
- Unknown direction with no plugin registering it; wrong argument count.
- Invalid `enter` position or state; non-numeric roll value.

**Warnings** (should fix):
- A voiced line without a tone.
- An expression that doesn't exist for that character in cast.yaml.
- A bleeped abbreviation without a spoken form in `[spoken]`.
- Digits or letters in a line without a reading in `[readings]` (e.g. `116`, `d4`).
- Missing line IDs.
- A voice reference text that duplicates a script line (it lures the voice model into reading on with the rest of the reference).

## Full example

A made-up scene using most elements, in English syntax:

```markdown
---
chapter: 1
title: The Fog Harbor Lighthouse
lang: en
---

[[chapter: Chapter 1: The Fog Harbor Lighthouse]]
[[bgm: title]]

## Act 1: The Empty Lighthouse

[[bg: lighthouse-ground | night | fog]]

Narrator: <suspenseful> The lighthouse had been dark for three days. ^c1-0001
Arlo[wary]: <whispering> It's locked from the inside. *raises the lantern* ^c1-0002
Mira: <impatient> Then we break it down. ^c1-0003

> Kobayashi: <teasing> Which of you has the higher Strength? ^c1-0004
> GM:void: <laughing> Roll a Strength check. ^c1-0005

[[roll: mira | strength | 20 | critical]]
[[fx: door-break]]
Mira[smug]: <laughing proudly> {Damn}, one kick! ^c1-0006

[[enter: keeper | center | ghost]]
[[fx: chill]]
Keeper: <weak, broken> Don't... don't light the lamp... ^c1-0007
[[exit: keeper]]
```

The same scene in Chinese syntax is in the [Chinese edition](../zh/script-format.md#完整示例).
