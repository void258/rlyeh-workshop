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


def probe(python, modules, timeout=240):
    """在后端配置的 Python 里试着 import 这些模块。返回 (能不能用, 说明)。torch 在的话顺便看有没有 CUDA。"""
    code = 'import sys, ' + ', '.join(modules) + '; print(sys.version.split()[0]'
    code += ', "cuda" if torch.cuda.is_available() else "cpu")' if 'torch' in modules else ')'
    try:
        proc = subprocess.run([python, '-c', code], capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=timeout, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    except FileNotFoundError:
        return False, f'{python} not found'
    except subprocess.TimeoutExpired:
        return False, f'{python} timed out importing {", ".join(modules)}'
    if proc.returncode:
        lines = [x for x in proc.stderr.strip().splitlines() if x.strip()]
        return False, lines[-1] if lines else f'exit {proc.returncode}'
    return True, 'Python ' + proc.stdout.strip()


def import_check(python, modules, pip):
    ok, detail = probe(python, modules)
    return dict(status='ok' if ok else 'fail', detail=f'{python}: {detail}',
                hint=None if ok else ('doctor.hint_pip', dict(python=python, pkgs=pip)))


def path_check(key, value, backend):
    ok = bool(value) and pathlib.Path(value).exists()
    return dict(status='ok' if ok else 'fail', detail=f'{key} = {value}',
                hint=None if ok else ('doctor.hint_path', dict(field=key, backend=backend)))


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
