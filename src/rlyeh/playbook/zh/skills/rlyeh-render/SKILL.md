---
name: rlyeh-render
description: 拉莱耶工坊项目里打包播放器、预览、逐帧渲染成片、重新混音、压制分享版时使用。
---

# 打包、渲染、压制

## 打包播放器

`replay build` → `build/player/`。输出会列出缺的配音、图片、音效、曲子和不认识的指令：缺的回到对应阶段补；不认识的指令回剧本改。打包后可以用 `replay preview` 打开 `/player`（或 `rlyeh_preview_url page=player line=<台词ID>` 从某句开始）给用户看。

## 渲染

- **先试一段**：`replay render --from <台词ID> --seconds 30`，看节奏、立绘、特效对不对，再渲染整部。
- **整部**：`replay render`（几章同时渲染再拼起来），1 小时成片大约要 1–2 小时，后台跑（`rlyeh_run_stage render`），开始前告诉用户大概多久。
- **只改了混音**（`[mix]` 的电平、压低比例、响度）：`replay render --remix`，不重新渲染画面。
- 需要 playwright 和 ffmpeg；`replay doctor` 会检查。

## 压制

- `replay encode share`：AV1 分享版，体积小（显卡支持就用 NVENC，否则 CPU）。
- `replay encode compat`：H.264，老设备、网页也能放。
- 母版就是 `replay render` 写出的 `build/video/<项目ID>.mp4`。

## 规矩

- **不要实时录屏**：录屏会掉帧，也要花和片长一样的时间。渲染是逐帧的，画面只取决于时间轴。
- 渲染出来的视频是用户的作品：上传、发布由用户自己做。
- 用到只能非商用的后端（`replay doctor` 会提示，例如 YuE2）时，提醒用户成片不能商用。
