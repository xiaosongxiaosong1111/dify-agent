"""One new bounded product-API batch; physical traffic requires a frozen direct approval."""
import copy,hashlib,json,os,sys,tempfile,threading,time
from decimal import Decimal
from pathlib import Path
from common import PROJECT,LIMITS,capture,known_apps,digest,require,sha

SAFE_FRAMES=('worker.py','journey.py','boundary.py','storage_guard.py','reviews.py','candidate.py','pagination.py')

def failure_location(exc,root):
    """Only whitelisted package frames: basename, code function name and line."""
    frames=[]
    try:
        root=Path(root).resolve();trace=exc.__traceback__
        while trace is not None and len(frames)<8:
            path=Path(trace.tb_frame.f_code.co_filename).resolve()
            if path.name in SAFE_FRAMES and path.parent==root:
                frames.append({'file':path.name,'function':trace.tb_frame.f_code.co_name,'line':int(trace.tb_lineno)})
            trace=trace.tb_next
    except Exception:return frames
    return frames

def run(mode,output,plan=None):
    live=mode=='live';root=Path(__file__).resolve().parent;output=Path(output).resolve()
    require(output.is_relative_to(PROJECT/'work') and not output.exists() and not sys.flags.optimize,'New nonoptimized output required')
    if live:
        from execute import authorize_worker
        authorize_worker(root,plan)
    output.mkdir();fixture=json.loads((root/'fixture.json').read_text('utf-8'))
    record={'state':'running','mode':mode,'physical_http':0,'automatic_retry':False,'approved_model_slots':8,'effective_model_http':6,'json_repair_http':0,'responses':{},'reviews':{},'business_acceptance_complete':False,'human_signoff':False}
    lock=threading.RLock()
    def save():
        with lock:
            tmp=output/'progress-writing.tmp';tmp.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(tmp,output/'progress.json')
    save()
    with tempfile.TemporaryDirectory(dir=output,prefix='bootstrap-') as bootstrap:
        os.environ['FLOWCRAFT_DATA_DIR']=bootstrap
        sys.path.insert(0,plan['backend_path'] if live else str(PROJECT/'backend'))
        from app import main as h
        from app.storage import Store
        from app.plan_drafts import inspect_text
        from app.planning import reserve_cost,PlanningStopped
        from app.providers import ProviderError
        from fastapi.testclient import TestClient
        import httpx
        if live:
            source=Store(PROJECT/'data');env=source.get('environment',fixture['environment_id']);provider=source.get('provider',fixture['provider_id'])
            require(env and provider and digest(provider)==plan['provider_sha256'],'Frozen profile changed')
        else:
            source=h.store
            with TestClient(h.app) as api:
                env=api.post('/api/environments',json={'name':'公开替身专用环境','base_url':'https://public-dify.invalid','version':'1.17.1','console_token':'PUBLIC_OLD_CONSOLE','csrf_token':'PUBLIC_OLD_CSRF','service_api_key':'app-PUBLIC_OLD_RUNTIME_KEY','service_app_id':'11111111-1111-4111-8111-111111111111'}).json()
                env=source.get('environment',env['id']);env.update(console_workspace_id=fixture['workspace_id'],console_login_binding={'base_url':env['base_url'],'version':'1.17.1','workspace_id':fixture['workspace_id']})
                source.put_with_secrets('environment',env['id'],env,{'console_login_email':'public@example.invalid','console_login_password':'PUBLIC_SYNTHETIC_ONLY'})
                provider=api.post('/api/providers',json={'name':'公开模型替身','provider':'deepseek','protocol':'openai-compatible','base_url':'https://api.deepseek.com','model':'deepseek-flash','api_key':'PUBLIC_MODEL_KEY','role':'main','pricing':{'input_per_million_usd':.3,'output_per_million_usd':1.2}}).json()
                provider=source.get('provider',provider['id'])
                for i in range(26):require(api.post('/api/tasks',json={'name':'受保护公开任务'+str(i),'app_type':'workflow'}).status_code==201,'Seed failed')
            fixture['environment_id']=env['id'];fixture['provider_id']=provider['id'];fixture['configuration']['assistant_provider_id']=provider['id']
        before=capture(source);contract={}
        from boundary import Boundary
        from storage_guard import guarded,verify
        from candidate import register
        from reviews import Reviews
        b=Boundary(env,provider,source.secret(provider['id'],'api_key'),fixture,contract,record,known_apps(source))
        b.candidates=set();b.save=save
        Protected=guarded(Store,env,provider,fixture,contract,b,before);h.DATA_ROOT=source.root;h.store=Protected(source.root)
        h.sierra_fixture=fixture;h.sierra_review_secrets=[source.secret(provider['id'],'api_key')]+[source.secret(env['id'],k) for k in ('console_token','csrf_token','console_login_password','service_api_key')]
        h.sierra_review_secrets=[s for s in h.sierra_review_secrets if s]
        reviews=Reviews(output,h,record,live,save);b.wait_review=reviews.wait
        b.register_plan=lambda host,task,version,receipt:register(host,task,version,receipt,b,fixture,contract)
        original_model=h.call_model;original_budget=h.budgets.call;old_async=httpx.AsyncHTTPTransport.handle_async_request;old_sync=httpx.HTTPTransport.handle_request
        settings=copy.deepcopy(h.get_settings());h.get_settings=lambda:{**settings,'max_retries':0,'max_minutes':4,'max_cost_usd':.600}
        from synthetic import Synthetic
        synthetic=Synthetic(b,mode,h);h.sierra_synthetic_trace_expectations=synthetic.expectations
        def current():
            require(not (output/'stop.json').exists(),'Explicit stop')
            if b.owner:h.budgets.ready(b.owner)
            if live:
                from execute import verify_frozen,approved
                verify_frozen(root,plan);approved(root,plan)
        async def budget(item,revision,kind,selected,key,messages,**kwargs):
            current();t=h.get_task(b.owner)
            require(item==b.owner and revision==t['revision'] and selected==provider and key==source.secret(provider['id'],'api_key'),'Wrong current model scope')
            require(kind==('interview' if b.phase.endswith('interview') else 'plan') and kwargs.get('max_tokens')==6000 and 0<kwargs.get('timeout',0)<=120 and not kwargs.get('stream'),'Wrong model operation')
            if b.phase in {'first_interview','complete_interview','original_plan'}:
                require(fixture['changed_no_hit_reply'] not in json.dumps(messages,ensure_ascii=False),'Future revision leaked into original model context')
            if kind=='plan':
                payload=json.loads(messages[1]['content']);cases=payload.get('acceptance_cases') or {}
                require(cases.get('case_count')==6 and cases.get('turn_count')==7,'Current six cases missing')
                if b.phase=='original_plan':require(payload.get('existing_plan_context') is None and not t.get('workflow_plan'),'Original must begin without an old graph')
                else:require(digest(payload['existing_plan_context']['plan'])==digest(contract['original']['plan']),'Wrong modified baseline')
            quote=reserve_cost(messages,provider['pricing'],6000)
            require(Decimal(0)<=quote<=Decimal('.100'),'Per-call quote exceeded before reservation')
            return await original_budget(item,revision,kind,selected,key,messages,**kwargs)
        h.budgets.call=budget
        async def model(selected,key,messages,**kwargs):
            current();b.prepare_model(selected,key,messages,kwargs)
            try:
                text,usage=await original_model(selected,key,messages,**{**kwargs,'require_final_text':True})
                require(isinstance(text,str) and len(text)<=100000,'Incomplete or oversize final model text')
                inspect_text(text);require(not any(s in text for s in h.sierra_review_secrets),'Model response contains protected text')
                name='model-response-'+b.phase+'.txt';(output/name).write_text(text,'utf-8')
                record['responses'][b.phase]={'file':name,'sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(text)}
                value=json.loads(text,parse_constant=lambda _:require(False,'Non-finite model JSON'))
                if isinstance(value,dict) and isinstance(value.get('nodes'),list):b.candidates.add(digest(value))
                save();return text,usage
            except ProviderError:raise
            except Exception:raise ProviderError('本批完整模型原文或候选无法安全核对，已停止，不修复重试。',usage=locals().get('usage',{})) from None
            finally:b.finish_model()
        h.call_model=model
        async def intercept(own,request):
            current()
            async def physical(req):
                record['physical_http']+=1;save();return await old_async(own,req)
            return await b.dispatch(physical if live else synthetic,request)
        def forbidden(*args,**kwargs):raise RuntimeError('Synchronous physical HTTP forbidden')
        httpx.AsyncHTTPTransport.handle_async_request=intercept;httpx.HTTPTransport.handle_request=forbidden
        try:
            from journey import run as journey
            with TestClient(h.app) as api:journey(api,h,b,fixture,contract,output,mode)
            require(record.get('state')=='passed','Journey did not complete')
        except BaseException as exc:
            b.halted=True;record.update(state='stopped',failure_type=type(exc).__name__,phase=b.phase,failure_location=failure_location(exc,root))
            if not live:
                import traceback
                record.update(local_public_error=str(exc),local_public_traceback=traceback.format_exc())
        finally:
            try:record['protection']=verify(h.store,env,b,before)
            except Exception:
                record.update(state='stopped',protection_failure=True)
                if not live:raise
            if live:
                from execute import verify_history
                try:verify_history(plan)
                except Exception:
                    record.update(state='stopped',history_protection_failure=True);save();raise
            save();httpx.AsyncHTTPTransport.handle_async_request=old_async;httpx.HTTPTransport.handle_request=old_sync
        if not live:require(record['physical_http']==0,'Physical HTTP during rehearsal')
        return record
