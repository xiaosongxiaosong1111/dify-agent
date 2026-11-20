"""Drive the real built App to explicitly retire an obsolete conflict, then separately confirm scope.

A single normal Workflow task, its eight public requirements, manual intake acknowledgement,
requirements confirmation, one public policy material, the sourced C1 conflict and the normal
material deletion are seeded through the local TestClient API. The browser must only use the
real dismiss and confirm UI. Physical HTTP, model calls and Dify calls are forbidden; the Store
is a TemporaryDirectory under the fresh output directory.
"""
import argparse
import copy
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

TASK_NAME = '失效冲突撤销界面验收-345'
REQUIREMENTS = {
    'goal': 'Public refund policy answer', 'audience': 'Customers', 'input': 'One order question',
    'output': 'A refund policy answer', 'rules': 'Refunds within 7 days.',
    'knowledge': 'No additional source needed', 'exceptions': 'Unclear cases ask for order details',
    'tests': 'A refund question returns the seven-day rule',
}
POLICY_NAME = 'policy.md'
POLICY_TEXT = 'Refunds within 30 days.'
DISMISS_REASON = 'The policy.md material that contributed the thirty-day window was removed; only the seven-day requirement source remains current.'
CONFLICT = {
    'id': 'C1',
    'title': 'Refund window differs',
    'sources': [
        {'kind': 'requirement', 'id': 'rules', 'quote': REQUIREMENTS['rules']},
    ],
    'question': 'Should refunds be accepted within seven or thirty days?',
    'options': [
        {'id': 'A', 'label': 'Keep seven days',
         'requirements_patch': {'rules': 'Refunds within 7 days.'},
         'experience': 'The seven-day window remains.', 'cost': 'No change.',
         'manual_work': 'None.'},
        {'id': 'B', 'label': 'Use thirty days',
         'requirements_patch': {'rules': 'Refunds within 30 days.'},
         'experience': 'The refund window is extended.', 'cost': 'May increase refund cost.',
         'manual_work': 'Update the policy text.'},
    ],
    'recommended_option_id': 'B',
    'recommendation_reason': 'The source material suggests thirty days, but the user must decide; the recommendation is not applied automatically.',
}
REVIEW = {'schema_version': 1, 'conflicts': [CONFLICT],
          'notes': 'Only compares the public requirement rule with the uploaded public policy material; it does not prove the business fact.'}

with tempfile.TemporaryDirectory(prefix='flowcraft-data-', dir=output) as folder:
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
        return {row['id']: REQUIREMENTS.get(row['id'], 'Explicitly not applicable: public text only')
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
        assert task['requirements_confirmed'] is True, '正常需求确认未保存'

        (output / 'public-policy.md').write_text(POLICY_TEXT, encoding='utf-8')
        uploaded = client.post(path + '/materials',
                               files={'file': (POLICY_NAME, POLICY_TEXT.encode('utf-8'), 'text/markdown')})
        assert uploaded.status_code == 200, uploaded.text
        task = uploaded.json()
        material = task['materials'][-1]
        assert material['status'] == 'parsed' and material['text'] == POLICY_TEXT
        task = request(client, 'PATCH', f"{path}/materials/{material['id']}",
                       {'revision': task['revision'], 'reference_mode': 'borrow'})

        review = copy.deepcopy(REVIEW)
        review['conflicts'][0]['sources'].append(
            {'kind': 'material', 'id': material['id'], 'quote': POLICY_TEXT})
        saved = request(client, 'POST', path + '/conflicts',
                        {'revision': task['revision'], 'review': review})
        assert saved['requirements'] == REQUIREMENTS, '保存冲突不得改写需求'
        assert saved['conflict_review']['review'] == review
        assert not saved.get('conflict_decisions')

        deleted = client.delete(f"{path}/materials/{material['id']}",
                                params={'revision': saved['revision']})
        assert deleted.status_code == 200, deleted.text
        task = deleted.json()
        assert all(item['id'] != material['id'] for item in task['materials']), '正常删除后材料应不存在'
        assert task['requirements'] == REQUIREMENTS
        assert task['requirements_confirmed'] is False and task['configuration_confirmed'] is False
        source_revision = task['revision']

        state = request(client, 'GET', path + '/conflicts')
        assert state['stale'] is True, '移除来源后旧冲突检查应标记过期'
        assert state['confirmed'] is False
        assert [row['id'] for row in state['record']['review']['conflicts']] == ['C1'], '旧冲突行应保留'
        assert state['dismissal_candidates'] == [{'conflict_id': 'C1',
                                                  'missing_material_ids': [material['id']]}], state['dismissal_candidates']

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    info = {
        'base': f'http://127.0.0.1:{port}',
        'output': str(output),
        'task_id': task_id,
        'taskId': task_id,
        'task_name': TASK_NAME,
        'original_rules': REQUIREMENTS['rules'],
        'requirements_after_delete': REQUIREMENTS,
        'materials_after_delete': task['materials'],
        'source_revision': source_revision,
        'reason': DISMISS_REASON,
        'conflict_id': 'C1',
        'conflict': review['conflicts'][0],
        'missing_material_id': material['id'],
        'missing_material_ids': [material['id']],
        'material_name': POLICY_NAME,
        'public_policy': str(output / 'public-policy.md'),
        'seed_note': 'The Workflow task, eight public requirements, manual intake acknowledgement, requirements confirmation, policy material, sourced C1 conflict and normal material deletion were seeded through the local TestClient API; the task was not created from the UI.',
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
            ['node', str(PROJECT / 'tools/check_conflict_dismissal_ui.cjs'),
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

    ui_proof = json.loads((output / 'ui-proof.json').read_text('utf-8'))
    dismiss_revision = ui_proof['dismiss_revision']
    h.store = Store(Path(folder))
    with TestClient(h.app) as client:
        persisted = request(client, 'GET', path)
        assert persisted['name'] == TASK_NAME
        assert persisted['requirements'] == REQUIREMENTS, '撤销失效冲突不得自动改写需求'
        assert persisted['materials'] == [], '撤销失效冲突不得恢复或改动材料'
        assert persisted['requirements_confirmed'] is False and persisted['configuration_confirmed'] is False
        assert persisted.get('artifact') is None and persisted.get('dify_app_id') is None
        assert not persisted.get('runs'), '撤销与确认不得产生运行记录'
        dismissals = persisted.get('conflict_dismissals') or []
        assert len(dismissals) == 1, '应有且仅有一条不可变撤销记录'
        event = dismissals[0]
        assert event['conflict'] == review['conflicts'][0], '撤销记录须保留完整旧冲突行'
        assert event['missing_material_ids'] == [material['id']]
        assert event['reason'] == DISMISS_REASON
        assert event['source_revision'] == source_revision
        assert event['result_revision'] == dismiss_revision == source_revision + 1
        assert event.get('created_at'), '撤销记录须有时间'
        state = request(client, 'GET', path + '/conflicts')
        assert state['confirmed'] is True, '撤销后仍须单独确认当前检查范围'
        assert state['record']['confirmation']['token'] == state['review_token']
        assert len(state['dismissals']) == 1
        assert state['dismissals'][0]['conflict'] == review['conflicts'][0]

    proof = {
        **ui_proof,
        'state': 'passed',
        'task_seeded_via_local_api_not_ui_creation': True,
        'task_name': TASK_NAME,
        'original_rules': REQUIREMENTS['rules'],
        'source_revision': source_revision,
        'dismiss_revision': dismiss_revision,
        'final_revision': persisted['revision'],
        'original_conflict': review['conflicts'][0],
        'missing_material_ids': [material['id']],
        'dismissal_event': event,
        'persisted_requirements': persisted['requirements'],
        'persisted_materials': persisted['materials'],
        'requirements_confirmed': False,
        'configuration_confirmed': False,
        'conflict_confirmed': state['confirmed'],
        'artifact': persisted.get('artifact'),
        'runs': persisted.get('runs'),
        'dify_app_id': persisted.get('dify_app_id'),
        'public_temporary_store_only': True,
        'production_accessed': False,
        'physical_model_dify_http': 0,
        'model_calls': 0,
    }
    (output / 'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'state': 'passed', 'task_id': task_id,
                      'source_revision': source_revision,
                      'dismiss_revision': dismiss_revision,
                      'conflict_confirmed': state['confirmed'],
                      'physical_model_dify_http': 0}))
