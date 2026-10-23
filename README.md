# 拉莱耶工坊 · R'lyeh Workshop

[English](README.en.md) | **中文**

**让你自己的 AI，把跑团记录做成视觉小说式的 replay 和视频。**

把 FVTT 等平台导出的跑团记录交给拉莱耶工坊，由你常用的 AI（Claude Code、Codex、DeepSeek Harness）来润色剧本、设计角色、写美术和音乐提示词；拉莱耶工坊负责配音、质检、消音、立绘后处理、BGM、音效，最后生成一个能在浏览器里播放的视觉小说，以及逐帧渲染出来的视频。选声线、审美术、逐句审听这些需要品味的环节，留给你在图形界面里把关。

> **状态：M3 进行中。** 规格（M0）已定稿；目前能用的是导入跑团记录（`replay import`）、剧本解析和校验（`replay lint`、`replay ids`）、配音一整条线（`replay voice design / pick / build / qa / redo`、`replay bleep`）、美术（`replay art jobs / run / compose / check`，Codex 生图、表情差分合成）、音效（`replay sfx`）、BGM（`replay music gen / check / pick`，YuE2 先找无人声乐谱再渲染）、播放器（`replay build`）、逐帧渲染和混音（`replay render`）、压制（`replay encode`）、环境检查（`replay doctor`），以及选声线、逐句审听、美术审核、BGM 试听这几个页面（`replay preview`）。命令行这一层（M1）已经完整，可以拿 [示例团](examples/fog-harbor/README.md) 从记录一路跑到成片。AI 接入（M2）已经有任务引擎（`replay next` / `replay done`）、MCP 服务（`replay mcp`）、中英流程手册，`replay export-agent` 一键导出给 Claude Code、Codex 和 DeepSeek Harness。图形界面（M3）先做网页版：`replay studio` 已经能新建、打开项目，看任务看板，一键运行工具任务、看实时日志。欢迎在 Issues 里讨论设计。

## 它能做什么

- **剧本**：AI 把聊天记录润色成剧本，标好语气、表情和舞台指令；场外闲聊保留成场外弹幕。
- **配音**：每个角色一种声线，整句生成；语音识别自动质检、自动重做；脏话照写在字幕里，配音里换成「哔」。
- **美术**：立绘透明背景、多种表情差分、场景和 CG 造型一致。
- **音乐与音效**：按幕切换的 BGM，战斗自动换战斗曲；骰子、打击、喷火、破门等音效自动跟着演出走。
- **播放器**：章节卡、立绘调度、场外弹幕聊天栏、d20 掷骰、伤害数字、对抗、CG、片尾字幕；界面风格可以换主题，也可以让 AI 按团的气质设计一套。
- **视频**：逐帧确定性渲染（不掉帧），自动混音，一键压制母版和体积小的 AV1 分享版。

## 支持的 AI harness

| Harness | 接入方式 |
|---|---|
| Claude Code | `CLAUDE.md` + `.claude/skills/` + `.mcp.json` |
| Codex | `AGENTS.md` + `.agents/skills/` + `.codex/config.toml` |
| DeepSeek Harness | `AGENTS.md` + `.agents/skills/` + `--patch .rlyeh/dsh-patch.yml` |

在项目文件夹里运行 `replay export-agent <claude-code|codex|dsh|all>` 就会写好这些文件。三家共用同一个命令行工具 `replay` 和同一个 MCP 服务。详见 [AI 接入](docs/zh/agents.md)。

## 示例团

[`examples/fog-harbor`](examples/fog-harbor/README.md)：一场编出来的短团「雾港灯塔」，带原始记录、AI 整理的剧本、角色表、生图提示词和曲目表。默认全用占位后端，不装任何模型也能从导入跑到成片。

## 文档

- [总览](docs/zh/overview.md)：设计原则、组成部分、路线图
- [项目格式](docs/zh/project-format.md)
- [剧本格式](docs/zh/script-format.md)
- [流水线](docs/zh/pipeline.md)：每个阶段做什么，以及实战总结的默认规则
- [AI 接入](docs/zh/agents.md)
- [后端与授权](docs/zh/backends.md)
- [播放器主题](docs/zh/theming.md)：每个团可以有自己的界面风格，让 AI 按团的气质设计
- [Studio](docs/zh/studio.md)：图形界面（网页版），`replay studio` 打开

## 路线图

| 里程碑 | 内容 |
|---|---|
| M0 ✓ | 规格文档 |
| M1 ✓ | 核心流水线与命令行，示例团从头跑到成片 |
| M2 ✓ | MCP 服务与流程手册，接入三家 harness |
| **M3** ← 当前 | Studio 图形界面（先做网页版，中英双语，内置剧本编辑器） |
| M4 | 发布 0.1（Electron 安装包，先 Windows） |

## 开发

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync                      # 安装依赖；要渲染视频再加 --extra render，并装好 ffmpeg
uv run replay init my-replay # 新建一个示例项目
uv run replay lint -C my-replay
uv run pytest                # 跑测试
```

## 授权

代码以 [Apache License 2.0](LICENSE) 发布。

拉莱耶工坊**不包含、也不分发任何模型权重**。你用到的配音、生图、音乐模型各有各的授权：有的要求署名，有的只能非商用。拉莱耶工坊会在界面里提示，并在片尾自动生成署名。详见 [后端与授权](docs/zh/backends.md)。

做 replay 前，请确认所有玩家同意公开他们的跑团记录。
