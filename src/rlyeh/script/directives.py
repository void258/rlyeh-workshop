"""舞台指令目录（规格见 docs/zh/script-format.md#舞台指令）。

每条指令有一个英文规范名和若干别名（中文名、英文名）。参数按位置写，取值是枚举的参数也有中英别名，
解析后统一换成英文规范值，播放器和工具只认规范值。
"""
from dataclasses import dataclass, field

# 枚举：规范值 → 别名
POSITIONS = {'left': ['左'], 'center': ['中'], 'right': ['右']}
STATES = {'hurt': ['受伤'], 'ghost': ['灵体']}
RESULTS = {'hit': ['命中'], 'miss': ['未中'], 'success': ['成功'], 'failure': ['失败'],
           'critical': ['大成功'], 'fumble': ['大失败']}
EFFECTS = {'shake': ['震屏'], 'flash': ['闪白'], 'dash': ['冲刺'], 'breath-fire': ['喷火'], 'flames': ['火焰'],
           'chill': ['寒气'], 'dawn-light': ['晨光'], 'door-break': ['破门']}
VARIANTS = {'dusk': ['黄昏'], 'night': ['夜'], 'warm': ['暖光'], 'dawn': ['黎明'], 'mist': ['晨雾'],
            'dormant': ['沉睡'], 'fog': ['雾'], 'shadows': ['窗外人影'], 'siege': ['围城']}

ENUMS = {'position': POSITIONS, 'state': STATES, 'result': RESULTS, 'fx': EFFECTS, 'variant': VARIANTS}
# 字段的中英名，用在校验信息里
FIELD_NAMES = {'position': ('位置', 'position'), 'state': ('状态', 'state'), 'result': ('结果', 'result'),
               'fx': ('特效', 'effect'), 'variant': ('背景变体', 'background variant'),
               'value': ('点数', 'value'), 'amount': ('数值', 'amount')}


def canonical(kind, value):
    """枚举取值 → 规范值；不认识返回 None。"""
    table = ENUMS[kind]
    v = value.strip()
    if v in table:
        return v
    for key, aliases in table.items():
        if v in aliases or v.lower() == key:
            return key
    return None


@dataclass(frozen=True)
class Param:
    name: str
    kind: str = 'text'          # text | char | number | position | state | result | fx | variant
    optional: bool = False
    rest: bool = False          # 吃掉剩下的所有参数（背景变体）


@dataclass(frozen=True)
class Spec:
    name: str
    aliases: tuple
    params: tuple = field(default_factory=tuple)

    @property
    def min_args(self):
        return sum(1 for p in self.params if not p.optional and not p.rest)

    @property
    def max_args(self):
        return None if any(p.rest for p in self.params) else len(self.params)


SPECS = [
    Spec('chapter', ('章节',), (Param('title', optional=True),)),
    Spec('chapter-end', ('章节结束',)),
    Spec('credits', ('片尾',)),
    Spec('bg', ('背景', 'background'), (Param('scene'), Param('variant', 'variant', rest=True))),
    Spec('cg', ('CG',), (Param('name'),)),
    Spec('cg-end', ('CG结束',)),
    Spec('enter', ('登场',), (Param('char', 'char'), Param('position', 'position', optional=True),
                              Param('state', 'state', optional=True))),
    Spec('exit', ('退场',), (Param('char', 'char'),)),
    Spec('fx', ('特效', 'effect'), (Param('fx', 'fx'),)),
    Spec('roll', ('骰子',), (Param('char', 'char'), Param('skill'), Param('value', 'number'), Param('result', 'result'))),
    Spec('damage', ('伤害',), (Param('target'), Param('amount', 'number'))),
    Spec('contest', ('对抗',), (Param('a'), Param('b'), Param('result', optional=True))),
    Spec('battle-start', ('战斗开始',)),
    Spec('round', ('回合',), (Param('name'),)),
    Spec('battle-end', ('战斗结束',)),
    Spec('item', ('道具',), (Param('name'),)),
    Spec('bgm', ('BGM', '音乐', 'music'), (Param('cue', optional=True),)),
    Spec('sfx', ('音效',), (Param('name'),)),
]
BY_NAME = {}
for _s in SPECS:
    BY_NAME[_s.name] = _s
    for _a in _s.aliases:
        BY_NAME[_a] = _s
        BY_NAME[_a.lower()] = _s


def lookup(name):
    return BY_NAME.get(name.strip()) or BY_NAME.get(name.strip().lower())
