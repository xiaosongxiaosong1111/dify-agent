"""One disposable product-API process; live mode requires canonical frozen approval."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from common import PROJECT,capture,known_apps,require


def run(mode,output,plan=None):
    root=Path(__file__).resolve().parent;output=Path(output);output.mkdir(parents=True,exist_ok=False)
    fixture=json.loads((root/'fixture.json').read_text('utf-8'));live=mode=='live'
    if live:
        from execute import authorized
        authorized(root,plan)
    # Never instantiate a production Store during import or local rehearsal.
    with tempfile.TemporaryDirectory(dir=output,prefix='public-module-') as folder:
        os.environ['FLOWCRAFT_DATA_DIR']=folder
        sys.path.insert(0,plan['backend_path'] if live else str(PROJECT/'backend'))
        from app import main as h
        from app.storage import Store
        from fastapi.testclient import TestClient
        import httpx
        from contract import build
        from boundary import Boundary
        from storage_guard import guarded,verify
        from journey import run as journey
        if live:
            source=Store(PROJECT/'data');env=source.get('environment',fixture['environment_id'])
            contract=json.loads((root/'contract.json').read_text('utf-8'))
        else:
            h.DATA_ROOT=Path(folder);h.store=Store(Path(folder));source=h.store
            with TestClient(h.app) as api:
                env=api.post('/api/environments',json={'name':'公开合成连接','base_url':'https://public-dify.invalid','version':'1.17.1','console_token':'PUBLIC_OLD_CONSOLE','csrf_token':'PUBLIC_OLD_CSRF','service_api_key':'app-PUBLIC_OLD_RUNTIME_KEY','service_app_id':'11111111-1111-4111-8111-111111111111'}).json()
                env=source.get('environment',env['id']);env.update(console_workspace_id=fixture['workspace_id'],console_login_binding={'base_url':env['base_url'],'version':'1.17.1','workspace_id':fixture['workspace_id']})
                source.put_with_secrets('environment',env['id'],env,{'console_login_email':'public@example.invalid','console_login_password':'PUBLIC_SYNTHETIC_ONLY'})
                for i in range(19):require(api.post('/api/tasks',json={'name':'公开保护任务'+str(i),'app_type':'workflow'}).status_code==201,'Public seed failed')
                api.get('/api/settings')
            contract=build(h,fixture)
        old=capture(source);record={'state':'running','automatic_retry':False,'physical_http':0,'business_acceptance_complete':False}
        boundary=Boundary(env,fixture,contract,record,known_apps(source))
        def save():
            path=output/'progress-writing.tmp';path.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(path,output/'progress.json')
        boundary.save=save;save()
        Protected=guarded(Store,env,fixture,contract,boundary,old);h.DATA_ROOT=source.root;h.store=Protected(source.root)
        def forbidden(*a,**kw):raise RuntimeError('Sierra models/synchronous HTTP forbidden')
        h.call_model=forbidden;httpx.HTTPTransport.handle_request=forbidden
        original=httpx.AsyncHTTPTransport.handle_async_request
        from synthetic import Synthetic
        synthetic=Synthetic(boundary,mode)
        async def intercepted(own,request):
            async def physical(req):
                record['physical_http']+=1;save();return await original(own,req)
            return await boundary.dispatch(physical if live else synthetic,request)
        httpx.AsyncHTTPTransport.handle_async_request=intercepted
        try:
            with TestClient(h.app) as api:journey(api,h,boundary,fixture,contract,output,mode)
        except BaseException as exc:
            boundary.halted=True;record.update(state='stopped',failure_type=type(exc).__name__)
            if not live:record['local_public_failure']=str(exc)
        finally:
            record['protection']=verify(h.store,env,boundary,old);save()
            httpx.AsyncHTTPTransport.handle_async_request=original
        if live:require(record['state']=='passed','One-shot stopped; no retry or stage replay')
        else:require(record['physical_http']==0,'Physical HTTP used during public rehearsal')
        return record

if __name__=='__main__':
    require(len(sys.argv)==3 and sys.argv[1]!='live','Only public rehearsal is directly callable')
    result=run(sys.argv[1],Path(sys.argv[2]));print(json.dumps({'state':result['state'],'counts':result['dispatch_counts'],'physical_http':result['physical_http'],'failure':result.get('local_public_failure')}))
