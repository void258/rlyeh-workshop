"""BGM：曲目表（music.yaml）→ 生成 → 识别检查有没有唱出词 → 试听选定（人工）。

规矩见 docs/zh/pipeline.md「音乐」：
- 纯音乐容易被音乐模型唱出词来：先只生成乐谱，换种子直到人声声部一个音符都没有，再用这份乐谱渲染成音频；
- 用语音识别检查成品，识别出成串文字的版本不用；
- 长度限制在 2–3 分钟，播放时交叉淡化循环；片尾曲可以是带词的歌。
"""
import pathlib
import re
import shutil
import tempfile
import time

import numpy as np
import soundfile as sf
import yaml
from scipy.signal import resample_poly

from . import backends
from .state import digest
from .util import now, read_json, write_json

CONFIG = 'music.yaml'
BGM_DIR = 'audio/bgm'
TAKES_DIR = 'audio/bgm/takes'
TAKES = 'audio/bgm/takes.json'
PLANS = 'build/music_plans.json'
CHECK = 'build/music_check.json'
REVIEW = 'review/music-review.json'
AUDIO_EXT = ('.flac', '.wav', '.ogg', '.mp3')
# 纯音乐：风格里写 instrumental / no vocals，歌词只放不唱的段落标签
INSTRUMENTAL = '[Intro]\n\n[Instrumental]\n\n[Interlude]\n\n[Instrumental]\n\n[Outro]\n'
NOTE = re.compile(r"[\^_=]*[A-Ga-g][,']*(\d*/?\d*)-?")
CUE_ID = re.compile(r'^[A-Za-z0-9_-]+$')


class MusicError(RuntimeError):
    pass


def settings(project):
    m = project.config.get('music') or {}
    return dict(search_from=int(m.get('search_from', 3001)), search_limit=int(m.get('search_limit', 12)),
                seconds=float(m.get('seconds', 160)), check_chunk=float(m.get('check_chunk', 20)))


def sheet(project):
    path = project.root / CONFIG
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        raise MusicError(f'{CONFIG} is not valid YAML: {e}') from e


def cues(project):
    """曲目表：{曲目 ID: dict(id, names, style, lyrics, instrumental, seconds)}。"""
    s = settings(project)
    out = {}
    for cid, c in (sheet(project).get('cues') or {}).items():
        cid, c = str(cid), c or {}
        if not CUE_ID.match(cid):
            raise MusicError(f'{CONFIG}: cue ID "{cid}" must be ASCII letters, digits, - or _')
        if not c.get('style'):
            raise MusicError(f'{CONFIG}: cue "{cid}" has no style')
        n = c.get('name')
        names = {str(k): str(v) for k, v in n.items()} if isinstance(n, dict) else ({'zh-CN': str(n)} if n else {})
        lyrics = str(c.get('lyrics') or '').strip()
        out[cid] = dict(id=cid, names=names, style=str(c['style']).strip(), lyrics=lyrics + '\n' if lyrics else INSTRUMENTAL,
                        instrumental=bool(c.get('instrumental', not lyrics)), seconds=float(c.get('seconds') or s['seconds']))
    return out


def battle_cue(project):
    """战斗开始时自动切的曲目（music.yaml 的 battle，默认叫 battle 的那段）。"""
    b = sheet(project).get('battle', 'battle')
    return b if b in cues(project) else None


def resolve(project, name):
    """剧本里 【BGM：…】 写的名字 → 曲目 ID；对不上返回 None。"""
    name = str(name).strip()
    cs = cues(project)
    if name in cs:
        return name
    return next((cid for cid, c in cs.items() if name in c['names'].values()), None)


def vocal_notes(abc):
    """ABC 乐谱里人声声部（V:Vocal）有几个音符；和弦标注不算。"""
    voice, n = None, 0
    for line in abc.splitlines():
        s = line.strip()
        if s.startswith('V:'):
            voice = s[2:].strip().split()[0] if s[2:].strip() else None
        elif voice == 'Vocal' and s and not s.startswith('%'):
            n += len(NOTE.findall(re.sub(r'"[^"]*"', '', s)))
    return n


def _inputs(cue, backend_id):
    return digest(cue['style'], cue['lyrics'], cue['seconds'], backend_id)


def takes(project):
    """所有生成或放进来的版本：{文件名（不含扩展名）: 记录}。takes/ 里有、记录里没有的文件按手动放进来的算。"""
    idx = read_json(project.root / TAKES, {})
    d = project.root / TAKES_DIR
    if d.exists():
        ids = sorted(cues(project), key=len, reverse=True)
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in AUDIO_EXT or f.stem in idx:
                continue
            cue = next((c for c in ids if f.stem == c or f.stem.startswith(c + '_')), None)
            if cue:
                idx[f.stem] = dict(file=f'{TAKES_DIR}/{f.name}', cue=cue, seed=None, source='manual',
                                   seconds=round(sf.info(str(f)).duration, 1))
    return {k: v for k, v in idx.items() if (project.root / v['file']).exists()}


def cue_takes(project, cid):
    return [(k, t) for k, t in takes(project).items() if t['cue'] == cid]


def gen(project, only=None, n_takes=1, on_line=None):
    """每段曲子补到至少 n_takes 个现行版本（风格、歌词、长度没变的）。返回 dict(done, waiting, problems)。"""
    backend = backends.get(project, 'music')
    s = settings(project)
    idx = read_json(project.root / TAKES, {})
    plans = read_json(project.root / PLANS, {})
    res = dict(done=[], waiting=[], problems=[])
    have = takes(project)
    for cid, cue in cues(project).items():
        if only and cid not in only:
            continue
        inputs = _inputs(cue, backend.info.id)
        current = [k for k, t in have.items() if t['cue'] == cid and (t.get('inputs') == inputs or t.get('source') == 'manual')]
        need = n_takes - len(current)
        if need <= 0:
            continue
        if not backend.generates:
            res['waiting'].append(dict(id=cid, put=f'{TAKES_DIR}/{cid}_1.flac'))
            continue
        used = {t.get('seed') for t in have.values() if t['cue'] == cid and t.get('inputs') == inputs}
        tried = plans.get(cid) if (plans.get(cid) or {}).get('inputs') == inputs else {'inputs': inputs, 'seeds': {}}
        plans[cid] = tried
        found = 0
        for seed in range(s['search_from'], s['search_from'] + s['search_limit']):
            if found >= need:
                break
            if seed in used or (tried['seeds'].get(str(seed)) or 0) > 0:
                continue
            abc = None
            if cue['instrumental'] and backend.can_plan:          # 先只出乐谱，人声声部有音符就换种子
                abc = backend.plan(cue, seed, on_line)
                notes = vocal_notes(abc)
                tried['seeds'][str(seed)] = notes
                write_json(project.root / PLANS, plans)
                if on_line:
                    on_line(f'{cid} seed {seed}: {notes} vocal notes')
                if notes:
                    continue
                (project.root / TAKES_DIR).mkdir(parents=True, exist_ok=True)
                (project.root / TAKES_DIR / f'{cid}_s{seed}.abc').write_text(abc, encoding='utf-8')
            t0 = time.time()
            out = pathlib.Path(backend.render(cue, seed, project.root / TAKES_DIR / f'{cid}_s{seed}', abc, on_line))
            idx[out.stem] = dict(file=out.relative_to(project.root).as_posix(), cue=cid, seed=seed, inputs=inputs,
                                 backend=backend.info.id, seconds=round(sf.info(str(out)).duration, 1),
                                 searched=abc is not None, took=round(time.time() - t0), at=now())
            write_json(project.root / TAKES, idx)
            res['done'].append(out.stem)
            found += 1
            if on_line:
                on_line(f'{out.name} {idx[out.stem]["seconds"]}s')
        if found < need:
            res['problems'].append(dict(id=cid, reason=f'no vocal-free score in {s["search_limit"]} seeds from '
                                                       f'{s["search_from"]}; raise [music] search_limit or rewrite the style'))
    return res


def _mono16k(path):
    y, sr = sf.read(str(path), dtype='float32')
    m = y.mean(1) if y.ndim > 1 else y
    return m, sr, resample_poly(m, 16000, sr).astype(np.float32)


def check(project, only=None, on_line=None):
    """纯音乐的版本每 check_chunk 秒识别一次，识别出成串文字就是唱出了词。写 build/music_check.json。识别后端是 none 时返回 None。"""
    asr = backends.get(project, 'asr')
    if asr.info.id == 'none':
        return None
    cs = cues(project)
    report = read_json(project.root / CHECK, {})
    chunk = settings(project)['check_chunk']
    todo = []
    for k, t in takes(project).items():
        cue = cs.get(t['cue'])
        if not cue or not cue['instrumental'] or (only and t['cue'] not in only):
            continue
        h = digest(project.root / t['file'])
        if (report.get(k) or {}).get('file_hash') != h:
            todo.append((k, t, h))
    if not todo:
        return report
    with tempfile.TemporaryDirectory(prefix='rlyeh-music-') as tmp:
        parts, info = [], {}
        for k, t, h in todo:
            m, sr, x = _mono16k(project.root / t['file'])
            info[k] = dict(cue=t['cue'], seconds=round(len(m) / sr, 1),
                           loudness_db=round(20 * float(np.log10(np.sqrt((m ** 2).mean()) + 1e-9)), 1), file_hash=h)
            step = int(16000 * chunk)
            for i in range(0, len(x), step):
                p = pathlib.Path(tmp) / f'{len(parts):05d}.wav'
                sf.write(p, x[i:i + step], 16000)
                parts.append((k, i // 16000, str(p)))
        texts = asr.transcribe([p for _, _, p in parts], 'auto', on_line)
        if texts is None:
            return None
    words = {k: [] for k, _, _ in todo}
    for k, start, p in parts:
        text = (texts.get(p) or '').strip()
        if len(re.sub(r'\W', '', text)) > 2:              # 只有一两个字的多半是误识别，不算
            words[k].append(dict(at=start, text=text[:40]))
    for k in words:
        report[k] = dict(info[k], words=words[k], clean=not words[k], at=now())
    write_json(project.root / CHECK, report)
    return report


def final(project, cid):
    """选定后的成品 audio/bgm/<曲目ID>.<扩展名>。"""
    for ext in AUDIO_EXT:
        p = project.root / BGM_DIR / f'{cid}{ext}'
        if p.exists():
            return p
    return None


def pick(project, cid, choice, note='', by=''):
    """choice：版本序号（1 起，按 replay music 列出的顺序）或文件名。把选中的版本复制成 audio/bgm/<曲目ID>.<扩展名>。"""
    if cid not in cues(project):
        raise MusicError(f'unknown cue: {cid}')
    ts = cue_takes(project, cid)
    if isinstance(choice, int) or str(choice).isdigit():
        k = int(choice) - 1
        if not 0 <= k < len(ts):
            raise MusicError(f'{cid}: no take #{choice}')
        key, take = ts[k]
    else:
        stem = pathlib.Path(str(choice)).stem
        match = [(k, t) for k, t in ts if k == stem]
        if not match:
            raise MusicError(f'{cid}: no take named {choice}')
        key, take = match[0]
    src = project.root / take['file']
    old = final(project, cid)
    if old:
        old.unlink()
    dst = project.root / BGM_DIR / f'{cid}{src.suffix.lower()}'
    shutil.copy2(src, dst)
    reviews = read_json(project.root / REVIEW, {})
    reviews[cid] = dict(status='approved', choice=take['file'], note=note, by=by, at=now())
    write_json(project.root / REVIEW, reviews)
    return reviews[cid]


def summary(project):
    cs = cues(project)
    ts = takes(project)
    rep = read_json(project.root / CHECK, {})
    reviews = read_json(project.root / REVIEW, {})
    return dict(cues=len(cs), with_takes=len({t['cue'] for t in ts.values() if t['cue'] in cs}),
                takes=len(ts), vocals=sum(1 for k in ts if rep.get(k) and not rep[k]['clean']),
                picked=sum(1 for c in cs if final(project, c) and (reviews.get(c) or {}).get('status') == 'approved'))
