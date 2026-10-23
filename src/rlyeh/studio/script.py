"""Studio 的剧本编辑器：读写 script/*.md、校验还没保存的内容、补台词 ID、给自动补全用的名字表。

保存时带上打开时的版本号：文件在外面被改过（AI 或别的编辑器）就不覆盖，返回冲突让用户选。
"""
import hashlib
import pathlib

from .. import music, sfx
from ..i18n import t
from ..script import directives as dirs
from ..script import ids as script_ids
from ..script import parser
from ..script.ids import assign
from ..script.lint import lint
from ..util import slug


class ScriptError(Exception):
    pass


class Conflict(ScriptError):
    def __init__(self, message, current):
        super().__init__(message)
        self.current = current


def version(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _rel(project, path):
    return path.resolve().relative_to(project.root.resolve()).as_posix()


def _path(project, rel):
    """只认 script/ 下面的 .md 文件。"""
    rel = (rel or '').replace('\\', '/')
    path = (project.root / rel).resolve()
    if path.parent != (project.root / 'script').resolve() or path.suffix != '.md':
        raise ScriptError(f'not a script file: {rel}')
    return path


def _read(path):
    return path.read_text(encoding='utf-8').lstrip('﻿').replace('\r\n', '\n')


def _chapters(project, rel=None, text=None):
    """按 project.chapters() 的方式解析全部章节；rel 这一章用还没保存的 text。"""
    out = []
    for i, path in enumerate(project.script_files(), 1):
        if rel is not None and _rel(project, path) == rel and text is not None:
            ch = parser.parse(text, str(path), i, project.narrator_names)
        else:
            ch = parser.parse_file(path, i, project.narrator_names)
        assign(ch)
        out.append(ch)
    return out


def files(project):
    chapters = _chapters(project)
    issues = lint(chapters, project)
    out = []
    for ch in chapters:
        mine = [i for i in issues if i.file == ch.path]
        out.append(dict(path=_rel(project, pathlib.Path(ch.path)), number=ch.number, title=ch.title,
                        lines=len(ch.spoken), errors=sum(1 for i in mine if i.level == 'error'),
                        warnings=sum(1 for i in mine if i.level == 'warning')))
    return out


def read(project, rel):
    path = _path(project, rel)
    if not path.is_file():
        raise ScriptError(f'no such file: {rel}')
    text = _read(path)
    return dict(path=_rel(project, path), text=text, version=version(text))


def check(project, rel, text):
    """校验一章（用编辑器里还没保存的内容），ID 重复之类跨章的问题也算上。"""
    path = _path(project, rel)
    chapters = _chapters(project, _rel(project, path), text.replace('\r\n', '\n'))
    return [i.as_dict() for i in lint(chapters, project) if i.file == str(path)]


def _anchors(text):
    return [m.group('id') for line in text.split('\n') if (m := parser.ANCHOR.search(line))]


def save(project, rel, text, base, force=False):
    path = _path(project, rel)
    text = text.replace('\r\n', '\n')
    current = _read(path) if path.is_file() else ''
    if not force and path.is_file() and version(current) != base:
        raise Conflict('the file was changed outside the editor', dict(text=current, version=version(current)))
    path.write_bytes(text.encode('utf-8'))
    removed = [a for a in _anchors(current) if a not in set(_anchors(text))]
    return dict(path=_rel(project, path), version=version(text), removed=removed)


def new_chapter(project, title):
    title = (title or '').strip()
    if not title:
        raise ScriptError('the chapter needs a title')
    numbers = [ch.number for ch in _chapters(project)]
    n = max(numbers, default=0) + 1
    name = f'{n:02d}-{slug(title)[:40].strip("-") or "chapter"}.md'
    path = project.root / 'script' / name
    if path.exists():
        raise ScriptError(f'{name} already exists')
    en = project.lang.lower().startswith('en')
    head = f'---\nchapter: {n}\ntitle: {title}\nlang: {"en" if en else "zh-CN"}\n---\n\n'
    body = f'[[chapter: {title}]]\n\n' if en else f'【章节：{title}】\n\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((head + body).encode('utf-8'))
    return dict(path=_rel(project, path))


def assign_ids(project):
    """同 replay ids：给还没有 ID 的台词补上，已有的不动。"""
    total = 0
    for ch in project.chapters():
        anchored = sum(1 for it in ch.spoken if it.anchor)
        fresh = [it for it in ch.spoken if not it.anchor]
        if anchored == 0:
            fresh = ch.spoken
        total += script_ids.write_anchors(ch.path, fresh)
    return dict(assigned=total, message=t('cli.ids_done', n=total) if total else t('cli.ids_none'))


def meta(project):
    """自动补全用：说话人和表情、场外玩家、指令和参数、枚举值、曲目、音效。"""
    speakers = []
    for ch in project.characters.values():
        speakers.append(dict(id=ch.id, names=sorted(set(ch.names.values())), kind=ch.kind,
                             expressions=list(ch.expressions)))
    directives = [dict(name=s.name, aliases=list(s.aliases),
                       params=[dict(name=p.name, kind=p.kind, optional=p.optional, rest=p.rest) for p in s.params])
                  for s in dirs.SPECS]
    try:
        cues = [dict(id=cid, names=sorted(set(c['names'].values()) | {cid})) for cid, c in music.cues(project).items()]
    except Exception:                                   # 曲目表写坏了也不影响编辑
        cues = []
    try:
        sounds = [dict(id=k, aliases=v['aliases']) for k, v in sfx.catalog(project).items()]
    except Exception:
        sounds = []
    return dict(speakers=speakers, narrators=sorted(project.narrator_names), players=sorted(project.players),
                directives=directives, enums={k: v for k, v in dirs.ENUMS.items()}, cues=cues, sounds=sounds,
                lang=project.lang)

