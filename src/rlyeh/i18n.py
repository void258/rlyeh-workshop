"""命令行和校验信息的中英文本。

语言优先级：--lang 参数 > 环境变量 RLYEH_LANG > 项目语言 > 系统语言；都没有时用中文。
"""
import locale
import os

MESSAGES = {
    # 校验：错误
    'parse.unknown_line': ('无法解析这一行', 'cannot parse this line'),
    'parse.unclosed_front_matter': ('文件头没有结束的 ---', 'front matter is not closed with ---'),
    'parse.bad_front_matter': ('文件头不是合法的 YAML：{err}', 'front matter is not valid YAML: {err}'),
    'parse.deep_heading': ('只支持 # 章节和 ## 幕，这一级标题会被忽略', 'only # chapter and ## scene headings are supported; this heading is ignored'),
    'lint.unknown_speaker': ('说话人「{who}」不在 cast.yaml 里', 'speaker "{who}" is not in cast.yaml'),
    'lint.unknown_player': ('场外发言人「{who}」不在 replay.toml 的 [players] 里', 'OOC speaker "{who}" is not in [players] of replay.toml'),
    'lint.duplicate_id': ('台词 ID {id} 重复（另一处在 {other}）', 'duplicate line ID {id} (also at {other})'),
    'lint.unknown_directive': ('不认识的指令「{name}」', 'unknown direction "{name}"'),
    'lint.arg_count': ('指令「{name}」需要 {expected} 个参数，这里有 {got} 个', 'direction "{name}" takes {expected} arguments, got {got}'),
    'lint.bad_enum': ('指令「{name}」的{field}不能是「{value}」，可选：{choices}', '"{value}" is not a valid {field} for "{name}"; choose from: {choices}'),
    'lint.not_number': ('指令「{name}」的{field}应该是数字，这里是「{value}」', '{field} of "{name}" should be a number, got "{value}"'),
    # 校验：警告
    'lint.no_tone': ('要配音的台词没写语气', 'voiced line has no tone'),
    'lint.unknown_face': ('角色「{who}」没有「{face}」这个表情差分', 'character "{who}" has no expression "{face}"'),
    'lint.bleep_no_spoken': ('消音词「{word}」是字母缩写，但 [spoken] 里没有读法', 'bleeped abbreviation "{word}" has no spoken form in [spoken]'),
    'lint.no_reading': ('台词里的「{token}」没有在 [readings] 里写读法', '"{token}" in this line has no entry in [readings]'),
    'lint.no_id': ('没有台词 ID（运行 replay ids 补上）', 'no line ID (run replay ids)'),
    'lint.unknown_fx': ('不认识的特效「{value}」', 'unknown effect "{value}"'),
    'lint.unknown_variant': ('不认识的背景变体「{value}」', 'unknown background variant "{value}"'),
    'lint.reference_overlap': ('角色「{who}」的声线参考文本和这句台词重复，配音模型可能把参考接着念下去', 'the voice reference text of "{who}" repeats this line; the voice model may read on with the reference'),
    # 命令行
    'cli.no_project': ('当前目录和上级目录里都没找到 replay.toml', 'no replay.toml found in this or any parent directory'),
    'cli.lint_summary': ('{errors} 个错误，{warnings} 个警告', '{errors} errors, {warnings} warnings'),
    'cli.ids_done': ('补上了 {n} 个台词 ID', 'assigned {n} line IDs'),
    'cli.ids_none': ('所有台词都已经有 ID', 'every line already has an ID'),
    'cli.init_done': ('已创建项目：{path}', 'project created: {path}'),
    'cli.init_exists': ('{path} 里已经有 replay.toml', '{path} already contains replay.toml'),
    'cli.status_chapter': ('第 {n} 章 {title}：{lines} 句台词（{voiced} 句要配音），{scenes} 幕，{directives} 条指令',
                           'Chapter {n} {title}: {lines} lines ({voiced} voiced), {scenes} scenes, {directives} directions'),
    'cli.import_copied': ('复制进 logs/raw/：{names}', 'copied into logs/raw/: {names}'),
    'cli.import_summary': ('读了 {files} 个文件：原始 {raw} 条，合并去重后 {merged} 条，保留 {events} 条，分成 {sessions} 场',
                           'read {files} files: {raw} raw messages, {merged} after merging, {events} kept in {sessions} sessions'),
    'cli.import_session': ('  第 {n} 场 {start} – {end}：{events} 条；发言人：{speakers}',
                           '  session {n} {start} – {end}: {events} events; speakers: {speakers}'),
    'cli.import_dropped': ('丢掉 {n} 段太短的记录（当作测试）', 'dropped {n} short stretches (treated as tests)'),
    'cli.import_unknown': ('这些发言人没对上玩家、GM 或旁观者，按角色处理：{names}',
                           'these speakers match no player, GM or observer and are treated as characters: {names}'),
    'cli.import_private': ('发现 {n} 处可能的隐私信息（手机号、邮箱、QQ 号、链接），公开前请处理：',
                           'found {n} possible private details (phone, email, QQ, links); handle them before publishing:'),
    'cli.import_consent': ('提醒：做成公开内容前，请确认所有玩家都同意。', 'Reminder: make sure every player agrees before publishing.'),
    'cli.status_voice': ('配音：{lines} 句，已生成 {done}，过期 {stale}，未生成 {todo}，质检不合格 {failed}，标记重做 {marked}，共 {minutes} 分钟',
                         'voice: {lines} lines, {done} done, {stale} stale, {todo} to do, {failed} failed QA, {marked} marked for redo, {minutes} min total'),
    'cli.status_no_voice': ('还没选声线：{names}', 'no voice chosen yet: {names}'),
    'cli.voice_design_done': ('已生成 {n} 个角色的候选声线，到 replay preview 的选声线页里挑', 'voice candidates generated for {n} characters; pick them on the voice page of replay preview'),
    'cli.voice_pick_done': ('{cid} 选定：{file}', '{cid} chose: {file}'),
    'cli.voice_extra_done': ('{cid} 补了 {n} 段附加参考', '{cid}: {n} extra references added'),
    'cli.voice_build_done': ('生成了 {n} 句', '{n} lines synthesized'),
    'cli.voice_build_none': ('没有需要生成的句子', 'nothing to synthesize'),
    'cli.voice_qa_done': ('检查 {n} 句，不合格 {bad} 句{ids}', 'checked {n} lines, {bad} failed{ids}'),
    'cli.voice_qa_skipped': ('识别后端是 none，跳过质检', 'ASR backend is "none"; QA skipped'),
    'cli.voice_redo_done': ('重做 {n} 句；仍不合格：{ids}', 'redid {n} lines; still failing: {ids}'),
    'cli.bleep_done': ('消音 {n} 句', '{n} lines bleeped'),
    'cli.bleep_problem': ('  {id}：{reason}', '  {id}: {reason}'),
    'cli.preview_at': ('预览：{url}（Ctrl+C 退出）', 'preview: {url} (Ctrl+C to quit)'),
    'cli.art_jobs_done': ('新写了 {n} 份提示词（art/prompts/），原有 {have} 份没动', 'wrote {n} new prompt files (art/prompts/); {have} existing ones left as they are'),
    'cli.art_needs_prompt': ('这些提示词还有 TODO，写好才能生成：{ids}', 'these prompts still have TODO and are skipped until written: {ids}'),
    'cli.art_run_done': ('生成 {done} 张，收下人工放进来的 {adopted} 张', '{done} images generated, {adopted} hand-placed images adopted'),
    'cli.art_waiting': ('等你放进来（手动后端）：', 'waiting for you to put these in place (manual backend):'),
    'cli.art_blocked': ('  {id}：{reason}', '  {id}: {reason}'),
    'cli.art_compose_done': ('合成了 {n} 张表情差分', '{n} expression variants composited'),
    'cli.art_check_done': ('检查 {n} 张：缺 {missing}，有问题 {warn}；总览图：{sheets}', 'checked {n}: {missing} missing, {warn} with problems; overview sheets: {sheets}'),
    'cli.art_warn': ('  ⚠ {out}：{notes}', '  ⚠ {out}: {notes}'),
    'cli.status_art': ('美术：{jobs} 张，已生成 {done}，过期 {stale}，未生成 {todo}，提示词待写 {needs_prompt}，通过 {approved}，打回 {redo}',
                       'art: {jobs} images, {done} done, {stale} stale, {todo} to do, {needs_prompt} prompts to write, {approved} approved, {redo} rejected'),
    'cli.status_art_unplanned': ('还有 {n} 张图没有提示词文件（运行 replay art jobs）', '{n} images have no prompt file yet (run replay art jobs)'),
    'cli.sfx_done': ('生成了 {n} 个音效：{names}', '{n} sound effects generated: {names}'),
    'cli.sfx_none': ('音效都是最新的', 'all sound effects are up to date'),
    'cli.sfx_problem': ('  {id}：{reason}', '  {id}: {reason}'),
    'cli.sfx_list': ('{id}{mark}：{aliases}', '{id}{mark}: {aliases}'),
    'cli.status_sfx': ('音效：{done} / {total}（项目音效 {custom} 个）', 'sound effects: {done} / {total} ({custom} project sounds)'),
    'cli.music_gen_done': ('生成了 {n} 个版本：{names}', '{n} takes generated: {names}'),
    'cli.music_gen_none': ('每段曲子都有版本了（要多几版用 --takes）', 'every cue has a take (use --takes for more)'),
    'cli.music_waiting': ('  {id}：把曲子放到 {put}', '  {id}: put a track at {put}'),
    'cli.music_problem': ('  {id}：{reason}', '  {id}: {reason}'),
    'cli.music_check_done': ('检查 {n} 个版本，唱出词的 {bad} 个{ids}', 'checked {n} takes, {bad} with vocals{ids}'),
    'cli.music_check_skipped': ('识别后端是 none，跳过人声检查', 'ASR backend is "none"; vocal check skipped'),
    'cli.music_pick_done': ('{cid} 选定：{file}', '{cid} chose: {file}'),
    'cli.status_music': ('BGM：{cues} 段，有版本 {with_takes}，已选 {picked}，唱出词的版本 {vocals} 个',
                         'music: {cues} cues, {with_takes} with takes, {picked} chosen, {vocals} takes with vocals'),
    'cli.error': ('出错：{err}', 'error: {err}'),
    'level.error': ('错误', 'error'),
    'level.warning': ('警告', 'warning'),
}

_lang = None


def detect(project_lang=None):
    env = os.environ.get('RLYEH_LANG')
    if env:
        return env
    if project_lang:
        return project_lang
    loc = (locale.getlocale()[0] or '').lower()
    return 'en' if loc.startswith('en') else 'zh-CN'


def set_lang(lang):
    global _lang
    _lang = lang


def lang():
    return _lang or detect()


def t(key, **kw):
    zh, en = MESSAGES[key]
    text = en if lang().lower().startswith('en') else zh
    return text.format(**kw)
