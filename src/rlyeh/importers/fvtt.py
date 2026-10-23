"""Foundry VTT 聊天记录导出（Export Chat Log 得到的 fvtt-log-*.txt）。

格式：每条消息是「[M/D/YYYY, h:mm:ss AM] 发言人」一行 + 正文若干行，消息之间用一行 27 个横线分隔。
同一场团常常导出好几份、时间互相重叠，合并时同一秒同内容的消息只留一份。
"""
import collections
import datetime
import re

from . import cards
from .base import Event, classify, parse_roll

SEP = '-' * 27
HEADER = re.compile(r'^\[(\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} [AP]M)\] (.*)$')


def sniff(text):
    lines = text.lstrip('﻿').splitlines()[:5]
    return any(HEADER.match(l) for l in lines)


def parse(text):
    """一份导出 → [(时间, 发言人, 正文)]。"""
    out, cur = [], None
    for line in text.lstrip('﻿').replace('\r\n', '\n').split('\n'):
        if line == SEP:
            if cur:
                out.append(cur)
            cur = None
            continue
        if cur is None:
            m = HEADER.match(line)
            if m:
                cur = [datetime.datetime.strptime(m.group(1), '%m/%d/%Y, %I:%M:%S %p'), m.group(2).strip(), []]
        else:
            cur[2].append(line)
    if cur:
        out.append(cur)
    return [(ts, spk, '\n'.join(body).strip('\n')) for ts, spk, body in out]


def merge(sources):
    """sources: [(文件名, [(时间, 发言人, 正文)])]。

    同一秒、同一正文的消息算同一条；一份导出里本来就连发了几次的（比如玩家狂点发送），
    以出现次数最多、导出时间最晚的那份为准，所以连发的次数不会丢也不会翻倍。
    """
    ranked = sorted(sources, key=lambda s: s[1][-1][0] if s[1] else datetime.datetime.min)
    best = {}
    for rank, (name, msgs) in enumerate(ranked):
        groups = collections.defaultdict(list)
        for i, (ts, spk, body) in enumerate(msgs):
            groups[(ts, body)].append((i, spk))
        for key, items in groups.items():
            if key not in best or len(items) >= len(best[key][2]):
                best[key] = (rank, name, items)
    rows = [(ts, rank, i, spk, body, name) for (ts, body), (rank, name, items) in best.items() for i, spk in items]
    rows.sort(key=lambda r: r[:3])
    return [(ts, spk, body, name) for ts, _, _, spk, body, name in rows]


def to_events(rows, system=None):
    events = []
    for ts, spk, body, name in rows:
        roll = parse_roll(body)
        card = None if roll else cards.parse(body, system)
        if roll:
            e = Event(ts, spk, body, 'roll', data=roll, source=name)
        elif card:
            e = Event(ts, spk, body, 'card', data=card, source=name)
        else:
            e = Event(ts, spk, body, classify(body), source=name)
        events.append(e)
    return events
