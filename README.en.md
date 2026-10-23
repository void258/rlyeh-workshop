# R'lyeh Workshop · 拉莱耶工坊

**English** | [中文](README.md)

**Turn your tabletop RPG session logs into visual-novel replays and videos, driven by your own AI agent.**

Hand R'lyeh Workshop a session log exported from Foundry VTT or a similar platform. Your usual AI agent (Claude Code, Codex, or DeepSeek Harness) polishes the script, designs the characters, and writes the art and music prompts. R'lyeh Workshop handles voice acting, QA, profanity bleeping, sprite post-processing, BGM and sound effects, then produces a visual novel that plays in the browser plus a frame-by-frame rendered video. The steps that need taste — picking voices, approving art, listening line by line — stay with you, in a graphical interface.

> **Status: M1 in progress.** The specification (M0) is final. What works today is script parsing, linting (`replay lint`) and line IDs (`replay ids`); the voice, art and rendering pipeline is being brought over. Design discussion is welcome in Issues.

## What it does

- **Script**: the AI turns chat logs into a script with tone, expression and stage directions; out-of-character chatter is kept as an OOC chat feed.
- **Voice**: one voice per character, generated sentence by sentence; automatic speech-recognition QA and retries; profanity stays in the subtitles and is bleeped in the audio.
- **Art**: sprites with transparent backgrounds, multiple expressions, consistent designs across scenes and CGs.
- **Music & SFX**: BGM switches per scene and automatically during battles; dice, hits, fire breath, doors breaking and more follow the staging.
- **Player**: chapter cards, sprite staging, OOC chat feed, d20 rolls, damage numbers, contests, CGs, credits.
- **Video**: deterministic frame-by-frame rendering (no dropped frames), automatic mixing, one-click master and compact AV1 share encodes.

## Supported AI harnesses

| Harness | Integration |
|---|---|
| Claude Code | `CLAUDE.md` + `.claude/skills/` + `.mcp.json` |
| Codex | `AGENTS.md` + `.agents/skills/` + `.codex/config.toml` |
| DeepSeek Harness | `AGENTS.md` + `.agents/skills/` + MCP client plugin |

All three share the same `replay` CLI and the same MCP server. See [Agent integration](docs/en/agents.md).

## Documentation

- [Overview](docs/en/overview.md): principles, components, roadmap
- [Project format](docs/en/project-format.md)
- [Script format](docs/en/script-format.md)
- [Pipeline](docs/en/pipeline.md): what each stage does, plus defaults learned in production
- [Agent integration](docs/en/agents.md)
- [Backends & licensing](docs/en/backends.md)

## Roadmap

| Milestone | Scope |
|---|---|
| **M0** ← current | Specification |
| M1 | Core pipeline and CLI; a sample session rendered end to end |
| M2 | MCP server and playbooks for the three harnesses |
| M3 | Studio GUI (Chinese and English) |
| M4 | Release 0.1 (Windows first) |

## Development

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                      # install dependencies
uv run replay init my-replay # create a sample project
uv run replay lint -C my-replay
uv run pytest                # run the tests
```

## License

The code is released under the [Apache License 2.0](LICENSE).

R'lyeh Workshop **does not include or distribute any model weights**. The voice, image and music models you use have their own licenses — some require attribution, some are non-commercial only. R'lyeh Workshop shows these in the interface and generates the credits automatically. See [Backends & licensing](docs/en/backends.md).

Before making a replay, make sure every player agrees to have their session published.
