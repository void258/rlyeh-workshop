---
name: rlyeh-cast
description: Use in an R'lyeh Workshop project to write or complete the cast sheet cast.yaml (looks, expressions, nameplate colors, tone-to-expression rules, voice descriptions).
---

# Cast sheet

One entry per character in `cast.yaml`; character IDs are ASCII only. Format: [Project format · cast.yaml](https://github.com/void258/rlyeh-workshop/blob/main/docs/en/project-format.md#castyaml).

## When

`replay next` returns `cast.write`: the script has unregistered speakers, or characters are missing looks, expressions or voice descriptions.

## What each character needs

```yaml
characters:
  arlo:
    name: { en: Arlo, zh-CN: 阿洛 }
    kind: pc                      # pc | npc | narrator | gm
    player: Kobayashi             # pcs only; matches [players]
    color: "#c9a23a"              # nameplate color; keep characters distinct
    appearance: a trainee adventurer of about twenty, messy brown hair, worn leather armor...
    expressions:                  # 3–6 expressions: name → look
      calm: calm face, relaxed mouth
      wary: slight frown, alert eyes
      surprised: wide eyes, mouth slightly open
    default_expression: calm
    face_rules:                   # used when the script gives no [expression]; first match on the <tone> wins
      - [surprised, "surprised|startled"]
      - [wary, "hushed|wary|careful"]
    sprite: { scale: 1.0, head: [0.5, 0.17] }   # smaller scale for short characters; mouth sets where breath-fire starts
    voice: { gender: male, design: a clean, lively young man's voice in his twenties, faster when nervous }
```

- The narrator (`kind: narrator`) and the GM (`kind: gm`) only need a name and a voice.
- Without existing designs, infer looks, age and gender from the story and **tell the user which parts you inferred** so they can confirm (in production, "this character is actually a woman" and "make him a boy of eleven or twelve" were both changed at this step).
- Be concrete about looks: build, hair, clothes, signature items, colors — image prompts use this text directly.
- Choose expressions the character actually needs in the script; take `face_rules` keywords from the script's common tones.
- Voice descriptions cover gender, age, timbre and speech habits; match the character's gender; no dialect voices; tell characters apart by voice, not pitch shifting.

## Done when

`replay lint` has no "speaker not in cast.yaml" errors and `cast.write` is done in `replay next`. After changing looks or expressions, run `replay art jobs` for new expressions (existing prompts are never overwritten; edit them yourself).
