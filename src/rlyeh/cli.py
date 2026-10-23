"""命令行入口：replay <子命令>。所有子命令都支持 --json，出错时退出码非零。"""
import argparse
import json
import pathlib
import re
import sys
from importlib import resources

from . import SPEC_VERSION, __version__, art, doctor, encode, i18n, importers, music, player, render, sfx, tasks, voice
from .backends import BackendError
from .backends.worker import WorkerError
from .player.theme import ThemeError
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
audio/sfx/_takes/
audio/bgm/takes/
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
    for name in ('music.yaml', 'sfx.yaml'):
        (target / name).write_text((tpl / name).read_text(encoding='utf-8'), encoding='utf-8')
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
    ars, ss, ms = art.summary(proj), sfx.summary(proj), music.summary(proj)
    lines.append(t('cli.status_art', **{k: v for k, v in ars.items() if k != 'unplanned'}))
    if ars['unplanned']:
        lines.append(t('cli.status_art_unplanned', n=ars['unplanned']))
    lines.append(t('cli.status_sfx', **ss))
    lines.append(t('cli.status_music', **ms))
    _out(args, dict(ok=True, project=proj.config.get('project', {}), chapters=rows, voice=vs, art=ars, sfx=ss, music=ms),
         '\n'.join(lines))
    return 0


def _ids(s):
    return set(filter(None, (s or '').split(','))) or None


def _progress(args):
    if args.json:                                   # --json 时标准输出只放结果，进度写到标准错误（后台任务的日志就是它）
        return lambda line: print(line, file=sys.stderr, flush=True)
    return lambda line: print('  ' + line, flush=True)


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


def cmd_art(args):
    proj = _project(args)
    on = _progress(args)
    if args.action == 'jobs':
        created, have = art.scaffold(proj)
        todo = [j.id for j in art.load_jobs(proj) if j.needs_prompt and not j.skip]
        lines = [t('cli.art_jobs_done', n=len(created), have=have)]
        if todo:
            lines.append(t('cli.art_needs_prompt', ids=', '.join(todo)))
        _out(args, dict(ok=True, created=created, needs_prompt=todo), '\n'.join(lines))
    elif args.action == 'run':
        kinds = _ids(args.kind)
        res = art.run(proj, _ids(args.ids), kinds, args.force, args.marked, args.limit, on)
        lines = [t('cli.art_run_done', done=len(res['done']), adopted=len(res['adopted']))]
        if res['waiting']:
            lines.append(t('cli.art_waiting'))
            lines += [f"  {w['out']}" for w in res['waiting']]
        lines += [t('cli.art_blocked', **b) for b in res['blocked']]
        _out(args, dict(ok=True, **res), '\n'.join(lines))
    elif args.action == 'compose':
        done = art.compose_all(proj, _ids(args.ids))
        _out(args, dict(ok=True, composed=done), t('cli.art_compose_done', n=len(done)))
    elif args.action == 'check':
        report, sheets = art.check(proj)
        warn = {k: v for k, v in report.items() if v['status'] == 'warn'}
        missing = sum(1 for v in report.values() if v['status'] in ('missing', 'needs_prompt'))
        lines = [t('cli.art_check_done', n=len(report), missing=missing, warn=len(warn), sheets=', '.join(sheets) or '—')]
        lines += [t('cli.art_warn', out=k, notes='; '.join(v['notes'])) for k, v in warn.items()]
        _out(args, dict(ok=True, report=report, sheets=sheets), '\n'.join(lines))
    return 0


def cmd_sfx(args):
    proj = _project(args)
    if args.list:
        cat = sfx.catalog(proj)
        lines = [t('cli.sfx_list', id=k, mark='' if v['builtin'] else ' *', aliases='、'.join(v['aliases']) or '—') for k, v in cat.items()]
        _out(args, dict(ok=True, sounds=cat), '\n'.join(lines))
        return 0
    res = sfx.build(proj, set(args.names) or None, args.force, _progress(args))
    lines = [t('cli.sfx_done', n=len(res['done']), names=', '.join(res['done'])) if res['done'] else t('cli.sfx_none')]
    lines += [t('cli.sfx_problem', **p) for p in res['problems']]
    _out(args, dict(ok=not res['problems'], **res), '\n'.join(lines))
    return 0


def cmd_music(args):
    proj = _project(args)
    on = _progress(args)
    if args.action == 'gen':
        res = music.gen(proj, _ids(args.cues), args.takes, on)
        lines = [t('cli.music_gen_done', n=len(res['done']), names=', '.join(res['done'])) if res['done'] else t('cli.music_gen_none')]
        lines += [t('cli.music_waiting', **w) for w in res['waiting']]
        lines += [t('cli.music_problem', **p) for p in res['problems']]
        _out(args, dict(ok=not res['problems'], **res), '\n'.join(lines))
    elif args.action == 'check':
        report = music.check(proj, _ids(args.cues), on)
        if report is None:
            _out(args, dict(ok=True, skipped=True), t('cli.music_check_skipped'))
            return 0
        bad = [k for k, v in report.items() if not v['clean']]
        _out(args, dict(ok=True, report=report, vocals=bad),
             t('cli.music_check_done', n=len(report), bad=len(bad), ids='：' + ', '.join(bad) if bad else ''))
    elif args.action == 'pick':
        rec = music.pick(proj, args.cue, args.choice, args.note or '')
        _out(args, dict(ok=True, pick=rec), t('cli.music_pick_done', cid=args.cue, file=rec['choice']))
    return 0


def cmd_build(args):
    proj = _project(args)
    res = player.build(proj, theme=args.theme)
    lines = [t('cli.build_done', path=res['path'], chapters=res['chapters'], steps=res['steps']), t('cli.build_theme', theme=res['theme'])]
    lines += [t('cli.theme_warning', w=w) for w in res['warnings']]
    for k, items in res['missing'].items():
        if items:
            lines.append(t('cli.build_missing', what=t('missing.' + k), n=len(items),
                           items='、'.join(items[:12]) + ('…' if len(items) > 12 else '')))
    _out(args, dict(ok=True, **res), '\n'.join(lines))
    return 0


def cmd_theme(args):
    proj = _project(args)
    from .player import theme as themes
    if args.action == 'list':
        current = themes.configured(proj)
        rows = []
        for tid, path in themes.builtin().items():
            cfg = themes._load(path)
            rows.append(dict(id=tid, name=cfg.get('name', tid), description=cfg.get('description', ''), builtin=True))
        if current not in themes.builtin():
            cfg = themes._load(themes.locate(proj, current)[0])
            rows.append(dict(id=current, name=cfg.get('name', current), description=cfg.get('description', ''), builtin=False))
        lines = [t('cli.theme_list_item', mark='*' if r['id'] == current else ' ', **{k: r[k] for k in ('id', 'name', 'description')})
                 for r in rows]
        lines.append(t('cli.theme_current', theme=current))
        _out(args, dict(ok=True, themes=rows, current=current), '\n'.join(lines))
    elif args.action == 'new':
        path = themes.scaffold(proj, args.folder, args.base, args.name)
        used = themes.use(proj, args.folder)
        lines = [t('cli.theme_new_done', path=path.relative_to(proj.root).as_posix(), base=args.base),
                 t('cli.theme_new_used' if used else 'cli.theme_new_kept', folder=args.folder)]
        _out(args, dict(ok=True, path=path.relative_to(proj.root).as_posix(), used=used), '\n'.join(lines))
    elif args.action == 'preview':
        res = render.theme_preview(proj, args.theme, _progress(args))
        lines = [t('cli.theme_preview_done', theme=res['theme'], n=len(res['shots']), sheet=res['sheet'])]
        lines += [t('cli.theme_warning', w=w) for w in res['warnings']]
        _out(args, dict(ok=True, **res), '\n'.join(lines))
    return 0


def cmd_render(args):
    proj = _project(args)
    chapters = [int(c) for c in args.chapter.split(',')] if args.chapter else None
    res = render.render(proj, args.start, args.seconds, chapters, args.remix, args.name, _progress(args))
    _out(args, dict(ok=True, **res), t('cli.render_done', video=res['video'], minutes=round(res['seconds'] / 60, 1),
                                        took=round(res['took'] / 60, 1)))
    return 0


def cmd_encode(args):
    proj = _project(args)
    out = encode.encode(proj, args.preset, args.src, _progress(args))
    rel = out.relative_to(proj.root).as_posix()
    _out(args, dict(ok=True, path=rel, bytes=out.stat().st_size), t('cli.encode_done', path=rel, mb=round(out.stat().st_size / 2 ** 20, 1)))
    return 0


def cmd_next(args):
    proj = _project(args)
    all_tasks = tasks.plan(proj)
    task = tasks.next_task(proj, all_tasks)
    if args.all:
        mark = {'done': '✓', 'skip': '·', 'review': '?', 'todo': '→', 'stale': '↻'}
        lines = [t('cli.next_row', mark=mark.get(x.status, ' '), status=x.status, kind=x.kind, id=x.id, title=x.title)
                 for x in all_tasks]
        _out(args, dict(ok=True, next=task.as_dict() if task else None, tasks=[x.as_dict() for x in all_tasks],
                        overview=tasks.overview(all_tasks)), '\n'.join(lines))
        return 0
    if task is None:
        _out(args, dict(ok=True, next=None), t('cli.next_none'))
        return 0
    lines = [t('cli.next_task', kind=task.kind, id=task.id, title=task.title)]
    if task.kind == 'agent':
        lines.append(t('cli.next_agent', playbook=task.playbook, id=task.id))
    elif task.kind == 'tool':
        lines.append(t('cli.next_tool', command=' '.join(task.command or [])))
    else:
        lines.append(t('cli.next_review', page=task.page))
    shown = {k: v for k, v in task.detail.items() if k != 'key' and v not in ([], {}, 0, None, '')}
    if shown:
        lines.append(t('cli.next_detail', detail=json.dumps(shown, ensure_ascii=False)[:600]))
    _out(args, dict(ok=True, next=task.as_dict()), '\n'.join(lines))
    return 0


def cmd_done(args):
    proj = _project(args)
    rec = tasks.complete(proj, args.id, args.note or '')
    _out(args, dict(ok=True, id=args.id, record=rec), t('cli.done_ok', id=args.id))
    return 0


def cmd_mcp(args):
    from .mcp import serve
    serve(args.project)                              # 标准输出只放 MCP 协议消息
    return 0


def cmd_doctor(args):
    root = find_root(args.project)
    proj = Project(root) if root else None
    if proj and not args.lang:
        i18n.set_lang(i18n.detect(proj.lang))
    rows = doctor.run(proj)
    mark = {'ok': '✓', 'warn': '!', 'fail': '✗'}
    lines, group = [], None
    for r in rows:
        if r['group'] != group:
            group = r['group']
            lines.append(t('doctor.group.' + group))
        lines.append(f"  {mark[r['status']]} {r['name']}" + (f": {r['detail']}" if r['detail'] else '')
                     + (f"\n      → {r['hint']}" if r['hint'] else ''))
    fail, warn = (sum(1 for r in rows if r['status'] == s) for s in ('fail', 'warn'))
    lines.append(t('cli.doctor_summary', fail=fail, warn=warn))
    _out(args, dict(ok=fail == 0, checks=rows), '\n'.join(lines))
    return 1 if fail else 0


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
    p = sub.add_parser('next', parents=[common], help='the next task / 下一件该做的事')
    p.add_argument('--all', action='store_true', help='every task with its status / 列出全部任务')
    p.set_defaults(func=cmd_next)
    p = sub.add_parser('done', parents=[common], help='mark an agent task done / 标记 AI 任务完成')
    p.add_argument('id')
    p.add_argument('--note')
    p.set_defaults(func=cmd_done)

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

    p = sub.add_parser('art', help='art: prompts, images, expressions / 美术')
    arts = p.add_subparsers(dest='action', required=True)
    arts.add_parser('jobs', parents=[common], help='write starter prompts / 写起步用的提示词')
    q = arts.add_parser('run', parents=[common], help='generate images / 生成图片')
    q.add_argument('--ids', help='job IDs or output paths / 任务 ID 或输出路径')
    q.add_argument('--kind', help='sprite,expression,background,cg,item')
    q.add_argument('--force', action='store_true')
    q.add_argument('--marked', action='store_true', help='images rejected in review / 审核打回的')
    q.add_argument('--limit', type=int, default=0)
    q = arts.add_parser('compose', parents=[common], help='composite expressions / 合成表情差分')
    q.add_argument('--ids')
    arts.add_parser('check', parents=[common], help='check images, overview sheets / 检查图片、拼总览图')
    for q in arts.choices.values():
        q.set_defaults(func=cmd_art)

    p = sub.add_parser('sfx', parents=[common], help='sound effects / 音效')
    p.add_argument('names', nargs='*')
    p.add_argument('--force', action='store_true')
    p.add_argument('--list', action='store_true', help='list sounds and aliases / 列出音效和别名')
    p.set_defaults(func=cmd_sfx)

    p = sub.add_parser('music', help='background music / BGM')
    ms = p.add_subparsers(dest='action', required=True)
    q = ms.add_parser('gen', parents=[common], help='generate takes / 生成')
    q.add_argument('--cues', help='cue IDs, comma separated / 曲目 ID，逗号分隔')
    q.add_argument('--takes', type=int, default=1, help='takes per cue / 每段至少几版')
    q = ms.add_parser('check', parents=[common], help='check for vocals / 检查有没有唱出词')
    q.add_argument('--cues')
    q = ms.add_parser('pick', parents=[common], help='choose a take / 选定一版')
    q.add_argument('cue')
    q.add_argument('choice', help='take number or file / 版本序号或文件名')
    q.add_argument('--note')
    for q in ms.choices.values():
        q.set_defaults(func=cmd_music)

    p = sub.add_parser('mcp', parents=[common], help='run the MCP server on stdio / 以 stdio 方式运行 MCP 服务')
    p.set_defaults(func=cmd_mcp)
    p = sub.add_parser('doctor', parents=[common], help='check the environment and backends / 检查环境和后端')
    p.set_defaults(func=cmd_doctor)
    p = sub.add_parser('build', parents=[common], help='build the player / 打包播放器')
    p.add_argument('--theme', help='use this theme instead of [player] theme / 临时换个主题')
    p.set_defaults(func=cmd_build)
    p = sub.add_parser('theme', help='player themes / 播放器主题')
    ths = p.add_subparsers(dest='action', required=True)
    ths.add_parser('list', parents=[common], help='built-in themes / 列出主题')
    q = ths.add_parser('new', parents=[common], help='create a project theme / 新建项目主题')
    q.add_argument('folder', nargs='?', default='theme')
    q.add_argument('--base', default='dark-fantasy', help='theme to start from / 基于哪个主题')
    q.add_argument('--name', help='display name / 主题名')
    q = ths.add_parser('preview', parents=[common], help='screenshots of every UI state / 截图预览')
    q.add_argument('--theme', help='preview this theme instead of [player] theme / 预览指定主题')
    for q in ths.choices.values():
        q.set_defaults(func=cmd_theme)
    p = sub.add_parser('render', parents=[common], help='render the video frame by frame / 逐帧渲染成视频')
    p.add_argument('--from', dest='start', help='start at this line ID / 从这句开始')
    p.add_argument('--seconds', type=float, default=0, help='render only this long / 只渲染这么多秒')
    p.add_argument('--chapter', help='chapter numbers, comma separated / 只渲染这几章')
    p.add_argument('--remix', action='store_true', help='remix the audio only / 只重新混音')
    p.add_argument('--name', help='output name / 输出文件名')
    p.set_defaults(func=cmd_render)
    p = sub.add_parser('encode', parents=[common], help='encode a release version / 压制')
    p.add_argument('preset', help='share | compat | a preset in [encode.*] / 预设')
    p.add_argument('--src', help='input video, default build/video/<id>.mp4 / 输入视频')
    p.set_defaults(func=cmd_encode)

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
    except (voice.VoiceError, art.ArtError, sfx.SfxError, music.MusicError, render.RenderError, encode.EncodeError, ThemeError, tasks.TaskError,
            BackendError, WorkerError) as e:
        _out(args, dict(ok=False, error=str(e)), t('cli.error', err=e))
        return 3


if __name__ == '__main__':
    sys.exit(main())
