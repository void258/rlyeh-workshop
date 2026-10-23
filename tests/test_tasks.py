import json

import pytest

from rlyeh import importers, tasks, voice
from rlyeh.cli import main
from rlyeh.project import Project


def by_id(proj):
    return {t.id: t for t in tasks.plan(proj)}


def test_fresh_example_flow(example_project):
    proj = example_project
    t = by_id(proj)
    assert t['import.run'].status == 'todo' and tasks.next_task(proj).id == 'import.run'
    assert t['cast.write'].status == 'done' and t['script.lint'].status == 'done' and t['art.prompts'].status == 'done'
    assert t['voice.design'].status == 'skip' and t['voice.pick'].status == 'skip'          # 占位配音不用选声线
    importers.run(proj.root, proj.config)
    nxt = tasks.next_task(Project(proj.root))
    assert nxt.id == 'script.write' and nxt.kind == 'agent' and nxt.playbook == 'rlyeh-script'
    tasks.complete(proj, 'script.write', '示例剧本已经覆盖记录')
    proj = Project(proj.root)
    assert by_id(proj)['script.write'].status == 'done'
    assert tasks.next_task(proj).id == 'voice.build'
    voice.build(proj)
    t = by_id(proj)
    assert t['voice.build'].status == 'done' and t['voice.bleep'].status == 'todo' and t['voice.bleep'].command == ['bleep']
    assert tasks.next_task(proj).id == 'voice.bleep'


def test_agent_records_go_stale(example_project):
    proj = example_project
    importers.run(proj.root, proj.config)
    tasks.complete(proj, 'script.write')
    log = proj.root / 'logs' / 'raw' / 'session-2024-05-18.txt'
    log.write_text(log.read_text(encoding='utf-8') + '[2024-05-18 20:19:00] GM：补一句\n', encoding='utf-8')
    importers.run(proj.root, proj.config)
    assert by_id(Project(proj.root))['script.write'].status == 'stale'                      # 记录变了：再看一遍


def test_conditions(example_project):
    proj = example_project
    script = proj.root / 'script' / '01-雾港灯塔.md'
    script.write_text(script.read_text(encoding='utf-8') + '\n陌生人：〔低声〕你们是谁？\n【背景：没写过的地方】\n【BGM：没写过的曲子】\n',
                      encoding='utf-8')
    proj = Project(proj.root)
    t = by_id(proj)
    assert t['cast.write'].status == 'todo' and any('陌生人' in m for m in t['cast.write'].detail['unknown_speakers'])
    assert t['script.ids'].status == 'todo' and t['art.jobs'].status == 'todo'
    assert t['music.sheet'].status == 'todo' and t['music.sheet'].detail['missing'] == ['没写过的曲子']
    with pytest.raises(tasks.TaskError, match='condition'):
        tasks.complete(proj, 'cast.write')                     # 条件型任务要真的改好，不能直接标完成
    with pytest.raises(tasks.TaskError, match='tool task'):
        tasks.complete(proj, 'voice.build')
    with pytest.raises(tasks.TaskError, match='unknown'):
        tasks.complete(proj, 'nope')


def test_optional_theme_last(example_project):
    proj = example_project
    t = by_id(proj)
    assert t['player.theme'].optional and t['player.theme'].status == 'todo'
    tasks.complete(proj, 'player.theme', '用默认主题')
    assert by_id(Project(proj.root))['player.theme'].status == 'done'


def test_cli_next_done(example_project, capsys):
    root = str(example_project.root)
    assert main(['next', '-C', root, '--json']) == 0
    assert json.loads(capsys.readouterr().out)['next']['id'] == 'import.run'
    assert main(['next', '-C', root, '--all', '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out['tasks']) >= 25 and out['overview']['todo'] >= 1
    assert main(['done', 'voice.build', '-C', root, '--json']) == 3
    assert 'tool task' in json.loads(capsys.readouterr().out)['error']
