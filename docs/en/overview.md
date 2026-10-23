# R'lyeh Workshop · Overview

> Specification v0.1 draft (M0). This is the English edition; the Chinese edition is in [`docs/zh/`](../zh/overview.md). Both say the same thing; if they disagree, the Chinese edition wins.

## What it is

R'lyeh Workshop (拉莱耶工坊) turns tabletop RPG session logs into **visual-novel replays**: a web page that plays in any browser, and a video rendered frame by frame from it.

The work is driven by **your own AI agent**. The first supported harnesses are Claude Code, Codex and DeepSeek Harness. R'lyeh Workshop ships no language model; it provides four things:

- **Project and script formats**: the AI, the tools and you all read and write the same project folder.
- **Pipeline tools**: import, voice synthesis, QA, bleeping, art post-processing, BGM, sound effects, player, rendering, encoding.
- **Integration layer**: the `replay` CLI, an MCP server, and a bilingual playbook exported in each harness's own format.
- **Studio GUI**: project dashboard, review pages, agent panel, render and export.

The workflow comes from a complete real production: the "Ram's Horn Inn" arc of a *Shadow of the Demon Lord* campaign — two sessions, a 40-minute video, 532 voiced lines. Every pitfall hit along the way became a default; see the "Defaults" in [Pipeline](pipeline.md).

## Principles

1. **Judgment goes to the AI, labor goes to the tools.** Polishing the script, tagging tone, writing art and music prompts, reading QA reports and deciding what to redo all need judgment, so the AI does them. Parsing, synthesis, alignment, rendering, mixing and encoding are deterministic, so tools do them.
2. **The project folder is the single source of truth.** Everything is plain text or ordinary media files — diffable and git-friendly. Studio, the AI and hand edits never conflict.
3. **Human review is a first-class gate.** Picking voices, approving art, listening line by line and auditioning BGM must be done by a person. The AI continues only after reading the review results.
4. **Backends are replaceable; no model weights are bundled.** Every capability (images, voice, recognition, music…) is a swappable backend. The software only calls models or services the user installed, and states each license clearly.
5. **Rendering is deterministic.** Videos are rendered frame by frame; each frame depends only on the timeline, nothing is dropped, and the same project renders identically every time.
6. **Chinese first, bilingual.** The UI, docs and playbook exist in Chinese and English; scripts can be written in either language.
7. **Right by default.** Practices proven in production are the defaults, so users don't have to rediscover the pitfalls.

## Non-goals

- Not a TRPG platform or VTT; it doesn't run sessions.
- No hosted service: everything runs on the user's machine (backends may be the user's own cloud APIs).
- Ships and distributes no model weights.
- Doesn't replace human taste: the AI and tools keep the process correct; a person decides whether it looks and sounds good.

## Components

```
┌──────────────── Studio (GUI, Chinese/English) ────────────────┐
│ Dashboard · pipeline progress · review pages · agent panel · export │
└───────────────┬───────────────────────────────────────────┘
                │ local HTTP (127.0.0.1)
┌───────────────▼────────────────── Core (Python) ─────────────┐
│ Project/script formats & lint · pipeline stages · task queue   │
│ Interfaces: replay CLI ── MCP server (replay mcp) ── playbook  │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────┘
 Import    Image       Voice/ASR    Music/SFX   Render/encode
                                                 │
                               ┌─────────────────▼────────┐
                               │ Player (web, themeable)   │
                               │ Virtual clock for render  │
                               └──────────────────────────┘
```

| Part | Stack | Notes |
|---|---|---|
| Core | Python 3.11+, managed with uv | The existing tools are Python; the speech, audio and imaging ecosystems live there |
| Local server | Python standard-library HTTP (grown from `replay preview`) | No extra dependencies; Studio, the review pages and the player preview share one server, and the same implementation as the CLI and MCP server |
| Studio | React + TypeScript + Vite; CodeMirror 6 for the script editor | A web app first (`replay studio` opens it in the browser); M4 wraps it in Electron for the installer |
| Player | TypeScript, no framework | The same data plays on the web and renders frame by frame |
| Video | ffmpeg | Detects NVENC / AMF / QSV, falls back to CPU |

## Pipeline at a glance

See [Pipeline](pipeline.md) for details.

| Stage | AI | Tools | Human gate |
|---|---|---|---|
| Import | — | Parse logs, merge overlapping exports, anonymize | Confirm player consent |
| Script | Polish, split into scenes, tag tone/expression/directions | Lint, assign stable IDs | Optional: script review |
| Cast | Infer looks, expressions, colors from the story | Validate | Confirm designs |
| Voices | Write voice design prompts | Generate candidates, fix references | **Pick voices** |
| Voice acting | Read QA, fix readings | Whole-sentence synthesis, ASR QA, reseeded retries | **Line-by-line review** |
| Bleeping | — | Forced alignment, replace with a beep | — |
| Art | Write prompts, judge consistency | Transparent backgrounds, expression compositing, overview sheets | **Approve art** |
| Music | Write the cue list and style prompts | Generate, detect vocals, loop | **Audition BGM** |
| SFX | Mark story sound effects in the script | Synthesized SFX library, auto-attached to staging | — |
| Render | — | Frame-by-frame render, timeline-based mix | Optional: watch the cut |
| Encode | — | Master / share / compat | — |

## Roadmap

| Milestone | Scope | Done when |
|---|---|---|
| **M0 Spec** | This document set: overview, project format, script format, pipeline, agents, backends & licensing | Reviewed and finalized by the maintainer |
| **M1 Core & CLI** | Generalize the production tools into a pipeline; `replay doctor`; a made-up sample session | The sample renders end to end from the CLI, no AI involved |
| **M2 Agents** | MCP server; bilingual playbook; export to Claude Code / Codex / DeepSeek Harness | Unit tests pass; each harness's own CLI reads the exported config (no model calls) |
| **M3 Studio** | Web Studio (`replay studio`): create and open projects, task board (one-click runs, live logs), built-in script editor (highlighting, live linting), review pages, agent panel (export config, show progress, flag reviews), backend settings and environment checks, render and encode; Chinese and English UI | The sample can be finished without touching the CLI |
| **M4 Release 0.1** | Electron shell and Windows installer; first-run model setup; macOS / Linux afterwards | From install to finished video on a fresh machine |

"Ram's Horn Inn" serves as a private regression project: after every major change it is re-rendered and compared frame by frame against the reference cut (rendering is deterministic, so frame comparison works). It contains real players' chat logs and will **not** be published in the public repository.

## Documents

| Document | Contents |
|---|---|
| [Project format](project-format.md) | Folder layout, `replay.toml`, `cast.yaml`, review files, state and incremental rebuilds |
| [Script format](script-format.md) | Lines, narration, OOC chat, tone, expressions, bleeps, stage directions; Chinese and English syntax |
| [Pipeline](pipeline.md) | Inputs and outputs of each stage, review gates, QA rules, defaults |
| [Agent integration](agents.md) | CLI, MCP, playbook; exact setup for Claude Code / Codex / DeepSeek Harness |
| [Backends & licensing](backends.md) | Backend interfaces, first-wave backends, model licenses, privacy and consent |
| [Studio](studio.md) | The GUI: starting it, what's there, security, endpoints, frontend development |
