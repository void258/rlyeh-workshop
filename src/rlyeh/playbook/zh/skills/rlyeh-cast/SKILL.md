---
name: rlyeh-cast
description: 拉莱耶工坊项目里写或补全角色表 cast.yaml（外貌、表情差分、名牌颜色、语气→表情规则、声线描述）时使用。
---

# 角色表

`cast.yaml` 里每个角色一条，角色 ID 只用 ASCII。格式见 [项目格式 · cast.yaml](https://github.com/void258/rlyeh-workshop/blob/main/docs/zh/project-format.md#castyaml)。

## 什么时候用

`replay next` 给出 `cast.write`：剧本里有没登记的说话人，或者有角色缺外貌、表情差分、声线描述。

## 每个角色写什么

```yaml
characters:
  arlo:
    name: { zh-CN: 阿洛, en: Arlo }
    kind: pc                      # pc | npc | narrator | gm
    player: 小林                   # pc 才写，对应 [players]
    color: "#c9a23a"              # 名牌颜色，角色之间要分得开
    appearance: 二十岁左右的见习冒险者，棕色短发，旧皮甲……
    expressions:                  # 3–6 个表情差分：名字 → 样子
      平静: 神情平静，嘴角放松
      警惕: 眉头微皱，眼神警觉
      惊讶: 眼睛睁大，嘴巴微张
    default_expression: 平静
    face_rules:                   # 剧本没写［表情］时按〔语气〕挑，先中先用
      - [惊讶, "惊|吓"]
      - [警惕, "压低声音|警惕|小心"]
    sprite: { scale: 1.0, head: [0.5, 0.17] }   # 矮个子 scale 小一点；mouth 写了喷火从嘴里出
    voice: { gender: male, design: 二十岁左右的青年男声，干净有朝气，紧张时语速变快 }
```

- 旁白（`kind: narrator`）和 GM（`kind: gm`）只要名字和声线。
- 没有现成设定时，按剧情推断外貌、年龄、性别，并**告诉用户哪些是你推断的**，请用户确认（实战里「这个角色其实是女性」「改成十一二岁的小男孩」都是这一步改的）。
- 外貌写具体：体型、发型发色、服装、标志性物品、配色——生图提示词直接用它。
- 表情差分挑这个角色在剧本里真会用到的情绪；`face_rules` 的关键词从剧本里常见的〔语气〕里找。
- 声线描述写性别、年龄、音色、说话习惯；声线要符合角色性别；不用方言声线；角色之间靠不同的声音区分。

## 做完

`replay lint` 没有「说话人不在 cast.yaml」的错误，`replay next` 里 `cast.write` 变成 done。cast.yaml 改了外貌或表情后运行 `replay art jobs` 给新表情补提示词（已有的提示词不会被覆盖，要改得自己改）。
