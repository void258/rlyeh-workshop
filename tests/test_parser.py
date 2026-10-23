from rlyeh.script import parse
from rlyeh.script.directives import canonical
from rlyeh.script.model import Directive, Scene, Spoken

ZH = """---
chapter: 3
title: 雾港灯塔
lang: zh-CN
---

<!-- 注释
跨两行 -->
【章节：第三章　雾港灯塔】

## 第一幕　无人的灯塔

【背景：灯塔底层｜夜｜雾】
旁白：〔带着悬念地讲述〕灯塔已经三天没有亮过了。 ^c3-0001
阿洛［警惕］：〔压低声音〕门是从里面锁上的。（举起提灯）
> GM:void：〔笑着〕过个力量检定吧。
【骰子：米拉｜力量检定｜20｜大成功】
米拉［得意］：〔得意大笑〕{tm}的，一脚就开了！
德克：……
"""

EN = """# Chapter 1: The Lighthouse

## Act 1: The Empty Lighthouse

[[bg: lighthouse-ground | night | fog]]
Narrator: <suspenseful> The lighthouse had been dark for three days. ^c1-0001
Arlo[wary]: <whispering> It's locked from the inside. *raises the lantern*
> GM:void: <laughing> Roll a Strength check.
[[roll: mira | strength | 20 | critical]]
Old Nok: <booming> Who dares?
[[cg-end]]
"""


def test_zh_front_matter_and_line_numbers():
    ch = parse(ZH, 'x.md')
    assert ch.number == 3 and ch.title == '雾港灯塔' and ch.lang == 'zh-CN'
    assert not ch.issues
    nar = next(it for it in ch.items if isinstance(it, Spoken) and it.kind == 'narration')
    assert nar.line_no == 14 and nar.anchor == 'c3-0001' and nar.tone == '带着悬念地讲述'
    assert nar.say == '灯塔已经三天没有亮过了。'


def test_zh_line_face_tone_action_bleep():
    ch = parse(ZH)
    arlo = next(it for it in ch.spoken if it.speaker == '阿洛')
    assert arlo.face == '警惕' and arlo.tone == '压低声音'
    assert arlo.segments == [['t', '门是从里面锁上的。'], ['a', '（举起提灯）']]
    assert arlo.say == '门是从里面锁上的。' and arlo.text.endswith('（举起提灯）')
    mira = next(it for it in ch.spoken if it.speaker == '米拉')
    assert mira.bleeps == ['tm'] and mira.say.startswith('tm的')


def test_gm_colon_name_and_ooc():
    for text in (ZH, EN):
        ooc = next(it for it in parse(text).spoken if it.kind == 'ooc')
        assert ooc.speaker == 'GM:void' and ooc.tone in ('笑着', 'laughing')


def test_directives_canonical_names_both_syntaxes():
    zh = [it for it in parse(ZH).items if isinstance(it, Directive)]
    en = [it for it in parse(EN).items if isinstance(it, Directive)]
    assert [d.name for d in zh] == ['chapter', 'bg', 'roll']
    assert [d.name for d in en] == ['bg', 'roll', 'cg-end']
    assert zh[1].args == ['灯塔底层', '夜', '雾'] and en[0].args == ['lighthouse-ground', 'night', 'fog']
    assert canonical('result', zh[2].args[3]) == canonical('result', en[1].args[3]) == 'critical'
    assert canonical('variant', '雾') == 'fog' and canonical('position', 'Left') == 'left'


def test_en_speaker_with_space_and_scene():
    ch = parse(EN)
    assert ch.title == 'Chapter 1: The Lighthouse'
    assert isinstance(ch.items[0], Scene) and ch.items[0].title == 'Act 1: The Empty Lighthouse'
    nok = next(it for it in ch.spoken if it.speaker == 'Old Nok')
    assert nok.tone == 'booming' and nok.say == 'Who dares?'
    arlo = next(it for it in ch.spoken if it.speaker == 'Arlo')
    assert arlo.segments[-1] == ['a', 'raises the lantern'] and arlo.say == "It's locked from the inside."


def test_silent_line_is_not_voiced():
    dirk = next(it for it in parse(ZH).spoken if it.speaker == '德克')
    assert not dirk.voiced


def test_unparseable_line_reported():
    ch = parse('这一行没有冒号\n')
    assert [i.code for i in ch.issues] == ['parse.unknown_line'] and ch.issues[0].line == 1


def test_unknown_directive_kept():
    d = parse('【跳舞：浓痰】\n').items[0]
    assert isinstance(d, Directive) and not d.known and d.name == '跳舞'
