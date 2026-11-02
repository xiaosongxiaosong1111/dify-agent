"""Normal product interview/planning APIs in a disposable, zero-Dify workspace."""
import copy,hashlib,io,json,os,sys,tempfile,time,zipfile
from decimal import Decimal
from pathlib import Path
from common import PROJECT,ReadOnly,capture,digest,require
from guard import Boundary,STAGES,CAP,candidate,changed_plan,check_review

def run(mode,output,plan=None):
 live=mode=='live';root=Path(__file__).resolve().parent;output=Path(output).resolve()
 require(output.is_relative_to(PROJECT/'work') and not output.exists(),'New isolated output only');output.mkdir()
 fixture=json.loads((root/'fixture.json').read_text('utf-8'));record={'state':'running','mode':mode,'physical_http':0,'model_http_started':0,'automatic_retry':False,'production_task_changed':False,'business_verified':False,'reviews':{}}
 def save():
  temp=output/'progress-writing.tmp';temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(temp,output/'progress.json')
 save()
 if live:
  from execute import authorize_worker
  authorize_worker(root,plan)
 before=capture(ReadOnly(PROJECT/'data'))
 with tempfile.TemporaryDirectory(dir=output,prefix='bootstrap-') as temp:
  os.environ['FLOWCRAFT_DATA_DIR']=temp;sys.path.insert(0,plan['backend_path'] if live else str(PROJECT/'backend'))
  from app import main as h
  from app.storage import Store
  from app.plan_drafts import inspect_text
  from app.planning import reserve_cost,PlanningStopped
  from fastapi.testclient import TestClient
  import httpx
  data=output/'data'
  class LocalStore(Store):
   def connect(self):
    require(self.root.resolve()==data and self.path.resolve()==data/'flowcraft.sqlite3','Only owned isolated writes');return super().connect()
   def secret(self,item,field):
    require(item==fixture['provider_id'] and field=='api_key','Other credential read forbidden');return key
   def has_secret(self,item,field):return item==fixture['provider_id'] and field=='api_key' and bool(key)
   def set_secret(self,*a,**kw):raise RuntimeError('No persisted credential copies')
   def put_with_secrets(self,*a,**kw):raise RuntimeError('No persisted credential copies')
   def put_many_with_secrets(self,*a,**kw):raise RuntimeError('No persisted credential copies')
   def put_many_with_secret_sets(self,*a,**kw):raise RuntimeError('No persisted credential copies')
  h.DATA_ROOT=data;h.store=LocalStore(data)
  if live:
   from cryptography.fernet import Fernet
   source=ReadOnly(PROJECT/'data');provider=source.get('provider',fixture['provider_id']);require(digest(provider)==plan['provider_sha256'],'Provider changed');source.cipher=Fernet((PROJECT/'data/.credential-key').read_bytes());key=Store.secret(source,fixture['provider_id'],'api_key')
  else:
   provider={'id':fixture['provider_id'],'name':'公开替身主模型','role':'main','provider':'deepseek','protocol':'openai-compatible','base_url':'https://api.deepseek.com','model':'deepseek-flash','pricing':{'input_per_million_usd':.3,'cached_input_per_million_usd':.006,'output_per_million_usd':1.2}};key='PUBLIC_SYNTHETIC_ONLY'
  h.store.put('provider',provider['id'],provider);h.store.put('settings','execution',{'max_retries':0,'max_minutes':4,'max_cost_usd':.200})
  boundary=Boundary(provider,key,record,save);original_call=h.call_model;original_budget=h.budgets.call;old_async=httpx.AsyncHTTPTransport.handle_async_request;old_sync=httpx.HTTPTransport.handle_request
  def current_scope():
   require(not (output/'stop.json').exists(),'Explicit stop')
   if live:
    from execute import current,validated
    require(validated(root)==plan,'Frozen sources changed');current(plan)
  async def budget_admit(item_id,revision,kind,selected,credential,messages,**kwargs):
   current_scope();t=h.get_task(record['task_id']);phase=boundary.phase
   require(item_id==t['id'] and revision==t['revision'] and selected==provider and credential==key and 'initial_intake' in record['reviews'] and not boundary.halted and boundary.calls[phase]==0,'Current phase/profile/revision only')
   require(kind==('interview' if phase.endswith('interview') else 'plan') and kwargs.get('max_tokens')==6000 and 0<kwargs.get('timeout',0)<=120 and not kwargs.get('stream'),'Exact stage kind/settings required')
   if phase in {'original','modified'}:
    from app.node_guidance import for_task
    from app.planning_case_context import current as cases_current
    payload=json.loads(messages[1]['content']);cases=cases_current(t)
    if mode=='wrong_original_context' and phase=='original':payload['existing_plan_context']={'plan':{'nodes':[]}}
    if mode=='missing_planning_cases' and phase=='original':payload.pop('acceptance_cases',None)
    try:
     require(payload.get('requirements')==t['requirements'] and payload.get('configuration')==t['configuration'] and payload.get('node_guidance')==for_task(t),'Current rules/configuration missing')
     require(payload.get('acceptance_cases')==cases and cases['case_count']==6 and cases['turn_count']==7,'Current six cases/seven turns missing')
     existing=payload.get('existing_plan_context')
     if phase=='original':require(existing is None and t.get('workflow_plan') is None and not t.get('dsl_reference') and not t.get('materials'),'No old graph/template may enter original planning')
     else:require(existing and digest(existing['plan'])==record['original_plan_sha256']==digest(t['workflow_plan']),'Reviewed current original graph required for modification')
    except RuntimeError:
     record['local_admission_stopped']=True;save();raise PlanningStopped('scope_admission','本批当前样例或原版基线来源未通过，尚未派发请求或预留费用。') from None
    record.setdefault('planning_context',{})[phase]={'case_count':6,'turn_count':7,'case_sha256':cases['content_sha256'],'existing_plan_sha256':digest(existing['plan']) if existing else None};save()
   quote=reserve_cost(messages,provider['pricing'],6000);require(0<=quote<=CAP and quote+sum(boundary.quotes.values(),Decimal(0))<=CAP*2,'Configured reserve exceeded')
   return await original_budget(item_id,revision,kind,selected,credential,messages,**kwargs)
  h.budgets.call=budget_admit
  async def call_model(p,k,messages,**kwargs):
   current_scope();boundary.prepare(p,k,messages,kwargs)
   try:
    text,usage=await original_call(p,k,messages,**{**kwargs,'require_final_text':True})
    try:
     require(isinstance(text,str) and len(text)<=100000,'Bounded complete response required');inspect_text(text)
     name='model-response-'+boundary.phase+'.txt'
     with (output/name).open('x',encoding='utf-8',newline='') as f:f.write(text)
     record.setdefault('responses',{})[boundary.phase]={'file':name,'sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(text)};save()
    except Exception:
     from app.providers import ProviderError
     raise ProviderError('本批完整原文无法安全归档，已停止；不回显、不重试。',usage=usage) from None
    return text,usage
   finally:boundary.finish()
  h.call_model=call_model
  async def intercept(own,request):
   current_scope();boundary.admit(request)
   if live:record['physical_http']+=1;save();return await old_async(own,request)
   if mode=='provider_error':return httpx.Response(502,json={'error':'PUBLIC_FAILURE'},request=request)
   phase=boundary.phase
   body=copy.deepcopy(synthetic_plan)
   if phase=='modified':body=changed_plan(body,fixture)
   if mode=='invalid_original' and phase=='original':body={'schema_version':1,'nodes':[],'edges':[]}
   if mode=='original_clarification' and phase=='original':body={'error':'请明确公开配置。','needs_decision':[{'question':'请核对资料。'}]}
   if mode=='changed_scope' and phase=='modified':body['nodes'][0]['title']='UNAPPROVED_CHANGE'
   if mode=='unchanged_modified' and phase=='modified':body=copy.deepcopy(synthetic_plan)
   content='{"bad": [}' if mode=='invalid_json' else json.dumps(body,ensure_ascii=False)
   unknown=mode=='unknown_usage' or mode=='unknown_second' and phase=='complete_interview' or mode=='unknown_modified' and phase=='modified'
   usage={} if unknown else {'prompt_tokens':200,'completion_tokens':300,'total_tokens':500}
   return httpx.Response(200,json={'choices':[{'finish_reason':'length' if mode=='truncated' else 'stop','message':{'role':'assistant','content':content}}],'usage':usage},request=request)
  def forbidden(*a,**kw):raise RuntimeError('No synchronous HTTP, Dify or other endpoint')
  httpx.HTTPTransport.handle_request=forbidden;httpx.AsyncHTTPTransport.handle_async_request=intercept
  def wait_review(stage,t,assessment,proposed=None):
   actual=h.get_task(t['id']);body={'stage':stage,'task_id':t['id'],'revision':t['revision'],'saved_task_sha256':digest(actual),'requirements':t['requirements'],'configuration':t['configuration'],'intake_review':t.get('intake_review'),'interview_attempts':t.get('interview_attempts',[]),'messages':t['messages'],'candidate':proposed,'assessment':assessment,'responses':copy.deepcopy(record.get('responses',{})),'saved_test_cases':t.get('test_cases',[]),'requested_requirements':fixture['requirements'],'delegated_clarifications':fixture['delegated_clarifications'],'verification':'requires_actual_root_review_not_business_acceptance'}
   inspect_text(json.dumps(body,ensure_ascii=False));src={k:body[k] for k in ('stage','task_id','revision')};src['source_sha256']=digest(body)
   (output/('review-source-'+stage+'.json')).write_text(json.dumps(body,ensure_ascii=False,indent=2),'utf-8');record['waiting_review']=src;save();path=output/('review-'+stage+'.json')
   if not live:
    reject=mode=='review_reject' and stage=='original' or mode=='intake_review_reject' and stage=='initial_intake'
    receipt={**src,'decision':'reject' if reject else 'proceed','actor':'synthetic_protocol','note':'Public protocol only, not actual model quality or human signoff.'}
    if mode=='review_stale' and stage=='original' or mode=='complete_review_stale' and stage=='complete_interview' or mode=='intake_review_stale' and stage=='initial_intake':receipt['source_sha256']='0'*64
    path.write_text(json.dumps(receipt),'utf-8')
   deadline=time.monotonic()+300
   while not path.exists():require(time.monotonic()<deadline and not (output/'stop.json').exists(),'Root review timeout/stop');time.sleep(.25)
   require(time.monotonic()<deadline and not (output/'stop.json').exists(),'Late root review')
   from execute import load
   require(digest(h.get_task(t['id']))==body['saved_task_sha256'] and digest(load(output/('review-source-'+stage+'.json')))==src['source_sha256'],'Review source changed')
   receipt=load(path);review=check_review(receipt,src,live);inspect_text(review['note']);record['reviews'][stage]=review;record.pop('waiting_review',None);save()
  try:
   with TestClient(h.app) as api:
    def req(method,path,body=None,allowed=(200,201)):
     r=api.request(method,path,json=body) if body is not None else api.request(method,path)
     require(r.status_code in allowed,'Product API refused '+path+' '+str(r.status_code));return r.json()
    task=req('POST','/api/tasks',{'name':fixture['task_name'],'app_type':'advanced-chat'});tid=task['id'];base='/api/tasks/'+tid;record['task_id']=tid
    def fresh():return h.get_task(tid)
    def post(path,**body):return req('POST',base+path,{'revision':fresh()['revision'],**body})
    budget=req('PATCH',base+'/budget',{'revision':fresh()['revision'],'policy_revision':0,'limit_usd':'0.200','acknowledge_change':True,'note':'本独立隔离新任务累计配置价估算上限；不含旧账本，不代表供应商账单硬限。'})
    require(budget['limit_usd']=='0.200' and not budget['entries'] and not budget['excluded_history_present'],'Explicit fresh cumulative policy required')
    def known_stage(stage):
     entries=h.budgets.get(tid)['entries'];index=STAGES.index(stage)
     require(len(entries)==index+1 and all(e['status']=='settled' and e['cost_basis']=='reported_usage' and e['charged_usd'] is not None and e.get('call_status')=='returned' for e in entries),'Every dispatched stage must have complete known reported usage before review or continuation')
     record['known_usage_stages']=list(STAGES[:index+1]);save()
    req('PATCH',base,{'requirements':fixture['requirements'],'configuration':fixture['configuration']})
    post('/test-cases',cases=fixture['cases'])
    wait_review('initial_intake',fresh(),{'actor':'agent_delegated','manual_intake_required':True,'model_interview_verified':False,'case_expectations_kept':True,'clarifications':fixture['delegated_clarifications']})
    if not live:
     source=ReadOnly(PROJECT/'work/offline-candidate409/data').list('task')[0];synthetic_plan=copy.deepcopy(source['workflow_plan'])
    first=None
    def review_intake():
     t=fresh();state=req('GET',base+'/intake');answers={q['id']:t['requirements'].get(q['id'],t['requirements']['rules']) for q in state['standard']}
     post('/intake/manual',context_token=state['context_token'],answers=answers,acknowledge_review=True,actor='agent_delegated',actor_note='根代理已按既有委托实际核对当前需求、配置、六例七轮及文案澄清后进行手工内容准入；本批没有模型访谈，不代表人类签收或业务已验收。');post('/confirm',kind='requirements')
    review_intake()
    record['manual_intake_revision']=fresh()['revision'];record['model_interview_verified']=False;record['manual_intake_actor']=fresh()['intake_review']['review_actor'];record['manual_intake_note']=fresh()['intake_review']['actor_note'];require(record['manual_intake_actor']=='agent_delegated' and fresh()['intake_review']['source']=='agent_declared','Actual delegated manual intake record required');save()
    for stage in ('original','modified'):
     if stage=='modified':
      require(first is not None and 'original' in record['reviews'],'Reviewed original required')
      reqs=copy.deepcopy(fresh()['requirements']);reqs['output']=reqs['output'].replace(fixture['inputs']['no_hit_reply'],fixture['changed_no_hit_reply']);req('PATCH',base,{'requirements':reqs})
      cases=copy.deepcopy(fixture['cases']);cases[1]['expectation']['expected']=fixture['changed_no_hit_reply'];post('/test-cases',cases=cases);review_intake()
     boundary.begin(stage);req('POST',base+'/plan/generate',{'revision':fresh()['revision']},allowed=(200,422));t=fresh();op=t['planning_runs'][-1]
     known_stage(stage)
     require(boundary.calls[stage]==1 and len(op['attempts'])==1 and op['attempts'][0]['cost_basis']=='reported_usage' and op['attempts'][0]['status']=='valid','Only one valid known-usage attempt per plan')
     if stage=='original':require(op['status']=='succeeded' and t['plan_source']=='model' and t['workflow_plan'],'Fresh normal model draft required');proposed=copy.deepcopy(t['workflow_plan'])
     else:require(op['status']=='paused' and op['stop_reason']=='replanning_review' and digest(t['workflow_plan'])==digest(first),'Changed candidate must retain the old formal original');proposed=copy.deepcopy(op['last_candidate'])
     raw=h.extract_json((output/record['responses'][stage]['file']).read_text('utf-8'));require(digest(raw)==digest(proposed),'Candidate differs from original model JSON')
     view=copy.deepcopy(t);view['workflow_plan']=proposed;assessment=candidate(h,view,fixture,first);wait_review(stage,t,assessment,proposed)
     post('/plan',plan=proposed);review_intake();post('/plan',plan=proposed);post('/confirm',kind='configuration');post('/build');t=fresh();require(digest(t['workflow_plan'])==digest(proposed),'Adopted graph changed')
     response=api.get(base+'/delivery-bundle',params={'revision':t['revision']});require(response.status_code==200,'Static bundle refused')
     with zipfile.ZipFile(io.BytesIO(response.content)) as z:
      manifest=json.loads(z.read('manifest.json'));require(all(manifest[k] is False for k in ('network_requested','business_verified','platform_checked')) and all(hashlib.sha256(z.read(n)).hexdigest()==v['sha256'] and len(z.read(n))==v['bytes'] for n,v in manifest['files'].items()),'Bundle source/flags/hash invalid')
     (output/(stage+'.zip')).write_bytes(response.content);record.setdefault('deliveries',[]).append({'stage':stage,'revision':t['revision'],'plan_sha256':digest(proposed),'zip_sha256':hashlib.sha256(response.content).hexdigest(),'static_only':True})
     if stage=='original':first=copy.deepcopy(proposed);record['original_plan_sha256']=digest(first);save()
    require(sum(boundary.calls.values())==2 and len(record['reviews'])==3 and len(record['deliveries'])==2,'Full reviewed-spec two-plan dual-version chain incomplete');record['state']='passed'
  except BaseException as exc:
   boundary.stop();record.update(state='stopped',failure_type=type(exc).__name__)
   if not live:record['public_failure']=str(exc)
  finally:
   h.call_model=original_call;h.budgets.call=original_budget;httpx.AsyncHTTPTransport.handle_async_request=old_async;httpx.HTTPTransport.handle_request=old_sync
   require(capture(ReadOnly(PROJECT/'data'))==before,'Production data changed')
   if live:
    from execute import current
    current(plan)
   with h.store.connect() as db:require(db.execute('SELECT COUNT(*) FROM secrets').fetchone()[0]==0,'Persisted credential copy')
   record['budget_entry_count']=sum(len(x.get('entries',[])) for x in h.store.list('task_budget'));record.update(production_data_kept=True,isolated_secrets_persisted=False,semantic_reviewed=live and record['state']=='passed',human_signoff=False,actual_dify_verified=False);save()
 return record

if __name__=='__main__':
 require(len(sys.argv)==3 and sys.argv[1]!='live','Public rehearsal only');r=run(sys.argv[1],sys.argv[2]);print(json.dumps({k:r.get(k) for k in ('state','model_http_started','physical_http','public_failure')}))
