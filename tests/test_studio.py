"""replay studio：本地服务的接口（打开、新建项目，任务看板，后台任务）和安全检查。"""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from rlyeh import studio


@pytest.fixture
def server(tmp_path):
    st = studio.Studio(config_dir=tmp_path / 'home')
    srv = studio.make_server(st, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}'

    def call(path, body=None, headers=None, raw=False):
        h = {'X-Rlyeh': '1', 'Content-Type': 'application/json'} if body is not None else {}
        h.update(headers or {})
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode('utf-8'), headers=h)
        try:
            with urllib.request.urlopen(req) as r:
                data = r.read()
                return r.status, (data if raw else json.loads(data)), r.headers
        except urllib.error.HTTPError as e:
            data = e.read()
            try:
                return e.code, json.loads(data), e.headers
            except ValueError:
                return e.code, data, e.headers

    call.studio = st
    yield call
    srv.shutdown()
    srv.server_close()


def test_no_project(server):
    code, data, _ = server('/api/studio/state')
    assert code == 200 and data['project'] is None and data['recent'] == []
    assert server('/api/tasks')[0] == 409
    assert server('/api/voices')[0] == 409                 # 审核页的接口也要先打开项目
    code, page, headers = server('/', raw=True)
    assert code == 200 and b'id="root"' in page and headers['Content-Type'].startswith('text/html')
    code, js, headers = server('/assets/studio.js', raw=True)
    assert code == 200 and headers['Content-Type'].startswith('text/javascript')
    assert server('/assets/%2E%2E/__init__.py', raw=True)[0] != 200


def test_guards(server, tmp_path):
    code, _, _ = server('/api/studio/new', {'path': str(tmp_path / 'x')}, headers={'X-Rlyeh': ''})
    assert code == 403 and not (tmp_path / 'x').exists()  # 没有 X-Rlyeh 头：别的网站发不出这种请求
    code, _, _ = server('/api/studio/state', headers={'Host': 'evil.example:80'})
    assert code == 403                                     # DNS 重绑定


def test_new_and_browse(server, tmp_path):
    target = tmp_path / 'camp' / 'new-one'
    code, data, _ = server('/api/studio/new', {'path': str(target), 'title': '新的团', 'lang': 'en'})
    assert code == 200 and data['project']['title'] == '新的团' and data['project']['lang'] == 'en'
    assert (target / 'replay.toml').is_file() and (target / 'script' / '01-chapter.md').is_file()
    code, data, _ = server('/api/studio/new', {'path': str(target)})
    assert code == 400 and 'replay.toml' in data['error']
    code, data, _ = server('/api/studio/state')
    assert data['project']['root'] == str(target) and data['recent'][0]['path'] == str(target)
    assert json.loads((tmp_path / 'home' / 'studio.json').read_text(encoding='utf-8'))['recent'][0]['title'] == '新的团'

    code, data, _ = server('/api/studio/browse?path=' + urllib.request.quote(str(tmp_path / 'camp')))
    assert code == 200 and data['dirs'] == [{'name': 'new-one', 'path': str(target), 'project': True}]
    assert data['parent'] == str(tmp_path)
    assert server('/api/studio/browse?path=' + urllib.request.quote(str(tmp_path / 'nope')))[0] == 400

    assert server('/api/studio/close', {})[0] == 200
    assert server('/api/studio/state')[1]['project'] is None
    code, data, _ = server('/api/studio/open', {'path': str(tmp_path)})
    assert code == 400


def test_board_and_jobs(server, example_project):
    root = example_project.root
    code, data, _ = server('/api/studio/open', {'path': str(root / 'script')})   # 子文件夹也能找到项目
    assert code == 200 and data['project']['root'] == str(root)

    code, board, _ = server('/api/tasks?lang=zh')
    assert code == 200 and board['next'] == 'import.run'
    ids = {x['id']: x for x in board['tasks']}
    assert ids['import.run']['kind'] == 'tool' and ids['import.run']['title'].startswith('导入')
    en = server('/api/tasks?lang=en')[1]
    assert next(x for x in en['tasks'] if x['id'] == 'import.run')['title'].startswith('Import')

    assert server('/api/run', {'task': 'script.write'})[0] == 400   # agent 任务不能当工具跑
    assert server('/api/run', {'stage': 'import', 'args': ['-C', '/']})[0] == 400
    code, data, _ = server('/api/run', {'task': 'import.run'})
    assert code == 200 and data['job']['command'] == ['import'] and data['job']['status'] == 'queued'
    jid = data['job']['id']
    for _ in range(120):
        job = server(f'/api/jobs/{jid}')[1]['job']
        if job['status'] not in ('queued', 'running'):
            break
        time.sleep(0.5)
    assert job['status'] == 'done' and job['result']['ok'] and job['offset'] == len(job['log'])
    again = server(f'/api/jobs/{jid}?offset={job["offset"]}')[1]['job']
    assert again['log'] == ''
    assert server('/api/jobs')[1]['jobs'][0]['id'] == jid
    assert server('/api/jobs/..%5C..%5Cx')[0] == 400

    board = server('/api/tasks?lang=zh')[1]
    assert next(x for x in board['tasks'] if x['id'] == 'import.run')['status'] == 'done'
    write = next(x for x in board['tasks'] if x['id'] == 'script.write')
    assert write['status'] == 'todo' and 'key' in write['detail']
    code, data, _ = server('/api/tasks/done', {'id': 'script.write'})
    assert code == 200 and data['record']['key'] == write['detail']['key']
    assert server('/api/tasks/done', {'id': 'import.run'})[0] == 400

    code, voices, _ = server('/api/voices')                  # 审核页接口照常可用
    assert code == 200 and voices['meta']['title']
