---
name: rlyeh-voice
description: 拉莱耶工坊项目里设计声线、生成配音、看配音质检报告、决定改读法或重做、消音时使用。
---

# 声线与配音

## 流程

1. **声线候选**（`voice.design`）：`replay voice design` 按 cast.yaml 的 `voice.design` 给每个角色生成 3 段候选。
2. **选声线**（`voice.pick`，人）：请用户打开 `replay preview` 的 `/voices` 页试听挑选，**不要替用户选**。
3. **配音**（`voice.build`）：`replay voice build`，后台跑（`rlyeh_run_stage voice.build`）。
4. **质检**（`voice.qa`）：`replay voice qa` 把每句识别回文字，按拼音比相似度、看时长。
5. **处理不合格**（`voice.fix`，你）：见下文。
6. **审听**（`voice.review`，人）：请用户在 `/review/voice` 逐句听，标「重做」的句子用 `replay voice redo --marked` 重做。
7. **消音**（`voice.bleep`）：`replay bleep` 把 `{}` 里的词换成「哔」。

## 看质检（voice.fix）

`replay voice qa` 的结果在 `build/voice_qa.json`（或 `rlyeh_qa_report stage=voice failed_only=true`）：`sim` 相似度、`heard` 识别到的字、`seconds` 时长、`too_long`。对每句不合格的：

- **识别器听错了**（同音字、专有名词、语气词）：可以放过。
- **真念错了**：
  - 数字、字母、外号念错 → 在 `replay.toml` 的 `[readings]` 写读法（只改配音不改字幕），再 `replay voice redo --ids <ID>`；
  - 句子太长或重复太多 → 改剧本写法（重复的名字少喊几遍），再重做；
  - 只是这次生成得不好 → `replay voice redo --ids <ID>` 换种子，最多试 5 个种子。
- **太长**（`too_long`，模型停不下来）：几乎都要改写法。

处理完运行 `replay done voice.fix`（剩下的都是可以接受的才这样做）。

## 规矩

| 规则 | 说明 |
|---|---|
| 每个角色只用一段固定参考 | 不要用前几句的生成结果当下一句的参考：误差会累积，还会把参考里的话接着念 |
| 参考音频的文字不能和剧本台词重复 | 否则念到那句时会顺着把参考后半段念出来 |
| 选好的参考太慢太低沉 | 用同一个音色补念几段节奏普通的话当附加参考（`replay voice extra <角色>`，文字写在 `voice.extra_texts`），**不换用户选的音色** |
| 每句整句连续生成 | 语气变成模型的方括号指示；脏话照念，之后再消音 |
| 数字、字母缩写 | 必须在 `[readings]` / `[spoken]` 写读法 |
| 质检门槛 | 相似度 ≥ 0.75，识别字数 ≤ 台词 1.4 倍，时长 ≤ 2.5 秒 + 每字 0.42 秒 |
| 克隆真人声音 | 只有本人同意才可以；默认用设计出来的合成声线 |
