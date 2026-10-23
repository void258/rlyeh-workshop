"""逐帧渲染和离线混音。

无头浏览器打开播放器的渲染模式（?rec），注入虚拟时钟（player/vclock.js），每帧把时间精确推进 1/fps 秒再截图，
截图直接送进 ffmpeg。画面只取决于虚拟时间：不掉帧，每次渲染结果一样，机器慢只是渲染得慢。
声音不在浏览器里放：播放器把配音、音效、BGM 的时间点记下来，渲染完照着这份记录离线混音（说话时压低 BGM、
循环接缝交叉淡化），最后统一响度。

  replay render                              整部：几章同时渲染再拼起来 → build/video/<项目ID>.mp4
  replay render --from c1-0142 --seconds 60  从某句开始只渲染 60 秒 → build/video/<项目ID>_clip.mp4
  replay render --remix                      画面不动，按已有的事件记录重新混音（调了 [mix] 之后用）
要装 playwright（uv sync --extra render 或 pip install "rlyeh-workshop[render]"，再 playwright install chromium）和 ffmpeg。
"""
import asyncio
import base64
import json
import subprocess
import sys
import threading
import time
from importlib import resources

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import encode, player
from .preview import make_server

VIDEO = 'build/video'
VCLOCK = resources.files('rlyeh') / 'player' / 'vclock.js'
SR = 48000


class RenderError(RuntimeError):
    pass


def settings(project):
    r = project.config.get('render') or {}
    m = project.config.get('mix') or {}
    return dict(width=int(r.get('width', 1920)), height=int(r.get('height', 1080)), fps=int(r.get('fps', 60)),
                browser=r.get('browser', 'chromium'), jobs=int(r.get('jobs', 2)), jpeg=int(r.get('jpeg_quality', 92)),
                voice_rms=float(m.get('voice_rms', .1)), bgm_level=float(m.get('bgm_level', .3)), duck=float(m.get('duck', .5)),
                sfx_level=float(m.get('sfx_level', .55)), loudness=float(m.get('loudness', -16)),
                loop_xfade=float(m.get('loop_xfade', 3)))


# ───────── 逐帧渲染画面 ─────────
async def _launch(pw, s):
    args = ['--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--force-device-scale-factor=1', '--hide-scrollbars']
    if sys.platform == 'win32':
        args.append('--use-angle=d3d11')
    launch = dict(headless=True, args=args)
    if s['browser'] != 'chromium':
        launch['channel'] = s['browser']                       # msedge / chrome：用系统里装好的浏览器
    return await pw.chromium.launch(**launch)


async def _page(pw, url, video_path, max_sec, s, project, on_line, tag=''):
    master = encode.preset(project, 'master')
    vargs = encode.video_args(master['codec'], master.get('quality', 19), master.get('encoder', 'auto'), s['fps'])
    ff = subprocess.Popen([encode.ffmpeg(), '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', str(s['fps']),
                           '-c:v', 'mjpeg', '-i', '-', *vargs, str(video_path)], stdin=subprocess.PIPE)
    browser = await _launch(pw, s)
    errors = []
    try:
        page = await browser.new_page(viewport={'width': s['width'], 'height': s['height']}, device_scale_factor=1)
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.add_init_script(script=VCLOCK.read_text(encoding='utf-8'))
        cdp = await page.context.new_cdp_session(page)
        await page.goto(url)
        try:
            await page.wait_for_function('typeof window.__go === "function"', timeout=180000)     # 素材载入完
        except Exception as e:
            raise RenderError('player did not finish loading' + (f': {errors[0]}' if errors else '')) from e
        await page.evaluate('document.fonts.ready.then(() => 0)')
        origin = await page.evaluate('performance.timeOrigin')
        vt0 = await page.evaluate('window.__vt()')
        await page.evaluate('window.__go()')
        n, t_start, dt = 0, time.time(), 1000 / s['fps']
        while True:
            await page.evaluate(f'window.__advance({dt})')
            shot = await cdp.send('Page.captureScreenshot', {'format': 'jpeg', 'quality': s['jpeg'], 'optimizeForSpeed': True})
            try:
                ff.stdin.write(base64.b64decode(shot['data']))
            except (BrokenPipeError, OSError) as e:
                raise RenderError(f'ffmpeg stopped while rendering {video_path.name}') from e
            n += 1
            if errors:
                raise RenderError(f'player error: {errors[0]}')
            if n % s['fps'] == 0:
                if on_line and n % (s['fps'] * 30) == 0:
                    el = time.time() - t_start
                    on_line(f'{tag}{n / s["fps"] / 60:5.1f} min rendered in {el / 60:5.1f} min ({n / el:4.1f} fps)')
                if await page.evaluate('window.__rec.done') or (max_sec and n / s['fps'] >= max_sec):
                    break
        events = await page.evaluate('window.__rec.events')
    finally:
        await browser.close()
        ff.stdin.close()
        ff.wait()
    for e in events:                     # 事件时间：timeOrigin + 虚拟毫秒；视频第 0 帧对应 vt0
        e['t'] -= origin
    return events, vt0 / 1000, n / s['fps'], n


def _playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RenderError('playwright is not installed: uv sync --extra render (or pip install "rlyeh-workshop[render]"), '
                          'then playwright install chromium') from e
    return async_playwright


async def _render_all(jobs, s, project, on_line):
    async_playwright = _playwright()
    sem = asyncio.Semaphore(max(1, s['jobs']))
    async with async_playwright() as pw:
        async def one(url, path, max_sec, tag):
            async with sem:
                return await _page(pw, url, path, max_sec, s, project, on_line, tag)
        return await asyncio.gather(*[one(*j) for j in jobs])


class _Server:
    """渲染期间在本机起一个预览服务，播放器从 /files/build/player/ 载入。"""

    def __init__(self, project):
        self.server = make_server(project, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f'http://127.0.0.1:{self.server.server_address[1]}/files/{player.OUT}/index.html?rec'

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


# ───────── 混音 ─────────
def _load(path, cache):
    key = str(path)
    if key not in cache:
        y, sr = sf.read(str(path), always_2d=True, dtype='float32')
        if sr != SR:
            y = resample_poly(y, SR, sr, axis=0).astype(np.float32)
        if y.shape[1] == 1:
            y = np.repeat(y, 2, 1)
        cache[key] = y[:, :2]
    return cache[key]


def _add(buf, y, at, gain=1.0):
    i = int(at * SR)
    if i >= len(buf) or i + len(y) <= 0:
        return
    if i < 0:
        y, i = y[-i:], 0
    j = min(len(buf), i + len(y))
    buf[i:j] += y[:j - i] * gain


def looped(track, n, xfade):
    """把一首曲子接成 n 个采样那么长，接缝处交叉淡化。"""
    if len(track) >= n:
        return track[:n].copy()
    x = min(int(xfade * SR), len(track) // 2)
    fade = np.linspace(0, 1, x, dtype=np.float32)[:, None]
    seam = track[-x:] * (1 - fade) + track[:x] * fade
    unit = np.concatenate([track[x:-x], seam])           # 第二遍起从 x 处接着放
    out, total = [track[:-x], seam], len(track)
    while total < n:
        out.append(unit)
        total += len(unit)
    return np.concatenate(out)[:n]


def mix(project, events, t0, duration, out_wav):
    """按事件记录混音：配音归一到 voice_rms，BGM 先归一再乘 bgm_level，说话时压到 duck，音效乘 sfx_level。"""
    s = settings(project)
    base = project.root / player.OUT
    n = int(duration * SR) + SR
    voice, fx, music = (np.zeros((n, 2), np.float32) for _ in range(3))
    speaking = np.zeros(n, np.float32)
    cache = {}
    rel = lambda e: e['t'] / 1000 - t0   # noqa: E731
    for e in events:
        if e['type'] == 'voice' and e.get('src'):
            y = _load(base / e['src'], cache)
            g = min(s['voice_rms'] / (float(np.sqrt((y ** 2).mean())) + 1e-6), .95 / (np.abs(y).max() + 1e-6))
            _add(voice, y, rel(e), g)
            a, b = int(rel(e) * SR), int((rel(e) + len(y) / SR) * SR)
            speaking[max(0, a):max(0, min(n, b))] = 1
        elif e['type'] == 'sfx' and e.get('src'):
            _add(fx, _load(base / e['src'], cache), rel(e), e.get('gain', .7) * s['sfx_level'])
    cues = [e for e in events if e['type'] == 'bgm']
    for k, e in enumerate(cues):                # 每次切换：旧曲按新事件的 fade 淡出，新曲淡入
        if not e.get('src'):
            continue
        start = rel(e)
        end = rel(cues[k + 1]) if k + 1 < len(cues) else duration
        fade_out = cues[k + 1]['fade'] if k + 1 < len(cues) else 3
        seg = int((end - start + fade_out) * SR)
        if seg <= 0:
            continue
        track = _load(base / e['src'], cache)
        track = track * (s['voice_rms'] / (float(np.sqrt((track ** 2).mean())) + 1e-6))
        y = looped(track, seg, s['loop_xfade'])
        env = np.ones(seg, np.float32)
        fi, fo = min(int(e['fade'] * SR), seg), min(int(fade_out * SR), seg)
        if fi:
            env[:fi] *= np.linspace(0, 1, fi)
        if fo:
            env[-fo:] *= np.linspace(1, 0, fo)
        _add(music, y * env[:, None], start, s['bgm_level'])
    # 说话时压低 BGM：0.15 秒压下去，0.6 秒放回来
    target = np.where(speaking > 0, s['duck'], 1.0).astype(np.float32)
    atk, rls = np.exp(-64 / (.15 * SR)), np.exp(-64 / (.6 * SR))
    sm = np.empty_like(target)
    v = 1.0
    for i in range(0, n, 64):                                   # 每 64 个采样更新一次，够平滑
        c = atk if target[i] < v else rls
        v = target[i] + (v - target[i]) * c
        sm[i:i + 64] = v
    out = voice + fx + music * sm[:, None]
    peak = float(np.abs(out).max())
    if peak > .98:                                              # 简单软限幅
        out = np.tanh(out / peak * 1.4) / np.tanh(1.4) * .98
    sf.write(str(out_wav), out[:int(duration * SR)], SR, subtype='PCM_24')


def _mux(project, video, wav, final):
    s = settings(project)
    cmd = [encode.ffmpeg(), '-y', '-loglevel', 'error', '-i', str(video), '-i', str(wav),
           '-af', f'loudnorm=I={s["loudness"]}:TP=-1.5:LRA=11', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-ar', '48000',
           '-shortest', '-movflags', '+faststart', str(final)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if proc.returncode:
        raise RenderError(f'ffmpeg mux failed: {proc.stderr[-1500:]}')


# ───────── 入口 ─────────
def render(project, start=None, seconds=0.0, chapters=None, remix=False, name=None, on_line=None):
    """渲染并混音，返回 dict(video, seconds, frames, took)。chapters：只渲染这几章（从 1 数）。"""
    pid = (project.config.get('project') or {}).get('id', 'replay')
    name = name or (f'{pid}_clip' if start or seconds else pid)
    out = project.root / VIDEO
    out.mkdir(parents=True, exist_ok=True)
    silent, events_file = out / f'{name}_video.mp4', out / f'{name}_events.json'
    t_start = time.time()
    s = settings(project)
    frames = None
    if remix:
        if not events_file.exists() or not silent.exists():
            raise RenderError(f'{events_file.name} or {silent.name} not found; render first')
        d = json.loads(events_file.read_text(encoding='utf-8'))
        events, t0, dur = d['events'], d['t0'], d['duration']
    else:
        player.build(project)
        with _Server(project) as url:
            if start or seconds:
                jobs = [(url + (f'#{start}' if start else ''), silent, seconds, '')]
                (events, t0, dur, frames), = asyncio.run(_render_all(jobs, s, project, on_line))
            else:
                total = len(player.data(project)['chapters'])
                picked = [c - 1 for c in chapters] if chapters else list(range(total))
                if not picked or any(not 0 <= c < total for c in picked):
                    raise RenderError(f'chapters must be between 1 and {total}')
                parts_files = [out / f'{name}_ch{c + 1}_video.mp4' for c in picked]
                jobs = [(url + f'&chapter={c}', f, 0, f'ch{c + 1} ') for c, f in zip(picked, parts_files)]
                parts = asyncio.run(_render_all(jobs, s, project, on_line))
                if len(parts_files) == 1:
                    parts_files[0].replace(silent)
                else:
                    lst = out / f'{name}_concat.txt'
                    lst.write_text(''.join(f"file '{f.name}'\n" for f in parts_files), encoding='utf-8')
                    proc = subprocess.run([encode.ffmpeg(), '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst),
                                           '-c', 'copy', str(silent)], capture_output=True, text=True, encoding='utf-8', errors='replace')
                    if proc.returncode:
                        raise RenderError(f'ffmpeg concat failed: {proc.stderr[-1500:]}')
                    lst.unlink()
                    for f in parts_files:
                        f.unlink()
                events, offset = [], 0.0                     # 各章的事件时间接到一条时间轴上
                for ev, t0_, dur_, _ in parts:
                    for e in ev:
                        events.append(dict(e, t=(e['t'] / 1000 - t0_ + offset) * 1000))
                    offset += dur_
                t0, dur, frames = 0.0, offset, sum(p[3] for p in parts)
        events_file.write_text(json.dumps(dict(t0=t0, duration=dur, events=events), ensure_ascii=False), encoding='utf-8')
    wav = out / f'{name}_audio.wav'
    mix(project, events, t0, dur, wav)
    final = out / f'{name}.mp4'
    _mux(project, silent, wav, final)
    return dict(video=final.relative_to(project.root).as_posix(), seconds=round(dur, 2), frames=frames,
                took=round(time.time() - t_start, 1))


# ───────── 主题预览 ─────────
PREVIEW = 'build/theme-preview'
# 样板戏每一步开始后多少毫秒截图（这时动画差不多停稳了）
SHOTS = {'chapter': ('chapter', 2600), 'scene': ('scene', 1300), 'nar': ('narration', 2000), 'line': ('line', 2000),
         'ooc': ('ooc', 1600), 'roll': ('dice', 1700), 'battle-start': ('battle', 1000), 'damage': ('damage', 420),
         'contest': ('contest', 2100), 'item': ('item', 1300), 'round': ('round', 650), 'battle-end': ('victory', 1000),
         'chapter-end': ('chapter-end', 2400), 'credits': ('credits', 9000)}


async def _preview(base, out, s):
    async_playwright = _playwright()
    shots = []
    async with async_playwright() as pw:
        browser = await _launch(pw, s)
        try:
            page = await browser.new_page(viewport={'width': s['width'], 'height': s['height']}, device_scale_factor=1)
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            await page.add_init_script(script=VCLOCK.read_text(encoding='utf-8'))
            # 标题画面：普通播放模式，载入完再走 3 秒让动画到位
            await page.goto(base + '?data=showcase')
            await page.wait_for_selector('.t-load.done', state='attached', timeout=180000)
            for _ in range(40):
                await page.evaluate('window.__advance(100)')
            path = out / '00-title.png'
            await page.screenshot(path=str(path))
            shots.append(path)
            # 样板戏：渲染模式，按每一步开始的时间截图
            await page.goto(base + '?rec&data=showcase')
            await page.wait_for_function('typeof window.__go === "function"', timeout=180000)
            origin = await page.evaluate('performance.timeOrigin')
            await page.evaluate('window.__go()')
            pending, seen, counts = [], 0, {}
            for _ in range(int(180 * 1000 / 50)):                  # 最多走 3 分钟虚拟时间
                vt = await page.evaluate('window.__advance(50)')
                events = await page.evaluate(f'window.__rec.events.slice({seen})')
                seen += len(events)
                for e in events:
                    kind = e.get('name') if e.get('k') == 'do' else e.get('k')
                    if e['type'] == 'step' and kind in SHOTS:
                        label, delay = SHOTS[kind]
                        counts[label] = counts.get(label, 0) + 1
                        pending.append((e['t'] - origin + delay, f'{label}-{counts[label]}' if counts[label] > 1 else label))
                for due, label in [x for x in pending if x[0] <= vt]:
                    pending.remove((due, label))
                    path = out / f'{len(shots):02d}-{label}.png'
                    await page.screenshot(path=str(path))
                    shots.append(path)
                if errors:
                    raise RenderError(f'player error: {errors[0]}')
                if 'credits' in counts and not pending:
                    break
        finally:
            await browser.close()
    return shots


def _sheet(shots, path, cols=3, w=640):
    from PIL import Image, ImageDraw

    from .art import _font
    h, pad, label = w * 9 // 16, 16, 34
    rows = (len(shots) + cols - 1) // cols
    canvas = Image.new('RGB', (cols * (w + pad) + pad, rows * (h + label + pad) + pad), (20, 18, 16))
    draw = ImageDraw.Draw(canvas)
    font, _ = _font(20)
    for i, shot in enumerate(shots):
        x, y = pad + (i % cols) * (w + pad), pad + (i // cols) * (h + label + pad)
        with Image.open(shot) as im:
            canvas.paste(im.convert('RGB').resize((w, h), Image.LANCZOS), (x, y))
        draw.text((x + 4, y + h + 6), shot.stem, fill=(220, 210, 190), font=font)
    canvas.save(path)


def theme_preview(project, theme=None, on_line=None):
    """用当前主题（或指定主题）把每种界面元素截一张图，再拼成一张总览：build/theme-preview/<主题>/。"""
    res = player.build(project, theme=theme)
    player.write_showcase(project)
    out = project.root / PREVIEW / res['theme']
    if out.exists():
        for f in out.glob('*.png'):
            f.unlink()
    out.mkdir(parents=True, exist_ok=True)
    s = settings(project)
    with _Server(project) as url:
        shots = asyncio.run(_preview(url.split('?')[0], out, s))
    sheet = out.parent / f'{res["theme"]}.png'
    _sheet(shots, sheet)
    if on_line:
        on_line(f'{len(shots)} screenshots')
    rel = lambda p: p.relative_to(project.root).as_posix()   # noqa: E731
    return dict(theme=res['theme'], shots=[rel(p) for p in shots], sheet=rel(sheet), warnings=res['warnings'])
