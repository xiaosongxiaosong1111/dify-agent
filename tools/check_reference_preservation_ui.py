"""Drive the real built App through reference preservation, then verify plan/confirm/build by API.

The single Workflow task, its eight public requirements, manual intake acknowledgement and
explicit plan are seeded through the local TestClient only. The browser must add the YAML,
select code, then use the normal material single-edit modal to add format. Physical HTTP,
model calls and Dify calls are forbidden; the Store is a TemporaryDirectory.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--playwright', required=True, help='absolute path to the Playwright module')
args = parser.parse_args()

output = Path(args.output).resolve()
assert (PROJECT / 'work').is_dir(), '项目 work 目录缺失'
assert output.is_relative_to(PROJECT / 'work'), '输出目录必须位于项目 work 下'
assert output != (PROJECT / 'work'), '输出目录不能是 work 本身'
assert not output.is_relative_to(PROJECT / 'frontend' / 'dist'), '不得写入构建 dist'
assert not output.exists(), '输出目录必须尚不存在；不删除或复用已有输出'
playwright = Path(args.playwright)
assert playwright.is_absolute() and playwright.exists(), '必须提供存在的绝对 Playwright 模块路径'
assert (PROJECT / 'frontend/dist/index.html').is_file(), '请先构建 frontend/dist'
output.mkdir(parents=True, exist_ok=False)

TASK_NAME = '参考保留正常界面验收-344'
REQUIREMENTS = {
    'goal': 'Public text processor', 'audience': 'Colleagues', 'input': 'One query string',
    'output': 'A result string', 'rules': 'Trim query then uppercase and format as text',
    'knowledge': 'No additional source needed', 'exceptions': 'Blank input returns an error',
    'tests': 'abc produces ABC',
}
PLAN = {
    'schema_version': 1,
    'nodes': [
        {'id': 'start', 'type': 'start',
         'config': {'variables': [{'variable': 'query', 'type': 'text-input', 'required': True}]}},
        {'id': 'code', 'type': 'code',
         'config': {'code_language': 'python3',
                    'code': "def main(query):\n    return {'result': query.strip().upper()}\n",
                    'variables': [{'variable': 'query', 'value_selector': ['start', 'query']}],
                    'outputs': {'result': {'type': 'string'}}}},
        {'id': 'format', 'type': 'template-transform',
         'config': {'template': '{{ value }}',
                    'variables': [{'variable': 'value', 'value_selector': ['code', 'result']}]}},
        {'id': 'end', 'type': 'end',
         'config': {'outputs': [{'variable': 'result', 'value_selector': ['format', 'output']}]}},
    ],
    'edges': [{'source': 'start', 'target': 'code'}, {'source': 'code', 'target': 'format'},
              {'source': 'format', 'target': 'end'}],
}

with tempfile.TemporaryDirectory(prefix='reference-preservation-ui-') as folder:
    os.environ['FLOWCRAFT_DATA_DIR'] = folder
    sys.path[:0] = [str(PROJECT / 'backend'), str(PROJECT / 'backend/tests')]
    import httpx
    import uvicorn
    from fastapi.testclient import TestClient
    from app import main as h
    from app.storage import Store

    h.DATA_ROOT = Path(folder)
    h.store = Store(Path(folder))

    def forbidden(*args, **kwargs):
        raise AssertionError('No physical model or Dify HTTP is allowed')

    httpx.HTTPTransport.handle_request = forbidden
    httpx.AsyncHTTPTransport.handle_async_request = forbidden
    h.DifyClient.request = forbidden
    h.call_model = forbidden

    def request(client, method, path, body=None):
        response = client.request(method, path, json=body) if body is not None else client.request(method, path)
        assert response.status_code in (200, 201), (path, response.status_code, response.text)
        return response.json()

    def intake_answers(summary):
        return {row['id']: REQUIREMENTS.get(row['id'], 'Explicitly not applicable: text only')
                for row in summary['standard']}

    with TestClient(h.app) as client:
        task = request(client, 'POST', '/api/tasks', {'name': TASK_NAME, 'app_type': 'workflow'})
        task_id = task['id']
        path = f'/api/tasks/{task_id}'
        task = request(client, 'PATCH', path, {'requirements': REQUIREMENTS,
                                               'configuration': {'resource_plan': 'Local public static design only'}})
        intake = request(client, 'GET', path + '/intake')
        task = request(client, 'POST', path + '/intake/manual',
                       {'revision': task['revision'], 'context_token': intake['context_token'],
                        'answers': intake_answers(intake), 'acknowledge_review': True})
        task = request(client, 'POST', path + '/confirm',
                       {'revision': task['revision'], 'kind': 'requirements'})
        task = request(client, 'POST', path + '/plan',
                       {'revision': task['revision'], 'plan': PLAN})
        source, validation = h.compile_current(h.get_task(task_id))
        assert validation['valid'], validation
        assert not h.get_task(task_id)['materials'], '上传前不应已有参考材料'
        initial_revision = task['revision']
        (output / 'public-reference.yaml').write_text(source, encoding='utf-8')

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    info = {
        'base': f'http://127.0.0.1:{port}',
        'output': str(output),
        'task_id': task_id,
        'taskId': task_id,
        'task_name': TASK_NAME,
        'source_yaml': str(output / 'public-reference.yaml'),
        'initial_revision': initial_revision,
        'seed_note': 'Task, eight public requirements, manual intake acknowledgement and explicit plan were seeded through the local TestClient API; the task was not created from the UI.',
    }
    (output / 'info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), 'utf-8')

    server = uvicorn.Server(uvicorn.Config(h.app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            assert thread.is_alive(), '本地服务线程提前退出'
            time.sleep(.1)
        assert server.started, '本地服务未启动'
        result = subprocess.run(
            ['node', str(PROJECT / 'tools/check_reference_preservation_ui.cjs'),
             str(playwright), str(output / 'info.json')],
            cwd=PROJECT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
        if result.returncode != 0:
            (output / 'node-failure.txt').write_text(
                (result.stdout or '') + (result.stderr or ''), 'utf-8')
            raise AssertionError('浏览器验收失败；详情见输出目录 node-failure.txt')
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), '本地服务线程未停止'

    with TestClient(h.app) as client:
        task = request(client, 'GET', f'/api/tasks/{task_id}')
        assert task['name'] == TASK_NAME
        references = [material for material in task['materials']
                      if material.get('source_kind') == 'reference_dsl']
        assert len(references) == 1, '应只有一份参考 DSL 材料'
        material = references[0]
        assert material['reference_mode'] == 'preserve'
        assert material['preserve_node_ids'] == ['code', 'format']
        assert task['revision'] > initial_revision
        assert task['requirements_confirmed'] is False and task['configuration_confirmed'] is False

        intake = request(client, 'GET', f'/api/tasks/{task_id}/intake')
        task = request(client, 'POST', f'/api/tasks/{task_id}/intake/manual',
                       {'revision': task['revision'], 'context_token': intake['context_token'],
                        'answers': intake_answers(intake), 'acknowledge_review': True})
        task = request(client, 'POST', f'/api/tasks/{task_id}/confirm',
                       {'revision': task['revision'], 'kind': 'requirements'})
        task = request(client, 'POST', f'/api/tasks/{task_id}/plan',
                       {'revision': task['revision'], 'plan': PLAN})
        confirmed = client.post(f'/api/tasks/{task_id}/confirm',
                                json={'revision': task['revision'], 'kind': 'configuration'})
        assert confirmed.status_code == 200, confirmed.text
        task = confirmed.json()
        built = client.post(f'/api/tasks/{task_id}/build', json={'revision': task['revision']})
        assert built.status_code == 200, built.text
        task = built.json()
        report = task['artifact']['validation']['reference_preservation']
        assert report['business_verified'] is False and report['platform_verified'] is False
        entry = report['materials'][0]
        assert entry['mode'] == 'preserve'
        assert set(entry['node_ids']) == {'code', 'format'}
        assert entry['complete_node_config'] is True and entry['connections_locked'] is False

    api_report = {
        'state': 'passed', 'task_id': task_id, 'task_name': TASK_NAME,
        'material_id': material['id'], 'preserve_node_ids': material['preserve_node_ids'],
        'initial_revision': initial_revision, 'built_revision': task['revision'],
        'artifact_revision': task['artifact']['revision'],
        'verification': report['verification'],
        'business_verified': report['business_verified'],
        'platform_verified': report['platform_verified'],
        'complete_node_config': entry['complete_node_config'],
        'connections_locked': entry['connections_locked'],
        'physical_model_dify_http': 0, 'model_calls': 0,
    }
    (output / 'api-static-report.json').write_text(
        json.dumps(api_report, ensure_ascii=False, indent=2), 'utf-8')
    ui_proof = json.loads((output / 'ui-proof.json').read_text('utf-8'))
    proof = {
        **ui_proof,
        'state': 'passed',
        'task_seeded_via_local_api_not_ui_creation': True,
        'task_name': TASK_NAME,
        'initial_revision': initial_revision,
        'built_revision': task['revision'],
        'artifact_revision': task['artifact']['revision'],
        'api_reference_preservation': {
            'verification': report['verification'],
            'material_node_ids': entry['node_ids'],
            'complete_node_config': entry['complete_node_config'],
            'connections_locked': entry['connections_locked'],
            'business_verified': False,
            'platform_verified': False,
        },
        'public_temporary_store_only': True,
        'production_accessed': False,
        'physical_model_dify_http': 0,
        'model_calls': 0,
    }
    (output / 'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'state': 'passed', 'task_id': task_id,
                      'material_node_ids': material['preserve_node_ids'],
                      'built_revision': task['revision'],
                      'physical_model_dify_http': 0}))
