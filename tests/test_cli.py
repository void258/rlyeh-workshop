import json

import pytest

from rlyeh import i18n
from rlyeh.cli import main


@pytest.fixture(autouse=True)
def zh():
    i18n.set_lang('zh-CN')
    yield
    i18n.set_lang(None)


def run(capsys, *argv):
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize('lang', ['zh-CN', 'en'])
def test_init_then_lint_is_clean_after_ids(tmp_path, capsys, lang):
    proj = tmp_path / 'demo'
    code, out = run(capsys, 'init', str(proj), '--lang', lang, '--json')
    assert code == 0 and out['lang'] == lang
    assert (proj / 'replay.toml').exists() and (proj / 'script' / '01-chapter.md').exists()
    code, out = run(capsys, 'lint', '-C', str(proj), '--json')
    assert code == 0 and out['errors'] == 0
    assert {i['code'] for i in out['issues']} == {'lint.no_id'}
    code, out = run(capsys, 'ids', '-C', str(proj), '--json')
    assert code == 0 and len(out['assigned']) == 3
    code, out = run(capsys, 'lint', '-C', str(proj), '--json')
    assert out['errors'] == 0 and out['warnings'] == 0


def test_lint_reports_semantic_errors(tmp_path, capsys):
    proj = tmp_path / 'demo'
    run(capsys, 'init', str(proj), '--lang', 'zh-CN', '--json')
    (proj / 'script' / '02-bad.md').write_text(
        '路人甲：〔喊〕谁在那里！ ^c2-0001\n'
        '> 路人乙：〔吐槽〕好吓人。 ^c2-0001\n'
        '【登场：阿洛｜上面】\n'
        '【骰子：阿洛｜力量｜很高｜成功】\n'
        '【特效：彩虹】\n'
        '阿洛［大笑］：哈哈 ^c2-0002\n'
        '阿洛：〔平静〕我有 116 块，还有 {sb}。 ^c2-0003\n', encoding='utf-8')
    code, out = run(capsys, 'lint', '-C', str(proj), '--json')
    codes = [(i['code'], i['line']) for i in out['issues'] if i['file'].endswith('02-bad.md')]
    assert code == 1
    for expected in [('lint.unknown_speaker', 1), ('lint.unknown_player', 2), ('lint.duplicate_id', 2),
                     ('lint.bad_enum', 3), ('lint.not_number', 4), ('lint.unknown_fx', 5),
                     ('lint.unknown_face', 6), ('lint.no_tone', 6), ('lint.no_reading', 7), ('lint.bleep_no_spoken', 7)]:
        assert expected in codes, expected


def test_status(tmp_path, capsys):
    proj = tmp_path / 'demo'
    run(capsys, 'init', str(proj), '--json')
    code, out = run(capsys, 'status', '-C', str(proj), '--json')
    ch = out['chapters'][0]
    assert code == 0 and (ch['lines'], ch['voiced'], ch['scenes'], ch['directives']) == (3, 3, 1, 4)


def test_no_project(tmp_path, capsys):
    code, out = run(capsys, 'lint', '-C', str(tmp_path), '--json')
    assert code == 2 and not out['ok']
