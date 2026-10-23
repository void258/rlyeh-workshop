"""游戏系统的骰子/技能卡片解析。Foundry 各系统的卡片文字不同，按系统分别解析；认不出就当普通消息。

目前支持：demonlord（《魔王之影》系统，中文界面）。新增系统时在 PARSERS 里注册一个函数：正文 → dict 或 None。
"""
import re

DL_HEADS = ('攻击：', '检定投骰：', '法术：', '天赋：')


def _dl_roll_vs(L, start):
    """从 start 读：属性, 总值, 总值, 骰值与加值…, VS, 对抗属性, 数值"""
    vs = L.index('VS', start)
    return dict(attr=L[start], total=L[start + 1], terms=L[start + 3:vs],
                vs_attr=L[vs + 1], vs_val=L[vs + 2] if vs + 2 < len(L) else '', end=vs + 4)


def demonlord(body):
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    if lines and lines[0].startswith('选择进行一个'):          # 战斗轮开始时选快速/慢速回合，只有一行
        return dict(type='turn', speed='fast' if '快速' in lines[0] else 'slow')
    if len(lines) < 2:
        return None
    if lines[0] in DL_HEADS or lines[0].startswith('伤害骰:'):
        sub, L = None, lines
    else:
        sub, L = lines[0], lines[1:]
    if not L:
        return None
    head = L[0]
    try:
        if head == '攻击：':
            d = dict(type='attack', subtitle=sub, weapon=L[1])
            if L[2] == '目标：':
                d['target'], pos = L[3], 4
            else:
                d['target'], pos = None, 2
            d.update(_dl_roll_vs(L, pos))
            rest = L[d.pop('end'):]
            d['notes'] = [re.sub(r'\s*•\s*', ' ', x) for x in rest if '•' in x]
            d['damage'] = next((m.group(1) for x in rest for m in [re.search(r'伤害 \((.*)\)$', x)] if m), None)
            return d
        if head == '检定投骰：':
            d = dict(type='check', subtitle=sub, result=L[1])
            d.update(_dl_roll_vs(L, 3))
            d.pop('end')
            return d
        if head.startswith('伤害骰:'):
            stop = next(i for i, x in enumerate(L) if x.startswith('对目标应用'))
            return dict(type='damage', subtitle=sub, total=head.split(':', 1)[1].strip(), terms=L[1:stop])
        if head == '法术：':
            d = dict(type='spell', subtitle=sub, name=L[1], target=None, attack=None, description='', extras=[])
            if '目标：' in L:
                d['target'] = L[L.index('目标：') + 1]
            ui = next(i for i, x in enumerate(L) if x.startswith('次数'))
            d['uses'] = L[ui].replace('次数:', '').replace(' ', '')
            if 'VS' in L:
                d['attack'] = _dl_roll_vs(L, ui + 1)
                d['attack'].pop('end')
            if '描述' in L:
                for x in L[L.index('描述') + 1:]:
                    if re.match(r'^(伤害|额外伤害|检定投骰)', x):
                        d['extras'].append(x)
                    else:
                        d['description'] += x
            return d
        if head == '天赋：':
            desc = '\n'.join(L[L.index('描述') + 1:]) if '描述' in L else ''
            return dict(type='talent', subtitle=sub, name=L[1], description=desc)
    except (ValueError, IndexError, StopIteration):
        return None
    return None


PARSERS = {'demonlord': demonlord}


def parse(body, system=None):
    if '\n' not in body.strip() and not body.strip().startswith('选择进行一个'):
        return None
    if system:
        fn = PARSERS.get(system)
        return fn(body) if fn else None
    for fn in PARSERS.values():           # 没指定系统时挨个试
        d = fn(body)
        if d:
            return d
    return None
