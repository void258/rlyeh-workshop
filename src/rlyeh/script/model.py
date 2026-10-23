"""剧本解析结果的数据结构。"""
from dataclasses import dataclass, field


@dataclass
class Issue:
    level: str                  # error | warning
    code: str                   # i18n 键，例如 lint.no_tone
    file: str
    line: int                   # 行号，从 1 开始；0 表示整个文件
    message: str

    def as_dict(self):
        return dict(level=self.level, code=self.code, file=self.file, line=self.line, message=self.message)


@dataclass
class Item:
    kind: str                   # scene | directive | line | narration | ooc
    line_no: int
    raw: str


@dataclass
class Scene(Item):
    title: str = ''


@dataclass
class Directive(Item):
    name: str = ''              # 规范名（英文），不认识的指令保留原文
    written: str = ''           # 剧本里写的名字
    args: list = field(default_factory=list)
    known: bool = True


@dataclass
class Spoken(Item):
    """要显示的台词、旁白、场外弹幕。"""
    speaker: str = ''           # 剧本里写的说话人
    face: str | None = None     # 剧本里写的表情
    tone: str | None = None
    segments: list = field(default_factory=list)   # [['t'|'a'|'b', 文本]]：普通字、动作、消音词
    anchor: str | None = None   # 行尾写的 ID
    id: str | None = None       # 最终 ID（anchor 或自动编号）

    @property
    def text(self):
        """显示用全文（含动作，消音词照原文）。"""
        return ''.join(s for _, s in self.segments)

    @property
    def say(self):
        """要念的字：去掉动作，消音词照原文。"""
        return ''.join(s for k, s in self.segments if k != 'a').strip()

    @property
    def bleeps(self):
        return [s for k, s in self.segments if k == 'b']

    @property
    def voiced(self):
        return any(ch.isalnum() for ch in self.say)


@dataclass
class Chapter:
    path: str
    number: int
    title: str = ''
    lang: str | None = None
    meta: dict = field(default_factory=dict)
    items: list = field(default_factory=list)
    issues: list = field(default_factory=list)

    @property
    def spoken(self):
        return [it for it in self.items if isinstance(it, Spoken)]
