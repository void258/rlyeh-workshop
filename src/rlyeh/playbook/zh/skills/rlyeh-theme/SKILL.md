---
name: rlyeh-theme
description: 拉莱耶工坊项目里按这个团的题材和气质设计播放器界面主题（配色、字体、对话框、横幅文字）、预览截图时使用。
---

# 设计播放器主题

播放器的界面风格由主题决定。内置三套：`dark-fantasy`（默认，金色描边的黑暗奇幻）、`noir`（旧案卷宗：纸质对话框、墨字、印章红）、`neon`（霓虹终端：青色品红、直角、扫描线）。完整说明见 [播放器主题](https://github.com/void258/rlyeh-workshop/blob/main/docs/zh/theming.md)。

## 什么时候用

`replay next` 给出 `player.theme`（可选任务），或者用户想换界面风格。用户决定就用默认主题的话，`replay done player.theme`。

## 步骤

1. **读这个团**：题材、年代、基调（恐怖、轻松、史诗、悬疑）、主要场景、`[art] style`、已有背景和立绘的颜色。
2. **先试内置主题**：`replay theme preview --theme noir`（不改配置），看 `build/theme-preview/<主题>.png`。合适就在 `replay.toml` 写 `[player] theme = "noir"`，结束。
3. **自己设计**：`replay theme new --base <最接近的内置主题>`，会建好 `theme/theme.toml`（全部设计变量注释掉、带当前值和说明）和 `theme/theme.css`，并写上 `[player] theme = "theme"`。
4. 在 `description` 写一句设计说明，例如「雾港小镇的冷蓝雾夜，旧航海日志的质感」。
5. 改 `[vars]`：
   - 配色：从背景和立绘里取主色，定 `accent`、`accent-hi`、`text`、`box-bg`；`good` / `bad` / `fumble` 三种结果色要一眼分得开；
   - 字体：`font-body`、`font-ui`、`font-display`，用系统常见字体，或者把可再分发（OFL 等）的字体文件放进 `theme/fonts/` 再在 `[fonts]` 登记；
   - 形状：`box-radius`、`nameplate-shape`、`box-corner`（`none` 去掉花纹）。
6. 变量做不到的（纹理、版式、动画）写 `theme/theme.css`；图片放 `theme/images/`，用相对路径引用。
7. 横幅和片尾的文字换成合这个题材的说法：`[text.zh-CN]` 里的 `battleStart`、`battleEnd`、`victory`、`replayTag`……
8. `replay theme preview` 截图，看总览图，改到满意；看不了图的话把总览图路径给用户看。

## 检查清单

- 对话框里的字在最亮和最暗的背景上都看得清（对比度至少 4.5:1）；
- 旁白、台词、场外弹幕一眼能分开；
- 名牌颜色来自角色（`var(--c)`），别盖掉；
- 不引用网络上的字体和图片（渲染时是离线的）；
- 不用 `display: none` 藏掉骰子结果、伤害数字这类信息；
- `replay build` 输出里没有「unknown design variable」警告。
