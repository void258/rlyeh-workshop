import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from rlyeh import encode, render


def test_looped():
    track = np.ones((48000 * 4, 2), np.float32)
    y = render.looped(track, 48000 * 11, 1.0)
    assert len(y) == 48000 * 11 and np.allclose(y, 1, atol=1e-6)          # 常数信号接缝处交叉淡化后还是常数
    assert len(render.looped(track, 100, 1.0)) == 100


def tone(f, seconds, sr=48000, amp=.1):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def level(y, f, sr=48000):
    spec = np.abs(np.fft.rfft(y[:, 0] * np.hanning(len(y))))
    return spec[int(round(f * len(y) / sr))]


def test_mix_ducks_bgm_under_voice(make_project):
    proj = make_project()
    base = proj.root / 'build' / 'player' / 'audio'
    base.mkdir(parents=True)
    sf.write(base / 'bgm.wav', tone(200, 6), 48000)
    sf.write(base / 'voice.wav', tone(1000, 1.5, amp=.3), 24000 * 2)
    sf.write(base / 'hit.wav', tone(3000, .2), 48000)
    events = [dict(t=0, type='bgm', cue='m', src='audio/bgm.wav', fade=0), dict(t=2000, type='voice', src='audio/voice.wav', sec=1.5),
              dict(t=5000, type='sfx', name='hit', src='audio/hit.wav', gain=1.0)]
    out = proj.root / 'mix.wav'
    render.mix(proj, events, 0, 6, out)
    y, sr = sf.read(out)
    assert sr == 48000 and len(y) == 6 * 48000
    seg = lambda a, b: y[int(a * sr):int(b * sr)]   # noqa: E731
    before, during = level(seg(1.0, 1.5), 200), level(seg(2.8, 3.3), 200)
    assert .4 < during / before < .6                                        # 说话时 BGM 压到一半
    assert level(seg(2.8, 3.3), 1000) > level(seg(1.0, 1.5), 1000) * 50    # 配音在 2 秒处进来
    assert level(seg(5.0, 5.2), 3000) > level(seg(4.5, 4.7), 3000) * 20    # 音效在 5 秒处


def test_encode_args(make_project, monkeypatch):
    proj = make_project()
    monkeypatch.setattr(encode, 'ffmpeg', lambda: 'ffmpeg')
    monkeypatch.setattr(encode, 'works', lambda enc: enc.endswith('nvenc'))
    cmd = encode.command(proj, 'share', 'in.mp4', 'out.mp4')
    assert cmd[cmd.index('-c:v') + 1] == 'av1_nvenc' and 'p010le' in cmd and cmd[cmd.index('-cq') + 1] == '37'
    assert cmd[cmd.index('-c:a') + 1] == 'copy'
    monkeypatch.setattr(encode, 'works', lambda enc: False)                # 没有显卡编码器：退回 CPU，cq 换成 crf
    cmd = encode.command(proj, 'share', 'in.mp4', 'out.mp4')
    assert cmd[cmd.index('-c:v') + 1] == 'libsvtav1' and cmd[cmd.index('-crf') + 1] == '38'
    cfg = proj.root / 'replay.toml'
    cfg.write_text(cfg.read_text(encoding='utf-8') + '\n[encode.small]\ncodec = "h264"\nquality = 28\nheight = 720\naudio = "aac"\n',
                   encoding='utf-8')
    from rlyeh.project import Project
    cmd = encode.command(Project(proj.root), 'small', 'in.mp4', 'out.mp4')
    assert 'scale=-2:720:flags=lanczos' in cmd and cmd[cmd.index('-c:v') + 1] == 'libx264' and cmd[cmd.index('-c:a') + 1] == 'aac'
    with pytest.raises(encode.EncodeError):
        encode.encode(proj, 'master')
    with pytest.raises(encode.EncodeError):
        encode.preset(proj, 'nope')


def _can_render():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return bool(shutil.which('ffmpeg'))
    except Exception:
        return False


@pytest.mark.skipif(not _can_render(), reason='needs playwright with chromium and ffmpeg')
def test_render_clip(full_project):
    proj = full_project()
    res = render.render(proj, seconds=6)
    assert res['video'] == 'build/video/demo_clip.mp4' and res['frames'] == 360
    video = proj.root / res['video']
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(video)],
                           capture_output=True, text=True)
    assert abs(float(probe.stdout) - 6) < .2
    events = (proj.root / 'build/video/demo_clip_events.json').read_text(encoding='utf-8')
    assert '"sfx"' in events and '"scene"' in events
    res = render.render(proj, seconds=6, remix=True)                        # 只重新混音
    assert res['frames'] is None and video.exists()
