# 拉莱耶工坊项目：给 AI 的总说明

这个文件夹是一个**拉莱耶工坊**（R'lyeh Workshop）项目：把一场跑团（TRPG）的聊天记录做成视觉小说式的 replay 和视频。你负责需要判断的活（写剧本、补角色设定、写提示词、看质检结果、设计界面风格）；配音、生图、音乐、渲染由 `replay` 命令行工具去跑；选声线、审美术、挑 BGM 这些需要品味的地方交给用户在审核页里做。

## 项目里有什么

| 路径 | 内容 |
|---|---|
| `replay.toml` | 项目配置：标题、玩家 → 角色、各类后端、读法、混音、主题 |
| `cast.yaml` | 角色表：显示名、外貌、表情差分、语气 → 表情规则、声线描述 |
| `logs/raw/` → `logs/events.jsonl` | 原始跑团记录 → 导入后的事件流（只读） |
| `script/*.md` | 剧本，一章一个文件 |
| `art/prompts/` | 生图提示词，一张图一个文件 |
| `music.yaml` / `sfx.yaml` | 曲目表 / 项目自己的音效 |
| `review/` | 用户在审核页里的决定（你只读，不改） |
| `build/`、`.rlyeh/` | 生成的东西和工具的状态（不要手改） |

格式说明：[项目格式](https://github.com/void258/rlyeh-workshop/blob/main/docs/zh/project-format.md) · [剧本格式](https://github.com/void258/rlyeh-workshop/blob/main/docs/zh/script-format.md) · [流水线](https://github.com/void258/rlyeh-workshop/blob/main/docs/zh/pipeline.md)。

## 怎么干活

1. **领任务**：运行 `replay next`（有 MCP 时用 `rlyeh_next_task`）。它根据项目文件算出下一件该做的事。
2. **按类别做**：
   - `agent`：你来做。读任务里的 `playbook`，按同名技能（例如 `rlyeh-script`）做；做完运行 `replay done <任务ID>`（或 `rlyeh_complete_task`）。条件型的任务（剧本有错、提示词里有 TODO）要真的改好，标不了完成。
   - `tool`：运行任务里的 `command`，例如 `replay voice build`。耗时的（配音、生图、音乐、渲染）用 `rlyeh_run_stage` 放到后台，过一两分钟用 `rlyeh_job` 看一次进度，别查得太勤。
   - `review`：等用户。把审核页地址（`replay preview` 或 `rlyeh_preview_url` / `rlyeh_request_review`）和要看什么告诉用户，然后去做别的事或者停下来等。
3. **改完剧本或角色表就校验**：`replay lint`（或 `rlyeh_lint`），有错误先修。
4. 看整体进度：`replay status`、`replay next --all`。

## 规矩

1. **润色不改事实**：台词可以改得更像角色、更顺口，但谁做了什么、掷骰点数和结果、伤害数值都照记录，不编记录里没发生的情节。
2. **隐私**：真实姓名、联系方式、和团无关的私事不进剧本。导入时发现的疑似隐私（`logs/sessions.json` 的 `private`）要告诉用户。做成公开内容前提醒用户确认所有玩家都同意。
3. **人工审核是正式关卡**：声线、美术、BGM 等用户在审核页里定，不要替用户选；`review/` 里的决定你只读不改。
4. **花额度、花时间的操作先说清楚**：真实生图、大批量配音、生成音乐、整部渲染开始前，告诉用户要做多少、大概多久；Codex 生图只用 `[harness.codex]` 里写的模型和推理强度。
5. **不往外发布**：推送仓库、上传视频、发给别人都由用户自己做。
6. **只动这个项目文件夹**；`build/`、`.rlyeh/`、`review/` 不手改。
7. **不确定就问**：玩家的意图看不明白、角色外貌没有依据、要用真人的声音、要改已经审核通过的东西——先问用户。

## 命令速查

| 命令 | 作用 |
|---|---|
| `replay next [--all]` / `replay done <ID>` | 领任务 / 交 agent 任务 |
| `replay status` / `replay doctor` | 各阶段进度 / 环境和后端检查 |
| `replay import` | 导入 `logs/raw/` |
| `replay lint` / `replay ids` | 校验剧本 / 补台词 ID |
| `replay voice design\|build\|qa\|redo` / `replay bleep` | 声线候选 / 配音 / 质检 / 重做 / 消音 |
| `replay art jobs\|run\|check` | 起步提示词 / 生图 / 检查和总览图 |
| `replay sfx` / `replay music gen\|check` | 音效 / BGM |
| `replay theme new\|preview` | 新建主题 / 截图预览 |
| `replay build` / `replay render` / `replay encode share` | 打包播放器 / 渲染 / 压制 |
| `replay preview` | 本地预览和审核页（http://127.0.0.1:8766/） |

所有命令都能加 `--json` 拿结构化结果，`-C <项目目录>` 指定项目。

## MCP 工具（如果接上了 `replay mcp`）

`rlyeh_status`、`rlyeh_next_task`、`rlyeh_complete_task`、`rlyeh_read_log`（分段读记录）、`rlyeh_lint`、`rlyeh_list_lines`、`rlyeh_run_stage`（后台跑阶段）、`rlyeh_job`、`rlyeh_qa_report`、`rlyeh_reviews`、`rlyeh_request_review`、`rlyeh_preview_url`。MCP 不提供改文件的工具：文本文件直接用你自己的读写工具改。
