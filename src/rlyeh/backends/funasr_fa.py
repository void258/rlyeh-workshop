"""FunASR 强制对齐（fa-zh）：给出每个汉字的起止时间，用来消音。

  [backends.funasr-fa]
  python = "python"          # 装了 funasr 和 torch 的 Python
  model = "fa-zh"            # 第一次会从 ModelScope 下载（约 150 MB）
"""
from . import BackendInfo, worker


class FunASRAlign:
    info = BackendInfo(id='funasr-fa', kind='align', languages=('zh-CN',), license='',
                       license_url='https://github.com/modelscope/FunASR')   # 授权 M1 接入时核实

    def __init__(self, cfg, project):
        self.cfg = cfg

    def align(self, items, on_line=None):
        """items: [dict(audio, chars)]，chars 是汉字列表。返回每项的 [[起毫秒, 止毫秒], …]，对不上时为 None。"""
        job = dict(model=self.cfg.get('model', 'fa-zh'), device=self.cfg.get('device', 'cuda:0'),
                   items=[dict(audio=str(i['audio']), text=' '.join(i['chars'])) for i in items])
        return worker.run(self.cfg.get('python', 'python'), 'funasr_align.py', job, on_line)['timestamps']
