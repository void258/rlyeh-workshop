---
name: rlyeh-theme
description: Use in an R'lyeh Workshop project to design a player theme (colors, fonts, dialogue box, banner wording) that fits the campaign's genre and mood, and to preview it with screenshots.
---

# Designing a player theme

The player's look comes from a theme. Three are built in: `dark-fantasy` (default; gold-ruled dark fantasy), `noir` (case files: paper dialogue box, ink, seal red) and `neon` (cyan and magenta neon, square corners, scanlines). Full reference: [Player themes](https://github.com/void258/rlyeh-workshop/blob/main/docs/en/theming.md).

## When

`replay next` returns `player.theme` (optional), or the user wants a different look. If the user settles on the default theme, run `replay done player.theme`.

## Steps

1. **Read the campaign**: genre, era, tone (horror, comedy, epic, mystery), main locations, `[art] style`, the colors of existing backgrounds and sprites.
2. **Try the built-ins first**: `replay theme preview --theme noir` (no config change) and look at `build/theme-preview/<theme>.png`. If one fits, set `[player] theme = "noir"` in `replay.toml` and you're done.
3. **Design your own**: `replay theme new --base <closest built-in>` creates `theme/theme.toml` (every design variable commented out with its current value and description) and `theme/theme.css`, and sets `[player] theme = "theme"`.
4. Write a one-sentence design note in `description`, e.g. "cold blue fog in a harbor town, the feel of an old ship's log".
5. Edit `[vars]`:
   - colors: take key colors from backgrounds and sprites; set `accent`, `accent-hi`, `text`, `box-bg`; the `good` / `bad` / `fumble` result colors must be told apart at a glance;
   - fonts: `font-body`, `font-ui`, `font-display` — common system fonts, or redistributable (OFL etc.) font files placed in `theme/fonts/` and listed under `[fonts]`;
   - shapes: `box-radius`, `nameplate-shape`, `box-corner` (`none` removes the ornament).
6. What variables can't do (textures, layout, animation) goes in `theme/theme.css`; put images in `theme/images/` and reference them with relative paths.
7. Banner and credits wording in the campaign's voice: `battleStart`, `battleEnd`, `victory`, `replayTag`... under `[text.en]`.
8. `replay theme preview`, look at the overview sheet, revise until it works; if you can't see images, give the user the sheet's path.

## Checklist

- Dialogue text stays readable over the brightest and darkest backgrounds (contrast at least 4.5:1);
- narration, lines and OOC chat are distinct at a glance;
- nameplate colors come from the characters (`var(--c)`); don't override them;
- no fonts or images from the web (rendering is offline);
- don't hide dice results or damage numbers with `display: none`;
- `replay build` prints no "unknown design variable" warnings.
