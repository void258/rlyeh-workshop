"""示例团从导入一路跑到播放器（能渲染的机器上再渲染几秒）。"""
import pathlib
import shutil

import pytest

from rlyeh import art, i18n, importers, music, player, render, sfx, voice
from rlyeh.project import Project
from rlyeh.script.lint import lint

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / 'examples' / 'fog-harbor'
SOURCES = ['replay.toml', 'cast.yaml', 'music.yaml', 'sfx.yaml', 'logs/raw', 'script', 'art/prompts']


@pytest.fixture
def example(tmp_path):
    """只复制「原料」：示例团在仓库里跑过的话，生成的文件不带过来。"""
    i18n.set_lang('zh-CN')
    root = tmp_path / 'fog-harbor'
    for rel in SOURCES:
        src, dst = EXAMPLE / rel, root / rel
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    yield Project(root)
    i18n.set_lang(None)


def test_example_end_to_end(example):
    proj = example
    events, rep = importers.run(proj.root, proj.config)
    assert rep['events'] == 45 and len(rep['sessions']) == 1 and not rep['private']
    assert {e.role for e in events if e.speaker == 'GM'} == {'gm'} and {e.kind for e in events if e.speaker == '维拉'} >= {'roll'}
    assert lint(proj.chapters(), proj) == []                                  # 剧本没有错误也没有警告

    assert len(voice.build(proj)) == 24
    done, problems = voice.bleep(proj)
    assert list(done) == ['c1-0012'] and not problems                          # 「tmd」那句

    assert not [j.id for j in art.load_jobs(proj) if j.needs_prompt]             # 提示词都写好了
    res = art.run(proj)
    assert len(res['done']) == 20 and not res['blocked']
    report, _ = art.check(proj)
    assert all(v['status'] == 'ok' for v in report.values())

    res = sfx.build(proj)
    assert 'wail' in res['done'] and not res['problems']
    assert sfx.resolve(proj, '雾魇的哀嚎') == 'wail'
    assert len(music.gen(proj)['done']) == 5
    for cue in music.cues(proj):
        music.pick(proj, cue, 1)

    res = player.build(proj)
    assert not any(res['missing'].values()), res['missing']
    d = player.data(proj)
    heads = [s['h'] for s in d['credits']['sections']]
    assert heads[:4] == ['主持', '玩家', '登场人物', '剧本整理 · 演出'] and heads[-1] == '原始记录'
    assert d['credits']['sections'][-1]['items'] == [['聊天记录', '2024-05-18']]
    assert d['title_screen'] == {'bg': '雾港码头', 'variants': ['night', 'fog'], 'bgm': 'title'}
    bleeped = next(s for ch in d['chapters'] for s in ch['steps'] if s.get('id') == 'c1-0012')
    assert bleeped['voice'] == 'audio/voice-bleep/c1-0012.wav'


def _can_render():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return bool(shutil.which('ffmpeg'))
    except Exception:
        return False


@pytest.mark.skipif(not _can_render(), reason='needs playwright with chromium and ffmpeg')
def test_example_renders(example):
    proj = example
    voice.build(proj)
    art.run(proj)
    sfx.build(proj)
    music.gen(proj)
    for cue in music.cues(proj):
        music.pick(proj, cue, 1)
    res = render.render(proj, start='c1-0012', seconds=4)                      # 从砸门那句开始：对抗、破门、CG
    assert res['frames'] == 240 and (proj.root / res['video']).exists()
