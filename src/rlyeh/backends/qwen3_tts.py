"""Qwen3-TTS：VoiceDesign 按文字描述设计声线候选；Base 克隆选定的声线念别的话（给旁白补节奏普通的附加参考）。

模型跑在用户自己的 Python 环境里（要有 torch、qwen_tts）：
  [backends.qwen3-tts]
  python = "D:/claude_code_project/qwen3-tts/env/python.exe"
  design_model = "D:/claude_code_project/qwen3-tts/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
  base_model = "D:/claude_code_project/qwen3-tts/models/Qwen3-TTS-12Hz-1.7B-Base"
  device = "cuda:0"
"""
from . import BackendError, BackendInfo, worker

LANG = {'zh-CN': 'Chinese', 'en': 'English'}


class Qwen3TTS:
    info = BackendInfo(id='qwen3-tts', kind='voice_design', needs_gpu=True, vram_gb=5,
                       license='', license_url='https://huggingface.co/Qwen', credit='Qwen3-TTS VoiceDesign')     # 授权 M1 接入时核实

    def __init__(self, cfg, project):
        self.cfg = cfg
        self.project = project
        if not cfg.get('python'):
            raise BackendError('[backends.qwen3-tts] python is not set')

    def _job(self, mode, jobs, out_dir, **extra):
        model = self.cfg.get('design_model' if mode == 'design' else 'base_model')
        if not model:
            raise BackendError(f'[backends.qwen3-tts] {"design_model" if mode == "design" else "base_model"} is not set')
        return dict(mode=mode, model=model, device=self.cfg.get('device', 'cuda:0'), out_dir=str(out_dir),
                    jobs=[dict(j, language=LANG.get(j.get('language'), j.get('language') or 'Chinese')) for j in jobs], **extra)

    def design(self, jobs, out_dir, on_line=None):
        """jobs: [dict(name, instruct, text, seed, language)] → [dict(name, file, seconds)]"""
        return worker.run(self.cfg['python'], 'qwen3_tts.py', self._job('design', jobs, out_dir), on_line)['results']

    def clone(self, ref_audio, ref_text, jobs, out_dir, on_line=None):
        """用 ref_audio 的音色念 jobs 里的 text。"""
        job = self._job('clone', jobs, out_dir, ref_audio=str(ref_audio), ref_text=ref_text)
        return worker.run(self.cfg['python'], 'qwen3_tts.py', job, on_line)['results']
