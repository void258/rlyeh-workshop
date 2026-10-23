"""台词 ID：行尾写了 ^ID 的用写的；没写的自动编号，已有的 ID 永远不改。"""
import re

DEFAULT = re.compile(r'^c(?P<ch>\d+)-(?P<n>\d+)$')


def assign(chapter):
    """给 chapter 里每句台词定 ID（写入 item.id）。返回这次自动编号的条目。

    整章都没写 ID：按出现顺序编号 c<章>-0001、0002……（和旧剧本兼容）。
    部分写了：没写的从这一章已用的最大编号往后接，不和已有的撞。
    """
    spoken = chapter.spoken
    anchored = [it.anchor for it in spoken if it.anchor]
    if not anchored:
        for n, it in enumerate(spoken, 1):
            it.id = f'c{chapter.number}-{n:04d}'
        return list(spoken)
    used = set(anchored)
    nums = [int(m.group('n')) for a in anchored if (m := DEFAULT.match(a)) and int(m.group('ch')) == chapter.number]
    nxt = max(nums, default=0) + 1
    fresh = []
    for it in spoken:
        if it.anchor:
            it.id = it.anchor
            continue
        while f'c{chapter.number}-{nxt:04d}' in used:
            nxt += 1
        it.id = f'c{chapter.number}-{nxt:04d}'
        used.add(it.id)
        nxt += 1
        fresh.append(it)
    return fresh


def write_anchors(path, items):
    """把 items 的 ID 写到剧本文件对应行的行尾。只改这些行，其它字节原样保留。"""
    if not items:
        return 0
    raw = open(path, encoding='utf-8', newline='').read()
    lines = raw.split('\n')
    for it in items:
        idx = it.line_no - 1
        line = lines[idx]
        cr = line.endswith('\r')
        body = line[:-1] if cr else line
        lines[idx] = body.rstrip() + f' ^{it.id}' + ('\r' if cr else '')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(lines))
    return len(items)
