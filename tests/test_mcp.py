"""MCP 服务：真开一个 replay mcp 子进程，按协议一问一答。"""
import json
import subprocess
import sys
import time

import pytest

from rlyeh import importers
from rlyeh.mcp import Server


class Client:
    def __init__(self, root):
        self.proc = subprocess.Popen([sys.executable, '-m', 'rlyeh.cli', 'mcp', '-C', str(root)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.n = 0

    def send(self, method, params=None, notify=False):
        msg = dict(jsonrpc='2.0', method=method, **({'params': params} if params is not None else {}))
        if not notify:
            self.n += 1
            msg['id'] = self.n
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
        self.proc.stdin.flush()
        if notify:
            return None
        reply = json.loads(self.proc.stdout.readline().decode('utf-8'))
        assert reply['id'] == self.n
        return reply

    def call(self, name, **args):
        r = self.send('tools/call', dict(name=name, arguments=args))['result']
        return r['isError'], json.loads(r['content'][0]['text'])

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


@pytest.fixture
def client(example_project):
    importers.run(example_project.root, example_project.config)
    c = Client(example_project.root)
    yield c
    c.close()


def test_protocol(client):
    r = client.send('initialize', dict(protocolVersion='2025-03-26', capabilities={}, clientInfo=dict(name='t', version='0')))
    assert r['result']['protocolVersion'] == '2025-03-26' and r['result']['serverInfo']['name'] == 'rlyeh'
    client.send('notifications/initialized', notify=True)                     # 通知不回
    tools = client.send('tools/list')['result']['tools']
    names = {t['name'] for t in tools}
    assert len(names) == 12 and all(n.startswith('rlyeh_') for n in names)
    assert all(t['inputSchema']['type'] == 'object' and t['description'] for t in tools)
    assert client.send('ping')['result'] == {}
    assert client.send('resources/list')['error']['code'] == -32601
    err, out = client.call('rlyeh_nope')
    assert err and 'unknown tool' in out['error']
    err, out = client.call('rlyeh_lint', bogus=1)
    assert err and 'bad arguments' in out['error']


def test_tools(client):
    err, out = client.call('rlyeh_next_task')
    assert not err and out['next']['id'] == 'script.write'
    err, out = client.call('rlyeh_complete_task', id='script.write', note='示例剧本')
    assert not err and out['ok']
    err, out = client.call('rlyeh_status')
    assert out['next']['id'] == 'voice.build' and out['voice']['lines'] == 24
    err, out = client.call('rlyeh_read_log', limit=10, kind='roll')
    assert out['total'] == 5 and all(e['kind'] == 'roll' for e in out['events']) and out['next_offset'] is None
    err, out = client.call('rlyeh_read_log', limit=20)
    assert out['total'] == 45 and out['next_offset'] == 20
    err, out = client.call('rlyeh_lint')
    assert out == dict(errors=0, warnings=0, issues=[])
    err, out = client.call('rlyeh_list_lines', character='阿洛')
    assert [x['id'] for x in out['lines']] == ['c1-0002', 'c1-0009', 'c1-0010', 'c1-0015']    # 含小林的场外话：用阿洛的声线
    assert out['lines'][0]['status'] == 'todo'
    err, out = client.call('rlyeh_list_lines', status='todo', limit=5)
    assert out['total'] == 24 and len(out['lines']) == 5
    err, out = client.call('rlyeh_preview_url', page='player')
    assert err and 'not built' in out['error']
    err, out = client.call('rlyeh_request_review', kind='voices', note='挑一下声线')
    assert not err and out['url'].endswith('/voices')
    err, out = client.call('rlyeh_reviews', kind='art')
    assert out['reviews'] == {}


def test_background_job(client):
    err, out = client.call('rlyeh_run_stage', stage='voice.build', args=['--ids', 'c1-0001,c1-0002'])
    assert not err and out['command'] == 'replay voice build --ids c1-0001,c1-0002'
    jid = out['job']
    for _ in range(120):
        err, job = client.call('rlyeh_job', id=jid)
        if job['status'] in ('done', 'failed'):
            break
        time.sleep(.5)
    assert job['status'] == 'done' and sorted(job['result']['built']) == ['c1-0001', 'c1-0002']
    err, out = client.call('rlyeh_list_lines', status='done')
    assert out['total'] == 2
    err, out = client.call('rlyeh_job')
    assert out['jobs'][-1]['id'] == jid
    err, out = client.call('rlyeh_run_stage', stage='voice.build', args=['-C', '..'])
    assert err and 'project folder' in out['error']
    err, out = client.call('rlyeh_run_stage', task='script.write')
    assert err and 'not a tool task' in out['error']


def test_without_project(tmp_path):
    s = Server(str(tmp_path))
    r = s.handle(dict(jsonrpc='2.0', id=1, method='tools/call', params=dict(name='rlyeh_status', arguments={})))
    assert r['result']['isError'] and 'no replay.toml' in r['result']['content'][0]['text']
