---
name: rlyeh-import
description: Use in an R'lyeh Workshop project to import session logs, handle anonymization and privacy, and read the imported event stream.
---

# Importing session logs

## When

- `replay next` returns `import.run`;
- the user provides new logs (Foundry VTT chat exports, plain-text exports from chat apps);
- you need to read the log before writing the script.

## Steps

1. Put the logs in `logs/raw/` (txt or zip; or `replay import <files...>` copies them in).
2. Check `replay.toml` first:
   - `[players]`: OOC player names → the character IDs they play; the GM is `{ role = "gm" }`;
   - `[import]`: `gm`, `observers`, `renamed` (accounts renamed mid-campaign), `session_gap_hours`, `min_session_messages`;
   - `[aliases]`: real name → alias, replaced on import.
3. Run `replay import`. Read the output: files read, messages after merging, sessions, and speakers that matched no player (usually characters or monsters).
4. **Privacy**: if the output lists possible private details (phone numbers, emails, QQ numbers, links), go through them with the user and ask whether to replace them via `[aliases]` or drop those messages.
5. Remind the user that every player must agree before anything is published.

## Reading the log

- Logs can run to thousands of events; don't read them all at once. Use `rlyeh_read_log` in pages (`offset`, `limit`, filtered by `session`, `speaker` or `kind`), or read `logs/events.jsonl` line by line.
- Each event: `id`, `ts`, `speaker`, `text`, `kind` (`message` · `ooc` · `roll` · `card`), `role` (`gm` · `player` · `observer` · `character`), `data` (roll formula and result, card fields), `session`.
- `logs/sessions.json` has each session's times, counts and speakers, plus dropped test stretches.

## Rules

- `logs/raw/` isn't edited after import; to re-import, change `replay.toml` and run `replay import` again.
- When unsure whether a speaker is a player, the GM or a character, ask the user and record it in `[players]` / `[import]`.
