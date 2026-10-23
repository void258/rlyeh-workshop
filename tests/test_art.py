import json
import sys
import threading
import urllib.request

import numpy as np
import pytest
from PIL import Image

from rlyeh import art
from rlyeh.backends import BackendError
from rlyeh.backends.codex_image import CodexImage
from rlyeh.cli import main
from rlyeh.preview import make_server
from rlyeh.project import Project
from rlyeh.util import read_json, slug

SCRIPT = """---
chapter: 1
title: 雾港
---

## 第一幕　雾中

【背景：灯塔底层｜夜】
旁白：〔讲述〕灯塔已经三天没有亮过了。 ^c1-0001
【CG：灯塔熄灭】
【道具：铜钥匙】
【背景：灯塔底层｜黎明】
"""


def fill_todo(project):
    for f in (project.root / art.PROMPTS).rglob('*.md'):
        f.write_text(f.read_text(encoding='utf-8').replace('<!-- TODO', '夜里起雾。<!-- 写好了'), encoding='utf-8')


@pytest.fixture
def proj(make_project):
    return make_project({'image': 'placeholder'}, SCRIPT)


def test_slug():
    assert [slug(x) for x in ['平静', '羊角旅馆', 'YC116', "Ram's Horn Inn"]] == ['pingjing', 'yangjiaolvguan', 'yc116', 'ram-s-horn-inn']


def test_scaffold(proj):
    created, have = art.scaffold(proj)
    assert have == 0
    assert set(created) == {'sprites/hero_pingjing', 'sprites/hero_jingti', 'sprites/hero_jingya',
                            'backgrounds/dengtadiceng', 'cg/dengtaximie', 'items/tongyaoshi'}
    jobs = {j.id: j for j in art.load_jobs(proj)}
    base, expr = jobs['sprites/hero_pingjing'], jobs['sprites/hero_jingti']
    assert base.kind == 'sprite' and base.transparent and '阿洛' in base.body and '神情平静' in base.body
    assert expr.kind == 'expression' and expr.base == base.out and '只修改表情' in expr.body
    assert jobs['backgrounds/dengtadiceng'].needs_prompt and not base.needs_prompt
    assert jobs['backgrounds/dengtadiceng'].name == '灯塔底层'
    path = proj.root / art.PROMPTS / 'sprites' / 'hero_pingjing.md'
    path.write_text(path.read_text(encoding='utf-8') + '\n人改过的\n', encoding='utf-8')
    assert art.scaffold(proj) == ([], 6)                                     # 已有的文件一律不动
    assert '人改过的' in path.read_text(encoding='utf-8')


def test_prompt_strips_comments_and_appends(proj):
    art.scaffold(proj)
    job = next(j for j in art.load_jobs(proj) if j.id == 'cg/dengtaximie')
    job.body = '画面：灯塔熄灭。<!-- 给人看的备注 -->'
    assert art.prompt(proj, job) == '画面：灯塔熄灭。\n\n不要假细节假纹理'


def test_run_is_incremental(proj):
    art.scaffold(proj)
    res = art.run(proj)
    assert set(res['done']) == {'sprites/hero_pingjing', 'sprites/hero_jingti', 'sprites/hero_jingya'}
    assert {b['id'] for b in res['blocked']} == {'backgrounds/dengtadiceng', 'cg/dengtaximie', 'items/tongyaoshi'}
    fill_todo(proj)
    res = art.run(proj)
    assert set(res['done']) == {'backgrounds/dengtadiceng', 'cg/dengtaximie', 'items/tongyaoshi'}
    assert art.run(proj)['done'] == []
    # 改基础立绘的提示词：基础图重画，两张差分跟着过期
    path = proj.root / art.PROMPTS / 'sprites' / 'hero_pingjing.md'
    path.write_text(path.read_text(encoding='utf-8').replace('棕色短发', '黑色长发'), encoding='utf-8')
    assert art.summary(proj)['stale'] == 1
    res = art.run(proj)
    assert set(res['done']) == {'sprites/hero_pingjing', 'sprites/hero_jingti', 'sprites/hero_jingya'}
    assert (proj.root / art.RAW / 'history' / 'sprites' / 'hero' / 'hero_pingjing.1.png').exists()
    s = art.summary(proj)
    assert (s['jobs'], s['done'], s['stale'], s['todo'], s['needs_prompt']) == (6, 6, 0, 0, 0)


def test_compose_keeps_base_alpha(proj):
    art.scaffold(proj)
    art.run(proj, kinds={'sprite', 'expression'})
    base = np.asarray(Image.open(proj.root / 'art/sprites/hero/hero_pingjing.png')).astype(int)
    var = np.asarray(Image.open(proj.root / 'art/sprites/hero/hero_jingti.png')).astype(int)
    assert (base[..., 3] == var[..., 3]).all()
    ys, xs = np.nonzero(np.abs(base - var).sum(2))
    assert ys.size and ys.min() > 50 and ys.max() < 210 and xs.min() > 186 and xs.max() < 326     # 只动了头里面
    assert (proj.root / art.RAW / 'sprites' / 'hero' / 'hero_jingti.png').exists()
    assert art.compose_all(proj).keys() == {'sprites/hero_jingti', 'sprites/hero_jingya'}


def test_manual_backend_waits_and_adopts(make_project):
    proj = make_project({'image': 'manual'}, SCRIPT)
    art.scaffold(proj)
    fill_todo(proj)
    res = art.run(proj)
    assert res['done'] == [] and len(res['waiting']) == 6
    out = proj.root / 'art/backgrounds/dengtadiceng.png'
    Image.new('RGB', (64, 36), (10, 20, 30)).save(out)
    res = art.run(proj)
    assert res['adopted'] == ['backgrounds/dengtadiceng'] and len(res['waiting']) == 5
    path = proj.root / art.PROMPTS / 'backgrounds' / 'dengtadiceng.md'
    path.write_text(path.read_text(encoding='utf-8').replace('夜里起雾', '白天放晴'), encoding='utf-8')
    assert 'backgrounds/dengtadiceng' in [w['id'] for w in art.run(proj)['waiting']]       # 图没换：还在等
    Image.new('RGB', (64, 36), (200, 200, 30)).save(out)
    assert art.run(proj)['done'] == ['backgrounds/dengtadiceng']


def test_never_overwrites_hand_placed_images(proj):
    art.scaffold(proj)
    out = proj.root / 'art/sprites/hero/hero_pingjing.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGBA', (512, 768), (1, 2, 3, 0)).save(out)
    res = art.run(proj, kinds={'sprite'})
    assert res['adopted'] == ['sprites/hero_pingjing'] and res['done'] == []
    assert Image.open(out).getpixel((0, 0)) == (1, 2, 3, 0)


def test_check_and_overview(proj):
    art.scaffold(proj)
    art.run(proj, kinds={'sprite', 'expression'})
    Image.new('RGB', (512, 768), (90, 90, 90)).save(proj.root / 'art/sprites/hero/hero_jingya.png')     # 没有透明通道
    report, sheets = art.check(proj)
    assert report['art/sprites/hero/hero_pingjing.png']['status'] == 'ok'
    assert report['art/sprites/hero/hero_jingya.png']['status'] == 'warn'
    assert report['art/backgrounds/dengtadiceng.png']['status'] == 'needs_prompt'
    assert sheets == ['art/_overview/sprites_hero.png'] and (proj.root / sheets[0]).exists()


FAKE_CODEX = r'''
import os, pathlib, re, sys
from PIL import Image
args = sys.argv[1:]
text = sys.stdin.buffer.read().decode('utf-8')
here = pathlib.Path(__file__).parent
(here / 'args.txt').write_text('\n'.join(args), encoding='utf-8')
(here / 'stdin.txt').write_bytes(text.encode('utf-8'))
target = re.search(r'复制到：(.+)', text).group(1).strip()
img = Image.new('RGBA', (64, 96), (0, 0, 0, 0))
if os.environ.get('FAKE_CODEX_MODE') == 'leave':          # 不复制，图留在 Codex 自己的输出目录
    gen = pathlib.Path(os.environ['CODEX_HOME']) / 'generated_images' / 'sess'
    gen.mkdir(parents=True, exist_ok=True)
    img.save(gen / 'ig_1.png')
else:
    img.save(target)
pathlib.Path(args[args.index('-o') + 1]).write_text(target, encoding='utf-8')
'''


@pytest.fixture
def codex_proj(make_project, tmp_path, monkeypatch):
    fake = tmp_path / 'fake' / 'codex.py'
    fake.parent.mkdir()
    fake.write_text(FAKE_CODEX, encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'codex-home'))
    extra = (f'[harness.codex]\nmodel = "gpt-test"\neffort = "low"\n\n'
             f'[backends.codex]\nbin = ["{sys.executable.replace(chr(92), "/")}", "{fake.as_posix()}"]\n')
    return make_project({'image': 'codex'}, SCRIPT, extra), fake.parent


def test_codex_backend(codex_proj, monkeypatch):
    proj, fake = codex_proj
    art.scaffold(proj)
    res = art.run(proj, kinds={'sprite', 'expression'})
    assert set(res['done']) == {'sprites/hero_pingjing', 'sprites/hero_jingti', 'sprites/hero_jingya'}
    args = (fake / 'args.txt').read_text(encoding='utf-8').split('\n')
    assert args[:3] == ['exec', '-m', 'gpt-test'] and 'model_reasoning_effort="low"' in args
    assert args[-1] == '-' and any(a.startswith('--image=') and a.endswith('hero_pingjing.png') for a in args)
    stdin = (fake / 'stdin.txt').read_bytes().decode('utf-8')
    job = next(j for j in art.load_jobs(proj) if j.id == 'sprites/hero_jingya')
    assert stdin.endswith(art.prompt(proj, job) + '\n')                          # 提示词原样附在最后
    assert '不要上网搜索' in stdin and '透明背景' in stdin and '第一张（hero_pingjing.png）是要修改的原图' in stdin
    monkeypatch.setenv('FAKE_CODEX_MODE', 'leave')
    res = art.run(proj, ids={'sprites/hero_pingjing'}, force=True)
    assert res['done'] == ['sprites/hero_pingjing'] and (proj.root / 'art/sprites/hero/hero_pingjing.png').exists()


def test_codex_needs_model_and_effort(make_project):
    proj = make_project({'image': 'codex'}, SCRIPT)
    with pytest.raises(BackendError, match='harness.codex'):
        CodexImage({}, proj)


def test_art_review_api(proj):
    art.scaffold(proj)
    art.run(proj, kinds={'sprite'})
    server = make_server(proj, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        d = json.loads(urllib.request.urlopen(base + '/api/art').read())
        items = {x['id']: x for x in d['items']}
        assert items['sprites/hero_pingjing']['status'] == 'done' and items['sprites/hero_pingjing']['url']
        assert items['backgrounds/dengtadiceng']['status'] == 'needs_prompt'
        assert urllib.request.urlopen(base + items['sprites/hero_pingjing']['url']).status == 200
        out = 'art/sprites/hero/hero_pingjing.png'
        req = urllib.request.Request(base + '/api/art/review', json.dumps({out: {'status': 'redo', 'note': '再凶一点'}}).encode(),
                                     {'Content-Type': 'application/json'})
        assert json.loads(urllib.request.urlopen(req).read())['marks'][out]['note'] == '再凶一点'
        assert art.marked(proj) == [out]
        assert b'<script>' in urllib.request.urlopen(base + '/review/art').read()
    finally:
        server.shutdown()
    res = art.run(Project(proj.root), only_marked=True)                          # 打回的重画，审核状态回到待审
    assert res['done'] == ['sprites/hero_pingjing']
    assert read_json(proj.root / art.REVIEW, {})[out]['status'] == 'pending'


def test_cli_art(proj, capsys):
    assert main(['art', 'jobs', '-C', str(proj.root), '--json']) == 0
    assert len(json.loads(capsys.readouterr().out)['needs_prompt']) == 3
    assert main(['art', 'run', '-C', str(proj.root), '--json', '--kind', 'sprite']) == 0
    assert json.loads(capsys.readouterr().out)['done'] == ['sprites/hero_pingjing']
    assert main(['status', '-C', str(proj.root), '--json']) == 0
    s = json.loads(capsys.readouterr().out)['art']
    assert (s['done'], s['todo'], s['needs_prompt']) == (1, 2, 3)
