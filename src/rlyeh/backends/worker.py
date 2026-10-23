"""调后端小脚本：模型（torch、funasr……）不装进拉莱耶工坊自己的环境，而是用后端配置里写的 Python 去跑
src/rlyeh/workers/ 下的独立脚本。双方用 JSON 文件交换：job.json 进，result.json 出；脚本的标准输出逐行转发给 on_line。
"""
import json
import os
import pathlib
import subprocess
import tempfile

WORKERS = pathlib.Path(__file__).resolve().parent.parent / 'workers'


class WorkerError(RuntimeError):
    pass


def run(python, script, job, on_line=None, env=None, timeout=None):
    with tempfile.TemporaryDirectory(prefix='rlyeh-') as tmp:
        job_path, out_path = pathlib.Path(tmp) / 'job.json', pathlib.Path(tmp) / 'result.json'
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
        cmd = [python, str(WORKERS / script), str(job_path), str(out_path)]
        full_env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', **(env or {}))
        tail = []
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=full_env,
                              text=True, encoding='utf-8', errors='replace') as proc:
            for line in proc.stdout:
                line = line.rstrip('\n')
                tail = (tail + [line])[-40:]
                if on_line:
                    on_line(line)
            proc.wait(timeout=timeout)
        if proc.returncode or not out_path.exists():
            raise WorkerError(f'{script} exited with {proc.returncode}\n' + '\n'.join(tail))
        return json.loads(out_path.read_text(encoding='utf-8'))
