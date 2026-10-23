import json

import numpy as np
import pytest
import soundfile as sf

from rlyeh import sfx
from rlyeh.cli import main
from rlyeh.sfx import synth
from rlyeh.util import read_json

SFX_YAML = """
sounds:
  scream:
    name: { zh-CN: 尖叫, en: scream }
    voice: hero
    tone: 撕心裂肺的惨叫
    text: 啊啊啊啊啊——！！
    max_seconds: 2.5
    space: upstairs
  zombie:
    name: 僵尸
    min_gap: 40
    space: behind-door
    layers:
      - { voice: hero, tone: 含混地呻吟, text: 呃……啊……, pitch: -4 }
      - { voice: gm, tone: 低沉地嘶吼, text: 嗬……呃啊……, pitch: -3, at: 0.5, gain: 0.8, seeds: [7] }
  creak:
    name: 吱呀
    file: assets/creak.wav
"""


@pytest.fixture
def proj(make_project):
    return make_project({'tts': 'placeholder'})


def test_synth_is_deterministic():
    a = synth.render('dice_roll')
    synth.render('gong')
    assert np.array_equal(a, synth.render('dice_roll'))          # 和生成顺序无关
    assert a.shape[1] == 2 and abs(np.abs(a).max() - 10 ** (-1 / 20)) < 1e-6


def test_builtin_build_is_incremental(proj):
    res = sfx.build(proj)
    assert len(res['done']) == len(synth.SOUNDS) and not res['problems']
    info = sf.info(str(proj.root / 'audio/sfx/door_break.wav'))
    assert info.samplerate == 48000 and info.channels == 2
    assert sfx.build(proj)['done'] == []
    index = read_json(proj.root / sfx.INDEX, {})
    assert index['door_break']['aliases'] == ['破门'] and index['door_break']['seconds'] > 0.5


def test_project_sounds(proj):
    (proj.root / 'sfx.yaml').write_text(SFX_YAML, encoding='utf-8')
    res = sfx.build(proj)
    assert {'scream', 'zombie'} <= set(res['done'])
    assert res['problems'] == [{'id': 'creak', 'reason': 'file not found: assets/creak.wav'}]
    assert sorted(p.name for p in (proj.root / sfx.TAKES).glob('*.wav')) == [
        'scream_0_11.wav', 'scream_0_12.wav', 'zombie_0_11.wav', 'zombie_0_12.wav', 'zombie_1_7.wav']
    (proj.root / 'assets').mkdir()
    sf.write(proj.root / 'assets/creak.wav', np.zeros(4800, np.float32), 48000)
    res = sfx.build(proj)
    assert res == {'done': [], 'problems': []}
    index = read_json(proj.root / sfx.INDEX, {})
    assert index['zombie']['min_gap'] == 40 and index['creak']['file'] == 'assets/creak.wav'
    assert sfx.resolve(proj, '尖叫') == 'scream' and sfx.resolve(proj, 'Scream') == 'scream'
    assert sfx.resolve(proj, '破门') == 'door_break' and sfx.resolve(proj, '不存在') is None
    # 改了设置就重做这一个
    (proj.root / 'sfx.yaml').write_text(SFX_YAML.replace('space: upstairs', 'space: room'), encoding='utf-8')
    assert sfx.build(proj)['done'] == ['scream']
    assert sfx.summary(proj) == dict(total=len(synth.SOUNDS) + 3, custom=3, done=len(synth.SOUNDS) + 3)


def test_bad_space(proj):
    (proj.root / 'sfx.yaml').write_text(SFX_YAML.replace('space: upstairs', 'space: cave'), encoding='utf-8')
    res = sfx.build(proj, only={'scream'})
    assert len(res['problems']) == 1 and res['problems'][0]['id'] == 'scream' and 'cave' in res['problems'][0]['reason']


def test_cli_sfx(proj, capsys):
    assert main(['sfx', '--list', '-C', str(proj.root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['sounds']['gong']['aliases'] == ['锣']
    assert main(['sfx', 'gong', 'clash', '-C', str(proj.root), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['done'] == ['gong', 'clash']
