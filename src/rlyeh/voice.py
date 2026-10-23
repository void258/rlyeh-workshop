"""配音流水线：声线候选 → 选定（人工）→ 附加参考 → 整句生成 → 识别质检 → 换种子重做 → 消音。

规矩见 docs/zh/pipeline.md 的「声线」「配音」「消音」：每个角色一段固定参考，不滚动参考；整句连续生成，
脏话照念、之后再消音；质检按拼音比相似度并看时长。
"""
import datetime
import difflib
import json
import pathlib
import re

import numpy as np
import soundfile as sf
from pypinyin import lazy_pinyin

from . import backends
from .state import State, digest

CANDIDATES = 'voices/candidates'
EXTRA = 'voices/extra'
VOICE_DIR = 'audio/voice'
BLEEP_DIR = 'audio/voice-bleep'
QA_REPORT = 'build/voice_qa.json'
PICK = 'review/voice-pick.json'
REVIEW = 'review/voice-review.json'

SEEDS = [123, 7, 42, 2026, 99]
SAMPLE = {   # 声线候选默认念的话：故意不用剧本里的台词，免得配音模型把参考的后半段接着念下去
    'zh-CN': '今天的风有点大，我们还是早点出发吧。路上要是遇到什么麻烦，记得先别慌，慢慢来。',
    'en': "The wind is picking up today, so let's head out early. If we run into trouble on the road, don't panic.",
}


class VoiceError(RuntimeError):
    pass


def read_json(path, default):
    path = pathlib.Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def settings(project):
    v = project.config.get('voice') or {}
    return dict(candidates=int(v.get('candidates', 3)), seeds=list(v.get('seeds', SEEDS)),
                min_similarity=float(v.get('min_similarity', .75)), max_extra=float(v.get('max_extra', 1.4)))


def lines(project):
    """[(章, 台词, 声线角色ID, 语言)]，只要要配音的。"""
    out = []
    for ch in project.chapters():
        lang = ch.lang or project.lang
        for it in ch.spoken:
            if it.voiced:
                out.append((ch, it, project.voice_of(it), lang))
    return out


# ───────── 声线候选、选定、参考 ─────────
def voiced_characters(project):
    return [c for c in project.characters.values() if c.voice.get('design') or c.kind in ('narrator', 'gm')]


def design(project, chars=None, n=None, on_line=None):
    backend = backends.get(project, 'voice_design')
    n = n or settings(project)['candidates']
    out_dir = project.root / CANDIDATES
    index = read_json(project.root / 'voices' / 'candidates.json', {})
    jobs = []
    for ch in voiced_characters(project):
        if chars and ch.id not in chars:
            continue
        text = ch.voice.get('sample_text') or SAMPLE['en' if project.lang.startswith('en') else 'zh-CN']
        jobs += [dict(name=f'{ch.id}_{i}', cid=ch.id, instruct=ch.voice.get('design') or '', text=text, seed=1000 + i,
                      language=project.lang) for i in range(1, n + 1)]
    if not jobs:
        return index
    results = {r['name']: r for r in backend.design(jobs, out_dir, on_line)}     # 一次交给后端，模型只加载一次
    for cid in dict.fromkeys(j['cid'] for j in jobs):
        index[cid] = [dict(file=pathlib.Path(results[j['name']]['file']).resolve().relative_to(project.root).as_posix(),
                           seconds=results[j['name']]['seconds'], seed=j['seed'], text=j['text'], instruct=j['instruct'])
                      for j in jobs if j['cid'] == cid and j['name'] in results]
    write_json(project.root / 'voices' / 'candidates.json', index)
    return index


def pick(project, cid, choice, note='', by=''):
    """choice: 候选序号（1 起）或文件名。写 review/voice-pick.json。"""
    cands = read_json(project.root / 'voices' / 'candidates.json', {}).get(cid) or []
    if isinstance(choice, int) or str(choice).isdigit():
        k = int(choice) - 1
        if not 0 <= k < len(cands):
            raise VoiceError(f'{cid}: no candidate #{choice}')
        file = cands[k]['file']
    else:
        file = str(choice)
    picks = read_json(project.root / PICK, {})
    picks[cid] = dict(status='approved', choice=file, note=note, by=by, at=now())
    write_json(project.root / PICK, picks)
    return picks[cid]


def reference(project, cid):
    """角色的固定参考 (路径, 文本)：cast.yaml 写了 reference 就用它，否则用审核页选定的候选。"""
    ch = project.characters.get(cid)
    if ch is None:
        return None
    if ch.voice.get('reference'):
        return project.root / ch.voice['reference'], ch.voice.get('reference_text', '')
    chosen = read_json(project.root / PICK, {}).get(cid)
    if not chosen or chosen.get('status') != 'approved':
        return None
    for c in read_json(project.root / 'voices' / 'candidates.json', {}).get(cid) or []:
        if c['file'] == chosen['choice']:
            return project.root / c['file'], c['text']
    return None


def extra_references(project, cid):
    ch = project.characters.get(cid)
    out = []
    for e in (ch.voice.get('extra_references') or []) if ch else []:
        if isinstance(e, dict):
            out.append((project.root / e['file'], e.get('text', '')))
    for e in read_json(project.root / 'voices' / 'extra.json', {}).get(cid) or []:
        out.append((project.root / e['file'], e['text']))
    return out


def make_extra(project, cid, texts=None, on_line=None):
    """用同一个音色补念几段节奏普通的话，作为附加参考（实战：旁白选定的参考太慢太低沉）。"""
    ref = reference(project, cid)
    if ref is None:
        raise VoiceError(f'{cid}: no chosen voice yet')
    ch = project.characters[cid]
    texts = texts or ch.voice.get('extra_texts') or []
    if not texts:
        raise VoiceError(f'{cid}: voice.extra_texts is empty in cast.yaml')
    backend = backends.get(project, 'voice_clone')
    jobs = [dict(name=f'{cid}_{i}', text=t, seed=200 + i, language=project.lang) for i, t in enumerate(texts, 1)]
    res = backend.clone(ref[0], ref[1], jobs, project.root / EXTRA, on_line)
    index = read_json(project.root / 'voices' / 'extra.json', {})
    index[cid] = [dict(file=pathlib.Path(r['file']).relative_to(project.root).as_posix(), text=j['text'], seconds=r['seconds'])
                  for r, j in zip(res, jobs)]
    write_json(project.root / 'voices' / 'extra.json', index)
    return index[cid]


# ───────── 生成 ─────────
def _inputs(project, item, voice, refs, backend_id):
    return digest(project.tts_text(item), item.tone or '', voice or '', backend_id,
                  *[pathlib.Path(a) for a, _ in refs], *[t for _, t in refs])


def plan(project, ids=None, force=False):
    """要生成的句子。默认只挑没生成或过期的；ids 指定时只看这些，force 时不管新旧都重做。"""
    state = State(project.root)
    backend_id = (project.config.get('backends') or {}).get('tts', backends.DEFAULTS['tts'])
    todo, missing = [], set()
    for ch, it, voice, lang in lines(project):
        if ids and it.id not in ids:
            continue
        ref = reference(project, voice) if voice else None
        if ref is None and backend_id != 'placeholder':
            missing.add(voice or it.speaker)
            continue
        refs = ([ref] if ref else []) + extra_references(project, voice)
        inputs = _inputs(project, it, voice, refs, backend_id)
        key = f'{VOICE_DIR}/{it.id}.wav'
        if not force and state.fresh(key, inputs, project.root / key):
            continue
        todo.append(dict(id=it.id, text=project.tts_text(it), tone=it.tone, voice=voice, refs=refs, inputs=inputs))
    return todo, sorted(missing)


def build(project, ids=None, seed=123, force=False, limit=0, on_line=None):
    todo, missing = plan(project, ids, force)
    if missing:
        raise VoiceError('no chosen voice for: ' + ', '.join(missing))
    if limit:
        todo = todo[:limit]
    if not todo:
        return {}
    backend = backends.get(project, 'tts')
    for it in todo:
        it['seed'] = seed
    done = backend.synthesize(todo, project.root / VOICE_DIR, on_line)
    state = State(project.root)
    for it in todo:
        if it['id'] in done:
            state.set(f'{VOICE_DIR}/{it["id"]}.wav', inputs=it['inputs'], seed=seed, seconds=done[it['id']], voice=it['voice'])
            state.drop(f'{BLEEP_DIR}/{it["id"]}.wav')
    state.save()
    return done


# ───────── 质检 ─────────
PUNCT = re.compile(r'[\W_]')


def pinyin(text):
    """汉字转拼音逐字比；字母、数字逐个算；「幺」和「一」、阿拉伯数字和汉字数字视为一样。"""
    text = PUNCT.sub('', text).lower().replace('幺', '一')
    text = text.translate(str.maketrans('0123456789', '零一二三四五六七八九'))
    out = []
    for ch in text:
        if '一' <= ch <= '鿿':
            out.append(lazy_pinyin(ch)[0])
        elif ch.isalnum():
            out.append(ch)
    return out


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def score(want, heard, seconds, lang, min_sim=.75, max_extra=1.4):
    a, b = (words(want), words(heard)) if lang.startswith('en') else (pinyin(want), pinyin(heard))
    sim = difflib.SequenceMatcher(None, a, b).ratio() if a else 1.0
    extra = len(b) / max(len(a), 1)
    per = .45 if lang.startswith('en') else .42
    limit = 2.5 + per * len(a) + .5 * want.count('…') / 2 + .5 * want.count('...')
    too_long = bool(seconds and seconds > limit)
    bad = too_long or (len(a) >= 2 and (sim < min_sim or extra > max_extra))
    return dict(sim=round(sim, 3), extra=round(extra, 2), seconds=seconds, too_long=too_long, heard=heard, bad=bad)


def qa(project, ids=None, on_line=None):
    """识别并打分，写 build/voice_qa.json。识别后端是 none 时返回 None（跳过）。"""
    state = State(project.root)
    targets = [(it, lang) for _, it, _, lang in lines(project)
               if (not ids or it.id in ids) and (project.root / VOICE_DIR / f'{it.id}.wav').exists()]
    if not targets:
        return {}
    asr = backends.get(project, 'asr')
    report = read_json(project.root / QA_REPORT, {})
    s = settings(project)
    for lang in sorted({lang for _, lang in targets}):
        group = [it for it, l in targets if l == lang]
        files = [str(project.root / VOICE_DIR / f'{it.id}.wav') for it in group]
        texts = asr.transcribe(files, lang, on_line)
        if texts is None:
            return None
        for it, f in zip(group, files):
            rec = state.get(f'{VOICE_DIR}/{it.id}.wav') or {}
            seconds = rec.get('seconds') or round(sf.info(f).duration, 3)
            report[it.id] = score(project.tts_text(it), texts.get(f, ''), seconds, lang, s['min_similarity'], s['max_extra'])
    write_json(project.root / QA_REPORT, report)
    return report


def failed(project):
    return sorted(k for k, v in read_json(project.root / QA_REPORT, {}).items() if v.get('bad'))


def marked(project):
    return sorted(k for k, v in read_json(project.root / REVIEW, {}).items() if v.get('status') == 'redo')


def redo(project, ids, on_line=None):
    """换种子重做，直到质检通过或种子用完。返回仍不合格的 ID。"""
    ids = list(ids)
    for seed in settings(project)['seeds'][1:]:
        if not ids:
            break
        if on_line:
            on_line(f'== seed {seed}: {len(ids)} lines')
        build(project, ids=set(ids), seed=seed, force=True, on_line=on_line)
        report = qa(project, set(ids), on_line)
        if report is None:
            return []
        ids = [i for i in ids if report.get(i, {}).get('bad')]
    reviews = read_json(project.root / REVIEW, {})
    for i in reviews:                     # 人工标的重做已经处理过，改回待审
        if reviews[i].get('status') == 'redo' and i not in ids:
            reviews[i] = dict(reviews[i], status='pending', at=now())
    write_json(project.root / REVIEW, reviews)
    return ids


# ───────── 消音 ─────────
TONE = 1000
PAD = .04


def bleep_spans(project, item):
    """消音词在 TTS 读法里占哪几个汉字：[(起, 止)]，按汉字下标。"""
    chars = [c for c in project.tts_text(item) if '一' <= c <= '鿿']
    spoken = project.spoken_forms
    spans = []
    for word in dict.fromkeys(item.bleeps):
        w = [c for c in spoken.get(word, word) if '一' <= c <= '鿿']
        for i in range(len(chars) - len(w) + 1):
            if w and chars[i:i + len(w)] == w:
                spans.append((i, i + len(w)))
    return chars, spans


def beep(n, sr, level):
    t = np.arange(n) / sr
    y = np.sin(2 * np.pi * TONE * t) * level
    f = min(n // 2, int(sr * .008))
    if f:
        ramp = np.linspace(0, 1, f)
        y[:f] *= ramp
        y[-f:] *= ramp[::-1]
    return y


def apply_bleeps(src, dst, timestamps, spans, n_chars):
    """把 spans 对应的时间换成「哔」。句首/句尾的词一直盖到开头/结尾：对齐起点常落在送气声母之后，会漏出半个字。"""
    y, sr = sf.read(src, always_2d=True)
    level = min(.5, float(np.sqrt((y ** 2).mean())) * 2.2 + .05)
    cuts = []
    for a, b in spans:
        t0 = 0 if a == 0 else max(0, timestamps[a][0] / 1000 - PAD)
        t1 = len(y) / sr if b == n_chars else min(len(y) / sr, timestamps[b - 1][1] / 1000 + PAD)
        i0, i1 = int(t0 * sr), int(t1 * sr)
        y[i0:i1] = beep(i1 - i0, sr, level)[:, None]
        cuts.append([round(t0, 3), round(t1, 3)])
    pathlib.Path(dst).parent.mkdir(parents=True, exist_ok=True)
    sf.write(dst, y, sr)
    return cuts


def bleep(project, on_line=None):
    """给带消音词的句子做消音版。返回 {id: [[起秒, 止秒], …]}；对不上的句子记在 problems。"""
    state = State(project.root)
    todo, problems = [], []
    for _, it, _, lang in lines(project):
        src = project.root / VOICE_DIR / f'{it.id}.wav'
        if not it.bleeps or not src.exists():
            continue
        if lang.startswith('en'):
            problems.append(dict(id=it.id, reason='english bleeping needs a word aligner (planned)'))
            continue
        chars, spans = bleep_spans(project, it)
        if not spans:
            problems.append(dict(id=it.id, reason='bleeped word not found in the spoken text'))
            continue
        key = f'{BLEEP_DIR}/{it.id}.wav'
        inputs = digest(src, spans)
        if state.fresh(key, inputs, project.root / key):
            continue
        todo.append((it, src, chars, spans, inputs))
    done = {}
    if todo:
        stamps = backends.get(project, 'align').align([dict(audio=src, chars=chars) for _, src, chars, _, _ in todo], on_line)
        for (it, src, chars, spans, inputs), ts in zip(todo, stamps):
            if ts is None:
                problems.append(dict(id=it.id, reason='alignment failed'))
                continue
            done[it.id] = apply_bleeps(src, project.root / BLEEP_DIR / f'{it.id}.wav', ts, spans, len(chars))
            state.set(f'{BLEEP_DIR}/{it.id}.wav', inputs=inputs, cuts=done[it.id])
        state.save()
    return done, problems


# ───────── 汇总 ─────────
def summary(project):
    state = State(project.root)
    qa_rep = read_json(project.root / QA_REPORT, {})
    marks = set(marked(project))
    out = dict(lines=0, done=0, stale=0, todo=0, failed=0, marked=0, seconds=0.0, no_voice=[])
    todo, missing = plan(project)
    stale_ids = {t['id'] for t in todo}
    out['no_voice'] = missing
    for _, it, _, _ in lines(project):
        out['lines'] += 1
        exists = (project.root / VOICE_DIR / f'{it.id}.wav').exists()
        if it.id in stale_ids:
            out['stale' if exists else 'todo'] += 1
        elif exists:
            out['done'] += 1
        else:
            out['todo'] += 1
        out['seconds'] += (state.get(f'{VOICE_DIR}/{it.id}.wav') or {}).get('seconds', 0)
        out['failed'] += bool(qa_rep.get(it.id, {}).get('bad'))
        out['marked'] += it.id in marks
    out['seconds'] = round(out['seconds'], 1)
    return out
