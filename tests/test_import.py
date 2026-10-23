import json

from rlyeh import importers, i18n
from rlyeh.cli import main
from rlyeh.importers import cards, fvtt, text

SEP = '-' * 27


def fv(*msgs):
    """[(时间, 发言人, 正文)] → FVTT 导出文本。"""
    return '\n'.join(f'[{ts}] {who}\n{body}\n{SEP}' for ts, who, body in msgs) + '\n'


M1 = ('7/20/2022, 8:00:00 PM', 'void', '欢迎来到雾港。')
M2 = ('7/20/2022, 8:00:05 PM', '小林', '手机打字好痛苦。')
M3 = ('7/20/2022, 8:00:09 PM', '阿洛', '门是从里面锁上的。')
M4 = ('7/20/2022, 8:00:20 PM', '阿洛', '14\n1d20 + 2 = 12 + 2 = 14')
M5 = ('7/20/2022, 8:01:00 PM', 'Mia', '（我刚刚是不是投错了）')


def test_fvtt_merge_keeps_repeated_sends_once():
    a = fvtt.parse(fv(M1, M2, M2, M2, M3))            # 第一份：小林同一秒连发了三遍
    b = fvtt.parse(fv(M2, M2, M2, M3, M4, M5))        # 第二份：时间和第一份重叠
    rows = fvtt.merge([('a.txt', a), ('b.txt', b)])
    assert [r[1] for r in rows] == ['void', '小林', '小林', '小林', '阿洛', '阿洛', 'Mia']


def test_fvtt_events_kinds():
    evs = fvtt.to_events(fvtt.merge([('a.txt', fvtt.parse(fv(M1, M4, M5)))]))
    assert [e.kind for e in evs] == ['message', 'roll', 'ooc']
    assert evs[1].data == dict(formula='1d20 + 2', total='14', detail='12 + 2')


def test_demonlord_check_card():
    body = '检定投骰：\n成功\n成功\n力量\n14\n14\n12\n+\n2\nVS\n难度\n10'
    d = cards.parse(body, 'demonlord')
    assert d['type'] == 'check' and d['result'] == '成功' and d['attr'] == '力量' and d['total'] == '14'
    assert cards.parse('选择进行一个慢速回合', 'demonlord') == dict(type='turn', speed='slow')


def make_raw(tmp_path, *files):
    raw = tmp_path / 'logs' / 'raw'
    raw.mkdir(parents=True)
    for name, body in files:
        (raw / name).write_text(body, encoding='utf-8')
    return raw


def test_build_sessions_roles_aliases(tmp_path):
    late = ('7/21/2022, 8:00:00 PM', '张三', '第二天了，我tm来辣！')
    raw = make_raw(tmp_path, ('a.txt', fv(M1, M2, M3, M4, M5, late)))
    config = {'players': {'小林': 'arlo', 'Mia': 'mira', '张三': 'nok'},
              'import': {'gm': ['void'], 'min_session_messages': 1},
              'aliases': {'张三': '阿杰'}}
    events, rep = importers.build(config, raw)
    assert [e.session for e in events] == [1, 1, 1, 1, 1, 2]
    assert events[0].role == 'gm' and events[1].role == 'player' and events[2].role == 'character'
    assert events[-1].speaker == '阿杰' and events[-1].role == 'character'   # 化名不在 [players]，按角色处理
    assert [e.id for e in events][:2] == ['e000001', 'e000002']
    assert rep['raw_messages'] == 6 and len(rep['sessions']) == 2


def test_short_session_dropped(tmp_path):
    early = ('7/19/2022, 1:00:00 PM', 'void', '测试一下')
    raw = make_raw(tmp_path, ('a.txt', fv(early, M1, M2, M3, M4, M5)))
    events, rep = importers.build({'import': {'min_session_messages': 3}}, raw)
    assert len(events) == 5 and len(rep['dropped']) == 1 and rep['dropped'][0]['events'] == 1


def test_text_inline_and_block():
    inline = '[2022-07-20 20:00:05] 小林：手机打字好痛苦\n接着上一句\n[20:00:09] 阿洛: 门锁着\n'
    evs = text.parse(inline, 'x.txt')
    assert [(e.speaker, e.text) for e in evs] == [('小林', '手机打字好痛苦\n接着上一句'), ('阿洛', '门锁着')]
    assert evs[1].ts.isoformat() == '2022-07-20T20:00:09'
    block = '2022-07-20 20:00:05 小林(123456789)\n他说：走吧\n\n2022-07-20 20:00:09 阿洛<a@b.c>\n好\n'
    evs = text.parse(block, 'qq.txt')
    assert [(e.speaker, e.text) for e in evs] == [('小林', '他说：走吧'), ('阿洛', '好')]


def test_private_scan(tmp_path):
    raw = make_raw(tmp_path, ('a.txt', '小林：加我 qq 123456，或者打 13800138000\n'))
    _, rep = importers.build({}, raw)
    assert {p['kind'] for p in rep['private']} == {'qq', 'phone'}


def test_cli_import(tmp_path, capsys):
    i18n.set_lang('zh-CN')
    proj = tmp_path / 'demo'
    main(['init', str(proj), '--json'])
    capsys.readouterr()
    src = tmp_path / 'export.txt'
    src.write_text(fv(M1, M2, M3, M4, M5), encoding='utf-8')
    code = main(['import', str(src), '-C', str(proj), '--json'])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out['copied'] == ['export.txt'] and out['events'] == 5
    lines = (proj / 'logs' / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    assert json.loads(lines[3])['kind'] == 'roll'
    main(['import', str(src), '-C', str(proj), '--json'])             # 重复导入同一份：不重复复制、结果不变
    out = json.loads(capsys.readouterr().out)
    assert out['copied'] == [] and out['events'] == 5
    i18n.set_lang(None)
