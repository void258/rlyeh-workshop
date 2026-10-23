# Studio

> M3 in progress. Chinese version: [`docs/zh/studio.md`](../zh/studio.md)

Studio is R'lyeh Workshop's graphical interface. It starts as a web app: `replay studio` runs a local server and opens it in your browser. M4 wraps it in Electron for the installer.

## Starting it

```bash
replay studio                   # looks for a project in this folder (or above); shows the home page otherwise
replay studio -C my-campaign    # open this project directly
replay studio --no-browser      # don't open the browser
```

The default address is `http://127.0.0.1:8766/`; if the port is taken another one is used, and the command prints the real address. It is the same server as `replay preview`: review pages, the player and `/files/` stay at their usual addresses, so review links your AI gets over MCP open here too.

## What's there now (M3, first two batches)

- **Home**: create a project (where, folder name, title, script language), open a project (browse local folders, with projects marked; a subfolder of a project works too), recent projects.
- **Task board**: every task by stage (same as `replay next --all`), with the next one on top.
  - Tool tasks: "Run" starts them in the background and shows progress while they run; finished ones can run again.
  - Agent tasks: show which skill to follow, for your own AI; if it forgot to report back, "Mark done" records it.
  - Review tasks: open the matching review page inside Studio.
  - Skipped tasks say why they don't apply (no logs, placeholder backend, no recognition backend…).
  - Script lint errors jump to that line in the editor.
- **Script editor**:
  - Highlighting for both the Chinese and English notation: speakers, expressions, tones, actions, bleeped words, directions, line IDs.
  - Linting as you type (the same rules as `replay lint`, including duplicate IDs across chapters); errors and warnings are marked by the line numbers and listed below, and clicking one jumps to it.
  - Completions when you type a speaker at the start of a line or start a direction with `【` or `[[`: character names, expressions, direction names, positions, effects, background variants, cues, sounds.
  - **Line IDs are protected**: the `^c1-0001` at the end of a line is the key to its voice and review records, so the editor won't let you change it or type after it. Deleting the whole line is fine; saving tells you which lines were removed.
  - If the file changes outside the editor (your AI, another editor), it reloads automatically when you have no unsaved changes; otherwise it shows the conflict and lets you load their version or overwrite with yours.
  - Unsaved changes survive switching chapters or pages; `Ctrl+S` saves; you can add a chapter and assign line IDs.
- **Review**: voice picking, line review, art review, music and the player all live inside Studio with its look; each can also open in a new tab.
- **Jobs**: one runs at a time and the rest queue; live logs and the command's result; jobs finish even if you close the page.
- **Chinese and English UI**: switch at the top right; until you choose, it follows the project language.

Last batch: the agent panel (export config, show progress, flag reviews), backend settings and environment checks, and the render and encode page. Studio never launches an AI for you, so you stay in control of usage.

## Security

- Listens on this machine only. Requests whose `Host` isn't local are refused (DNS-rebinding protection).
- Studio endpoints that change anything need an `X-Rlyeh: 1` header: other websites can't send cross-site requests with custom headers from your browser, so they can't create projects or run jobs for you.
- The folder picker has the local server list folder names (browsers can't see local paths); it doesn't read file contents.
- Only tool tasks from the board and the stages MCP can run are allowed, and their arguments can't switch projects.
- Recent projects are kept in `~/.rlyeh/studio.json`; set `RLYEH_HOME` to move it.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/studio/state` | Current project, recent projects, version |
| `GET /api/studio/browse?path=` | Subfolders, with projects marked; plus drives and the home folder |
| `POST /api/studio/open` `{path}` | Open a project (searching up from `path` for `replay.toml`) |
| `POST /api/studio/new` `{path, title, lang}` | Create a project and open it (same as `replay init`) |
| `POST /api/studio/close` | Close the project and go back home |
| `GET /api/tasks?lang=` | Task board: all tasks, the next one, counts per status; titles follow `lang` |
| `POST /api/tasks/done` `{id}` | Mark an agent task done (same as `replay done`) |
| `POST /api/run` `{task}` or `{stage, args}` | Run a tool task or stage in the background (same as `rlyeh_run_stage`) |
| `GET /api/jobs` | Recent background jobs |
| `GET /api/jobs/<id>?offset=` | Job status, log text added since `offset`, the command's result |
| `GET /api/studio/player` | Whether the player has been built |
| `GET /api/script` | Chapters: title, line count, error and warning counts |
| `GET /api/script/file?path=` | A chapter's text and version (only `.md` files in `script/`) |
| `POST /api/script/lint` `{path, text, lang}` | Lint unsaved text |
| `POST /api/script/save` `{path, text, base, force}` | Save; if the file changed outside (the version doesn't match) it returns 409 with the current text, and only `force` overwrites; returns the line IDs removed |
| `POST /api/script/new` `{title}` | Add the next chapter |
| `POST /api/script/ids` | Assign line IDs (same as `replay ids`) |
| `GET /api/script/meta` | Names for completion: characters and expressions, OOC players, directions and parameters, enum values, cues, sounds |

The review pages' existing endpoints (`/api/voices`, `/api/lines`, `/api/art`, `/api/music` and their POSTs) are unchanged; they return 409 while no project is open. The review pages share `/static/common.css` and `/static/common.js`; with `?embed` in the address (inside Studio) they hide the link back to the home page.

## Development

The frontend lives in `studio/` in the repository (React + TypeScript + Vite; the script editor uses CodeMirror 6 and is bundled separately, loaded only when you open the script page). The built files are committed in `src/rlyeh/studio/static/`, so people installing with pip don't need Node.

```bash
cd studio
npm ci
npm run dev       # dev server (http://localhost:5173/) proxying the API to 8766; run replay studio --no-browser in another terminal
npm run build     # type-check, then build into src/rlyeh/studio/static/
```

After changing the frontend, run `npm run build` again and commit `static/` with it. Dependencies are pinned (`package-lock.json`).
