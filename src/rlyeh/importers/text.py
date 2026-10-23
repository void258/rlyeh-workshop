"""纯文本聊天记录。两种写法，按文件自动判断：

块状（QQ 等聊天软件导出）：头一行「日期 时间 名字(号码)」，下面若干行是内容。
    2022-07-20 20:31:05 小林(123456789)
    我tm来辣！
逐行：每行一条，可以带时间。
    [2022-07-20 20:31:05] 小林：内容      [20:31] 小林: 内容      小林：内容
逐行写法里认不出的行接在上一条后面；块状写法里只有头一行算新消息，内容里有冒号也不会被拆开。
"""
import datetime
import re

from .base import Event, classify, parse_roll

DATE_TIME = r'\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?'
TIME = r'\d{1,2}:\d{2}(?::\d{2})?'
BLOCK = re.compile(r'^(?P<ts>' + DATE_TIME + r')\s+(?P<who>.+?)(?:\s*[(<（][^)>）]*[)>）])?\s*$')
INLINE = re.compile(r'^(?:\[(?P<ts>' + DATE_TIME + '|' + TIME + r')\]\s*)?'
                    r'(?P<who>[^\s：:\[][^：:]{0,31}?)(?:：|:\s)\s*(?P<text>.*)$')


def _parse_ts(s, last_date):
    if not s:
        return None
    s = s.replace('/', '-').replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            pass
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            t = datetime.datetime.strptime(s, fmt).time()
            return datetime.datetime.combine(last_date or datetime.date(1970, 1, 1), t)
        except ValueError:
            pass
    return None


def _rows_block(lines):
    rows, cur = [], None
    for line in lines:
        m = BLOCK.match(line)
        if m:
            cur = [_parse_ts(m.group('ts'), None), m.group('who').strip(), []]
            rows.append(cur)
        elif cur is not None and line.strip():
            cur[2].append(line.strip())
    return rows


def _rows_inline(lines):
    rows, cur, last_date = [], None, None
    for line in lines:
        m = INLINE.match(line)
        if m and not line.startswith((' ', '\t')):
            ts = _parse_ts(m.group('ts'), last_date)
            if ts:
                last_date = ts.date()
            cur = [ts, m.group('who').strip(), [m.group('text')]]
            rows.append(cur)
        elif cur is not None and line.strip():
            cur[2].append(line.strip())
    return rows


def parse(text, name=''):
    lines = [l.rstrip() for l in text.lstrip('﻿').replace('\r\n', '\n').split('\n')]
    block = sum(1 for l in lines if BLOCK.match(l))
    rows = _rows_block(lines) if block >= 2 else _rows_inline(lines)
    events = []
    for ts, who, body in rows:
        body_text = '\n'.join(body).strip()
        if not body_text:
            continue
        roll = parse_roll(body_text)
        events.append(Event(ts, who, body_text, 'roll' if roll else classify(body_text), data=roll or {}, source=name))
    return events
