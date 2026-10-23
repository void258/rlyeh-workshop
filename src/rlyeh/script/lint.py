"""剧本校验（replay lint）。规格见 docs/zh/script-format.md#校验规则replay-lint。"""
import re

from ..i18n import lang, t
from . import directives as dirs
from .model import Directive, Issue, Spoken

ABBR = re.compile(r'^[A-Za-z]+$')
LATIN_DIGIT = re.compile(r'[A-Za-z0-9]+')


def _issue(level, code, item, path, **kw):
    return Issue(level, code, path, item.line_no if item else 0, t(code, **kw))


def _field(kind):
    zh, en = dirs.FIELD_NAMES.get(kind, (kind, kind))
    return en if lang().lower().startswith('en') else zh


def check_directive(d, path, out, project=None):
    if not d.known:
        out.append(_issue('error', 'lint.unknown_directive', d, path, name=d.written))
        return
    spec = dirs.lookup(d.name)
    n = len(d.args)
    if n < spec.min_args or (spec.max_args is not None and n > spec.max_args):
        expected = str(spec.min_args) if spec.max_args == spec.min_args else (
            f'{spec.min_args}–{spec.max_args}' if spec.max_args is not None else f'≥{spec.min_args}')
        out.append(_issue('error', 'lint.arg_count', d, path, name=d.written, expected=expected, got=n))
        return
    params = list(spec.params)
    for i, value in enumerate(d.args):
        p = params[min(i, len(params) - 1)]
        if p.kind == 'number':
            if not re.fullmatch(r'-?\d+', value.strip()):
                out.append(_issue('error', 'lint.not_number', d, path, name=d.written, field=_field(p.name), value=value))
        elif p.kind in ('position', 'state', 'result'):
            if dirs.canonical(p.kind, value) is None:
                choices = ' / '.join(f'{k}（{"、".join(v)}）' for k, v in dirs.ENUMS[p.kind].items())
                out.append(_issue('error', 'lint.bad_enum', d, path, name=d.written, field=_field(p.kind), value=value, choices=choices))
        elif p.kind == 'fx' and dirs.canonical('fx', value) is None:
            out.append(_issue('warning', 'lint.unknown_fx', d, path, value=value))
        elif p.kind == 'variant' and dirs.canonical('variant', value) is None:
            out.append(_issue('warning', 'lint.unknown_variant', d, path, value=value))


def check_spoken(it, path, out, project=None, script_lang='zh-CN'):
    if it.voiced and not it.tone:
        out.append(_issue('warning', 'lint.no_tone', it, path))
    if not it.anchor:
        out.append(_issue('warning', 'lint.no_id', it, path))
    if project is None:
        return
    if it.kind == 'ooc':
        if it.speaker not in project.players:
            out.append(_issue('error', 'lint.unknown_player', it, path, who=it.speaker))
    elif it.kind == 'line':
        ch = project.character(it.speaker)
        if ch is None:
            out.append(_issue('error', 'lint.unknown_speaker', it, path, who=it.speaker))
        elif it.face and ch.expressions and it.face not in ch.expressions:
            out.append(_issue('warning', 'lint.unknown_face', it, path, who=it.speaker, face=it.face))
    spoken, readings = project.spoken_forms, project.readings
    for word in it.bleeps:
        if ABBR.match(word) and word not in spoken and script_lang.startswith('zh'):
            out.append(_issue('warning', 'lint.bleep_no_spoken', it, path, word=word))
    if script_lang.startswith('zh'):
        plain = ''.join(s for k, s in it.segments if k == 't')
        for tok in dict.fromkeys(LATIN_DIGIT.findall(plain)):
            if not any(tok in r or r in tok for r in readings):
                out.append(_issue('warning', 'lint.no_reading', it, path, token=tok))


def lint(chapters, project=None):
    """返回 Issue 列表（含解析阶段的问题），按文件和行号排序。"""
    out = []
    seen = {}
    refs = []
    if project:
        for ch in project.characters.values():
            text = (ch.voice or {}).get('reference_text')
            if text:
                refs.append((ch.name(project.lang), re.sub(r'\W', '', text)))
    for chapter in chapters:
        out.extend(chapter.issues)
        script_lang = chapter.lang or (project.lang if project else 'zh-CN')
        for it in chapter.items:
            if isinstance(it, Directive):
                check_directive(it, chapter.path, out, project)
            elif isinstance(it, Spoken):
                check_spoken(it, chapter.path, out, project, script_lang)
                if it.id:
                    if it.id in seen:
                        other = seen[it.id]
                        out.append(_issue('error', 'lint.duplicate_id', it, chapter.path, id=it.id, other=f'{other[0]}:{other[1]}'))
                    else:
                        seen[it.id] = (chapter.path, it.line_no)
                say = re.sub(r'\W', '', it.say)
                if len(say) >= 6:
                    for who, ref in refs:
                        if say in ref or (len(ref) >= 6 and ref in say):
                            out.append(_issue('warning', 'lint.reference_overlap', it, chapter.path, who=who))
    out.sort(key=lambda i: (i.file, i.line, i.level != 'error'))
    return out
