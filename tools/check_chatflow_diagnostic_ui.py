"""Run the normal diagnostic UI against public temporary Chatflow records."""
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
p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--playwright', required=True)
args = p.parse_args()
output = Path(args.output).resolve()
assert output.is_relative_to(PROJECT / 'work')
output.mkdir(parents=True, exist_ok=False)
with tempfile.TemporaryDirectory(dir=output, prefix='public-store-') as folder:
    os.environ['FLOWCRAFT_DATA_DIR'] = folder
    sys.path[:0] = [str(PROJECT / 'backend'), str(PROJECT / 'backend/tests')]
    from app import main as h
    from app.storage import Store
    from app.dify import DifyClient, DifyError
    from fastapi.testclient import TestClient
    from pytest import MonkeyPatch
    from test_chatflow_diagnostic_source import recorded, reader, MESSAGE, CONVERSATION, REMOTE, OTHER
    import httpx
    import uvicorn
    h.DATA_ROOT = Path(folder); h.store = Store(Path(folder))
    def forbidden(*a, **kw): raise AssertionError('Public diagnostic fixture cannot make real HTTP/model calls')
    httpx.HTTPTransport.handle_request = forbidden
    httpx.AsyncHTTPTransport.handle_async_request = forbidden
    h.call_model = forbidden
    modes = ['normal', 'wrong_conversation', 'lookup_failure', 'missing_identity']
    tasks = {}
    with TestClient(h.app) as client:
        for mode in modes:
            task, run = recorded(client); task['name'] = '消息诊断公开案例-' + mode
            if mode == 'missing_identity': run['result'].pop('id'); run['result'].pop('message_id')
            h.save_task(task); tasks[mode] = task
    readers = {}; patch = MonkeyPatch()
    for mode, task in tasks.items():
        msg = {'id': MESSAGE, 'conversation_id': OTHER if mode == 'wrong_conversation' else CONVERSATION, 'workflow_run_id': REMOTE}
        calls = reader(patch, task, message=msg)
        readers[task['environment_id']] = {'request': DifyClient.request, 'calls': calls, 'mode': mode}
    async def transport(own, method, path, **kwargs):
        row = readers[own.env['id']]
        if row['mode'] == 'lookup_failure':
            row['calls'].append(path); raise DifyError('Dify HTTP 404', http_status=404)
        return await row['request'](own, method, path, **kwargs)
    DifyClient.request = transport
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    info = {'base': 'http://127.0.0.1:' + str(port), 'output': str(output),
        'tasks': [{'mode': mode, 'name': task['name'], 'id': task['id']} for mode, task in tasks.items()]}
    (output / 'info.json').write_text(json.dumps(info, ensure_ascii=False), 'utf-8')
    server = uvicorn.Server(uvicorn.Config(h.app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        for _ in range(100):
            if server.started: break
            assert thread.is_alive(); time.sleep(.1)
        assert server.started
        result = subprocess.run(['node', str(PROJECT / 'tools/check_chatflow_diagnostic_ui.cjs'),
            args.playwright, str(output / 'info.json')], cwd=PROJECT, timeout=180)
        assert result.returncode == 0
        for mode, task in tasks.items():
            expected = 4 if mode == 'normal' else 0 if mode == 'missing_identity' else 1
            assert len(readers[task['environment_id']]['calls']) == expected
            saved = h.get_task(task['id'])
            assert saved['revision'] == task['revision']
            assert {k: v for k, v in saved['runs'][0].items() if k != 'diagnostics'} == task['runs'][0]
        proof = json.loads((output / 'proof.json').read_text('utf-8'))
        proof.update(public_temporary_store_only=True, production_accessed=False, physical_model_dify_http=0,
            fake_management_reads={v['mode']: len(v['calls']) for v in readers.values()})
        (output / 'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), 'utf-8')
        print(json.dumps({'state': 'passed', 'cases': len(modes), 'physical_model_dify_http': 0}))
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
