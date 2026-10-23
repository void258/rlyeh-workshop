import json
import os
import shutil
import subprocess
import threading
import urllib.request

import pytest

from rlyeh import art, player
from rlyeh.cli import main
from rlyeh.preview import make_server
from rlyeh.project import Project


def steps(d):
    return [s for ch in d['chapters'] for s in ch['steps']]


def test_build_data(full_project):
    proj = full_project()
    path = proj.root / 'script' / '01-chapter.md'                             # 素材都做完以后再加，让它们缺着
    path.write_text(path.read_text(encoding='utf-8') + '【CG：不存在的图】\n【音效：不存在的声音】\n【BGM：不存在的曲子】\n【音效：破门】\n',
                    encoding='utf-8')
    proj = Project(proj.root)
    res = player.build(proj)
    assert res['missing']['images'] == ['cg: 不存在的图']
    assert res['missing']['sfx'] == ['不存在的声音'] and res['missing']['bgm'] == ['不存在的曲子'] and not res['missing']['voice']
    d = player.data(proj)
    hero = d['chars']['hero']
    assert hero['name'] == '阿洛' and hero['default'] == '平静' and set(hero['faces']) == {'平静', '警惕', '惊讶'}
    assert d['who']['阿洛'] == 'hero' and d['players']['GM']['gm'] and d['players']['小林']['char'] == 'hero'
    out = proj.root / player.OUT
    for rel in [*hero['faces'].values(), hero['avatar'], *d['bg'].values(), *d['cg'].values(), *d['items'].values()]:
        assert (out / rel).exists(), rel
    ss = steps(d)
    by = lambda name: [s['args'] for s in ss if s.get('name') == name]   # noqa: E731
    assert by('bg') == [['灯塔底层', 'night', 'fog']]                            # 枚举换成规范值
    assert by('roll') == [['hero', '力量检定', '14', 'success']]                  # 角色名换成 ID
    assert by('enter') == [['hero', 'left', 'ghost']] and by('fx') == [['door-break']] and by('damage') == [['hero', '3']]
    assert by('bgm') == [['battle'], ['不存在的曲子']] and by('sfx') == [['不存在的声音'], ['door_break']]
    line = next(s for s in ss if s.get('id') == 'c1-0002')
    assert line['who'] == 'hero' and line['face'] == '警惕' and line['voice'] == 'audio/voice/c1-0002.wav' and line['sec'] > 0
    assert os.path.samefile(out / line['voice'], proj.root / line['voice'])        # 音频是硬链接（或者复制），不转码
    assert d['sfx']['door_break']['gain'] == .9 and d['bgm'] == {'main': 'audio/bgm/main.flac', 'battle': 'audio/bgm/battle.flac'}
    assert d['battle'] == 'battle' and d['title_screen'] == {'bg': '灯塔底层', 'variants': ['night', 'fog'], 'bgm': 'main'}
    assert [s['h'] for s in d['credits']['sections']] == ['主持', '玩家', '音效'] and d['credits']['end'] == '完'
    assert d['chapters'][0]['label'] == '第一章　开场'


def test_rebuild_prunes_and_credits(full_project):
    proj = full_project()
    player.build(proj)
    out = proj.root / player.OUT
    (proj.root / 'art/items/tongyaoshi.png').unlink()
    for f in (proj.root / art.PROMPTS / 'items').glob('*.md'):
        f.unlink()
    cfg = proj.root / 'replay.toml'
    cfg.write_text(cfg.read_text(encoding='utf-8').replace('[project]', '[project]\nsession_dates = ["2022-07-20", "2022-07-21"]')
                   + '\n[credits]\nstaff = [["剧本整理", "Aoi"]]\nend = "未完待续"\n', encoding='utf-8')
    proj = Project(proj.root)
    player.build(proj)
    d = player.data(proj)
    assert d['items'] == {} and not (out / 'img/items/tongyaoshi.webp').exists()
    assert d['kicker'] == 'TRPG REPLAY · 2022.07.20 — 2022.07.21'
    heads = [s['h'] for s in d['credits']['sections']]
    assert '剧本整理' in heads and heads[-1] == '原始记录' and d['credits']['end'] == '未完待续'


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
def test_player_js_syntax():
    for name in ('player/static/player.js', 'player/vclock.js'):
        path = os.path.join(os.path.dirname(player.__file__), '..', name)
        assert subprocess.run(['node', '--check', path]).returncode == 0


def test_player_route_and_cli(full_project, capsys):
    proj = full_project()
    assert main(['build', '-C', str(proj.root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['chapters'] == 1
    server = make_server(proj, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        r = urllib.request.urlopen(base + '/player')
        assert r.url.endswith('/files/build/player/index.html') and b'player.js' in r.read()
        assert urllib.request.urlopen(base + '/files/build/player/data.js').headers['Content-Type'].startswith('text/javascript')
    finally:
        server.shutdown()
