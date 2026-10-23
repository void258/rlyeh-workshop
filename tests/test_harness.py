"""replay export-agent：流程手册、技能和三家 harness 的 MCP 配置。"""
import json
import re
import tomllib

import yaml

from rlyeh import harness, tasks
from rlyeh.cli import main


def test_playbook_skills_are_valid():
    names = {}
    for lang in ('zh', 'en'):
        book = harness.playbook(lang)
        assert 'AGENTS.md' in book
        skills = {}
        for rel, text in book.items():
            if not rel.startswith('skills/'):
                continue
            folder = rel.split('/')[1]
            meta = harness.front_matter(text)
            assert meta['name'] == folder
            assert re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', folder) and len(folder) <= 64
            assert 0 < len(meta['description']) <= 1024
            skills[folder] = text
        names[lang] = set(skills)
    assert names['zh'] == names['en'] and len(names['zh']) == 8
    used = {line.split("playbook='")[1].split("'")[0]
            for line in open(tasks.__file__, encoding='utf-8') if "playbook='" in line}
    assert used <= names['zh']                          # 任务里点名的技能都有


def test_export_all(make_project, capsys):
    proj = make_project()
    root = proj.root
    assert main(['export-agent', 'all', '-C', str(root), '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['ok'] and out['harnesses'] == ['claude-code', 'codex', 'dsh']
    for rel in ('AGENTS.md', 'CLAUDE.md', '.claude/skills/rlyeh-script/SKILL.md', '.agents/skills/rlyeh-voice/SKILL.md'):
        assert (root / rel).is_file(), rel
    assert (root / 'CLAUDE.md').read_text(encoding='utf-8').strip() == '@AGENTS.md'
    assert b'\r\n' not in (root / 'AGENTS.md').read_bytes()

    server = json.loads((root / '.mcp.json').read_text(encoding='utf-8'))['mcpServers']['rlyeh']
    assert server['args'][-3:] == ['mcp', '-C', str(root)]
    codex = tomllib.loads((root / '.codex/config.toml').read_text(encoding='utf-8'))
    assert codex['mcp_servers']['rlyeh']['args'] == server['args'] and 'model' not in codex
    rows = yaml.safe_load((root / harness.DSH_PATCH).read_text(encoding='utf-8'))
    mcp = rows[-1]['insert'][0]
    assert mcp['name'] == '@deepseek-ai/dsh-mcp-client' and mcp['config']['serverName'] == 'rlyeh'
    assert mcp['config']['command'] == server['command'] and len(rows) == 1     # 没配模型就不改 dsh 的默认模型
    assert any('codex_no_model' in n or 'effort' in n for n in out['notes'])

    assert main(['export-agent', 'all', '-C', str(root), '--json']) == 0       # 再导一次什么都不变
    again = json.loads(capsys.readouterr().out)
    assert {f['action'] for f in again['files']} == {'unchanged'}


def test_export_keeps_edits(make_project, capsys):
    proj = make_project()
    root = proj.root
    harness.export(proj, ['codex'])
    skill = root / '.agents/skills/rlyeh-art/SKILL.md'
    skill.write_text(skill.read_text(encoding='utf-8') + '\n- 本团不画血\n', encoding='utf-8')
    res = harness.export(proj, ['codex'])
    row = next(f for f in res['files'] if f['path'] == '.agents/skills/rlyeh-art/SKILL.md')
    assert row['action'] == 'kept' and row['reason'] == 'edited' and '本团不画血' in skill.read_text(encoding='utf-8')

    agents = root / 'AGENTS.md'                         # 旧版本写的、用户没动过：升级后直接换成新的
    agents.write_text('旧版手册\n', encoding='utf-8')
    record = json.loads((root / harness.RECORD).read_text(encoding='utf-8'))
    record['files']['AGENTS.md'] = harness._digest('旧版手册\n')
    (root / harness.RECORD).write_text(json.dumps(record), encoding='utf-8')
    res = harness.export(proj, ['codex'])
    assert next(f for f in res['files'] if f['path'] == 'AGENTS.md')['action'] == 'updated'

    assert main(['export-agent', 'codex', '--force', '-C', str(root), '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['ok'] and '本团不画血' not in skill.read_text(encoding='utf-8')


def test_export_merges_configs(make_project):
    extra = ('\n[harness.codex]\nmodel = "gpt-6.1-sol"\neffort = "low"\n'
             '\n[harness.claude-code]\nmodel = "sonnet"\n'
             '\n[harness.dsh]\nmodel = "deepseek-pro"\n')
    proj = make_project(extra=extra)
    root = proj.root
    (root / 'CLAUDE.md').write_text('# 我的笔记\n别动这一行\n', encoding='utf-8')
    (root / '.mcp.json').write_text(json.dumps({'mcpServers': {'other': {'command': 'x'}}}), encoding='utf-8')
    (root / '.codex').mkdir()
    (root / '.codex/config.toml').write_text(
        '# 我的设置\napproval_policy = "on-request"\nmodel = "old"\n\n[mcp_servers.other]\ncommand = "y"\n\n'
        '[mcp_servers.rlyeh]\ncommand = "stale"\n\n[mcp_servers.rlyeh.env]\nA = "1"\n\n[profiles.fast]\nmodel = "z"\n',
        encoding='utf-8')
    res = harness.export(proj, ['claude-code', 'codex', 'dsh'], command='replay')
    actions = {f['path']: f['action'] for f in res['files']}
    assert actions['CLAUDE.md'] == actions['.mcp.json'] == actions['.codex/config.toml'] == 'merged'

    claude = (root / 'CLAUDE.md').read_text(encoding='utf-8')
    assert claude.startswith('@AGENTS.md\n') and '别动这一行' in claude
    servers = json.loads((root / '.mcp.json').read_text(encoding='utf-8'))['mcpServers']
    assert servers['other'] == {'command': 'x'} and servers['rlyeh']['command'] == 'replay'
    assert json.loads((root / '.claude/settings.json').read_text(encoding='utf-8')) == {'model': 'sonnet'}

    text = (root / '.codex/config.toml').read_text(encoding='utf-8')
    codex = tomllib.loads(text)
    assert text.startswith('# 我的设置\n')
    assert codex['model'] == 'gpt-6.1-sol' and codex['model_reasoning_effort'] == 'low' and codex['approval_policy'] == 'on-request'
    assert codex['mcp_servers']['other'] == {'command': 'y'} and codex['profiles']['fast'] == {'model': 'z'}
    assert codex['mcp_servers']['rlyeh']['command'] == 'replay' and 'env' not in codex['mcp_servers']['rlyeh']

    rows = yaml.safe_load((root / harness.DSH_PATCH).read_text(encoding='utf-8'))
    assert rows[0] == {'id': 'agent-default-model', 'config': {'provider': 'deepseek-official', 'model': 'deepseek-pro'}}

    again = harness.export(proj, ['claude-code', 'codex', 'dsh'], command='replay')
    assert {f['action'] for f in again['files']} == {'unchanged'}


def test_export_leaves_broken_config(make_project, capsys):
    proj = make_project()
    (proj.root / '.mcp.json').write_text('{oops', encoding='utf-8')
    assert main(['export-agent', 'claude-code', '-C', str(proj.root), '--json']) == 0
    out = json.loads(capsys.readouterr().out)
    assert not out['ok'] and out['kept'] == ['.mcp.json']
    assert (proj.root / '.mcp.json').read_text(encoding='utf-8') == '{oops'


def test_export_language_and_default(make_project, capsys):
    proj = make_project(extra='')
    res = harness.export(proj, lang='en')               # 不写 harness 就用 [harness] default
    assert res['harnesses'] == ['claude-code'] and res['lang'] == 'en'
    assert (proj.root / 'AGENTS.md').read_text(encoding='utf-8').startswith("# R'lyeh Workshop project")
    assert main(['export-agent', 'cursor', '-C', str(proj.root), '--json']) == 3
    assert 'cursor' in json.loads(capsys.readouterr().out)['error']


def test_mcp_command(tmp_path):
    cmd, args = harness.mcp_command(tmp_path)
    assert args[-3:] == ['mcp', '-C', str(tmp_path)]
    assert cmd.lower().endswith(('replay', 'replay.exe')) or args[:2] == ['-m', 'rlyeh.cli']
    assert harness.mcp_command(tmp_path, 'replay') == ('replay', ['mcp', '-C', str(tmp_path)])
