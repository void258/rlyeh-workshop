from rlyeh.script import parse
from rlyeh.script.ids import assign, write_anchors

NO_IDS = """旁白：〔讲述〕第一句。
阿洛：〔平静〕第二句。
> 小林：〔吐槽〕第三句。
"""

MIXED = """旁白：〔讲述〕第一句。 ^c2-0001
阿洛：〔平静〕新插进来的一句。
阿洛：〔平静〕原来的第二句。 ^c2-0002
"""


def test_sequential_when_no_anchors():
    ch = parse(NO_IDS, 'x.md', index=1)
    assign(ch)
    assert [it.id for it in ch.spoken] == ['c1-0001', 'c1-0002', 'c1-0003']


def test_existing_ids_never_change():
    ch = parse(MIXED, '02-x.md')
    fresh = assign(ch)
    assert [it.id for it in ch.spoken] == ['c2-0001', 'c2-0003', 'c2-0002']
    assert [it.id for it in fresh] == ['c2-0003']


def test_write_anchors_keeps_other_bytes(tmp_path):
    p = tmp_path / '01-x.md'
    p.write_bytes(NO_IDS.replace('\n', '\r\n').encode('utf-8'))
    ch = parse(p.read_text(encoding='utf-8'), str(p), 1)
    assign(ch)
    assert write_anchors(p, ch.spoken) == 3
    text = p.read_bytes().decode('utf-8')
    assert text.count('\r\n') == 3
    assert '第一句。 ^c1-0001\r\n' in text and '第三句。 ^c1-0003\r\n' in text
    again = parse(p.read_text(encoding='utf-8'), str(p), 1)
    assign(again)
    assert [it.anchor for it in again.spoken] == ['c1-0001', 'c1-0002', 'c1-0003']
