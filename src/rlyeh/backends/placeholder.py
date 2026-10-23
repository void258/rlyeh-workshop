"""占位后端：不装任何模型也能把流水线跑通（预览节奏、跑测试）。

配音：按字数生成一段长度合适的轻柔音调；声线设计、克隆同理。识别：不识别，质检直接跳过。
生图：画一个简单的剪影 / 渐变底图，差分只改嘴和眉毛。音乐：一段柔和的和弦铺底。
"""
import colorsys
import pathlib
import zlib

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw

from . import BackendInfo

SR = 24000


def tone_wav(path, seconds, pitch):
    t = np.arange(int(SR * seconds)) / SR
    env = np.minimum(1, t / .05) * np.minimum(1, (seconds - t) / .1)
    y = .15 * np.sin(2 * np.pi * pitch * t) * (1 + .3 * np.sin(2 * np.pi * 5 * t)) * env
    sf.write(path, y.astype(np.float32), SR)


def _pitch(key):
    return 180 + (sum(map(ord, key)) % 12) * 15          # 不同的声线给不同的音高，听得出是谁


def _seconds(text):
    chars = sum(1 for ch in text if ch.isalnum())
    return round(min(20, .6 + .2 * chars), 3)


def _placeholder(what):
    return [dict(status='warn', detail='', hint=('doctor.hint_placeholder', dict(what=what)))]


class PlaceholderTTS:
    info = BackendInfo(id='placeholder', kind='tts', license='Apache-2.0')

    def check(self):
        return _placeholder('voice')

    def __init__(self, cfg, project):
        self.cfg = cfg

    def synthesize(self, items, out_dir, on_line=None):
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        done = {}
        for it in items:
            sec = _seconds(it['text'])
            tone_wav(out_dir / f'{it["id"]}.wav', sec, _pitch(str(it.get('voice', ''))))
            done[it['id']] = sec
        return done

    def design(self, jobs, out_dir, on_line=None):
        out = []
        for j in jobs:
            path = pathlib.Path(out_dir) / f'{j["name"]}.wav'
            path.parent.mkdir(parents=True, exist_ok=True)
            sec = _seconds(j['text'])
            tone_wav(path, sec, _pitch(j['name']))
            out.append(dict(name=j['name'], file=str(path), seconds=sec))
        return out

    def clone(self, ref_audio, ref_text, jobs, out_dir, on_line=None):
        return self.design(jobs, out_dir, on_line)


class NoASR:
    info = BackendInfo(id='none', kind='asr', license='Apache-2.0')

    def check(self):
        return [dict(status='warn', detail='', hint=('doctor.hint_no_asr', {}))]

    def __init__(self, cfg, project):
        pass

    def transcribe(self, files, language='zh-CN', on_line=None):
        return None                                        # None = 没有识别，质检跳过


# ───────── 生图 ─────────
SIZES = {'sprite': (512, 768), 'expression': (512, 768), 'item': (384, 384), 'background': (960, 540), 'cg': (960, 540)}


def _color(key, s=.45, v=.75):
    r, g, b = colorsys.hsv_to_rgb((zlib.crc32(key.encode()) % 360) / 360, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def _face(draw, key, skin):
    """在头上画眉眼和嘴；嘴和眉毛的样子随表情变。"""
    k = zlib.crc32(key.encode())
    draw.ellipse((206, 135, 306, 188), fill=skin)                      # 先把原来的嘴、眉盖掉
    draw.rectangle((205, 88, 307, 106), fill=skin)
    for x in (230, 282):
        draw.ellipse((x - 7, 108, x + 7, 122), fill=(30, 26, 24, 255))
        tilt = (k >> 3) % 9 - 4
        draw.line((x - 12, 98 + tilt, x + 12, 98 - tilt), fill=(40, 30, 26, 255), width=4)
    shape = k % 3
    if shape == 0:
        draw.arc((226, 140, 286, 176), 20, 160, fill=(90, 30, 30, 255), width=5)
    elif shape == 1:
        draw.ellipse((241, 148, 271, 176), fill=(90, 30, 30, 255))
    else:
        draw.line((228, 162, 284, 162), fill=(90, 30, 30, 255), width=5)


class PlaceholderImage:
    info = BackendInfo(id='placeholder', kind='image', license='Apache-2.0')
    edits = True
    writes = True

    def check(self):
        return _placeholder('image')

    def __init__(self, cfg, project):
        self.cfg = cfg

    def generate(self, req, target, on_line=None):
        target = pathlib.Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        kind, key = req['kind'], req['id']
        size = SIZES.get(kind, (512, 512))
        if kind == 'expression' and req.get('base'):
            im = Image.open(req['base']).convert('RGBA')
            _face(ImageDraw.Draw(im), key, im.getpixel((256, 75)))
        elif kind in ('sprite', 'expression'):
            im = Image.new('RGBA', size, (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            skin, cloth = (232, 200, 170, 255), (*_color(req['prompt']), 255)          # 提示词一改，颜色就变
            d.rounded_rectangle((136, 230, 376, 790), 90, fill=cloth)
            d.ellipse((186, 50, 326, 210), fill=skin)
            _face(d, key, skin)
        elif kind == 'item':
            im = Image.new('RGBA', size, (0, 0, 0, 0))
            ImageDraw.Draw(im).ellipse((72, 72, 312, 312), fill=(*_color(req['prompt']), 255), outline=(240, 230, 210, 255), width=6)
        else:
            top, bottom = np.array(_color(req['prompt'], .35, .45)), np.array(_color(key, .5, .18))
            t = np.linspace(0, 1, size[1])[:, None, None]
            grad = (top * (1 - t) + bottom * t).astype(np.uint8)
            im = Image.fromarray(np.broadcast_to(grad, (size[1], size[0], 3)).copy(), 'RGB')
            ImageDraw.Draw(im).text((24, 20), key, fill=(235, 225, 210))
        im.save(target)
        return True


# ───────── 音乐 ─────────
MUSIC_SR = 48000
CHORDS = [(220.0, 277.18, 329.63), (196.0, 246.94, 293.66), (174.61, 220.0, 261.63), (164.81, 207.65, 246.94)]


class PlaceholderMusic:
    info = BackendInfo(id='placeholder', kind='music', license='Apache-2.0')
    generates = True
    can_plan = False

    def check(self):
        return _placeholder('music')

    def __init__(self, cfg, project):
        self.max_seconds = float(cfg.get('max_seconds', 20))

    def render(self, cue, seed, out, abc=None, on_line=None):
        """一段柔和的和弦铺底，长度按曲目设定（最多 max_seconds 秒，免得占地方）。"""
        seconds = min(float(cue.get('seconds') or 60), self.max_seconds)
        t = np.arange(int(MUSIC_SR * seconds)) / MUSIC_SR
        chord = CHORDS[(zlib.crc32(cue['id'].encode()) + seed) % len(CHORDS)]
        y = sum(np.sin(2 * np.pi * f * t + i) for i, f in enumerate(chord)) / len(chord)
        y *= .12 * (1 + .25 * np.sin(2 * np.pi * .2 * t)) * np.minimum(1, t / 1.5) * np.minimum(1, (seconds - t) / 1.5)
        out = pathlib.Path(out).with_suffix('.flac')
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, np.stack([y, np.roll(y, 240)], 1).astype(np.float32), MUSIC_SR)
        return out
