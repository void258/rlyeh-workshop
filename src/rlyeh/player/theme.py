"""播放器主题：每个团可以有自己的界面风格，由 AI 按团的气质设计，人可以改。

主题是一个文件夹：
  theme.toml   name、description、base（基于哪个主题），[vars] 设计变量，[text] 界面文字，[fonts] 字体文件，[images] 图片
  theme.css    可选：任意额外的样式，在设计变量之后载入，可以改任何元素
  其余文件     字体、图片、纹理，theme.css 里用相对路径引用
内置主题在 rlyeh/player/themes/ 下；项目自己的主题放在项目文件夹里（例如 theme/），replay.toml 写 [player] theme = "theme"。
设计变量的完整列表、默认值和说明就是 player.css 开头的 :root，tokens() 直接读它。
"""
import pathlib
import re
import shutil
import tomllib
from importlib import resources

BUILTIN = pathlib.Path(str(resources.files('rlyeh') / 'player' / 'themes'))
CSS = pathlib.Path(str(resources.files('rlyeh') / 'player' / 'static' / 'player.css'))
DEFAULT = 'dark-fantasy'
TOKEN = re.compile(r'^\s*--([a-z0-9-]+):\s*(.+?);\s*/\*\s*(.+?)\s*\|\s*(.+?)\s*\*/\s*$')
OWN = ('theme.toml', 'theme.css')
LANGS = ('zh-CN', 'en')
# [text] 能改的界面文字（默认值在 player.js 的 TEXT 里）
TEXT_KEYS = {
    'battleStart': ('战斗开始', 'Battle'), 'encounter': ('ENCOUNTER', 'ENCOUNTER'), 'battleEnd': ('战斗结束', 'Battle over'),
    'victory': ('VICTORY', 'VICTORY'), 'round1': ('第一轮', 'Round 1'), 'roundTag': ('ROUND', 'ROUND'),
    'combat': ('战斗中 · ', 'In combat · '), 'end': ('完', 'Fin'), 'itemTag': ('ITEM', 'ITEM'), 'vs': ('VS', 'VS'),
    'natural': ('NATURAL', 'NATURAL'), 'replayTag': ('TRPG REPLAY', 'TRPG REPLAY'), 'oocHead': ('场外 · OOC', 'OOC · TABLE TALK'),
    'narrator': ('旁白', 'Narrator'), 'ooc': ('场外', 'OOC'),
}


class ThemeError(RuntimeError):
    pass


def tokens():
    """设计变量：[(名字, 默认值, 中文说明, 英文说明)]，按 player.css 里的顺序。"""
    text = CSS.read_text(encoding='utf-8')
    start = text.index(':root {')
    block = text[start:text.index('\n}', start)]
    return [m.groups() for m in map(TOKEN.match, block.splitlines()) if m]


def builtin():
    """内置主题：{id: 目录}。"""
    return {d.name: d for d in sorted(BUILTIN.iterdir()) if (d / 'theme.toml').is_file()}


def _load(path):
    try:
        return tomllib.loads((path / 'theme.toml').read_text(encoding='utf-8'))
    except tomllib.TOMLDecodeError as e:
        raise ThemeError(f'{path / "theme.toml"}: {e}') from e


def locate(project, name):
    """主题名 → (目录, 是不是内置)：项目里有这个文件夹（带 theme.toml）就用它，否则找内置主题。"""
    if project is not None:
        p = project.root / name
        if (p / 'theme.toml').is_file():
            return p, False
    b = builtin()
    if name in b:
        return b[name], True
    raise ThemeError(f'theme "{name}" not found: no {name}/theme.toml in the project and no such built-in theme '
                     f'(built-in: {", ".join(b)})')


def chain(project, name):
    """这个主题和它的 base 们，从最底下的开始：[(id, 目录, 设置)]。"""
    out, seen = [], set()
    while name:
        if name in seen:
            raise ThemeError(f'theme base loop at "{name}"')
        seen.add(name)
        path, _ = locate(project, name)
        cfg = _load(path)
        out.append((name, path, cfg))
        name = cfg.get('base')
    return out[::-1]


def configured(project):
    return ((project.config.get('player') or {}).get('theme') if project else None) or DEFAULT


def resolve(project, name=None):
    """把主题和它的 base 合起来：dict(id, name, description, vars, text, fonts, images, layers, warnings)。"""
    name = name or configured(project)
    known = {t[0] for t in tokens()}
    want = 'en' if project is not None and project.lang.startswith('en') else 'zh-CN'
    out = dict(id=name, vars={}, text={}, fonts={}, images={}, layers=[], warnings=[])
    for tid, path, cfg in chain(project, name):
        for k, v in (cfg.get('vars') or {}).items():
            k = k.lstrip('-')
            if k not in known:
                out['warnings'].append(f'{tid}: unknown design variable --{k}')
            out['vars'][k] = str(v)
        text = dict(cfg.get('text') or {})
        for lang in LANGS:                                 # [text.zh-CN] / [text.en] 只在对应语言的项目里生效
            sub = text.pop(lang, None)
            if isinstance(sub, dict) and lang == want:
                text.update(sub)
        for k, v in text.items():
            if k == 'results' and isinstance(v, dict):
                out['text'].setdefault('results', {}).update({str(a): str(b) for a, b in v.items()})
            else:
                if k not in TEXT_KEYS:
                    out['warnings'].append(f'{tid}: unknown text key {k}')
                out['text'][k] = str(v)
        for family, f in (cfg.get('fonts') or {}).items():
            out['fonts'][str(family)] = (path, str(f))
        for key, f in (cfg.get('images') or {}).items():
            out['images'][str(key)] = (path, str(f))
        out['layers'].append((tid, path))
        out['name'] = cfg.get('name', tid)
        out['description'] = cfg.get('description', '')
    for family, (path, f) in out['fonts'].items():
        if not (path / f).is_file():
            out['warnings'].append(f'font file not found: {path / f}')
    for key, (path, f) in out['images'].items():
        if not (path / f).is_file():
            out['warnings'].append(f'image not found: {path / f}')
    return out


def _font_format(name):
    return {'.woff2': 'woff2', '.woff': 'woff', '.ttf': 'truetype', '.otf': 'opentype'}.get(pathlib.Path(name).suffix.lower(), '')


def write(project, out_dir, name=None):
    """把主题写进 <out_dir>/theme/：theme.css（字体、设计变量、各层的 theme.css）和用到的文件。

    返回放进 data.js 的 dict(id, name, text, images)，外加 warnings。
    """
    t = resolve(project, name)
    dst = pathlib.Path(out_dir) / 'theme'
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    css = [f'/* theme: {t["id"]} · {t["name"]} */']
    for tid, path in t['layers']:                          # 每层主题文件夹里的字体、图片原样复制，后面的层盖前面的
        for f in sorted(path.rglob('*')):
            if f.is_file() and f.name not in OWN:
                target = dst / f.relative_to(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
    for family, (path, f) in t['fonts'].items():
        fmt = _font_format(f)
        css.append(f'@font-face {{ font-family: "{family}"; src: url("{pathlib.PurePath(f).as_posix()}")'
                   + (f' format("{fmt}")' if fmt else '') + '; font-display: block; }')
    if t['vars']:
        css.append(':root {\n' + ''.join(f'  --{k}: {v};\n' for k, v in t['vars'].items()) + '}')
    for tid, path in t['layers']:
        if (path / 'theme.css').is_file():
            css.append(f'/* ── {tid}/theme.css ── */\n' + (path / 'theme.css').read_text(encoding='utf-8'))
    (dst / 'theme.css').write_text('\n'.join(css) + '\n', encoding='utf-8')
    images = {k: 'theme/' + pathlib.PurePath(f).as_posix() for k, (path, f) in t['images'].items()}
    return dict(id=t['id'], name=t['name'], text=t['text'], images=images), t['warnings']


# ───────── 新建主题 ─────────
CSS_GUIDE = {
    'zh-CN': """/* {name} · 自定义样式
 *
 * 在 theme.toml 的 [vars] 里改设计变量就能换掉大部分风格；这里写变量做不到的事：换版式、加纹理、改形状、加动画。
 * 这个文件在 player.css 和设计变量之后载入，同样的选择器写在这里就会盖过默认样式。
 * 图片、字体放在主题文件夹里，用相对路径引用，例如 background: url("images/paper.png")。
 *
 * 画面结构（舞台固定 1920×1080）：
 *   #stage
 *     #world        背景 #bg、氛围粒子 #atmo、立绘 #chars > .char、CG #cg、暗角 #vignette
 *     #hud          骰子 .dice-panel > .die-col（.good .bad .fumble .crit）、伤害 .dmg、对抗 .vs-panel、横幅 .banner（.round .end）、道具 .item-show
 *     #ui           幕名 #scene-title、战斗条 #combat、场外弹幕 #chat > .bub（.gm）、
 *                   对话框 #box（.nar 旁白）> .nameplate > .name .sub、.text、.narmark、四角 .orn、按钮 #controls
 *     #card         章节卡 .cc-num .cc-name .cc-end；#credits 片尾 .cr-title .cr-h .cr-p；#log 对话记录；#title 标题画面
 * <body> 上有 .theme-<主题ID>，渲染时还有 .rec。
 * 用 replay theme preview 截图看效果。
 */
""",
    'en': """/* {name} · custom styles
 *
 * Most of the look changes through the design variables in [vars] of theme.toml; use this file for what variables
 * can't do: different layouts, textures, shapes, animations. It loads after player.css and the variables, so the same
 * selectors here override the defaults. Put images and fonts in the theme folder and use relative paths,
 * e.g. background: url("images/paper.png").
 *
 * Structure (the stage is a fixed 1920×1080):
 *   #stage
 *     #world        background #bg, particles #atmo, sprites #chars > .char, CG #cg, vignette #vignette
 *     #hud          dice .dice-panel > .die-col (.good .bad .fumble .crit), damage .dmg, contest .vs-panel,
 *                   banners .banner (.round .end), items .item-show
 *     #ui           scene title #scene-title, combat strip #combat, OOC chat #chat > .bub (.gm),
 *                   dialogue box #box (.nar for narration) > .nameplate > .name .sub, .text, .narmark, corners .orn, #controls
 *     #card         chapter card .cc-num .cc-name .cc-end; #credits .cr-title .cr-h .cr-p; #log backlog; #title title screen
 * <body> carries .theme-<theme id>, plus .rec while rendering.
 * Check the result with replay theme preview.
 */
""",
}


def scaffold(project, folder='theme', base=DEFAULT, name=None):
    """在项目里新建主题文件夹：theme.toml 列出全部设计变量（注释掉，带默认值和说明），theme.css 写好画面结构说明。"""
    root = project.root / folder
    if (root / 'theme.toml').exists():
        raise ThemeError(f'{folder}/theme.toml already exists')
    inherited = resolve(project, base)                     # base 要存在；注释里写它实际生效的值
    en = project.lang.startswith('en')
    name = name or (project.config.get('project') or {}).get('title') or folder
    lines = [f'name = "{name}"', f'base = "{base}"' + ('                 # start from this theme, then apply what is written below'
                                                       if en else '                 # 先套用这个主题，再改下面写的'),
             'description = ""', '',
             '# Design variables: uncomment and change. Values are CSS.' if en else '# 设计变量：去掉 # 再改，值就是 CSS。',
             '[vars]']
    for key, default, zh, en_desc in tokens():
        value = inherited['vars'].get(key, default).replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'# {key} = "{value}"  # {en_desc if en else zh}')
    lines += ['', '# Interface wording (defaults shown); [text.en] / [text.zh-CN] apply to one language only' if en
              else '# 界面上的固定文字（后面是默认值）；写在 [text.zh-CN] / [text.en] 里的只对那种语言的项目生效', '[text]']
    for key, (zh, en_text) in TEXT_KEYS.items():
        lines.append(f'# {key} = "{en_text if en else zh}"')
    lines += ['# results = { success = "成功", failure = "失败", critical = "大成功", fumble = "大失败", hit = "命中", miss = "未中" }'
              if not en else '# results = { success = "Success", failure = "Failure", critical = "Critical", fumble = "Fumble", hit = "Hit", miss = "Miss" }',
              '', '# Font files in this folder; then use the family name in [vars], e.g. font-display = "\'Harbor\', serif"'
              if en else '# 字体文件（放在这个文件夹里）；然后在 [vars] 里用字体名，例如 font-display = "\'Harbor\', serif"',
              '[fonts]', '# "Harbor" = "fonts/Harbor.woff2"', '',
              '# Images' if en else '# 图片', '[images]', '# gm_avatar = "images/gm.png"' + ('   # avatar of GM chat bubbles' if en
                                                                                           else '   # GM 弹幕的头像'), '']
    root.mkdir(parents=True, exist_ok=True)
    (root / 'theme.toml').write_text('\n'.join(lines), encoding='utf-8')
    (root / 'theme.css').write_text(CSS_GUIDE['en' if en else 'zh-CN'].format(name=name), encoding='utf-8')
    return root


def use(project, folder):
    """在 replay.toml 的 [player] 里写上 theme = "<folder>"（已经写了别的主题就不动，返回 False）。"""
    cfg = project.root / 'replay.toml'
    text = cfg.read_text(encoding='utf-8')
    if (project.config.get('player') or {}).get('theme'):
        return False
    if re.search(r'^\[player\]\s*$', text, re.M):
        text = re.sub(r'^\[player\]\s*$', f'[player]\ntheme = "{folder}"', text, count=1, flags=re.M)
    else:
        text = text.rstrip('\n') + f'\n\n[player]\ntheme = "{folder}"\n'
    cfg.write_text(text, encoding='utf-8')
    return True
