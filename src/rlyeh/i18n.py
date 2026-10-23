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
