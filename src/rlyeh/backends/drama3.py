"""Fish Audio Drama 3，audio.cpp 本地版（GGUF）。

一次会话用 --request-sequence 跑一批请求；参考音频在请求里按句传。台词开头的〔语气〕变成 Drama 3 的 [方括号指示]。
audio.cpp 碰到中文路径容易出错，所以参考副本和原始输出都放在纯英文的工作目录里。

  [backends.drama3]
  cli = "D:/vtts/audio.cpp/build/windows-cuda-release/bin/audiocpp_cli.exe"
  model = "D:/vtts/drama3/drama-3-backbone-8bit-F32-routers-experts-Q4_K_S.gguf"
  dll_dirs = ["D:/vtts/cuda128/Library/bin"]     # 可选：加进 PATH 的 DLL 目录
  cwd = "D:/vtts/drama3"                          # 可选：运行目录
  work_dir = "C:/rlyeh-work/drama3"              # 可选：英文工作目录，默认在系统临时目录下
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import soundfile as sf

from . import BackendError, BackendInfo, worker

GEN = {'max_tokens': '1400', 'temperature': '0.7', 'top_p': '0.7'}
SESSION = {'cpu_expert_layers': '0', 'context_length': '4096', 'disk_experts': 'true', 'expert_cache_size': '64'}


class Drama3:
    # 授权条款以 Fish Audio 官方为准（M1 接入时核实）：要求署名，只能克隆本人同意的声音
    info = BackendInfo(id='drama3', kind='tts', needs_gpu=True, vram_gb=6, license='Fish Audio Community License',
                       attribution='Built with Fish Audio', clone_requires_consent=True, credit='Fish Audio Drama 3')

    def __init__(self, cfg, project):
        self.cfg = cfg
        self.project = project
        for key in ('cli', 'model'):
            if not cfg.get(key):
                raise BackendError(f'[backends.drama3] {key} is not set')
        pid = (project.config.get('project') or {}).get('id', 'project')
        self.work = pathlib.Path(cfg.get('work_dir') or pathlib.Path(tempfile.gettempdir()) / 'rlyeh' / pid / 'drama3')
        self.chunk = int(cfg.get('chunk', 80))
        self.gen = {**GEN, **{k: str(v) for k, v in (cfg.get('gen') or {}).items()}}
        self.session = {**SESSION, **{k: str(v) for k, v in (cfg.get('session') or {}).items()}}

    def check(self):
        out = [worker.path_check(k, self.cfg.get(k), 'drama3') for k in ('cli', 'model')]
        out += [worker.path_check('dll_dirs', d, 'drama3') for d in self.cfg.get('dll_dirs') or []]
        return out

    def _ascii_ref(self, path):
        """参考音频复制一份到英文目录，文件名用内容哈希。"""
        path = pathlib.Path(path)
        refs = self.work / 'refs'
        refs.mkdir(parents=True, exist_ok=True)
        dst = refs / (hashlib.sha1(path.read_bytes()).hexdigest()[:16] + path.suffix.lower())
        if not dst.exists():
            shutil.copy2(path, dst)
        return dst.as_posix()

    def request(self, item):
        """item: dict(id, text, tone, refs=[(音频, 文本)], seed, max_tokens=可选)。返回 audio.cpp 的一条请求。"""
        refs = [dict(audio_path=self._ascii_ref(a), text=t) for a, t in item['refs']]
        text = (f'[{item["tone"]}]' if item.get('tone') else '') + item['text']
        gen = dict(self.gen, max_tokens=str(item['max_tokens'])) if item.get('max_tokens') else self.gen   # 音效限短，免得拖一大段
        return dict(id=item['id'], seed=int(item['seed']), text=text,
                    options=dict(gen, references=json.dumps(refs, ensure_ascii=False)))

    def _run(self, requests, name, on_line):
        raw = self.work / 'raw'
        raw.mkdir(parents=True, exist_ok=True)
        seq = self.work / f'{name}.json'
        seq.write_text(json.dumps({'requests': requests}, ensure_ascii=False), encoding='utf-8')
        cmd = [self.cfg['cli'], '--task', 'tts', '--family', 'fish_drama3', '--backend', self.cfg.get('device', 'cuda'),
               '--mode', 'offline', '--model', self.cfg['model'], '--request-sequence', str(seq), '--out-dir', str(raw),
               '--threads', str(self.cfg.get('threads', 10))]
        for k, v in self.session.items():
            cmd += ['--session-option', f'fish_drama3.{k}={v}']
        env = dict(os.environ)
        dirs = [*(self.cfg.get('dll_dirs') or []), str(pathlib.Path(self.cfg['cli']).parent)]
        env['PATH'] = os.pathsep.join(dirs + [env.get('PATH', '')])
        log = self.work / f'{name}.log'
        with open(log, 'w', encoding='utf-8', errors='replace') as f:
            proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=self.cfg.get('cwd') or None)
        if proc.returncode:
            tail = log.read_text(encoding='utf-8', errors='replace')[-1500:]
            raise BackendError(f'audiocpp_cli exited with {proc.returncode} (log: {log})\n{tail}')
        return raw

    def synthesize(self, items, out_dir, on_line=None):
        """逐批合成，输出 out_dir/<id>.wav。返回 {id: 秒数}。"""
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        done = {}
        for c in range(0, len(items), self.chunk):
            chunk = items[c:c + self.chunk]
            raw = self._run([self.request(it) for it in chunk], f'seq_{c // self.chunk:03d}', on_line)
            for it in chunk:
                src = raw / f'{it["id"]}.wav'
                if src.exists():
                    shutil.copy2(src, out_dir / f'{it["id"]}.wav')
                    done[it['id']] = round(sf.info(str(src)).duration, 3)
                    if on_line:
                        on_line(f'{it["id"]} {done[it["id"]]:.1f}s {it["text"][:24]}')
        return done
