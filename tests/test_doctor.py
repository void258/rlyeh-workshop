import json

import numpy as np
import soundfile as sf

from rlyeh import doctor, voice
from rlyeh.backends.estimate import EstimateAlign
from rlyeh.cli import main
from rlyeh.project import Project


def rows_by(rows, group):
    return {r['name']: r for r in rows if r['group'] == group}


def test_doctor_project(make_project):
    proj = make_project({'image': 'placeholder', 'music': 'placeholder', 'asr': 'none', 'align': 'estimate'})
    rows = doctor.project_backends(proj)
    b = rows_by(rows, 'backends')
    assert b['tts: drama3']['status'] == 'fail' and 'cli is not set' in b['tts: drama3']['detail']
    assert b['image: placeholder']['status'] == 'warn' and '占位后端' in b['image: placeholder']['hint']
    assert b['align: estimate']['status'] == 'ok'
    p = rows_by(doctor.project_checks(proj), 'project')
    assert p['script']['status'] == 'ok'


def test_doctor_noncommercial_and_paths(make_project, tmp_path):
    cli = tmp_path / 'audiocpp_cli.exe'
    cli.write_bytes(b'')
    extra = (f'[backends.drama3]\ncli = "{cli.as_posix()}"\nmodel = "{(tmp_path / "missing.gguf").as_posix()}"\n'
             '[backends.yue2-comfyui]\nurl = "http://127.0.0.1:9"\n')
    proj = make_project({'music': 'yue2-comfyui', 'asr': 'none', 'align': 'estimate'}, extra=extra)
    rows = [r for r in doctor.project_backends(proj)]
    drama = [r for r in rows if r['name'] == 'tts: drama3']
    assert [r['status'] for r in drama] == ['ok', 'fail'] and 'missing.gguf' in drama[1]['detail']
    comfy = next(r for r in rows if r['name'] == 'music: yue2-comfyui')
    assert comfy['status'] == 'warn' and 'ComfyUI' in comfy['hint']
    lic = next(r for r in rows if r['name'] == 'license')
    assert 'CC BY-NC 4.0' in lic['detail']


def test_cli_doctor(make_project, capsys):
    proj = make_project({'tts': 'placeholder', 'asr': 'none', 'align': 'estimate'})
    code = main(['doctor', '-C', str(proj.root), '--json'])
    out = json.loads(capsys.readouterr().out)
    fails = [r for r in out['checks'] if r['status'] == 'fail']
    assert code == (1 if fails else 0) and {r['group'] for r in out['checks']} >= {'env', 'backends', 'project'}


def test_estimate_align(tmp_path):
    sr = 24000
    y = np.zeros(sr * 2, np.float32)
    y[int(.5 * sr):int(1.5 * sr)] = .3                               # 有声段在 0.5–1.5 秒
    sf.write(tmp_path / 'a.wav', y, sr)
    stamps = EstimateAlign({'margin': 0}, None).align([dict(audio=tmp_path / 'a.wav', chars=['ab', 'c', 'c'])])[0]
    assert abs(stamps[0][0] - 500) <= 20 and abs(stamps[0][1] - 1000) <= 20 and abs(stamps[-1][1] - 1500) <= 20


EN_SCRIPT = """---
chapter: 1
title: Fog
lang: en
---

Arlo: <grumbling> What a {damn} door. ^c1-0001
"""


def test_english_bleep(tmp_path, capsys):
    root = tmp_path / 'en'
    main(['init', str(root), '--lang', 'en', '--json'])
    capsys.readouterr()
    cfg = (root / 'replay.toml').read_text(encoding='utf-8').replace('tts = "drama3"', 'tts = "placeholder"')
    (root / 'replay.toml').write_text(cfg.replace('asr = "sensevoice"', 'asr = "none"'), encoding='utf-8')
    (root / 'script' / '01-chapter.md').write_text(EN_SCRIPT, encoding='utf-8')
    proj = Project(root)
    assert proj.config['backends']['align'] == 'estimate'
    chars, spans = voice.bleep_spans(proj, proj.chapters()[0].spoken[0], 'en')
    assert chars == ['what', 'a', 'damn', 'door'] and spans == [(2, 3)]
    voice.build(proj)
    done, problems = voice.bleep(proj)
    assert list(done) == ['c1-0001'] and not problems
    cfg = (root / 'replay.toml').read_text(encoding='utf-8').replace('align = "estimate"', 'align = "funasr-fa"')
    (root / 'replay.toml').write_text(cfg, encoding='utf-8')
    (root / '.rlyeh' / 'state.json').unlink()
    done, problems = voice.bleep(Project(root))
    assert not done and 'does not support en' in problems[0]['reason']
