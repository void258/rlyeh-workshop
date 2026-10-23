"""后台任务：在一个独立的进程里跑 replay 命令（配音、生图、渲染……），MCP 服务立即返回任务 ID。

  .rlyeh/jobs/<ID>.json   状态：queued → running → done / failed，命令、开始结束时间、退出码、命令的 JSON 结果
  .rlyeh/jobs/<ID>.log    进度日志
任务由单独的 runner 进程（python -m rlyeh.jobs <项目> <ID>）执行，MCP 连接断了也会跑完。
同一个项目里一次只跑一个任务，后来的排队：显卡同时跑两个大模型会爆显存。
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid

from .util import now, read_json, write_json

JOBS = '.rlyeh/jobs'
HEARTBEAT = 10            # 运行中的任务每隔这么多秒写一次心跳
STALE = 45                # 心跳超过这么久没更新，当作 runner 已经死了


def _dir(root):
    d = pathlib.Path(root) / JOBS
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stamp():
    return time.time()


def start(root, argv):
    """排一个任务：写任务记录，开一个脱离当前进程的 runner。返回任务记录。"""
    jid = datetime.datetime.now().strftime('%m%d-%H%M%S-') + uuid.uuid4().hex[:4]
    rec = dict(id=jid, command=list(argv), status='queued', queued_at=now(), heartbeat=_stamp())
    write_json(_dir(root) / f'{jid}.json', rec)
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(root))
    if sys.platform == 'win32':
        kw['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kw['start_new_session'] = True
    subprocess.Popen([sys.executable, '-m', 'rlyeh.jobs', str(root), jid], **kw)
    return rec


def _alive(rec):
    return rec.get('status') in ('queued', 'running') and _stamp() - rec.get('heartbeat', 0) < STALE


def listing(root, limit=20):
    recs = [read_json(p, {}) for p in sorted(_dir(root).glob('*.json'))]
    for r in recs:
        if r.get('status') in ('queued', 'running') and not _alive(r):
            r['status'] = 'lost'                          # runner 没了（进程被杀、机器重启）
    return recs[-limit:]


def get(root, jid, tail=40):
    path = _dir(root) / f'{jid}.json'
    if not path.exists():
        return None
    rec = read_json(path, {})
    if rec.get('status') in ('queued', 'running') and not _alive(rec):
        rec['status'] = 'lost'
    log = _dir(root) / f'{jid}.log'
    rec['log_tail'] = log.read_text(encoding='utf-8', errors='replace').splitlines()[-tail:] if log.exists() else []
    return rec


def _wait_turn(root, jid):
    """排队：比自己早的任务还活着就等。"""
    while True:
        earlier = [r for r in listing(root, 1000) if r['id'] < jid and _alive(r)]
        if not earlier:
            return
        rec = read_json(_dir(root) / f'{jid}.json', {})
        write_json(_dir(root) / f'{jid}.json', dict(rec, heartbeat=_stamp(), waiting_for=earlier[0]['id']))
        time.sleep(2)


def run(root, jid):
    """runner：等轮到自己，跑命令，把结果写回任务记录。"""
    d = _dir(root)
    path = d / f'{jid}.json'
    _wait_turn(root, jid)
    rec = read_json(path, {})
    rec.pop('waiting_for', None)
    rec.update(status='running', started_at=now(), heartbeat=_stamp())
    write_json(path, rec)
    stop = threading.Event()

    def beat():
        while not stop.wait(HEARTBEAT):
            cur = read_json(path, {})
            write_json(path, dict(cur, heartbeat=_stamp()))

    threading.Thread(target=beat, daemon=True).start()
    cmd = [sys.executable, '-m', 'rlyeh.cli', *rec['command'], '-C', str(root), '--json']
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    with open(d / f'{jid}.log', 'w', encoding='utf-8') as log:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=log, env=env, cwd=str(root))
    stop.set()
    out = proc.stdout.decode('utf-8', errors='replace').strip()
    try:
        result = json.loads(out) if out else None
    except json.JSONDecodeError:
        result = dict(raw=out[-4000:])
    rec = read_json(path, {})
    rec.update(status='done' if proc.returncode == 0 else 'failed', exit_code=proc.returncode, ended_at=now(),
               heartbeat=_stamp(), result=result)
    write_json(path, rec)


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
