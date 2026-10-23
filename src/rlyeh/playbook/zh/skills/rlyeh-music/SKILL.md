---
name: rlyeh-music
description: 拉莱耶工坊项目里写曲目表 music.yaml、项目音效 sfx.yaml、生成和检查 BGM 时使用。
---

# 音乐与音效

## 曲目表（music.sheet）

剧本里 `【BGM：港口】` 用到的每个名字都要在 `music.yaml` 里有一段：

```yaml
battle: battle                    # 战斗开始时自动切的曲目
cues:
  harbor:                         # 曲目 ID，只用 ASCII
    name: { zh-CN: 港口, en: Harbor }
    style: Instrumental, no vocals, foggy night harbor, celesta and harp ostinato, low cello drone, mysterious and lonely, 76 BPM
    seconds: 150
  ending:
    name: 片尾曲
    style: Mandarin Chinese, dark fantasy anime ending theme, warm clear female vocal, acoustic guitar, piano, 88 BPM
    lyrics: |
      [Verse]
      ……
```

- 按幕和剧情的情绪写：每段写风格、配器、情绪、速度（BPM）。YuE2 用英文写效果更好。
- 纯音乐写上 `Instrumental, no vocals`，不写 `lyrics`。
- 片尾曲可以是带词的歌：歌词按这次冒险写，分 `[Verse]`、`[Chorus]` 段。
- 战斗曲叫 `battle`（或在 `battle:` 指定），战斗开始自动切，不用在剧本里写。

## 生成和挑选

1. `replay music gen`（后台跑，一段几分钟）：纯音乐会先只出乐谱，换种子直到人声声部一个音符都没有再渲染。**开始前告诉用户要生成几段、大概多久**；YuE2 要先开着 ComfyUI。
2. `replay music check`：语音识别检查有没有唱出词；`build/music_check.json` 里 `clean: false` 的版本不用。
3. **挑一版**（`music.pick`，人）：请用户在 `/review/music` 试听挑选。

## 音效（sfx.yaml）

内置的合成音效（骰子、打击、破门、锣、幽灵、火焰……）不用写；`replay sfx --list` 列出全部名字。剧本里 `【音效：…】` 要用的项目音效写进 `sfx.yaml`：

```yaml
sounds:
  wail:
    name: 雾魇的哀嚎
    voice: wraith                 # 用这个角色的声线生成
    tone: 凄厉地哀嚎，像风穿过破窗
    text: 啊——呜——
    max_seconds: 2.5
    space: room                   # dry · room · next-room · behind-door · upstairs
    min_gap: 0                    # 两次播放至少隔几秒
```

## 规矩

- YuE2 的模型权重是 CC BY-NC 4.0：**只能非商用**，片尾会自动署名；用户要商用就换手动后端，用自己有授权的曲子。
- 同一个音效重复太多会腻：围城、僵尸呻吟这类设 `min_gap`（例如 40 秒）。
