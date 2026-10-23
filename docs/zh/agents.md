# AI 接入

> 规格 v0.1 草稿。英文版：[`docs/en/agents.md`](../en/agents.md)

拉莱耶工坊不内置大模型，由用户自己的 AI harness 来驱动。第一批支持 **Claude Code**、**Codex**、**DeepSeek Harness（dsh）**。

接入分三层，三家共用：

| 层 | 是什么 | 谁用 |
|---|---|---|
| 命令行 | `replay <子命令>`，每一步都能单独执行，加 `--json` 输出结构化结果 | 任何能执行命令的 AI，是保底方案 |
| MCP 服务 | `replay mcp`（stdio），把查进度、领任务、跑阶段、看质检包装成工具 | 支持 MCP 的 harness |
| 流程手册 | 中英两套 markdown：总说明 + 每个阶段一个技能（skill） | 导出成各家能读的说明文件和技能目录 |

## 命令行（v0.1 草案）

| 命令 | 作用 |
|---|---|
| `replay init <目录>` | 新建项目（含 `.gitignore`、示例 `replay.toml`） |
| `replay doctor` | 检查 Python、ffmpeg、显卡编码器、各后端模型是否就绪 |
| `replay import <文件…>` | 导入跑团记录 |
| `replay status` | 各阶段进度：完成 / 过期 / 等待审核 / 未开始 |
| `replay next` | 下一件该做的事（任务 JSON，见 [流水线](pipeline.md#任务与状态)） |
| `replay done <任务ID>` | 标记任务完成 |
| `replay lint` / `replay ids` | 校验剧本 / 补台词 ID |
| `replay voice design\|build\|qa\|redo <ID…>` | 声线候选 / 生成配音 / 质检 / 换种子重做 |
| `replay bleep` | 消音 |
| `replay art jobs\|run\|compose\|check` | 写起步提示词 / 生成（`--marked` 重画审核打回的）/ 重新合成差分 / 检查和总览图 |
| `replay music gen\|check\|pick` | 生成 BGM / 查人声 / 选定一版 |
| `replay sfx [--list]` | 生成音效（内置合成 + sfx.yaml）/ 列出音效和别名 |
| `replay build` | 打包播放器（`build/player/`），列出缺的素材 |
| `replay preview` | 启动本地预览（播放器、审核页） |
| `replay render [--chapter N] [--from ID --seconds S] [--remix]` | 逐帧渲染 / 只重新混音 |
| `replay encode <预设>` | 压制：`share` / `compat` / 自己在 `[encode.*]` 加的（`master` 就是渲染出的成片） |
| `replay mcp` | 以 stdio 方式运行 MCP 服务 |
| `replay export-agent <claude-code\|codex\|dsh>` | 把流程手册和 MCP 配置导出到项目里 |

所有命令都支持 `--json`，失败时返回非零退出码和结构化错误，方便 AI 判断下一步。

## MCP 工具（v0.1 草案）

工具名统一以 `rlyeh_` 开头。harness 里看到的完整名字由各家决定（Claude Code 和 dsh 是 `mcp__rlyeh__<工具名>`）。

| 工具 | 作用 |
|---|---|
| `rlyeh_status` | 项目各阶段状态 |
| `rlyeh_next_task` / `rlyeh_complete_task` | 领任务 / 交任务 |
| `rlyeh_read_log` | 按会话、时间段或条数读导入后的记录（记录可能很长，分段读） |
| `rlyeh_lint` | 校验剧本，返回错误和警告 |
| `rlyeh_list_lines` | 按章、角色、状态筛选台词 |
| `rlyeh_run_stage` | 运行某个阶段（可以只跑指定台词或素材）；长任务立即返回任务 ID |
| `rlyeh_job` | 查长任务进度和日志 |
| `rlyeh_qa_report` | 读某阶段的质检报告 |
| `rlyeh_reviews` | 读人工审核结果 |
| `rlyeh_request_review` | 请 Studio 把某些条目放进审核队列，并通知用户 |
| `rlyeh_preview_url` | 拿到播放器预览地址（可以指定从哪一句开始） |

MCP 服务**不提供改文件的工具**：harness 自己有读写文件的能力，剧本、角色表这些文本直接改文件，改完调 `rlyeh_lint`。

## 流程手册

```
playbook/
├── zh/
│   ├── AGENTS.md                 总说明：项目是什么、怎么领任务、规矩、该问人的时候
│   └── skills/
│       ├── rlyeh-script/SKILL.md     剧本润色
│       ├── rlyeh-cast/SKILL.md       角色表
│       ├── rlyeh-voice/SKILL.md      声线与配音质检
│       ├── rlyeh-art/SKILL.md        美术提示词
│       ├── rlyeh-music/SKILL.md      曲目表与 BGM
│       └── rlyeh-render/SKILL.md     渲染与压制
└── en/                           同上，英文
```

每个 `SKILL.md` 带 YAML 头，至少有 `name` 和 `description`（三家都要求这两项）：

```markdown
---
name: rlyeh-voice
description: 拉莱耶工坊项目里设计声线、生成配音、看配音质检报告、决定重做时使用。
---
```

[流水线](pipeline.md) 里的「默认规则」都会写进对应技能，例如「声线只用一段固定参考」「生图直接出透明背景」。

## 导出到各家 harness

`replay export-agent` 把流程手册（按项目语言选中文或英文）和 MCP 配置写进项目文件夹。下表的路径和格式都对照过各家官方文档或源码：

| | Claude Code | Codex | DeepSeek Harness |
|---|---|---|---|
| 项目说明 | `CLAUDE.md`（内容为 `@AGENTS.md`，直接引用总说明） | `AGENTS.md` | `AGENTS.md`（默认读 `AGENTS.md` 和 `CLAUDE.md`） |
| 技能 | `.claude/skills/<名>/SKILL.md` | `.agents/skills/<名>/SKILL.md` | `.agents/skills/` 或 `.dsh/skills/` |
| MCP 配置 | `.mcp.json` | `.codex/config.toml`（项目要被 Codex 标为可信） | 运行时用 `--patch` 叠加一份 YAML，插入 `@deepseek-ai/dsh-mcp-client` 插件 |
| 无人值守运行 | `claude -p` | `codex exec` | `dsh headless` |
| 结构化输出 | `--output-format stream-json` | 待 M2 核实 | `--json`（逐行输出运行事件） |

Codex 和 DeepSeek Harness 都读 `AGENTS.md` 和 `.agents/skills/`，所以这两家共用同一份；Claude Code 再镜像一份到 `.claude/skills/`。

### Claude Code：`.mcp.json`

```json
{
  "mcpServers": {
    "rlyeh": { "command": "replay", "args": ["mcp"] }
  }
}
```

### Codex：`.codex/config.toml`

```toml
[mcp_servers.rlyeh]
command = "replay"
args = ["mcp"]
startup_timeout_sec = 30
tool_timeout_sec = 600        # 跑阶段的工具可能很久，长任务本身会立即返回任务 ID
```

也可以用命令行登记：`codex mcp add rlyeh -- replay mcp`。

### DeepSeek Harness：`.rlyeh/dsh-mcp.yml`

```yaml
- insert:
    - id: mcp-rlyeh
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: stdio
        serverName: rlyeh
        command: replay
        args: [mcp]
        env: {}
        cwd: .
        toolCallTimeoutMs: 600000
        failOnStartupError: true
```

运行：`dsh headless --patch .rlyeh/dsh-mcp.yml --json "按 AGENTS.md 继续做这个 replay 项目"`。交互使用时，把同样的条目加进 `$DSH_HOME/profiles/web/cordis.patch.yml`。

> DeepSeek Harness 目前是开发者预览版，官方说明会有不兼容的改动。M2 实现时以当时的版本为准，导出逻辑做成可单独更新的模板。

## Studio 的 AI 面板

- 选择这个项目用哪家 harness；一键执行 `replay export-agent`。
- 按阶段派任务：用对应的无人值守命令启动 harness，把结构化输出实时显示成进度和日志。
- 也可以不派任务：用户在自己的终端里和 AI 对话，Studio 只负责显示进度、弹出审核。
- 每次运行记下用时和用量（harness 提供的话）。

## 用量和权限

- `replay.toml` 的 `[harness.<名字>]` 给每家设模型和推理强度上限，导出时写进对应配置。实战教训：Codex 没指定模型时默认用了最贵的模型和最高推理强度，自己去查资料、找参考图，一次生图前后调了 9 次模型。
- 长任务（配音、渲染）在后台跑，工具立即返回任务 ID，AI 用 `rlyeh_job` 查进度，不要干等或轮询太勤。
- 能改的只有项目文件夹；往外发布（推仓库、上传）一律由用户在 Studio 里确认。

## 用 Codex 生图

美术后端选 `codex` 时，拉莱耶工坊用 `codex exec` 调 Codex 的生图能力。规矩写进 `rlyeh-art` 技能，也写进发给 Codex 的固定指令：

1. 提示词由驱动项目的 AI 写好（角色造型、服装、构图、光线、画风、要避免的东西），原样传给 Codex。
2. 模型和推理强度按 `[harness.codex]`，不留空。
3. 固定指令：直接调用一次生图，提示词原样使用；不读额外说明、不上网搜索、不找参考图、不做额外检查；生成后把图片复制到指定路径，只回复路径。
4. 需要保持造型一致时（差分、CG），先让 Codex 打开项目里的参考图，明确说明这是本项目的素材，不是去找参考图。

实际的调用：`codex exec -m <模型> -c model_reasoning_effort="<强度>" --skip-git-repo-check --ephemeral -s workspace-write -C <项目目录> -o <最后回复> --image=<底图或参考图> -`，固定指令和提示词按 UTF-8 从标准输入传进去。Codex 没把图复制过去时（例如沙箱不让写），工具自己到 `~/.codex/generated_images/`（或 `CODEX_HOME`）取这次新生成的那张。

## 能力差异

不是每家 harness 都能看图。需要视觉判断的环节（美术一致性、抠图干净与否）：

- harness 能看图：读总览图做判断。
- 看不了：用数值检查兜底（透明通道边缘、差分前后头部位置偏移、和参考图的相似度），判断不了的直接交给人审核。
