# Studio

> M3 进行中。英文版：[`docs/en/studio.md`](../en/studio.md)

Studio 是拉莱耶工坊的图形界面，先做成网页：`replay studio` 在本机开一个服务，用浏览器打开。M4 再套上 Electron 做成安装包。

## 启动

```bash
replay studio                 # 在当前文件夹（或上级）找项目，找不到就显示首页
replay studio -C 我的团        # 直接打开这个项目
replay studio --no-browser    # 不自动打开浏览器
```

默认地址是 `http://127.0.0.1:8766/`，端口被占时自动换一个，命令行会打印实际地址。它和 `replay preview` 是同一个服务：审核页、播放器、`/files/` 都在原来的地址上，AI 通过 MCP 拿到的审核页链接也能直接打开。

## 现在有什么（M3 第一批）

- **首页**：新建项目（放在哪、文件夹名、标题、剧本语言）、打开项目（浏览本机文件夹，项目会标出来；选到项目里的子文件夹也行）、最近打开的项目。
- **任务看板**：按阶段列出全部任务（和 `replay next --all` 一样），最上面是下一步。
  - 工具任务：点「运行」在后台跑，正在跑的显示进度；做完的可以再跑一次。
  - AI 任务：显示该照哪个技能做，交给你自己的 AI；AI 忘了报完成时可以手动「标记完成」。
  - 审核任务：直接打开对应的审核页。
- **后台任务**：一次只跑一个，后来的排队；实时日志和命令结果；关掉页面也会跑完。
- **审核**：选声线、逐句审听、美术审核、BGM 试听、播放器，在新标签页打开。
- **中英界面**：右上角切换；没选过时跟着项目语言。

后面两批：内置剧本编辑器（高亮、实时校验）、审核页并进 Studio；AI 面板（导出配置、显示进度、提醒审核）、后端设置和环境检查、渲染压制页。Studio 不会替你启动 AI，用多少额度由你自己掌握。

## 安全

- 只监听本机。`Host` 不是本机的请求一律拒绝（防 DNS 重绑定）。
- 会改东西的 Studio 接口要带 `X-Rlyeh: 1` 头：别的网站在浏览器里跨站发不出带自定义头的请求，没法替你建项目、跑任务。
- 选文件夹时由本地服务列出本机的文件夹名（浏览器拿不到本地路径），不读文件内容。
- 能跑的只有任务看板里的工具任务和 MCP 也能跑的那些阶段，参数不能换项目。
- 最近打开的项目记在 `~/.rlyeh/studio.json`，环境变量 `RLYEH_HOME` 可以换位置。

## 接口

| 接口 | 作用 |
|---|---|
| `GET /api/studio/state` | 当前项目、最近的项目、版本 |
| `GET /api/studio/browse?path=` | 列出子文件夹，标出哪些是项目；附带盘符和主目录 |
| `POST /api/studio/open` `{path}` | 打开项目（从 `path` 往上找 `replay.toml`） |
| `POST /api/studio/new` `{path, title, lang}` | 新建项目并打开（同 `replay init`） |
| `POST /api/studio/close` | 关闭项目，回到首页 |
| `GET /api/tasks?lang=` | 任务看板：全部任务、下一步、各状态数量；任务标题跟着 `lang` |
| `POST /api/tasks/done` `{id}` | 标记 AI 任务完成（同 `replay done`） |
| `POST /api/run` `{task}` 或 `{stage, args}` | 在后台运行工具任务或阶段（同 `rlyeh_run_stage`） |
| `GET /api/jobs` | 最近的后台任务 |
| `GET /api/jobs/<ID>?offset=` | 任务状态、从 `offset` 起新增的日志、命令结果 |

审核页原来的接口（`/api/voices`、`/api/lines`、`/api/art`、`/api/music` 和对应的 POST）不变；没打开项目时返回 409。

## 开发

前端在仓库的 `studio/` 里（React + TypeScript + Vite）。构建好的文件提交在 `src/rlyeh/studio/static/`，所以用 pip 装的人不需要 Node。

```bash
cd studio
npm ci
npm run dev       # 开发服务器（http://localhost:5173/），接口转给 8766；另开一个终端运行 replay studio --no-browser
npm run build     # 类型检查，再构建到 src/rlyeh/studio/static/
```

改了前端要重新 `npm run build`，把 `static/` 一起提交。依赖都锁死版本（`package-lock.json`）。
