"""replay preview：本地小服务器（只用标准库），提供审核页和接口。只监听本机，只读写当前项目。

  /                  首页
  /voices            选声线：试听候选、选定（写 review/voice-pick.json）
  /review/voice      逐句审听：连续播放、看质检、标重做（写 review/voice-review.json）
  /review/art        美术审核：逐张通过或打回（写 review/art-review.json）
  /review/music      BGM 试听：每段曲子选一版（写 review/music-review.json，复制成 audio/bgm/<曲目ID>）
  /player            播放器（replay build 打包的 build/player/）
  /files/<路径>      项目里的文件（音频、图片），不缓存，重做后马上看到、听到新版本
"""
import http.server
import json
import re
import urllib.parse
from importlib import resources

from .. import art, backends, music, voice
from ..script.model import Scene
from ..state import State
from ..util import read_json, save_marks

STATIC = resources.files('rlyeh') / 'preview' / 'static'
SHARED = {'/static/common.css': 'text/css; charset=utf-8', '/static/common.js': 'text/javascript; charset=utf-8'}
PAGES = {'/': 'index.html', '/voices': 'voices.html', '/review/voice': 'review.html', '/review/art': 'art.html',
         '/review/music': 'music.html'}


def meta(project):
    p = project.config.get('project') or {}
    return dict(title=p.get('title', ''), lang=project.lang)


def voices_data(project):
    cands = voice.read_json(project.root / 'voices' / 'candidates.json', {})
    picks = voice.read_json(project.root / voice.PICK, {})
    chars = []
    for ch in voice.voiced_characters(project):
        chars.append(dict(id=ch.id, name=ch.name(project.lang), kind=ch.kind, color=ch.color, player=ch.player,
                          design=ch.voice.get('design', ''), reference=ch.voice.get('reference'),
                          candidates=[dict(c, url='/files/' + urllib.parse.quote(c['file'])) for c in cands.get(ch.id) or []],
                          pick=picks.get(ch.id)))
    return dict(meta=meta(project), characters=chars)


def lines_data(project):
    state = State(project.root)
    qa = voice.read_json(project.root / voice.QA_REPORT, {})
    marks = voice.read_json(project.root / voice.REVIEW, {})
    colors = {c.id: c.color for c in project.characters.values()}
    out = []
    for ch in project.chapters():
        out.append(dict(kind='chapter', title=f'{ch.number} · {ch.title}'))
        for it in ch.items:
            if isinstance(it, Scene):
                out.append(dict(kind='scene', title=it.title))
                continue
            if not hasattr(it, 'segments') or not it.voiced:
                continue
            v = project.voice_of(it)
            rec = state.get(f'{voice.VOICE_DIR}/{it.id}.wav')
            bleeped = (project.root / voice.BLEEP_DIR / f'{it.id}.wav').exists()
            audio = None
            if rec and (project.root / voice.VOICE_DIR / f'{it.id}.wav').exists():
                path = f'{voice.BLEEP_DIR if bleeped else voice.VOICE_DIR}/{it.id}.wav'
                audio = dict(url='/files/' + path + f'?v={rec.get("inputs", "")[-8:]}{rec.get("seed", "")}',
                             seconds=rec.get('seconds'), seed=rec.get('seed'), bleeped=bleeped)
            out.append(dict(kind=it.kind, id=it.id, who=it.speaker, voice=v, color=colors.get(v), tone=it.tone,
                            text=it.text, audio=audio, qa=qa.get(it.id)))
    return dict(meta=meta(project), lines=out, marks=marks)


def _url(project, rel):
    path = project.root / rel
    v = int(path.stat().st_mtime) if path.exists() else 0
    return '/files/' + urllib.parse.quote(rel) + f'?v={v}'


def art_data(project):
    state = State(project.root)
    reviews = read_json(project.root / art.REVIEW, {})
    checked = read_json(project.root / art.CHECK, {})
    items = []
    for job in art.load_jobs(project):
        if job.skip:
            continue
        exists = (project.root / job.out).exists()
        rec = state.get(job.out)
        if job.needs_prompt and not exists:
            status = 'needs_prompt'
        elif not exists:
            status = 'missing'
        elif rec and rec.get('inputs') != art._inputs(project, job):
            status = 'stale'
        else:
            status = 'done'
        items.append(dict(id=job.id, kind=job.kind, name=job.name, char=job.char, out=job.out, status=status,
                          url=_url(project, job.out) if exists else None, transparent=job.transparent,
                          notes=(checked.get(job.out) or {}).get('notes') or [], review=reviews.get(job.out)))
    chars = {c.id: dict(name=c.name(project.lang), color=c.color) for c in project.characters.values()}
    return dict(meta=meta(project), items=items, chars=chars)


def music_data(project):
    bid = (project.config.get('backends') or {}).get('music', backends.DEFAULTS['music'])
    reviews = read_json(project.root / music.REVIEW, {})
    checked = read_json(project.root / music.CHECK, {})
    out = []
    for cid, cue in music.cues(project).items():
        inputs = music._inputs(cue, bid)
        pick = reviews.get(cid)
        takes = [dict(key=k, url=_url(project, t['file']), file=t['file'], seed=t.get('seed'), seconds=t.get('seconds'),
                      current=t.get('source') == 'manual' or t.get('inputs') == inputs, check=checked.get(k),
                      picked=bool(pick and pick.get('choice') == t['file'])) for k, t in music.cue_takes(project, cid)]
        name = cue['names'].get(project.lang) or next(iter(cue['names'].values()), cid)
        out.append(dict(id=cid, name=name, style=cue['style'], lyrics=None if cue['instrumental'] else cue['lyrics'],
                        instrumental=cue['instrumental'], seconds=cue['seconds'], takes=takes, pick=pick))
    return dict(meta=meta(project), cues=out, battle=music.battle_cue(project))


class Context:
    """服务当前用的项目。replay preview 固定一个；Studio 里可以打开、关闭、切换（None 表示没打开项目）。"""
    def __init__(self, project=None):
        self.project = project


def make_handler(source):
    ctx = source if isinstance(source, Context) else Context(source)

    class Handler(http.server.BaseHTTPRequestHandler):
        context = ctx

        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code=200):
            self._send(code, json.dumps(data, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

        def _file(self, target, ctype):
            """发文件：分块读，支持 Range（视频、长音频才能拖进度条）。"""
            size = target.stat().st_size
            start, end, code = 0, size - 1, 200
            m = re.fullmatch(r'bytes=(\d*)-(\d*)', (self.headers.get('Range') or '').strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.end_headers()
                    return
                code = 206
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            if code == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            with open(target, 'rb') as f:
                f.seek(start)
                left = end - start + 1
                try:
                    while left > 0:
                        chunk = f.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass                                    # 浏览器拖进度条时会断开旧请求

        def _project(self):
            if ctx.project is None:
                self._json(dict(ok=False, error='no project is open'), 409)
            return ctx.project

        def do_GET(self):
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            if path in SHARED:                              # 审核页共用的样式和脚本，不需要项目
                self._send(200, (STATIC / path.rsplit('/', 1)[1]).read_bytes(), SHARED[path])
                return
            project = self._project()
            if project is None:
                return
            root = project.root.resolve()
            if path in ('/player', '/player/'):             # replay build 打出来的播放器
                self.send_response(302)
                self.send_header('Location', '/files/build/player/index.html')
                self.end_headers()
            elif path in PAGES:
                self._send(200, (STATIC / PAGES[path]).read_bytes(), 'text/html; charset=utf-8')
            elif path == '/api/voices':
                self._json(voices_data(project))
            elif path == '/api/lines':
                self._json(lines_data(project))
            elif path == '/api/art':
                self._json(art_data(project))
            elif path == '/api/music':
                self._json(music_data(project))
            elif path.startswith('/files/'):
                target = (root / path[len('/files/'):]).resolve()
                if root not in target.parents or not target.is_file():
                    self._send(404, b'not found', 'text/plain')
                    return
                ctype = {'.wav': 'audio/wav', '.flac': 'audio/flac', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg',
                         '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                         '.json': 'application/json', '.html': 'text/html; charset=utf-8', '.mp4': 'video/mp4',
                         '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}.get(target.suffix.lower(), 'application/octet-stream')
                self._file(target, ctype)
            else:
                self._send(404, b'not found', 'text/plain')

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            project = self._project()
            if project is None:
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
                if path == '/api/voices/pick':
                    self._json(dict(ok=True, pick=voice.pick(project, body['id'], body['choice'], body.get('note', ''))))
                elif path == '/api/review':
                    self._json(dict(ok=True, marks=save_marks(project.root / voice.REVIEW, body)))
                elif path == '/api/art/review':
                    self._json(dict(ok=True, marks=save_marks(project.root / art.REVIEW, body)))
                elif path == '/api/music/pick':
                    self._json(dict(ok=True, pick=music.pick(project, body['id'], body['choice'], body.get('note', ''))))
                else:
                    self._send(404, b'not found', 'text/plain')
            except (ValueError, KeyError, AttributeError, voice.VoiceError, music.MusicError, art.ArtError) as e:
                self._json(dict(ok=False, error=str(e)), 400)

    return Handler


def make_server(project, host='127.0.0.1', port=8766, handler=None):
    return http.server.ThreadingHTTPServer((host, port), handler or make_handler(project))


def serve(project, host='127.0.0.1', port=8766, on_ready=None):
    server = make_server(project, host, port)
    if on_ready:
        on_ready(f'http://{host}:{server.server_address[1]}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

