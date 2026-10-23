# Player themes

> Specification v0.1 draft. Chinese edition (authoritative): [`docs/zh/theming.md`](../zh/theming.md)

The look of the player (dialogue box, nameplates, OOC chat, dice, banners, chapter cards, title screen, credits...) comes from a **theme**. The default, "dark fantasy", comes from *Shadow of the Demon Lord · Ram's Horn Inn*; other campaigns can switch to a built-in theme or have the AI design one that fits the campaign.

```toml
# replay.toml
[player]
theme = "noir"          # a built-in theme, or a theme folder in the project (e.g. "theme")
```

## Built-in themes

| ID | Look | Good for |
|---|---|---|
| `dark-fantasy` | Gold rules, dark frosted dialogue box, gilded chapter names (default) | Fantasy, medieval |
| `noir` | Yellowed paper dialogue box, ink type, seal red, typewriter labels, sepia film grain | Cthulhu, detectives, 1920s, Victorian |
| `neon` | Dark blue glass panels, cyan and magenta neon, square corners, monospace, scanlines | Cyberpunk, space, tech wastelands |

`replay theme list` lists every theme; `replay theme preview --theme noir` shows a theme on this campaign without changing the config.

## Theme folder

```
theme/
├── theme.toml     name, description, base theme, design variables, wording, fonts, images
├── theme.css      optional: any extra styles
├── fonts/         optional: bundled fonts
└── images/        optional: textures, ornaments, avatars
```

`replay theme new` creates one: `theme.toml` lists every design variable (commented out, with the value in effect and a description), `theme.css` describes the page structure, and `replay.toml` gets `[player] theme = "theme"`. `--base noir` starts from another theme.

### theme.toml

```toml
name = "Fog Harbor · Night Watch"
base = "noir"                    # apply this theme first, then what is written below (defaults if omitted)
description = "Cold blue foggy nights, harbor mystery"

[vars]                           # design variables; values are CSS
accent = "#7fb3c9"
box-bg = "linear-gradient(180deg, rgba(10, 20, 28, .82), rgba(4, 8, 12, .94))"
font-display = "'Harbor Serif', 'Noto Serif SC', serif"

[text]                           # interface wording for every language
replayTag = "HARBOR FILE"

[text.en]                        # English projects only
battleStart = "Ambush"
results = { success = "Success", critical = "Critical" }

[text.zh-CN]                     # Chinese projects only
battleStart = "遇袭"

[fonts]                          # family name = file in the theme folder
"Harbor Serif" = "fonts/HarborSerif.woff2"

[images]
gm_avatar = "images/gm.png"      # avatar of GM chat bubbles
```

There are seventy-odd **design variables** in groups: fonts (`font-body`, `font-ui`, `font-display`), colors (`accent`, `accent-hi`, `text`, `good`, `bad`, `fumble`...), dialogue box (`box-*`, `text-size`, `nar-*`), nameplate (`nameplate-*`), dice panel (`panel-*`, `die-*`), OOC chat (`chat-*`), metallic text and banners (`metal`, `banner-*`, `combat-*`, `damage-text`), full-screen pages (`card-*`, `title-shade`, `log-bg`, `credits-bg`, `vignette`) and particles (`fx-*` written as "R, G, B", `flash-battle`). The full list with defaults and descriptions is the `:root` block at the top of [`player.css`](../../src/rlyeh/player/static/player.css); the `theme.toml` written by `replay theme new` has all of them too. `replay build` warns about unknown variables.

**Wording**: `battleStart` `encounter` `battleEnd` `victory` `round1` `roundTag` `combat` `end` `itemTag` `vs` `natural` `replayTag` `oocHead` `narrator` `ooc`, plus `results` (`success` `failure` `critical` `fumble` `hit` `miss`).

### theme.css

Loaded after `player.css` and the variables; use it for what variables can't do: other layouts, textures, shapes, animations. The same selectors here override the defaults, and `@keyframes` of the same name can be redefined. Reference images and fonts with relative paths (`url("images/paper.png")`).

Page structure (the stage is a fixed 1920×1080, scaled to the window):

| Element | Contents |
|---|---|
| `#world` | background `#bg`, particles `#atmo`, sprites `#chars > .char`, CG `#cg`, vignette `#vignette` |
| `#hud` | dice `.dice-panel > .die-col` (`.good` `.bad` `.fumble` `.crit`), damage `.dmg`, contest `.vs-panel`, banners `.banner` (`.round` `.end`), items `.item-show` |
| `#ui` | scene title `#scene-title`, combat strip `#combat`, OOC chat `#chat > .bub` (`.gm`), dialogue box `#box` (`.nar` for narration) `> .nameplate .text .narmark .orn`, buttons `#controls` |
| Full-screen pages | chapter card `#card` (`.cc-num` `.cc-name` `.cc-end`), credits `#credits` (`.cr-title` `.cr-h` `.cr-p`), backlog `#log`, title screen `#title` |

`<body>` carries `.theme-<theme id>`, plus `.rec` while rendering.

## Preview

```bash
replay theme preview                 # the current theme
replay theme preview --theme neon    # try another without changing the config
```

It stages a sample scene with this campaign's own characters, backgrounds and items (narration, a two-person exchange, a bleeped word, OOC chat, two dice including a critical, battle start, damage, a contest, an item, a round, battle end, chapter end, credits), renders it frame by frame, takes a screenshot as each moment settles into `build/theme-preview/<theme>/`, and lays them out in one overview, `build/theme-preview/<theme>.png`.

## Design process for the AI

The agent driving the project designs a campaign's theme in these steps (the `rlyeh-theme` skill in the playbooks says the same):

1. **Read the campaign**: genre, era, tone (horror, comedy, epic, mystery), main locations, the art style (`[art] style`), the colors of existing backgrounds and sprites.
2. **Pick a direction**: start from the closest built-in theme as `base` and write a one-sentence design note (in `description`), e.g. "cold blue fog in a harbor town, the feel of an old ship's log".
3. **Colors**: take the key colors from backgrounds and sprites; set `accent`, `accent-hi`, `text` and the box background; success / failure / fumble must be told apart at a glance.
4. **Fonts**: common system fonts, or redistributable fonts (OFL etc.) bundled in the theme folder; never web fonts — rendering is offline.
5. **Shape and texture**: corner radius, nameplate shape, corner ornaments, textures; write `theme.css` when variables aren't enough.
6. **Wording**: banner and credits labels in the campaign's voice (`[text.zh-CN]` / `[text.en]`).
7. **Preview, look, revise**: run `replay theme preview` and look at the overview; harnesses that can see images judge for themselves, others hand it to a person.

Checklist:

- Dialogue text stays readable over the brightest and darkest backgrounds (contrast at least 4.5:1);
- Narration, lines and OOC chat are distinct at a glance;
- Nameplate colors come from the characters (`var(--c)`); don't override them;
- No fonts or images from the web;
- Don't hide information such as dice results or damage numbers with `display: none`.
