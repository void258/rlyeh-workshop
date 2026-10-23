"""replay studio：网页版 Studio。在浏览器里新建、打开项目，看任务看板，一键运行工具任务，看实时日志。

和 replay preview 是同一个本地服务：审核页、播放器、/files/ 都在原来的地址上。Studio 多了：
  /                      Studio 页面（studio/ 里用 Vite 构建，产物在 rlyeh/studio/static/）
  /api/studio/state      当前项目、最近的项目
  /api/studio/browse     选文件夹：列出子文件夹，标出哪些是项目
  /api/studio/open|new|close   打开、新建、关闭项目
  /api/tasks             任务看板（同 replay next --all）
  /api/tasks/done        标记 agent 任务完成（同 replay done）
  /api/run               在后台运行工具任务或阶段（同 rlyeh_run_stage）
  /api/jobs[/<ID>]       后台任务；带 offset 取日志增量
只监听本机。Host 不是本机的请求一律拒绝（防 DNS 重绑定）；会改东西的 Studio 请求要带 X-Rlyeh 头，
别的网站跨站发不出带自定义头的请求。
"""
import json
import os
import pathlib
import re
import string
import sys
import urllib.parse
from importlib import resources

from .. import __version__, i18n, jobs, preview, tasks
from ..mcp import stage_command
from ..project import Project, ProjectError, create, find_root
from ..util import read_json, write_json

STATIC = resources.files('rlyeh') / 'studio' / 'static'
RECENT_MAX = 12
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.json': 'application/json'}


class StudioError(Exception):
    pass


def home():
    """Studio 自己的设置（最近的项目）放在 RLYEH_HOME，默认 ~/.rlyeh。"""
    return pathlib.Path(os.environ.get('RLYEH_HOME') or pathlib.Path.home() / '.rlyeh')


def summary(project):
    p = project.config.get('project') or {}
    return dict(root=str(project.root), id=p.get('id', ''), title=p.get('title') or project.root.name, lang=project.lang)


def roots():
    if sys.platform == 'win32':
        return [f'{c}:\\' for c in string.ascii_uppercase if os.path.isdir(f'{c}:\\')]
    return ['/']


def browse(path=None):
    """列出一个文件夹里的子文件夹（不含隐藏的），标出哪些是项目。"""
    p = pathlib.Path(path).expanduser() if path else pathlib.Path.home()
    try:
        p = p.resolve()
        children = sorted(p.iterdir(), key=lambda c: c.name.lower())
    except OSError as e:
        raise StudioError(f'cannot open {p}: {e.strerror or e}') from None
    dirs = []
    for c in children:
        if c.name.startswith(('.', '$')) or c.name in ('System Volume Information', '__pycache__', 'node_modules'):
            continue
        try:
            if c.is_dir():
                dirs.append(dict(name=c.name, path=str(c), project=(c / 'replay.toml').is_file()))
        except OSError:
            continue
    return dict(path=str(p), parent=str(p.parent) if p.parent != p else None, project=(p / 'replay.toml').is_file(),
                dirs=dirs, roots=roots(), home=str(pathlib.Path.home()))


class Studio:
    def __init__(self, project=None, config_dir=None):
        self.ctx = preview.Context(project)
        self.config_dir = pathlib.Path(config_dir) if config_dir else home()
        if project:
            self._remember(project)

    @property
    def project(self):
        return self.ctx.project

    def _settings(self):
        return read_json(self.config_dir / 'studio.json', {})

    def _remember(self, project):
        cfg = self._settings()
        root = str(project.root)
        recent = [r for r in cfg.get('recent', []) if r.get('path') != root]
        recent.insert(0, dict(path=root, title=summary(project)['title'], lang=project.lang))
        cfg['recent'] = recent[:RECENT_MAX]
        write_json(self.config_dir / 'studio.json', cfg)

    def state(self):
        recent = [dict(r, exists=(pathlib.Path(r['path']) / 'replay.toml').is_file()) for r in self._settings().get('recent', [])]
        return dict(version=__version__, project=summary(self.project) if self.project else None, recent=recent)

    def reload(self):
        """每次请求重新读项目：文件可能被 AI 或编辑器改过。"""
        if self.project:
            self.ctx.project = Project(self.project.root)
        return self.project

    def open(self, path):
        root = find_root(path) if path else None
        if root is None:
            raise StudioError(f'no replay.toml in {path} or its parent folders')
        project = Project(root)
        self.ctx.project = project
        self._remember(project)
        return summary(project)

    def new(self, path, title=None, lang='zh-CN'):
        if not path:
            raise StudioError('choose a folder')
        target = pathlib.Path(path)
        if target.exists() and not target.is_dir():
            raise StudioError(f'{target} is a file')
        try:
            root, _ = create(target, title or None, lang)
        except ProjectError as e:
            raise StudioError(str(e)) from None
        return self.open(root)

    def close(self):
        self.ctx.project = None
        return {}

    def board(self, lang=None):
        project = self.reload()
        if project is None:
            raise StudioError('no project is open')
        i18n.set_lang(lang or i18n.detect(project.lang))  # 任务标题跟着界面语言
        all_tasks = tasks.plan(project)
        nxt = tasks.next_task(project, all_tasks)
        return dict(tasks=[x.as_dict() for x in all_tasks], next=nxt.id if nxt else None, overview=tasks.overview(all_tasks))

    def done(self, tid, note=''):
        project = self.reload()
        try:
            return tasks.complete(project, tid, note)
        except tasks.TaskError as e:
            raise StudioError(str(e)) from None

    def run(self, task=None, stage=None, args=None):
        project = self.reload()
        try:
            argv = stage_command(project, stage, task, args)
        except ValueError as e:
            raise StudioError(str(e)) from None
        return jobs.start(project.root, argv)

    def jobs(self):
        keep = ('id', 'command', 'status', 'queued_at', 'started_at', 'ended_at', 'exit_code', 'waiting_for')
        return [{k: r.get(k) for k in keep if r.get(k) is not None} for r in reversed(jobs.listing(self.project.root, 30))]

    def job(self, jid, offset=0):
        if not re.fullmatch(r'[0-9A-Za-z-]+', jid):
            raise StudioError(f'no job {jid}')
        rec = jobs.get(self.project.root, jid, tail=1)
        if rec is None:
            raise StudioError(f'no job {jid}')
        rec.pop('log_tail', None)
        log = self.project.root / jobs.JOBS / f'{jid}.log'
        text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
        offset = max(0, min(int(offset or 0), len(text)))
        return dict(rec, log=text[offset:], offset=len(text))


def make_handler(studio):
    Base = preview.make_handler(studio.ctx)

    class Handler(Base):
        def _local(self):
            host = (self.headers.get('Host') or '').strip()
            host = host[1:host.index(']')] if host.startswith('[') else host.rsplit(':', 1)[0]
            if host in LOCAL_HOSTS:
                return True
            self._send(403, b'forbidden', 'text/plain')
            return False

        def _static(self, rel):
            target = STATIC / rel
            if not target.is_file():
                self._send(404, b'not found', 'text/plain')
                return
            self._send(200, target.read_bytes(), TYPES.get(pathlib.PurePosixPath(rel).suffix, 'application/octet-stream'))

        def _api(self, fn, *args, **kw):
            try:
                self._json(dict(ok=True, **fn(*args, **kw)))
            except StudioError as e:
                self._json(dict(ok=False, error=str(e)), 400)
            except ProjectError as e:
                self._json(dict(ok=False, error=str(e)), 400)

        def _need_project(self):
            if studio.project is None:
                self._json(dict(ok=False, error='no project is open'), 409)
                return False
            return True

        def do_GET(self):
            if not self._local():
                return
            url = urllib.parse.urlparse(self.path)
            path, q = urllib.parse.unquote(url.path), dict(urllib.parse.parse_qsl(url.query))
            if path in ('/', '/index.html'):
                self._static('index.html')
            elif path.startswith('/assets/') and '..' not in path:
                self._static(path.lstrip('/'))
            elif path == '/api/studio/state':
                self._api(studio.state)
            elif path == '/api/studio/browse':
                self._api(browse, q.get('path'))
            elif path == '/api/tasks':
                self._need_project() and self._api(studio.board, q.get('lang'))
            elif path == '/api/jobs':
                self._need_project() and self._api(lambda: dict(jobs=studio.jobs()))
            elif path.startswith('/api/jobs/'):
                self._need_project() and self._api(lambda: dict(job=studio.job(path.rsplit('/', 1)[1], q.get('offset', 0))))
            else:
                studio.reload()
                super().do_GET()

        def do_POST(self):
            if not self._local():
                return
            path = urllib.parse.urlparse(self.path).path
            if not (path.startswith('/api/studio/') or path in ('/api/tasks/done', '/api/run')):
                studio.reload()
                super().do_POST()
                return
            if self.headers.get('X-Rlyeh') != '1':
                self._send(403, b'missing X-Rlyeh header', 'text/plain')
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8') or '{}')
            except (ValueError, UnicodeDecodeError):
                self._json(dict(ok=False, error='bad JSON'), 400)
                return
            if path == '/api/studio/open':
                self._api(lambda: dict(project=studio.open(body.get('path'))))
            elif path == '/api/studio/new':
                self._api(lambda: dict(project=studio.new(body.get('path'), body.get('title'), body.get('lang') or 'zh-CN')))
            elif path == '/api/studio/close':
                self._api(studio.close)
            elif not self._need_project():
                return
            elif path == '/api/tasks/done':
                self._api(lambda: dict(record=studio.done(body.get('id', ''), body.get('note', ''))))
            elif path == '/api/run':
                self._api(lambda: dict(job=studio.run(body.get('task'), body.get('stage'), body.get('args'))))
            else:
                self._send(404, b'not found', 'text/plain')

    return Handler


def make_server(studio, host='127.0.0.1', port=8766):
    try:
        return preview.make_server(None, host, port, handler=make_handler(studio))
    except OSError:                                     # 端口被占了（也许开着 replay preview）：换个空端口
        return preview.make_server(None, host, 0, handler=make_handler(studio))


def serve(project=None, host='127.0.0.1', port=8766, on_ready=None):
    server = make_server(Studio(project), host, port)
    if on_ready:
        on_ready(f'http://{host}:{server.server_address[1]}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
