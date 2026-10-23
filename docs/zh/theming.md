# 播放器主题

> 规格 v0.1 草稿。英文版：[`docs/en/theming.md`](../en/theming.md)

播放器的界面风格（对话框、名牌、场外弹幕、骰子、横幅、章节卡、标题画面、片尾……）由**主题**决定。默认主题「黑暗奇幻」来自《魔王之影 · 羊角旅馆》；别的团可以换内置主题，也可以让 AI 按这个团的气质设计一套自己的。

```toml
# replay.toml
[player]
theme = "noir"          # 内置主题名，或者项目里的主题文件夹（例如 "theme"）
```

## 内置主题

| ID | 风格 | 适合 |
|---|---|---|
| `dark-fantasy` | 金色描边、暗色毛玻璃对话框、烫金章节名（默认） | 奇幻、魔幻、中世纪 |
| `noir` | 泛黄的纸质对话框、墨色铅字、印章红、打字机标签、老胶片的褐色和颗粒 | 克苏鲁、侦探、民国、维多利亚 |
| `neon` | 深蓝玻璃面板、青色和品红霓虹、直角、等宽字体、扫描线 | 赛博朋克、星际、科技废土 |

`replay theme list` 列出全部主题；`replay theme preview --theme noir` 不改配置就能看某个主题套在这个团上的样子。

## 主题文件夹

```
theme/
├── theme.toml     名字、说明、基于哪个主题、设计变量、界面文字、字体、图片
├── theme.css      可选：任意额外样式
├── fonts/         可选：主题自带的字体
└── images/        可选：纹理、花纹、头像
```

`replay theme new` 新建一个：`theme.toml` 里把全部设计变量列好（注释掉，带当前生效的值和说明），`theme.css` 里写好画面结构，并在 `replay.toml` 里写上 `[player] theme = "theme"`。`--base noir` 从某个主题出发。

### theme.toml

```toml
name = "雾港 · 灯塔守夜"
base = "noir"                    # 先套用这个主题，再改下面写的（不写就从默认值开始）
description = "冷蓝雾夜，海港悬疑"

[vars]                           # 设计变量，值就是 CSS
accent = "#7fb3c9"
box-bg = "linear-gradient(180deg, rgba(10, 20, 28, .82), rgba(4, 8, 12, .94))"
font-display = "'Harbor Serif', 'Noto Serif SC', serif"

[text]                           # 界面上的固定文字，所有语言都生效
replayTag = "HARBOR FILE"

[text.zh-CN]                     # 只对中文项目生效
battleStart = "遇袭"
results = { success = "成功", critical = "大成功" }

[text.en]                        # 只对英文项目生效
battleStart = "Ambush"

[fonts]                          # 字体名 = 主题文件夹里的文件
"Harbor Serif" = "fonts/HarborSerif.woff2"

[images]
gm_avatar = "images/gm.png"      # GM 弹幕的头像
```

**设计变量**一共七十多个，分几组：字体（`font-body`、`font-ui`、`font-display`）、颜色（`accent`、`accent-hi`、`text`、`good`、`bad`、`fumble`……）、对话框（`box-*`、`text-size`、`nar-*`）、名牌（`nameplate-*`）、骰子面板（`panel-*`、`die-*`）、场外弹幕（`chat-*`）、金属字和横幅（`metal`、`banner-*`、`combat-*`、`damage-text`）、全屏页（`card-*`、`title-shade`、`log-bg`、`credits-bg`、`vignette`）、特效粒子（`fx-*` 写成「R, G, B」三个数，`flash-battle`）。完整列表、默认值和说明就是 [`player.css`](../../src/rlyeh/player/static/player.css) 开头的 `:root`，`replay theme new` 生成的 `theme.toml` 里也全有。写了不认识的变量，`replay build` 会提醒。

**界面文字**：`battleStart` `encounter` `battleEnd` `victory` `round1` `roundTag` `combat` `end` `itemTag` `vs` `natural` `replayTag` `oocHead` `narrator` `ooc`，以及 `results`（`success` `failure` `critical` `fumble` `hit` `miss`）。

### theme.css

在 `player.css` 和设计变量之后载入，写变量做不到的事：换版式、加纹理、改形状、加动画。同样的选择器写在这里就会盖过默认样式；同名的 `@keyframes` 也能重新定义。图片、字体用相对路径引用（`url("images/paper.png")`）。

画面结构（舞台固定 1920×1080，按窗口缩放）：

| 元素 | 内容 |
|---|---|
| `#world` | 背景 `#bg`、氛围粒子 `#atmo`、立绘 `#chars > .char`、CG `#cg`、暗角 `#vignette` |
| `#hud` | 骰子 `.dice-panel > .die-col`（`.good` `.bad` `.fumble` `.crit`）、伤害 `.dmg`、对抗 `.vs-panel`、横幅 `.banner`（`.round` `.end`）、道具 `.item-show` |
| `#ui` | 幕名 `#scene-title`、战斗条 `#combat`、场外弹幕 `#chat > .bub`（`.gm`）、对话框 `#box`（`.nar` 旁白）`> .nameplate .text .narmark .orn`、按钮 `#controls` |
| 全屏页 | 章节卡 `#card`（`.cc-num` `.cc-name` `.cc-end`）、片尾 `#credits`（`.cr-title` `.cr-h` `.cr-p`）、对话记录 `#log`、标题画面 `#title` |

`<body>` 上有 `.theme-<主题ID>`，渲染时还有 `.rec`。

## 预览

```bash
replay theme preview                 # 用当前主题
replay theme preview --theme neon    # 试别的主题，不改配置
```

用这个团自己的角色、背景、道具拼一段样板戏（旁白、两人对话、消音词、场外弹幕、两颗骰子含大成功、战斗开始、伤害、对抗、道具、回合、战斗结束、章节结束、片尾），逐帧渲染到每个画面停稳时截图，输出到 `build/theme-preview/<主题>/`，再拼成一张总览 `build/theme-preview/<主题>.png`。

## 给 AI 的设计流程

驱动项目的 AI 按这几步给一个团设计主题（流程手册里的 `rlyeh-theme` 技能就是这些）：

1. **读这个团**：题材、年代、基调（恐怖、轻松、史诗、悬疑）、主要场景、美术风格（`[art] style`）、已有的背景和立绘颜色。
2. **定方向**：先挑最接近的内置主题当 `base`，再写一句话的设计说明（放进 `description`），例如「雾港小镇的冷蓝雾夜，旧航海日志的质感」。
3. **配色**：从背景和立绘里取主色；定 `accent`、`accent-hi`、`text`、对话框底色；成功 / 失败 / 大失败三种颜色要一眼分得开。
4. **字体**：系统里常见的字体，或者主题文件夹里自带的可再分发字体（OFL 等）；不能引用网络字体，渲染时是离线的。
5. **形状和质感**：圆角、名牌外形、四角花纹、纹理，变量不够就写 `theme.css`。
6. **文字**：横幅、片尾标签换成合这个题材的说法（`[text.zh-CN]` / `[text.en]`）。
7. **预览、看图、再改**：运行 `replay theme preview`，看总览图；能看图的 harness 自己判断，看不了图的就交给人。

检查清单：

- 对话框里的字在最亮和最暗的背景上都看得清（对比度至少 4.5:1）；
- 旁白、台词、场外弹幕三种一眼能分开；
- 名牌颜色来自角色（`var(--c)`），别盖掉；
- 不引用网络上的字体和图片；
- 不要靠 `display: none` 藏掉骰子结果、伤害数字这类信息。
