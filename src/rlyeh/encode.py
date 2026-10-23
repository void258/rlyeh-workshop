"""压制：按预设把渲染出的成片转成要发布的版本。显卡编码器能用就用（NVENC / QSV / AMF），不能用退回 CPU。

  replay encode share      → build/video/<名>_share.mp4（AV1 10-bit，体积小，适合发出去）
  replay encode compat     → build/video/<名>_compat.mp4（H.264，老设备、网页也能放）
master 是 replay render 自己写的成片（H.264 高画质），不用另外压。

预设写在 replay.toml 的 [encode.<名>]，没写的项用下面 PRESETS 的默认值：
  codec = "h264" | "hevc" | "av1"
  quality = 37               数字越小画质越好、文件越大：显卡编码是 cq / qp，CPU 编码换算成 crf
  encoder = "auto"           auto | nvenc | qsv | amf | cpu
  audio = "copy"             copy | aac
  audio_bitrate = "160k"
  height = 720               缩小到这个高度（不写就不缩）
"""
import shutil
import subprocess

PRESETS = {
    'master': dict(codec='h264', quality=19, encoder='auto'),
    'share': dict(codec='av1', quality=37, encoder='auto', audio='copy'),
    'compat': dict(codec='h264', quality=26, encoder='auto', audio='aac', audio_bitrate='160k'),
}
HW = {'nvenc': {'h264': 'h264_nvenc', 'hevc': 'hevc_nvenc', 'av1': 'av1_nvenc'},
      'qsv': {'h264': 'h264_qsv', 'hevc': 'hevc_qsv', 'av1': 'av1_qsv'},
      'amf': {'h264': 'h264_amf', 'hevc': 'hevc_amf', 'av1': 'av1_amf'}}
CPU = {'h264': 'libx264', 'hevc': 'libx265', 'av1': 'libsvtav1'}
CRF_OFFSET = {'h264': 0, 'hevc': 2, 'av1': 1}     # 显卡的 cq 换成 CPU 的 crf 大致要加多少（AV1 实测：cq37 ≈ crf38）


class EncodeError(RuntimeError):
    pass


def ffmpeg():
    exe = shutil.which('ffmpeg')
    if not exe:
        raise EncodeError('ffmpeg not found; install it and make sure it is on PATH')
    return exe


_works = {}


def works(encoder):
    """编码器列出来不代表能用（例如显卡不支持 AV1 编码）：拿一小段黑屏试一下，结果缓存。"""
    if encoder not in _works:
        cmd = [ffmpeg(), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=256x256:r=30:d=0.3',
               '-c:v', encoder, '-f', 'null', '-']
        try:
            _works[encoder] = subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _works[encoder] = False
    return _works[encoder]


def choose(codec, prefer='auto'):
    """挑编码器：返回 (类别, 编码器名)，类别是 nvenc / qsv / amf / cpu。"""
    if codec not in CPU:
        raise EncodeError(f'unknown codec {codec} (h264 | hevc | av1)')
    kinds = ['nvenc', 'qsv', 'amf'] if prefer == 'auto' else [prefer] if prefer != 'cpu' else []
    for kind in kinds:
        if kind not in HW:
            raise EncodeError(f'unknown encoder {prefer} (auto | nvenc | qsv | amf | cpu)')
        if works(HW[kind][codec]):
            return kind, HW[kind][codec]
    if prefer not in ('auto', 'cpu'):
        raise EncodeError(f'{HW[prefer][codec]} does not work on this machine')
    return 'cpu', CPU[codec]


def video_args(codec, quality, prefer='auto', fps=60):
    kind, enc = choose(codec, prefer)
    q = str(int(quality))
    gop = str(int(fps) * 10)
    if kind == 'nvenc':
        args = ['-c:v', enc, '-preset', 'p7' if codec == 'av1' else 'p6', '-tune', 'hq', '-rc', 'vbr', '-cq', q, '-b:v', '0']
        if codec == 'av1':       # 实测：多看几帧、多用 B 帧、时域滤波，同样画质体积小一截
            args += ['-rc-lookahead', '32', '-bf', '4', '-b_ref_mode', 'middle', '-tf_level', '4', '-g', gop, '-pix_fmt', 'p010le']
        else:
            args += ['-pix_fmt', 'yuv420p']
        return args
    if kind == 'qsv':
        return ['-c:v', enc, '-preset', 'veryslow', '-global_quality', q, '-g', gop] + (['-pix_fmt', 'p010le'] if codec == 'av1' else [])
    if kind == 'amf':
        return ['-c:v', enc, '-quality', 'quality', '-rc', 'cqp', '-qp_i', q, '-qp_p', q, '-g', gop]
    crf = str(int(quality) + CRF_OFFSET[codec])
    if codec == 'av1':
        return ['-c:v', enc, '-preset', '6', '-crf', crf, '-g', gop, '-pix_fmt', 'yuv420p10le']
    return ['-c:v', enc, '-preset', 'slow' if codec == 'h264' else 'medium', '-crf', crf, '-pix_fmt', 'yuv420p']


def preset(project, name):
    cfg = dict(PRESETS.get(name, {}))
    cfg.update((project.config.get('encode') or {}).get(name) or {})
    if 'codec' not in cfg:
        raise EncodeError(f'unknown preset {name}: add [encode.{name}] to replay.toml (codec, quality)')
    return cfg


def command(project, name, src, out, fps=60):
    cfg = preset(project, name)
    cmd = [ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(src)]
    if cfg.get('height'):
        cmd += ['-vf', f'scale=-2:{int(cfg["height"])}:flags=lanczos']
    cmd += video_args(cfg['codec'], cfg.get('quality', 23), cfg.get('encoder', 'auto'), fps)
    if cfg.get('audio', 'copy') == 'copy':
        cmd += ['-c:a', 'copy']
    else:
        cmd += ['-c:a', 'aac', '-b:a', str(cfg.get('audio_bitrate', '160k'))]
    return cmd + ['-movflags', '+faststart', str(out)]


def encode(project, name, src=None, on_line=None):
    """按预设压一版，返回输出路径。"""
    if name == 'master':
        raise EncodeError('master is the file replay render writes; encode share or compat from it')
    pid = (project.config.get('project') or {}).get('id', 'replay')
    video = project.root / 'build' / 'video'
    src = project.root / src if src else video / f'{pid}.mp4'
    if not src.exists():
        raise EncodeError(f'{src} not found; run replay render first')
    out = src.with_name(f'{src.stem}_{name}.mp4')
    fps = int((project.config.get('render') or {}).get('fps', 60))
    cmd = command(project, name, src, out, fps)
    if on_line:
        on_line(' '.join(cmd[cmd.index('-c:v'):cmd.index('-c:v') + 2]))
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if proc.returncode or not out.exists():
        raise EncodeError(f'ffmpeg failed ({proc.returncode}): {proc.stderr[-1500:]}')
    return out
