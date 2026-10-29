"""Exercise explicit continuation drafting/saving in a disposable public Store."""
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
p = __import__('argparse').ArgumentParser()
p.add_argument('--output', required=True); p.add_argument('--playwright', required=True)
args = p.parse_args(); output = Path(args.output).resolve()
assert output.is_relative_to(PROJECT / 'work'); output.mkdir(parents=True, exist_ok=False)
with tempfile.TemporaryDirectory(dir=output, prefix='public-store-') as folder:
    os.environ['FLOWCRAFT_DATA_DIR'] = folder
    sys.path[:0] = [str(PROJECT / 'backend'), str(PROJECT / 'backend/tests')]
    from app import main as h
    from app.storage import Store
    from app.after_sales_cases import propose
    from test_after_sales_continuation import memory_built
    from test_after_sales_cases import built
    from fastapi.testclient import TestClient
    import httpx, uvicorn
    h.DATA_ROOT = Path(folder); h.store = Store(Path(folder))
    def forbidden(*a, **kw): raise AssertionError('No real model/Dify requests in public drafting fixture')
    httpx.HTTPTransport.handle_request = forbidden; httpx.AsyncHTTPTransport.handle_async_request = forbidden
    h.call_model = forbidden; h.DifyClient.request = forbidden
    modes = ['normal', 'duplicate', 'memory_off', 'forged_followup', 'malformed_row', 'bad_source']
    tasks = {}; before = {}; ledgers = {}
    with TestClient(h.app) as client:
        for mode in modes:
            task = built(client) if mode == 'memory_off' else memory_built(client)
            task['name'] = '订单接续公开案例-' + mode
            rows, _ = propose(task, '订单查询模拟', None if mode=='memory_off' else 'DEMO-001')
            missing = next(r for r in rows if r['scenario']=='missing_order')
            old = {k: v for k, v in missing.items() if k!='scenario'} | {'id':'old-missing'}
            task['test_cases'] = [old]
            if mode=='duplicate': task['test_cases'].append({k:v for k,v in rows[-1].items() if k!='scenario'} | {'id':'old-continuation'})
            h.store.put('task', task['id'], task)
            # Name is part of the native DSL; bind the public renamed fixture to its own fresh build.
            built_response=client.post('/api/tasks/'+task['id']+'/build',json={'revision':task['revision']})
            assert built_response.status_code==200,built_response.text
            task=h.get_task(task['id'])
            tasks[mode] = task; before[mode] = copy.deepcopy(h.get_task(task['id']))
            ledgers[mode] = copy.deepcopy(h.store.get('task_budget', task['id']))
    with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    info={'base':'http://127.0.0.1:'+str(port),'output':str(output),
        'tasks':[{'mode':mode,'id':t['id'],'name':t['name']} for mode,t in tasks.items()]}
    (output/'info.json').write_text(json.dumps(info,ensure_ascii=False),'utf-8')
    server=uvicorn.Server(uvicorn.Config(h.app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started: break
            assert thread.is_alive();time.sleep(.1)
        assert server.started
        result=subprocess.run(['node',str(PROJECT/'tools/check_after_sales_continuation_ui.cjs'),args.playwright,str(output/'info.json')],cwd=PROJECT,timeout=240)
        assert result.returncode==0
        for mode,task in tasks.items():
            saved=h.get_task(task['id'])
            assert h.store.get('task_budget',task['id'])==ledgers[mode]
            if mode=='normal':
                assert saved['revision']>task['revision'] and len(saved['test_cases'])==2
                assert saved['test_cases'][0]==task['test_cases'][0]
                assert saved['test_cases'][1]['followups'][0]['input']=={'query':'DEMO-001'}
                assert not saved['requirements_confirmed'] and not saved['configuration_confirmed'] and saved['artifact'] is None
                assert saved['runs']==task['runs']
            else: assert saved==before[mode]
        proof=json.loads((output/'proof.json').read_text('utf-8'));proof.update(public_temporary_store_only=True,physical_model_dify_http=0,production_accessed=False,all_ledgers_and_old_runs_kept=True)
        (output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps({'state':'passed','cases':len(modes),'physical_model_dify_http':0}))
    finally:
        server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()
