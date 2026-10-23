"""估算对齐：不用模型，按字数把有声段平均分给每个字（中文）或每个词（英文），再往两边多留一点。

粗略，但不用装任何东西，中英文都能用；英文项目消音、示例团用它。要准就换 funasr-fa（中文）。
  [backends]
  align = "estimate"
"""
import numpy as np
import soundfile as sf

from . import BackendInfo

MARGIN = 80          # 每个字前后多盖的毫秒数：估算有误差，宁可多盖一点


class EstimateAlign:
    info = BackendInfo(id='estimate', kind='align', languages=('zh-CN', 'en'), license='Apache-2.0')

    def __init__(self, cfg, project):
        self.margin = int(cfg.get('margin', MARGIN))

    def align(self, items, on_line=None):
        """items: [dict(audio, chars)]，chars 是要对齐的单位（汉字或英文词）。返回每项的 [[起毫秒, 止毫秒], …]。"""
        out = []
        for it in items:
            y, sr = sf.read(str(it['audio']), always_2d=True, dtype='float32')
            m = np.abs(y).mean(1)
            hop = max(1, int(sr * .02))
            env = np.array([m[i:i + hop].mean() for i in range(0, len(m), hop)]) if len(m) else np.zeros(1)
            voiced = np.nonzero(env > max(float(env.max()) * .08, 1e-4))[0]
            start, end = (voiced[0] * hop / sr, (voiced[-1] + 1) * hop / sr) if voiced.size else (0.0, len(m) / sr)
            weights = [max(1, len(u)) for u in it['chars']] or [1]
            total, t, stamps = sum(weights), start, []
            for w in weights:
                d = (end - start) * w / total
                stamps.append([max(0, round(t * 1000) - self.margin), round((t + d) * 1000) + self.margin])
                t += d
            out.append(stamps)
        return out

    def check(self):
        return [dict(status='ok', detail='no model needed (rough timing)', hint=None)]
