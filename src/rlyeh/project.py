"""项目：replay.toml + cast.yaml + script/*.md。规格见 docs/zh/project-format.md。"""
import pathlib
import re
import tomllib
from dataclasses import dataclass, field

import yaml

from .script import parser
from .script.ids import assign

CONFIG = 'replay.toml'
CAST = 'cast.yaml'


class ProjectError(Exception):
    pass


@dataclass
class Character:
    id: str
    names: dict                 # 语言 → 显示名
    kind: str = 'npc'           # pc | npc | narrator | gm
    player: str | None = None
    color: str | None = None
    expressions: dict = field(default_factory=dict)
    default_expression: str | None = None
    face_rules: list = field(default_factory=list)
    sprite: dict = field(default_factory=dict)
    voice: dict = field(default_factory=dict)
    appearance: str = ''

    def name(self, lang='zh-CN'):
        return self.names.get(lang) or next(iter(self.names.values()), self.id)

    def pick_face(self, face, tone):
        """剧本写了表情就用写的；没写按语气关键词套 face_rules；都不中用默认表情。"""
        if face:
            return face
        for rule in self.face_rules:
            target, pattern = rule[0], rule[1]
            if tone and re.search(pattern, tone):
                return target
        return self.default_expression


def _names(raw, cid):
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if raw:
        return {'zh-CN': str(raw)}
    return {'zh-CN': cid}


class Project:
    def __init__(self, root):
        self.root = pathlib.Path(root).resolve()
        cfg_path = self.root / CONFIG
        if not cfg_path.exists():
            raise ProjectError(str(cfg_path))
        self.config = tomllib.loads(cfg_path.read_text(encoding='utf-8'))
        cast_path = self.root / CAST
        raw = yaml.safe_load(cast_path.read_text(encoding='utf-8')) if cast_path.exists() else {}
        self.characters = {}
        for cid, c in ((raw or {}).get('characters') or {}).items():
            c = c or {}
            self.characters[str(cid)] = Character(
                id=str(cid), names=_names(c.get('name'), str(cid)), kind=c.get('kind', 'npc'), player=c.get('player'),
                color=c.get('color'), expressions=c.get('expressions') or {}, default_expression=c.get('default_expression'),
                face_rules=c.get('face_rules') or [], sprite=c.get('sprite') or {}, voice=c.get('voice') or {},
                appearance=c.get('appearance') or '')
        self._speaker_index = {}
        for ch in self.characters.values():
            self._speaker_index[ch.id] = ch
            for n in ch.names.values():
                self._speaker_index[n] = ch

    # ── 配置 ──
    @property
    def lang(self):
        return self.config.get('project', {}).get('language', 'zh-CN')

    @property
    def players(self):
        """场外玩家名 → 角色 ID（GM 为 None）。"""
        out = {}
        for name, v in (self.config.get('players') or {}).items():
            out[name] = None if isinstance(v, dict) else str(v)
        return out

    @property
    def readings(self):
        return {str(k): str(v) for k, v in (self.config.get('readings') or {}).items()}

    @property
    def spoken_forms(self):
        return {str(k): str(v) for k, v in (self.config.get('spoken') or {}).items()}

    @property
    def narrator_names(self):
        names = set(parser.NARRATOR_NAMES)
        for ch in self.characters.values():
            if ch.kind == 'narrator':
                names.update(ch.names.values())
                names.add(ch.id)
        return names

    # ── 说话人 ──
    def character(self, speaker):
        return self._speaker_index.get(speaker)

    def voice_of(self, item):
        """这句话用哪个角色的声线：场外弹幕用玩家所扮演角色，GM 用 kind=gm 的角色。"""
        if item.kind == 'ooc':
            if item.speaker not in self.players:
                return None
            cid = self.players[item.speaker]
            if cid is None:
                gm = next((c for c in self.characters.values() if c.kind == 'gm'), None)
                return gm.id if gm else None
            return cid
        if item.kind == 'narration':
            nar = next((c for c in self.characters.values() if c.kind == 'narrator'), None)
            return nar.id if nar else None
        ch = self.character(item.speaker)
        return ch.id if ch else None

    def tts_text(self, item):
        """送进 TTS 的读法：去掉动作，消音词换成 [spoken] 的读法，再套 [readings]（长的先换）。"""
        spoken = self.spoken_forms
        text = ''.join(spoken.get(s, s) if k == 'b' else s for k, s in item.segments if k != 'a').strip()
        for k in sorted(self.readings, key=len, reverse=True):
            text = text.replace(k, self.readings[k])
        return text

    # ── 剧本 ──
    def script_files(self):
        return sorted((self.root / 'script').glob('*.md'))

    def chapters(self):
        out = []
        for i, path in enumerate(self.script_files(), 1):
            ch = parser.parse_file(path, i, self.narrator_names)
            assign(ch)
            out.append(ch)
        return out


def find_root(start='.'):
    p = pathlib.Path(start).resolve()
    for d in [p, *p.parents]:
        if (d / CONFIG).exists():
            return d
    return None
