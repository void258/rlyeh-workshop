# 项目格式

> 规格 v0.1 草稿。英文版：[`docs/en/project-format.md`](../en/project-format.md)

一个 replay 就是一个项目文件夹。Studio、命令行、AI 读写的都是它，没有隐藏的数据库。

## 文件夹结构

```
my-replay/
├── replay.toml          项目配置
├── cast.yaml            角色表
├── logs/                原始记录（只读，导入后不改）
│   ├── raw/             原样保存的导出文件
│   └── events.jsonl     导入后统一格式的事件流
├── script/              剧本，一章一个文件
│   ├── 01-羊角旅馆.md
│   └── 02-树精之森.md
├── voices/              声线：候选试听、选定的固定参考
├── art/
│   ├── prompts/         生图提示词（AI 写，人可改）
│   ├── sprites/<角色ID>/<角色ID>_<表情>.png
│   ├── backgrounds/  cg/  items/
│   ├── _raw/            生成原图备份（差分合成前）
│   └── _overview/       总览图（审核用）
├── audio/
│   ├── voice/<台词ID>.wav        配音原样
│   ├── voice-bleep/<台词ID>.wav  消过音的版本（只有带脏话的句子）
│   ├── bgm/<曲目ID>.flac
│   └── sfx/
├── review/              人工审核结果（Studio 写，AI 读）
├── build/               可再生成的产物：播放器数据、渲染画面、成片
└── .rlyeh/              状态与缓存：state.json、任务记录、日志
```

规则：

- **文件名和 ID 只用 ASCII。** 中文路径在不少工具里会出问题（实战里 audio.cpp 和 Windows 控制台编码都踩过）。角色、曲目、场景在配置里有 ASCII ID，显示名可以是中文。
  - 例外：剧本文件名、人看的文档可以用中文，工具不依赖它们的文件名。
- `logs/raw/` 只读，导入阶段之后不再改动。
- `build/` 和 `.rlyeh/` 可以随时删掉重建，不要放进 git。
- 大文件（音频、图片、视频）建议用 Git LFS 或者不进版本库，Studio 新建项目时会生成合适的 `.gitignore`。

## replay.toml

项目配置。下面是一个完整示例，字段含义见注释。

```toml
spec = "0.1"                      # 规格版本

[project]
id = "yangjiao"                   # ASCII，用于文件名
title = "魔王之影 · 羊角旅馆"
language = "zh-CN"                # 剧本语言：zh-CN / en
session_dates = ["2022-07-20", "2022-07-21"]

# 场外玩家 → 他们扮演的角色（角色 ID 见 cast.yaml）。GM 单独标出
[players]
"小林" = "nongtan"
"阿杰" = "dirk"
"柚子" = "yc116"
"Mia" = "guwa"
"GM:void" = { role = "gm" }

[harness]
default = "claude-code"           # claude-code | codex | dsh

# 给每家 harness 设上限，防止默认用到最贵的模型和最高推理强度
[harness.codex]
model = "gpt-6.1-sol"
effort = "low"

[harness.dsh]
model = "deepseek-v4-flash"

[backends]                        # 每类能力用哪个后端，详见 backends.md
import = "fvtt"
image = "codex"                   # codex | comfyui | openai | manual
voice_design = "qwen3-tts"
tts = "drama3"
asr = "sensevoice"
align = "funasr-fa"
music = "yue2-comfyui"            # yue2-comfyui | ace-step | manual

[backends.drama3]                 # 每个后端自己的参数
cli = "D:/vtts/audio.cpp/build/bin/audiocpp_cli.exe"
model = "D:/vtts/drama3/drama-3-backbone-Q4_K_S.gguf"

[art]
style = "日系动画风格，干净的赛璐璐上色，低饱和暗色调，黑暗奇幻氛围"
always_append = "不要假细节假纹理"  # 每条生图提示词都会加上

# 只改送进 TTS 的读法，不改字幕
[readings]
"116" = "幺幺六"
"d4" = "滴四"

# 消音词在 TTS 里怎么念（念完再整段哔掉）
[spoken]
"cnm" = "操你妈"
"sb" = "傻逼"

[render]
width = 1920
height = 1080
fps = 60

[mix]
voice_rms = 0.1                   # 每句配音归一到的 RMS
bgm_level = 0.3                   # 相对配音
duck = 0.5                        # 说话时 BGM 压到的比例
sfx_level = 0.55
loudness = -16                    # 成片响度（LUFS）

[encode.master]
codec = "h264"
quality = 19

[encode.share]
codec = "av1"
quality = 37                      # NVENC cq；CPU 编码时自动换算成 SVT-AV1 crf
```

### 导入相关的配置

```toml
[import]
system = "demonlord"              # 解析哪个游戏系统的骰子卡片；不写就挨个试
gm = ["void"]                     # GM 的账号名
observers = ["ob1"]               # 旁观者
renamed = { "白石" = "鲨鱼" }     # 中途改过名的账号，统一成一个名字
session_gap_hours = 3             # 两条消息隔这么久就算下一场
min_session_messages = 20         # 少于这么多条的一场当作测试，丢掉

# 匿名化：真名 → 化名。导入时发言人和正文里都会换掉
[aliases]
"张三" = "小林"
```

### 配音相关的配置

```toml
[voice]
candidates = 3                    # 每个角色生成几段候选声线
seeds = [123, 7, 42, 2026, 99]    # 第一个是默认种子，后面的给重做用
min_similarity = 0.75             # 质检：识别结果和台词的相似度下限
max_extra = 1.4                   # 质检：识别出的字数最多是台词的几倍

# 模型类后端跑在用户自己的 Python 环境里（拉莱耶工坊本身不装 torch）
[backends.qwen3-tts]
python = "D:/qwen3-tts/env/python.exe"
design_model = "D:/qwen3-tts/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
base_model = "D:/qwen3-tts/models/Qwen3-TTS-12Hz-1.7B-Base"

[backends.sensevoice]
python = "C:/python311/python.exe"      # 装了 funasr 的 Python
model = "D:/models/SenseVoiceSmall"

[backends.funasr-fa]
python = "C:/python311/python.exe"
```

`tts = "placeholder"`、`voice_design = "placeholder"`、`asr = "none"` 是占位后端：不装任何模型也能把流程跑通，配音会是一段长度合适的音调。

声线相关的文件：

| 文件 | 内容 |
|---|---|
| `voices/candidates/<角色ID>_<n>.wav` + `voices/candidates.json` | 候选声线和它们念的文字 |
| `voices/extra/` + `voices/extra.json` | 同一音色补念的附加参考（`replay voice extra`，文字写在 cast.yaml 的 `voice.extra_texts`） |
| `review/voice-pick.json` | 每个角色选定哪一段（选声线页写入；cast.yaml 里写了 `voice.reference` 的以 cast.yaml 为准） |
| `build/voice_qa.json` | 每句的质检结果：相似度、识别到的文字、时长、是否不合格 |

## 导入后的记录

`replay import` 把 `logs/raw/` 里的所有导出（txt、zip）合并成 `logs/events.jsonl`，每行一条：

```json
{"id": "e000042", "ts": "2022-07-20T21:12:05", "speaker": "浓痰", "text": "19\n1d20 + 3 = 16 + 3 = 19",
 "kind": "roll", "role": "character", "data": {"formula": "1d20 + 3", "total": "19", "detail": "16 + 3"},
 "source": "log.zip/fvtt-log-Wed-Jul-20-2022.txt", "session": 1}
```

| 字段 | 含义 |
|---|---|
| `id` | 事件 ID，按时间顺序编号 |
| `ts` | 时间（ISO 8601）；纯文本记录没写时间时为 `null` |
| `speaker` | 发言人（已经按 `renamed`、`[aliases]` 换过） |
| `text` | 原文 |
| `kind` | `message` 普通消息 · `ooc` 括号开头的场外话 · `roll` 掷骰 · `card` 系统卡片 |
| `role` | `gm` · `player`（`[players]` 里的玩家账号）· `observer` · `character`（其余发言人，一般是角色或怪物） |
| `data` | 掷骰的算式和结果，或者系统卡片解析出的字段（攻击、检定、伤害、法术……） |
| `source` | 来自哪份导出 |
| `session` | 第几场 |

同时写出 `logs/sessions.json`：每场的起止时间、条数、发言人，被丢掉的测试段，以及扫到的疑似隐私信息（手机号、邮箱、QQ 号、链接）。

## cast.yaml

角色表。角色 ID 是 ASCII，`name` 是显示名，可以分语言。

```yaml
characters:
  nongtan:
    name: { zh-CN: 浓痰, en: Phlegm }
    kind: pc                       # pc | npc | narrator | gm
    player: 小林
    color: "#7d9a3c"               # 名牌颜色
    appearance: >                  # 外貌描述，写生图提示词用
      一名魁梧的兽人老兵，灰绿色皮肤，下颌两颗粗短的獠牙……
    expressions:                   # 表情差分：名字 → 描述
      嚣张: 嚣张跋扈，咧嘴露出獠牙，斜着眼看人
      暴怒: 眉毛倒竖紧皱，张大嘴咆哮
      狂笑: 仰着头张大嘴哈哈大笑
    default_expression: 嚣张
    face_rules:                    # 剧本没写［表情］时，按〔语气〕关键词挑差分，先中先用
      - [狂笑, "狂笑|大笑"]
      - [暴怒, "怒|吼|咆哮"]
    sprite:                        # 立绘在画面里的参数（比例都相对立绘宽高）
      scale: 1.0                   # 立绘都画满画框，矮个子要缩小
      head: [0.55, 0.115]          # 头像裁剪中心
      mouth: [0.542, 0.13]         # 嘴的位置（喷火之类的特效从这里出）
    voice:
      gender: male
      design: 粗犷沙哑的中年兽人男声，嗓门大，说话带着蛮横劲
      reference: voices/nongtan_2.wav        # 选定后由 Studio 写入
      reference_text: 老子今天心情好，不跟你们计较……

  narrator:
    name: { zh-CN: 旁白, en: Narrator }
    kind: narrator
    voice: { gender: male, reference: voices/narrator_1.wav, extra_references: [voices/narrator_x1.wav] }

  gm:
    name: { zh-CN: "GM:void", en: "GM:void" }
    kind: gm
    voice: { gender: male, reference: voices/gm_2.wav }
```

## 审核文件 review/

Studio 的审核页写这些文件，AI 和工具只读。每条记录的结构相同：

```json
{
  "c1-0054": { "status": "redo", "note": "全是呻吟声", "by": "void", "at": "2026-10-22T19:43:45+08:00" }
}
```

`status` 取值：`pending`（待审）、`approved`（通过）、`redo`（重做）、`skip`（不处理）。

| 文件 | 内容 | 键 |
|---|---|---|
| `voice-pick.json` | 每个角色选定哪段候选声线 | 角色 ID |
| `voice-review.json` | 逐句审听的标记 | 台词 ID |
| `art-review.json` | 立绘、背景、CG、道具的审核 | 素材路径 |
| `music-review.json` | 每段 BGM 选哪一版 | 曲目 ID |
| `script-review.json` | 可选：剧本审阅意见 | 台词 ID 或幕名 |

## 状态与增量重建 .rlyeh/state.json

每个产物都记下它是由哪些输入生成的（输入内容的哈希）。输入一变，产物就标成**过期**，下次只重做过期的部分。例如：

- 一句台词的文字、语气或角色声线参考变了 → 这句配音过期，消音也跟着过期。
- 某张立绘重画了 → 播放器数据过期，渲染过期。
- 剧本里只改了一个舞台指令 → 配音不受影响，只有播放器数据和渲染过期。

`replay status` 按阶段列出：完成、过期、等待审核、未开始。

```json
{
  "stages": { "voice": { "done": 528, "stale": 3, "review": 1, "todo": 0 } },
  "artifacts": {
    "audio/voice/c1-0054.wav": { "inputs": "sha256:9f2c…", "seed": 7, "qa": { "sim": 0.91, "ok": true } }
  }
}
```

增量重建依赖**稳定的台词 ID**，见 [剧本格式 · 台词 ID](script-format.md#台词-id)。
