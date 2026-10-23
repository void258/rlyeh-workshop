"""任务：把流水线每个阶段拆成任务，告诉 AI 下一件该做什么。规格见 docs/zh/pipeline.md#任务与状态。

任务分三类：
- agent：要判断的活，交给 AI（写剧本、补角色表、写提示词、看质检结果……），做完 replay done <ID>；
- tool：工具自己跑（command 就是要运行的 replay 命令），跑完状态自然变成 done；
- review：等人审核（选声线、审美术、挑 BGM），在 replay preview 的页面里做。
状态：todo（要做）· stale（做过但输入变了）· review（等人）· done · skip（这个项目用不到）。
每个任务的状态都是从项目文件现算的，不另外存进度；只有 agent 任务的「我做完了」记在 .rlyeh/tasks.json，
连同当时输入的哈希：输入一变，就又变成要做。
"""
from dataclasses import asdict, dataclass, field

from . import art, backends, music, sfx, voice
from .i18n import lang, t
from .script.lint import lint
from .state import digest
from .util import now, read_json, write_json

RECORD = '.rlyeh/tasks.json'
ACTIVE = ('todo', 'stale')


@dataclass
class Task:
    id: str
    kind: str                      # agent | tool | review
    stage: str
    status: str                    # todo | stale | review | done | skip
    title: str = ''
    detail: dict = field(default_factory=dict)
    command: list | None = None    # tool 任务：要运行的 replay 命令（不含 replay 本身）
    playbook: str | None = None    # agent 任务：照哪个技能做
    inputs: list = field(default_factory=list)
    blocked_by: list = field(default_factory=list)
    optional: bool = False         # 可选：不挡后面的任务，没别的事可做时才提
    page: str | None = None        # review 任务：replay preview 里的哪一页

    def as_dict(self):
        return {k: v for k, v in asdict(self).items() if v not in (None, [], {})}


def _mtime(paths):
    times = [p.stat().st_mtime for p in paths if p.exists()]
    return max(times) if times else 0


def _files(root, *patterns):
    out = []
    for pat in patterns:
        out += [p for p in root.glob(pat) if p.is_file()]
    return out


class Planner:
    """从项目文件算出全部任务。"""

    def __init__(self, project):
        self.p = project
        self.root = project.root
        self.records = read_json(self.root / RECORD, {})
        self.tasks = []

    # ── 记录 ──
    def _agent(self, tid, key, **kw):
        """agent 任务：记录的输入哈希和现在一致就是 done，记过但变了就是 stale，没记过就是 todo。"""
        rec = self.records.get(tid)
        status = 'done' if rec and rec.get('key') == key else ('stale' if rec else 'todo')
        self._add(tid, 'agent', status=status, key=key, **kw)

    def _add(self, tid, kind, status, key=None, **kw):
        task = Task(id=tid, kind=kind, stage=tid.split('.')[0], status=status, title=t('task.' + tid), **kw)
        if key is not None:
            task.detail['key'] = key                 # replay done 记下的就是它
        self.tasks.append(task)
        return task

    def find(self, tid):
        return next((x for x in self.tasks if x.id == tid), None)

    # ── 各阶段 ──
    def plan(self):
        p, root = self.p, self.root
        raw = _files(root / 'logs' / 'raw', '*')
        events = root / 'logs' / 'events.jsonl'
        scripts = p.script_files()

        # 导入
        if raw:
            stale = not events.exists() or _mtime(raw) > events.stat().st_mtime
            self._add('import.run', 'tool', 'todo' if stale else 'done', command=['import'], inputs=['logs/raw/'])
        else:
            self._add('import.run', 'tool', 'skip', detail=dict(reason='no logs in logs/raw'))

        # 剧本：从记录写剧本是主观的活，靠 replay done 记下；没有记录但剧本比记录新，也当作写过了
        if events.exists():
            key = digest(events)
            if self.records.get('script.write') is None and scripts and _mtime(scripts) > events.stat().st_mtime:
                self._add('script.write', 'agent', 'done', key=key, playbook='rlyeh-script', inputs=['logs/events.jsonl'])
            else:
                self._agent('script.write', key, playbook='rlyeh-script', inputs=['logs/events.jsonl', 'script/'],
                            blocked_by=['import.run'])
        else:
            self._add('script.write', 'agent', 'done' if scripts else 'todo', playbook='rlyeh-script', inputs=['script/'])

        chapters = p.chapters()
        issues = lint(chapters, p)
        errors = [i for i in issues if i.level == 'error']
        unknown = sorted({i.message for i in errors if i.code in ('lint.unknown_speaker', 'lint.unknown_player')})
        thin = [c.id for c in p.characters.values() if c.kind in ('pc', 'npc')
                and (not c.appearance or not c.voice.get('design') or not c.expressions)]
        self._add('cast.write', 'agent', 'todo' if unknown or thin else 'done', playbook='rlyeh-cast',
                  inputs=['cast.yaml', 'script/'], detail=dict(unknown_speakers=unknown, incomplete=thin))
        others = [i.as_dict() for i in errors if i.code not in ('lint.unknown_speaker', 'lint.unknown_player')]
        self._add('script.lint', 'agent', 'todo' if others else 'done', playbook='rlyeh-script', inputs=['script/'],
                  detail=dict(errors=others[:30], total=len(others)), command=['lint', '--errors-only'])
        no_id = sum(1 for ch in chapters for it in ch.spoken if not it.anchor)
        self._add('script.ids', 'tool', 'todo' if no_id else 'done', command=['ids'], detail=dict(lines=no_id))

        # 声线和配音
        tts = (p.config.get('backends') or {}).get('tts', backends.DEFAULTS['tts'])
        cands = read_json(root / 'voices' / 'candidates.json', {})
        chars = voice.voiced_characters(p)
        need_design = [c.id for c in chars if c.id not in cands and voice.reference(p, c.id) is None]
        placeholder = tts == 'placeholder'
        self._add('voice.design', 'tool', 'todo' if need_design and not placeholder else ('skip' if placeholder else 'done'),
                  command=['voice', 'design', '--chars', ','.join(need_design)] if need_design else ['voice', 'design'],
                  detail=dict(characters=need_design), blocked_by=['cast.write'])
        unpicked = [c.id for c in chars if c.id in cands and voice.reference(p, c.id) is None]
        status = 'skip' if placeholder else 'review' if unpicked else 'todo' if need_design else 'done'
        self._add('voice.pick', 'review', status,
                  page='/voices', detail=dict(characters=unpicked), blocked_by=['voice.design'])
        vs = voice.summary(p)
        build_status = 'todo' if vs['todo'] else ('stale' if vs['stale'] else 'done')
        self._add('voice.build', 'tool', build_status, command=['voice', 'build'], blocked_by=['voice.pick', 'script.ids'],
                  detail=dict(todo=vs['todo'], stale=vs['stale'], no_voice=vs['no_voice']))
        asr = (p.config.get('backends') or {}).get('asr', backends.DEFAULTS['asr'])
        qa_rep = read_json(root / voice.QA_REPORT, {})
        built = [it.id for _, it, _, _ in voice.lines(p) if (root / voice.VOICE_DIR / f'{it.id}.wav').exists()]
        unchecked = [i for i in built if i not in qa_rep]
        self._add('voice.qa', 'tool', 'skip' if asr == 'none' else ('todo' if unchecked else 'done'), command=['voice', 'qa'],
                  detail=dict(unchecked=len(unchecked)), blocked_by=['voice.build'])
        bad = voice.failed(p)
        if bad:                                      # 质检不合格的句子：AI 决定改读法、重做，还是接受（replay done）
            self._agent('voice.fix', digest(bad), playbook='rlyeh-voice', inputs=[voice.QA_REPORT], blocked_by=['voice.qa'],
                        detail=dict(failed=bad[:50], total=len(bad)))
        else:
            self._add('voice.fix', 'agent', 'done', playbook='rlyeh-voice')
        marks = voice.marked(p)
        self._add('voice.redo', 'tool', 'todo' if marks else 'done', command=['voice', 'redo', '--marked'], detail=dict(lines=marks))
        self._add('voice.review', 'review', 'review' if built else 'todo', page='/review/voice', optional=True,
                  detail=dict(lines=len(built)), blocked_by=['voice.build'])
        pending = voice.bleep_pending(p)
        self._add('voice.bleep', 'tool', 'todo' if pending else 'done', command=['bleep'], detail=dict(lines=pending),
                  blocked_by=['voice.build'])

        # 美术
        a = art.summary(p)
        self._add('art.jobs', 'tool', 'todo' if a['unplanned'] else 'done', command=['art', 'jobs'], detail=dict(new=a['unplanned']),
                  blocked_by=['cast.write'])
        todo_prompts = [j.id for j in art.load_jobs(p) if j.needs_prompt and not j.skip]
        self._add('art.prompts', 'agent', 'todo' if todo_prompts else 'done', playbook='rlyeh-art', inputs=['art/prompts/'],
                  detail=dict(prompts=todo_prompts), blocked_by=['art.jobs'])
        image = (p.config.get('backends') or {}).get('image', backends.DEFAULTS['image'])
        status = 'todo' if a['todo'] else ('stale' if a['stale'] else 'done')
        self._add('art.run', 'tool', status, command=['art', 'run'], blocked_by=['art.prompts'],
                  detail=dict(todo=a['todo'], stale=a['stale'], backend=image))
        rejected = art.marked(p)
        if rejected:
            self._agent('art.redo', digest(rejected, root / art.REVIEW), playbook='rlyeh-art',
                        inputs=[art.REVIEW, 'art/prompts/'], detail=dict(images=rejected),
                        command=['art', 'run', '--marked'])
        unreviewed = a['done'] - a['approved'] - a['redo']
        self._add('art.review', 'review', 'review' if unreviewed > 0 else ('done' if a['done'] else 'todo'), page='/review/art',
                  optional=True, detail=dict(unreviewed=unreviewed), blocked_by=['art.run'])

        # 音效
        s = sfx.summary(p)
        self._add('sfx.build', 'tool', 'todo' if s['done'] < s['total'] else 'done', command=['sfx'], detail=dict(s))

        # 音乐：剧本里用到、曲目表里没有的曲子要先写进 music.yaml
        used = {d.args[0].strip() for ch in chapters for d in ch.items
                if getattr(d, 'name', '') == 'bgm' and getattr(d, 'args', None) and d.args[0].strip()}
        cues = music.cues(p)
        missing = sorted(n for n in used if music.resolve(p, n) is None)
        self._add('music.sheet', 'agent', 'todo' if missing or (used and not cues) else 'done', playbook='rlyeh-music',
                  inputs=['music.yaml', 'script/'], detail=dict(missing=missing))
        takes = music.takes(p)
        no_takes = [c for c in cues if not any(x['cue'] == c for x in takes.values())]
        self._add('music.gen', 'tool', 'todo' if no_takes else 'done', command=['music', 'gen'], detail=dict(cues=no_takes),
                  blocked_by=['music.sheet'])
        check = read_json(root / music.CHECK, {})
        unchecked = [k for k, x in takes.items() if cues.get(x['cue'], {}).get('instrumental') and k not in check]
        self._add('music.check', 'tool', 'skip' if asr == 'none' else ('todo' if unchecked else 'done'),
                  command=['music', 'check'], blocked_by=['music.gen'])
        reviews = read_json(root / music.REVIEW, {})
        unpicked_cues = [c for c in cues if not music.final(p, c) or (reviews.get(c) or {}).get('status') != 'approved']
        status = 'review' if unpicked_cues and takes else 'todo' if unpicked_cues else 'done' if cues else 'skip'
        self._add('music.pick', 'review', status,
                  page='/review/music', detail=dict(cues=unpicked_cues), blocked_by=['music.gen'])

        # 主题（可选）：没设主题就提一句，让 AI 按团的气质设计一套
        if (p.config.get('player') or {}).get('theme'):
            self._add('player.theme', 'agent', 'done', playbook='rlyeh-theme', optional=True)
        else:                                        # 决定就用默认主题的话 replay done 一下
            self._agent('player.theme', 'default', playbook='rlyeh-theme', optional=True, inputs=['replay.toml', 'theme/'])

        # 打包、渲染、压制
        data = root / 'build' / 'player' / 'data.js'
        sources = scripts + _files(root, 'cast.yaml', 'replay.toml', 'music.yaml', 'sfx.yaml', '.rlyeh/state.json',
                                   'review/*.json', 'audio/sfx/index.json', 'audio/bgm/*.*', 'theme/**/*')
        built_at = data.stat().st_mtime if data.exists() else 0
        self._add('player.build', 'tool', 'todo' if not data.exists() else ('stale' if _mtime(sources) > built_at else 'done'),
                  command=['build'])
        pid = (p.config.get('project') or {}).get('id', 'replay')
        video = root / 'build' / 'video' / f'{pid}.mp4'
        status = 'todo' if not video.exists() else ('stale' if built_at > video.stat().st_mtime else 'done')
        self._add('render.video', 'tool', status, command=['render'], blocked_by=['player.build'])
        share = video.with_name(f'{pid}_share.mp4')
        status = 'todo' if not share.exists() else ('stale' if video.exists() and video.stat().st_mtime > share.stat().st_mtime else 'done')
        self._add('render.encode', 'tool', status, command=['encode', 'share'], blocked_by=['render.video'])
        return self.tasks


def plan(project):
    return Planner(project).plan()


def _ready(task, tasks):
    by = {x.id: x for x in tasks}
    return all(by[b].status in ('done', 'skip') or by[b].optional for b in task.blocked_by if b in by)


def next_task(project, tasks=None):
    """下一件该做的事：先找没被挡住的必做任务（agent / tool），再是等人审核的，最后是可选的。都没有返回 None。"""
    tasks = tasks if tasks is not None else plan(project)
    for want in ('required', 'review', 'optional'):
        for x in tasks:
            if not _ready(x, tasks):
                continue
            if want == 'required' and x.status in ACTIVE and not x.optional:
                return x
            if want == 'review' and x.status == 'review' and not x.optional:
                return x
            if want == 'optional' and (x.status in ACTIVE or x.status == 'review') and x.optional:
                return x
    return None


class TaskError(RuntimeError):
    pass


def complete(project, tid, note=''):
    """agent 任务做完了：记下当时输入的哈希。tool 任务要运行命令，review 任务要人在审核页里做，都不能直接标完成。"""
    tasks = plan(project)
    task = next((x for x in tasks if x.id == tid), None)
    if task is None:
        raise TaskError(f'unknown task: {tid} (see replay next --all)')
    if task.kind == 'tool':
        raise TaskError(f'{tid} is a tool task: run replay {" ".join(task.command or [])}')
    if task.kind == 'review':
        raise TaskError(f'{tid} waits for a person: open {task.page} in replay preview')
    if 'key' not in task.detail:
        raise TaskError(f'{tid} is done when its condition is met, not by marking it: {task.detail}')
    records = read_json(project.root / RECORD, {})
    records[tid] = dict(key=task.detail['key'], at=now(), note=note, lang=lang())
    write_json(project.root / RECORD, records)
    return records[tid]


def overview(tasks):
    counts = {}
    for x in tasks:
        counts[x.status] = counts.get(x.status, 0) + 1
    return counts
