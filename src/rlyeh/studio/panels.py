"""Studio 的 AI 面板、后端设置和出片页用的数据和操作。

AI 面板不替用户启动 AI：只导出配置、给出启动命令和开场白、显示 AI 做到哪了、列出 AI 请求的审核。
设置只改 replay.toml 里允许改的几项（各类后端、harness 的模型），注释和别的内容原样保留。
"""
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib

from .. import backends, doctor, harness, jobs, tasks, voice
from ..i18n import t
from ..mcp import REQUESTS
from ..util import read_json, write_json


class PanelError(Exception):
    pass


# ── AI 面板 ──

CLIS = {'claude-code': 'claude', 'codex': 'codex', 'dsh': 'dsh'}
PROMPT = {
    'zh': '这是拉莱耶工坊的 replay 项目。先读 AGENTS.md，再用 replay next（或 MCP 工具 rlyeh_next_task）一件一件领任务做；'
          '需要我审核或拍板的时候停下来，告诉我去 Studio 的哪一页。',
    'en': "This is an R'lyeh Workshop replay project. Read AGENTS.md first, then take tasks one at a time with replay next "
          '(or the MCP tool rlyeh_next_task). When something needs my review or decision, stop and tell me which Studio page to open.',
}


def _quote(s):
    return f'"{s}"' if re.search(r'[\s"]', s) else s


def agent(project, lang):
    root = project.root
    en = lang.startswith('en')
    prompt = PROMPT['en' if en else 'zh']
    record = read_json(root / harness.RECORD, {})
    requests = [dict(r, index=i) for i, r in enumerate(read_json(root / REQUESTS, []))]
    done = read_json(root / tasks.RECORD, {})
    activity = sorted(({'id': k, 'at': v.get('at', ''), 'note': v.get('note', '')} for k, v in done.items()),
                      key=lambda x: x['at'], reverse=True)[:12]
    commands = {
        'claude-code': ['claude'],
        'codex': ['codex'],
        'dsh': [f'dsh --profile headless --patch {harness.DSH_PATCH} {_quote(prompt)}'],
    }
    return dict(default=harness.default_harness(project), harnesses=list(harness.HARNESSES), root=str(root),
                exported=record.get('harnesses', {}), installed={h: bool(shutil.which(c)) for h, c in CLIS.items()},
                prompt=prompt, commands=commands, requests=requests[::-1], activity=activity)


def export(project, names, lang, force=False):
    res = harness.export(project, names, lang, None, force)
    notes = [t(key, **kw) for key, kw in res['notes']] + [t('export.moved')]
    files = [dict(f, reason=t('export.reason.' + f['reason']) if f['reason'] else '') for f in res['files']]
    return dict(harnesses=res['harnesses'], command=res['command'], files=files, notes=notes)


def close_request(project, index):
    path = project.root / REQUESTS
    reqs = read_json(path, [])
    if not isinstance(index, int) or not 0 <= index < len(reqs):
        raise PanelError(f'no review request {index}')
    reqs[index]['status'] = 'done'
    write_json(path, reqs)
    return dict(request=reqs[index])


def attention(project):
    """导航栏上的提醒：等人审核的任务、AI 请求的审核。"""
    waiting = [x.id for x in tasks.plan(project) if x.status == 'review']
    open_requests = sum(1 for r in read_json(project.root / REQUESTS, []) if r.get('status') == 'open')
    return dict(reviews=waiting, requests=open_requests)


# ── 设置 ──

HEADER = re.compile(r'^\s*\[([^\[\]]+)\]\s*(?:#.*)?$')
EDITABLE = {('harness', 'default'), ('harness.codex', 'model'), ('harness.codex', 'effort'), ('harness.claude-code', 'model'),
            ('harness.dsh', 'provider'), ('harness.dsh', 'model')}


def settings(project):
    table = project.config.get('backends') or {}
    reg = backends._registry()
    kinds = []
    for kind in doctor.KINDS:
        current = table.get(kind) or backends.DEFAULTS.get(kind)
        options = []
        for name, cls in reg[kind].items():
            info = getattr(cls, 'info', None)
            options.append(dict(id=name, license=getattr(info, 'license', ''), commercial=getattr(info, 'commercial_use', None),
                                gpu=getattr(info, 'needs_gpu', False), vram=getattr(info, 'vram_gb', None),
                                languages=list(getattr(info, 'languages', ()))))
        params = table.get(current) if isinstance(table.get(current), dict) else {}
        kinds.append(dict(kind=kind, current=current, options=options, params=params))
    cfg = project.config.get('harness') or {}
    return dict(backends=kinds, harness=dict(default=cfg.get('default') or 'claude-code', harnesses=list(harness.HARNESSES),
                                             codex=cfg.get('codex') or {}, claude=cfg.get('claude-code') or {}, dsh=cfg.get('dsh') or {}))


def _value(v):
    return json.dumps(v, ensure_ascii=False)


def set_toml(path, table, key, value):
    """改 TOML 里 [table] 的 key：有就换值（留着行尾注释），没有就补上；value 为空时删掉这一行。其余内容原样保留。"""
    text = path.read_text(encoding='utf-8').replace('\r\n', '\n')
    lines = text.split('\n')
    start = next((i for i, line in enumerate(lines) if (m := HEADER.match(line)) and m.group(1).strip() == table), None)
    new_line = f'{key} = {_value(value)}'
    pat = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*)("(?:[^"\\]|\\.)*"|[^#\s]+)(\s*#.*)?$')
    if start is None:
        if value in ('', None):
            return
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ['', f'[{table}]', new_line, '']
    else:
        end = next((i for i in range(start + 1, len(lines)) if HEADER.match(lines[i]) or lines[i].lstrip().startswith('[[')), len(lines))
        idx = next((i for i in range(start + 1, end) if pat.match(lines[i])), None)
        if idx is not None and value in ('', None):
            del lines[idx]
        elif idx is not None:
            m = pat.match(lines[idx])
            lines[idx] = m.group(1) + _value(value) + (m.group(3) or '')
        elif value not in ('', None):
            at = end
            while at > start + 1 and not lines[at - 1].strip():
                at -= 1
            lines.insert(at, new_line)
    new = '\n'.join(lines)
    try:
        tomllib.loads(new)
    except tomllib.TOMLDecodeError as e:
        raise PanelError(f'replay.toml would become invalid: {e}') from None
    path.write_bytes(new.encode('utf-8'))


def update(project, table, key, value):
    value = '' if value is None else str(value).strip()
    if table == 'backends':
        reg = backends._registry()
        if key not in doctor.KINDS or value not in reg.get(key, {}):
            raise PanelError(f'unknown {key} backend: {value}')
    elif (table, key) not in EDITABLE:
        raise PanelError(f'{table}.{key} cannot be changed here')
    elif (table, key) == ('harness', 'default') and value not in harness.HARNESSES:
        raise PanelError(f'unknown harness: {value}')
    set_toml(project.root / 'replay.toml', table, key, value)
    return dict(table=table, key=key, value=value)


def check(project, lang):
    return dict(checks=doctor.run(project))


# ── 出片 ──

KIND = re.compile(r'_(share|compat|clip)$')


def video(project):
    root = project.root
    pid = (project.config.get('project') or {}).get('id', 'replay')
    vdir = root / 'build' / 'video'
    files = []
    for f in sorted(vdir.glob('*.mp4')) if vdir.is_dir() else []:
        if f.stem.endswith('_video') or re.search(r'_ch\d+_video$', f.stem):
            continue                                    # 还没混音的中间文件
        m = KIND.search(f.stem)
        kind = m.group(1) if m else ('master' if f.stem == pid else 'other')
        st = f.stat()
        files.append(dict(path=f.relative_to(root).as_posix(), name=f.name, kind=kind, bytes=st.st_size, mtime=int(st.st_mtime)))
    last = read_json(vdir / f'{pid}_events.json', {}) if vdir.is_dir() else {}
    chapters = [dict(number=ch.number, title=ch.title, first=next((it.id for it in ch.spoken), None)) for ch in project.chapters()]
    vs = voice.summary(project)
    return dict(id=pid, files=files, player=(root / 'build' / 'player' / 'data.js').is_file(), chapters=chapters,
                last_seconds=last.get('duration'), voice_seconds=vs.get('seconds', 0),
                tools=dict(ffmpeg=bool(shutil.which('ffmpeg')), playwright=importlib.util.find_spec('playwright') is not None),
                jobs=[r for r in jobs.listing(root, 50) if r.get('command', [''])[0] in ('render', 'encode', 'build')][-6:][::-1])


def reveal(project, rel):
    """在文件管理器里打开项目里的某个文件或文件夹（只认项目里面的）。"""
    root = project.root.resolve()
    target = (root / (rel or '')).resolve()
    if target != root and root not in target.parents or not target.exists():
        raise PanelError(f'not found in the project: {rel}')
    if sys.platform == 'win32':
        if target.is_file():
            subprocess.Popen(['explorer', '/select,', str(target)])
        else:
            os.startfile(str(target))
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', '-R', str(target)] if target.is_file() else ['open', str(target)])
    else:
        subprocess.Popen(['xdg-open', str(target.parent if target.is_file() else target)])
    return dict(path=pathlib.Path(target).relative_to(root).as_posix() if target != root else '.')
