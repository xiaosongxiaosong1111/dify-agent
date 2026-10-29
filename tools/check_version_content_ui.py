"""Disposable public fixture + built UI checks; production data is never opened."""
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
p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--playwright', required=True)
args = p.parse_args()
output = Path(args.output).resolve()
assert output.is_relative_to(PROJECT / 'work')
output.mkdir(parents=True, exist_ok=False)

with tempfile.TemporaryDirectory(dir=output, prefix='public-store-') as folder:
    os.environ['FLOWCRAFT_DATA_DIR'] = folder
    sys.path.insert(0, str(PROJECT / 'backend'))
    from app import main as h
    from app.storage import Store
    from fastapi.testclient import TestClient
    import httpx
    import uvicorn
    h.DATA_ROOT = Path(folder)
    h.store = Store(Path(folder))
    def forbidden(*a, **kw):
        raise AssertionError('No model, credential or external HTTP in public UI fixture')
    httpx.HTTPTransport.handle_request = forbidden
    httpx.AsyncHTTPTransport.handle_async_request = forbidden
    h.call_model = forbidden
    with TestClient(h.app) as client:
        r = client.post('/api/tasks', json={'name': '历史正文页面公开案例', 'app_type': 'workflow'})
        assert r.status_code == 201
        task = r.json()
    task['requirements'] = {key: '公开合成的明确说明' for key in h.REQ_KEYS}
    task['requirements']['rules'] = '历史公开政策🙂逐字核对。' * 1200
    task['workflow_plan'] = {'schema_version': 1, 'nodes': [
        {'id': 'start', 'type': 'start', 'config': {'variables': []}},
        {'id': 'code', 'type': 'code', 'config': {'code_language': 'python3',
            'code': 'def main() -> dict:\n    return {"result": "<script>globalThis.__historyCodeRan=true</script>"}\n',
            'variables': [], 'outputs': {'result': {'type': 'string', 'children': None}}}},
        {'id': 'end', 'type': 'end', 'config': {'outputs': [{'variable': 'out', 'value_selector': ['code', 'result']}]}}],
        'edges': [{'source': 'start', 'target': 'code'}, {'source': 'code', 'target': 'end'}]}
    h.snapshot(task, '旧版公开长正文')
    old = copy.deepcopy(task['versions'][-1])
    old['configuration']['max_tokens'] = 9007199254740993  # Exact legacy saved JSON, not a runnable configuration.
    task['requirements']['rules'] = '另一历史快照正文，不能混入旧分页。'
    h.snapshot(task, '另一份公开快照')
    other = copy.deepcopy(task['versions'][-1])
    task['versions'] = [old, other]
    task['requirements']['rules'] = '当前保存内容必须保持，查看历史不恢复。'
    h.store.put('task', task['id'], task)
    before = copy.deepcopy(h.get_task(task['id']))
    ledger = copy.deepcopy(h.store.get('task_budget', task['id']))
    h.store.secret = forbidden
    h.store.put = forbidden
    info = {'task_id': task['id'], 'task_name': task['name'], 'revision': task['revision'],
        'old_version_id': old['id'], 'other_version_id': other['id'],
        'old_requirements': json.dumps(old['requirements'], ensure_ascii=False, indent=2),
        'other_requirements': json.dumps(other['requirements'], ensure_ascii=False, indent=2),
        'output': str(output)}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    info['base'] = 'http://127.0.0.1:' + str(port)
    (output / 'info.json').write_text(json.dumps(info, ensure_ascii=False), 'utf-8')
    server = uvicorn.Server(uvicorn.Config(h.app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        for _ in range(100):
            if server.started: break
            assert thread.is_alive(); time.sleep(.1)
        assert server.started
        result = subprocess.run(['node', str(PROJECT / 'tools/check_version_content_ui.cjs'),
            args.playwright, str(output / 'info.json')], cwd=PROJECT, timeout=300)
        assert result.returncode == 0
        assert h.get_task(task['id']) == before and h.store.get('task_budget', task['id']) == ledger
        proof = json.loads((output / 'proof.json').read_text('utf-8'))
        proof.update(disposable_public_store_only=True, saved_task_and_ledger_unchanged=True,
            new_model_dify_http=0, credentials_decrypted=False)
        (output / 'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), 'utf-8')
        print(json.dumps({'state': 'passed', 'cases': len(proof['cases']), 'production_accessed': False}))
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
