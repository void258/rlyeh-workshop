---
name: rlyeh-art
description: Use in an R'lyeh Workshop project to write image prompts (sprites, expressions, backgrounds, CGs, items), generate images, and handle art review notes.
---

# Art

One prompt file per image, `art/prompts/<kind>/<name>.md`: the front matter gives the kind, output path, base and reference images; the body is the prompt, sent to the image backend verbatim. Format: [Project format · image prompts](https://github.com/void258/rlyeh-workshop/blob/main/docs/en/project-format.md#image-prompts-artprompts).

## Flow

1. `replay art jobs` writes starter prompts for images that have none. Sprites are already assembled from looks and expressions; backgrounds, CGs and items keep a `<!-- TODO -->`.
2. **You write** (`art.prompts`): replace each TODO with a concrete description (see below).
3. `replay art run` generates images (in the background). Expression variants are composited automatically: only the face goes back onto the base sprite.
4. `replay art check` checks transparency and builds overview sheets in `art/_overview/*.png`. If you can see images, look at them.
5. **Review** (`art.review`, a person): ask the user to approve or reject each image on `/review/art`.
6. **Rejected images** (`art.redo`): read the notes in `review/art-review.json` (or `rlyeh_reviews kind=art`), revise those prompts, then `replay art run --marked`.

## Writing prompts

- A prompt = style (`[art] style`) + subject + composition + things to avoid; `[art] always_append` (by default "no fake details or fake textures") is appended automatically.
- **Backgrounds**: place, time, light, weather, mood, what is in the scene; **no people**; keep the bottom third simple for the dialogue box.
- **CGs**: who does what, the shot, the light; characters must look like their sprites (include their looks); to match a final image, add its path to `refs` in the front matter.
- **Items**: material, shape, colors, features; a single object on a transparent background.
- Keep one style per campaign; the same place at another time is a background variant (night, dusk...), not a new image.
- Gore tends to be blocked by image services: write horror without blood.
- Mark images you don't want with `skip: true`; variants that change the whole character (e.g. into a ghost) get `full_redraw: true`.

## Rules

- Generate sprites on a transparent background directly; never a solid background to cut out later (the color reflects onto the character).
- Expression variants change only the facial features: head angle, size and position stay.
- With Codex: you write the prompt and it's passed verbatim; only the model and effort in `[harness.codex]` are used; **tell the user how many images a real batch will draw before starting it**.
- Images the tools didn't make are never overwritten: files the user puts in place are adopted.
