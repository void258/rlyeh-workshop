"""命令行入口：replay <子命令>。所有子命令都支持 --json，出错时退出码非零。"""
import argparse
import json
import pathlib
import re
import sys
from importlib import resources

from . import SPEC_VERSION, __version__, i18n, importers, voice
from .backends import BackendError
from .backends.worker import WorkerError
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
    lines = [t('cli.status_chapter', n=r['chapter'], title=r['title'], lines=r['lines'], voiced=r['voiced'],
               scenes=r['scenes'], directives=r['directives']) for r in rows]
    vs = voice.summary(proj)
    lines.append(t('cli.status_voice', minutes=round(vs['seconds'] / 60, 1), **{k: v for k, v in vs.items() if k != 'seconds'}))
    if vs['no_voice']:
        lines.append(t('cli.status_no_voice', names='、'.join(vs['no_voice'])))
    _out(args, dict(ok=True, project=proj.config.get('project', {}), chapters=rows, voice=vs), '\n'.join(lines))
    return 0


def _ids(s):
    return set(filter(None, (s or '').split(','))) or None


def _progress(args):
    return None if args.json else (lambda line: print('  ' + line, flush=True))


def cmd_voice(args):
    proj = _project(args)
    on = _progress(args)
    if args.action == 'design':
        index = voice.design(proj, _ids(args.chars), args.n, on)
        _out(args, dict(ok=True, candidates=index), t('cli.voice_design_done', n=len(index)))
    elif args.action == 'pick':
        rec = voice.pick(proj, args.char, args.choice, args.note or '')
        _out(args, dict(ok=True, pick=rec), t('cli.voice_pick_done', cid=args.char, file=rec['choice']))
    elif args.action == 'extra':
        refs = voice.make_extra(proj, args.char, on_line=on)
        _out(args, dict(ok=True, extra=refs), t('cli.voice_extra_done', cid=args.char, n=len(refs)))
    elif args.action == 'build':
        done = voice.build(proj, _ids(args.ids), args.seed, args.force, args.limit, on)
        _out(args, dict(ok=True, built=done), t('cli.voice_build_done', n=len(done)) if done else t('cli.voice_build_none'))
    elif args.action == 'qa':
        report = voice.qa(proj, _ids(args.ids), on)
        if report is None:
            _out(args, dict(ok=True, skipped=True), t('cli.voice_qa_skipped'))
            return 0
        bad = [k for k, v in report.items() if v.get('bad') and (not args.ids or k in _ids(args.ids))]
        _out(args, dict(ok=True, report=report, failed=bad), t('cli.voice_qa_done', n=len(report), bad=len(bad), ids='：' + ','.join(bad) if bad else ''))
    elif args.action == 'redo':
        ids = set(_ids(args.ids) or ())
        if args.failed:
            ids |= set(voice.failed(proj))
        if args.marked:
            ids |= set(voice.marked(proj))
        if args.voice:
            ids |= {it.id for _, it, v, _ in voice.lines(proj) if v == args.voice}
        left = voice.redo(proj, sorted(ids), on)
        _out(args, dict(ok=True, redone=sorted(ids), still_failing=left),
             t('cli.voice_redo_done', n=len(ids), ids=','.join(left) if left else '—'))
    return 0


def cmd_bleep(args):
    proj = _project(args)
    done, problems = voice.bleep(proj, _progress(args))
    lines = [t('cli.bleep_done', n=len(done))] + [t('cli.bleep_problem', id=p['id'], reason=p['reason']) for p in problems]
    _out(args, dict(ok=not problems, bleeped=done, problems=problems), '\n'.join(lines))
    return 0


def cmd_preview(args):
    proj = _project(args)
    from .preview import serve
    serve(proj, args.host, args.port, on_ready=lambda url: print(t('cli.preview_at', url=url), flush=True))
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

    p = sub.add_parser('voice', help='voices and voice acting / 声线与配音')
    vs = p.add_subparsers(dest='action', required=True)
    q = vs.add_parser('design', parents=[common], help='voice candidates / 生成候选声线')
    q.add_argument('--chars', help='character IDs, comma separated / 角色 ID，逗号分隔')
    q.add_argument('-n', type=int, help='candidates per character / 每个角色几段')
    q = vs.add_parser('pick', parents=[common], help='choose a candidate / 选定声线')
    q.add_argument('char')
    q.add_argument('choice', help='candidate number or file / 候选序号或文件')
    q.add_argument('--note')
    q = vs.add_parser('extra', parents=[common], help='extra references in the same voice / 同音色补附加参考')
    q.add_argument('char')
    q = vs.add_parser('build', parents=[common], help='synthesize lines / 生成配音')
    q.add_argument('--ids')
    q.add_argument('--seed', type=int, default=123)
    q.add_argument('--force', action='store_true')
    q.add_argument('--limit', type=int, default=0)
    q = vs.add_parser('qa', parents=[common], help='speech-recognition QA / 识别质检')
    q.add_argument('--ids')
    q = vs.add_parser('redo', parents=[common], help='retry with new seeds / 换种子重做')
    q.add_argument('--ids')
    q.add_argument('--failed', action='store_true', help='lines that failed QA / 质检不合格的')
    q.add_argument('--marked', action='store_true', help='lines marked in review / 审听标了重做的')
    q.add_argument('--voice', help='every line of this character / 这个角色的全部台词')
    for q in vs.choices.values():
        q.set_defaults(func=cmd_voice)

    p = sub.add_parser('bleep', parents=[common], help='bleep profanity / 消音')
    p.set_defaults(func=cmd_bleep)
    p = sub.add_parser('preview', parents=[common], help='local preview and review pages / 本地预览与审核页')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8766)
    p.set_defaults(func=cmd_preview)
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
    except (voice.VoiceError, BackendError, WorkerError) as e:
        _out(args, dict(ok=False, error=str(e)), t('cli.error', err=e))
        return 3


if __name__ == '__main__':
    sys.exit(main())
