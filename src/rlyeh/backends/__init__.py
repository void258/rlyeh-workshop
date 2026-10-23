"""可替换的后端。规格见 docs/zh/backends.md。

replay.toml 里 [backends] 写每类能力用哪个后端，后端自己的参数写在同名表里：
  [backends]
  tts = "drama3"
  [backends.drama3]
  cli = "D:/vtts/audio.cpp/.../audiocpp_cli.exe"
"""
from dataclasses import dataclass


class BackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackendInfo:
    id: str
    kind: str                         # import | image | voice_design | tts | asr | align | music | sfx | encode
    languages: tuple = ('zh-CN', 'en')
    needs_gpu: bool = False
    vram_gb: float | None = None
    license: str = ''
    license_url: str = ''
    commercial_use: bool | None = None
    attribution: str | None = None
    clone_requires_consent: bool = False
    credit: str = ''                  # 片尾字幕里写的名字；空的不上片尾（占位、手动）


def _registry():
    from . import codex_image, drama3, funasr_fa, manual, placeholder, qwen3_tts, sensevoice, yue2_comfyui
    return {
        'tts': {'drama3': drama3.Drama3, 'placeholder': placeholder.PlaceholderTTS},
        'voice_design': {'qwen3-tts': qwen3_tts.Qwen3TTS, 'placeholder': placeholder.PlaceholderTTS},
        'voice_clone': {'qwen3-tts': qwen3_tts.Qwen3TTS, 'placeholder': placeholder.PlaceholderTTS},
        'asr': {'sensevoice': sensevoice.SenseVoice, 'none': placeholder.NoASR},
        'align': {'funasr-fa': funasr_fa.FunASRAlign},
        'image': {'codex': codex_image.CodexImage, 'manual': manual.ManualImage, 'placeholder': placeholder.PlaceholderImage},
        'music': {'yue2-comfyui': yue2_comfyui.YuE2Comfy, 'manual': manual.ManualMusic, 'placeholder': placeholder.PlaceholderMusic},
    }


DEFAULTS = {'tts': 'placeholder', 'voice_design': 'placeholder', 'voice_clone': None, 'asr': 'none', 'align': 'funasr-fa',
            'image': 'manual', 'music': 'manual'}


def get(project, kind, name=None):
    """按项目配置取后端实例。voice_clone 没配时跟 voice_design 用同一个。"""
    table = project.config.get('backends') or {}
    name = name or table.get(kind) or (table.get('voice_design') if kind == 'voice_clone' else None) or DEFAULTS.get(kind)
    reg = _registry().get(kind, {})
    if name not in reg:
        raise BackendError(f'unknown {kind} backend: {name} (available: {", ".join(reg)})')
    cfg = table.get(name) if isinstance(table.get(name), dict) else {}
    return reg[name](cfg, project)
