"""剧本解析：中文写法（全角符号）和英文写法（ASCII 符号）都认，可以混用。规格见 docs/zh/script-format.md。"""
import pathlib
import re

import yaml

from ..i18n import t
from . import directives as dirs
from .model import Chapter, Directive, Issue, Scene, Spoken

DIRECTIVE_ZH = re.compile(r'^【(?P<name>[^：】]+?)(?:：(?P<args>[^】]*))?】$')
DIRECTIVE_EN = re.compile(r'^\[\[(?P<name>[^:\]]+?)(?::\s*(?P<args>.*?))?\]\]$')
# 说话人：中文冒号，或者后面跟空白的英文冒号（所以 GM:void 这种名字里的冒号不算分隔）
SPEAKER = re.compile(r'^(?P<who>[^：［\[〔<>\s][^：［\[]{0,31}?)(?:[［\[](?P<face>[^］\]]+)[］\]])?(?:：|:(?=\s|$))\s*(?P<text>.*)$')
ANCHOR = re.compile(r'\s\^(?P<id>[A-Za-z0-9][A-Za-z0-9_-]*)\s*$')
TONE = re.compile(r'^(?:〔(?P<zh>[^〕]+)〕|<(?P<en>[^>]+)>)\s*')
TOKEN = re.compile(r'\{(?P<b>[^}]+)\}|(?P<az>（[^）]*）)|\*(?P<ae>[^*]+)\*')
COMMENT = re.compile(r'<!--.*?-->', re.S)
ARG_SPLIT = re.compile(r'\s*[｜|]\s*')

NARRATOR_NAMES = {'旁白', 'Narrator', 'narrator'}


def _blank_comments(text):
    """去掉 HTML 注释，但保留换行，行号不变。"""
    return COMMENT.sub(lambda m: '\n' * m.group(0).count('\n'), text)


def split_front_matter(text, path, issues):
    if not text.startswith('---\n'):
        return {}, text, 0
    end = text.find('\n---', 4)
    if end < 0:
        issues.append(Issue('error', 'parse.unclosed_front_matter', path, 1, t('parse.unclosed_front_matter')))
        return {}, text, 0
    head = text[4:end]
    rest_start = text.find('\n', end + 1)
    rest = text[rest_start + 1:] if rest_start >= 0 else ''
    offset = text[:rest_start + 1].count('\n') if rest_start >= 0 else text.count('\n')
    try:
        meta = yaml.safe_load(head) or {}
    except yaml.YAMLError as e:
        issues.append(Issue('error', 'parse.bad_front_matter', path, 1, t('parse.bad_front_matter', err=e)))
        meta = {}
    return meta if isinstance(meta, dict) else {}, rest, offset


def parse_text_body(body):
    """台词正文 → (语气, 分段, 行尾 ID)。"""
    anchor = None
    m = ANCHOR.search(body)
    if m:
        anchor = m.group('id')
        body = body[:m.start()]
    tone = None
    m = TONE.match(body)
    if m:
        tone = (m.group('zh') or m.group('en')).strip()
        body = body[m.end():]
    segments, pos = [], 0
    for m in TOKEN.finditer(body):
        if m.start() > pos:
            segments.append(['t', body[pos:m.start()]])
        if m.group('b') is not None:
            segments.append(['b', m.group('b')])
        elif m.group('az') is not None:
            segments.append(['a', m.group('az')])
        else:
            segments.append(['a', m.group('ae')])
        pos = m.end()
    if pos < len(body):
        segments.append(['t', body[pos:]])
    # 首尾空白不算台词
    if segments and segments[0][0] == 't':
        segments[0][1] = segments[0][1].lstrip()
    if segments and segments[-1][0] == 't':
        segments[-1][1] = segments[-1][1].rstrip()
    return tone, [s for s in segments if s[1]], anchor


def parse_directive(line):
    m = DIRECTIVE_ZH.match(line) or DIRECTIVE_EN.match(line)
    if not m:
        return None
    written = m.group('name').strip()
    args_text = m.group('args')
    args = ARG_SPLIT.split(args_text.strip()) if args_text and args_text.strip() else []
    spec = dirs.lookup(written)
    return written, (spec.name if spec else written), args, spec is not None


def chapter_number(meta, path, index):
    if isinstance(meta.get('chapter'), int):
        return meta['chapter']
    m = re.match(r'^(\d+)', pathlib.Path(path).name)
    return int(m.group(1)) if m else index


def parse(text, path='<memory>', index=1, narrator_names=NARRATOR_NAMES):
    """解析一章剧本。返回 Chapter；问题记在 chapter.issues（解析层面的错误，语义检查在 lint）。"""
    text = text.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')
    issues = []
    meta, body, offset = split_front_matter(text, path, issues)
    body = _blank_comments(body)
    ch = Chapter(path=str(path), number=chapter_number(meta, path, index), title=str(meta.get('title', '') or ''),
                 lang=meta.get('lang'), meta=meta, issues=issues)
    for i, raw in enumerate(body.split('\n')):
        no = i + 1 + offset
        s = raw.strip()
        if not s:
            continue
        if s.startswith('#'):
            level = len(s) - len(s.lstrip('#'))
            title = s[level:].strip()
            if level == 1:
                ch.title = ch.title or title
            elif level == 2:
                ch.items.append(Scene('scene', no, raw, title=title))
            else:
                issues.append(Issue('warning', 'parse.deep_heading', ch.path, no, t('parse.deep_heading')))
            continue
        d = parse_directive(s)
        if d:
            written, name, args, known = d
            ch.items.append(Directive('directive', no, raw, name=name, written=written, args=args, known=known))
            continue
        ooc = s.startswith('>')
        if ooc:
            s = s.lstrip('>').strip()
            if not s:
                continue
        m = SPEAKER.match(s)
        if not m:
            issues.append(Issue('error', 'parse.unknown_line', ch.path, no, t('parse.unknown_line')))
            continue
        who = m.group('who').strip()
        tone, segments, anchor = parse_text_body(m.group('text'))
        kind = 'ooc' if ooc else ('narration' if who in narrator_names else 'line')
        face = m.group('face').strip() if m.group('face') else None
        ch.items.append(Spoken(kind, no, raw, speaker=who, face=face, tone=tone, segments=segments, anchor=anchor))
    return ch


def parse_file(path, index=1, narrator_names=NARRATOR_NAMES):
    path = pathlib.Path(path)
    return parse(path.read_text(encoding='utf-8'), str(path), index, narrator_names)
