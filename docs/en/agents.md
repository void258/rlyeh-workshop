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
| `replay export-agent <claude-code\|codex\|dsh>` | Export the playbook and MCP config into the project |

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

## Playbook

```
playbook/
├── zh/
│   ├── AGENTS.md                 main guide: what the project is, how to take tasks, rules, when to ask a person
│   └── skills/
│       ├── rlyeh-script/SKILL.md     script polishing
│       ├── rlyeh-cast/SKILL.md       cast sheet
│       ├── rlyeh-voice/SKILL.md      voices and voice QA
│       ├── rlyeh-art/SKILL.md        art prompts
│       ├── rlyeh-music/SKILL.md      cue list and BGM
│       ├── rlyeh-theme/SKILL.md      player theme designed for the campaign
│       └── rlyeh-render/SKILL.md     rendering and encoding
└── en/                           same, in English
```

Each `SKILL.md` has YAML front matter with at least `name` and `description` (all three harnesses require both):

```markdown
---
name: rlyeh-voice
description: Use in a R'lyeh Workshop project when designing voices, synthesizing voice lines, reading the voice QA report or deciding on redos.
---
```

Every "Default" in [Pipeline](pipeline.md) is written into the matching skill, e.g. "one fixed voice reference per character", "generate sprites with transparent backgrounds".

## Exporting to each harness

`replay export-agent` writes the playbook (Chinese or English, following the project language) and the MCP config into the project folder. Paths and formats below were checked against each harness's official docs or source:

| | Claude Code | Codex | DeepSeek Harness |
|---|---|---|---|
| Project instructions | `CLAUDE.md` (containing `@AGENTS.md`, importing the main guide) | `AGENTS.md` | `AGENTS.md` (reads `AGENTS.md` and `CLAUDE.md` by default) |
| Skills | `.claude/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` | `.agents/skills/` or `.dsh/skills/` |
| MCP config | `.mcp.json` | `.codex/config.toml` (the project must be trusted by Codex) | A YAML overlay passed with `--patch`, inserting the `@deepseek-ai/dsh-mcp-client` plugin |
| Headless run | `claude -p` | `codex exec` | `dsh headless` |
| Structured output | `--output-format stream-json` | to be verified in M2 | `--json` (newline-delimited run events) |

Codex and DeepSeek Harness both read `AGENTS.md` and `.agents/skills/`, so they share one copy; Claude Code gets a mirror in `.claude/skills/`.

### Claude Code: `.mcp.json`

```json
{
  "mcpServers": {
    "rlyeh": { "command": "replay", "args": ["mcp"] }
  }
}
```

### Codex: `.codex/config.toml`

```toml
[mcp_servers.rlyeh]
command = "replay"
args = ["mcp"]
startup_timeout_sec = 30
tool_timeout_sec = 600        # stage tools can be slow; long jobs return a job ID right away
```

Or register it from the CLI: `codex mcp add rlyeh -- replay mcp`.

### DeepSeek Harness: `.rlyeh/dsh-mcp.yml`

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

Run: `dsh headless --patch .rlyeh/dsh-mcp.yml --json "Continue this replay project following AGENTS.md"`. For interactive use, add the same entry to `$DSH_HOME/profiles/web/cordis.patch.yml`.

> DeepSeek Harness is a developer preview and its maintainers state that breaking changes will happen. M2 will target the version current at that time, and the export logic will be a template that can be updated on its own.

## Studio's agent panel

- Choose which harness the project uses; run `replay export-agent` with one click.
- Dispatch tasks per stage: launch the harness with its headless command and show its structured output as live progress and logs.
- Or don't dispatch: the user talks to the agent in their own terminal, and Studio just shows progress and pops up reviews.
- Record time and usage for each run (when the harness reports it).

## Usage limits and permissions

- `[harness.<name>]` in `replay.toml` caps the model and reasoning effort per harness, and the export writes these into each config. A production lesson: with no model specified, Codex defaulted to its most expensive model at maximum effort, researched and searched for references on its own, and made 9 model calls for one image.
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
