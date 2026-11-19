"""Two public static revisions driven through the real built UI and a temporary Store.

The only model answers are the fixed after-sales fixture (no provider is contacted).
The task itself is created from the browser; configuration and the six public cases
are seeded through same-origin API requests after that UI creation.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from uuid import uuid4

import yaml

PROJECT = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--playwright', required=True)
parser.add_argument('--platform', action='store_true',
                    help='用正常页面完成两版导入／发布／Key／试跑／诊断，替身仅在本机')
args = parser.parse_args()
output = Path(args.output).resolve()
assert output.is_relative_to(PROJECT / 'work'), '输出目录必须位于项目 work 下'
assert not output.exists(), '输出目录必须尚不存在'
output.mkdir(parents=True, exist_ok=False)

TASK_NAME = '公开售后静态双版界面验收'
DOCUMENT_PREFIX = '当前任务资料：'

with tempfile.TemporaryDirectory(dir=output, prefix='public-store-') as folder:
    os.environ['FLOWCRAFT_DATA_DIR'] = folder
    sys.path[:0] = [str(PROJECT / 'backend'), str(PROJECT / 'backend/tests')]
    import httpx
    import uvicorn
    from fastapi.testclient import TestClient
    from app import main as h
    from app.storage import Store
    from app.intake import BASE
    from app.after_sales_starter import prepare
    from test_api import planning_provider, create_env
    from test_after_sales_intake_to_graph import (
        OPENING, REQUIREMENTS, CLARIFY_ANSWER, NEW_NO_HIT_REPLY, acceptance_cases,
        answer_for, case_turns, turn_identity)
    from test_after_sales_starter import context, inputs

    h.DATA_ROOT = Path(folder)
    h.store = Store(Path(folder))

    def forbidden(*args, **kwargs):
        raise AssertionError('No physical model or Dify HTTP is allowed')

    httpx.HTTPTransport.handle_request = forbidden
    httpx.AsyncHTTPTransport.handle_async_request = forbidden
    h.DifyClient.request = forbidden
    h.call_model = forbidden

    ANSWER = '\n'.join(REQUIREMENTS.values())
    REQUEST = f'请把无命中和资料不足的固定回复都改成「{NEW_NO_HIT_REPLY}」。其余规则和分支保持。'
    OLD_REPLY = inputs()['no_hit_reply']
    EXPECTED_TOPICS = set(BASE) | {'memory', 'dialogue', 'retrieval', 'external', 'conversation_state'}
    TOPIC_FIELD = {'memory': 'rules', 'dialogue': 'exceptions', 'retrieval': 'knowledge',
                   'external': 'rules', 'conversation_state': 'rules'}

    def seeded_cases():
        rows = acceptance_cases()
        for row in rows:
            row.setdefault('required', True)
        return rows

    calls = []

    def sole_task():
        tasks = h.store.list('task')
        assert len(tasks) == 1, '临时目录中只能有界面创建的一个任务'
        return tasks[0]

    PUBLIC_KEY = 'sierra-isolated-not-a-real-key'
    substitute_apps = []
    substitute_state = {}
    substitute_service_calls = []
    substitute_reads = {'messages': [], 'runs': [], 'nodes': []}
    substitute_events = []

    def app_and_rest(path):
        parts = path.split('/')
        assert len(parts) >= 5 and parts[1:4] == ['console', 'api', 'apps'], '未知管理路径：' + path
        app_id = parts[4]
        assert app_id in substitute_state, '未知替身App：' + app_id
        return app_id, parts[5:]

    async def substitute_request(self, method, path, *, credential, secret_owner=None,
                                 _console_refreshed=False, **kwargs):
        task = sole_task()
        assert self.env['id'] == environment_id, '替身请求环境不匹配'
        if path == '/console/api/apps/imports':
            assert (method, credential) == ('POST', 'console_token')
            assert len(substitute_apps) < 2, '本检查只允许两版各一次导入'
            expected = yaml.safe_load(h.artifact_path(task).read_bytes())
            root = yaml.safe_load(kwargs['json']['yaml_content'])
            assert root == expected, '导入内容必须是当前成果DSL'
            app_id = str(uuid4())
            assert app_id not in substitute_state
            graph = root['workflow']['graph']
            draft = root['workflow'] | {'hash': 'fixture-draft-' + app_id}
            no_hit = next(node['data']['template'] for node in graph['nodes']
                          if node['id'] == 'no_hit')
            substitute_state[app_id] = {
                'root': root, 'graph': graph, 'draft': draft, 'published': None,
                'served': {}, 'messages': {}, 'cid': {}, 'revision': task['revision'],
                'no_hit': no_hit}
            substitute_apps.append(app_id)
            return {'status': 'completed', 'app_id': app_id}
        if path == '/v1/chat-messages':
            assert (method, credential) == ('POST', 'service_api_key')
            app_id = self.env.get('service_app_id')
            assert app_id in substitute_state, '运行Key未绑定到本检查的替身App'
            app = substitute_state[app_id]
            assert app['published'] is not None, '未发布替身App不可试跑'
            assert app['revision'] == task['revision'], '替身试跑修订不匹配'
            body = kwargs['json']
            query = body['query']
            case_id, index = turn_identity(task['test_cases'], query)
            key = (case_id, index)
            assert key not in app['served'], '同一轮次不允许重复试跑'
            assert body.get('inputs') == {}, '样例输入只应包含query'
            if index == 0:
                assert body.get('conversation_id') in (None, ''), '首轮不应带旧会话'
                cid = str(uuid4())
                app['cid'][case_id] = cid
            else:
                assert body.get('conversation_id') == app['cid'].get(case_id), '后续轮必须沿同一会话'
                cid = app['cid'][case_id]
            message_id, run_id = str(uuid4()), str(uuid4())
            app['served'][key] = {'case_id': case_id, 'index': index, 'message_id': message_id,
                                  'run_id': run_id, 'conversation_id': cid, 'query': query}
            app['messages'][message_id] = (cid, run_id)
            substitute_service_calls.append((app_id, query))
            substitute_events.append(('service', app_id))
            return {'answer': answer_for(query, app['no_hit']), 'conversation_id': cid,
                    'id': message_id, 'message_id': message_id}
        app_id, rest = app_and_rest(path)
        app = substitute_state[app_id]
        assert credential == 'console_token'
        if rest == []:
            assert method == 'GET'
            return {'id': app_id, 'mode': 'advanced-chat'}
        if rest == ['workflows', 'draft']:
            assert method == 'GET'
            return app['draft']
        if rest == ['workflows', 'publish']:
            if method == 'POST':
                assert app['published'] is None, '同一App不允许重复发布'
                app['published'] = app['draft'] | {'id': str(uuid4())}
                return {'result': 'success'}
            assert method == 'GET'
            return app['published']
        if rest[:1] == ['messages'] and len(rest) == 2:
            assert method == 'GET'
            message_id = rest[1]
            assert message_id in app['messages'], '未知消息ID'
            cid, run_id = app['messages'][message_id]
            substitute_reads['messages'].append((app_id, message_id))
            substitute_events.append(('read', app_id))
            return {'id': message_id, 'conversation_id': cid,
                    'workflow_run_id': run_id, 'app_id': app_id}
        if rest[:1] == ['workflow-runs'] and len(rest) == 3 and rest[2] == 'node-executions':
            assert method == 'GET'
            run_id = rest[1]
            assert run_id in {row['run_id'] for row in app['served'].values()}, '未知运行ID'
            substitute_reads['nodes'].append((app_id, run_id))
            llm_node = next(node['id'] for node in app['graph']['nodes']
                            if node['data']['type'] == 'llm')
            return {'data': [{'id': str(uuid4()), 'node_id': llm_node, 'node_type': 'llm',
                              'title': '合成LLM节点', 'status': 'succeeded', 'error': None}]}
        if rest[:1] == ['workflow-runs'] and len(rest) == 2:
            assert method == 'GET'
            run_id = rest[1]
            assert run_id in {row['run_id'] for row in app['served'].values()}, '未知运行ID'
            substitute_reads['runs'].append((app_id, run_id))
            return {'id': run_id, 'status': 'succeeded', 'graph': app['graph']}
        raise AssertionError(f'未知管理请求：{method} {path}')

    def opening_reply():
        question = {'topic': 'goal', 'question': '售后助手要处理哪些问题，还需要查订单吗？',
                    'recommendation': '先说明资料与订单范围。', 'reason': '明确需覆盖的分支。',
                    'experience': '先确认范围再出图。', 'cost': '资源费用后续核对。',
                    'manual_work': '请补充规则。'}
        rows = [{'topic': key, 'status': 'needs_input', 'detail': '尚需明确', 'evidence': []}
                for key in (*BASE, 'memory', 'dialogue')]
        return {'message': question['question'], 'requirements_patch': {},
                'intake_review': {'schema_version': 1, 'checks': rows, 'questions': [question]}}

    def requirements_reply(data):
        source = next(row for row in data['intake_sources']
                      if row['kind'] == 'message' and row['text'] == ANSWER)
        rows = [{'topic': key, 'status': 'complete', 'detail': '用户已补充规则。',
                 'evidence': [{'kind': 'message', 'id': source['id'],
                               'quote': REQUIREMENTS[TOPIC_FIELD.get(key, key)]}]}
                for key in sorted(EXPECTED_TOPICS)]
        return {'message': '售后范围和模拟条件已记录，请核对确认。',
                'requirements_patch': REQUIREMENTS,
                'intake_review': {'schema_version': 1, 'checks': rows, 'questions': []}}

    def revision_reply(data, task):
        source = next(row for row in data['intake_sources']
                      if row['kind'] == 'message' and row['text'] == REQUEST)
        review = copy.deepcopy(data['previous_intake'])
        for row in review['checks']:
            if row['topic'] in {'exceptions', 'dialogue'}:
                row['evidence'] = [{'kind': 'message', 'id': source['id'], 'quote': NEW_NO_HIT_REPLY}]
        exceptions = task['requirements']['exceptions'].replace(OLD_REPLY, NEW_NO_HIT_REPLY)
        assert exceptions != task['requirements']['exceptions']
        return {'message': '已记录新回复，其余规则保持，请复核。',
                'requirements_patch': {'exceptions': exceptions}, 'intake_review': review}

    def original_plan(task):
        text, validation = prepare(task, inputs() | {'clarify_reply': CLARIFY_ANSWER})
        assert validation['valid']
        return json.loads(text)

    def revised_plan(baseline, requirements):
        old_plan = copy.deepcopy(baseline['plan'])
        assert NEW_NO_HIT_REPLY not in json.dumps(old_plan, ensure_ascii=False)
        assert OLD_REPLY in json.dumps(old_plan, ensure_ascii=False)
        assert NEW_NO_HIT_REPLY in requirements['exceptions']
        new_plan = copy.deepcopy(old_plan)
        nodes = {node['id']: node for node in new_plan['nodes']}
        nodes['no_hit']['config']['template'] = NEW_NO_HIT_REPLY
        prompt_config = nodes['grounded_answer']['config']
        assert OLD_REPLY in prompt_config['system_prompt']
        prompt_config['system_prompt'] = prompt_config['system_prompt'].replace(
            OLD_REPLY, NEW_NO_HIT_REPLY)
        return new_plan

    async def model(provider, key, messages, **kwargs):
        task = sole_task()
        prompt = messages[1]['content']
        if prompt.startswith(DOCUMENT_PREFIX):
            data = json.loads(prompt[len(DOCUMENT_PREFIX):])
            assert NEW_NO_HIT_REPLY not in json.dumps(data['requirements'], ensure_ascii=False)
            interviews = [call for call in calls if call['kind'] == 'interview']
            if len(interviews) == 0:
                assert OPENING in messages[-1]['content']
                assert not any(data['requirements'].values())
                result = opening_reply()
                calls.append({'kind': 'interview', 'stage': 'opening', 'revision': task['revision']})
            elif len(interviews) == 1:
                assert ANSWER in messages[-1]['content']
                result = requirements_reply(data)
                calls.append({'kind': 'interview', 'stage': 'requirements', 'revision': task['revision']})
            else:
                assert len(interviews) == 2
                assert REQUEST in messages[-1]['content']
                result = revision_reply(data, task)
                calls.append({'kind': 'interview', 'stage': 'revision', 'revision': task['revision']})
        else:
            data = json.loads(prompt)
            baseline = data['existing_plan_context']
            if baseline is None:
                assert data['requirements'] == REQUIREMENTS
                assert data['intake_assessment']['can_confirm']
                assert NEW_NO_HIT_REPLY not in json.dumps(data, ensure_ascii=False)
                result = original_plan(task)
                calls.append({'kind': 'plan', 'stage': 'original', 'revision': task['revision']})
            else:
                assert baseline['changed_requirements_fields'] == ['exceptions']
                result = revised_plan(baseline, data['requirements'])
                calls.append({'kind': 'plan', 'stage': 'revision', 'revision': task['revision']})
        return json.dumps(result, ensure_ascii=False), {'prompt_tokens': 100, 'completion_tokens': 30}

    environment_id = None
    with TestClient(h.app) as client:
        planning_provider(client)
        if args.platform:
            environment_id = create_env(client)['id']
    h.call_model = model
    if args.platform:
        h.DifyClient.request = substitute_request

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    info = {
        'base': f'http://127.0.0.1:{port}',
        'output': str(output),
        'task_name': TASK_NAME,
        'opening': OPENING,
        'requirements': ANSWER,
        'request': REQUEST,
        'new_reply': NEW_NO_HIT_REPLY,
        'old_reply': OLD_REPLY,
        'configuration': context()['configuration'],
        'cases': acceptance_cases(),
        'platform_mode': args.platform,
        'environment_id': environment_id,
        'public_fixture_runtime_key': PUBLIC_KEY,
        'assistant_messages': {
            'opening': '售后助手要处理哪些问题，还需要查订单吗？',
            'requirements': '售后范围和模拟条件已记录，请核对确认。',
            'revision': '已记录新回复，其余规则保持，请复核。',
        },
    }
    (output / 'info.json').write_text(json.dumps(info, ensure_ascii=False), 'utf-8')

    server = uvicorn.Server(uvicorn.Config(h.app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    failure = None
    try:
        for _ in range(100):
            if server.started:
                break
            assert thread.is_alive(), '本地服务线程提前退出'
            time.sleep(.1)
        assert server.started, '本地服务未启动'
        result = subprocess.run(
            ['node', str(PROJECT / 'tools/check_after_sales_static_ui.cjs'),
             args.playwright, str(output / 'info.json')],
            cwd=PROJECT, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            (output / 'node-failure.txt').write_text(
                (result.stdout or '') + (result.stderr or ''), 'utf-8')
            failure = 'Node UI 运行失败；详情见输出目录 node-failure.txt'
        else:
            tasks = h.store.list('task')
            assert len(tasks) == 1, '临时 Store 中应只有一个任务'
            task = tasks[0]
            assert task['name'] == TASK_NAME

            if args.platform:
                imports = [r for r in task['runs'] if r.get('kind') == 'import'
                           and r.get('status') == 'success']
                assert len(imports) == 2, '两版各应有一次成功导入'
                assert len(substitute_apps) == 2 and len(set(substitute_apps)) == 2
                assert {r['result']['app_id'] for r in imports} == set(substitute_apps)
                assert len(substitute_service_calls) == 14
                assert task['dify_app_id'] == substitute_apps[-1]
                for app_id in substitute_apps:
                    app = substitute_state[app_id]
                    revision = app['revision']
                    runs = [r for r in task['runs'] if r.get('kind') == 'run'
                            and r.get('revision') == revision and r.get('app_id') == app_id]
                    assert len(runs) == 6, '每版应有六个样例运行'
                    assert all(r['status'] == 'success'
                               and r['evaluation']['status'] == 'passed' for r in runs)
                    assert all(r['environment_id'] == environment_id for r in runs)
                    assert len(app['served']) == 7
                    assert sum(1 for a, _ in substitute_service_calls if a == app_id) == 7
                    assert len({row['conversation_id'] for row in app['served'].values()}) == 6
                    diagnostics = [d for run in runs for d in run.get('diagnostics', [])]
                    assert len(diagnostics) == 7
                    for run in runs:
                        turns = case_turns(run['test_case'])
                        actual = ([t['result']['answer'] for t in run['result']['turns']]
                                  if run['test_case'].get('followups')
                                  else [run['result']['answer']])
                        assert actual == [answer_for(turn['query'], app['no_hit'])
                                          for turn in turns], '实际回复必须逐字符合该版替身'
                    for diagnostic in diagnostics:
                        assert diagnostic['source_revision'] == revision
                        assert diagnostic['app_id'] == app_id
                        assert diagnostic['current_source'] is True
                        assert diagnostic['trace_state'] == 'read'
                        assert diagnostic['source_graph']['matched'] is True
                    assert {mid for a, mid in substitute_reads['messages'] if a == app_id} == {
                        row['message_id'] for row in app['served'].values()}
                    assert {rid for a, rid in substitute_reads['runs'] if a == app_id} == {
                        row['run_id'] for row in app['served'].values()}
                    assert {rid for a, rid in substitute_reads['nodes'] if a == app_id} == {
                        row['run_id'] for row in app['served'].values()}
                    first_read = substitute_events.index(('read', app_id))
                    assert all(kind != 'service' for kind, a in substitute_events[first_read:]
                               if a == app_id), '诊断不得再次派发Service'
                assert len({row['conversation_id'] for app_id in substitute_apps
                            for row in substitute_state[app_id]['served'].values()}) == 12


            def read_bundle(bundle_path):
                with zipfile.ZipFile(bundle_path) as archive:
                    members = {name: archive.read(name) for name in archive.namelist()}
                manifest = json.loads(members.pop('manifest.json'))
                assert set(members) == set(manifest['files'])
                for name, meta in manifest['files'].items():
                    assert meta['bytes'] == len(members[name]), name
                    assert meta['sha256'] == hashlib.sha256(members[name]).hexdigest(), name
                return manifest, members

            original_manifest, original_files = read_bundle(output / 'original.zip')
            modified_manifest, modified_files = read_bundle(output / 'modified.zip')
            original_revision = original_manifest['revision']
            modified_revision = modified_manifest['revision']
            assert modified_revision > original_revision
            assert original_manifest['task_id'] == task['id'] == modified_manifest['task_id']
            for manifest in (original_manifest, modified_manifest):
                assert manifest['app_type'] == 'advanced-chat'
                assert manifest['artifact_verification'] == 'static_only'
                assert manifest['platform_checked'] is False
                assert manifest['business_verified'] is False
                assert manifest['network_requested'] is False
                assert manifest['task_changed'] is False

            def dsl_file(files, manifest, mode='advanced-chat'):
                return files[f'dify-{mode}-r{manifest["revision"]}.yaml']

            original_dsl = dsl_file(original_files, original_manifest)
            modified_dsl = dsl_file(modified_files, modified_manifest)

            def graph_nodes(raw):
                document = yaml.safe_load(raw)
                assert document['app']['mode'] == 'advanced-chat'
                return {node['id']: node['data'] for node in document['workflow']['graph']['nodes']}

            def prompts(nodes):
                return '\n'.join(part.get('text', '') for part in nodes['grounded_answer']['prompt_template'])

            original_nodes = graph_nodes(original_dsl)
            modified_nodes = graph_nodes(modified_dsl)
            assert original_nodes['no_hit']['template'] == OLD_REPLY
            assert modified_nodes['no_hit']['template'] == NEW_NO_HIT_REPLY
            assert OLD_REPLY in prompts(original_nodes) and NEW_NO_HIT_REPLY not in prompts(original_nodes)
            assert NEW_NO_HIT_REPLY in prompts(modified_nodes) and OLD_REPLY not in prompts(modified_nodes)

            original_exceptions = task['requirements']['exceptions'].replace(NEW_NO_HIT_REPLY, OLD_REPLY)
            original_report = original_files[f'report-r{original_revision}.md'].decode()
            modified_report = modified_files[f'report-r{modified_revision}.md'].decode()
            for report, revision, exceptions in (
                    (original_report, original_revision, original_exceptions),
                    (modified_report, modified_revision, task['requirements']['exceptions'])):
                assert f'类型：advanced-chat；版本：r{revision}' in report
                assert f'- exceptions：{exceptions}' in report
                assert f"- tests：{REQUIREMENTS['tests']}" in report

            if args.platform:
                original_expected = [[answer_for(turn['query'], OLD_REPLY)
                                      for turn in case_turns(case)] for case in seeded_cases()]
                modified_expected = [[answer_for(turn['query'], NEW_NO_HIT_REPLY)
                                      for turn in case_turns(case)] for case in seeded_cases()]
                for report, expected, traces in ((original_report, original_expected, 7),
                                                 (modified_report, modified_expected, 14)):
                    assert report.count('"trace_state": "read"') == traces
                    summary = json.loads(report.split('## 当前修订的样例汇总', 1)[1]
                                         .split('```json\n', 1)[1].split('\n```', 1)[0])
                    assert summary['required']['passed'] == 6
                    assert summary['required']['total'] == 6
                    assert summary['all_required_passed'] is True
                    replies = json.loads(report.split('## 当前 Chatflow 样例实际回复', 1)[1]
                                         .split('```json\n', 1)[1].split('\n```', 1)[0])
                    assert len(replies) == 6 and len(replies[-1]['turns']) == 2
                    assert [[turn['answer'] for turn in item['turns']]
                            for item in replies] == expected
                assert '成功运行返回 6 次，已声明必选样例 6 / 6 通过' in modified_report

            versions = task['versions']
            original_version = next(
                version for version in versions
                if version['revision'] == original_revision
                and (version.get('artifact') or {}).get('revision') == original_revision)
            assert original_version['requirements']['exceptions'] == original_exceptions
            assert original_version['test_cases'] == seeded_cases()
            assert original_version['artifact']['sha256'] == hashlib.sha256(original_dsl).hexdigest()
            assert original_version['workflow_plan']['nodes']
            plan_texts = {json.dumps(version['workflow_plan'], sort_keys=True, ensure_ascii=False)
                          for version in versions if version.get('workflow_plan')}
            plan_texts.add(json.dumps(task['workflow_plan'], sort_keys=True, ensure_ascii=False))
            assert len(plan_texts) >= 2

            expected_cases = seeded_cases()
            next(row for row in expected_cases if row['id'] == 'no-hit')['expectation']['expected'] = NEW_NO_HIT_REPLY
            assert task['test_cases'] == expected_cases
            assert task['artifact']['revision'] == modified_revision
            assert task['artifact']['sha256'] == hashlib.sha256(modified_dsl).hexdigest()

            folder_path = Path(folder) / task['id']
            original_on_disk = (folder_path / f'artifact-r{original_revision}.yaml').read_bytes()
            modified_on_disk = (folder_path / f'artifact-r{modified_revision}.yaml').read_bytes()
            assert original_on_disk == original_dsl
            assert modified_on_disk == modified_dsl
            assert hashlib.sha256(original_on_disk).hexdigest() == original_version['artifact']['sha256']
            assert original_on_disk != modified_on_disk

            assert [call['stage'] for call in calls] == [
                'opening', 'requirements', 'original', 'revision', 'revision']
            assert sum(call['kind'] == 'interview' for call in calls) == 3
            assert sum(call['kind'] == 'plan' for call in calls) == 2

            def plan_summary(plan):
                nodes = {node['id']: node for node in plan['nodes']}
                return {
                    'plan_sha256': hashlib.sha256(
                        json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                    'node_ids': sorted(nodes),
                    'no_hit_template': nodes['no_hit']['config']['template'],
                    'grounded_answer_has_new_reply': NEW_NO_HIT_REPLY in
                        nodes['grounded_answer']['config']['system_prompt'],
                }

            def task_summary(value):
                return {
                    'revision': value['revision'],
                    'plan': plan_summary(value['workflow_plan']),
                    'test_cases': [{'id': row['id'], 'expected': row['expectation'].get('expected')}
                                   for row in value['test_cases']],
                    'exceptions': value['requirements']['exceptions'],
                    'artifact': {key: value['artifact'].get(key)
                                 for key in ('revision', 'filename', 'sha256', 'verification')},
                }

            (output / 'snapshot-original.json').write_text(
                json.dumps(task_summary(original_version), ensure_ascii=False, indent=2), 'utf-8')
            (output / 'snapshot-modified.json').write_text(
                json.dumps(task_summary(task), ensure_ascii=False, indent=2), 'utf-8')

            proof = json.loads((output / 'proof.json').read_text('utf-8'))
            ui_flow = 'two_revisions_with_substitute_platform' if args.platform else 'static_two_revisions'
            proof.update(
                state='passed',
                ui_flow=ui_flow,
                task_created_from_ui=True,
                resource_and_cases_seeded_via_local_api=True,
                public_temporary_store_only=True,
                production_accessed=False,
                physical_model_dify_http=0,
                simulated_model_calls=len(calls),
                model_call_sequence=calls,
                models_are_substitutes=True,
                model_capability_not_verified=True,
                original_artifact_kept=True,
                zip_revisions=[original_revision, modified_revision],
                platform_mode=args.platform,
                platform_checked=False,
                business_verified=False,
            )
            if args.platform:
                proof.update(
                    substitute_apps=len(substitute_apps),
                    substitute_service_calls=len(substitute_service_calls),
                    substitute_diagnostics=sum(len(run.get('diagnostics', []))
                                               for run in task['runs']),
                    per_revision_ran_cases=6,
                    key_binding_via_ui=True,
                    resources_are_public_substitutes=True,
                )
            (output / 'proof.json').write_text(
                json.dumps(proof, ensure_ascii=False, indent=2), 'utf-8')
            print(json.dumps({'state': 'passed', 'ui_flow': ui_flow,
                              'simulated_model_calls': len(calls),
                              'physical_model_dify_http': 0,
                              'substitute_service_calls': len(substitute_service_calls)}))
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), '本地服务线程未停止'
    if failure:
        raise SystemExit(failure)
