import http.server
import io
import json
import threading
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from rlyeh import backends, music
from rlyeh.backends import BackendInfo
from rlyeh.cli import main
from rlyeh.preview import make_server
from rlyeh.util import read_json

VOCAL_ABC = 'X:1\nL:1/8\nK:C\nV:Vocal\n"Am" A2 B c | z4 |\nV:Piano\n"Am" [ACE]4 |\n'
CLEAN_ABC = 'X:1\nL:1/8\nK:C\nV:Vocal\n"Am" z4 | z4 |\n% A B c\nV:Piano\n"Am" [ACE]4 |\n'

SONG = """
battle: fight
cues:
  main:
    name: { zh-CN: 主题, en: Main theme }
    style: Instrumental, no vocals, calm harp
    seconds: 30
  fight:
    name: 战斗
    style: Instrumental, no vocals, war drums
  ending:
    name: 片尾曲
    style: Mandarin Chinese, warm female vocal
    lyrics: |
      [Verse]
      雾还没散去
"""


def test_vocal_notes():
    assert music.vocal_notes(VOCAL_ABC) == 3
    assert music.vocal_notes(CLEAN_ABC) == 0


def test_cues(make_project):
    proj = make_project()
    (proj.root / 'music.yaml').write_text(SONG, encoding='utf-8')
    cs = music.cues(proj)
    assert cs['main']['instrumental'] and cs['main']['lyrics'] == music.INSTRUMENTAL and cs['main']['seconds'] == 30
    assert not cs['ending']['instrumental'] and cs['ending']['lyrics'].startswith('[Verse]')
    assert cs['fight']['seconds'] == 160
    assert music.battle_cue(proj) == 'fight'
    assert music.resolve(proj, '主题') == 'main' and music.resolve(proj, 'Main theme') == 'main'
    assert music.resolve(proj, 'ending') == 'ending' and music.resolve(proj, '没有') is None
    (proj.root / 'music.yaml').write_text('cues:\n  主题: {style: x}\n', encoding='utf-8')
    with pytest.raises(music.MusicError):
        music.cues(proj)


def test_gen_pick_placeholder(make_project):
    proj = make_project({'music': 'placeholder'})
    res = music.gen(proj)
    assert res['done'] == ['main_s3001', 'battle_s3001'] and not res['problems']
    assert music.gen(proj)['done'] == []
    assert music.gen(proj, {'main'}, n_takes=2)['done'] == ['main_s3002']
    rec = music.pick(proj, 'main', 2)
    assert rec['choice'] == 'audio/bgm/takes/main_s3002.flac' and (proj.root / 'audio/bgm/main.flac').exists()
    music.pick(proj, 'main', 'main_s3001')
    assert read_json(proj.root / music.REVIEW, {})['main']['choice'].endswith('main_s3001.flac')
    with pytest.raises(music.MusicError):
        music.pick(proj, 'main', 9)
    s = music.summary(proj)
    assert (s['cues'], s['with_takes'], s['takes'], s['picked']) == (2, 2, 3, 1)


def test_manual_takes(make_project):
    proj = make_project()
    res = music.gen(proj)
    assert [w['id'] for w in res['waiting']] == ['main', 'battle']
    (proj.root / music.TAKES_DIR).mkdir()
    sf.write(proj.root / 'audio/bgm/takes/main_mine.wav', np.zeros(4800, np.float32), 48000)
    ts = music.takes(proj)
    assert ts['main_mine']['source'] == 'manual' and ts['main_mine']['cue'] == 'main'
    assert [w['id'] for w in music.gen(proj)['waiting']] == ['battle']


class FakeComfy(http.server.BaseHTTPRequestHandler):
    graphs = {}

    def log_message(self, *a):
        pass

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        g = json.loads(self.rfile.read(int(self.headers['Content-Length'])))['prompt']
        pid = f'p{len(FakeComfy.graphs)}'
        FakeComfy.graphs[pid] = g
        self._json({'prompt_id': pid})

    def do_GET(self):
        if self.path.startswith('/history/'):
            pid = self.path.rsplit('/', 1)[1]
            g = FakeComfy.graphs[pid]
            seed = g['3']['inputs']['seed']
            if g['4']['class_type'] == 'PreviewAny':
                out = {'4': {'text': [VOCAL_ABC if seed == 3001 else CLEAN_ABC]}}
            else:
                out = {'4': {'audio': [{'filename': f'x_{seed}.flac', 'subfolder': 'demo', 'type': 'output'}]}}
            self._json({pid: {'status': {'completed': True, 'status_str': 'success'}, 'outputs': out}})
        elif self.path.startswith('/view'):
            buf = io.BytesIO()
            sf.write(buf, np.zeros((48000, 2), np.float32), 48000, format='FLAC')
            data = buf.getvalue()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)


@pytest.fixture
def comfy():
    FakeComfy.graphs = {}
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeComfy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()


def test_yue2_searches_for_vocal_free_score(make_project, comfy):
    proj = make_project({'music': 'yue2-comfyui'}, extra=f'[backends.yue2-comfyui]\nurl = "{comfy}"\npoll = 0.01\n')
    (proj.root / 'music.yaml').write_text(SONG, encoding='utf-8')
    res = music.gen(proj, {'main', 'ending'})
    assert res['done'] == ['main_s3002', 'ending_s3001'] and not res['problems']
    graphs = list(FakeComfy.graphs.values())
    kinds = [(g['4']['class_type'], g['3']['inputs']['seed']) for g in graphs]
    assert kinds == [('PreviewAny', 3001), ('PreviewAny', 3002), ('SaveAudio', 3002), ('SaveAudio', 3001)]
    assert graphs[2]['3']['inputs']['abc'] == CLEAN_ABC                       # 用找到的那份乐谱渲染
    assert graphs[2]['3']['inputs']['semantic_max_tokens'] == 30 * 25
    assert 'abc' not in graphs[3]['3']['inputs'] and '雾还没散去' in graphs[3]['3']['inputs']['lyrics']   # 带词的歌直接渲染
    assert (proj.root / 'audio/bgm/takes/main_s3002.abc').read_text(encoding='utf-8') == CLEAN_ABC
    assert read_json(proj.root / music.PLANS, {})['main']['seeds'] == {'3001': 3, '3002': 0}
    take = music.takes(proj)['main_s3002']
    assert take['searched'] and take['seconds'] == 1.0
    FakeComfy.graphs = {}
    assert music.gen(proj, {'main'}, n_takes=2)['done'] == ['main_s3003']
    assert [g['3']['inputs']['seed'] for g in FakeComfy.graphs.values()][0] == 3003      # 已知有人声的种子不再试


class FakeASR:
    info = BackendInfo(id='fake', kind='asr')

    def transcribe(self, files, language='zh-CN', on_line=None):
        assert language == 'auto'
        return {f: ('啦啦啦我们走吧' if i == 0 else '') for i, f in enumerate(files)}


def test_check_flags_vocals(make_project, monkeypatch):
    proj = make_project({'music': 'placeholder'})
    music.gen(proj)
    real = backends.get
    monkeypatch.setattr(backends, 'get', lambda p, k, name=None: FakeASR() if k == 'asr' else real(p, k, name))
    report = music.check(proj)
    assert not report['main_s3001']['clean'] and report['main_s3001']['words'][0]['text'] == '啦啦啦我们走吧'
    assert report['battle_s3001']['clean'] and report['battle_s3001']['seconds'] == 20.0
    assert music.check(proj) == report                                       # 文件没变不重查
    assert music.summary(proj)['vocals'] == 1


def test_music_page_and_cli(make_project, capsys):
    proj = make_project({'music': 'placeholder', 'asr': 'none'})
    assert main(['music', 'gen', '-C', str(proj.root), '--json']) == 0
    assert len(json.loads(capsys.readouterr().out)['done']) == 2
    assert main(['music', 'check', '-C', str(proj.root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['skipped'] is True
    server = make_server(proj, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        d = json.loads(urllib.request.urlopen(base + '/api/music').read())
        assert [c['id'] for c in d['cues']] == ['main', 'battle'] and d['battle'] == 'battle'
        take = d['cues'][0]['takes'][0]
        assert take['current'] and urllib.request.urlopen(base + take['url']).status == 200
        req = urllib.request.Request(base + '/api/music/pick', json.dumps({'id': 'main', 'choice': take['key']}).encode(),
                                     {'Content-Type': 'application/json'})
        assert json.loads(urllib.request.urlopen(req).read())['pick']['status'] == 'approved'
        assert json.loads(urllib.request.urlopen(base + '/api/music').read())['cues'][0]['takes'][0]['picked']
        assert b'<script>' in urllib.request.urlopen(base + '/review/music').read()
    finally:
        server.shutdown()
    assert main(['status', '-C', str(proj.root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['music']['picked'] == 1
