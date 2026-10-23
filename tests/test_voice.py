import json
import threading
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from rlyeh import backends, i18n, voice
from rlyeh.backends.drama3 import Drama3
from rlyeh.cli import main
from rlyeh.preview import make_server
from rlyeh.project import Project

SCRIPT = """---
chapter: 1
title: 雾港
lang: zh-CN
---

## 第一幕　雾中

旁白：〔讲述〕灯塔已经三天没有亮过了。 ^c1-0001
阿洛：〔压低声音〕门是从里面锁上的。 ^c1-0002
阿洛：〔骂〕{sb}才走正门。 ^c1-0003
> GM：〔笑着〕过个力量检定吧。 ^c1-0004
"""


@pytest.fixture
def proj(tmp_path, capsys):
    i18n.set_lang('zh-CN')
    root = tmp_path / 'demo'
    main(['init', str(root), '--json'])
    capsys.readouterr()
    cfg = (root / 'replay.toml').read_text(encoding='utf-8')
    cfg = cfg.replace('tts = "drama3"', 'tts = "placeholder"\nvoice_design = "placeholder"').replace('asr = "sensevoice"', 'asr = "none"')
    cfg = cfg.replace('[spoken]', '[spoken]\n"sb" = "傻逼"')
    (root / 'replay.toml').write_text(cfg, encoding='utf-8')
    (root / 'script' / '01-chapter.md').write_text(SCRIPT, encoding='utf-8')
    yield Project(root)
    i18n.set_lang(None)


class FakeASR:
    def __init__(self, answers):
        self.answers = answers

    def transcribe(self, files, language='zh-CN', on_line=None):
        return {f: self.answers.get(f.replace('\\', '/').rsplit('/', 1)[1][:-4], '') for f in files}


def use_fake(monkeypatch, kind, obj):
    real = backends.get
    monkeypatch.setattr(backends, 'get', lambda project, k, name=None: obj if k == kind else real(project, k, name))


def test_design_pick_reference(proj):
    index = voice.design(proj)
    assert set(index) == {'narrator', 'gm', 'hero'} and len(index['hero']) == 3
    assert (proj.root / index['hero'][1]['file']).exists()
    voice.pick(proj, 'hero', 2)
    path, text = voice.reference(proj, 'hero')
    assert path.name == 'hero_2.wav' and text == voice.SAMPLE['zh-CN']
    assert voice.reference(proj, 'gm') is None


def test_build_is_incremental(proj):
    done = voice.build(proj)
    assert sorted(done) == ['c1-0001', 'c1-0002', 'c1-0003', 'c1-0004']
    assert voice.build(proj) == {}
    script = proj.root / 'script' / '01-chapter.md'
    script.write_text(script.read_text(encoding='utf-8').replace('门是从里面锁上的', '门锁死了'), encoding='utf-8')
    todo, _ = voice.plan(Project(proj.root))
    assert [t['id'] for t in todo] == ['c1-0002']
    s = voice.summary(Project(proj.root))
    assert (s['lines'], s['done'], s['stale'], s['todo']) == (4, 3, 1, 0)


def test_tts_text_uses_spoken_forms(proj):
    it = next(i for ch in proj.chapters() for i in ch.spoken if i.id == 'c1-0003')
    assert proj.tts_text(it) == '傻逼才走正门。'


def test_score():
    good = voice.score('门是从里面锁上的。', '门是从里面锁上的', 3.0, 'zh-CN')
    assert good['sim'] == 1.0 and not good['bad']
    assert voice.score('封印？', '枫叶', 1.0, 'zh-CN')['bad']
    assert voice.score('白石白石。', '白石白石', 65.0, 'zh-CN')['too_long']
    assert voice.score('幺幺六这骰运', '116这骰运', 2.0, 'zh-CN')['sim'] == 1.0
    assert not voice.score("It's locked from the inside.", 'its locked from the inside', 2.5, 'en')['bad']


def test_qa_and_redo(proj, monkeypatch):
    voice.build(proj)
    answers = {'c1-0001': '灯塔已经三天没有亮过了', 'c1-0002': '完全不对的一句话啊', 'c1-0003': '傻逼才走正门', 'c1-0004': '过个力量检定吧'}
    use_fake(monkeypatch, 'asr', FakeASR(answers))
    report = voice.qa(proj)
    assert [k for k, v in report.items() if v['bad']] == ['c1-0002'] and voice.failed(proj) == ['c1-0002']
    voice.write_json(proj.root / voice.REVIEW, {'c1-0002': {'status': 'redo', 'note': ''}})
    answers['c1-0002'] = '门是从里面锁上的'                     # 换种子后念对了
    assert voice.redo(proj, ['c1-0002']) == []
    assert voice.read_json(proj.root / voice.REVIEW, {})['c1-0002']['status'] == 'pending'
    rec = voice.read_json(proj.root / '.rlyeh' / 'state.json', {})['artifacts']['audio/voice/c1-0002.wav']
    assert rec['seed'] == voice.SEEDS[1]


def test_bleep(proj, monkeypatch):
    voice.build(proj)
    src = proj.root / voice.VOICE_DIR / 'c1-0003.wav'
    y, sr = sf.read(src)

    class FakeAlign:
        def align(self, items, on_line=None):
            out = []
            for it in items:
                n = len(it['chars'])
                step = len(y) / sr * 1000 / n
                out.append([[round(i * step), round((i + 1) * step)] for i in range(n)])
            return out
    use_fake(monkeypatch, 'align', FakeAlign())
    done, problems = voice.bleep(proj)
    assert list(done) == ['c1-0003'] and not problems
    assert done['c1-0003'][0][0] == 0                                  # 句首的词从 0 开始盖
    b, _ = sf.read(proj.root / voice.BLEEP_DIR / 'c1-0003.wav')
    seg = b[int(.05 * sr):int(.25 * sr)]
    freq = np.argmax(np.abs(np.fft.rfft(seg))) * sr / len(seg)
    assert abs(freq - 1000) < 20
    assert voice.bleep(proj) == ({}, [])                               # 已经是最新的，不重做
    # 消音后再识别：还听得出「傻逼」就报出来，同音字也算
    use_fake(monkeypatch, 'asr', FakeASR({'c1-0003': '沙比才走正门'}))
    it = next(i for ch in proj.chapters() for i in ch.spoken if i.id == 'c1-0003')
    assert voice.recheck(proj, [(it, 'zh-CN')])[0]['id'] == 'c1-0003'
    use_fake(monkeypatch, 'asr', FakeASR({'c1-0003': '才走正门'}))
    assert voice.recheck(proj, [(it, 'zh-CN')]) == []


def test_drama3_request(proj, tmp_path):
    ref = tmp_path / '参考.wav'
    sf.write(ref, np.zeros(2400, np.float32), 24000)
    d = Drama3({'cli': 'x.exe', 'model': 'm.gguf', 'work_dir': str(tmp_path / 'work')}, proj)
    req = d.request(dict(id='c1-0002', text='门锁死了。', tone='压低声音', refs=[(ref, '参考文字')], seed=7))
    assert req['text'] == '[压低声音]门锁死了。' and req['seed'] == 7
    refs = json.loads(req['options']['references'])
    assert refs[0]['text'] == '参考文字' and refs[0]['audio_path'].isascii()


def test_preview_server(proj):
    voice.design(proj)
    voice.build(proj)
    server = make_server(proj, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        get = lambda p: json.loads(urllib.request.urlopen(base + p).read())          # noqa: E731
        v = get('/api/voices')
        assert {c['id'] for c in v['characters']} == {'narrator', 'gm', 'hero'}
        lines = get('/api/lines')['lines']
        line = next(x for x in lines if x.get('id') == 'c1-0002')
        assert line['voice'] == 'hero' and line['audio']['seconds'] > 0
        assert urllib.request.urlopen(base + line['audio']['url']).status == 200
        req = urllib.request.Request(base + '/api/review', json.dumps({'c1-0002': {'status': 'redo', 'note': '凶一点'}}).encode(),
                                     {'Content-Type': 'application/json'})
        assert json.loads(urllib.request.urlopen(req).read())['marks']['c1-0002']['note'] == '凶一点'
        assert voice.marked(proj) == ['c1-0002']
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + '/files/..%2F..%2Fsecret.txt')
        for page in ('/', '/voices', '/review/voice'):
            assert b'<script>' in urllib.request.urlopen(base + page).read()
    finally:
        server.shutdown()


def test_cli_voice(proj, capsys):
    assert main(['voice', 'design', '-C', str(proj.root), '--json']) == 0
    capsys.readouterr()
    assert main(['voice', 'build', '-C', str(proj.root), '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out['built']) == 4
    assert main(['voice', 'qa', '-C', str(proj.root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['skipped'] is True
    assert main(['status', '-C', str(proj.root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['voice']['done'] == 4
