"""导入：把各平台导出的跑团记录统一成事件流 logs/events.jsonl。规格见 docs/zh/project-format.md#导入后的记录。"""
import datetime
import json
import re
from dataclasses import asdict, dataclass, field


@dataclass
class Event:
    ts: datetime.datetime | None
    speaker: str
    text: str
    kind: str = 'message'        # message | ooc | roll | card
    role: str = 'unknown'        # gm | player | character | observer | unknown
    data: dict = field(default_factory=dict)   # 骰子、系统卡片解析出的字段
    source: str = ''             # 来自哪个导出文件
    session: int = 0
    id: str = ''

    def as_json(self):
        d = asdict(self)
        d['ts'] = self.ts.isoformat() if self.ts else None
        return json.dumps({'id': d.pop('id'), **d}, ensure_ascii=False)


# 骰子结果：Foundry 核心掷骰的文本形如「19\n1d20 + 2 = 17 + 2 = 19」
ROLL = re.compile(r'^(-?\d+)\n(.+)$')


def parse_roll(text):
    m = ROLL.match(text.strip())
    if not m or ' = ' not in m.group(2) or not re.search(r'\d*d\d', m.group(2)):
        return None
    parts = m.group(2).split(' = ')
    total = parts[-1].strip()
    detail = parts[1].strip() if len(parts) >= 3 and parts[1] != total else ''
    return dict(formula=parts[0].strip(), total=total, detail=detail)


def classify(text):
    """消息类型：括号开头的是场外话（跑团常见写法）；能解析成骰子的是掷骰。"""
    b = text.strip()
    if parse_roll(b):
        return 'roll'
    if b[:1] in ('(', '（'):
        return 'ooc'
    return 'message'


# 隐私：导入时提醒检查，不自动改
PRIVATE = {
    'phone': re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'),
    'email': re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
    'qq': re.compile(r'(?i)(?:qq|扣扣)[:：\s号]*\d{5,11}'),
    'url': re.compile(r'https?://\S+'),
}


def scan_private(events):
    found = []
    for e in events:
        for kind, rx in PRIVATE.items():
            for m in rx.finditer(e.text):
                found.append(dict(id=e.id, kind=kind, text=m.group(0), speaker=e.speaker))
    return found
