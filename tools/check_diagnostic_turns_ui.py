"""Normal built UI with public saved conversations, never production data or HTTP."""
import argparse
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

PROJECT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--playwright',required=True)
args=p.parse_args();output=Path(args.output).resolve();assert output.is_relative_to(PROJECT/'work');output.mkdir(parents=True,exist_ok=False)
with tempfile.TemporaryDirectory(dir=output,prefix='public-store-') as folder:
    os.environ['FLOWCRAFT_DATA_DIR']=folder
    sys.path[:0]=[str(PROJECT/'backend'),str(PROJECT/'backend/tests')]
    import httpx
    import uvicorn
    from app import main as h
    from app.storage import Store
    from app.dify import DifyClient
    from fastapi.testclient import TestClient
    from pytest import MonkeyPatch
    from test_diagnostic_turn_selection import conversation,transport
    h.DATA_ROOT=Path(folder);h.store=Store(Path(folder))
    def forbidden(*a,**kw):raise AssertionError('No physical model/Dify HTTP allowed')
    httpx.HTTPTransport.handle_request=forbidden;httpx.AsyncHTTPTransport.handle_async_request=forbidden;h.call_model=forbidden
    modes=['normal','whole_failed','pending','duplicate','late_source'];tasks={};before={};readers={};patch=MonkeyPatch()
    with TestClient(h.app) as client:
        for mode in modes:
            task,run=conversation(client);task['name']='逐轮诊断公开案例-'+mode
            if mode=='whole_failed':run.update(status='failed',error='later Dify HTTP 401',http_status=401,evaluation={'status':'failed'})
            if mode=='pending':run['result'].update(pending_turn=run['result']['turns'].pop(),complete=False);run.update(status='unknown',error='后续中断')
            if mode=='duplicate':run['result']['turns'].append(copy.deepcopy(run['result']['turns'][0]))
            h.save_task(task);tasks[mode]=task;before[mode]=copy.deepcopy(task)
            def change(path,task_id=task['id']):
                if '/messages/' in path:
                    current=h.get_task(task_id);current['runs'][0]['result']['turns'][0]['result']['answer']='changed-after-read';h.save_task(current)
            calls=transport(patch,task,change if mode=='late_source' else None)
            readers[task['environment_id']]={'request':DifyClient.request,'calls':calls,'mode':mode}
    async def send(own,method,path,**kwargs):return await readers[own.env['id']]['request'](own,method,path,**kwargs)
    DifyClient.request=send
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    info={'base':f'http://127.0.0.1:{port}','output':str(output),'tasks':[{'mode':mode,'name':t['name'],'id':t['id']} for mode,t in tasks.items()]}
    (output/'info.json').write_text(json.dumps(info,ensure_ascii=False),'utf-8')
    server=uvicorn.Server(uvicorn.Config(h.app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            assert thread.is_alive();time.sleep(.1)
        assert server.started
        result=subprocess.run(['node',str(PROJECT/'tools/check_diagnostic_turns_ui.cjs'),args.playwright,str(output/'info.json')],cwd=PROJECT,timeout=180)
        assert result.returncode==0
        for mode,t in tasks.items():
            saved=h.get_task(t['id']);original=copy.deepcopy(before[mode])
            if mode=='late_source':original['runs'][0]['result']['turns'][0]['result']['answer']='changed-after-read'
            changed=[k for k in set(saved)|set(original) if k not in {'runs','updated_at','state_sequence'} and saved.get(k)!=original.get(k)]; assert not changed,(mode,changed)
            expected_saves={'normal':4,'whole_failed':2,'pending':1,'duplicate':0,'late_source':1}[mode]
            assert saved['state_sequence']-before[mode]['state_sequence']==expected_saves
            assert {k:v for k,v in saved['runs'][0].items() if k!='diagnostics'}==original['runs'][0]
            assert len(readers[t['environment_id']]['calls'])=={'normal':8,'whole_failed':4,'pending':4,'duplicate':0,'late_source':4}[mode]
        proof=json.loads((output/'proof.json').read_text('utf-8'));proof.update(public_temporary_store_only=True,production_accessed=False,physical_model_dify_http=0,original_saved_runs_kept=True)
        (output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8');print(json.dumps({'state':'passed','ui_cases':len(modes),'physical_http':0}))
    finally:
        server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()
