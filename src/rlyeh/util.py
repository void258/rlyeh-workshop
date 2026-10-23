"""各流水线共用的小工具：读写 JSON、时间戳、ASCII 文件名。"""
import datetime
import json
import pathlib
import re

from pypinyin import lazy_pinyin


def read_json(path, default):
    path = pathlib.Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


STATUSES = ('pending', 'approved', 'redo', 'skip')


def save_marks(path, body):
    """审核页写回的标记 body: {键: {status, note}}，合并进 review/*.json。只接受 STATUSES 里的状态。"""
    marks = read_json(path, {})
    for k, v in body.items():
        status = v.get('status', 'redo')
        if status not in STATUSES:
            continue
        marks[str(k)] = dict(status=status, note=str(v.get('note', ''))[:500], by=str(v.get('by', '')), at=now())
    write_json(path, marks)
    return marks


def slug(text):
    """显示名 → 文件名用的 ASCII 写法：英文原样转小写，中文转拼音（平静 → pingjing，羊角旅馆 → yangjiaolvguan）。"""
    s = ''.join(lazy_pinyin(str(text))).lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-') or 'x'

