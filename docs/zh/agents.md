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
| `replay theme list\|new\|preview` | 列出主题 / 新建项目主题 / 每种界面截图预览（见 [播放器主题](theming.md)） |
| `replay render [--chapter N] [--from ID --seconds S] [--remix]` | 逐帧渲染 / 只重新混音 |
| `replay encode <预设>` | 压制：`share` / `compat` / 自己在 `[encode.*]` 加的（`master` 就是渲染出的成片） |
| `replay mcp` | 以 stdio 方式运行 MCP 服务 |
| `replay export-agent [claude-code\|codex\|dsh\|all]` | 把流程手册和 MCP 配置导出到项目里（默认用 `[harness] default`） |

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

实现：`replay mcp` 只用标准库，stdio 上一行一条 JSON-RPC 消息，支持协议版本 2025-06-18、2025-03-26、2024-11-05；工具说明跟着项目语言（中文 / 英文）。已经用官方的 MCP Inspector 客户端核对过。

**后台任务**：`rlyeh_run_stage` 开一个独立的 runner 进程跑对应的 `replay` 命令，记录在 `.rlyeh/jobs/<任务ID>.json`（状态 queued → running → done / failed，命令的 JSON 结果）和 `.log`（进度）。runner 和 MCP 连接无关，harness 关掉也会跑完；同一个项目一次只跑一个，后来的排队（显卡同时跑两个大模型会爆显存）；runner 意外死掉的任务显示为 `lost`。

## 流程手册

装在 `rlyeh` 包里（`src/rlyeh/playbook/`），中英各一套：

```
playbook/
├── zh/
│   ├── AGENTS.md                 总说明：项目里有什么、怎么领任务、规矩、命令和 MCP 工具
│   └── skills/
│       ├── rlyeh-import/SKILL.md     导入记录、隐私
│       ├── rlyeh-script/SKILL.md     写剧本、润色、修校验错误
│       ├── rlyeh-cast/SKILL.md       角色表
│       ├── rlyeh-voice/SKILL.md      声线、配音质检、重做、消音
│       ├── rlyeh-art/SKILL.md        生图提示词、审核打回
│       ├── rlyeh-music/SKILL.md      曲目表、BGM、项目音效
│       ├── rlyeh-theme/SKILL.md      按团的气质设计播放器主题
│       └── rlyeh-render/SKILL.md     打包、渲染、压制
└── en/                           同上，英文
```

`replay next` 给出的 agent 任务带 `playbook` 字段，就是这里的技能名。每个 `SKILL.md` 带 YAML 头，`name`（小写字母、数字和连字符，和文件夹同名）和 `description`（什么时候用）三家都要求：

```markdown
---
name: rlyeh-voice
description: 拉莱耶工坊项目里设计声线、生成配音、看配音质检报告、决定改读法或重做、消音时使用。
---
```

[流水线](pipeline.md) 里的「默认规则」都写进了对应技能，例如「声线只用一段固定参考」「生图直接出透明背景」。

## 导出到各家 harness

```bash
replay export-agent              # 用 replay.toml 的 [harness] default
replay export-agent codex dsh    # 指定几家；all 是三家都导
```

把流程手册（按项目语言选中文或英文，`--lang` 可以改）和 MCP 配置写进项目文件夹。路径和格式对照过各家的官方文档或源码（Codex 0.159、dsh 0.1.5）：

| | Claude Code | Codex | DeepSeek Harness |
|---|---|---|---|
| 项目说明 | `CLAUDE.md`（一行 `@AGENTS.md`，引用总说明） | `AGENTS.md` | `AGENTS.md`（`AGENTS.md` 和 `CLAUDE.md` 都读） |
| 技能 | `.claude/skills/<名>/SKILL.md` | `.agents/skills/<名>/SKILL.md` | `.agents/skills/`（和 Codex 共用） |
| MCP 配置 | `.mcp.json` | `.codex/config.toml` | `.rlyeh/dsh-patch.yml`，运行时用 `--patch` 叠加 |
| 模型 | `[harness.claude-code] model` → `.claude/settings.json` | `[harness.codex] model / effort` → 顶层 `model` / `model_reasoning_effort` | `[harness.dsh] provider / model` → 补丁里的 `agent-default-model` |
| 无人值守运行 | `claude -p` | `codex exec` | `dsh --profile headless "任务"` |
| 结构化输出 | `--output-format stream-json` | `--json`（逐行输出事件） | 没有：最终回答在标准输出，推理过程在标准错误，退出码 0 / 1 |

覆盖规则：

- **手册和技能**整份由工具写。重新导出时，还是上次导出样子的文件换成新版（升级 rlyeh 后手册跟着更新）；你改过的留着不动，输出里标「保留」，加 `--force` 才覆盖。导出记录在 `.rlyeh/agent-export.json`。
- **配置文件**（`CLAUDE.md`、`.mcp.json`、`.claude/settings.json`、`.codex/config.toml`）只改拉莱耶工坊自己那一项：`@AGENTS.md` 这一行、`rlyeh` 这个服务、模型；别的内容原样保留。文件解析不了就不碰，报出来。
- **启动命令**默认是这个安装里 `replay` 的绝对路径（找不到同一个安装的 `replay` 时用 `<当前 Python> -m rlyeh.cli`），参数是 `mcp -C <项目绝对路径>`。换机器或挪文件夹后重新导出一次；想写成依赖 PATH 的 `replay`，加 `--command replay`。

### Claude Code

`.mcp.json`：

```json
{
  "mcpServers": {
    "rlyeh": { "type": "stdio", "command": "…/replay", "args": ["mcp", "-C", "…/我的团"] }
  }
}
```

项目里的 MCP 服务要用户批准：第一次在项目文件夹里启动 `claude` 会问，选启用；`/mcp` 里能看到连没连上。导出不会替你批准。

### Codex

`.codex/config.toml`：

```toml
model = "gpt-6.1-sol"              # 来自 [harness.codex]，没写就不加
model_reasoning_effort = "low"

[mcp_servers.rlyeh]
command = "…/replay"
args = ["mcp", "-C", "…/我的团"]
startup_timeout_sec = 30
tool_timeout_sec = 600             # 慢的阶段走后台任务，这里只兜底
```

Codex 只读**受信任项目**的 `.codex/config.toml`：第一次在这里运行 `codex` 时选信任。不想信任的话，用 `codex mcp add rlyeh -- <导出时打印的命令>` 登记到全局。`[harness.codex]` 没写模型时导出会提醒：Codex 会用你自己的默认模型和推理强度。

### DeepSeek Harness

dsh 的配置只有 profile 和 `$DSH_HOME` 两级，没有项目级，所以导出成一份补丁，运行时带上：

```yaml
- id: agent-default-model          # 来自 [harness.dsh]，没写就不加；补丁整块替换插件配置，所以 provider 也写上
  config:
    provider: deepseek-official
    model: deepseek-flash
- insert:
  - id: mcp-rlyeh
    name: '@deepseek-ai/dsh-mcp-client'
    config:
      serverName: rlyeh
      transport: stdio
      command: …/replay
      args: [mcp, -C, …/我的团]
      cwd: …/我的团
      toolCallTimeoutMs: 600000
      failOnStartupError: true
```

运行：`dsh --profile headless --patch .rlyeh/dsh-patch.yml "按 AGENTS.md 继续做这个 replay 项目"`。dsh 启动 MCP 服务时会去掉名字里带 KEY、TOKEN、SECRET、PASSWORD 的环境变量。

> DeepSeek Harness 目前是开发者预览版，官方说明会有不兼容的改动。导出格式按 0.1.5 核对；dsh 改格式时只需要改 `rlyeh/harness.py`。

## Studio 的 AI 面板

- 选择这个项目用哪家 harness；一键执行 `replay export-agent`。
- 按阶段派任务：用对应的无人值守命令启动 harness，把结构化输出实时显示成进度和日志。
- 也可以不派任务：用户在自己的终端里和 AI 对话，Studio 只负责显示进度、弹出审核。
- 每次运行记下用时和用量（harness 提供的话）。

## 用量和权限

- `replay.toml` 的 `[harness.<名字>]` 给每家设模型和推理强度上限，`replay export-agent` 把它写进对应配置（见上表）。实战教训：Codex 没指定模型时默认用了最贵的模型和最高推理强度，自己去查资料、找参考图，一次生图前后调了 9 次模型。
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
