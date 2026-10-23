"""SenseVoice（FunASR）语音识别：配音质检、查 BGM 里有没有人声。

  [backends.sensevoice]
  python = "python"          # 装了 funasr 和 torch 的 Python
  model = "C:/Users/me/.cache/modelscope/hub/models/iic/SenseVoiceSmall"   # 不写就用 iic/SenseVoiceSmall（第一次会下载）
  device = "cuda:0"
"""
from . import BackendInfo, worker


class SenseVoice:
    info = BackendInfo(id='sensevoice', kind='asr', languages=('zh-CN', 'en'), needs_gpu=False,
                       license='', license_url='https://github.com/FunAudioLLM/SenseVoice')   # 授权 M1 接入时核实

    def __init__(self, cfg, project):
        self.cfg = cfg

    def check(self):
        out = [worker.import_check(self.cfg.get('python', 'python'), ['torch', 'funasr'], 'funasr torch')]
        model = self.cfg.get('model')
        if model and ('/' in model or '\\' in model) and not model.startswith('iic/'):
            out.append(worker.path_check('model', model, 'sensevoice'))
        elif not model:
            out.append(dict(status='warn', detail='model = iic/SenseVoiceSmall', hint=('doctor.hint_download', {})))
        return out

    def transcribe(self, files, language='zh-CN', on_line=None):
        """返回 {文件路径: 识别文字}。language: zh-CN | en | auto。"""
        lang = {'zh': 'zh', 'en': 'en'}.get(language[:2], 'auto')        # auto：查 BGM 里有没有人声时用
        job = dict(model=self.cfg.get('model', 'iic/SenseVoiceSmall'), device=self.cfg.get('device', 'cuda:0'),
                   language=lang, files=[str(f) for f in files])
        return worker.run(self.cfg.get('python', 'python'), 'sensevoice.py', job, on_line)['texts']
