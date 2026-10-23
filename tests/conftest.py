import pytest

from rlyeh import i18n
from rlyeh.cli import main
from rlyeh.project import Project


@pytest.fixture
def make_project(tmp_path, capsys):
    """replay init 出一个项目，按 backends 改 [backends]，script 写进第一章。返回 Project。"""
    i18n.set_lang('zh-CN')

    def make(backends=None, script=None, extra=''):
        root = tmp_path / 'demo'
        main(['init', str(root), '--json'])
        capsys.readouterr()
        cfg = (root / 'replay.toml').read_text(encoding='utf-8')
        for kind, name in (backends or {}).items():
            lines = cfg.split('\n')
            for i, line in enumerate(lines):
                if line.startswith(f'{kind} = '):
                    lines[i] = f'{kind} = "{name}"'
                    break
            else:
                lines[lines.index('[backends]') + 1:lines.index('[backends]') + 1] = [f'{kind} = "{name}"']
            cfg = '\n'.join(lines)
        (root / 'replay.toml').write_text(cfg + '\n' + extra, encoding='utf-8')
        if script is not None:
            (root / 'script' / '01-chapter.md').write_text(script, encoding='utf-8')
        return Project(root)

    yield make
    i18n.set_lang(None)


DEMO_EXTRA = """
【伤害：阿洛｜3】
【BGM：战斗】
【战斗开始】
【回合：第二轮】
【战斗结束】
【CG：灯塔熄灭】
阿洛：〔惊呼〕灯灭了！
【CG结束】
【道具：铜钥匙】
【登场：阿洛｜左｜灵体】
【章节结束】
【片尾】
"""


@pytest.fixture
def full_project(make_project):
    """占位后端把美术、配音、音效、BGM 全做出来的示例项目（播放器、渲染测试用）。"""
    from rlyeh import art, music, sfx, voice

    def make(extra_script=''):
        proj = make_project({'image': 'placeholder', 'music': 'placeholder', 'tts': 'placeholder', 'asr': 'none'})
        path = proj.root / 'script' / '01-chapter.md'
        path.write_text(path.read_text(encoding='utf-8') + DEMO_EXTRA + extra_script, encoding='utf-8')
        proj = Project(proj.root)
        art.scaffold(proj)
        for f in (proj.root / art.PROMPTS).rglob('*.md'):
            f.write_text(f.read_text(encoding='utf-8').replace('<!-- TODO', '夜里起雾。<!-- 写好了'), encoding='utf-8')
        art.run(proj)
        sfx.build(proj)
        music.gen(proj)
        for cue in music.cues(proj):
            music.pick(proj, cue, 1)
        voice.build(proj)
        return proj

    return make
