"""Normal product planning in disposable data; production source is read-only."""
import copy,hashlib,io,json,os,sys,tempfile,time,zipfile
from decimal import Decimal
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require
from guard import Boundary,candidate,check_review,replacement

def run(mode,output,plan=None):
    live=mode=='live';root=Path(__file__).resolve().parent;output=Path(output).resolve()
    require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New work output required');output.mkdir()
    fixture=json.loads((root/'fixture.json').read_text('utf-8'));record={'state':'running','mode':mode,'physical_http':0,'model_http_started':0,'automatic_retry':False,'production_task_changed':False,'business_verified':False,'reviews':{}}
    def save():
        temp=output/'progress-writing.tmp';temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(temp,output/'progress.json')
    save()
    if live:
        from execute import authorize_worker
        authorize_worker(root,plan)
    with tempfile.TemporaryDirectory(dir=output,prefix='module-bootstrap-') as bootstrap:
        os.environ['FLOWCRAFT_DATA_DIR']=bootstrap;sys.path.insert(0,plan['backend_path'] if live else str(PROJECT/'backend'))
        from app import main as h
        from app.storage import Store
        from app.plan_drafts import inspect_text
        from fastapi.testclient import TestClient
        import httpx
        data=output/'data'
        class LocalStore(Store):
            def connect(self):
                require(self.root.resolve()==data and self.path.resolve()==data/'flowcraft.sqlite3','Only isolated data writes');return super().connect()
            def secret(self,item,field):
                require(item==fixture['provider_id'] and field=='api_key','Other credential read forbidden');return key
            def has_secret(self,item,field):return item==fixture['provider_id'] and field=='api_key' and bool(key)
            def set_secret(self,*args,**kwargs):raise RuntimeError('Credential copies are not persisted')
            def put_with_secrets(self,*args,**kwargs):raise RuntimeError('Credential copies are not persisted')
            def put_many_with_secrets(self,*args,**kwargs):raise RuntimeError('Credential copies are not persisted')
            def put_many_with_secret_sets(self,*args,**kwargs):raise RuntimeError('Credential copies are not persisted')
        h.DATA_ROOT=data;h.store=LocalStore(data)
        before=capture(ReadOnly(PROJECT/'data')) if live else None
        if live:
            from cryptography.fernet import Fernet
            source=ReadOnly(PROJECT/'data');provider=source.get('provider',fixture['provider_id']);require(digest(provider)==plan['provider_sha256'],'Provider changed')
            # Reuse the standard decryptor with a URI read-only connection; never
            # initialize a writable production Store or copy the credential key.
            source.cipher=Fernet((PROJECT/'data/.credential-key').read_bytes());key=Store.secret(source,fixture['provider_id'],'api_key')
        else:
            provider={'id':fixture['provider_id'],'name':'公开替身主模型','role':'main','provider':'deepseek','protocol':'openai-compatible','base_url':'https://api.deepseek.com','model':'deepseek-flash','pricing':{'input_per_million_usd':.3,'cached_input_per_million_usd':.006,'output_per_million_usd':1.2}};key='PUBLIC_SYNTHETIC_ONLY'
        h.store.put('provider',provider['id'],provider)
        h.store.put('settings','execution',{'max_retries':0,'max_minutes':2,'max_cost_usd':.080})
        boundary=Boundary(provider,key,record,save);original_call=h.call_model;original_transport=httpx.AsyncHTTPTransport.handle_async_request
        async def call_model(p,k,messages,**kwargs):
            require(not (output/'stop.json').exists(),'Explicit stop before model dispatch')
            if live:
                from execute import current,validated
                require(validated(root)==plan,'Frozen sources changed');current(plan)
            boundary.prepare(p,k,messages,kwargs)
            try:return await original_call(p,k,messages,**{**kwargs,'require_final_text':True})
            finally:boundary.finish()
        h.call_model=call_model
        async def intercept(own,request):
            require(not (output/'stop.json').exists(),'Explicit stop at transport admission')
            boundary.admit(request)
            if live:
                record['physical_http']+=1;save();return await original_transport(own,request)
            if mode=='provider_error':return httpx.Response(502,json={'error':'PUBLIC_FAILURE'},request=request)
            if mode=='clarification':body={'error':'公开澄清问题','needs_decision':[{'question':'请明确这个条件。'}]}
            elif mode=='invalid_original' and boundary.phase=='original':body={'schema_version':1,'nodes':[],'edges':[]}
            else:
                body=copy.deepcopy(synthetic_plan)
                if boundary.phase=='modified':body=replacement(body,fixture['inputs']['no_hit_reply'],fixture['changed_no_hit_reply'])
                if mode=='changed_scope' and boundary.phase=='modified':body['nodes'][0]['title']='Changed beyond wording'
            usage={} if mode=='unknown_usage' else {'prompt_tokens':200,'completion_tokens':300,'total_tokens':500}
            return httpx.Response(200,json={'choices':[{'finish_reason':'length' if mode=='truncated' else 'stop','message':{'role':'assistant','content':json.dumps(body,ensure_ascii=False)}}],'usage':usage},request=request)
        def forbidden(*a,**kw):raise RuntimeError('Synchronous/other HTTP forbidden')
        old_sync=httpx.HTTPTransport.handle_request;httpx.HTTPTransport.handle_request=forbidden;httpx.AsyncHTTPTransport.handle_async_request=intercept
        def wait_review(stage,task,assessment):
            body={'stage':stage,'task_id':task['id'],'revision':task['revision'],'saved_task_sha256':digest(h.get_task(task['id'])),'requirements':task['requirements'],'configuration':task['configuration'],'candidate':task['workflow_plan'],'assessment':assessment,'verification':'requires_root_review_not_business_acceptance'}
            inspect_text(json.dumps(body,ensure_ascii=False));source={k:body[k] for k in ('stage','task_id','revision')};source['source_sha256']=digest(body)
            (output/('review-source-'+stage+'.json')).write_text(json.dumps(body,ensure_ascii=False,indent=2),'utf-8');record['waiting_review']=source;save()
            path=output/('review-'+stage+'.json')
            if not live:
                receipt={**source,'decision':'reject' if mode=='review_reject' else 'proceed','actor':'synthetic_protocol','note':'Public protocol only; no semantic review or human signoff.'}
                if mode=='review_stale':receipt['source_sha256']='0'*64
                path.write_text(json.dumps(receipt),'utf-8')
            deadline=time.monotonic()+300
            while not path.exists():
                require(time.monotonic()<deadline and not (output/'stop.json').exists(),'Review timeout/explicit stop; no later call');time.sleep(.25)
            require(time.monotonic()<deadline and not (output/'stop.json').exists(),'Late review/explicit stop')
            from execute import load
            current=h.get_task(task['id']);require(digest(current)==body['saved_task_sha256'] and digest(json.loads((output/('review-source-'+stage+'.json')).read_text('utf-8')))==source['source_sha256'],'Review source changed')
            receipt=load(path);review=check_review(receipt,source,live);inspect_text(review['note']);record['reviews'][stage]=review;record.pop('waiting_review',None);save()
        try:
            with TestClient(h.app) as api:
                def req(method,path,body=None,allowed=(200,201)):
                    r=api.request(method,path,json=body) if body is not None else api.request(method,path)
                    require(r.status_code in allowed,'Product API refused '+path+' '+str(r.status_code));return r.json()
                task=req('POST','/api/tasks',{'name':fixture['task_name'],'app_type':'advanced-chat'});tid=task['id'];base='/api/tasks/'+tid;record['task_id']=tid
                def fresh():return h.get_task(tid)
                def post(path,**body):return req('POST',base+path,{'revision':fresh()['revision'],**body})
                cfg=copy.deepcopy(fixture['configuration']);cfg['assistant_provider_id']=provider['id']
                req('PATCH',base,{'requirements':fixture['requirements'],'configuration':cfg})
                def review_intake():
                    t=fresh();state=req('GET',base+'/intake');extra={'memory':'保留最近5轮；每个实际样例使用新会话，缺号补号在原会话。','dialogue':fixture['inputs']['clarify_reply']+' 缺号使用固定追问。','retrieval':t['requirements']['knowledge']+' 资料不足逐字用无答案文字。','external':t['requirements']['knowledge']+' 仅合成表，无其它接口。','conversation_state':'order_wait_requested/order_wait_consumed均boolean初始false、每会话隔离、未更新保留；不同表示等待，每轮先消费，缺号重新登记，不保存敏感信息、不计数。'}
                    answers={r['id']:t['requirements'].get(r['id'],extra.get(r['id'],'仅本次公开合成静态规划，不进行外部资源操作。')) for r in state['standard']}
                    post('/intake/manual',context_token=state['context_token'],answers=answers,acknowledge_review=True,actor='agent_delegated',actor_note='冻结前根代理逐项核对的明确公开需求；按常规委托保存，无模型访谈或人类签收声明。');post('/confirm',kind='requirements')
                review_intake()
                if not live:
                    from app.after_sales_starter import prepare
                    synthetic_plan=json.loads(prepare(fresh(),fixture['inputs'])[0])
                first=None
                for stage in ('original',):
                    if stage=='modified':
                        changed=copy.deepcopy(fixture['requirements']);changed['output']=changed['output'].replace(fixture['inputs']['no_hit_reply'],fixture['changed_no_hit_reply'])
                        req('PATCH',base,{'expected_revision':fresh()['revision'],'requirements':changed});require(fresh()['plan_stale'] and not fresh()['configuration_confirmed'],'Change did not invalidate');review_intake()
                    boundary.begin(stage);response=req('POST',base+'/plan/generate',{'revision':fresh()['revision']},allowed=(200,422));task=fresh();op=task['planning_runs'][-1]
                    require(boundary.calls[stage]==1 and len(op['attempts'])==1 and op['attempts'][0].get('cost_basis')!='reserved_unknown_usage','Missing call/unknown usage/retry')
                    require(op['attempts'][0].get('usage',{}).get('completion_tokens') is not None,'Usage incomplete')
                    require(Decimal(str(op['estimated_cost_usd']))<=Decimal('0.080') and sum((Decimal(str(r.get('estimated_cost_usd',0))) for r in task['planning_runs']),Decimal(0))<=Decimal('0.080'),'Reported configured cost exceeded scope; no later call')
                    record.setdefault('configured_costs',{})[stage]=str(op['estimated_cost_usd']);save()
                    if stage=='modified':
                        require(op['status']=='paused' and op.get('stop_reason')=='replanning_review' and isinstance(op.get('last_candidate'),dict),'No valid explicit modification candidate')
                        task=copy.deepcopy(task);task['workflow_plan']=copy.deepcopy(op['last_candidate'])
                    else:require(op['status']=='succeeded' and task['plan_source']=='model','Original model did not produce valid plan')
                    assessment=candidate(h,task,fixture,first);current=fresh()
                    # The saved source is the immutable model candidate; a separate
                    # review view uses that candidate without applying it early.
                    view=copy.deepcopy(current);view['workflow_plan']=task['workflow_plan']
                    wait_review(stage,view,assessment)
                    raw_candidate=copy.deepcopy(task['workflow_plan']);record.setdefault('candidate_digests',{})[stage]=digest(raw_candidate)
                    # Normal explicit adoption of the reviewed model JSON, then
                    # the existing post-plan state review/confirmation sequence.
                    post('/plan',plan=raw_candidate);review_intake();post('/plan',plan=raw_candidate);post('/confirm',kind='configuration');post('/build')
                    require(digest(fresh()['workflow_plan'])==digest(raw_candidate),'Adopted graph differs from model candidate')
                    r=api.get(base+'/delivery-bundle',params={'revision':fresh()['revision']});require(r.status_code==200,'Static delivery failed')
                    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                        manifest=json.loads(z.read('manifest.json'));require(all(manifest[k] is False for k in ('network_requested','business_verified','platform_checked')),'Static flags changed')
                    (output/(stage+'.zip')).write_bytes(r.content);record.setdefault('deliveries',[]).append({'stage':stage,'revision':fresh()['revision'],'zip_sha256':hashlib.sha256(r.content).hexdigest(),'static_only':True})
                    if first is None:first=raw_candidate
                    if mode=='stop_after_original' and stage=='original':(output/'stop.json').write_text('{}','utf-8')
                require(sum(boundary.calls.values())==1 and len(record['reviews'])==1,'Incomplete single planning batch');record['state']='passed'
        except BaseException as exc:
            boundary.stop();record.update(state='stopped',failure_type=type(exc).__name__)
            if not live:record['public_failure']=str(exc)
        finally:
            h.call_model=original_call;httpx.AsyncHTTPTransport.handle_async_request=original_transport;httpx.HTTPTransport.handle_request=old_sync
            if live:require(capture(ReadOnly(PROJECT/'data'))==before,'Production data changed')
            with h.store.connect() as db:require(db.execute('SELECT COUNT(*) FROM secrets').fetchone()[0]==0,'Isolated credential persistence forbidden')
            record.update(production_data_kept=True,isolated_secrets_persisted=False,semantic_reviewed=live and record['state']=='passed',human_signoff=False,actual_dify_verified=False);save()
        return record

if __name__=='__main__':
    require(len(sys.argv)==3 and sys.argv[1]!='live','Public rehearsal only')
    result=run(sys.argv[1],Path(sys.argv[2]));print(json.dumps({k:result.get(k) for k in ('state','model_http_started','physical_http','public_failure')}))
