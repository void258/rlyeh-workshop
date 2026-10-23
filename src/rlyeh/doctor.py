"""replay doctor：检查环境和项目配置的各个后端能不能用，不能用的告诉你怎么修。

每项结果是 dict(group, name, status, detail, hint)：status 是 ok / warn / fail，hint 已经翻译成当前语言。
fail 表示照现在的配置某一步一定会出错；warn 是能跑但有限制（占位后端、ComfyUI 没开、只能非商用……）。
"""
import platform
import shutil
import subprocess
import sys

from . import __version__, backends, encode
from .i18n import t

KINDS = ['image', 'voice_design', 'tts', 'asr', 'align', 'music']


def _row(group, name, status, detail='', hint=None):
    if isinstance(hint, tuple):
        kw = dict(hint[1])
        if 'what' in kw:
            kw['what'] = t('doctor.what.' + kw['what'])
        hint = t(hint[0], **kw)
    return dict(group=group, name=name, status=status, detail=detail, hint=hint or '')


def environment(project=None):
    rows = []
    ok = sys.version_info >= (3, 11)
    rows.append(_row('env', 'python', 'ok' if ok else 'fail', f'{platform.python_version()} · rlyeh-workshop {__version__}',
                     None if ok else ('doctor.hint_python', {})))
    ff = shutil.which('ffmpeg')
    if not ff:
        rows.append(_row('env', 'ffmpeg', 'fail', 'not found', ('doctor.hint_ffmpeg', {})))
    else:
        first = subprocess.run([ff, '-hide_banner', '-version'], capture_output=True, text=True, errors='replace').stdout.split('\n')[0]
        rows.append(_row('env', 'ffmpeg', 'ok', first.replace('ffmpeg version ', '').split(' Copyright')[0]))
        picked = []
        for codec in ('h264', 'av1'):
            try:
                kind, enc = encode.choose(codec)
                picked.append(f'{codec}: {enc}')
            except encode.EncodeError as e:
                picked.append(f'{codec}: {e}')
        gpu = any(not p.split(': ')[1].startswith('lib') for p in picked)
        rows.append(_row('env', 'encoders', 'ok' if gpu else 'warn', ', '.join(picked), None if gpu else ('doctor.hint_cpu_encode', {})))
    browser = ((project.config.get('render') or {}).get('browser', 'chromium')) if project else 'chromium'
    try:
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as pw:
                b = pw.chromium.launch(**({} if browser == 'chromium' else {'channel': browser}))
                version = b.version
                b.close()
            rows.append(_row('env', 'browser', 'ok', f'playwright {browser} {version}'))
        except Exception as e:                                  # 浏览器没下载、系统里没装……
            rows.append(_row('env', 'browser', 'warn', str(e).strip().splitlines()[0][:120], ('doctor.hint_browser', {})))
    except ImportError:
        rows.append(_row('env', 'browser', 'warn', 'playwright not installed', ('doctor.hint_playwright', {})))
    smi = shutil.which('nvidia-smi')
    gpu = None
    if smi:
        proc = subprocess.run([smi, '--query-gpu=name,memory.total', '--format=csv,noheader'], capture_output=True, text=True, errors='replace')
        gpu = proc.stdout.strip().splitlines()[0] if proc.returncode == 0 and proc.stdout.strip() else None
    rows.append(_row('env', 'gpu', 'ok' if gpu else 'warn', gpu or 'no NVIDIA GPU found', None if gpu else ('doctor.hint_gpu', {})))
    from .art import _font
    cjk = _font(12)[1]
    rows.append(_row('env', 'font', 'ok' if cjk else 'warn', 'CJK font found' if cjk else 'no CJK font', None if cjk else ('doctor.hint_font', {})))
    return rows


def project_backends(project):
    rows = []
    table = project.config.get('backends') or {}
    noncommercial = []
    for kind in KINDS:
        name = table.get(kind) or backends.DEFAULTS.get(kind)
        if kind == 'voice_design' and not name:
            continue
        try:
            b = backends.get(project, kind)
        except backends.BackendError as e:
            rows.append(_row('backends', f'{kind}: {name}', 'fail', str(e), ('doctor.hint_backend', dict(kind=kind))))
            continue
        info = getattr(b, 'info', None)
        if info and info.commercial_use is False:
            noncommercial.append(f'{info.id} ({info.license})')
        checks = b.check() if hasattr(b, 'check') else [dict(status='ok', detail='', hint=None)]
        for c in checks:
            rows.append(_row('backends', f'{kind}: {name}', c['status'], c['detail'], c.get('hint')))
    if noncommercial:
        rows.append(_row('backends', 'license', 'warn', ', '.join(noncommercial), ('doctor.hint_nc', {})))
    return rows


def project_checks(project):
    from . import voice
    from .script.lint import lint
    rows = []
    issues = lint(project.chapters(), project)
    errors = sum(1 for i in issues if i.level == 'error')
    rows.append(_row('project', 'script', 'fail' if errors else 'ok', f'{errors} errors, {len(issues) - errors} warnings',
                     ('doctor.hint_lint', {}) if errors else None))
    _, missing = voice.plan(project)
    if missing:
        rows.append(_row('project', 'voices', 'warn', ', '.join(missing), ('doctor.hint_voices', {})))
    return rows


def run(project=None):
    rows = environment(project)
    if project is not None:
        rows += project_backends(project) + project_checks(project)
    return rows
