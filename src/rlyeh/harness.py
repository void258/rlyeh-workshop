"""把流程手册和 MCP 配置导出给各家 harness：replay export-agent <claude-code|codex|dsh>。

写进项目文件夹的东西：
- 三家都有：AGENTS.md（流程手册）和 8 个技能；
- Claude Code：CLAUDE.md（一行 @AGENTS.md）、.claude/skills/、.mcp.json，配了模型时还有 .claude/settings.json；
- Codex：.agents/skills/、.codex/config.toml 里的 [mcp_servers.rlyeh] 和模型；
- dsh：.agents/skills/、.rlyeh/dsh-patch.yml（运行时用 --patch 带上）。

手册和技能整份由工具写：用户改过的（和上次导出的不一样）默认留着不动，--force 才覆盖。
配置文件只改自己那一项，别的内容原样保留；解析不了的配置不碰，报给用户。
启动命令里写的是这台机器上的绝对路径，换机器或挪文件夹后重新导出一次。
"""
import copy
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import tomllib
from importlib import resources

import yaml

from .i18n import t
from .util import now, read_json, write_json

HARNESSES = ('claude-code', 'codex', 'dsh')
RECORD = '.rlyeh/agent-export.json'
SERVER = 'rlyeh'
SKILL_DIRS = {'claude-code': '.claude/skills', 'codex': '.agents/skills', 'dsh': '.agents/skills'}
DSH_PATCH = '.rlyeh/dsh-patch.yml'
TOOL_TIMEOUT = 600                  # 秒；慢的阶段走后台任务，这里只兜底
DSH_HEAD = {
    'zh': ('# 拉莱耶工坊给 dsh 的补丁：接上 replay mcp。由 replay export-agent dsh 生成，重新导出会覆盖。\n'
           '# 用法：dsh --profile headless --patch {patch} "任务"\n'),
    'en': ("# R'lyeh Workshop patch for dsh: connects replay mcp. Written by replay export-agent dsh; re-exporting overwrites it.\n"
           '# Usage: dsh --profile headless --patch {patch} "task"\n'),
}


class ExportError(Exception):
    pass


def _lang(lang):
    return 'en' if (lang or '').lower().startswith('en') else 'zh'


def playbook(lang):
    """手册文件 {相对 playbook/<语言>/ 的路径: 文本}：AGENTS.md 和 skills/<名字>/SKILL.md。"""
    root = resources.files('rlyeh') / 'playbook' / _lang(lang)
    files = {'AGENTS.md': (root / 'AGENTS.md').read_text(encoding='utf-8')}
    for d in sorted((root / 'skills').iterdir(), key=lambda p: p.name):
        if (d / 'SKILL.md').is_file():
            files[f'skills/{d.name}/SKILL.md'] = (d / 'SKILL.md').read_text(encoding='utf-8')
    return files


def front_matter(text):
    """SKILL.md 开头 --- 之间的 YAML。"""
    m = re.match(r'---\n(.*?)\n---\n', _norm(text), re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def mcp_command(root, command=None):
    """启动 MCP 服务的命令和参数。默认用同一个安装里的 replay；不在一起时用当前 Python 跑模块，免得连到别的版本。"""
    args = ['mcp', '-C', str(root)]
    if command:
        return command, args
    exe = shutil.which('replay')
    py = pathlib.Path(sys.executable).absolute()        # 不解析软链接：虚拟环境的 python 常是指向系统 Python 的链接
    if exe and os.path.normcase(str(pathlib.Path(exe).absolute().parent)) == os.path.normcase(str(py.parent)):
        exe = pathlib.Path(exe).absolute()
        return str(exe.with_suffix(exe.suffix.lower())), args       # Windows 上 which 给的是 replay.EXE
    return str(py), ['-m', 'rlyeh.cli'] + args


def _norm(text):
    return text.replace('\r\n', '\n')


def _digest(text):
    return hashlib.sha256(_norm(text).encode('utf-8')).hexdigest()


class _Writer:
    def __init__(self, root, force):
        self.root, self.force = root, force
        self.record = read_json(root / RECORD, {})
        self.digests = dict(self.record.get('files', {}))
        self.files = {}                                 # 相对路径 → dict(path, action, reason)

    def _write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_norm(text).encode('utf-8'))   # 统一 LF，Windows 上 write_text 会写成 CRLF

    def _done(self, rel, action, reason=''):
        self.files[rel] = dict(path=rel, action=action, reason=reason)

    def own(self, rel, text):
        """整份由工具管的文件：没有就写；还是上次导出的样子就更新；用户改过就留着。"""
        if rel in self.files:                           # Codex 和 dsh 共用 .agents/skills，只写一次
            return
        path = self.root / rel
        action = 'written'
        if path.exists():
            old = path.read_text(encoding='utf-8')
            if _norm(old) == _norm(text):
                self.digests[rel] = _digest(text)
                return self._done(rel, 'unchanged')
            if not self.force and self.digests.get(rel) != _digest(old):
                return self._done(rel, 'kept', 'edited')
            action = 'updated'
        self._write(rel, text)
        self.digests[rel] = _digest(text)
        self._done(rel, action)

    def merge(self, rel, fn):
        """别人也会写的配置文件：fn(旧文本或 None) → 新文本，只改自己那一项；解析不了时 fn 抛 ValueError(原因)。"""
        if rel in self.files:
            return
        path = self.root / rel
        old = path.read_text(encoding='utf-8') if path.exists() else None
        try:
            new = fn(old)
        except ValueError as e:
            return self._done(rel, 'kept', str(e))
        if old is not None and _norm(old) == _norm(new):
            return self._done(rel, 'unchanged')
        self._write(rel, new)
        self._done(rel, 'written' if old is None else 'merged')

    def save(self, names, command):
        done = dict(self.record.get('harnesses', {}))
        for name in names:
            done[name] = dict(at=now(), command=command)
        write_json(self.root / RECORD, dict(files=self.digests, harnesses=done))


def _claude_md(old):
    if old is None:
        return '@AGENTS.md\n'
    if any(line.strip() == '@AGENTS.md' for line in old.splitlines()):
        return old
    return '@AGENTS.md\n\n' + old                       # 用户自己写的 CLAUDE.md 留着，开头引入手册


def _json_set(keys, value):
    def fn(old):
        data = {}
        if old is not None and old.strip():
            try:
                data = json.loads(old)
            except json.JSONDecodeError:
                raise ValueError('bad_json') from None
        if not isinstance(data, dict):
            raise ValueError('bad_json')
        new = copy.deepcopy(data)
        node = new
        for k in keys[:-1]:
            node = node.setdefault(k, {})
            if not isinstance(node, dict):
                raise ValueError('bad_json')
        node[keys[-1]] = value
        if old is not None and new == data:
            return old                                  # 内容一样就不重排格式
        return json.dumps(new, ensure_ascii=False, indent=2) + '\n'
    return fn


TOML_HEADER = re.compile(r'^\s*\[{1,2}\s*([^\[\]]+?)\s*\]{1,2}\s*(?:#.*)?$')


def _toml_value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return '[' + ', '.join(_toml_value(x) for x in v) + ']'
    return json.dumps(str(v), ensure_ascii=False)       # JSON 的字符串转义在 TOML 基本字符串里同样合法


def _toml_set(top, table, values):
    """改 TOML 文本：顶层键 top 换成新值或补上；[table]（连同它的子表）整段换成 values。其余行原样保留。"""
    def fn(old):
        text = _norm(old or '')
        if text.strip():
            try:
                tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                raise ValueError('bad_toml') from None
        kept, skip = [], False
        for line in text.split('\n'):
            m = TOML_HEADER.match(line)
            if m:
                name = m.group(1).replace(' ', '')
                skip = name == table or name.startswith(table + '.')
            if not skip:
                kept.append(line)
        first = next((i for i, line in enumerate(kept) if TOML_HEADER.match(line)), len(kept))
        head, rest = kept[:first], kept[first:]
        for k, v in top.items():
            pat = re.compile(rf'^\s*{re.escape(k)}\s*=')
            line = f'{k} = {_toml_value(v)}'
            i = next((i for i, x in enumerate(head) if pat.match(x)), None)
            if i is None:
                while head and not head[-1].strip():
                    head.pop()
                head.append(line)
            else:
                head[i] = line
        for part in (head, rest):
            while part and not part[-1].strip():
                part.pop()
        block = [f'[{table}]'] + [f'{k} = {_toml_value(v)}' for k, v in values.items()]
        lines = head + ([''] if head and rest else []) + rest + ([''] if head or rest else []) + block
        new = '\n'.join(lines) + '\n'
        try:
            tomllib.loads(new)
        except tomllib.TOMLDecodeError:
            raise ValueError('bad_toml') from None
        return new
    return fn


def _dsh_patch(root, command, args, cfg, lang):
    rows = []
    if cfg.get('model'):                                # 补丁会整块替换这个插件的配置，所以 provider 也写上
        rows.append(dict(id='agent-default-model',
                         config=dict(provider=cfg.get('provider') or 'deepseek-official', model=cfg['model'])))
    rows.append({'insert': [dict(id='mcp-rlyeh', name='@deepseek-ai/dsh-mcp-client', config=dict(
        serverName=SERVER, transport='stdio', command=command, args=args, cwd=str(root),
        toolCallTimeoutMs=TOOL_TIMEOUT * 1000, failOnStartupError=True))]})
    return DSH_HEAD[lang].format(patch=DSH_PATCH) + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False)


def default_harness(project):
    return (project.config.get('harness') or {}).get('default') or 'claude-code'


def export(project, names=None, lang=None, command=None, force=False):
    """把手册和 MCP 配置写进项目文件夹。返回 dict(harnesses, lang, command, files, notes)；notes 是 (i18n 键, 参数)。"""
    names = list(dict.fromkeys(names or [default_harness(project)]))
    if 'all' in names:
        names = list(HARNESSES)
    bad = [n for n in names if n not in HARNESSES]
    if bad:
        raise ExportError(t('export.unknown', names=', '.join(bad)))
    lang = _lang(lang or project.lang)
    root = project.root
    cmd, args = mcp_command(root, command)
    cfg = project.config.get('harness') or {}
    book = playbook(lang)
    w = _Writer(root, force)
    notes = []
    for name in names:
        w.own('AGENTS.md', book['AGENTS.md'])
        for rel, text in book.items():
            if rel.startswith('skills/'):
                w.own(SKILL_DIRS[name] + rel[len('skills'):], text)
        hc = cfg.get(name) or {}
        if name == 'claude-code':
            w.merge('CLAUDE.md', _claude_md)
            w.merge('.mcp.json', _json_set(['mcpServers', SERVER], dict(type='stdio', command=cmd, args=args)))
            if hc.get('model'):
                w.merge('.claude/settings.json', _json_set(['model'], hc['model']))
            notes.append(('export.hint.claude-code', {}))
        elif name == 'codex':
            top = {k: hc[src] for k, src in (('model', 'model'), ('model_reasoning_effort', 'effort')) if hc.get(src)}
            w.merge('.codex/config.toml', _toml_set(top, f'mcp_servers.{SERVER}', dict(
                command=cmd, args=args, startup_timeout_sec=30, tool_timeout_sec=TOOL_TIMEOUT)))
            if not top:
                notes.append(('export.codex_no_model', {}))
            notes.append(('export.hint.codex', dict(command=' '.join(_quote(x) for x in [cmd] + args))))
        else:
            w.own(DSH_PATCH, _dsh_patch(root, cmd, args, hc, lang))
            notes.append(('export.hint.dsh', dict(patch=DSH_PATCH)))
    w.save(names, [cmd] + args)
    return dict(harnesses=names, lang=lang, command=[cmd] + args, files=list(w.files.values()), notes=notes)


def _quote(s):
    return f'"{s}"' if re.search(r'\s', s) else s
