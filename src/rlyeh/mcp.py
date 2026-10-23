"""replay mcp：MCP 服务。stdio 上的 JSON-RPC 2.0，一行一条消息，只用标准库。规格见 docs/zh/agents.md#mcp-工具。

把查进度、领任务、跑阶段、看质检、读审核包装成工具，工具名都以 rlyeh_ 开头。
不提供改文件的工具：harness 自己能读写文件，剧本、角色表直接改，改完调 rlyeh_lint。
长任务在后台跑（见 jobs.py），rlyeh_run_stage 立即返回任务 ID，用 rlyeh_job 查进度。
标准输出只放协议消息，日志写到标准错误。
"""
import json
import sys
import threading

from . import __version__, art, i18n, jobs, music, sfx, tasks, voice
from .project import Project, ProjectError, find_root
from .script.lint import lint
from .util import now, read_json, write_json

PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')
# rlyeh_run_stage 能跑的阶段 → replay 子命令
STAGES = {
    'import': ['import'], 'ids': ['ids'], 'voice.design': ['voice', 'design'], 'voice.build': ['voice', 'build'],
    'voice.qa': ['voice', 'qa'], 'voice.redo': ['voice', 'redo'], 'bleep': ['bleep'], 'art.jobs': ['art', 'jobs'],
    'art.run': ['art', 'run'], 'art.compose': ['art', 'compose'], 'art.check': ['art', 'check'], 'sfx': ['sfx'],
    'music.gen': ['music', 'gen'], 'music.check': ['music', 'check'], 'build': ['build'], 'render': ['render'],
    'encode': ['encode'], 'theme.preview': ['theme', 'preview'], 'doctor': ['doctor'],
}
PAGES = {'player': '/player', 'voices': '/voices', 'voice': '/review/voice', 'art': '/review/art', 'music': '/review/music'}
REQUESTS = 'review/requests.json'


def _obj(props=None, required=()):
    return dict(type='object', properties=props or {}, required=list(required))


S, I, B = dict(type='string'), dict(type='integer'), dict(type='boolean')
ARR = dict(type='array', items=dict(type='string'))

TOOLS = [
    ('rlyeh_status', _obj(),
     ('项目各阶段的进度：配音、美术、音效、音乐的数量，全部任务的状态统计，以及下一件该做的事。',
      'Progress of every stage (voice, art, sfx, music counts), task status counts, and the next task.')),
    ('rlyeh_next_task', _obj(dict(all=B)),
     ('领下一件该做的事：agent 任务照 playbook 技能做，做完调 rlyeh_complete_task；tool 任务用 rlyeh_run_stage 跑 command；'
      'review 任务请人打开 page。all=true 列出全部任务。',
      'Get the next task: do agent tasks with their playbook skill and then call rlyeh_complete_task; run tool tasks with '
      'rlyeh_run_stage; for review tasks ask a person to open the page. all=true lists every task.')),
    ('rlyeh_complete_task', _obj(dict(id=S, note=S), ['id']),
     ('把 agent 任务记为完成（记下当时输入的哈希，输入变了会再次出现）。',
      'Mark an agent task done (records a hash of its inputs; it comes back if they change).')),
    ('rlyeh_read_log', _obj(dict(session=I, offset=I, limit=I, speaker=S, kind=S)),
     ('分段读导入后的跑团记录 logs/events.jsonl。可以按场次、发言人、类型（message / ooc / roll / card）筛选；'
      '返回 next_offset，接着读。',
      'Read the imported log (logs/events.jsonl) in pages, filtered by session, speaker or kind '
      '(message / ooc / roll / card); returns next_offset for the next page.')),
    ('rlyeh_lint', _obj(dict(errors_only=B)),
     ('校验剧本，返回错误和警告（文件、行号、说明）。改完剧本、角色表后调用。',
      'Lint the script and return errors and warnings (file, line, message). Call it after editing the script or cast.')),
    ('rlyeh_list_lines', _obj(dict(chapter=I, character=S, status=S, offset=I, limit=I)),
     ('按章、角色（ID 或名字）、状态筛选台词。status：todo（没生成）、stale（过期）、failed（质检不合格）、marked（审听标了重做）、done。',
      'List lines by chapter, character (ID or name) and status: todo (not generated), stale, failed (QA), '
      'marked (marked for redo in review), done.')),
    ('rlyeh_run_stage', _obj(dict(stage=dict(type='string', enum=sorted(STAGES)), task=S, args=ARR)),
     ('在后台运行一个阶段，立即返回任务 ID，用 rlyeh_job 查进度。可以给 stage，也可以给 rlyeh_next_task 返回的 tool 任务 ID（task）。'
      'args 原样加在命令后面，例如 voice.build 加 ["--ids", "c1-0001,c1-0002"]，voice.redo 加 ["--failed"]，'
      'render 加 ["--from", "c1-0012", "--seconds", "30"]，encode 加 ["share"]。同一个项目一次只跑一个，后来的排队。',
      'Run a stage in the background and return a job ID at once; poll it with rlyeh_job. Give a stage, or the ID of a tool '
      'task from rlyeh_next_task (task). args are appended to the command, e.g. voice.build ["--ids", "c1-0001,c1-0002"], '
      'voice.redo ["--failed"], render ["--from", "c1-0012", "--seconds", "30"], encode ["share"]. One job runs at a time per '
      'project; later ones queue.')),
    ('rlyeh_job', _obj(dict(id=S)),
     ('查后台任务：状态（queued / running / done / failed / lost）、日志最后几行、完成后的结果。不给 id 列出最近的任务。'
      '长任务（配音、渲染）要几分钟到几十分钟，别查得太勤。',
      'Check a background job: status (queued / running / done / failed / lost), the log tail and the result when done. '
      'Without id, list recent jobs. Long jobs (voices, rendering) take minutes to tens of minutes; do not poll too often.')),
    ('rlyeh_qa_report', _obj(dict(stage=dict(type='string', enum=['voice', 'music', 'art']), failed_only=B), ['stage']),
     ('读质检报告：voice 是配音识别结果（相似度、识别到的字、时长），music 是 BGM 人声检查，art 是图片检查。',
      'Read a QA report: voice (recognition similarity, heard text, duration), music (vocal check), art (image check).')),
    ('rlyeh_reviews', _obj(dict(kind=dict(type='string', enum=['voice-pick', 'voice', 'art', 'music'])), ['kind']),
     ('读人工审核的结果：选了哪段声线、哪些句子标了重做和意见、哪些图通过或打回、每段 BGM 选了哪一版。',
      'Read human review results: chosen voices, lines marked for redo with notes, approved or rejected images, chosen takes.')),
    ('rlyeh_request_review', _obj(dict(kind=dict(type='string', enum=['voices', 'voice', 'art', 'music', 'player']), items=ARR,
                                       note=S), ['kind']),
     ('请人审核：记进 review/requests.json，返回审核页地址，把地址和要看什么告诉用户。',
      'Ask a person to review: records the request in review/requests.json and returns the review page URL to give the user.')),
    ('rlyeh_preview_url', _obj(dict(page=dict(type='string', enum=sorted(PAGES)), line=S)),
     ('拿本地预览地址（需要的话先在后台启动预览服务）。page=player 时可以用 line 指定从哪一句开始播。',
      'Get a local preview URL (starting the preview server if needed). With page=player, line picks the line to start from.')),
]


class Server:
    def __init__(self, start='.'):
        self.start = start
        self.preview = None
        self.lang = 'zh-CN'
        try:
            self.project = Project(find_root(start)) if find_root(start) else None
        except ProjectError:
            self.project = None
        if self.project:
            self.lang = self.project.lang
            i18n.set_lang(i18n.detect(self.lang))          # 任务标题跟着项目语言

    # ── 协议 ──
    def tools(self):
        en = self.lang.startswith('en')
        return [dict(name=n, description=d[1] if en else d[0], inputSchema=schema) for n, schema, d in TOOLS]

    def handle(self, msg):
        method, mid, params = msg.get('method'), msg.get('id'), msg.get('params') or {}
        if mid is None:                                   # 通知：不回
            return None
        try:
            if method == 'initialize':
                want = params.get('protocolVersion')
                return self._ok(mid, dict(
                    protocolVersion=want if want in PROTOCOLS else PROTOCOLS[0],
                    capabilities=dict(tools=dict(listChanged=False)),
                    serverInfo=dict(name='rlyeh', version=__version__),
                    instructions=('拉莱耶工坊：先调 rlyeh_next_task 领任务，照 AGENTS.md 和对应技能做。'
                                  if not self.lang.startswith('en') else
                                  "R'lyeh Workshop: call rlyeh_next_task for work and follow AGENTS.md and the matching skill.")))
            if method == 'ping':
                return self._ok(mid, {})
            if method == 'tools/list':
                return self._ok(mid, dict(tools=self.tools()))
            if method == 'tools/call':
                return self._ok(mid, self.call(params.get('name'), params.get('arguments') or {}))
            return dict(jsonrpc='2.0', id=mid, error=dict(code=-32601, message=f'method not found: {method}'))
        except Exception as e:                            # 协议层的意外：回一个 JSON-RPC 错误，服务不退
            return dict(jsonrpc='2.0', id=mid, error=dict(code=-32603, message=f'{type(e).__name__}: {e}'))

    @staticmethod
    def _ok(mid, result):
        return dict(jsonrpc='2.0', id=mid, result=result)

    def call(self, name, args):
        fn = getattr(self, 'tool_' + str(name).removeprefix('rlyeh_'), None)
        if fn is None or not str(name).startswith('rlyeh_'):
            return self._text(dict(error=f'unknown tool {name}'), error=True)
        if self.project is None:
            return self._text(dict(error=f'no replay.toml found from {self.start}; run replay mcp inside a project'), error=True)
        try:
            self.project = Project(self.project.root)     # 每次重新读，文件可能被 harness 改过
            out = fn(**args)
            return self._text(out, error=isinstance(out, dict) and 'error' in out)
        except TypeError as e:
            return self._text(dict(error=f'bad arguments for {name}: {e}'), error=True)
        except Exception as e:                            # 工具出错：告诉 AI 原因，让它决定下一步
            return self._text(dict(error=f'{type(e).__name__}: {e}'), error=True)

    @staticmethod
    def _text(data, error=False):
        return dict(content=[dict(type='text', text=json.dumps(data, ensure_ascii=False, indent=1))], isError=error)

    # ── 工具 ──
    def tool_status(self):
        p = self.project
        all_tasks = tasks.plan(p)
        nxt = tasks.next_task(p, all_tasks)
        return dict(project=p.config.get('project', {}), voice=voice.summary(p), art=art.summary(p), sfx=sfx.summary(p),
                    music=music.summary(p), tasks=tasks.overview(all_tasks), next=nxt.as_dict() if nxt else None)

    def tool_next_task(self, all=False):
        all_tasks = tasks.plan(self.project)
        nxt = tasks.next_task(self.project, all_tasks)
        out = dict(next=nxt.as_dict() if nxt else None)
        if all:
            out['tasks'] = [x.as_dict() for x in all_tasks]
        return out

    def tool_complete_task(self, id, note=''):
        return dict(ok=True, id=id, record=tasks.complete(self.project, id, note))

    def tool_read_log(self, session=None, offset=0, limit=200, speaker=None, kind=None):
        path = self.project.root / 'logs' / 'events.jsonl'
        if not path.exists():
            return dict(error='logs/events.jsonl not found; run the import stage first')
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        rows = [r for r in rows if (session is None or r.get('session') == session) and (not speaker or r.get('speaker') == speaker)
                and (not kind or r.get('kind') == kind)]
        limit = max(1, min(int(limit), 1000))
        page = rows[offset:offset + limit]
        return dict(total=len(rows), offset=offset, events=page, next_offset=offset + len(page) if offset + len(page) < len(rows) else None)

    def tool_lint(self, errors_only=False):
        issues = lint(self.project.chapters(), self.project)
        errors = sum(1 for i in issues if i.level == 'error')
        shown = [i for i in issues if i.level == 'error'] if errors_only else issues
        return dict(errors=errors, warnings=len(issues) - errors, issues=[i.as_dict() for i in shown[:300]])

    def tool_list_lines(self, chapter=None, character=None, status=None, offset=0, limit=200):
        p = self.project
        todo, _ = voice.plan(p)
        stale = {x['id'] for x in todo}
        qa = read_json(p.root / voice.QA_REPORT, {})
        marks = set(voice.marked(p))
        want = p.character(character).id if character and p.character(character) else character
        rows = []
        for ch in p.chapters():
            if chapter is not None and ch.number != chapter:
                continue
            for it in ch.spoken:
                v = p.voice_of(it)
                if want and v != want and it.speaker != character:
                    continue
                exists = (p.root / voice.VOICE_DIR / f'{it.id}.wav').exists()
                st = ('silent' if not it.voiced else 'stale' if it.id in stale and exists
                      else 'todo' if it.id in stale or not exists else 'done')
                flags = [st] + (['failed'] if qa.get(it.id, {}).get('bad') else []) + (['marked'] if it.id in marks else [])
                if status and status not in flags:
                    continue
                rows.append(dict(id=it.id, chapter=ch.number, kind=it.kind, speaker=it.speaker, voice=v, tone=it.tone,
                                 text=it.text, voiced=it.voiced, status=st, qa=qa.get(it.id), marked=it.id in marks))
        limit = max(1, min(int(limit), 1000))
        return dict(total=len(rows), offset=offset, lines=rows[offset:offset + limit])

    def tool_run_stage(self, stage=None, task=None, args=None):
        if task:
            t = next((x for x in tasks.plan(self.project) if x.id == task), None)
            if t is None or t.kind != 'tool':
                return dict(error=f'{task} is not a tool task')
            argv = list(t.command)
        elif stage in STAGES:
            argv = list(STAGES[stage])
        else:
            return dict(error=f'unknown stage {stage}; choose from {", ".join(sorted(STAGES))}')
        extra = [str(a) for a in args or []]
        if any(a in ('-C', '--project') or a.startswith('--project=') for a in extra):
            return dict(error='args may not change the project folder')
        rec = jobs.start(self.project.root, argv + extra)
        return dict(job=rec['id'], command='replay ' + ' '.join(rec['command']), status=rec['status'])

    def tool_job(self, id=None):
        if not id:
            return dict(jobs=[{k: r.get(k) for k in ('id', 'command', 'status', 'queued_at', 'ended_at', 'exit_code')}
                              for r in jobs.listing(self.project.root)])
        rec = jobs.get(self.project.root, id)
        return rec if rec else dict(error=f'no job {id}')

    def tool_qa_report(self, stage, failed_only=False):
        p = self.project
        if stage == 'voice':
            rep = read_json(p.root / voice.QA_REPORT, {})
            return dict(report={k: v for k, v in rep.items() if v.get('bad') or not failed_only})
        if stage == 'music':
            rep = read_json(p.root / music.CHECK, {})
            return dict(report={k: v for k, v in rep.items() if not v.get('clean') or not failed_only})
        rep = read_json(p.root / art.CHECK, {})
        return dict(report={k: v for k, v in rep.items() if v.get('status') != 'ok' or not failed_only})

    def tool_reviews(self, kind):
        path = {'voice-pick': voice.PICK, 'voice': voice.REVIEW, 'art': art.REVIEW, 'music': music.REVIEW}[kind]
        return dict(kind=kind, reviews=read_json(self.project.root / path, {}))

    def _ensure_preview(self):
        if self.preview is None:
            from .preview import make_server
            try:
                server = make_server(self.project, port=8766)
            except OSError:                               # 8766 被占了（也许用户自己开着 replay preview）：换个空端口
                server = make_server(self.project, port=0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.preview = server
        return f'http://127.0.0.1:{self.preview.server_address[1]}'

    def tool_request_review(self, kind, items=None, note=''):
        path = self.project.root / REQUESTS
        reqs = read_json(path, [])
        reqs.append(dict(kind=kind, items=items or [], note=note, at=now(), status='open'))
        write_json(path, reqs)
        return dict(ok=True, url=self._ensure_preview() + PAGES[kind if kind in PAGES else 'player'],
                    tell_user='请用户打开这个地址审核' if not self.lang.startswith('en') else 'ask the user to open this URL and review')

    def tool_preview_url(self, page='player', line=None):
        base = self._ensure_preview()
        if page == 'player':
            if not (self.project.root / 'build' / 'player' / 'data.js').exists():
                return dict(error='the player is not built yet; run the build stage first')
            return dict(url=base + '/files/build/player/index.html' + (f'#{line}' if line else ''))
        return dict(url=base + PAGES[page])


def serve(start='.', stdin=None, stdout=None):
    """读一行处理一行，直到标准输入关闭。"""
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    server = Server(start)
    for raw in stdin:
        line = raw.decode('utf-8', errors='replace').strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = dict(jsonrpc='2.0', id=None, error=dict(code=-32700, message='parse error'))
        else:
            reply = server.handle(msg) if isinstance(msg, dict) else \
                dict(jsonrpc='2.0', id=None, error=dict(code=-32600, message='batches are not supported'))
        if reply is not None:
            stdout.write((json.dumps(reply, ensure_ascii=False) + '\n').encode('utf-8'))
            stdout.flush()
