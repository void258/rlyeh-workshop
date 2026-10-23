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


def test_script_editor(server, example_project):
    root = example_project.root
    server('/api/studio/open', {'path': str(root)})
    code, data, _ = server('/api/script')
    assert code == 200 and data['files'][0]['number'] == 1 and data['files'][0]['lines'] == 24
    rel = data['files'][0]['path']
    assert rel.startswith('script/') and data['files'][0]['errors'] == 0

    doc = server('/api/script/file?path=' + urllib.request.quote(rel))[1]['file']
    assert doc['text'].startswith('---\n') and len(doc['version']) == 16
    assert server('/api/script/file?path=replay.toml')[0] == 400                 # 只认 script/ 下面的 .md
    assert server('/api/script/file?path=script/../replay.toml')[0] == 400

    # 没保存的内容也能校验：说话人不在角色表、没 ID
    text = doc['text'] + '\n路人甲：〔大喊〕快跑！\n'
    issues = server('/api/script/lint', {'path': rel, 'text': text, 'lang': 'zh'})[1]['issues']
    last = text.count('\n')
    codes = {i['code'] for i in issues if i['line'] == last}
    assert {'lint.unknown_speaker', 'lint.no_id'} <= codes
    en = server('/api/script/lint', {'path': rel, 'text': text, 'lang': 'en'})[1]['issues']
    assert any('not in cast.yaml' in i['message'] for i in en)

    # 保存：带上打开时的版本；删掉的台词 ID 会报出来
    first_id = next(line for line in doc['text'].split('\n') if ' ^c1-0001' in line)
    shorter = doc['text'].replace(first_id + '\n', '')
    code, saved, _ = server('/api/script/save', {'path': rel, 'text': shorter, 'base': doc['version']})
    assert code == 200 and saved['removed'] == ['c1-0001']
    assert (root / rel).read_text(encoding='utf-8') == shorter
    code, data, _ = server('/api/script/save', {'path': rel, 'text': doc['text'], 'base': doc['version']})
    assert code == 409 and data['conflict']['version'] == saved['version']   # 文件已经变了：不覆盖
    code, data, _ = server('/api/script/save', {'path': rel, 'text': doc['text'], 'base': doc['version'], 'force': True})
    assert code == 200 and (root / rel).read_text(encoding='utf-8') == doc['text']

    # 新建章节、补台词 ID
    code, data, _ = server('/api/script/new', {'title': '尾声'})
    assert code == 200 and data['path'] == 'script/02-weisheng.md'
    new = root / data['path']
    assert new.read_text(encoding='utf-8').startswith('---\nchapter: 2\ntitle: 尾声\nlang: zh-CN\n---\n\n【章节：尾声】')
    assert server('/api/script/new', {'title': ''})[0] == 400
    new.write_text(new.read_text(encoding='utf-8') + '旁白：〔平静〕雾散了。\n', encoding='utf-8')
    code, data, _ = server('/api/script/ids', {'lang': 'zh'})
    assert code == 200 and data['assigned'] == 1 and new.read_text(encoding='utf-8').rstrip().endswith('^c2-0001')

    meta = server('/api/script/meta')[1]
    arlo = next(s for s in meta['speakers'] if s['id'] == 'arlo')
    assert '阿洛' in arlo['names'] and arlo['expressions']
    assert any(d['name'] == 'fx' and '特效' in d['aliases'] for d in meta['directives'])
    assert 'shake' in meta['enums']['fx'] and meta['players'] and meta['cues']


def test_review_pages_shared_style(server):
    code, css, headers = server('/static/common.css', raw=True)                # 不需要打开项目
    assert code == 200 and headers['Content-Type'].startswith('text/css') and b'[hidden]' in css
    assert server('/static/common.js', raw=True)[0] == 200
    assert server('/api/studio/player')[0] == 409


def test_agent_settings_video(server, example_project):
    root = example_project.root
    server('/api/studio/open', {'path': str(root)})

    info = server('/api/agent?lang=zh')[1]
    assert info['default'] == 'claude-code' and info['exported'] == {} and 'AGENTS.md' in info['prompt']
    assert set(info['installed']) == {'claude-code', 'codex', 'dsh'}
    code, res, _ = server('/api/agent/export', {'harness': ['codex'], 'lang': 'zh'})
    assert code == 200 and (root / '.codex' / 'config.toml').is_file() and any('Codex' in n for n in res['notes'])
    assert 'codex' in server('/api/agent?lang=zh')[1]['exported']
    assert server('/api/agent/export', {'harness': ['cursor']})[0] == 400

    (root / 'review').mkdir(exist_ok=True)
    (root / 'review' / 'requests.json').write_text(json.dumps([{'kind': 'art', 'items': ['bg'], 'note': '看背景', 'at': 'x', 'status': 'open'}]),
                                                  encoding='utf-8')
    assert server('/api/studio/attention')[1]['requests'] == 1
    assert server('/api/agent/request', {'index': 0})[0] == 200
    assert server('/api/studio/attention')[1]['requests'] == 0
    assert server('/api/agent/request', {'index': 5})[0] == 400

    # 设置：只改允许改的几项，注释留着
    before = (root / 'replay.toml').read_text(encoding='utf-8')
    s = server('/api/settings')[1]
    image = next(b for b in s['backends'] if b['kind'] == 'image')
    assert image['current'] == 'placeholder' and {o['id'] for o in image['options']} >= {'codex', 'manual', 'placeholder'}
    assert server('/api/settings', {'table': 'backends', 'key': 'image', 'value': 'manual'})[0] == 200
    assert server('/api/settings', {'table': 'harness.codex', 'key': 'model', 'value': 'gpt-6.1-sol'})[0] == 200
    assert server('/api/settings', {'table': 'harness.codex', 'key': 'effort', 'value': 'low'})[0] == 200
    after = (root / 'replay.toml').read_text(encoding='utf-8')
    import tomllib
    cfg = tomllib.loads(after)
    assert cfg['backends']['image'] == 'manual' and cfg['harness']['codex'] == {'model': 'gpt-6.1-sol', 'effort': 'low'}
    assert [line for line in before.split('\n') if line.lstrip().startswith('#')] == \
           [line for line in after.split('\n') if line.lstrip().startswith('#')]                # 注释一行都没少
    assert server('/api/settings', {'table': 'harness.codex', 'key': 'model', 'value': ''})[0] == 200
    assert 'model' not in tomllib.loads((root / 'replay.toml').read_text(encoding='utf-8'))['harness']['codex']
    assert server('/api/settings', {'table': 'backends', 'key': 'image', 'value': 'nope'})[0] == 400
    assert server('/api/settings', {'table': 'project', 'key': 'id', 'value': 'x'})[0] == 400

    checks = server('/api/doctor?lang=en')[1]['checks']
    assert {c['group'] for c in checks} >= {'env', 'backends', 'project'}

    v = server('/api/video')[1]
    assert v['files'] == [] and not v['player'] and v['chapters'][0]['first'] == 'c1-0001'
    vdir = root / 'build' / 'video'
    vdir.mkdir(parents=True)
    for name in ('fog-harbor.mp4', 'fog-harbor_video.mp4', 'fog-harbor_share.mp4'):
        (vdir / name).write_bytes(bytes(range(256)) * 4)
    v = server('/api/video')[1]
    assert [(f['name'], f['kind']) for f in v['files']] == [('fog-harbor.mp4', 'master'), ('fog-harbor_share.mp4', 'share')]
    assert server('/api/reveal', {'path': '../outside'})[0] == 400                          # 只认项目里面的

    # /files 支持 Range（视频能拖进度条）
    code, part, headers = server('/files/build/video/fog-harbor.mp4', headers={'Range': 'bytes=10-19'}, raw=True)
    assert code == 206 and part == bytes(range(10, 20)) and headers['Content-Range'] == 'bytes 10-19/1024'
    code, part, _ = server('/files/build/video/fog-harbor.mp4', headers={'Range': 'bytes=-4'}, raw=True)
    assert code == 206 and part == bytes(range(252, 256))
    code, whole, headers = server('/files/build/video/fog-harbor.mp4', raw=True)
    assert code == 200 and len(whole) == 1024 and headers['Accept-Ranges'] == 'bytes'
    assert server('/files/build/video/fog-harbor.mp4', headers={'Range': 'bytes=5000-'}, raw=True)[0] == 416
