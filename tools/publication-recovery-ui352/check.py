"""Isolated API-backed UI, synthetic unknown/evidence, physical HTTP/model forbidden."""
import argparse,json,os,sys,socket,subprocess,tempfile,threading,time,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
p=argparse.ArgumentParser();p.add_argument('--playwright',required=True);p.add_argument('--output',required=True);args=p.parse_args()
assert Path(args.playwright).is_absolute() and Path(args.playwright).is_dir()
out=Path(args.output).resolve();assert out.is_relative_to(PROJECT/'work');out.mkdir(exist_ok=False,parents=True)
sys.path[:0]=[str(PROJECT/'backend'),str(PROJECT/'backend/tests')]
with tempfile.TemporaryDirectory(dir=out,prefix='isolated-') as folder:
 os.environ['FLOWCRAFT_DATA_DIR']=folder
 import httpx,uvicorn,pytest
 from fastapi.testclient import TestClient
 from app import main
 from test_publication_recovery import unknown
 from app import publication_recovery as recovery
 def forbidden(*a,**k):raise AssertionError('Physical HTTP/model forbidden')
 httpx.HTTPTransport.handle_request=forbidden;httpx.AsyncHTTPTransport.handle_async_request=forbidden;main.call_model=forbidden
 patch=pytest.MonkeyPatch()
 with TestClient(main.app) as api:task,env,state,old,proof=unknown(api,patch)
 saved=copy.deepcopy(main.store.get('task',task['id']))
 @main.app.get('/__test/state')
 def inspect():return {'calls':state['calls'],'old_kept':main.store.get('workflow_publication',old['id'])==old,'old_runs_kept':main.store.get('task',task['id'])['runs'][:len(saved['runs'])]==saved['runs'],'recovery_states':[r['state'] for r in main.store.list(recovery.RECOVERY)]}
 sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
 server=uvicorn.Server(uvicorn.Config(main.app,host='127.0.0.1',port=port,log_level='error'));worker=threading.Thread(target=server.run,daemon=True);worker.start()
 try:
  for _ in range(150):
   if server.started:break
   assert worker.is_alive();time.sleep(.1)
  assert server.started
  info={'base':'http://127.0.0.1:'+str(port),'task_id':task['id'],'app_id':task['dify_app_id'],'revision':task['revision'],'evidence_id':proof['id'],'output':str(out)}
  (out/'info.json').write_text(json.dumps(info),'utf-8')
  result=subprocess.run(['node',str(ROOT/'journey.cjs'),args.playwright,str(out/'info.json')],cwd=PROJECT,timeout=150);assert result.returncode==0
 finally:
  server.should_exit=True;worker.join(timeout=10);assert not worker.is_alive();patch.undo()
assert not Path(folder).exists();print('Publication recovery isolated UI passed; physical model/Dify HTTP0')
