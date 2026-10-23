"""Qwen3-TTS 后端小脚本（在装了 torch、qwen_tts 的 Python 里跑，不依赖拉莱耶工坊本身）。

  python qwen3_tts.py job.json result.json
job: {mode: design|clone, model, device, out_dir, jobs: [{name, text, language, seed, instruct?}], ref_audio?, ref_text?}
"""
import json
import pathlib
import sys
import time


def main(job_path, out_path):
    job = json.loads(pathlib.Path(job_path).read_text(encoding='utf-8'))
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    model = Qwen3TTSModel.from_pretrained(job['model'], device_map=job.get('device', 'cuda:0'), dtype=torch.bfloat16)
    out_dir = pathlib.Path(job['out_dir'])
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = None
    if job['mode'] == 'clone':
        prompt = model.create_voice_clone_prompt(ref_audio=job['ref_audio'], ref_text=job['ref_text'])
    results = []
    for j in job['jobs']:
        torch.manual_seed(int(j.get('seed', 1000)))
        t0 = time.time()
        if job['mode'] == 'design':
            wavs, sr = model.generate_voice_design(text=j['text'], language=j['language'], instruct=j['instruct'])
        else:
            wavs, sr = model.generate_voice_clone(text=j['text'], language=j['language'], voice_clone_prompt=prompt)
        path = out_dir / f'{j["name"]}.wav'
        sf.write(path, wavs[0], sr)
        sec = round(len(wavs[0]) / sr, 3)
        results.append(dict(name=j['name'], file=str(path), seconds=sec))
        print(f'{j["name"]}: {sec:.1f}s ({time.time() - t0:.1f}s)', flush=True)
    pathlib.Path(out_path).write_text(json.dumps(dict(results=results), ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
