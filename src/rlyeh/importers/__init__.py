"""导入流程：logs/raw/ 里的所有导出 → 合并去重 → 改名、匿名化 → 标角色 → 切场次 → logs/events.jsonl。

每次 replay import 都把 logs/raw/ 全部重新解析一遍，所以分几次导入、重复导入同一份都没关系。
配置（replay.toml）：
  [import]
  system = "demonlord"            # 解析哪个游戏系统的卡片；不写就挨个试
  gm = ["void"]                    # GM 的账号名
  observers = ["ob1"]              # 旁观者
  renamed = { "白石" = "鲨鱼" }    # 中途改过名的账号，统一成一个名字
  session_gap_hours = 3            # 两条消息隔这么久就算下一场
  min_session_messages = 20        # 少于这么多条的一场当测试，丢掉
  [aliases]                        # 匿名化：真名 → 化名，发言人和正文里都换
  "张三" = "小林"
"""
import datetime
import json
import pathlib
import shutil
import zipfile

from . import fvtt, text
from .base import scan_private

RAW_SUFFIXES = ('.txt', '.log', '.zip')


def read_sources(paths):
    """[(名字, 文本)]，zip 里的 .txt 逐个展开。"""
    out = []
    for p in paths:
        p = pathlib.Path(p)
        if p.suffix.lower() == '.zip':
            with zipfile.ZipFile(p) as z:
                for n in sorted(z.namelist()):
                    if n.lower().endswith(('.txt', '.log')):
                        out.append((f'{p.name}/{n}', z.read(n).decode('utf-8-sig', errors='replace')))
        else:
            out.append((p.name, p.read_text(encoding='utf-8-sig', errors='replace')))
    return out


def copy_raw(inputs, raw_dir):
    """把要导入的文件复制进 logs/raw/；同名不同内容的加后缀，不覆盖。返回新复制的文件。"""
    raw_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    files = []
    for p in map(pathlib.Path, inputs):
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in RAW_SUFFIXES) if p.is_dir() else [p]
    for f in files:
        dst = raw_dir / f.name
        if dst.exists():
            if dst.read_bytes() == f.read_bytes():
                continue
            k = 2
            while (raw_dir / f'{f.stem}_{k}{f.suffix}').exists():
                k += 1
            dst = raw_dir / f'{f.stem}_{k}{f.suffix}'
        if f.resolve() != dst.resolve():
            shutil.copy2(f, dst)
            copied.append(dst.name)
    return copied


def _replace_names(s, table):
    for k in sorted(table, key=len, reverse=True):
        s = s.replace(k, table[k])
    return s


def build(config, raw_dir):
    """解析 raw_dir 里的全部导出，返回 (events, report)。"""
    imp = config.get('import') or {}
    renamed = {str(k): str(v) for k, v in (imp.get('renamed') or {}).items()}
    aliases = {str(k): str(v) for k, v in (config.get('aliases') or {}).items()}
    gm = set(map(str, imp.get('gm') or [])) | {'GM', 'Gamemaster'}
    observers = set(map(str, imp.get('observers') or []))
    players = set((config.get('players') or {}).keys())
    gap = datetime.timedelta(hours=float(imp.get('session_gap_hours', 3)))
    min_msgs = int(imp.get('min_session_messages', 20))

    files = sorted(f for f in raw_dir.glob('*') if f.suffix.lower() in RAW_SUFFIXES)
    sources = read_sources(files)
    fv, tx, raw_count = [], [], 0
    for name, body in sources:
        if fvtt.sniff(body):
            msgs = fvtt.parse(body)
            raw_count += len(msgs)
            fv.append((name, msgs))
        else:
            evs = text.parse(body, name)
            raw_count += len(evs)
            tx += evs
    events = fvtt.to_events(fvtt.merge(fv), imp.get('system')) + tx
    events.sort(key=lambda e: e.ts or datetime.datetime.max)

    for e in events:
        e.speaker = _replace_names(renamed.get(e.speaker, e.speaker), aliases)
        e.text = _replace_names(e.text, aliases)
        if e.speaker in gm or renamed.get(e.speaker) in gm:
            e.role = 'gm'
        elif e.speaker in players:
            e.role = 'player'
        elif e.speaker in observers:
            e.role = 'observer'
        else:
            e.role = 'character'

    # 切场次：两条消息之间隔得太久就算下一场；没有时间的记录整体算一场
    sessions, cur, last = [], None, None
    for e in events:
        if cur is None or (e.ts and last and e.ts - last > gap):
            cur = []
            sessions.append(cur)
        cur.append(e)
        last = e.ts or last
    kept, dropped, n = [], [], 0
    for s in sessions:
        if len(s) >= min_msgs or len(sessions) == 1:
            n += 1
            for e in s:
                e.session = n
            kept.append(s)
        else:
            dropped.append(s)
    out = [e for s in kept for e in s]
    for i, e in enumerate(out, 1):
        e.id = f'e{i:06d}'

    def span(s):
        ts = [e.ts for e in s if e.ts]
        return (ts[0].isoformat(), ts[-1].isoformat()) if ts else (None, None)

    report = dict(
        files=[name for name, _ in sources], raw_messages=raw_count, merged_messages=len(events), events=len(out),
        sessions=[dict(session=i + 1, start=span(s)[0], end=span(s)[1], events=len(s),
                       speakers=sorted({e.speaker for e in s})) for i, s in enumerate(kept)],
        dropped=[dict(start=span(s)[0], end=span(s)[1], events=len(s)) for s in dropped],
        private=scan_private(out),
        unknown_speakers=sorted({e.speaker for e in out if e.role == 'character'}),
    )
    return out, report


def run(project_root, config):
    root = pathlib.Path(project_root)
    raw_dir = root / 'logs' / 'raw'
    events, report = build(config, raw_dir)
    logs = root / 'logs'
    (logs / 'events.jsonl').write_text(''.join(e.as_json() + '\n' for e in events), encoding='utf-8')
    (logs / 'sessions.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return events, report

