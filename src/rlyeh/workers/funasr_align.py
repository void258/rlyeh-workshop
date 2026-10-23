"""FunASR 强制对齐小脚本（在装了 funasr、torch 的 Python 里跑）。

  python funasr_align.py job.json result.json
job: {model: fa-zh, device, items: [{audio, text: "字 字 字"}]} → result: {timestamps: [[[起, 止], …] 或 null]}
"""
import json
import logging
import pathlib
import sys
import warnings


def main(job_path, out_path):
    job = json.loads(pathlib.Path(job_path).read_text(encoding='utf-8'))
    warnings.filterwarnings('ignore')
    logging.disable(logging.WARNING)
    import torch
    from funasr import AutoModel

    device = job.get('device', 'cuda:0') if torch.cuda.is_available() else 'cpu'
    fa = AutoModel(model=job.get('model', 'fa-zh'), disable_update=True, log_level='ERROR', device=device)
    out = []
    for it in job['items']:
        r = fa.generate(input=(it['audio'], it['text']), data_type=('sound', 'text'), disable_pbar=True)[0]
        ts = r.get('timestamp')
        out.append(ts if ts and len(ts) == len(it['text'].split()) else None)
    pathlib.Path(out_path).write_text(json.dumps(dict(timestamps=out), ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
