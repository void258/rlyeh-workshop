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

## 有什么

- **首页**：新建项目（放在哪、文件夹名、标题、剧本语言）、打开项目（浏览本机文件夹，项目会标出来；选到项目里的子文件夹也行）、最近打开的项目。
- **任务看板**：按阶段列出全部任务（和 `replay next --all` 一样），最上面是下一步。
  - 工具任务：点「运行」在后台跑，正在跑的显示进度；做完的可以再跑一次。
  - AI 任务：显示该照哪个技能做，交给你自己的 AI；AI 忘了报完成时可以手动「标记完成」。
  - 审核任务：在 Studio 里打开对应的审核页。
  - 跳过的任务写着为什么用不上（没有记录、占位后端、没设识别后端……）。
  - 剧本校验的错误点一下就跳到编辑器里的那一行。
- **剧本编辑器**：
  - 中英两种写法都有高亮：说话人、表情、语气、动作、消音词、指令、台词 ID。
  - 边写边校验（和 `replay lint` 同一套规则，包括跨章的 ID 重复），错误和警告标在行号旁边，下面列出来，点一下跳过去。
  - 行首打说话人、打 `【` 或 `[[` 开始指令时有补全：角色名、表情、指令名、位置、特效、背景变体、曲目、音效。
  - **台词 ID 不能改**：行尾的 `^c1-0001` 是配音和审核记录的钥匙，编辑器不让改、也不让在后面接着打字；整行删掉可以，保存时会提醒删了哪几句。
  - 外面（AI、别的编辑器）改了文件：没改动时自动载入；有没保存的修改时提示冲突，选载入外面的版本还是用自己的覆盖。
  - 没保存的修改切到别的章节、别的页面再回来还在；`Ctrl+S` 保存；可以新建章节、补台词 ID。
- **审核**：选声线、逐句审听、美术审核、BGM 试听、播放器都在 Studio 里，样式和 Studio 一致；也可以在新标签页打开。
- **AI**：
  - 选用哪家（Claude Code、Codex、DeepSeek Harness），看本机装没装，一键导出流程手册和 MCP 配置（同 `replay export-agent`）。
  - 「怎么开始」给出进项目文件夹、启动 AI 的命令和开场白，都能一键复制。**Studio 不替你启动 AI**，用多少额度由你自己掌握。
  - 「AI 做到哪了」列出 AI 报告完成的任务和正在跑的后台任务；AI 用 `rlyeh_request_review` 请你审核的条目也在这里，导航栏上有数字提醒。
- **出片**：
  - 打包播放器、在 Studio 里看。
  - 渲染整部、只渲染某一章、从某一句开始试渲染一段、只重新混音；渲染时显示百分比、已用时间和预计剩余时间（播放器在渲染模式下报告进度，`replay render` 每 10 秒画面写一行 `steps 已渲染/总数`）。
  - 压制分享版、兼容版；做好的视频直接在页面里播放（支持拖进度条），或者在文件夹中显示。
- **设置**：
  - 各类后端（生图、声线设计、配音、识别质检、消音对齐、音乐）从下拉框里选，标出要不要显卡、能不能商用；改的是 `replay.toml` 的 `[backends]`，注释原样保留。
  - 每家 AI 的模型和推理强度（`[harness.*]`）。
  - 环境检查（同 `replay doctor`）：每项是 ✓ / ! / ✗，不能用的告诉你怎么修。
- **后台任务**：一次只跑一个，后来的排队；实时日志和命令结果；关掉页面也会跑完。
- **中英界面**：右上角切换；没选过时跟着项目语言。

M3 的验收：在一份干净的示例团里，只用 Studio 的页面（导出配置、按「下一步」运行任务、审美术、挑 BGM、渲染、压制）从导入做到成片，不碰命令行。

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
| `GET /api/studio/player` | 播放器打包了没有 |
| `GET /api/script` | 章节列表：标题、台词数、错误和警告数 |
| `GET /api/script/file?path=` | 一章的内容和版本号（只认 `script/` 下的 `.md`） |
| `POST /api/script/lint` `{path, text, lang}` | 校验还没保存的内容 |
| `POST /api/script/save` `{path, text, base, force}` | 保存；文件在外面被改过（版本号对不上）时返回 409 和现在的内容，`force` 才覆盖；返回删掉的台词 ID |
| `POST /api/script/new` `{title}` | 新建下一章 |
| `POST /api/script/ids` | 补台词 ID（同 `replay ids`） |
| `GET /api/script/meta` | 自动补全用的名字表：角色和表情、场外玩家、指令和参数、枚举值、曲目、音效 |
| `GET /api/studio/attention` | 导航栏提醒：等人审核的任务、没处理的审核请求数 |
| `GET /api/agent?lang=` | AI 面板：默认用哪家、装没装、导出记录、启动命令、开场白、最近完成的任务、审核请求 |
| `POST /api/agent/export` `{harness, lang, force}` | 导出配置（同 `replay export-agent`） |
| `POST /api/agent/request` `{index}` | 把一条审核请求标记为已处理 |
| `GET /api/settings` | 各类后端的当前选择和可选项、每家 AI 的模型设置 |
| `POST /api/settings` `{table, key, value}` | 改 `replay.toml`：只认 `[backends]` 的各类后端和 `[harness.*]` 的模型；`value` 为空时删掉这一项 |
| `GET /api/doctor?lang=` | 环境检查（同 `replay doctor`） |
| `GET /api/video` | 出片页：视频文件、播放器打包了没有、章节、上次成片时长、渲染和压制要的工具 |
| `POST /api/reveal` `{path}` | 在文件管理器里显示项目里的某个文件 |

`/files/` 支持 `Range` 请求，视频能拖进度条。审核页原来的接口（`/api/voices`、`/api/lines`、`/api/art`、`/api/music` 和对应的 POST）不变；没打开项目时返回 409。审核页共用的样式和脚本在 `/static/common.css`、`/static/common.js`，地址带 `?embed` 时（嵌在 Studio 里）不显示回首页的链接。

## 开发

前端在仓库的 `studio/` 里（React + TypeScript + Vite，剧本编辑器用 CodeMirror 6，单独打包，打开剧本页时才加载）。构建好的文件提交在 `src/rlyeh/studio/static/`，所以用 pip 装的人不需要 Node。

```bash
cd studio
npm ci
npm run dev       # 开发服务器（http://localhost:5173/），接口转给 8766；另开一个终端运行 replay studio --no-browser
npm run build     # 类型检查，再构建到 src/rlyeh/studio/static/
```

改了前端要重新 `npm run build`，把 `static/` 一起提交。依赖都锁死版本（`package-lock.json`）。
