"""命令行入口：replay <子命令>。所有子命令都支持 --json，出错时退出码非零。"""
import argparse
import json
import pathlib
import re
import sys
from importlib import resources

from . import SPEC_VERSION, __version__, i18n, importers
from .i18n import t
from .project import Project, ProjectError, find_root
from .script import ids as script_ids
from .script.lint import lint
from .script.model import Directive, Scene

GITIGNORE = """# 拉莱耶工坊：可以随时重新生成的东西 / regenerable outputs
build/
.rlyeh/
art/_raw/
art/_overview/
audio/voice/
audio/voice-bleep/
"""


def _out(args, data, text):
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    elif text:
        print(text)


def _project(args):
    root = find_root(args.project)
    if root is None:
        raise ProjectError(t('cli.no_project'))
    proj = Project(root)
    if not args.lang:
        i18n.set_lang(i18n.detect(proj.lang))
    return proj


def cmd_init(args):
    target = pathlib.Path(args.dir).resolve()
    if (target / 'replay.toml').exists():
        _out(args, dict(ok=False, error='exists', path=str(target)), t('cli.init_exists', path=target))
        return 1
    lang = 'en' if (args.lang or i18n.lang()).lower().startswith('en') else 'zh-CN'
    tpl = resources.files('rlyeh') / 'templates' / lang
    pid = re.sub(r'[^A-Za-z0-9_-]+', '-', target.name).strip('-').lower() or 'replay'
    title = args.title or target.name
    for d in ['script', 'logs/raw', 'voices', 'art/prompts', 'art/sprites', 'art/backgrounds', 'art/cg', 'art/items',
              'audio/bgm', 'audio/sfx', 'review']:
        (target / d).mkdir(parents=True, exist_ok=True)
    config = (tpl / 'replay.toml').read_text(encoding='utf-8').replace('{id}', pid).replace('{title}', title)
    (target / 'replay.toml').write_text(config, encoding='utf-8')
    (target / 'cast.yaml').write_text((tpl / 'cast.yaml').read_text(encoding='utf-8'), encoding='utf-8')
    (target / 'script' / '01-chapter.md').write_text((tpl / 'chapter.md').read_text(encoding='utf-8'), encoding='utf-8')
    gi = target / '.gitignore'
    if not gi.exists():
        gi.write_text(GITIGNORE, encoding='utf-8')
    _out(args, dict(ok=True, path=str(target), lang=lang), t('cli.init_done', path=target))
    return 0


def cmd_lint(args):
    proj = _project(args)
    chapters = proj.chapters()
    issues = lint(chapters, proj)
    errors = sum(1 for i in issues if i.level == 'error')
    warnings = len(issues) - errors
    if args.errors_only:
        issues = [i for i in issues if i.level == 'error']
    lines = []
    for i in issues:
        rel = pathlib.Path(i.file).resolve().relative_to(proj.root) if pathlib.Path(i.file).is_absolute() else i.file
        lines.append(f'{rel}:{i.line}: {t("level." + i.level)}: {i.message}')
    lines.append(t('cli.lint_summary', errors=errors, warnings=warnings))
    _out(args, dict(ok=errors == 0, errors=errors, warnings=warnings, issues=[i.as_dict() for i in issues]), '\n'.join(lines))
    return 1 if errors else 0


def cmd_ids(args):
    proj = _project(args)
    total = 0
    written = []
    for ch in proj.chapters():
        anchored = sum(1 for it in ch.spoken if it.anchor)
        fresh = [it for it in ch.spoken if not it.anchor]
        if anchored == 0:
            fresh = ch.spoken          # 整章都没写：按顺序编号的结果原样写进去
        total += script_ids.write_anchors(ch.path, fresh)
        written += [dict(file=ch.path, line=it.line_no, id=it.id) for it in fresh]
    _out(args, dict(ok=True, assigned=written), t('cli.ids_done', n=total) if total else t('cli.ids_none'))
    return 0


def cmd_status(args):
    proj = _project(args)
    rows = []
    for ch in proj.chapters():
        spoken = ch.spoken
        rows.append(dict(chapter=ch.number, title=ch.title, file=ch.path, lines=len(spoken),
                         voiced=sum(1 for s in spoken if s.voiced),
                         scenes=sum(1 for it in ch.items if isinstance(it, Scene)),
                         directives=sum(1 for it in ch.items if isinstance(it, Directive))))
    text = '\n'.join(t('cli.status_chapter', n=r['chapter'], title=r['title'], lines=r['lines'], voiced=r['voiced'],
                       scenes=r['scenes'], directives=r['directives']) for r in rows)
    _out(args, dict(ok=True, project=proj.config.get('project', {}), chapters=rows), text)
    return 0


def cmd_import(args):
    proj = _project(args)
    copied = importers.copy_raw(args.files, proj.root / 'logs' / 'raw') if args.files else []
    events, rep = importers.run(proj.root, proj.config)
    lines = []
    if copied:
        lines.append(t('cli.import_copied', names='、'.join(copied)))
    lines.append(t('cli.import_summary', files=len(rep['files']), raw=rep['raw_messages'], merged=rep['merged_messages'],
                   events=rep['events'], sessions=len(rep['sessions'])))
    for s in rep['sessions']:
        lines.append(t('cli.import_session', n=s['session'], start=s['start'] or '?', end=s['end'] or '?', events=s['events'],
                       speakers='、'.join(s['speakers'][:12]) + ('…' if len(s['speakers']) > 12 else '')))
    if rep['dropped']:
        lines.append(t('cli.import_dropped', n=len(rep['dropped'])))
    if rep['unknown_speakers']:
        lines.append(t('cli.import_unknown', names='、'.join(rep['unknown_speakers'])))
    if rep['private']:
        lines.append(t('cli.import_private', n=len(rep['private'])))
        lines += [f"  {p['id']} {p['speaker']}: {p['text']}" for p in rep['private'][:20]]
    lines.append(t('cli.import_consent'))
    _out(args, dict(ok=True, copied=copied, **rep), '\n'.join(lines))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog='replay', description="R'lyeh Workshop / 拉莱耶工坊")
    ap.add_argument('--version', action='version', version=f'rlyeh-workshop {__version__} (spec {SPEC_VERSION})')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true', help='structured output / 输出 JSON')
    common.add_argument('--lang', help='zh-CN | en')
    common.add_argument('-C', '--project', default='.', help='project directory / 项目目录')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init', parents=[common], help='create a project / 新建项目')
    p.add_argument('dir')
    p.add_argument('--title')
    p.set_defaults(func=cmd_init)
    p = sub.add_parser('lint', parents=[common], help='check scripts / 校验剧本')
    p.add_argument('--errors-only', action='store_true')
    p.set_defaults(func=cmd_lint)
    p = sub.add_parser('ids', parents=[common], help='assign line IDs / 补台词 ID')
    p.set_defaults(func=cmd_ids)
    p = sub.add_parser('import', parents=[common], help='import session logs / 导入跑团记录')
    p.add_argument('files', nargs='*', help='log files, folders or zips / 记录文件、文件夹或 zip')
    p.set_defaults(func=cmd_import)
    p = sub.add_parser('status', parents=[common], help='project status / 项目进度')
    p.set_defaults(func=cmd_status)
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):        # Windows 控制台默认 GBK，中文会乱码
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.lang:
        i18n.set_lang(args.lang)
    try:
        return args.func(args)
    except ProjectError as e:
        _out(args, dict(ok=False, error=str(e)), str(e))
        return 2


if __name__ == '__main__':
    sys.exit(main())
