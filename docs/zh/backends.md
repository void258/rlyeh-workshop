# 后端与授权

> 规格 v0.1 草稿。英文版：[`docs/en/backends.md`](../en/backends.md)

## 后端接口

每一类能力都是可替换的后端。后端是一个 Python 类，实现对应的接口，并声明自己的**能力**和**授权信息**。

```python
class TTSBackend(Protocol):
    info: BackendInfo                         # 名字、授权、署名、能力

    def design(self, prompt: str, text: str, n: int) -> list[Path]: ...       # 可选：按描述生成候选声线
    def synthesize(self, items: list[Line], ref: VoiceRef, seed: int) -> list[Path]: ...

@dataclass
class BackendInfo:
    id: str                      # "drama3"
    kind: str                    # import | image | voice_design | tts | asr | align | music | sfx | encode
    languages: list[str]         # ["zh-CN", "en"]
    needs_gpu: bool
    vram_gb: float | None
    license: str                 # SPDX 标识或协议名
    license_url: str
    commercial_use: bool | None  # None = 需要用户自己确认
    attribution: str | None      # 要求在片尾署名的文字
    clone_requires_consent: bool # 克隆真人声音是否需要本人同意
```

| 类别 | 接口要点 |
|---|---|
| `import` | 原始文件 → 事件流；支持多份导出合并去重 |
| `image` | 文生图、带参考图生成、改图；能否直接出透明背景 |
| `voice_design` | 按文字描述生成候选声线 |
| `tts` | 按固定参考整句合成；支持语气指示；批量；种子 |
| `asr` | 识别（配音质检、查 BGM 人声） |
| `align` | 强制对齐，给出每个字/词的时间（消音） |
| `music` | 生成乐谱（可选）→ 渲染音频；能否先出乐谱再渲染 |
| `sfx` | 程序合成或从音效包取 |
| `encode` | 按预设压制；检测可用的硬件编码器 |

第三方可以写插件注册新后端，不用改核心代码。

## 第一批后端

授权一栏是 M0 时的了解，**M1 接入每个后端时会对照官方授权逐条核实**，以核实结果为准。

| 类别 | 后端 | 说明 | 授权（待核实） |
|---|---|---|---|
| import | FVTT、纯文本 | 实战已用 FVTT | 本项目代码 |
| image | Codex（`codex exec`） | 实战使用；需要用户自己的 Codex | 受 OpenAI 服务条款约束 |
| image | ComfyUI | 调用用户自己的工作流 | 取决于所用模型 |
| image | 手动导入 | 自己准备图片 | — |
| voice_design | Qwen3-TTS | VoiceDesign 设计声线 + Base 克隆 | 待核实 |
| tts | Fish Audio Drama 3（audio.cpp 本地版） | 实战使用，支持方括号语气指示 | Fish Audio 社区授权：要求署名「Built with Fish Audio」；只能克隆本人同意的声音（合成设计出来的声线可以） |
| asr | SenseVoice | 实战用于配音质检 | 待核实 |
| align | FunASR fa-zh | 实战用于中文消音 | 待核实 |
| asr / align（英文） | Whisper + WhisperX | 英文项目用 | Whisper 为 MIT；WhisperX 待核实 |
| music | YuE2（通过 ComfyUI） | 实战使用；支持先出乐谱再渲染 | 模型权重 CC BY-NC 4.0：**只能非商用**，需要署名 |
| music | 手动导入 | 自己的曲子 | — |
| sfx | 内置合成音效库 | 本项目自己合成 | 随本项目发布（Apache-2.0） |
| encode | ffmpeg | NVENC / AMF / QSV / CPU | 调用用户系统里的 ffmpeg；安装包如果附带 ffmpeg，用 LGPL 构建 |

## 授权原则

1. **不打包、不分发任何模型权重。** 安装向导只告诉用户去哪里下载、放在哪里，或者指定已经装好的位置。
2. **每个后端带授权信息。** Studio 里选后端时显示授权；项目里用到「只能非商用」的后端时，在导出视频前明确提醒。
3. **自动生成署名。** 片尾字幕的「音乐」「配音」「美术」等栏目按实际用到的后端填写；后端要求的署名文字（例如「Built with Fish Audio」）一定会出现。
4. **本项目自己的东西用 Apache-2.0。** 代码、播放器、内置音效库都是。字体使用 OFL 授权的思源宋体 / Noto 系列。

## 隐私与同意

跑团记录是真人的聊天，replay 做出来往往要公开。

- **导入时**：Studio 提示确认所有玩家同意公开；记录里出现的真实姓名、联系方式要提醒处理。
- **匿名化**：`replay.toml` 里可以写玩家名 → 化名的对照表，剧本、字幕、片尾都用化名。
- **声音**：默认用设计出来的合成声线。如果要克隆真人的声音（例如玩家本人），必须有本人同意；后端声明了 `clone_requires_consent` 的，Studio 会要求勾选确认。
- **示例项目**：公开仓库里的示例团全部是编出来的内容，不包含任何真实跑团记录。

## 硬件

- 推荐 NVIDIA 显卡 12 GB 显存以上（实战用 RTX 5070 Ti 16 GB）。各后端在 `BackendInfo` 里写明显存需求，`replay doctor` 据此给建议。
- 没有显卡时，每一类都至少要有一个能用的选择：云端 API、CPU 版本，或者手动导入。
- 显存不够同时跑两个大模型时（例如 YuE2 和 Drama 3），流水线按顺序排队，不并发。
