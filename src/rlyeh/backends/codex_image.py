"""用 Codex（codex exec）生图。规矩见 docs/zh/agents.md「用 Codex 生图」：

- 提示词由驱动项目的 AI 写好，原样交给 Codex；
- 模型和推理强度必须写明，不留空：留空会用 Codex 自己配置里的默认值，可能是最贵的模型和最高推理强度；
- 固定指令：直接调用一次生图，不读额外说明、不上网、不找参考图、不做额外检查；生成后复制到指定路径，只回复路径；
- 差分、CG 要附图时，说明附图是本项目自己的素材，不是让它去找参考图。

  [harness.codex]
  model = "gpt-6.1-sol"
  effort = "low"

  [backends.codex]            # 都可以不写
  bin = "codex"               # 也可以写成列表，例如 ["node", "D:/codex/bin/codex.js"]
  timeout = 900               # 每张图最多等几秒
  sandbox = "workspace-write" # Codex 要能把图复制进项目目录
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import time

from PIL import Image

from . import BackendError, BackendInfo

INSTRUCTION = {
    'zh-CN': dict(
        head=('你是拉莱耶工坊的生图执行器，只做下面这件事，不做别的：\n'
              '1. 直接调用一次 image_gen 生图工具。提示词原样使用下面「提示词」部分的全部文字，不改写、不翻译、不增删。\n'
              '2. 不要读任何 SKILL.md 或其他说明文件，不要上网搜索，不要找参考图，不要做额外检查，不要生成第二张。\n'
              '3. 生成后，把 {gen} 下刚生成的那张图片复制到：{target}\n'
              '4. 只回复保存路径，不要回复别的内容。'),
        images='附带的图片是本项目自己的素材，不是外部参考：{files}。',
        base='第一张（{base}）是要修改的原图，在它的基础上改图。',
        refs='画面里对应的东西要和参考图保持一致。',
        transparent='输出必须是透明背景的 PNG。',
        prompt='提示词：',
        join='、',
    ),
    'en': dict(
        head=("You are R'lyeh Workshop's image runner. Do exactly this and nothing else:\n"
              '1. Call the image_gen tool once. Use all of the text under "Prompt" below verbatim; do not rewrite, translate, '
              'add or remove anything.\n'
              '2. Do not read any SKILL.md or other instruction files, do not search the web, do not look for reference images, '
              'do not run extra checks, do not generate a second image.\n'
              '3. Then copy the image you just generated under {gen} to: {target}\n'
              '4. Reply with the saved path only.'),
        images='The attached images are assets of this project, not external references: {files}.',
        base='The first one ({base}) is the image to edit; edit on top of it.',
        refs='Keep the matching things in the picture consistent with the reference images.',
        transparent='The output must be a PNG with a transparent background.',
        prompt='Prompt:',
        join=', ',
    ),
}


class CodexImage:
    info = BackendInfo(id='codex', kind='image', license='OpenAI Terms of Use', license_url='https://openai.com/policies/terms-of-use')
    edits = True                 # 能拿底图改图
    writes = True

    def __init__(self, cfg, project):
        self.cfg = cfg
        self.project = project
        harness = (project.config.get('harness') or {}).get('codex') or {}
        self.model = cfg.get('model') or harness.get('model')
        self.effort = cfg.get('effort') or harness.get('effort')
        if not self.model or not self.effort:
            raise BackendError('set model and effort in [harness.codex] of replay.toml (left empty, Codex falls back to '
                               'its own defaults, which may be the most expensive model at the highest effort)')
        b = cfg.get('bin', 'codex')
        self.bin = [str(x) for x in b] if isinstance(b, list) else [str(b)]
        self.bin[0] = shutil.which(self.bin[0]) or self.bin[0]
        self.timeout = int(cfg.get('timeout', 900))
        self.sandbox = cfg.get('sandbox', 'workspace-write')
        self.home = pathlib.Path(cfg.get('home') or os.environ.get('CODEX_HOME') or pathlib.Path.home() / '.codex')

    def instruction(self, req, target):
        tx = INSTRUCTION['en' if self.project.lang.startswith('en') else 'zh-CN']
        parts = [tx['head'].format(gen=(self.home / 'generated_images').as_posix(), target=pathlib.Path(target).as_posix())]
        images = [p for p in [req.get('base'), *req.get('refs', [])] if p]
        if images:
            note = tx['images'].format(files=tx['join'].join(pathlib.Path(p).name for p in images))
            if req.get('base'):
                note += tx['base'].format(base=pathlib.Path(req['base']).name)
            if req.get('refs'):
                note += tx['refs']
            parts.append(note)
        if req.get('transparent'):
            parts.append(tx['transparent'])
        parts.append(f'{tx["prompt"]}\n{req["prompt"]}')
        return '\n\n'.join(parts) + '\n'

    def command(self, req, last_message):
        cmd = [*self.bin, 'exec', '-m', self.model, '-c', f'model_reasoning_effort="{self.effort}"', '--skip-git-repo-check',
               '--ephemeral', '-s', self.sandbox, '-C', str(self.project.root), '-o', str(last_message)]
        for img in [req.get('base'), *req.get('refs', [])]:
            if img:
                cmd.append(f'--image={img}')           # 写成 --image=…：-i 后面可以跟多个文件，会把提示词的 - 也吃掉
        cmd.append('-')                                # 指令从标准输入读，避开命令行长度和编码问题
        return cmd

    def _newest(self, since):
        gen = self.home / 'generated_images'
        files = [p for p in gen.rglob('*') if p.suffix.lower() in ('.png', '.webp', '.jpg', '.jpeg')
                 and p.stat().st_mtime >= since] if gen.exists() else []
        return max(files, key=lambda p: p.stat().st_mtime) if files else None

    def generate(self, req, target, on_line=None):
        target = pathlib.Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        start = time.time() - 1
        with tempfile.TemporaryDirectory(prefix='rlyeh-codex-') as tmp:
            last = pathlib.Path(tmp) / 'last.txt'
            try:
                # 按字节送 UTF-8：text 模式在 Windows 上会改换行符，提示词就不是原样了
                proc = subprocess.run(self.command(req, last), input=self.instruction(req, target).encode('utf-8'),
                                      capture_output=True, timeout=self.timeout)
            except FileNotFoundError as e:
                raise BackendError(f'codex not found ({self.bin[0]}); install the Codex CLI or set [backends.codex] bin') from e
            except subprocess.TimeoutExpired as e:
                raise BackendError(f'codex took longer than {self.timeout}s on {req["id"]}') from e
            reply = last.read_text(encoding='utf-8', errors='replace').strip() if last.exists() else ''
        if not target.exists():                        # Codex 没复制成功（沙箱、路径……）：自己去它的输出目录拿
            newest = self._newest(start)
            if newest:
                shutil.copy2(newest, target)
        if not target.exists():
            tail = (proc.stderr or proc.stdout or b'').decode('utf-8', 'replace')[-1500:]
            raise BackendError(f'codex produced no image for {req["id"]} (exit {proc.returncode}); reply: {reply[:300]}\n{tail}')
        try:
            with Image.open(target) as im:
                im.verify()
        except Exception as e:
            raise BackendError(f'{target} is not a valid image: {e}') from e
        if on_line:
            on_line(f'{req["id"]}: {target.name}')
        return True
