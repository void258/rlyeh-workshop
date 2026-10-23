# Agent integration

> Specification v0.1 draft. Chinese edition: [`docs/zh/agents.md`](../zh/agents.md)

R'lyeh Workshop ships no language model; the user's own AI harness drives it. The first supported harnesses are **Claude Code**, **Codex** and **DeepSeek Harness (dsh)**.

Integration has three layers, shared by all three:

| Layer | What | Who uses it |
|---|---|---|
| CLI | `replay <subcommand>`; every step runs on its own; `--json` for structured output | Any agent that can run commands — the fallback |
| MCP server | `replay mcp` (stdio): status, tasks, running stages and QA wrapped as tools | Harnesses with MCP support |
| Playbook | Bilingual markdown: a main guide plus one skill per stage | Exported to each harness's instruction files and skill folders |

## CLI (v0.1 draft)

| Command | Purpose |
|---|---|
| `replay init <dir>` | Create a project (with `.gitignore` and a sample `replay.toml`) |
| `replay doctor` | Check Python, ffmpeg, hardware encoders and backend models |
| `replay import <files…>` | Import session logs |
| `replay status` | Per-stage progress: done / stale / waiting for review / not started |
| `replay next` | The next thing to do (task JSON, see [Pipeline](pipeline.md#tasks-and-state)) |
| `replay done <task-id>` | Mark a task done |
| `replay lint` / `replay ids` | Lint scripts / assign line IDs |
| `replay voice design\|build\|qa\|redo <ID…>` | Voice candidates / synthesis / QA / reseeded redo |
| `replay bleep` | Bleep profanity |
| `replay art jobs\|run\|compose\|check` | Write starter prompts / generate (`--marked` redraws rejected images) / recomposite expressions / check and overview sheets |
| `replay music gen\|check\|pick` | Generate BGM / detect vocals / choose a take |
| `replay sfx [--list]` | Build sound effects (built-in + sfx.yaml) / list sounds and aliases |
| `replay build` | Build the player (`build/player/`) and list missing assets |
| `replay preview` | Start the local preview (player, review pages) |
| `replay theme list\|new\|preview` | List themes / create a project theme / screenshots of every UI state (see [Player themes](theming.md)) |
| `replay render [--chapter N] [--from ID --seconds S] [--remix]` | Frame-by-frame render / remix audio only |
| `replay encode <preset>` | Encode: `share` / `compat` / your own `[encode.*]` (`master` is the rendered file itself) |
| `replay mcp` | Run the MCP server over stdio |
| `replay export-agent [claude-code\|codex\|dsh\|all]` | Export the playbook and MCP config into the project (default: `[harness] default`) |

Every command supports `--json`; failures return a non-zero exit code and a structured error so the agent can decide what to do next.

## MCP tools (v0.1 draft)

Tool names start with `rlyeh_`. The full name a harness shows is up to the harness (Claude Code and dsh use `mcp__rlyeh__<tool>`).

| Tool | Purpose |
|---|---|
| `rlyeh_status` | Project stage status |
| `rlyeh_next_task` / `rlyeh_complete_task` | Take / complete a task |
| `rlyeh_read_log` | Read imported logs by session, time range or count (logs can be long; read in chunks) |
| `rlyeh_lint` | Lint scripts; returns errors and warnings |
| `rlyeh_list_lines` | Filter lines by chapter, character or status |
| `rlyeh_run_stage` | Run a stage (optionally for specific lines or assets); long jobs return a job ID immediately |
| `rlyeh_job` | Progress and logs of a long job |
| `rlyeh_qa_report` | Read a stage's QA report |
| `rlyeh_reviews` | Read human review results |
| `rlyeh_request_review` | Ask Studio to queue items for review and notify the user |
| `rlyeh_preview_url` | Get a player preview URL (optionally starting at a given line) |

The MCP server **has no file-editing tools**: harnesses already read and write files, so scripts and cast sheets are edited directly, followed by `rlyeh_lint`.

Implementation: `replay mcp` uses only the standard library, one JSON-RPC message per line over stdio, protocol versions 2025-06-18, 2025-03-26 and 2024-11-05; tool descriptions follow the project language (Chinese / English). Checked against the official MCP Inspector client.

**Background jobs**: `rlyeh_run_stage` starts a separate runner process for the matching `replay` command, recorded in `.rlyeh/jobs/<job-id>.json` (status queued → running → done / failed, plus the command's JSON result) and `.log` (progress). The runner doesn't depend on the MCP connection, so it finishes even if the harness exits; one job runs at a time per project and later ones queue (two large models at once would run out of VRAM); jobs whose runner died show as `lost`.

## Playbook

Shipped inside the `rlyeh` package (`src/rlyeh/playbook/`), in Chinese and English:

```
playbook/
├── zh/
│   ├── AGENTS.md                 main guide: what's in the project, taking tasks, rules, commands and MCP tools
│   └── skills/
│       ├── rlyeh-import/SKILL.md     importing logs, privacy
│       ├── rlyeh-script/SKILL.md     writing and polishing the script, fixing lint errors
│       ├── rlyeh-cast/SKILL.md       cast sheet
│       ├── rlyeh-voice/SKILL.md      voices, voice QA, redos, bleeping
│       ├── rlyeh-art/SKILL.md        image prompts, rejected images
│       ├── rlyeh-music/SKILL.md      cue sheet, BGM, project sound effects
│       ├── rlyeh-theme/SKILL.md      a player theme designed for the campaign
│       └── rlyeh-render/SKILL.md     building, rendering, encoding
└── en/                           same, in English
```

Agent tasks from `replay next` carry a `playbook` field naming one of these skills. Each `SKILL.md` has YAML front matter with `name` (lowercase letters, digits and hyphens, matching the folder) and `description` (when to use it); all three harnesses require both:

```markdown
---
name: rlyeh-voice
description: Use in an R'lyeh Workshop project to design voices, synthesize voice lines, read the voice QA report, decide on reading fixes or redos, and bleep profanity.
---
```

Every "Default" in [Pipeline](pipeline.md) is written into the matching skill, e.g. "one fixed voice reference per character", "generate sprites with transparent backgrounds".

## Exporting to each harness

```bash
replay export-agent              # uses [harness] default in replay.toml
replay export-agent codex dsh    # name harnesses; all exports all three
```

This writes the playbook (Chinese or English, following the project language; `--lang` overrides it) and the MCP config into the project folder. Paths and formats were checked against each harness's official docs or source (Codex 0.159, dsh 0.1.5):

| | Claude Code | Codex | DeepSeek Harness |
|---|---|---|---|
| Project instructions | `CLAUDE.md` (one line, `@AGENTS.md`, importing the main guide) | `AGENTS.md` | `AGENTS.md` (reads both `AGENTS.md` and `CLAUDE.md`) |
| Skills | `.claude/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` | `.agents/skills/` (shared with Codex) |
| MCP config | `.mcp.json` | `.codex/config.toml` | `.rlyeh/dsh-patch.yml`, layered on with `--patch` at run time |
| Model | `[harness.claude-code] model` → `.claude/settings.json` | `[harness.codex] model / effort` → top-level `model` / `model_reasoning_effort` | `[harness.dsh] provider / model` → `agent-default-model` in the patch |
| Headless run | `claude -p` | `codex exec` | `dsh --profile headless "task"` |
| Structured output | `--output-format stream-json` | `--json` (newline-delimited events) | none: the final answer goes to stdout, reasoning to stderr, exit code 0 / 1 |

What gets overwritten:

- **Playbook and skills** are written whole by the tool. On re-export, files still as the last export left them are replaced with the new version (so upgrading rlyeh updates the playbook); files you edited are kept and shown as "kept", unless you pass `--force`. The export record lives in `.rlyeh/agent-export.json`.
- **Config files** (`CLAUDE.md`, `.mcp.json`, `.claude/settings.json`, `.codex/config.toml`) only get R'lyeh Workshop's own entry: the `@AGENTS.md` line, the `rlyeh` server, the model. Everything else stays as it was. Files that can't be parsed are left alone and reported.
- **The MCP command** defaults to the absolute path of `replay` in this install (or `<current Python> -m rlyeh.cli` when no `replay` from the same install is found), with arguments `mcp -C <absolute project path>`. Export again after moving the folder or switching machines; for a PATH-dependent `replay`, pass `--command replay`.

### Claude Code

`.mcp.json`:

```json
{
  "mcpServers": {
    "rlyeh": { "type": "stdio", "command": "…/replay", "args": ["mcp", "-C", "…/my-campaign"] }
  }
}
```

Project MCP servers need the user's approval: the first time you start `claude` in the project folder it asks; enable it, and `/mcp` shows whether it's connected. The export doesn't approve it for you.

### Codex

`.codex/config.toml`:

```toml
model = "gpt-6.1-sol"              # from [harness.codex]; omitted when not set
model_reasoning_effort = "low"

[mcp_servers.rlyeh]
command = "…/replay"
args = ["mcp", "-C", "…/my-campaign"]
startup_timeout_sec = 30
tool_timeout_sec = 600             # slow stages run as background jobs; this is only a backstop
```

Codex only reads `.codex/config.toml` in **trusted projects**: trust the folder the first time you run `codex` there. If you'd rather not, register the server globally with `codex mcp add rlyeh -- <the command the export prints>`. When `[harness.codex]` sets no model, the export warns that Codex will use your own default model and reasoning effort.

### DeepSeek Harness

dsh only has profile-level and `$DSH_HOME`-level config, no project level, so the export writes a patch to pass at run time:

```yaml
- id: agent-default-model          # from [harness.dsh]; omitted when not set. A patch replaces the plugin's whole config, so provider is included
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
      args: [mcp, -C, …/my-campaign]
      cwd: …/my-campaign
      toolCallTimeoutMs: 600000
      failOnStartupError: true
```

Run: `dsh --profile headless --patch .rlyeh/dsh-patch.yml "Continue this replay project following AGENTS.md"`. When dsh starts an MCP server it drops environment variables whose names contain KEY, TOKEN, SECRET or PASSWORD.

> DeepSeek Harness is a developer preview and its maintainers say breaking changes will happen. The export format was checked against 0.1.5; if dsh changes it, only `rlyeh/harness.py` needs updating.

## Studio's agent panel

- Choose which harness the project uses; run `replay export-agent` with one click.
- Dispatch tasks per stage: launch the harness with its headless command and show its structured output as live progress and logs.
- Or don't dispatch: the user talks to the agent in their own terminal, and Studio just shows progress and pops up reviews.
- Record time and usage for each run (when the harness reports it).

## Usage limits and permissions

- `[harness.<name>]` in `replay.toml` caps the model and reasoning effort per harness, and `replay export-agent` writes them into each config (see the table above). A production lesson: with no model specified, Codex defaulted to its most expensive model at maximum effort, researched and searched for references on its own, and made 9 model calls for one image.
- Long jobs (voice, render) run in the background; the tool returns a job ID at once and the agent checks `rlyeh_job` instead of blocking or polling too often.
- Agents may modify only the project folder; publishing anything (pushing, uploading) is always confirmed by the user in Studio.

## Generating images with Codex

When the image backend is `codex`, R'lyeh Workshop drives Codex's image generation through `codex exec`. The rules live in the `rlyeh-art` skill and in the fixed instruction sent to Codex:

1. The driving agent writes the full prompt (character design, outfit, composition, lighting, style, things to avoid); Codex uses it verbatim.
2. Model and effort come from `[harness.codex]`; never left empty.
3. Fixed instruction: call image generation once with the prompt as given; don't read extra guides, search the web, look for references or run extra checks; copy the image to the given path and reply with the path only.
4. When consistency matters (expression variants, CGs), Codex first opens the project's reference images, explicitly told that these are the project's own assets, not references to search for.

The actual call: `codex exec -m <model> -c model_reasoning_effort="<effort>" --skip-git-repo-check --ephemeral -s workspace-write -C <project> -o <last reply> --image=<base or reference> -`, with the fixed instruction and the prompt sent as UTF-8 on standard input. If Codex doesn't copy the image (say the sandbox blocks the write), the tool picks up the newly generated image from `~/.codex/generated_images/` (or `CODEX_HOME`) itself.

## Capability differences

Not every harness can look at images. For steps that need visual judgment (art consistency, clean cutouts):

- If the harness can see images: judge from the overview sheets.
- If not: fall back to numeric checks (alpha edges, head-position drift between base and variant, similarity to the reference image), and hand anything undecidable to human review.
