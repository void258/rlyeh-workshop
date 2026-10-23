"""播放器：把剧本、配音、美术、音乐、音效打包成 build/player/，浏览器打开 index.html 就能播。

  replay build        → build/player/：index.html、player.js、player.css、data.js、img/、audio/
图片转成 WebP；音频用硬链接（同一个盘）或复制；只处理有变化的文件。replay preview 的 /player 直接打开它。
剧本里的指令换成英文规范名和规范值（【背景：雾港｜夜】→ bg ['雾港', 'night']），角色名换成角色 ID。
"""
import json
import os
import shutil
from importlib import resources

import soundfile as sf
from PIL import Image

from .. import art, backends, music, sfx, voice
from ..script import directives
from ..script.model import Directive, Scene, Spoken
from ..state import State
from ..util import read_json, slug
from . import theme as themes

OUT = 'build/player'
STATIC = resources.files('rlyeh') / 'player' / 'static'
GM_COLOR = '#9b8cff'
# 内置音效的音量（相对）；项目自己的音效在 sfx.yaml 里写 gain，默认 0.7
SFX_GAIN = {'dice_roll': .75, 'dice_good': .5, 'dice_bad': .5, 'dice_crit': .8, 'dice_fumble': .7, 'hit_blunt': .85, 'hit_slash': .8,
            'hit_heavy': .9, 'miss': .6, 'sling': .6, 'burn': .7, 'fire_breath': .85, 'flames': .65, 'ghost': .6, 'dash': .7,
            'door_break': .9, 'door_bang': .5, 'rumble': .7, 'flash': .6, 'dawn': .55, 'battle_start': .9, 'gong': .55,
            'battle_end': .7, 'clash': .8, 'item': .6, 'chapter': .75, 'scene': .35, 'cg': .7}
# 伤害音效：按前一次掷骰的技能名挑打击声，先中先用；都不中是重击（被怪物打）。replay.toml 的 [player] hit_sounds 可以改
HIT_SOUNDS = [['hit_slash', '匕首|剑|刀|斧|爪|sword|dagger|blade|axe|claw'], ['hit_heavy', '镐|锤|hammer|pick|maul'],
              ['burn', '火|焰|fire|flame|burn'], ['hit_blunt', '棒|杖|棍|投石|拳|club|staff|sling|mace|fist|punch']]
CREDITS = {
    'zh-CN': dict(gm='主持', players='玩家', cast='登场人物', art='美术', voice_design='声线设计', voice='配音', music='音乐',
                  sfx='音效', source='原始记录', synth='程序合成', end='完', chapter='第 {n} 章', chat='聊天记录'),
    'en': dict(gm='Game Master', players='Players', cast='Characters', art='Art', voice_design='Voice design', voice='Voices',
               music='Music', sfx='Sound effects', source='Session logs', synth='Synthesized', end='Fin', chapter='Chapter {n}',
               chat='Chat log'),
}


# ───────── 文件 ─────────
def _webp(src, dst, crop=None, size=None, quality=88):
    """源图比目标新才重新转。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        with Image.open(src) as im:
            if crop:
                im = im.convert('RGBA').crop(crop)
            if size:
                im = im.resize(size, Image.LANCZOS)
            im.save(dst, 'WEBP', quality=quality, method=4)


def _sync(src, dst):
    """音频：同一个盘上用硬链接，不行就复制；已经是同一个文件、或者大小和时间都一样就不动。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        a, b = src.stat(), dst.stat()
        if os.path.samefile(src, dst) or (a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)):
            return
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _prune(root, keep):
    """删掉 img/、audio/ 里这次没用到的旧文件（改名、删掉的素材）。"""
    for sub in ('img', 'audio'):
        base = root / sub
        if not base.exists():
            continue
        for f in base.rglob('*'):
            if f.is_file() and f.relative_to(root).as_posix() not in keep:
                f.unlink()


# ───────── 角色和素材 ─────────
def _chars(project, out, keep):
    """角色：显示名、名牌颜色、立绘各表情（WebP）、头像、头和嘴的位置。"""
    lang = project.lang
    faces_of = {}
    for job in art.load_jobs(project):
        if job.kind in ('sprite', 'expression') and job.char and (project.root / job.out).exists():
            faces_of.setdefault(job.char, {})[job.name] = project.root / job.out
    chars, who = {}, {}
    for ch in project.characters.values():
        sp = ch.sprite or {}
        faces = {}
        for face, src in faces_of.get(ch.id, {}).items():
            rel = f'img/sprites/{ch.id}/{src.stem}.webp'
            _webp(src, out / rel)
            keep.add(rel)
            faces[face] = rel
        default = ch.default_expression if ch.default_expression in faces else next(iter(faces), None)
        entry = dict(name=ch.name(lang), color=ch.color or ('#9b8cff' if ch.kind == 'gm' else '#888888'), kind=ch.kind,
                     scale=float(sp.get('scale', 1)), faces=faces, default=default, player=ch.player,
                     head=list(sp.get('head', [.5, .15]))[:2], mouth=list(sp['mouth'])[:2] if sp.get('mouth') else None,
                     state_faces=sp.get('state_faces') or {})
        if default:
            src = faces_of[ch.id][default]
            cx, cy, *rest = list(sp.get('head', [.5, .15]))
            with Image.open(src) as im:
                w, h = im.size
            half = int(w * (rest[0] if rest else .17))
            rel = f'img/avatars/{ch.id}.webp'
            x, y = int(w * cx), int(h * cy)
            _webp(src, out / rel, crop=(x - half, y - half, x + half, y + half), size=(256, 256), quality=90)
            keep.add(rel)
            entry['avatar'] = rel
        chars[ch.id] = entry
        for n in ch.names.values():
            who[n] = ch.id
    return chars, who


def _images(project, out, keep, kind):
    """背景、CG、道具：剧本里的名字 → WebP。先按提示词文件找，找不到再按名字的拼音找。"""
    folder = art.FOLDERS[kind]
    found = {job.name: project.root / job.out for job in art.load_jobs(project)
             if job.kind == kind and (project.root / job.out).exists()}
    used = {f.resolve() for f in found.values()}
    for f in sorted((project.root / 'art' / folder).glob('*.png')) if (project.root / 'art' / folder).exists() else []:
        if f.resolve() not in used:                          # 没有提示词文件、自己放进来的图：按文件名找
            found.setdefault(f.stem, f)
    out_map = {}
    for name, src in found.items():
        rel = f'img/{folder}/{src.stem}.webp'
        _webp(src, out / rel, quality=90)
        keep.add(rel)
        out_map[name] = rel
    return out_map


def _lookup(table, name):
    return name if name in table else next((k for k in table if slug(k) == slug(name)), None)


# ───────── 剧本 ─────────
def _args(project, d, who):
    """指令参数：枚举换成规范值，角色名换成角色 ID。"""
    spec = directives.BY_NAME.get(d.name)
    out = []
    for i, a in enumerate(d.args):
        a = a.strip()
        p = spec.params[min(i, len(spec.params) - 1)] if spec and spec.params else None
        if p and p.kind in directives.ENUMS:
            a = directives.canonical(p.kind, a) or a
        elif p and (p.kind == 'char' or p.name == 'target'):
            a = who.get(a, a)
        out.append(a)
    return out


def _steps(project, ch, data, report):
    state = State(project.root)
    steps = []
    for it in ch.items:
        if isinstance(it, Scene):
            steps.append(dict(k='scene', title=it.title))
        elif isinstance(it, Directive):
            if not it.known:
                report['unknown'].append(f'{it.written} ({ch.path}:{it.line_no})')
                continue
            args = _args(project, it, data['who'])
            name = it.name
            if name in ('bg', 'cg', 'item') and args:
                table = data[{'bg': 'bg', 'cg': 'cg', 'item': 'items'}[name]]
                hit = _lookup(table, args[0])
                if hit is None:
                    report['images'].append(f'{name}: {args[0]}')
                else:
                    args[0] = hit
            elif name == 'sfx' and args:
                sid = sfx.resolve(project, args[0])
                if sid is None or sid not in data['sfx']:
                    report['sfx'].append(args[0])
                args[0] = sid or args[0]
            elif name == 'bgm':
                cue = music.resolve(project, args[0]) if args and args[0] else None
                if args and args[0] and (cue is None or cue not in data['bgm']):
                    report['bgm'].append(args[0])
                args = [cue or args[0]] if args and args[0] else []
            steps.append(dict(k='do', name=name, args=args))
        elif isinstance(it, Spoken):
            k = {'narration': 'nar', 'line': 'line', 'ooc': 'ooc'}[it.kind]
            s = dict(k=k, id=it.id, who=it.speaker, tone=it.tone, rich=[list(x) for x in it.segments])
            if k == 'line':
                c = project.character(it.speaker)
                if c:
                    s['who'] = c.id
                    s['face'] = c.pick_face(it.face, it.tone)
                elif it.face:
                    s['face'] = it.face
            if it.voiced:
                plain = project.root / voice.VOICE_DIR / f'{it.id}.wav'
                bleeped = project.root / voice.BLEEP_DIR / f'{it.id}.wav'
                if plain.exists():
                    src = bleeped if bleeped.exists() else plain
                    rel = src.relative_to(project.root).as_posix()
                    data['_audio'].add(rel)
                    s['voice'] = rel
                    rec = state.get(f'{voice.VOICE_DIR}/{it.id}.wav') or {}
                    s['sec'] = rec.get('seconds') or round(sf.info(str(src)).duration, 3)
                else:
                    report['voice'].append(it.id)
            steps.append(s)
    return steps


# ───────── 片尾、标题画面 ─────────
def _used_backend(project, kind):
    """项目实际用到的后端（片尾署名用）：生图看生成记录，配音、音乐看有没有产物。"""
    table = project.config.get('backends') or {}
    if kind == 'image':
        ids = {(rec or {}).get('backend') for key, rec in State(project.root).artifacts.items() if key.startswith('art/')}
        return [i for i in ids if i]
    if kind == 'music':
        return list({t.get('backend') for t in music.takes(project).values() if t.get('backend')})
    name = table.get(kind) or backends.DEFAULTS.get(kind)
    return [name] if name else []


def _info(kind, bid):
    try:
        return backends._registry()[kind][bid].info
    except KeyError:
        return None


def credits(project, data):
    tx = CREDITS['en' if project.lang.startswith('en') else 'zh-CN']
    cfg = project.config.get('credits') or {}
    sections = []
    gms = [n for n, v in (project.config.get('players') or {}).items() if isinstance(v, dict) and v.get('role') == 'gm']
    if gms:
        sections.append(dict(h=tx['gm'], items=[[n, ''] for n in gms]))
    pcs = [[n, data['chars'].get(cid, {}).get('name', cid)] for n, cid in project.players.items() if cid]
    if pcs:
        sections.append(dict(h=tx['players'], items=pcs))
    npcs = [c['name'] for c in data['chars'].values() if c['kind'] == 'npc']
    if npcs:
        sections.append(dict(h=tx['cast'], items=[[' · '.join(npcs[i:i + 3]), ''] for i in range(0, len(npcs), 3)]))
    for row in cfg.get('staff') or []:                       # 额外的栏目：[标题, 名字, 名字…]
        sections.append(dict(h=str(row[0]), items=[[str(n), ''] for n in row[1:]]))

    def add(heading, kind):
        items = []
        for bid in _used_backend(project, kind):
            info = _info(kind, bid)
            if info and info.credit:
                items.append([info.credit, info.license if 'NC' in (info.license or '') else ''])
                if info.attribution and kind != 'music':
                    items.append([info.attribution, ''])
        if items:
            sections.append(dict(h=heading, items=items))

    add(tx['art'], 'image')
    if (project.root / 'voices' / 'candidates.json').exists():
        add(tx['voice_design'], 'voice_design')
    if any(s.get('voice') for ch in data['chapters'] for s in ch['steps']):
        add(tx['voice'], 'tts')
    add(tx['music'], 'music')
    vocal = any(not v.get('file') for v in sfx.custom(project).values())
    tts = _info('tts', _used_backend(project, 'tts')[0]) if vocal and _used_backend(project, 'tts') else None
    sections.append(dict(h=tx['sfx'], items=[[tx['synth'] + (f' · {tts.credit}' if tts and tts.credit else ''), '']]))
    p = project.config.get('project') or {}
    imp = (project.config.get('backends') or {}).get('import')
    if (project.root / 'logs' / 'events.jsonl').exists() or p.get('session_dates'):
        source = {'fvtt': 'Foundry VTT'}.get(imp) or tx['chat']
        sections.append(dict(h=tx['source'], items=[[source, ' / '.join(p.get('session_dates') or [])]]))
    bg = cfg.get('background')
    if not bg:
        bgs = [s['args'][0] for ch in data['chapters'] for s in ch['steps'] if s.get('name') == 'bg' and s['args']]
        bg = bgs[-1] if bgs else None
    return dict(sections=sections, end=str(cfg.get('end') or tx['end']), bg=bg)


def _title_screen(project, data):
    cfg = project.config.get('player') or {}
    first = next((s['args'] for ch in data['chapters'] for s in ch['steps'] if s.get('name') == 'bg' and s['args']), None)
    bg = cfg.get('title_bg') or (first[0] if first else None)
    variants = cfg.get('title_variants') or (first[1:] if first and bg == first[0] else [])
    variants = [directives.canonical('variant', v) or v for v in variants]
    cue = cfg.get('title_bgm') or ('title' if 'title' in data['bgm'] else next(iter(data['bgm']), None))
    return dict(bg=_lookup(data['bg'], bg) if bg else None, variants=variants, bgm=music.resolve(project, cue) if cue else None)


def _foot(project, data):
    names = list((project.config.get('players') or {}).keys())
    parts = ['　'.join(names)] if names else []
    tts = _used_backend(project, 'tts')
    info = _info('tts', tts[0]) if tts and any(s.get('voice') for ch in data['chapters'] for s in ch['steps']) else None
    if info and info.credit:
        parts.append(' · '.join(x for x in [info.credit, info.attribution] if x))
    return '　　|　　'.join(parts)


# ───────── 打包 ─────────
def build(project, on_line=None, theme=None):
    """写 build/player/。返回 dict(path, chapters, steps, missing, theme, warnings)：missing 里是缺的配音、图片、音效、曲子和
    不认识的指令；theme 指定时用这个主题（不写就用 [player] theme）。"""
    out = project.root / OUT
    out.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'player.js', 'player.css'):
        (out / name).write_bytes((STATIC / name).read_bytes())
    theme_info, warnings = themes.write(project, out, theme)
    keep = set()
    chars, who = _chars(project, out, keep)
    data = dict(id=(project.config.get('project') or {}).get('id', 'replay'), lang=project.lang, chars=chars, who=who,
                bg=_images(project, out, keep, 'background'), cg=_images(project, out, keep, 'cg'),
                items=_images(project, out, keep, 'item'), _audio=set())
    players = {}
    for name, cid in project.players.items():
        c = chars.get(cid) if cid else None
        players[name] = dict(char=cid, gm=cid is None, color=c['color'] if c else GM_COLOR, avatar=c.get('avatar') if c else None)
    data['players'] = players

    index = read_json(project.root / sfx.INDEX, {})
    customs = sfx.custom(project)
    data['sfx'] = {}
    for sid, e in index.items():
        if (project.root / e['file']).exists():
            spec = customs.get(sid, {})
            data['sfx'][sid] = dict(src=e['file'], gain=float(spec.get('gain', SFX_GAIN.get(sid, .7))),
                                    min_gap=float(e.get('min_gap') or 0), ambient=spec.get('ambient'))
            data['_audio'].add(e['file'])
    data['bgm'] = {}
    for cid in music.cues(project):
        f = music.final(project, cid)
        if f:
            rel = f.relative_to(project.root).as_posix()
            data['bgm'][cid] = rel
            data['_audio'].add(rel)
    data['battle'] = music.battle_cue(project)

    report = dict(voice=[], images=[], sfx=[], bgm=[], unknown=[])
    if not index:
        report['sfx'].append('(audio/sfx/index.json missing: run replay sfx)')
    tx = CREDITS['en' if project.lang.startswith('en') else 'zh-CN']
    data['chapters'] = []
    for ch in project.chapters():
        steps = _steps(project, ch, data, report)
        first = next((s['args'][0] for s in steps if s.get('name') == 'chapter' and s['args']), None)
        label = first or ' '.join(x for x in [tx['chapter'].format(n=ch.number), ch.title] if x)
        data['chapters'].append(dict(title=ch.title, label=label, steps=steps))
    p = project.config.get('project') or {}
    cfg = project.config.get('player') or {}
    dates = p.get('session_dates') or []
    span = ' — '.join(str(d).replace('-', '.') for d in ([dates[0], dates[-1]] if len(dates) > 1 else dates))
    tag = theme_info['text'].get('replayTag', 'TRPG REPLAY')
    data.update(title=p.get('title', ''), subtitle=p.get('subtitle', ''), die=int(cfg.get('die', 20)), theme=theme_info,
                kicker=' · '.join(x for x in [tag, span] if x), hit_sounds=cfg.get('hit_sounds') or HIT_SOUNDS)
    data['credits'] = credits(project, data)
    data['title_screen'] = _title_screen(project, data)
    data['foot'] = _foot(project, data)
    for rel in data.pop('_audio'):
        _sync(project.root / rel, out / rel)
        keep.add(rel)
    _prune(out, keep)
    (out / 'data.js').write_text('window.REPLAY = ' + json.dumps(data, ensure_ascii=False) + ';\n', encoding='utf-8')
    for k in report:
        report[k] = sorted(set(report[k]))
    return dict(path=OUT, chapters=len(data['chapters']), steps=sum(len(c['steps']) for c in data['chapters']), missing=report,
                theme=theme_info['id'], warnings=warnings)


def data(project, name='data'):
    """读回 build/player/data.js（或 showcase.js）。"""
    text = (project.root / OUT / f'{name}.js').read_text(encoding='utf-8')
    return json.loads(text[len('window.REPLAY = '):].rstrip().rstrip(';'))


# ───────── 主题预览用的样板戏 ─────────
SAMPLE = {
    'zh-CN': dict(chapter='第一章　主题预览', scene='第一幕　样式一览', nar='这是一句旁白：看看字体、字号、颜色和对话框的样子。',
                  line_a='这是{a}的台词，名牌用的是角色的颜色。', act='（拍了拍桌子）', line_b1='消音词会这样显示：', line_b2='，懂了吧。',
                  ooc_pl='场外弹幕在右边，像直播聊天栏。', ooc_gm='GM 的弹幕颜色不一样。', skill_a='察觉', skill_b='攻击',
                  stat_a='力量', stat_b='敏捷', win='{a}胜', item='铜钥匙', round='第二轮', tone_a='自信', tone_b='调侃'),
    'en': dict(chapter='Chapter 1 Theme preview', scene='Scene 1 Style sheet', nar='This is narration: check the fonts, size, colors and the box.',
               line_a="This is {a} speaking; the nameplate uses the character's color.", act='*taps the table*',
               line_b1='Bleeped words look like this: ', line_b2=', got it?', ooc_pl='OOC chat sits on the right, like a stream chat.',
               ooc_gm='GM messages look different.', skill_a='Perception', skill_b='Attack', stat_a='STR', stat_b='DEX',
               win='{a} wins', item='Brass key', round='Round 2', tone_a='confident', tone_b='teasing'),
}


def write_showcase(project):
    """用项目里的角色、背景、道具拼一段样板戏，写 build/player/showcase.js：每种界面元素都出场一次，主题预览截图用。"""
    d = data(project)
    sm = SAMPLE['en' if project.lang.startswith('en') else 'zh-CN']
    chars = [cid for cid, c in d['chars'].items() if c['faces'] and c['kind'] == 'pc'] or \
            [cid for cid, c in d['chars'].items() if c['faces']]
    a = chars[0] if chars else next(iter(d['chars']), 'a')
    b = chars[1] if len(chars) > 1 else a
    name = lambda cid: d['chars'].get(cid, {}).get('name', cid)   # noqa: E731
    pl = next((n for n, x in d['players'].items() if not x['gm']), 'Player')
    gm = next((n for n, x in d['players'].items() if x['gm']), 'GM')
    item = next(iter(d['items']), sm['item'])
    steps = [dict(k='do', name='chapter', args=[sm['chapter']]), dict(k='scene', title=sm['scene'])]
    if d['bg']:
        bg = d['title_screen'].get('bg') or next(iter(d['bg']))
        steps.append(dict(k='do', name='bg', args=[bg, *d['title_screen'].get('variants', [])]))
    steps += [
        dict(k='nar', id='s-01', who='', tone=None, rich=[['t', sm['nar']]]),
        dict(k='line', id='s-02', who=a, tone=sm['tone_a'], face=None, rich=[['t', sm['line_a'].format(a=name(a))], ['a', sm['act']]]),
        dict(k='line', id='s-03', who=b, tone=sm['tone_b'], face=None, rich=[['t', sm['line_b1']], ['b', 'tmd'], ['t', sm['line_b2']]]),
        dict(k='ooc', id='s-04', who=pl, tone=None, rich=[['t', sm['ooc_pl']]]),
        dict(k='ooc', id='s-05', who=gm, tone=None, rich=[['t', sm['ooc_gm']]]),
        dict(k='do', name='roll', args=[a, sm['skill_a'], '17', 'success']),
        dict(k='do', name='roll', args=[b, sm['skill_b'], '20', 'critical']),
        dict(k='do', name='battle-start', args=[]),
        dict(k='do', name='damage', args=[a, '5']),
        dict(k='do', name='contest', args=[f'{name(a)} {sm["stat_a"]} 15', f'{name(b)} {sm["stat_b"]} 12', sm['win'].format(a=name(a))]),
        dict(k='do', name='item', args=[item]),
        dict(k='do', name='round', args=[sm['round']]),
        dict(k='do', name='battle-end', args=[]),
        dict(k='do', name='chapter-end', args=[]),
        dict(k='do', name='credits', args=[]),
    ]
    show = dict(d, chapters=[dict(title=sm['chapter'], label=sm['chapter'], steps=steps)], battle=None)
    (project.root / OUT / 'showcase.js').write_text('window.REPLAY = ' + json.dumps(show, ensure_ascii=False) + ';\n', encoding='utf-8')
    return steps
