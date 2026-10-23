# 示例团：雾港灯塔

[English](README.en.md) | **中文**

一场编出来的短团：三名玩家、一位 GM，十几分钟的聊天记录。用来演示拉莱耶工坊从跑团记录到成片的整条流程。玩家、角色、记录全是虚构的。

默认全部用**占位后端**：不装任何模型也能跑完。图是剪影、配音是一段音调、音乐是和弦铺底。装好模型以后，在 `replay.toml` 的 `[backends]` 换成真的后端就行，`replay doctor` 会告诉你还缺什么。

## 里面有什么

| 文件 | 内容 |
|---|---|
| `logs/raw/session-2024-05-18.txt` | 原始聊天记录（纯文本，带时间） |
| `script/01-雾港灯塔.md` | AI 按记录整理的剧本：口语改成台词，补上语气、表情、舞台指令，场外闲聊留成弹幕 |
| `cast.yaml` | 角色表：外貌、表情差分、语气→表情规则、声线描述 |
| `art/prompts/` | 生图提示词：立绘、表情差分、背景、CG、道具，一张图一个文件 |
| `music.yaml` | 曲目表：每一幕的情绪、配器、速度 |
| `sfx.yaml` | 项目自己的音效（雾魇的哀嚎，用它的声线生成） |

跑出来的东西（配音、图片、音乐、`build/`）都在 `.gitignore` 里，不会混进版本库。

## 跑一遍

在仓库根目录：

```bash
uv run replay import -C examples/fog-harbor        # 记录 → logs/events.jsonl
uv run replay lint -C examples/fog-harbor
uv run replay voice build -C examples/fog-harbor   # 配音
uv run replay bleep -C examples/fog-harbor         # 「tmd」那句消音
uv run replay art run -C examples/fog-harbor       # 生图，表情差分自动合成
uv run replay sfx -C examples/fog-harbor
uv run replay music gen -C examples/fog-harbor
uv run replay preview -C examples/fog-harbor       # 打开 http://127.0.0.1:8766/
```

在预览页里：选声线、逐句审听、审美术、给每段 BGM 挑一版（也可以用 `replay music pick harbor 1`）。然后：

```bash
uv run replay build -C examples/fog-harbor         # 打包播放器，预览页的「播放器」直接打开
uv run replay render -C examples/fog-harbor        # 逐帧渲染成片（要先 uv sync --extra render，并装好 ffmpeg）
uv run replay encode share -C examples/fog-harbor  # 压一个体积小的分享版
```

成片在 `build/video/fog-harbor.mp4`。

## 让 AI 接手

```bash
uv run replay export-agent claude-code -C examples/fog-harbor   # 或 codex、dsh、all
```

写好流程手册、技能和 MCP 配置后，在 `examples/fog-harbor` 里启动你的 AI，跟它说「按 AGENTS.md 看看这个项目还差什么」。它会用 `replay next` 领任务：该自己做的（写提示词、看质检）照技能做，该跑工具的去跑，该你拍板的（选声线、审美术、挑 BGM）把审核页地址给你。各家的细节见 [AI 接入](../../docs/zh/agents.md#导出到各家-harness)。

## 换成真的后端

| 能力 | 占位 | 真的后端 |
|---|---|---|
| 生图 | `image = "placeholder"` | `codex`（要在 `[harness.codex]` 写模型和推理强度）或 `manual` 自己画 |
| 声线设计 | `voice_design = "placeholder"` | `qwen3-tts` |
| 配音 | `tts = "placeholder"` | `drama3` |
| 识别质检 | `asr = "none"` | `sensevoice` |
| 消音对齐 | `align = "estimate"`（按字数估算） | `funasr-fa`（中文，准） |
| 音乐 | `music = "placeholder"` | `yue2-comfyui`（要开着 ComfyUI）或 `manual` |

每个后端要写的设置见 [项目格式](../../docs/zh/project-format.md)。
