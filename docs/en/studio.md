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

## What's there now (M3, batch 1)

- **Home**: create a project (where, folder name, title, script language), open a project (browse local folders, with projects marked; a subfolder of a project works too), recent projects.
- **Task board**: every task by stage (same as `replay next --all`), with the next one on top.
  - Tool tasks: "Run" starts them in the background and shows progress while they run; finished ones can run again.
  - Agent tasks: show which skill to follow, for your own AI; if it forgot to report back, "Mark done" records it.
  - Review tasks: open the matching review page.
- **Jobs**: one runs at a time and the rest queue; live logs and the command's result; jobs finish even if you close the page.
- **Review**: voice picking, line review, art review, music and the player, each in a new tab.
- **Chinese and English UI**: switch at the top right; until you choose, it follows the project language.

Next two batches: the built-in script editor (highlighting, live linting) and review pages inside Studio; then the agent panel (export config, show progress, flag reviews), backend settings and environment checks, and the render and encode page. Studio never launches an AI for you, so you stay in control of usage.

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

The review pages' existing endpoints (`/api/voices`, `/api/lines`, `/api/art`, `/api/music` and their POSTs) are unchanged; they return 409 while no project is open.

## Development

The frontend lives in `studio/` in the repository (React + TypeScript + Vite). The built files are committed in `src/rlyeh/studio/static/`, so people installing with pip don't need Node.

```bash
cd studio
npm ci
npm run dev       # dev server (http://localhost:5173/) proxying the API to 8766; run replay studio --no-browser in another terminal
npm run build     # type-check, then build into src/rlyeh/studio/static/
```

After changing the frontend, run `npm run build` again and commit `static/` with it. Dependencies are pinned (`package-lock.json`).
