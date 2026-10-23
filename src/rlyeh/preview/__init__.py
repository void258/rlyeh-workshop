"""replay preview：本地小服务器（只用标准库），提供审核页和接口。只监听本机，只读写当前项目。

  /                  首页
  /voices            选声线：试听候选、选定（写 review/voice-pick.json）
  /review/voice      逐句审听：连续播放、看质检、标重做（写 review/voice-review.json）
  /files/<路径>      项目里的文件（音频等），不缓存，重做后马上听到新版本
"""
import http.server
import json
import urllib.parse
from importlib import resources

from .. import voice
from ..script.model import Scene
from ..state import State

STATIC = resources.files('rlyeh') / 'preview' / 'static'
PAGES = {'/': 'index.html', '/voices': 'voices.html', '/review/voice': 'review.html'}


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


def save_marks(project, body):
    """body: {id: {status, note}}。只接受 redo / pending / approved / skip。"""
    marks = voice.read_json(project.root / voice.REVIEW, {})
    for k, v in body.items():
        status = v.get('status', 'redo')
        if status not in ('redo', 'pending', 'approved', 'skip'):
            continue
        marks[k] = dict(status=status, note=str(v.get('note', ''))[:500], by=v.get('by', ''), at=voice.now())
    voice.write_json(project.root / voice.REVIEW, marks)
    return marks


def make_handler(project):
    root = project.root.resolve()

    class Handler(http.server.BaseHTTPRequestHandler):
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

        def do_GET(self):
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            if path in PAGES:
                self._send(200, (STATIC / PAGES[path]).read_bytes(), 'text/html; charset=utf-8')
            elif path == '/api/voices':
                self._json(voices_data(project))
            elif path == '/api/lines':
                self._json(lines_data(project))
            elif path.startswith('/files/'):
                target = (root / path[len('/files/'):]).resolve()
                if root not in target.parents or not target.is_file():
                    self._send(404, b'not found', 'text/plain')
                    return
                ctype = {'.wav': 'audio/wav', '.flac': 'audio/flac', '.mp3': 'audio/mpeg', '.png': 'image/png',
                         '.webp': 'image/webp', '.json': 'application/json'}.get(target.suffix.lower(), 'application/octet-stream')
                self._send(200, target.read_bytes(), ctype)
            else:
                self._send(404, b'not found', 'text/plain')

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
                if path == '/api/voices/pick':
                    self._json(dict(ok=True, pick=voice.pick(project, body['id'], body['choice'], body.get('note', ''))))
                elif path == '/api/review':
                    self._json(dict(ok=True, marks=save_marks(project, body)))
                else:
                    self._send(404, b'not found', 'text/plain')
            except (ValueError, KeyError, voice.VoiceError) as e:
                self._json(dict(ok=False, error=str(e)), 400)

    return Handler


def make_server(project, host='127.0.0.1', port=8766):
    return http.server.ThreadingHTTPServer((host, port), make_handler(project))


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

