"""音效：内置的程序合成音效库，加上项目自己的音效（写在 sfx.yaml 里）。

项目音效有两种：
- 人声类（尖叫、低吼、僵尸呻吟）：用配音后端按角色声线生成几版，挑最响的一版，截掉前后拖的部分，
  再按 space 加工成「隔着墙 / 门 / 楼板」的效果；几个声音可以错开叠在一起（layers）。
- 自己准备的文件：写 file。

  replay sfx                   → audio/sfx/<名字>.wav 和 audio/sfx/index.json（只做没做过或过期的）
规矩见 docs/zh/pipeline.md「音效」。
"""
import pathlib

import numpy as np
import soundfile as sf
import yaml
from scipy.signal import resample_poly

from .. import backends, voice
from ..state import State, digest
from ..util import write_json
from . import synth

SFX_DIR = 'audio/sfx'
TAKES = 'audio/sfx/_takes'
INDEX = 'audio/sfx/index.json'
CONFIG = 'sfx.yaml'

# 剧本里 【音效：…】 可以用的别名（播放器会自动给骰子、伤害、战斗、章节等挂音效，不用写）
ALIASES = {
    'dice_roll': ['掷骰'], 'dice_good': ['好运'], 'dice_bad': ['倒霉'], 'dice_crit': ['大成功'], 'dice_fumble': ['大失败'],
    'hit_blunt': ['钝击'], 'hit_slash': ['斩击'], 'hit_heavy': ['重击'], 'miss': ['挥空'], 'sling': ['投石'], 'burn': ['灼烧'],
    'fire_breath': ['喷火'], 'flames': ['火焰', '燃烧'], 'ghost': ['幽灵', '鬼魂'], 'dash': ['冲刺'], 'door_break': ['破门'],
    'door_bang': ['撞门', '砸门'], 'rumble': ['轰隆', '震动'], 'flash': ['闪光'], 'dawn': ['晨光', '黎明'],
    'battle_start': ['战斗开始'], 'gong': ['锣'], 'battle_end': ['战斗胜利'], 'clash': ['兵刃', '交锋'], 'item': ['获得道具'],
    'chapter': ['章节'], 'scene': ['转场'], 'cg': ['CG'],
}


class SfxError(RuntimeError):
    pass


def _filt2(y, lo=None, hi=None):
    if hi:
        y = synth.filt(y, 'low', hi)
    if lo:
        y = synth.filt(y, 'high', lo)
    return y


# 加工预设：声音从哪里传过来
SPACES = {
    'dry': lambda y: y,
    'room': lambda y: synth.reverb(y, .8, .25),
    'next-room': lambda y: synth.reverb(_filt2(y, hi=3500), 1.0, .3, 3000),           # 门内、隔壁，压低一点
    'behind-door': lambda y: synth.reverb(_filt2(y, 90, 1400), 1.4, .4, 1800),        # 闷在门外
    'upstairs': lambda y: synth.reverb(_filt2(y, 250, 3200), 1.6, .45, 3000),         # 隔着楼板
}


def custom(project):
    """sfx.yaml 里的项目音效：{ID: 设置}。"""
    path = project.root / CONFIG
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        raise SfxError(f'{CONFIG} is not valid YAML: {e}') from e
    return {str(k): v or {} for k, v in (data.get('sounds') or {}).items()}


def _names(spec):
    n = spec.get('name')
    if isinstance(n, dict):
        return [str(v) for v in n.values()]
    return [str(n)] if n else []


def catalog(project):
    """所有能用的音效：{ID: dict(builtin, aliases)}，项目音效同名时盖过内置的。"""
    out = {k: dict(builtin=True, aliases=list(v)) for k, v in ALIASES.items()}
    for k, spec in custom(project).items():
        out[k] = dict(builtin=False, aliases=_names(spec) + [str(a) for a in spec.get('aliases') or []])
    return out


def resolve(project, name):
    """剧本里写的音效名 → 音效 ID；对不上返回 None。"""
    name = str(name).strip()
    cat = catalog(project)
    if name in cat:
        return name
    for k, v in cat.items():
        if name in v['aliases'] or name.lower() in (a.lower() for a in v['aliases']):
            return k
    return None


# ───────── 人声类音效的加工 ─────────
def loudest(y, sr, max_len):
    """生成的音效常常前后拖一大段，只留能量最集中的 max_len 秒。"""
    n = int(max_len * sr)
    if len(y) <= n:
        return y
    e = np.convolve(y ** 2, np.ones(n), mode='valid')
    i = int(np.argmax(e[::256])) * 256
    return y[i:i + n]


def load_take(path, semitones=0, max_len=3.0):
    y, sr = sf.read(str(path), dtype='float32')
    y = y.mean(1) if y.ndim > 1 else y
    y = resample_poly(loudest(y, sr, max_len), synth.SR, sr)
    if semitones:                      # 用重采样降调（顺带放慢），呻吟声正好要这种拖沓感
        k = 2 ** (semitones / 12)
        y = resample_poly(y, 1000, int(round(1000 * k)))
    nz = np.where(np.abs(y) > .02)[0]
    return y[max(0, nz[0] - 2400):nz[-1] + 4800] if len(nz) else y


def energy(path, max_len):
    y, sr = sf.read(str(path), dtype='float32')
    y = y.mean(1) if y.ndim > 1 else y
    return float((loudest(y, sr, max_len) ** 2).sum())


def _layers(spec):
    if spec.get('layers'):
        return [dict(spec, **layer) for layer in spec['layers']]       # 层没写的设置跟整个音效走
    return [spec]


def _refs(project, cid, tts_id):
    ref = voice.reference(project, cid)
    if ref is None and tts_id != 'placeholder':
        raise SfxError(f'no chosen voice for {cid} (choose it in replay preview first)')
    return ([ref] if ref else []) + voice.extra_references(project, cid)


# ───────── 生成 ─────────
def _write(path, y):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y.astype(np.float32), synth.SR, subtype='PCM_16')
    return round(len(y) / synth.SR, 3)


def build(project, only=None, force=False, on_line=None):
    """生成内置音效和 sfx.yaml 里的音效，写 audio/sfx/index.json。返回 dict(done, problems)。"""
    state = State(project.root)
    sounds = custom(project)
    done, problems, index = [], [], {}
    for name in synth.SOUNDS:
        if name in sounds:
            continue
        key = f'{SFX_DIR}/{name}.wav'
        inputs = digest(synth.VERSION, name)
        if (not only or name in only) and (force or not state.fresh(key, inputs, project.root / key)):
            state.set(key, inputs=inputs, seconds=_write(project.root / key, synth.render(name)))
            done.append(name)
        index[name] = dict(file=key, builtin=True, aliases=ALIASES.get(name, []),
                           seconds=(state.get(key) or {}).get('seconds'), min_gap=0)

    tts_id = (project.config.get('backends') or {}).get('tts', backends.DEFAULTS['tts'])
    todo = []
    for sid, spec in sounds.items():
        entry = dict(builtin=False, aliases=_names(spec) + [str(a) for a in spec.get('aliases') or []],
                     min_gap=float(spec.get('min_gap', 0)))
        if spec.get('file'):
            f = project.root / spec['file']
            if not f.exists():
                if not only or sid in only:
                    problems.append(dict(id=sid, reason=f'file not found: {spec["file"]}'))
                continue
            index[sid] = dict(entry, file=spec['file'], seconds=round(sf.info(str(f)).duration, 3))
            continue
        key = f'{SFX_DIR}/{sid}.wav'
        try:
            layers = _layers(spec)
            if any(not (layer.get('voice') and layer.get('text')) for layer in layers):
                raise SfxError('every layer needs voice and text (or give file)')
            refs = [_refs(project, layer['voice'], tts_id) for layer in layers]
        except SfxError as e:
            if not only or sid in only:
                problems.append(dict(id=sid, reason=str(e)))
            continue
        inputs = digest({k: v for k, v in spec.items() if k not in ('name', 'aliases', 'min_gap')}, tts_id,
                        *[pathlib.Path(a) for r in refs for a, _ in r])
        index[sid] = dict(entry, file=key, seconds=(state.get(key) or {}).get('seconds'))
        if (not only or sid in only) and (force or not state.fresh(key, inputs, project.root / key)):
            todo.append((sid, spec, layers, refs, inputs))

    if todo:
        items = []
        for sid, spec, layers, refs, _ in todo:
            for i, (layer, r) in enumerate(zip(layers, refs)):
                for s in layer.get('seeds') or [11, 12]:
                    items.append(dict(id=f'{sid}_{i}_{s}', text=str(layer['text']), tone=layer.get('tone'),
                                      voice=layer['voice'], refs=r, seed=int(s), max_tokens=int(spec.get('max_tokens', 400))))
        got = backends.get(project, 'tts').synthesize(items, project.root / TAKES, on_line)     # 一次交给后端，模型只加载一次
        for sid, spec, layers, _, inputs in todo:
            parts = []
            for i, layer in enumerate(layers):
                max_len = float(layer.get('max_seconds', 3.0))
                takes = [project.root / TAKES / f'{sid}_{i}_{s}.wav' for s in layer.get('seeds') or [11, 12]
                         if f'{sid}_{i}_{s}' in got]
                if not takes:
                    break
                best = max(takes, key=lambda p: energy(p, max_len))           # 有的版本几乎没声音
                y = load_take(best, float(layer.get('pitch', 0)), max_len)
                parts.append((y / (np.abs(y).max() + 1e-6) * float(layer.get('gain', 1)), float(layer.get('at', 0))))
            if len(parts) < len(layers):
                problems.append(dict(id=sid, reason='the voice backend produced no audio'))
                continue
            n = max(len(y) + int(at * synth.SR) for y, at in parts)
            mix = np.zeros(n, np.float32)
            for y, at in parts:
                i = int(at * synth.SR)
                mix[i:i + len(y)] += y
            space = spec.get('space', 'dry')
            if space not in SPACES:
                problems.append(dict(id=sid, reason=f'unknown space "{space}" (choose from {", ".join(SPACES)})'))
                continue
            synth.seed(sid)
            y = synth.finish(SPACES[space](mix), float(spec.get('peak_db', -2)))
            state.set(f'{SFX_DIR}/{sid}.wav', inputs=inputs, seconds=_write(project.root / SFX_DIR / f'{sid}.wav', y))
            index[sid]['seconds'] = state.get(f'{SFX_DIR}/{sid}.wav')['seconds']
            done.append(sid)
    state.save()
    write_json(project.root / INDEX, index)
    return dict(done=done, problems=problems)


def summary(project):
    sounds = custom(project)
    files = {n: f'{SFX_DIR}/{n}.wav' for n in synth.SOUNDS if n not in sounds}
    files.update({k: v.get('file') or f'{SFX_DIR}/{k}.wav' for k, v in sounds.items()})
    return dict(total=len(files), custom=len(sounds), done=sum(1 for f in files.values() if (project.root / f).exists()))
