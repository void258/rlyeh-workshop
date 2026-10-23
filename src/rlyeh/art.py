"""美术：生图任务（提示词文件）→ 生成 → 表情差分合成 → 检查与总览图 → 人工审核。

规矩见 docs/zh/pipeline.md「美术」：
- 每张图一个提示词文件 art/prompts/<类别>/<名字>.md：文件头写类别、输出路径、底图和参考图，正文是提示词。
  AI 写、人可改，生成时原样交给生图后端（只去掉 <!-- 注释 -->，补上 [art] always_append）；
- 立绘直接出透明背景；表情差分拿基础立绘改图，只把脸部区域贴回基础图；
- 场景和 CG 要和定稿图一致时，把定稿图写进 refs；
- 不覆盖不是自己生成的图：输出路径上已经有图、又没有生成记录的，当作人工放进来的图收下。
"""
import pathlib
import re
import shutil
from dataclasses import dataclass, field

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.spatial import ConvexHull, QhullError

from . import backends
from .script.model import Directive
from .state import State, digest
from .util import now, read_json, slug, write_json

PROMPTS = 'art/prompts'
RAW = 'art/_raw'
OVERVIEW = 'art/_overview'
CHECK = 'build/art_check.json'
REVIEW = 'review/art-review.json'
KINDS = ('item', 'sprite', 'background', 'cg', 'expression')     # 生成顺序：被参考的先出
FOLDERS = {'sprite': 'sprites', 'expression': 'sprites', 'background': 'backgrounds', 'cg': 'cg', 'item': 'items'}
TRANSPARENT = {'sprite', 'expression', 'item'}
TODO = re.compile(r'<!--\s*TODO')
COMMENT = re.compile(r'<!--.*?-->', re.S)

TEXT = {
    'zh-CN': dict(
        character='角色：{name}，{appearance}',
        expression='表情：{desc}',
        sprite_frame=('构图：竖版，单人，膝盖以上的半身立绘，身体略微侧向画面一侧；头顶、手持物品和双手都完整在画面内，四周留少量空白；'
                      '平视角度，不要透视畸变。\n\n背景：完全透明的背景（PNG 透明通道），不要任何背景色、地面、投影或其他物体。'),
        sprite_tail='不要文字、水印、签名、边框；不要多余的手指或肢体；不要出现其他角色。',
        edit=('在这张图的基础上只修改表情，其余一律保持不变：脸型、发型、服装、配饰、手持物品、姿势、构图、画风、线条粗细、'
              '上色方式和透明背景都必须和原图完全一致；头部的角度、大小、位置不变，只改五官。\n\n新表情：{desc}'),
        edit_tail='不要文字、水印、签名、边框；不要改变画面尺寸和人物位置。',
        background='场景：{name}。',
        background_frame='构图：横版 16:9，视觉小说背景，画面里没有任何人物；画面下方三分之一保持简洁，留给对话框。',
        cg='事件 CG：{name}。',
        cg_frame='构图：横版 16:9，电影感镜头，视觉小说事件 CG。',
        item='道具：{name}。',
        item_frame='构图：单独一个物件居中摆放，略微俯视。\n\n背景：完全透明的背景（PNG 透明通道），不要任何背景色、地面或投影。',
        tail='不要文字、水印、签名、边框。',
        todo='<!-- TODO：{hint} -->',
        hint_appearance='写外貌、年龄、体型、发型、服装、配色（也可以写在 cast.yaml 的 appearance 里再重新生成任务）',
        hint_expression='写这个表情的样子',
        hint_background='写清楚地点、时间、光线、氛围、画面里有哪些东西',
        hint_cg='写清楚谁在做什么、角色造型（要和立绘一致）、镜头、光线；要和定稿图一致就把它的路径写进文件头的 refs',
        hint_item='写清楚材质、形状、颜色、特征',
        sep='；',
    ),
    'en': dict(
        character='Character: {name}, {appearance}',
        expression='Expression: {desc}',
        sprite_frame=('Composition: portrait orientation, a single character, knee-up half-body sprite, body turned slightly to one side; '
                      'the top of the head, held items and both hands fully inside the frame with a little margin; eye-level view, '
                      'no perspective distortion.\n\nBackground: fully transparent (PNG alpha channel); no background color, floor, '
                      'shadow or other objects.'),
        sprite_tail='no text, watermark, signature or border; no extra fingers or limbs; no other characters.',
        edit=('Edit this image and change only the facial expression; keep everything else exactly the same: face shape, hair, '
              'clothes, accessories, held items, pose, composition, art style, line weight, coloring and the transparent background. '
              'Keep the head angle, size and position; change only the facial features.\n\nNew expression: {desc}'),
        edit_tail='no text, watermark, signature or border; do not change the canvas size or the character position.',
        background='Location: {name}.',
        background_frame=('Composition: landscape 16:9, visual novel background, no people in the scene; keep the bottom third simple '
                          'for the dialogue box.'),
        cg='Event CG: {name}.',
        cg_frame='Composition: landscape 16:9, cinematic shot, visual novel event CG.',
        item='Item: {name}.',
        item_frame=('Composition: a single object centered, seen slightly from above.\n\nBackground: fully transparent (PNG alpha '
                    'channel); no background color, floor or shadow.'),
        tail='no text, watermark, signature or border.',
        todo='<!-- TODO: {hint} -->',
        hint_appearance='describe looks, age, build, hair, clothes and colors (or write appearance in cast.yaml and rerun art jobs)',
        hint_expression='describe this expression',
        hint_background='describe the place, time of day, light, mood and what is in the scene',
        hint_cg=('describe who does what, the characters as they look in their sprites, the shot and the light; to match a final '
                 'image, add its path to refs in the front matter'),
        hint_item='describe the material, shape, colors and distinctive features',
        sep='; ',
    ),
}


class ArtError(RuntimeError):
    pass


@dataclass
class Job:
    id: str                     # 提示词文件在 art/prompts 下的路径（不含 .md），例如 sprites/hero_pingjing
    kind: str                   # sprite | expression | background | cg | item
    name: str                   # 显示名：表情名，或剧本里写的场景 / CG / 道具名
    out: str                    # 输出图片（项目内相对路径）
    body: str = ''
    char: str | None = None
    base: str | None = None     # 表情差分的底图（基础立绘）
    refs: list = field(default_factory=list)
    transparent: bool = False
    skip: bool = False
    full_redraw: bool = False   # 差分整个人都变了（例如变成亡魂），不做脸部合成

    @property
    def needs_prompt(self):
        return bool(TODO.search(self.body))

    @property
    def raw(self):
        """改图的原始输出（合成之前）：art/_raw/sprites/<角色>/<文件>。"""
        return f'{RAW}/{self.out[len("art/"):]}' if self.out.startswith('art/') else f'{RAW}/{self.out}'

    def front(self):
        d = dict(kind=self.kind, name=self.name)
        if self.char:
            d['char'] = self.char
        d['out'] = self.out
        if self.base:
            d['base'] = self.base
        d['refs'] = list(self.refs)
        d['transparent'] = self.transparent
        return d


def _text(project):
    return TEXT['en' if project.lang.startswith('en') else 'zh-CN']


def _tail(project, tail):
    always = (project.config.get('art') or {}).get('always_append', '')
    return f'{always}{_text(project)["sep"]}{tail}' if always else tail


# ───────── 任务：该有哪些图 ─────────
def _script_names(project):
    """剧本里用到的背景、CG、道具名（按出现顺序去重）。"""
    found = {'background': {}, 'cg': {}, 'item': {}}
    key = {'bg': 'background', 'cg': 'cg', 'item': 'item'}
    for ch in project.chapters():
        for it in ch.items:
            if isinstance(it, Directive) and it.name in key and it.args and it.args[0].strip():
                found[key[it.name]].setdefault(it.args[0].strip(), None)
    return {k: list(v) for k, v in found.items()}


def wanted(project):
    """按 cast.yaml 和剧本推出该有哪些图，正文是起步用的提示词（缺的地方留 TODO 注释）。"""
    tx = _text(project)
    style = (project.config.get('art') or {}).get('style', '')
    lang = project.lang
    jobs = []
    for ch in project.characters.values():
        if ch.kind in ('narrator', 'gm'):
            continue
        exprs = list(ch.expressions.items()) or [('default', '')]
        default = ch.default_expression if ch.default_expression in ch.expressions else exprs[0][0]
        exprs.sort(key=lambda e: e[0] != default)
        name = ch.name(lang)
        base_out = None
        for i, (face, desc) in enumerate(exprs):
            stem = f'{ch.id}_{slug(face)}'
            out = f'art/sprites/{ch.id}/{stem}.png'
            desc = str(desc or '').strip() or tx['todo'].format(hint=tx['hint_expression'])
            if i == 0:
                appearance = ch.appearance.strip() or tx['todo'].format(hint=tx['hint_appearance'])
                body = [style, tx['character'].format(name=name, appearance=appearance), tx['expression'].format(desc=desc),
                        tx['sprite_frame'], _tail(project, tx['sprite_tail'])]
                jobs.append(Job(f'sprites/{stem}', 'sprite', face, out, char=ch.id, transparent=True,
                                body='\n\n'.join(p for p in body if p)))
                base_out = out
            else:
                body = [tx['edit'].format(desc=desc), _tail(project, tx['edit_tail'])]
                jobs.append(Job(f'sprites/{stem}', 'expression', face, out, char=ch.id, base=base_out, transparent=True,
                                body='\n\n'.join(body)))
    frames = {'background': 'background_frame', 'cg': 'cg_frame', 'item': 'item_frame'}
    for kind, names in _script_names(project).items():
        used = set()
        for nm in names:
            stem = slug(nm)
            while stem in used:
                stem += '-2'
            used.add(stem)
            folder = FOLDERS[kind]
            body = [style, tx[kind].format(name=nm) + tx['todo'].format(hint=tx['hint_' + kind]), tx[frames[kind]],
                    _tail(project, tx['tail'])]
            jobs.append(Job(f'{folder}/{stem}', kind, nm, f'art/{folder}/{stem}.png', transparent=kind in TRANSPARENT,
                            body='\n\n'.join(p for p in body if p)))
    return jobs


def _dump(job):
    front = yaml.safe_dump(job.front(), allow_unicode=True, sort_keys=False, default_flow_style=None).strip()
    return f'---\n{front}\n---\n\n{job.body.strip()}\n'


def scaffold(project):
    """给还没有提示词文件的图写一份起步用的提示词。已有的文件一律不动。返回 (新建的任务 ID, 已有的个数)。"""
    have = {j.id for j in load_jobs(project)}
    created = []
    for job in wanted(project):
        if job.id in have:
            continue
        path = project.root / PROMPTS / f'{job.id}.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump(job), encoding='utf-8')
        created.append(job.id)
    return created, len(have)


def load_jobs(project):
    """读 art/prompts 下的所有提示词文件。"""
    out = []
    base = project.root / PROMPTS
    for path in sorted(base.rglob('*.md')):
        text = path.read_text(encoding='utf-8')
        m = re.match(r'---\n(.*?)\n---\n?(.*)', text.replace('\r\n', '\n'), re.S)
        if not m:
            raise ArtError(f'{path}: missing front matter (---)')
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            raise ArtError(f'{path}: front matter is not valid YAML: {e}') from e
        jid = path.relative_to(base).with_suffix('').as_posix()
        kind = meta.get('kind')
        if kind not in FOLDERS:
            raise ArtError(f'{path}: kind must be one of {", ".join(FOLDERS)}')
        out.append(Job(jid, kind, str(meta.get('name') or jid), str(meta.get('out') or f'art/{jid}.png'), body=m.group(2),
                       char=meta.get('char'), base=meta.get('base'), refs=[str(r) for r in meta.get('refs') or []],
                       transparent=bool(meta.get('transparent', kind in TRANSPARENT)), skip=bool(meta.get('skip')),
                       full_redraw=bool(meta.get('full_redraw'))))
    return out


def prompt(project, job):
    """真正发给生图后端的提示词：去掉注释，补上 always_append。"""
    text = re.sub(r'\n{3,}', '\n\n', COMMENT.sub('', job.body)).strip()
    always = (project.config.get('art') or {}).get('always_append', '')
    if always and always not in text:
        text += '\n\n' + always
    return text


def _inputs(project, job):
    files = [pathlib.Path(project.root / p) for p in [job.base, *job.refs] if p]
    return digest(prompt(project, job), job.transparent, *files)


# ───────── 生成 ─────────
def _select(jobs, ids, kinds):
    return [j for j in jobs if (not ids or j.id in ids or j.out in ids) and (not kinds or j.kind in kinds)]


def marked(project):
    return sorted(k for k, v in read_json(project.root / REVIEW, {}).items() if v.get('status') == 'redo')


def _backup(project, out):
    """覆盖之前把旧图留一份到 art/_raw/history/，重画的不一定比原来的好。"""
    src = project.root / out
    if not src.exists():
        return
    stem = out[len('art/'):] if out.startswith('art/') else out
    for n in range(1, 1000):
        dst = project.root / RAW / 'history' / f'{stem[:-4]}.{n}{src.suffix}'
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
            return


def run(project, ids=None, kinds=None, force=False, only_marked=False, limit=0, on_line=None):
    """生成没生成过或过期的图。按 KINDS 的顺序一类一类来：底图、参考图先出，后面的任务按新的底图算是否过期。

    返回 dict(done, adopted, waiting, blocked)：adopted 是人工放进来、收下的图；waiting 是手动后端还在等人放进来的图；
    blocked 是还不能生成的任务和原因。
    """
    backend = backends.get(project, 'image')
    state = State(project.root)
    reviews = read_json(project.root / REVIEW, {})
    redo = set(marked(project)) if only_marked else None
    res = dict(done=[], adopted=[], waiting=[], blocked=[])
    count = 0
    jobs = _select(load_jobs(project), ids, kinds)

    def record(job, inputs, by):
        state.set(job.out, inputs=inputs, file=digest(project.root / job.out), backend=by, at=now())
        if job.out in reviews and by != 'adopted':
            reviews[job.out] = dict(reviews[job.out], status='pending', at=now())
            write_json(project.root / REVIEW, reviews)
        state.save()                       # 每张图都存一次：生图又慢又花钱，中途出错也不丢进度

    for kind in KINDS:
        for job in [j for j in jobs if j.kind == kind]:
            if job.skip or (redo is not None and job.out not in redo):
                continue
            if job.needs_prompt:
                res['blocked'].append(dict(id=job.id, reason='prompt has TODO'))
                continue
            missing = [p for p in [job.base, *job.refs] if p and not (project.root / p).exists()]
            if missing and backend.writes:                     # 手动后端不用底图和参考图，照样等人放图
                res['blocked'].append(dict(id=job.id, reason='missing ' + ', '.join(missing)))
                continue
            inputs = _inputs(project, job)
            path = project.root / job.out
            rec = state.get(job.out)
            if not force and redo is None:
                if path.exists() and rec is None:              # 人工放进来的图：收下，不覆盖
                    record(job, inputs, 'adopted')
                    res['adopted'].append(job.id)
                    continue
                if state.fresh(job.out, inputs, path):
                    continue
            if not backend.writes:                             # 手动：等人放进新图（文件内容变了就算放好了）
                if path.exists() and (rec is None or rec.get('file') != digest(path)):
                    record(job, inputs, backend.info.id)
                    res['done'].append(job.id)
                else:
                    res['waiting'].append(dict(id=job.id, out=job.out))
                continue
            if limit and count >= limit:
                break
            compose_after = kind == 'expression' and not job.full_redraw and backend.edits
            target = project.root / (job.raw if compose_after else job.out)
            _backup(project, job.out)
            req = dict(id=job.id, kind=kind, name=job.name, prompt=prompt(project, job), transparent=job.transparent,
                       base=project.root / job.base if job.base else None, refs=[project.root / r for r in job.refs])
            if on_line:
                on_line(f'{job.id} → {job.out}')
            backend.generate(req, target, on_line)
            count += 1
            if compose_after:
                compose(project.root / job.base, target, path)
            record(job, inputs, backend.info.id)
            res['done'].append(job.id)
    state.save()
    return res


# ───────── 表情差分合成 ─────────
INSET = 10      # 只换头部轮廓往里这么多像素以内的区域，头发外缘沿用基础图
GROW = 28       # 变化区域往外扩
FEATHER = 9     # 羽化半径
REACH = 170     # 离脸中心这么远以内的变化块都算脸部


def _load(path):
    return np.asarray(Image.open(path).convert('RGBA')).astype(np.float32) / 255


def _hull(xs, ys, shape):
    im = Image.new('L', (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(im)
    pts = np.column_stack([xs, ys]).astype(np.float64)
    try:
        hull = ConvexHull(pts)
        draw.polygon([tuple(pts[i]) for i in hull.vertices], fill=1)
    except (QhullError, ValueError):                # 点太少或共线：退回外接矩形
        draw.rectangle([int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())], fill=1)
    return np.asarray(im).astype(bool)


def compose(base_path, var_path, out_path):
    """以基础立绘为底，只把差分里脸部变化的那一块贴上去，返回替换面积占画面的比例。

    改图输出的透明通道分辨率低（边缘一格一格、背景蒙着半透明雾），而基础立绘的是平滑的。差分只改了表情，
    所以身体、轮廓、透明通道全部沿用基础图，只把「头部轮廓以内、和基础图差别明显」的区域换成差分的像素，边缘羽化。
    """
    base, var = _load(base_path), _load(var_path)
    if base.shape != var.shape:
        im = Image.fromarray((var * 255).astype(np.uint8), 'RGBA').resize(base.shape[1::-1], Image.LANCZOS)
        var = np.asarray(im).astype(np.float32) / 255
    ba = base[..., 3]
    inner = ndimage.distance_transform_edt(ba > .5) > INSET
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 基础图叠在灰底上和差分比颜色（差分的透明通道不可信，只看颜色）
    bc = base[..., :3] * ba[..., None] + .5 * (1 - ba[..., None])
    vc = var[..., :3]
    diff = ndimage.gaussian_filter(np.abs(bc - vc).mean(axis=2) * inner, 6)
    h = diff.shape[0]
    top = np.zeros_like(diff)
    top[:int(h * .55)] = diff[:int(h * .55)]                      # 表情只会出现在上半身
    if not inner.any():
        Image.fromarray((base * 255).astype(np.uint8), 'RGBA').save(out_path)
        return 0.0
    thr = max(.06, float(np.percentile(top[inner], 97)) * .6)
    mask = top > thr
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        Image.fromarray((base * 255).astype(np.uint8), 'RGBA').save(out_path)
        return 0.0
    # 最大的一块是脸的中心；眉、眼、嘴常常是分开的几块，把离它不远的变化块都算进来，再取凸包
    areas = np.bincount(lab.ravel())[1:]
    cents = np.array(ndimage.center_of_mass(mask, lab, range(1, n + 1)))
    main = int(np.argmax(areas))
    pick = [i + 1 for i in range(n) if areas[i] >= areas[main] * .05 and np.hypot(*(cents[i] - cents[main])) < REACH]
    ys, xs = np.nonzero(np.isin(lab, pick))
    region = _hull(xs, ys, mask.shape)
    region = (ndimage.distance_transform_edt(~region) <= GROW) & inner
    w = ndimage.gaussian_filter(region.astype(np.float32), FEATHER) * inner
    out = base.copy()
    out[..., :3] = base[..., :3] * (1 - w[..., None]) + vc * w[..., None]
    Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8), 'RGBA').save(out_path)
    return float(region.mean())


def compose_all(project, ids=None):
    """把 art/_raw 里的差分原图重新合成一遍（例如手动放进原图、或者调了底图之后）。返回 {任务 ID: 替换比例}。"""
    done = {}
    for job in _select(load_jobs(project), ids, {'expression'}):
        raw, base = project.root / job.raw, project.root / (job.base or '')
        if job.full_redraw or not job.base or not raw.exists() or not base.is_file():
            continue
        done[job.id] = round(compose(base, raw, project.root / job.out), 4)
    return done


# ───────── 检查与总览图 ─────────
FONTS = ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf', '/System/Library/Fonts/PingFang.ttc',
         '/System/Library/Fonts/STHeiti Medium.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
         '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc', '/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc']


def _font(size):
    for f in FONTS:
        if pathlib.Path(f).exists():
            return ImageFont.truetype(f, size), True
    return ImageFont.load_default(size), False


def inspect(project, job):
    """一张图的检查结果：status 是 missing / ok / warn，warn 时 notes 写原因。"""
    path = project.root / job.out
    if not path.exists():
        return dict(status='missing')
    with Image.open(path) as im:
        rec = dict(status='ok', size=list(im.size), mode=im.mode, notes=[])
        if job.transparent:
            if 'A' not in im.getbands():
                rec['notes'].append('no alpha channel')
            else:
                a = np.asarray(im.convert('RGBA'))[..., 3]
                border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
                rec['clear'] = round(float((a < 8).mean()), 3)
                rec['clear_border'] = round(float((border < 8).mean()), 3)
                if rec['clear'] < .15:
                    rec['notes'].append('background does not look transparent')
    if rec['notes']:
        rec['status'] = 'warn'
    return rec


def _checker(size, cell=24):
    w, h = size
    y, x = np.mgrid[0:h, 0:w]
    v = np.where(((x // cell) + (y // cell)) % 2, 70, 52).astype(np.uint8)
    return Image.fromarray(np.dstack([v, v, v, np.full_like(v, 255)]), 'RGBA')


def sheet(path, items, height):
    """总览图：一排缩略图（透明的铺在棋盘格上），下面写名字。"""
    font, cjk = _font(26)
    thumbs = []
    for label, ascii_label, file in items:
        with Image.open(file) as im:
            im = im.convert('RGBA')
            im = im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
        bg = _checker(im.size)
        bg.alpha_composite(im)
        thumbs.append((label if cjk else ascii_label, bg))
    w = sum(t.width for _, t in thumbs) + 20 * (len(thumbs) + 1)
    canvas = Image.new('RGB', (w, height + 70), (24, 21, 18))
    d = ImageDraw.Draw(canvas)
    x = 20
    for label, t in thumbs:
        canvas.paste(t.convert('RGB'), (x, 20))
        d.text((x + 6, height + 28), label, fill=(230, 220, 205), font=font)
        x += t.width + 20
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def check(project):
    """检查每张图（有没有、尺寸、透明背景是不是真透明），写 build/art_check.json，再拼总览图到 art/_overview/。"""
    report, groups = {}, {}
    for job in load_jobs(project):
        if job.skip:
            continue
        rec = dict(id=job.id, kind=job.kind, name=job.name, **inspect(project, job))
        if rec['status'] == 'missing' and job.needs_prompt:
            rec['status'] = 'needs_prompt'
        report[job.out] = rec
        if rec['status'] in ('ok', 'warn'):
            group = f'sprites_{job.char}' if job.kind in ('sprite', 'expression') else FOLDERS[job.kind]
            groups.setdefault(group, []).append((job.name, pathlib.Path(job.out).stem, project.root / job.out))
    write_json(project.root / CHECK, report)
    sheets = []
    for g, items in groups.items():
        path = project.root / OVERVIEW / f'{g}.png'
        sheet(path, items, 300 if g in ('backgrounds', 'cg') else 520)
        sheets.append(path.relative_to(project.root).as_posix())
    return report, sheets


# ───────── 汇总 ─────────
def summary(project):
    state = State(project.root)
    reviews = read_json(project.root / REVIEW, {})
    jobs = [j for j in load_jobs(project) if not j.skip]
    have = {j.id for j in load_jobs(project)}
    out = dict(jobs=len(jobs), done=0, stale=0, todo=0, needs_prompt=0, approved=0, redo=0,
               unplanned=sum(1 for j in wanted(project) if j.id not in have))
    for j in jobs:
        rec = state.get(j.out)
        exists = (project.root / j.out).exists()
        if j.needs_prompt:
            out['needs_prompt'] += 1
        elif exists and (rec is None or rec.get('inputs') == _inputs(project, j)):
            out['done'] += 1
        elif exists:
            out['stale'] += 1
        else:
            out['todo'] += 1
        st = (reviews.get(j.out) or {}).get('status')
        out['approved'] += st == 'approved'
        out['redo'] += st == 'redo'
    return out
