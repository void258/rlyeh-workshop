import json
import re
import tomllib

import pytest

from rlyeh import player
from rlyeh.cli import main
from rlyeh.player import theme
from rlyeh.project import Project

LOCAL_VARS = {'c', 'sc', 'img', 'dur', 'peak', 'rc', 'bc', 'bl', 'glow'}     # 元素自己设的变量，不是设计变量


def test_tokens_cover_css():
    toks = theme.tokens()
    names = [t[0] for t in toks]
    css = theme.CSS.read_text(encoding='utf-8')
    root = css[css.index(':root {'):css.index('\n}', css.index(':root {'))]
    assert len(names) == len(re.findall(r'^\s*--', root, re.M)) == len(set(names))      # 每个变量都带中英说明
    used = set(re.findall(r'var\(--([a-z0-9-]+)', css))
    js = (theme.CSS.parent / 'player.js').read_text(encoding='utf-8')
    used |= set(re.findall(r"(?:tok|rgb)\('([a-z0-9-]+)'", js))
    used |= {f'{v}-{e}' for v in re.findall(r"'die\w*:([a-z-]+)'", js) for e in 'ab'}
    assert used - LOCAL_VARS <= set(names), used - LOCAL_VARS - set(names)


def test_text_keys_exist_in_player():
    js = (theme.CSS.parent / 'player.js').read_text(encoding='utf-8')
    for key in theme.TEXT_KEYS:
        assert re.search(rf'\b{key}:', js), key


def test_builtin_themes_are_clean(make_project):
    proj = make_project()
    assert set(theme.builtin()) >= {'dark-fantasy', 'noir', 'neon'}
    for tid in theme.builtin():
        t = theme.resolve(proj, tid)
        assert t['warnings'] == [], (tid, t['warnings'])


def test_language_text_and_inheritance(make_project, tmp_path, capsys):
    proj = make_project()
    t = theme.resolve(proj, 'noir')
    assert t['text']['battleStart'] == '遭遇' and t['vars']['accent'] == '#a33a2c' and [x[0] for x in t['layers']] == ['dark-fantasy', 'noir']
    root = tmp_path / 'en'
    main(['init', str(root), '--lang', 'en', '--json'])
    capsys.readouterr()
    assert theme.resolve(Project(root), 'noir')['text']['battleStart'] == 'Encounter'


def test_project_theme_build(full_project):
    proj = full_project()
    folder = proj.root / 'mytheme'
    (folder / 'fonts').mkdir(parents=True)
    (folder / 'fonts' / 'Harbor.woff2').write_bytes(b'wOF2')
    (folder / 'images').mkdir()
    (folder / 'images' / 'gm.png').write_bytes(b'png')
    (folder / 'theme.toml').write_text('name = "雾港"\nbase = "noir"\n[vars]\naccent = "#7fb3c9"\nnot-a-var = "1"\n'
                                       '[text]\nreplayTag = "HARBOR FILE"\n[fonts]\n"Harbor" = "fonts/Harbor.woff2"\n'
                                       '[images]\ngm_avatar = "images/gm.png"\n', encoding='utf-8')
    (folder / 'theme.css').write_text('#box { outline: 2px solid red; }\n', encoding='utf-8')
    cfg = proj.root / 'replay.toml'
    cfg.write_text(cfg.read_text(encoding='utf-8') + '\n[player]\ntheme = "mytheme"\n', encoding='utf-8')
    proj = Project(proj.root)
    res = player.build(proj)
    assert res['theme'] == 'mytheme' and res['warnings'] == ['mytheme: unknown design variable --not-a-var']
    out = proj.root / player.OUT / 'theme'
    css = (out / 'theme.css').read_text(encoding='utf-8')
    assert '@font-face { font-family: "Harbor"; src: url("fonts/Harbor.woff2") format("woff2")' in css
    assert '--accent: #7fb3c9;' in css and '--box-text: #2a2119;' in css                     # noir 的变量也在
    assert css.index('noir/theme.css') < css.index('mytheme/theme.css')                      # base 的样式在前
    assert (out / 'fonts' / 'Harbor.woff2').exists() and (out / 'images' / 'gm.png').exists()
    d = player.data(proj)
    assert d['theme']['images'] == {'gm_avatar': 'theme/images/gm.png'} and d['theme']['text']['battleStart'] == '遭遇'
    assert d['kicker'].startswith('HARBOR FILE')
    html = (proj.root / player.OUT / 'index.html').read_text(encoding='utf-8')
    assert html.index('player.css') < html.index('theme/theme.css')


def test_scaffold_and_cli(make_project, capsys):
    proj = make_project()
    assert main(['theme', 'new', '-C', str(proj.root), '--base', 'neon', '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['used'] and out['path'] == 'theme'
    cfg = tomllib.loads((proj.root / 'theme' / 'theme.toml').read_text(encoding='utf-8'))
    assert cfg['base'] == 'neon' and cfg.get('vars', {}) == {}                             # 全是注释，什么都没改
    text = (proj.root / 'theme' / 'theme.toml').read_text(encoding='utf-8')
    assert '# accent = "#29e6ff"' in text                                                  # 注释里是 base 实际生效的值
    assert len(re.findall(r'^# [a-z0-9-]+ = ', text, re.M)) >= len(theme.tokens())
    assert Project(proj.root).config['player']['theme'] == 'theme'
    assert main(['theme', 'new', '-C', str(proj.root), '--json']) == 3                      # 已经有了
    capsys.readouterr()
    assert main(['theme', 'list', '-C', str(proj.root), '--json']) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows['current'] == 'theme' and {r['id'] for r in rows['themes']} >= {'noir', 'neon', 'theme'}


def _can_render():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _can_render(), reason='needs playwright with chromium')
def test_theme_preview(full_project):
    from rlyeh import render
    proj = full_project()
    res = render.theme_preview(proj, theme='noir')
    names = [p.rsplit('/', 1)[1] for p in res['shots']]
    assert names[0] == '00-title.png' and any('dice' in n for n in names) and names[-1].endswith('credits.png')
    assert len(names) == 17 and (proj.root / res['sheet']).exists()
    show = player.data(proj, 'showcase')
    kinds = [s.get('name') or s['k'] for s in show['chapters'][0]['steps']]
    assert {'roll', 'contest', 'item', 'credits', 'ooc', 'nar', 'line'} <= set(kinds)
