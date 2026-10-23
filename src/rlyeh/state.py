"""产物状态 .rlyeh/state.json：每个产物记下由哪些输入生成（输入的哈希），输入一变就算过期。"""
import hashlib
import json
import pathlib

STATE = '.rlyeh/state.json'


def digest(*parts):
    """把若干字符串、字节或文件路径（pathlib.Path）混在一起算哈希。文件按内容算。"""
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, pathlib.Path):
            h.update(p.read_bytes() if p.exists() else b'<missing>')
        elif isinstance(p, bytes):
            h.update(p)
        else:
            h.update(json.dumps(p, ensure_ascii=False, sort_keys=True).encode('utf-8'))
        h.update(b'\x00')
    return 'sha256:' + h.hexdigest()[:32]


class State:
    def __init__(self, root):
        self.path = pathlib.Path(root) / STATE
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.data.setdefault('artifacts', {})

    @property
    def artifacts(self):
        return self.data['artifacts']

    def get(self, key):
        return self.artifacts.get(key)

    def set(self, key, **fields):
        self.artifacts[key] = {**self.artifacts.get(key, {}), **fields}

    def drop(self, key):
        self.artifacts.pop(key, None)

    def fresh(self, key, inputs, file):
        """产物文件存在、而且记录的输入哈希和现在一致。"""
        rec = self.get(key)
        return bool(rec) and rec.get('inputs') == inputs and pathlib.Path(file).exists()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding='utf-8')
        tmp.replace(self.path)
