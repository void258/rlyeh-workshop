"""占位后端：不装任何模型也能把流水线跑通（预览节奏、跑测试）。

配音：按字数生成一段长度合适的轻柔音调；声线设计、克隆同理。识别：不识别，质检直接跳过。
"""
import pathlib

import numpy as np
import soundfile as sf

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


class PlaceholderTTS:
    info = BackendInfo(id='placeholder', kind='tts', license='Apache-2.0')

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

    def __init__(self, cfg, project):
        pass

    def transcribe(self, files, language='zh-CN', on_line=None):
        return None                                        # None = 没有识别，质检跳过
