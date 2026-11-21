"""Drive the real built App to read a trusted import source from history, then verify by API.

A complete public start -> pure-Python code -> end workflow is built through the existing
test_dsl_roundtrip.prepared(client) helper and then reseeded into the invalidated historical
state: matching saved plan and nonblank requirements, no current App or reference, but a
same-environment success import receipt and its generation-proposal baseline retained. The
fake local Dify export returns a valid manual code/layout variant of that same graph. Setup is
disclosed API plus temporary-Store fixture, not a full real import, a production history read
or a pure UI test. Physical HTTP, model and Dify requests are all forbidden; the Store is a
TemporaryDirectory and the server is stopped in finally.
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

NOHISTORY_NAME = '来源历史缺失-358'
NOENV_NAME = '来源环境缺失-358'
export_state = {'content': ''}

with tempfile.TemporaryDirectory(prefix='dsl-source-history-ui-') as folder:
    os.environ['FLOWCRAFT_DATA_DIR'] = folder
    sys.path[:0] = [str(PROJECT / 'backend'), str(PROJECT / 'backend/tests')]
    import copy
    import httpx
    import uvicorn
    import yaml
    from fastapi.testclient import TestClient
    from app import main as h
    from app.storage import Store
    from app.dsl_roundtrip import digest, parse, validate_preserved
    from app.run_diagnostics import binding as environment_binding
    import test_dsl_roundtrip

    h.DATA_ROOT = Path(folder)
    h.store = Store(Path(folder))

    def forbidden(*args, **kwargs):
        raise AssertionError('No physical model or Dify HTTP is allowed')

    exports = []

    async def fake_export(self, app_id):
        exports.append(str(app_id))
        assert export_state['content'], '假导出公开 DSL 尚未准备'
        return export_state['content']

    httpx.HTTPTransport.handle_request = forbidden
    httpx.AsyncHTTPTransport.handle_async_request = forbidden
    h.DifyClient.request = forbidden
    h.DifyClient.export_dsl = fake_export
    h.call_model = forbidden

    def request(client, method, path, body=None):
        response = client.request(method, path, json=body) if body is not None else client.request(method, path)
        assert response.status_code in (200, 201), (path, response.status_code, response.text)
        return response.json()

    with TestClient(h.app) as client:
        positive, root = test_dsl_roundtrip.prepared(client)
        positive_id = positive['id']
        positive_name = positive['name']
        env_id = positive['environment_id']
        assert env_id, '公开测试任务应绑定环境'
        receipt = next(run for run in positive['runs']
                       if run.get('kind') == 'import' and run.get('status') == 'success')
        known_app = receipt['result']['app_id']
        raw_env = h.store.get('environment', env_id)
        bind = environment_binding(raw_env)

        exported = test_dsl_roundtrip.changed(root)
        exported_text = yaml.safe_dump(exported, allow_unicode=True, sort_keys=False)
        assert digest(parse(exported_text, 'workflow')) == digest(exported), '假导出公开 DSL 解析应保持一致'
        assert validate_preserved(root)['valid'], '生成基线应通过现有保留校验'
        assert validate_preserved(exported)['valid'], '假导出公开 DSL 应通过现有保留校验'
        export_state['content'] = exported_text

        seeded = h.store.get('task', positive_id)
        seeded['dify_app_id'] = None
        seeded['artifact'] = None
        seeded['dsl_reference'] = None
        seeded['requirements_confirmed'] = False
        seeded['configuration_confirmed'] = False
        seeded['status'] = 'requirements'
        seeded['plan_stale'] = False
        assert seeded.get('workflow_plan') and all(str(value).strip() for value in seeded['requirements'].values()), '失效历史任务应保留计划和非空公开需求'
        receipt = next(run for run in seeded['runs']
                       if run.get('kind') == 'import' and run.get('status') == 'success')
        receipt['app_type'] = seeded['app_type']
        receipt['environment_binding'] = bind
        receipt['baseline_kind'] = 'generation_proposal'
        receipt['dsl_baseline'] = copy.deepcopy(root)
        seeded['revision'] += 1
        h.store.put('task', positive_id, seeded)
        initial_revision = seeded['revision']
        current_content, current_validation = h.compile_current(seeded)
        assert current_validation['valid'], '失效历史任务的当前代码方案应仍可编译'
        assert digest(parse(current_content, 'workflow')) == digest(root), '当前代码计划应与保留的生成基线一致'

        nohistory = request(client, 'POST', '/api/tasks',
                            {'name': NOHISTORY_NAME, 'app_type': 'workflow', 'environment_id': env_id})
        noenv = request(client, 'POST', '/api/tasks', {'name': NOENV_NAME, 'app_type': 'workflow'})
        nohistory_id, noenv_id = nohistory['id'], noenv['id']

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    info = {
        'base': f'http://127.0.0.1:{port}',
        'output': str(output),
        'positive': {'id': positive_id, 'name': positive_name, 'initial_revision': initial_revision},
        'negative_no_history': {'id': nohistory_id, 'name': NOHISTORY_NAME},
        'negative_no_environment': {'id': noenv_id, 'name': NOENV_NAME},
        'environment_id': env_id,
        'known_app_id': known_app,
        'seed_note': 'The existing test_dsl_roundtrip.prepared helper built a complete public start -> pure-Python code -> end workflow; the same task was then reseeded to the invalidated historical state with matching saved plan, nonblank requirements and the same-environment success import receipt plus generation baseline. The fake Dify export returns a valid manual code/layout variant of that graph. Setup is disclosed API plus temporary-Store fixture, not a full real import, a production history read or a pure UI test.',
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
            ['node', str(PROJECT / 'tools/check_dsl_source_history_ui.cjs'),
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
        task = request(client, 'GET', f'/api/tasks/{positive_id}')
        reference = task.get('dsl_reference') or {}
        assert reference.get('source_app_id') == known_app, '读取后引用来源应用不符'
        assert reference.get('source') == 'dify_draft', '读取来源应为实际 Dify 草稿'
        assert task.get('dify_app_id') is None, '读取来源不应伪造当前 App ID'
        assert task['revision'] > initial_revision, '读取后修订应增加'
        assert task.get('workflow_plan'), '读取后应保留当前代码计划供预览'
        assert any(run.get('kind') == 'import' and run.get('result', {}).get('app_id') == known_app
                   for run in task['runs']), '读取后应保留同环境成功导入回执'
        record = h.store.get('dsl_reference', reference['id'])
        assert digest(record['current']) == digest(exported), '新引用当前草稿应保存假导出的手工代码／布局'
        preview = request(client, 'GET', f'/api/tasks/{positive_id}/dsl-merge')
        assert preview['validation']['valid'] is True, ('预览未通过静态检查', preview['validation'])
        assert digest(parse(preview['content'], 'workflow')) == digest(exported), '预览应保留假导出的手工代码／布局'
        assert preview.get('source_app_id') == known_app
    assert exports == [known_app], '应恰好执行一次公开假导出，未重复请求'

    api_report = {
        'state': 'passed', 'task_id': positive_id, 'task_name': positive_name,
        'initial_revision': initial_revision, 'read_revision': task['revision'],
        'reference_source': reference.get('source'),
        'reference_source_app_id': reference.get('source_app_id'),
        'current_app_id_after_read': task.get('dify_app_id'),
        'preview_valid': preview['validation']['valid'],
        'preview_preserves_exported_code_layout': True,
        'fake_export_variant': 'manual code strip().upper() and code node position.x +17',
        'fake_dify_exports': exports,
        'physical_model_dify_http': 0, 'model_calls': 0,
    }
    (output / 'api-static-report.json').write_text(
        json.dumps(api_report, ensure_ascii=False, indent=2), 'utf-8')
    ui_proof = json.loads((output / 'ui-proof.json').read_text('utf-8'))
    proof = {
        **ui_proof,
        'state': 'passed',
        'setup_disclosed_not_full_import_or_pure_ui': True,
        'seed_note': info['seed_note'],
        'initial_revision': initial_revision,
        'read_revision': task['revision'],
        'reference_source': reference.get('source'),
        'reference_source_app_id': reference.get('source_app_id'),
        'current_app_id_after_read': task.get('dify_app_id'),
        'preview_valid': preview['validation']['valid'],
        'preview_preserves_exported_code_layout': True,
        'fake_export_variant': 'manual code strip().upper() and code node position.x +17',
        'fake_dify_exports': exports,
        'public_temporary_store_only': True,
        'production_accessed': False,
        'physical_model_dify_http': 0,
        'model_calls': 0,
    }
    (output / 'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'state': 'passed', 'task_id': positive_id,
                      'read_revision': task['revision'],
                      'reference_source_app_id': reference.get('source_app_id'),
                      'physical_model_dify_http': 0}))
