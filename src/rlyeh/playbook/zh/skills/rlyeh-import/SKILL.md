---
name: rlyeh-import
description: 拉莱耶工坊项目里导入跑团记录、处理匿名化和隐私、读导入后的事件流时使用。
---

# 导入跑团记录

## 什么时候用

- `replay next` 给出 `import.run`；
- 用户给了新的跑团记录（FVTT 聊天导出、QQ 等聊天软件导出的纯文本）；
- 写剧本前要读记录。

## 步骤

1. 记录文件放进 `logs/raw/`（txt 或 zip；也可以 `replay import <文件…>` 让工具复制进去）。
2. 先看 `replay.toml`：
   - `[players]`：场外玩家名 → 他们扮演的角色 ID，GM 写成 `{ role = "gm" }`；
   - `[import]`：`gm`、`observers`、`renamed`（中途改名的账号）、`session_gap_hours`、`min_session_messages`；
   - `[aliases]`：真名 → 化名，导入时替换。
3. 运行 `replay import`。看输出：读了几个文件、合并去重后多少条、切成几场、哪些发言人没对上玩家（一般就是角色或怪物）。
4. **隐私**：输出里有「可能的隐私信息」（手机号、邮箱、QQ 号、链接）时，逐条告诉用户，问要不要在 `[aliases]` 里换掉或者删掉那几条记录。
5. 提醒用户：做成公开内容前要所有玩家同意。

## 读记录

- 记录可能有几千条，别一次读完：用 `rlyeh_read_log` 分段读（`offset`、`limit`，可以按 `session`、`speaker`、`kind` 筛），或者自己按行读 `logs/events.jsonl`。
- 每条事件：`id`、`ts`、`speaker`、`text`、`kind`（`message` 普通 · `ooc` 场外 · `roll` 掷骰 · `card` 系统卡片）、`role`（`gm` · `player` · `observer` · `character`）、`data`（掷骰算式和结果、卡片字段）、`session`。
- `logs/sessions.json` 有每场的起止时间、条数、发言人，以及被丢掉的测试段。

## 规矩

- `logs/raw/` 导入后不再改；要重新导入就改 `replay.toml` 再运行 `replay import`。
- 不确定某个发言人是玩家、GM 还是角色时，问用户，然后写进 `[players]` / `[import]`。
