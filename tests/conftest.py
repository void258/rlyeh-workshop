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
