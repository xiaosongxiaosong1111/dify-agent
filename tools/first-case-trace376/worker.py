"""Fresh authentication and read-only failure evidence; no new Service or resources."""
import asyncio
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4
from support import PROJECT,capture,require
from probe import Boundary,metadata,protected


def run(mode,output,plan=None):
    root=Path(__file__).resolve().parent;live=mode=='live';output=Path(output);output.mkdir(parents=True,exist_ok=False)
    if live:
        from execute import authorized
        authorized(root,plan)
    with tempfile.TemporaryDirectory(dir=output,prefix='public-module-') as folder:
        os.environ['FLOWCRAFT_DATA_DIR']=folder;sys.path.insert(0,plan['backend_path'] if live else str(PROJECT/'backend'))
        from app import main as h
        from app.storage import Store
        from app.dify import DifyClient
        from app.run_diagnostics import binding,source_hash
        from fastapi.testclient import TestClient
        import httpx
        if live:
            target=json.loads((root/'target.json').read_text('utf-8'));base=Store(PROJECT/'data');task=base.get('task',target['task_id']);env=base.get('environment',target['environment_id'])
        else:
            h.DATA_ROOT=Path(folder);h.store=Store(Path(folder));base=h.store
            sys.path.insert(0,str(PROJECT/'backend/tests'))
            from test_after_sales_continuation import memory_built
            with TestClient(h.app) as api:
                task=memory_built(api)
                env=api.post('/api/environments',json={'name':'公开诊断连接','base_url':'https://public-dify.invalid','version':'1.17.1','console_token':'PUBLIC_OLD_TOKEN','csrf_token':'PUBLIC_OLD_CSRF','service_api_key':'app-PUBLIC_ORIGINAL_KEY','service_app_id':str(uuid4())}).json();env=base.get('environment',env['id'])
                workspace=str(uuid4());env.update(console_workspace_id=workspace,console_login_binding={'base_url':env['base_url'],'version':'1.17.1','workspace_id':workspace})
                base.put_with_secrets('environment',env['id'],env,{'console_login_email':'public@example.invalid','console_login_password':'PUBLIC_SYNTHETIC_ONLY'})
                app,mid,cid,rid=[str(uuid4()) for _ in range(4)]
                task.update(environment_id=env['id'],dify_app_id=app,status='run_completed')
                task['runs']=[{'id':rid,'kind':'run','status':'success','revision':task['revision'],'app_type':'advanced-chat','app_id':app,'environment_id':env['id'],'environment_binding':binding(env),'input':{'query':'公开政策问题'},'test_case':{'id':'faq-hit','input':{'query':'公开政策问题'},'expectation':{'mode':'contains','target':'answer','expected':['公开政策']}},'evaluation':{'status':'failed'},'result':{'id':mid,'message_id':mid,'conversation_id':cid,'mode':'advanced-chat','answer':'暂无资料'}}];h.save_task(task)
                for i in range(18):require(api.post('/api/tasks',json={'name':'公开保护任务'+str(i),'app_type':'workflow'}).status_code==201,'Public fixture failed')
            target={'task_id':task['id'],'revision':task['revision'],'run_id':rid,'app_id':app,'message_id':mid,'conversation_id':cid,'environment_id':env['id'],'workspace_id':workspace,'dataset_id':'existing-faq'}
        record={'state':'reading','business_case_retested':False,'physical_http':0,'automatic_retry':False};old=capture(base);b=Boundary(target,env,record)
        def save():
            p=output/'progress-writing.tmp';p.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(p,output/'progress.json')
        b.save=save;save();G,normal=protected(Store,copy.deepcopy(task),copy.deepcopy(env),b,old);h.DATA_ROOT=base.root;h.store=G(base.root)
        def source_current():
            current=h.get_task(target['task_id']);mutable={'console_checked_at','console_auth_mode','console_login_blocked','console_failure_id','capabilities'}
            current_env=h.store.get('environment',env['id'])
            same_env={k:v for k,v in current_env.items() if k not in mutable}=={k:v for k,v in env.items() if k not in mutable}
            same_env=same_env and {k:v for k,v in current_env.get('capabilities',{}).items() if k!='console'}=={k:v for k,v in env.get('capabilities',{}).items() if k!='console'}
            if normal(current)!=normal(task) or current['state_sequence']-task['state_sequence']!=h.store.task_saves or not same_env:
                record['source_changed_externally']=True;raise RuntimeError('Source changed;no more requests')
        b.source_current=source_current
        def forbidden(*a,**kw):raise RuntimeError('Models/synchronous HTTP forbidden')
        h.call_model=forbidden;httpx.HTTPTransport.handle_request=forbidden;original=httpx.AsyncHTTPTransport.handle_async_request
        if not live:
            from synthetic import Synthetic
            synthetic=Synthetic(h,b,mode)
        async def intercepted(own,request):
            async def forward(req):record['physical_http']+=1;save();return await original(own,req)
            return await b.dispatch(forward if live else synthetic,request)
        httpx.AsyncHTTPTransport.handle_async_request=intercepted
        try:
            with TestClient(h.app) as api:
                prefix='/api/environments/'+env['id']+'/saved-login/'
                response=api.post(prefix+'reconnect-plan',json={});require(response.status_code==200,'Reconnect plan refused');proposal=response.json()
                response=api.post(prefix+'reconnect',json={'plan_id':proposal['id'],'review_token':proposal['review_token'],'confirm_reconnect':True});require(response.status_code==200 and response.json()['record']['state']=='succeeded','Reconnect refused')
                b.phase='diagnose';response=api.post('/api/tasks/'+target['task_id']+'/runs/'+target['run_id']+'/diagnose',json={'revision':target['revision'],'read_remote':True});require(response.status_code==200,'Diagnostic refused')
                report=response.json();record['diagnostic']=report;save()
                require(report.get('source_hash')==source_hash(next(r for r in task['runs'] if r['id']==target['run_id'])) and report['trace_state']=='read' and report['source_graph']['matched'] and not report['truncated'],'Diagnostic source incomplete or different')
                b.phase='metadata'
                async def read_metadata():
                    adapter=DifyClient(h.store.get('environment',env['id']),h.store);path='/console/api/datasets/'+target['dataset_id']
                    detail=await adapter.request('GET',path,credential='console_token');record['dataset']=metadata(detail,['indexing_technique','document_count','available_document_count','permission']);save()
                    rows=await adapter.request('GET',path+'/documents',credential='console_token',params={'page':1,'limit':2});record['document_page']={'page':1,'limit':2,'returned':len(b.documents),'has_more':rows.get('has_more') if type(rows.get('has_more')) is bool else None,'total':rows.get('total') if type(rows.get('total')) is int and 0<=rows['total']<=10**12 else None};record['documents']=[]
                    for row in rows['data']:
                        status=await adapter.document_status(target['dataset_id'],row['id']);record['documents'].append({'id':row['id'],'saved_metadata':metadata(row,['indexing_status','enabled','archived','word_count','segment_count']),'indexing':metadata(status,['indexing_status','completed_segments','total_segments'])});save()
                asyncio.run(read_metadata());record.update(state='diagnostic_complete_no_retest',task_id=target['task_id'],run_id=target['run_id'],original_rule_failed_kept=True)
        except BaseException as exc:
            b.halted=True;record.update(state='stopped',failure_type=type(exc).__name__)
            if not live:record['public_failure']=str(exc)
        finally:
            now=capture(h.store);allowed={'environment:'+env['id'],'task:'+target['task_id']}
            require(all(now['objects'].get(k)==v for k,v in old['objects'].items() if k not in allowed),'Other object changed')
            require(all(now['secrets'].get(k)==v for k,v in old['secrets'].items() if k not in {env['id']+':console_token',env['id']+':csrf_token'}),'Original key/password changed')
            require(now['files']==old['files'],'Assets/masterkey changed');saved=h.get_task(target['task_id'])
            drift=bool(record.get('source_changed_externally')) or normal(saved)!=normal(task) or saved['state_sequence']-task['state_sequence']!=h.store.task_saves
            if drift:record.update(state='stopped',source_changed_externally=True)
            record.update(original_state_kept=not drift,saved_diagnostic_count=h.store.task_saves,new_tasks=0,new_models=0,new_resources=0,service_requests=0);save();httpx.AsyncHTTPTransport.handle_async_request=original
        if live:
            require(record['state']=='diagnostic_complete_no_retest','Read batch stopped;no retry')
            (root/'post-read-data-snapshot.json').write_text(json.dumps(capture(h.store)),'utf-8')
        else:require(record['physical_http']==0,'Public fixture used real HTTP')
        return record

if __name__=='__main__':
    require(len(sys.argv)==3 and sys.argv[1]!='live','Only independent public rehearsal');r=run(sys.argv[1],Path(sys.argv[2]));print(json.dumps({'state':r['state'],'counts':r['dispatch_counts'],'physical_http':r['physical_http'],'failure':r.get('public_failure')}))
