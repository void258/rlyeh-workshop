# R'lyeh Workshop project: instructions for the AI

This folder is an **R'lyeh Workshop** project: it turns the chat log of a tabletop RPG session into a visual-novel replay and a video. You do the work that needs judgment (writing the script, filling in the cast, writing prompts, reading QA reports, designing the look); the `replay` command-line tool runs voices, images, music and rendering; choices that need taste — picking voices, reviewing art, choosing music — belong to the user on the review pages.

## What's in the project

| Path | Contents |
|---|---|
| `replay.toml` | Project config: title, players → characters, backends, readings, mix, theme |
| `cast.yaml` | Cast sheet: display names, looks, expressions, tone → expression rules, voice descriptions |
| `logs/raw/` → `logs/events.jsonl` | Raw session logs → the imported event stream (read-only) |
| `script/*.md` | The script, one file per chapter |
| `art/prompts/` | Image prompts, one file per image |
| `music.yaml` / `sfx.yaml` | Cue sheet / the project's own sound effects |
| `review/` | The user's decisions from the review pages (read them, never edit them) |
| `build/`, `.rlyeh/` | Generated files and tool state (don't edit by hand) |

Formats: [Project format](https://github.com/void258/rlyeh-workshop/blob/main/docs/en/project-format.md) · [Script format](https://github.com/void258/rlyeh-workshop/blob/main/docs/en/script-format.md) · [Pipeline](https://github.com/void258/rlyeh-workshop/blob/main/docs/en/pipeline.md).

## How to work

1. **Get a task**: run `replay next` (or `rlyeh_next_task` over MCP). It works out the next thing to do from the project files.
2. **Act on its kind**:
   - `agent`: yours. Follow the skill named in `playbook` (e.g. `rlyeh-script`); when done run `replay done <task-id>` (or `rlyeh_complete_task`). Condition-based tasks (script errors, TODOs in prompts) must actually be fixed; they can't be marked done.
   - `tool`: run its `command`, e.g. `replay voice build`. Run slow ones (voices, images, music, rendering) in the background with `rlyeh_run_stage` and check `rlyeh_job` every minute or two; don't poll more often.
   - `review`: waits for the user. Give them the review page URL (`replay preview`, or `rlyeh_preview_url` / `rlyeh_request_review`) and what to look at, then work on something else or stop and wait.
3. **Lint after editing the script or cast**: `replay lint` (or `rlyeh_lint`); fix errors first.
4. Overall progress: `replay status`, `replay next --all`.

## Rules

1. **Polish, don't change facts**: lines can sound more in character and read better, but who did what, roll values and results, and damage numbers stay as logged. Don't invent events the log doesn't have.
2. **Privacy**: real names, contact details and private matters unrelated to the game stay out of the script. Tell the user about possible private details found on import (`private` in `logs/sessions.json`). Before anything is published, remind the user to get every player's consent.
3. **Human review is a real gate**: the user decides voices, art and music on the review pages; don't choose for them. Read `review/`, never edit it.
4. **Say what costs money or time first**: before real image generation, large voice batches, music generation or a full render, tell the user how much will be done and roughly how long it takes. Image generation through Codex only uses the model and effort in `[harness.codex]`.
5. **Nothing goes out**: pushing repositories, uploading videos and sending files are the user's to do.
6. **Only touch this project folder**; don't hand-edit `build/`, `.rlyeh/` or `review/`.
7. **When unsure, ask**: unclear player intent, no basis for a character's looks, using a real person's voice, changing something already approved — ask the user first.

## Commands

| Command | What |
|---|---|
| `replay next [--all]` / `replay done <id>` | Get a task / report an agent task done |
| `replay status` / `replay doctor` | Stage progress / environment and backend check |
| `replay import` | Import `logs/raw/` |
| `replay lint` / `replay ids` | Lint the script / assign line IDs |
| `replay voice design\|build\|qa\|redo` / `replay bleep` | Voice candidates / voices / QA / redo / bleeping |
| `replay art jobs\|run\|check` | Starter prompts / generate / check and overview sheets |
| `replay sfx` / `replay music gen\|check` | Sound effects / music |
| `replay theme new\|preview` | New theme / screenshot preview |
| `replay build` / `replay render` / `replay encode share` | Build the player / render / encode |
| `replay preview` | Local preview and review pages (http://127.0.0.1:8766/) |

Every command takes `--json` for structured output and `-C <project dir>` to pick the project.

## MCP tools (when `replay mcp` is connected)

`rlyeh_status`, `rlyeh_next_task`, `rlyeh_complete_task`, `rlyeh_read_log` (paged log reading), `rlyeh_lint`, `rlyeh_list_lines`, `rlyeh_run_stage` (background stages), `rlyeh_job`, `rlyeh_qa_report`, `rlyeh_reviews`, `rlyeh_request_review`, `rlyeh_preview_url`. There are no file-editing tools: edit text files with your own tools.
