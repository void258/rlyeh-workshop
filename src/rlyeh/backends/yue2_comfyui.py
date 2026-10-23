"""YuE2 音乐生成，通过 ComfyUI 的接口调用（要先开着 ComfyUI，装好 ComfyUI-YuE2 节点）。

YuE2 先规划一份 ABC 乐谱再渲染成音频。纯音乐容易被唱出词来，所以可以只跑规划（十几秒）、看乐谱的人声声部有没有音符，
挑一份人声声部是空的乐谱再渲染（见 rlyeh.music）。模型权重是 CC BY-NC 4.0：只能非商用，要署名。

  [backends.yue2-comfyui]
  url = "http://127.0.0.1:8188"
  vram = "16 GB"              # 12 GB | 16 GB | 24 GB | 32 GB | 48 GB，决定显存预算和是否把模型挪到内存
  model = "YuE2-3B"
  vae = "YuE2-Vae"
  timeout = 1800              # 一段曲子最多等几秒
  vae_tile_frames = 384       # 分块解码的块大小，显存小就改小
"""
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

from . import BackendError, BackendInfo

TOKENS_PER_SECOND = 25            # semantic token 大约每秒 25 个：4000 ≈ 160 秒


class YuE2Comfy:
    info = BackendInfo(id='yue2-comfyui', kind='music', needs_gpu=True, vram_gb=12, license='CC BY-NC 4.0',
                       license_url='https://creativecommons.org/licenses/by-nc/4.0/', commercial_use=False,
                       attribution='Music generated with YuE2 (CC BY-NC 4.0)', credit='YuE2 (m-a-p)')
    generates = True
    can_plan = True

    def __init__(self, cfg, project):
        self.url = str(cfg.get('url', 'http://127.0.0.1:8188')).rstrip('/')
        self.vram = cfg.get('vram', '16 GB')
        self.model = cfg.get('model', 'YuE2-3B')
        self.vae = cfg.get('vae', 'YuE2-Vae')
        self.timeout = float(cfg.get('timeout', 1800))
        self.poll = float(cfg.get('poll', 2))
        self.tile_frames = int(cfg.get('vae_tile_frames', 384))
        self.prefix = (project.config.get('project') or {}).get('id', 'replay')

    def check(self):
        try:
            info = self._api('/object_info/YuE2Sampler')
        except BackendError:
            return [dict(status='warn', detail=f'ComfyUI not reachable at {self.url}', hint=('doctor.hint_comfy', {}))]
        if 'YuE2Sampler' not in info:
            return [dict(status='fail', detail='ComfyUI is running but has no YuE2Sampler node', hint=('doctor.hint_yue2', {}))]
        return [dict(status='ok', detail=f'{self.url} has ComfyUI-YuE2', hint=None)]

    def _api(self, path, data=None):
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise BackendError(f'ComfyUI {path}: HTTP {e.code} {e.read()[:800].decode("utf-8", "replace")}') from e
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise BackendError(f'cannot reach ComfyUI at {self.url}; start ComfyUI first ({e})') from e

    def graph(self, cue, seed, abc=None, plan=False, prefix='rlyeh'):
        sampler = {'pipeline': ['2', 0], 'style': cue['style'], 'lyrics': cue['lyrics'], 'cot': 'full', 'seed': int(seed),
                   'cfg_scale': -1.0, 'ode_steps': 32, 'abc_max_tokens': 4096,
                   'semantic_max_tokens': int(float(cue.get('seconds') or 160) * TOKENS_PER_SECOND),
                   'abc_temperature': 0.7, 'semantic_temperature': 1.0, 'save_flac': False, 'save_abc': False,
                   'vae_decode': 'tiled', 'vae_tile_frames': self.tile_frames, 'abort_after_plan': plan}
        if abc:
            sampler['abc'] = abc
        g = {
            '1': {'class_type': 'YuE2MemoryPreset', 'inputs': {'vram': self.vram}},
            '2': {'class_type': 'YuE2Loader', 'inputs': {'model': self.model, 'vae': self.vae, 'device': 'cuda',
                                                         'memory_budget_gib': ['1', 0], 'offload_ar': ['1', 1], 'offline': True,
                                                         'attention_backend': 'auto', 'quantization': 'none'}},
            '3': {'class_type': 'YuE2Sampler', 'inputs': sampler},
        }
        if plan:
            g['4'] = {'class_type': 'PreviewAny', 'inputs': {'source': ['3', 1]}}      # 输出 1 是 ABC 乐谱
        else:
            g['4'] = {'class_type': 'SaveAudio', 'inputs': {'audio': ['3', 0], 'filename_prefix': prefix}}
        return g

    def _wait(self, graph, on_line):
        pid = self._api('/prompt', {'prompt': graph})['prompt_id']
        start = time.time()
        while time.time() - start < self.timeout:
            time.sleep(self.poll)
            h = self._api(f'/history/{pid}').get(pid)
            if not h:
                continue
            st = h.get('status') or {}
            if st.get('status_str') == 'error':
                raise BackendError('ComfyUI error: ' + json.dumps(st, ensure_ascii=False)[:1500])
            if st.get('completed') or '4' in (h.get('outputs') or {}):
                return h.get('outputs') or {}
        raise BackendError(f'ComfyUI did not finish within {self.timeout:.0f}s')

    def plan(self, cue, seed, on_line=None):
        """只跑乐谱规划，返回 ABC 文本。"""
        out = self._wait(self.graph(cue, seed, plan=True), on_line)
        text = (out.get('4') or {}).get('text') or []
        if not text:
            raise BackendError('ComfyUI returned no score; is ComfyUI-YuE2 up to date?')
        return text[0] if isinstance(text, list) else str(text)

    def render(self, cue, seed, out, abc=None, on_line=None):
        """渲染成音频（给了 abc 就照这份乐谱），存到 out（扩展名按 ComfyUI 给的来）。"""
        res = self._wait(self.graph(cue, seed, abc, prefix=f'{self.prefix}/{cue["id"]}_s{seed}'), on_line)
        audio = ((res.get('4') or {}).get('audio') or [None])[0]
        if not audio:
            raise BackendError('ComfyUI returned no audio')
        q = urllib.parse.urlencode(dict(filename=audio['filename'], subfolder=audio.get('subfolder', ''),
                                        type=audio.get('type', 'output')))
        try:
            with urllib.request.urlopen(f'{self.url}/view?{q}', timeout=120) as r:
                data = r.read()
        except urllib.error.URLError as e:
            raise BackendError(f'cannot download {audio["filename"]} from ComfyUI: {e}') from e
        out = pathlib.Path(out).with_suffix(pathlib.Path(audio['filename']).suffix or '.flac')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return out
