"""SenseVoice 识别小脚本（在装了 funasr、torch 的 Python 里跑）。

  python sensevoice.py job.json result.json
job: {model, device, language: zh|en, files: [路径]} → result: {texts: {路径: 文字}}
"""
import json
import logging
import pathlib
import re
import sys
import warnings


def main(job_path, out_path):
    job = json.loads(pathlib.Path(job_path).read_text(encoding='utf-8'))
    warnings.filterwarnings('ignore')
    logging.disable(logging.WARNING)
    import torch
    from funasr import AutoModel

    device = job.get('device', 'cuda:0') if torch.cuda.is_available() else 'cpu'
    asr = AutoModel(model=job['model'], disable_update=True, log_level='ERROR', device=device)
    texts = {}
    for i, f in enumerate(job['files'], 1):
        raw = asr.generate(input=f, language=job.get('language', 'zh'), use_itn=False, disable_pbar=True)[0]['text']
        texts[f] = re.sub(r'<\|[^|]*\|>', '', raw).strip()
        if i % 20 == 0:
            print(f'{i}/{len(job["files"])}', flush=True)
    pathlib.Path(out_path).write_text(json.dumps(dict(texts=texts), ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
