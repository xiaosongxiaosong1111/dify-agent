"""Public isolated full-chain checks for reviewed-remaining394; fake Dify only."""
import asyncio,copy,hashlib,importlib,io,json,os,shutil,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[2]
BACKEND=ROOT/'backend'
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import tool
from boundary import Boundary
from storage_guard import guarded,verify
from journey import run as journey
from reviewed_diagnostic_redaction import extend_guard

FAKE_KEY='diagnostic-secret-7f3a9c1b'

class _Stream(httpx.AsyncByteStream):
    def __init__(self,body):self.body=body
    async def __aiter__(self):yield self.body
def _response(value,status=200,headers=()):
    return httpx.Response(status,headers=[('content-type','application/json'),*headers],stream=_Stream(json.dumps(value,ensure_ascii=False).encode()))
def _raw(body,status=200):
    return httpx.Response(status,headers=[('content-type','application/json')],content=body)
class FakeDify:
    def __init__(self,b,fail_case=None,fail_turn=None,fail_mode=None,fail_service_mode=None,mismatch=None,fail_nodes=(),omit_nodes=()):
        self.b=b;self.fail_case=fail_case;self.fail_turn=fail_turn;self.fail_mode=fail_mode;self.fail_service_mode=fail_service_mode;self.mismatch=mismatch
        self.fail_nodes=set(fail_nodes);self.omit_nodes=set(omit_nodes);self.apps={};self.messages={};self.runs={}
    def seed_existing(self,app,workflow,message,conversation,native):
        self.apps[app]={'draft':copy.deepcopy(workflow)|{'hash':'public-existing-'+app},'published':copy.deepcopy(workflow)|{'id':str(uuid4())},'keys':[]}
        nodes=[{'id':str(uuid4()),'node_id':n['id'],'node_type':n['data']['type'],'title':n['data']['title'],'status':('failed' if n['id'] in self.fail_nodes else 'succeeded'),'error':('公开合成失败' if n['id'] in self.fail_nodes else None)} for n in workflow['graph']['nodes'] if n['id'] not in self.omit_nodes]
        self.messages[message]={'id':message,'conversation_id':conversation,'workflow_run_id':native}
        self.runs[native]={'detail':{'id':native,'status':'succeeded','graph':copy.deepcopy(workflow['graph'])},'trace':{'data':nodes}}
    async def __call__(self,request):
        b=self.b;path=request.url.path;method=request.method;body=json.loads(request.content) if request.content else {}
        if path=='/console/api/login':
            return _response({'result':'success'},200,[('set-cookie','access_token=PUBLICCONSOLETOKEN123456789; Path=/'),('set-cookie','csrf_token=PUBLICCSRFTOKEN123456789; Path=/')])
        if path=='/console/api/workspaces/current/summary':return _response({'id':b.env['console_workspace_id']})
        if path=='/console/api/apps':return _response({'data':[]})
        if path=='/console/api/apps/imports':
            from app.dsl_roundtrip import parse
            app=str(uuid4());native=parse(body['yaml_content'],'advanced-chat');self.apps[app]={'draft':native['workflow']|{'hash':'public-'+app},'published':None,'keys':[]}
            return _response({'status':'completed','app_id':app})
        app=path.split('/')[4] if path.startswith('/console/api/apps/') else b.current
        if app in self.apps:
            row=self.apps[app]
            if path==f'/console/api/apps/{app}':return _response({'id':app,'mode':'advanced-chat'})
            if path.endswith('/workflows/draft'):return _response(copy.deepcopy(row['draft']))
            if path.endswith('/workflows/publish'):
                if method=='POST':
                    row['published']=copy.deepcopy(row['draft'])|{'id':str(uuid4())};return _response({'result':'success','created_at':1700000000})
                return _response(None,404) if row['published'] is None else _response(copy.deepcopy(row['published']))
            if path.endswith('/api-keys'):
                if method=='POST':row['keys']=[{'id':str(uuid4()),'token':'app-PUBLIC-'+str(uuid4())}];return _response(row['keys'][0])
                return _response({'data':row['keys']})
        # fail_mode breaks the first saved-native diagnostic read (the reused first run),
        # not a Service response; fail_service_mode below is the separate Service case.
        if self.fail_mode is not None and '/messages/' in path:
            if self.fail_mode=='invalid_json':return _raw(b'not-json')
            if self.fail_mode=='http_500':return _response({'error':'公开合成技术失败'},500)
            if self.fail_mode=='transport':raise httpx.ConnectError('公开合成传输失败',request=request)
        if path=='/v1/chat-messages':
            if self.fail_service_mode=='invalid_json':return _raw(b'not-json')
            if self.fail_service_mode=='http_500':return _response({'error':'公开合成技术失败'},500)
            if self.fail_service_mode=='transport':raise httpx.ConnectError('公开合成传输失败',request=request)
            case=b.cases[b.case_index];second='conversation_id' in body;turn=case['followups'][0] if second else case
            expected=turn['expectation'].get('expected');answer=' '.join(expected) if isinstance(expected,list) else expected
            failed=self.fail_case is not None and b.case_index==self.fail_case and (self.fail_turn is None or (self.fail_turn==2 and second))
            if failed:answer='公开合成业务失败答案'
            cid=body.get('conversation_id') or str(uuid4());mid,rid=str(uuid4()),str(uuid4())
            self.messages[mid]={'id':mid,'conversation_id':cid,'workflow_run_id':rid}
            graph=copy.deepcopy(self.apps[b.current]['published']['graph']);nodes=[{'id':str(uuid4()),'node_id':n['id'],'node_type':n['data']['type'],'title':n['data']['title'],'status':('failed' if n['id'] in self.fail_nodes else 'succeeded'),'error':('公开合成失败' if n['id'] in self.fail_nodes else None)} for n in graph['nodes'] if n['id'] not in self.omit_nodes]
            self.runs[rid]={'detail':{'id':rid,'status':'succeeded','graph':graph},'trace':{'data':nodes}}
            return _response({'event':'message','mode':'advanced-chat','id':mid,'message_id':mid,'conversation_id':cid,'answer':answer,'metadata':{'usage':{'total_tokens':10,'total_price':'0.0001','currency':'USD'}}})
        if '/messages/' in path:
            value=copy.deepcopy(self.messages[path.rsplit('/',1)[-1]])
            if self.mismatch=='message':value['conversation_id']=str(uuid4())
            return _response(value)
        for rid,items in self.runs.items():
            if path.endswith('/'+rid):
                detail=copy.deepcopy(items['detail'])
                if self.mismatch=='native':detail['id']=str(uuid4())
                elif self.mismatch=='source':detail['graph']['nodes'][0]['data']['title']='公开合成错图'
                return _response(detail)
            if path.endswith('/'+rid+'/node-executions'):return _response(items['trace'])
        raise RuntimeError('Unexpected public fixture path')

def _api_call(api,method,path,body=None):
    r=api.request(method,path,json=body) if body is not None else api.request(method,path)
    assert r.status_code in (200,201),r.text;return r.json()
def _json_persist(path,record):
    """Real atomic progress write plus read-back; never a no-op save."""
    tool.atomic_json(path,record)
    return json.loads(Path(path).read_text('utf-8'),parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
def rejected(fn,label):
    try:fn()
    except RuntimeError:return
    raise AssertionError(label+' was accepted or wrong error type')
def _review(api,path):
    from app import main as h
    from app.intake import BASE
    task=_api_call(api,'GET',path);state=_api_call(api,'GET',path+'/intake')
    standard=state.get('standard')
    if not isinstance(standard,list) or not standard:raise RuntimeError('Public intake standard missing')
    answers={}
    for row in standard:
        key=row.get('id') if isinstance(row,dict) else None
        if not isinstance(key,str) or not key:raise RuntimeError('Public intake topic malformed')
        if key in BASE:value=task['requirements'].get(key)
        elif key in PUBLIC_TOPIC_ANSWERS:value=PUBLIC_TOPIC_ANSWERS[key]
        else:raise RuntimeError('Unexpected public topic '+key)
        if not isinstance(value,str) or not value.strip():raise RuntimeError('Public topic answer missing '+key)
        answers[key]=value
    task=_api_call(api,'POST',path+'/intake/manual',{'revision':task['revision'],'context_token':state['context_token'],
        'answers':answers,'acknowledge_review':True,'actor':'agent_delegated','actor_note':'公开合成代理复核，不是人类签收。'})
    return task

PUBLIC_TOPIC_ANSWERS={
 'memory':'公开合成链覆盖单轮与同会话接续两轮，只核对运行身份和轮次协议；不验证真实模型的记忆能力、指代消解质量或历史窗口效果。',
 'dialogue':'仅验证公开协议用途：固定回复、轮次编排和停止边界；不验证真实模型对话质量、追问策略或人工升级效果。',
 'agent_tools':'仅使用公开资料检索与答复节点，不调用外部工具或自定义接口。',
 'batch':'本批为单条公开问题，不处理批量数组；出现多项时逐项追问，不静默合并。',
 'retrieval':'公开合成图仅用于静态编译和 HTTP 字段验证；假 Dify 固定返回，不验证真实检索命中、无命中文案或回答模型路径，也不宣称真实业务质量。',
 'external':'本批不接外部接口；订单查询仅为公开合成模拟，不访问真实系统。',
 'trigger':'仅由手工公开示例触发，不配置定时或自动触发器。',
 'human':'无人工审核节点；需要人工时只输出固定客服指引，不自动升级或派发。',
 'loop_policy':'本批不使用循环；若出现重复改写立即停止并说明，不自动重试。',
 'document_processing':'本批不接收文件或扫描件；需要解析时停止并说明需另定范围。',
 'conversation_state':'本批公开示例不使用持久会话状态；不保存跨轮字段或敏感信息。',
 'schedule_time':'本批不启用定时触发，不声明时区或频次语义。',
 'schedule_delivery':'本批不进行定时投递或并发去重。',
 'schedule_operations':'本批不持续运行，无定时费用或启停责任。',
 'json_input_scope':'本批不接收JSON对象输入，不做Schema强制校验。',
 'batch_outcomes':'本批不产生逐项结果或汇总合同。'}
def _public_topic_answers(task,plan,requirements):
    from app.intake import BASE,topics
    answers={}
    for row in topics({**task,'workflow_plan':plan,'requirements':requirements}):
        key=row['id']
        answers[key]=requirements[key] if key in BASE else PUBLIC_TOPIC_ANSWERS[key]
    return answers

def _counting_store(provider_id,reads):
    from app.storage import Store
    class CountingStore(Store):
        def secret(self,item,key):
            if item==provider_id and key=='api_key':
                if reads[0]>=tool.DIAGNOSTIC_MAX_READS:raise RuntimeError('diagnostic key read budget exceeded')
                reads[0]+=1
            return super().secret(item,key)
    return CountingStore

def _setup(tmp,fail_case=None,fail_turn=None,fail_mode=None,fail_service_mode=None,mismatch=None,fail_nodes=(),omit_nodes=(),expectations_override=None,expected_stop=False,mutate_initial=None):
    os.environ['FLOWCRAFT_DATA_DIR']=str(Path(tmp)/'data')
    from app import main as h
    from app.storage import Store
    from app.dsl_roundtrip import parse
    from app.workflow_publication import core
    from app.run_diagnostics import binding as product_binding
    data=Path(tmp)/'data';source=Store(data)
    env_id=tool.ENVIRONMENT_ID;workspace=tool.WORKSPACE_ID;existing=tool.EXISTING_APP_ID;provider_id=str(uuid4())
    env={'id':env_id,'name':'公开合成Dify','base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':workspace,
         'console_login_binding':{'base_url':'https://public-dify.invalid','version':'1.17.1','workspace_id':workspace},
         'service_app_id':existing,'connection_revision':str(uuid4()),'capabilities':{'console':'verified','datasets':'untested','runtime':'registered_unverified'}}
    source.put_with_secrets('environment',env_id,env,{'console_token':'PUBLIC_CONSOLE','csrf_token':'PUBLIC_CSRF','service_api_key':'app-PUBLIC-OLD','dataset_api_key':'dataset-PUBLIC-OLD','console_login_email':'public@example.invalid','console_login_password':'PUBLIC_ONLY'})
    source.put('provider',provider_id,{'id':provider_id,'name':'公开合成助手模型','provider':'custom','base_url':'https://public-model.invalid/v1','model':'public-model','role':'main','protocol':'openai-compatible','capabilities':{'text':'untested'}})
    source.set_secret(provider_id,'api_key',FAKE_KEY)
    h.store=source;h.DATA_ROOT=data
    old='知识库暂无相关信息，请联系人工客服。';new='知识库暂无相关信息，请联系人工客服并提供商品型号。'
    requirements={'goal':'公开双版平台核对','audience':'公开合成用户','input':'query文字','output':'无答案固定文案：'+old,
                  'rules':'只按本批已审图运行；不改期望','knowledge':'不适用','exceptions':'技术失败停止','tests':'六例七轮'}
    cases=[{'id':f'case{i}','name':f'样例{i}','input':{'query':f'公开问题{i}'},'expectation':{'mode':'equals','target':'answer','expected':(old if i==2 else '答案'+str(i))},'required':True} for i in range(1,7)]
    cases[5]['followups']=[{'input':{'query':'公开续问'},'expectation':{'mode':'equals','target':'answer','expected':'续答'}}]
    config=copy.deepcopy(h.CONFIG_DEFAULT);config.update(dify_model_provider='deepseek',dify_model='deepseek-flash',assistant_provider_id=provider_id,resource_plan='仅公开本机合成平台核对，不新建Task/库/模型。')
    from fastapi.testclient import TestClient
    with TestClient(h.app) as api:
        task=_api_call(api,'POST','/api/tasks',{'name':'公开剩余平台任务','app_type':'advanced-chat','environment_id':env_id})
        tid=task['id'];rev=task['revision']
        _api_call(api,'PATCH',f'/api/tasks/{tid}',{'expected_revision':rev,'requirements':requirements,'configuration':config})
        task=_api_call(api,'GET',f'/api/tasks/{tid}')
        plan={'schema_version':1,'nodes':[
            {'id':'start','type':'start','config':{'variables':[]}},
            {'id':'no_hit_text','type':'template-transform','config':{'template':old,'variables':[]}},
            {'id':'faq_llm','type':'llm','config':{'system_prompt':'前缀'+old+'后缀','user_prompt':'{{#sys.query#}}'}},
            {'id':'answer','type':'answer','config':{'answer':'{{#faq_llm.text#}}'}}],
            'edges':[{'source':'start','target':'no_hit_text'},{'source':'no_hit_text','target':'faq_llm'},{'source':'faq_llm','target':'answer'}]}
        modified=copy.deepcopy(plan);modified['nodes'][1]['config']['template']=new;modified['nodes'][2]['config']['system_prompt']='前缀'+new+'后缀'
        _api_call(api,'POST',f'/api/tasks/{tid}/test-cases',{'revision':task['revision'],'cases':cases})
        task=_review(api,f'/api/tasks/{tid}')
        task=_api_call(api,'GET',f'/api/tasks/{tid}')
        task=_api_call(api,'POST',f'/api/tasks/{tid}/confirm',{'kind':'requirements','revision':task['revision']})
        task=_api_call(api,'POST',f'/api/tasks/{tid}/plan',{'revision':task['revision'],'plan':plan})
        task=_api_call(api,'GET',f'/api/tasks/{tid}')
        task=_api_call(api,'POST',f'/api/tasks/{tid}/confirm',{'kind':'configuration','revision':task['revision']})
        task=_api_call(api,'POST',f'/api/tasks/{tid}/build',{'revision':task['revision']})
        task=_api_call(api,'GET',f'/api/tasks/{tid}')
        budget={'id':tid,'policy_revision':1,'limit_usd':'0.600','entries':[
            {'id':str(uuid4()),'operation_id':str(uuid4()),'revision':8,'kind':'plan','provider_id':'synthetic-provider','model':'synthetic','pricing':{},'reserved_usd':'0.001','charged_usd':'0.001','status':'settled','call_status':'returned','cost_basis':'reported_usage','usage':{'completion_tokens':1},'policy_revision':1} for _ in range(5)],
            'policy_history':[],'excluded_history_present':False,'scope':'since_ledger_start','created_at':h.now()}
        first_rev=task['revision']
        import_run={'id':tool.EXISTING_IMPORT_RUN,'kind':'import','revision':first_rev,'environment_id':env_id,'status':'success','app_id':existing,'app_type':'advanced-chat','environment_binding':product_binding(env),'result':{'app_id':existing},'error':'','created_at':h.now(),'completed_at':h.now()}
        publish_run={'id':tool.EXISTING_PUBLISH_RUN,'kind':'publish','revision':first_rev,'environment_id':env_id,'status':'success','app_id':existing,'app_type':'advanced-chat','environment_binding':product_binding(env),'result':{'app_id':existing,'state':'succeeded'},'error':'','created_at':h.now(),'completed_at':h.now()}
        first_run={'id':tool.EXISTING_FIRST_RUN,'kind':'run','revision':first_rev,'environment_id':env_id,'status':'success','app_id':existing,'app_type':'advanced-chat','environment_binding':product_binding(env),'input':copy.deepcopy(cases[0]['input']),'test_case':copy.deepcopy(cases[0]),'result':{'id':tool.EXISTING_MESSAGE,'message_id':tool.EXISTING_MESSAGE,'conversation_id':tool.EXISTING_SESSION,'mode':'advanced-chat','answer':'答案1'},'evaluation':{'status':'passed'},'error':'','created_at':h.now(),'completed_at':h.now()}
        task['runs']=[import_run,publish_run,first_run];task['dify_app_id']=existing;task['status']='run_completed'
        if mutate_initial is not None:mutate_initial(task)
        source.put('task',tid,task);source.put('task_budget',tid,budget)
        source.put('execution_limits',tid,{'id':tid,'policy_revision':1,'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None,'updated_at':h.now(),
            'history':[{'before':{'max_started_runs':None,'max_total_minutes':None,'max_reported_cost_usd':None},'after':{'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None},'note':'公开已有首例策略','created_at':h.now(),'source':'user'}]})
        initial_task=source.get('task',tid);initial_budget=source.get('task_budget',tid);limits=source.get('execution_limits',tid)
        def native_of(p):
            content,validation=h.compile_current({**initial_task,'workflow_plan':p});assert validation['valid'],validation['errors'];root=parse(content,'advanced-chat');return root,core(root['workflow'])
        onative,ocore=native_of(plan);mnative,mcore=native_of(modified)
        expectations=expectations_override or {c['id']:{'1':{'must':['start','no_hit_text','faq_llm','answer'],'must_not':[],'any_of':[['no_hit_text'],['faq_llm']]},'2':{'must':['start','no_hit_text','faq_llm','answer'],'must_not':[],'any_of':[['no_hit_text'],['faq_llm']]}} for c in cases}
        modified_cases=copy.deepcopy(cases);modified_cases[1]['expectation']['expected']=new
        modified_requirements={**requirements,'output':requirements['output'].replace(old,new)}
        topic_answers={'original':_public_topic_answers(initial_task,plan,requirements),'modified':_public_topic_answers(initial_task,plan,modified_requirements)}
        contract={'owner_task_id':tid,'review_source':{'authority':'standing_delegated_content_review','actor':tool.REVIEW_ACTOR,'human_signoff':False,'decision':'proceed'},'topic_answers':topic_answers,
                  'original':{'plan':plan,'native':onative,'core':ocore,'trace_expectations':expectations,'requirements':requirements,'cases':cases},
                  'modified':{'plan':modified,'native':mnative,'core':mcore,'trace_expectations':expectations,'requirements':modified_requirements,'cases':modified_cases}}
        fixture={'task_name':'公开剩余平台任务','cases':cases,'requirements':requirements,'changed_no_hit_reply':new,'inputs':{'no_hit_reply':old},'topic_answers':topic_answers}
        old_capture=tool.capture(data)
        record={'state':'running','physical_http':0,'automatic_retry':False,'model_http_started':0}
        progress=Path(tmp)/'progress.json'
        b=Boundary(env,fixture,contract,record,tool.known_apps(data));b.owner=tid;b.save=lambda:_json_persist(progress,b.record)
        reads=[0];Base=_counting_store(provider_id,reads);diagnostics_seen={}
        Guarded=guarded(Base,env,contract,b,old_capture,initial_task,initial_budget,initial_limits=limits,first_run_id=tool.EXISTING_FIRST_RUN,diagnostics_seen=diagnostics_seen)
        scope={'provider_id':provider_id,'purpose':tool.DIAGNOSTIC_PURPOSE,'memory_only':True,'model_calls':0,'max_reads':tool.DIAGNOSTIC_MAX_READS}
        Scoped=extend_guard(Guarded,Base,b,initial_task,scope)
        h.store=Scoped(data);h.DATA_ROOT=data
        def forbidden(*a,**kw):raise RuntimeError('Sierra model/synchronous HTTP forbidden')
        h.call_model=forbidden;h.budgets.call=forbidden;httpx.HTTPTransport.handle_request=forbidden
        original=httpx.AsyncHTTPTransport.handle_async_request;synthetic=FakeDify(b,fail_case,fail_turn,fail_mode,fail_service_mode,mismatch,fail_nodes,omit_nodes)
        synthetic.seed_existing(existing,onative['workflow'],tool.EXISTING_MESSAGE,tool.EXISTING_SESSION,'5b66dc55-cce6-4457-bd4b-8f48ecdfc1bd')
        async def intercepted(own,request):
            async def physical(req):
                record['physical_http']+=1;return await original(own,req)
            return await b.dispatch(synthetic,request)
        httpx.AsyncHTTPTransport.handle_async_request=intercepted
        error=None
        try:
            with TestClient(h.app) as api:
                result=journey(api,h,b,fixture,contract,Path(tmp),scope=scope)
        except Exception as exc:
            if fail_case is None and fail_mode is None and fail_service_mode is None and mismatch is None and not expected_stop:raise
            error=str(exc);b.record.update(state='stopped',failure_type='business_rule_failure' if fail_case is not None else 'protocol_stop');result=None;b.save()
        finally:
            httpx.AsyncHTTPTransport.handle_async_request=original
        assert httpx.AsyncHTTPTransport.handle_async_request is original,'transport not restored'
        check=verify(h.store,env,b,old_capture,initial_task,initial_budget,first_run_id=tool.EXISTING_FIRST_RUN,seen=diagnostics_seen)
        saved=h.get_task(tid);ledger=h.store.get('task_budget',tid)
        first_after=next(r for r in saved['runs'] if r.get('id')==tool.EXISTING_FIRST_RUN)
        assert tool.run_without_diagnostics(first_after)==tool.run_without_diagnostics(first_run)
        if fail_case is not None:
            assert b.halted and b.record.get('failure_capture',{}).get('management_reads',99)<=4
            assert record['physical_http']==0
            services,records=(6,6) if fail_turn==2 else (1,2)
            assert b.counts['run']==services,(b.counts['run'],services)
            assert len([r for r in saved['runs'] if r.get('kind')=='run'])==records,'unexpected run records after stop'
            assert saved['workflow_plan']==plan and ledger['entries']==budget['entries']
            assert check['original_objects_kept'] and check['budget_kept']
            return b.record
        if fail_service_mode is not None:
            assert error is not None and b.halted,'technical Service failure must halt'
            assert b.counts['run']==1,'technical Service failure must record exactly one dispatch'
            assert len([e for e in b.record.get('dispatches',[]) if e.get('kind')=='run'])==1
            assert b.counts['import']==0 and b.counts['publish']==0 and b.counts['key']==0
            assert 'failure_capture' not in b.record
            assert record['physical_http']==0
            assert saved['workflow_plan']==plan and ledger['entries']==budget['entries']
            assert check['original_objects_kept'] and check['budget_kept']
            return {'error':error,'boundary':b,'record':b.record,'saved':saved,'ledger':ledger,'check':check}
        if fail_mode is not None or mismatch is not None or expected_stop:
            assert error is not None
            if fail_mode is not None or mismatch is not None:assert b.halted
            assert record['physical_http']==0
            assert saved['workflow_plan']==plan and ledger['entries']==budget['entries']
            assert check['original_objects_kept'] and check['budget_kept']
            return {'error':error,'boundary':b,'record':b.record,'saved':saved,'ledger':ledger,'check':check}
        assert result['state']=='passed' and result['counts']['model']==0 and record['physical_http']==0
        stats=result['stats']
        assert stats['apps']==1 and stats['publishes']==1 and stats['keys']==1 and stats['reused']==1
        assert stats['starts']==11 and stats['services']==13 and stats['diagnostics']==14 and stats['bundles']==2
        assert b.counts['run']==13 and b.counts['login']==1 and b.counts['import']==1 and b.counts['publish']==1 and b.counts['key']==1 and b.counts['reads']<=103
        assert len([r for r in saved['runs'] if r.get('kind')=='run'])==12
        assert len([r for r in saved['runs'] if r.get('kind')=='import'])==2 and len([r for r in saved['runs'] if r.get('kind')=='publish'])==2
        assert ledger['entries']==budget['entries']
        assert check['original_objects_kept'] and check['budget_kept']
        assert (Path(tmp)/'original.zip').is_file() and (Path(tmp)/'modified.zip').is_file()
        assert reads[0]==14,reads[0]
        assert len(first_after.get('diagnostics',[]))==1
        return result

def test_full_synthetic_chain():
    with tempfile.TemporaryDirectory() as tmp:return _setup(tmp)

def test_unique_business_failure_bounded_capture():
    with tempfile.TemporaryDirectory() as tmp:
        result=_setup(tmp,fail_case=1)
        assert result['state']=='stopped' and result['failure_capture']['state'] in {'captured','unavailable'}
        assert result['failure_capture']['management_reads']<=4

def test_second_turn_business_failure():
    with tempfile.TemporaryDirectory() as tmp:
        result=_setup(tmp,fail_case=5,fail_turn=2)
        assert result['state']=='stopped' and result['failure_capture']['turn']==2
        assert result['failure_capture']['state'] in {'captured','unavailable'}

def test_service_technical_stops():
    # fail_mode breaks the very first saved-native diagnostic read of the reused run.
    for mode in ('invalid_json','http_500','transport'):
        with tempfile.TemporaryDirectory() as tmp:
            out=_setup(tmp,fail_mode=mode)
            assert out['boundary'].counts['run']==0 and out['boundary'].counts['import']==0
            assert out['boundary'].counts['login']==1 and out['boundary'].counts['reads']>=2
            assert 'failure_capture' not in out['record'] and not out['record'].get('traces')

def test_service_technical_failure_after_first_case():
    # A genuine new-Service technical failure happens after the first saved-native
    # diagnostic and must show exactly one dispatch before the batch stops.
    for mode in ('invalid_json','http_500','transport'):
        with tempfile.TemporaryDirectory() as tmp:
            out=_setup(tmp,fail_service_mode=mode)
            assert out['boundary'].counts['run']==1,out['boundary'].counts
            assert out['boundary'].halted and 'failure_capture' not in out['record']
            assert out['boundary'].counts['import']==0 and out['boundary'].counts['publish']==0 and out['boundary'].counts['key']==0

def test_diagnostic_identity_rejections():
    for mismatch,needle in (('message','Message mapping mismatch'),('native','Native execution graph/identity mismatch'),('source','Native execution graph/identity mismatch')):
        with tempfile.TemporaryDirectory() as tmp:
            out=_setup(tmp,mismatch=mismatch)
            assert needle in out['error'],out['error']
            assert out['boundary'].counts['run']==0 and out['boundary'].counts['import']==0

def test_existing_source_rejections():
    # The reused first case must be verified before any new Service; a broken stored
    # source stops the batch with zero new import/publish/key/Service dispatches.
    mutations=[
        (lambda task:task.update(dify_app_id=str(uuid4())),'Existing App binding changed'),
        (lambda task:task['runs'][2].update(app_id=str(uuid4())),'Prior run source changed'),
        (lambda task:task['runs'][2].update(revision=7),'Prior run source changed'),
        (lambda task:task['runs'][2].update(environment_id=str(uuid4())),'Prior run source changed'),
        (lambda task:task['runs'][2].update(evaluation={'status':'failed'}),'Prior run not passed'),
        (lambda task:task['runs'][2].update(status='failed'),'Prior run not passed'),
        (lambda task:task['runs'][2].update(diagnostics=[{'id':'public-old-diagnostic'}]),'Prior diagnostics must be absent at start'),
        (lambda task:task['runs'][2]['result'].update(conversation_id=None),'Prior message/session missing'),
        (lambda task:task['runs'][2]['result'].update(message_id=str(uuid4()),id=str(uuid4())),'Prior message/session changed'),
    ]
    for mutate,needle in mutations:
        with tempfile.TemporaryDirectory() as tmp:
            out=_setup(tmp,expected_stop=True,mutate_initial=mutate)
            assert needle in out['error'],out['error']
            assert out['boundary'].counts['run']==0 and out['boundary'].counts['import']==0
            assert out['boundary'].counts['publish']==0 and out['boundary'].counts['key']==0

def test_existing_runs_prefix_binding():
    app,env_id,other=str(uuid4()),str(uuid4()),str(uuid4())
    first={'id':tool.EXISTING_FIRST_RUN,'kind':'run','revision':8,'environment_id':env_id,'app_id':app,'app_type':'advanced-chat',
           'environment_binding':'a'*64,'status':'success','result':{'message_id':str(uuid4()),'conversation_id':str(uuid4())},'evaluation':{'status':'passed'}}
    old=[{'id':tool.EXISTING_IMPORT_RUN,'kind':'import','status':'success','result':{'app_id':app}},
         {'id':tool.EXISTING_PUBLISH_RUN,'kind':'publish','status':'success','result':{'app_id':app}},first]
    report={'id':'d1','run_id':tool.EXISTING_FIRST_RUN,'source_hash':tool.run_source_hash(first),'source_revision':8,'environment_id':env_id,'app_id':app}
    def appended():
        value=copy.deepcopy(old);value[-1]['diagnostics']=[copy.deepcopy(report)];return value
    seen={}
    assert tool.check_existing_runs_prefix(old,appended(),tool.EXISTING_FIRST_RUN,seen)
    assert tool.check_existing_runs_prefix(old,appended(),tool.EXISTING_FIRST_RUN,seen)
    def bad(mutate,label):
        value=appended();mutate(value[-1]['diagnostics'][0])
        rejected(lambda:tool.check_existing_runs_prefix(old,value,tool.EXISTING_FIRST_RUN,{}),label)
    bad(lambda r:r.update(run_id=other),'diagnostics wrong run')
    bad(lambda r:r.update(source_hash='0'*64),'diagnostics wrong source hash')
    bad(lambda r:r.update(app_id=other),'diagnostics wrong app')
    bad(lambda r:r.update(source_revision=7),'diagnostics wrong revision')
    bad(lambda r:r.update(environment_id=other),'diagnostics wrong environment')
    replaced=appended();replaced[-1]['diagnostics'][0]['id']='d2'
    rejected(lambda:tool.check_existing_runs_prefix(old,replaced,tool.EXISTING_FIRST_RUN,seen),'diagnostics replaced')
    removed=[copy.deepcopy(run) for run in old]
    rejected(lambda:tool.check_existing_runs_prefix(old,removed,tool.EXISTING_FIRST_RUN,seen),'accepted diagnostics removed')
    cleared=appended();cleared[-1]['diagnostics']=[]
    rejected(lambda:tool.check_existing_runs_prefix(old,cleared,tool.EXISTING_FIRST_RUN,seen),'accepted diagnostics cleared')
    missing=appended();missing[-1].pop('diagnostics')
    rejected(lambda:tool.check_existing_runs_prefix(old,missing,tool.EXISTING_FIRST_RUN,seen),'accepted diagnostics field deleted')
    altered=appended();altered[-1]['diagnostics'][0].pop('source_hash')
    rejected(lambda:tool.check_existing_runs_prefix(old,altered,tool.EXISTING_FIRST_RUN,seen),'accepted diagnostics field removed')
    damaged=appended();damaged[-1]['result']={'tampered':True}
    rejected(lambda:tool.check_existing_runs_prefix(old,damaged,tool.EXISTING_FIRST_RUN,seen),'first run other field changed after acceptance')
    second=appended();second[-1]['diagnostics'].append(copy.deepcopy(report))
    rejected(lambda:tool.check_existing_runs_prefix(old,second,tool.EXISTING_FIRST_RUN,{}),'second diagnostics append')
    changed=appended();changed[-1]['evaluation']={'status':'failed'}
    rejected(lambda:tool.check_existing_runs_prefix(old,changed,tool.EXISTING_FIRST_RUN,{}),'first run fields changed')
    changed=appended();changed[0]['status']='failed'
    rejected(lambda:tool.check_existing_runs_prefix(old,changed,tool.EXISTING_FIRST_RUN,{}),'other old run changed')
    changed=appended();changed[1]['result']={'app_id':other}
    rejected(lambda:tool.check_existing_runs_prefix(old,changed,tool.EXISTING_FIRST_RUN,{}),'other old run result changed')
    changed=appended();changed[0]['diagnostics']=[{'id':'other'}]
    rejected(lambda:tool.check_existing_runs_prefix(old,changed,tool.EXISTING_FIRST_RUN,{}),'diagnostics on other run')
    changed=appended();changed[-1]['id']=other
    rejected(lambda:tool.check_existing_runs_prefix(old,changed,tool.EXISTING_FIRST_RUN,{}),'first run identity changed')

def test_inspect_existing_artifact_preconditions():
    # Calls the real inspect_existing with public metadata stand-ins and a real
    # temporary artifact file; ro_* readers are replaced only for this test and restored.
    original_anchor=tool.ORIGINAL_GRAPH_SHA;original_readers=(tool.ro_get,tool.ro_list,tool.ro_secret_cipher)
    with tempfile.TemporaryDirectory(prefix='public-inspect-') as tmp:
        project=Path(tmp);folder=project/'data'/tool.TASK_ID;folder.mkdir(parents=True)
        path=folder/'artifact-r8.yaml';body=b'public-artifact-bytes\n';path.write_bytes(body)
        plan={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[]}}],'edges':[]}
        provider=str(uuid4())
        env={'id':tool.ENVIRONMENT_ID,'base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':tool.WORKSPACE_ID,
             'service_app_id':tool.EXISTING_APP_ID,'console_login_binding':{'base_url':'https://public-dify.invalid','version':'1.17.1','workspace_id':tool.WORKSPACE_ID}}
        first={'id':tool.EXISTING_FIRST_RUN,'kind':'run','revision':8,'environment_id':tool.ENVIRONMENT_ID,'app_id':tool.EXISTING_APP_ID,
               'app_type':'advanced-chat','environment_binding':tool._binding(env),'status':'success','evaluation':{'status':'passed'},
               'result':{'message_id':tool.EXISTING_MESSAGE,'conversation_id':tool.EXISTING_SESSION}}
        runs=[{'id':tool.EXISTING_IMPORT_RUN,'kind':'import','status':'success','result':{'app_id':tool.EXISTING_APP_ID}},
              {'id':tool.EXISTING_PUBLISH_RUN,'kind':'publish','status':'success','result':{'app_id':tool.EXISTING_APP_ID}},
              first]
        task={'id':tool.TASK_ID,'revision':8,'plan_source':'manual','status':'run_completed','requirements_confirmed':True,
              'configuration_confirmed':True,'dify_app_id':tool.EXISTING_APP_ID,'environment_id':tool.ENVIRONMENT_ID,
              'workflow_plan':plan,'artifact':{'revision':8,'filename':'artifact-r8.yaml','sha256':hashlib.sha256(body).hexdigest()},
              'configuration':{'assistant_provider_id':provider},'runs':runs}
        budget={'id':tool.TASK_ID,'limit_usd':'0.600','policy_revision':1,'entries':[
            {'status':'settled','call_status':'returned'} for _ in range(5)]}
        limits={'id':tool.TASK_ID,'policy_revision':1,'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None}
        auth={'id':tool.ENVIRONMENT_ID+':app-runtime:'+tool.EXISTING_APP_ID,'app_id':tool.EXISTING_APP_ID}
        provider_row={'id':provider,'name':'公开助手模型','provider':'custom','role':'main'}
        key_row={'app_id':tool.EXISTING_APP_ID,'state':'succeeded'}
        objects={('task',tool.TASK_ID):task,('task_budget',tool.TASK_ID):budget,('environment',tool.ENVIRONMENT_ID):env,
                 ('execution_limits',tool.TASK_ID):limits,('app_runtime_credential',tool.ENVIRONMENT_ID+':app-runtime:'+tool.EXISTING_APP_ID):auth,
                 ('provider',provider):provider_row}
        cipher={(tool.ENVIRONMENT_ID,'service_api_key'):b'public-cipher',(provider,'api_key'):b'public-cipher'}
        def run(task_value):
            objects[('task',tool.TASK_ID)]=task_value
            tool.ro_get=lambda root,kind,item:objects.get((kind,item))
            tool.ro_list=lambda root,kind:([task_value]+[{}]*26) if kind=='task' else ([key_row] if kind=='app_runtime_key_creation' else [])
            tool.ro_secret_cipher=lambda root,item,key:cipher.get((item,key))
            return tool.inspect_existing(project)
        tool.ORIGINAL_GRAPH_SHA=tool.digest(plan)
        try:
            assert run(task)['first_run']['id']==tool.EXISTING_FIRST_RUN
            def bad(mutate,label):
                value=copy.deepcopy(task);mutate(value);rejected(lambda:run(value),label)
            bad(lambda t:t.update(workflow_plan={'schema_version':1,'nodes':[],'edges':[]}),'original plan digest changed')
            bad(lambda t:t.pop('artifact'),'missing artifact')
            bad(lambda t:t['artifact'].update(revision=7),'wrong artifact revision')
            bad(lambda t:t['artifact'].update(sha256=''),'missing artifact sha')
            bad(lambda t:t['artifact'].pop('filename'),'missing artifact filename')
            bad(lambda t:t['artifact'].update(filename='../escape.yaml'),'artifact path escape')
            bad(lambda t:t['artifact'].update(filename=str(Path(tmp)/'outside.yaml')),'artifact absolute path')
            path.write_bytes(b'changed-public-bytes\n')
            rejected(lambda:run(task),'artifact bytes changed')
            path.unlink()
            rejected(lambda:run(task),'artifact file missing')
        finally:
            path.write_bytes(body)
            tool.ORIGINAL_GRAPH_SHA=original_anchor
            tool.ro_get,tool.ro_list,tool.ro_secret_cipher=original_readers

def test_diagnostic_scope_helper():
    provider,owner=str(uuid4()),str(uuid4())
    task={'id':owner,'configuration':{'assistant_provider_id':provider}}
    class Base:
        def secret(self,item,key):return 'public-value'
    class Parent(Base):
        def secret(self,item,key):
            if item==provider and key=='api_key':raise RuntimeError('old refusal')
            return super().secret(item,key)
    class Owner:pass
    boundary=Owner();boundary.owner=owner
    Plain=extend_guard(Parent,Base,boundary,task,None)
    rejected(lambda:Plain().secret(provider,'api_key'),'scope-less provider key read')
    ok={'provider_id':provider,'purpose':tool.DIAGNOSTIC_PURPOSE,'memory_only':True,'model_calls':0,'max_reads':tool.DIAGNOSTIC_MAX_READS}
    Enabled=extend_guard(Parent,Base,boundary,task,ok)
    rejected(lambda:Enabled().secret(provider,'api_key'),'provider key read outside diagnostic context')
    assert Enabled().secret('other-item','api_key')=='public-value'
    for bad,label in (({**ok,'max_reads':15},'scope over ceiling'),({**ok,'max_reads':True},'scope bool reads'),
                      ({**ok,'model_calls':1},'scope model call'),({**ok,'purpose':'other'},'scope purpose'),
                      ({**ok,'memory_only':1},'scope not memory only'),({**ok,'provider_id':str(uuid4())},'scope wrong provider')):
        rejected(lambda bad=bad:extend_guard(Parent,Base,boundary,task,bad),label)
    rejected(lambda:extend_guard(Parent,Base,boundary,task,{k:v for k,v in ok.items() if k!='max_reads'}),'scope missing field')

def test_failure_report_safety():
    env={'id':str(uuid4()),'base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':str(uuid4())}
    b=Boundary(env,{'task_name':'公开','cases':[]},{'owner_task_id':'public-owner'},{'physical_http':0},[]);b.owner='public-owner'
    progress=Path(tempfile.mkdtemp(prefix='public-failure-'))/'progress.json'
    b.save=lambda:_json_persist(progress,b.record)
    b.version='modified';b.phase='modified_cases';b.case_index=3
    record={'state':'running','physical_http':2,'protection':{'original_objects_kept':True},'protection_error':None}
    report=tool.safe_failure_report(record,b,4,dict(b.counts),'RuntimeError')
    assert report['state']=='stopped' and report['failure_type']=='RuntimeError' and report['automatic_retry'] is False
    assert report['stage']=={'version':'modified','phase':'modified_cases','case_index':3,'halted':False}
    assert report['physical_http']==2 and report['provider_key_reads']==4 and report['counts']==dict(b.counts)
    assert report['protection']=={'original_objects_kept':True} and report['protection_error'] is None
    assert report['approval_consumed'] is True and report['rollback'] is False
    protected=tool.safe_failure_report({'protection':None,'protection_error':'RuntimeError'},b,0,{},'RuntimeError')
    assert protected['protection'] is None and protected['protection_error']=='RuntimeError'
    assert 'app-PUBLIC' not in json.dumps(report,ensure_ascii=False)

def test_trace_any_of():
    missing={f'case{i}':{'1':{'must':['start','answer'],'must_not':[],'any_of':[['branch_a'],['branch_b']]}} for i in range(1,7)}
    with tempfile.TemporaryDirectory() as tmp:
        out=_setup(tmp,expectations_override=missing,expected_stop=True)
        assert 'No allowed alternative terminal group succeeded' in out['error'],out['error']
    failed={f'case{i}':{'1':{'must':['start','answer'],'must_not':[],'any_of':[['no_hit_text'],['faq_llm']]}} for i in range(1,7)}
    with tempfile.TemporaryDirectory() as tmp:
        out=_setup(tmp,expectations_override=failed,fail_nodes={'no_hit_text','faq_llm'},expected_stop=True)
        assert 'No allowed alternative terminal group succeeded' in out['error'],out['error']

def _gate_state():
    old_app,app,last=str(uuid4()),tool.EXISTING_APP_ID,str(uuid4())
    env={'id':str(uuid4()),'base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':str(uuid4()),'service_app_id':old_app}
    cases=[{'id':f'case{i}','input':{'query':f'q{i}'},'expectation':{'mode':'equals','target':'answer','expected':'a'}} for i in range(1,7)]
    cases[5]['followups']=[{'input':{'query':'follow'},'expectation':{'mode':'equals','target':'answer','expected':'a'}}]
    fixture={'task_name':'公开合成','cases':cases}
    contract={'owner_task_id':'public-owner','original':{'core':{'public':'core'},'native':{'workflow':{'graph':{'nodes':[{'id':'n1','data':{'type':'start','title':'开始'}}],'edges':[]}}}},'modified':{}}
    return env,fixture,contract,old_app,app,last
def _gate(env,fixture,contract,old_app,source_verified=True):
    folder=Path(tempfile.mkdtemp(prefix='public-gate-'));progress=folder/'progress.json'
    b=Boundary(env,fixture,contract,{'dispatches':[]},[old_app,tool.EXISTING_APP_ID])
    b.owner='public-owner';b.source_verified=source_verified;b.save=lambda:_json_persist(progress,b.record);return b
def _expect_no_send(b,request,label):
    calls=[]
    async def send(req):calls.append(req);raise AssertionError('physical send called')
    try:asyncio.run(b.dispatch(send,request))
    except RuntimeError:pass
    else:raise AssertionError(label+' was accepted')
    assert not calls,label+' reached the physical send'
    assert b.halted

def test_boundary_rejections():
    env,fixture,contract,old_app,app,last=_gate_state()
    def fresh():return _gate(env,fixture,contract,old_app)
    b=fresh();b.started=time.monotonic()-3601
    _expect_no_send(b,httpx.Request('GET',env['base_url']+'/console/api/apps?page=1&limit=1'),'expired boundary')
    b=fresh();b.phase='original_cases'
    _expect_no_send(b,httpx.Request('POST',env['base_url']+'/console/api/login',json={'email':'public@example.invalid','password':'public','remember_me':False}),'login outside reconnect')
    b=fresh()
    _expect_no_send(b,httpx.Request('POST','https://api.deepseek.com/v1/chat/completions',json={'model':'deepseek-flash'}),'model URL')
    b=fresh()
    _expect_no_send(b,httpx.Request('GET',env['base_url']+'/console/api/apps/'+old_app+'/messages/'+str(uuid4())),'old App read')
    b=fresh();b.version='original';b.phase='original_cases';b.case_index=5;b.current=app
    b.apps[app]={'version':'original','published':True,'unpublished':False,'publish_started':True,'key_started':True,'key':'app-PUBLIC-394','service_count':6,'last_cid':last}
    body={'inputs':{},'query':'follow','response_mode':'blocking','conversation_id':str(uuid4()),'user':'flowcraft-local'}
    _expect_no_send(b,httpx.Request('POST',env['base_url']+'/v1/chat-messages',json=body,headers={'authorization':'Bearer app-PUBLIC-394'}),'cross-session turn')
    b=fresh();b.version='original';b.phase='original_cases';b.case_index=0;b.current=app
    b.apps[app]={'version':'original','published':True,'unpublished':False,'publish_started':True,'key_started':True,'key':'app-PUBLIC-394','service_count':1,'last_cid':None}
    body={'inputs':{},'query':'q1','response_mode':'blocking','user':'flowcraft-local'}
    _expect_no_send(b,httpx.Request('POST',env['base_url']+'/v1/chat-messages',json=body,headers={'authorization':'Bearer app-PUBLIC-394'}),'duplicate Service')
    b=fresh();b.version='original';b.phase='original_publish';b.current=app
    b.apps[app]={'version':'original','published':None,'unpublished':False,'publish_started':False,'key_started':False,'key':None,'service_count':0,'last_cid':None}
    calls=[]
    async def wrong_send(req):
        calls.append(req)
        return _response({'id':str(uuid4()),'graph':{'nodes':[{'id':'n1','data':{'type':'start','title':'公开合成错图'}}],'edges':[]}})
    try:asyncio.run(b.dispatch(wrong_send,httpx.Request('GET',env['base_url']+'/console/api/apps/'+app+'/workflows/publish')))
    except RuntimeError as exc:assert 'Remote draft/published graph differs' in str(exc),str(exc)
    else:raise AssertionError('wrong publish graph was accepted')
    assert len(calls)==1 and b.halted

def test_boundary_source_and_resource_gates():
    env,fixture,contract,old_app,app,last=_gate_state()
    def state(verified=True,version='original',phase='original_cases',case=1,count=1,current=None):
        b=_gate(env,fixture,contract,old_app,source_verified=verified)
        b.version=version;b.phase=phase;b.case_index=case;b.current=current or app
        b.apps[b.current]={'version':'original' if version=='original' else 'modified','published':True,'unpublished':False,
                           'publish_started':True,'key_started':True,'key':'app-PUBLIC-394','service_count':count,'last_cid':last}
        return b
    def chat(query='q2'):
        return httpx.Request('POST',env['base_url']+'/v1/chat-messages',
            json={'inputs':{},'query':query,'response_mode':'blocking','user':'flowcraft-local'},headers={'authorization':'Bearer app-PUBLIC-394'})
    _expect_no_send(state(verified=False),chat(),'Service before the first saved native source is verified')
    assert state().admit(chat())['kind']=='run'
    _expect_no_send(state(phase='original_import'),httpx.Request('POST',env['base_url']+'/console/api/apps/imports',
        json={'mode':'yaml-content','yaml_content':'public','name':'公开合成'}),'original import')
    _expect_no_send(state(phase='original_publish'),httpx.Request('POST',env['base_url']+f'/console/api/apps/{app}/workflows/publish',
        json={'marked_name':'公开','marked_comment':'公开'}),'original publish')
    _expect_no_send(state(phase='original_key'),httpx.Request('POST',env['base_url']+f'/console/api/apps/{app}/api-keys',json={}),'original key')
    _expect_no_send(state(version='modified',phase='modified_cases',current=app),chat(),'modified version on reused App')
    new_app=str(uuid4())
    _expect_no_send(state(verified=False,version='modified',phase='modified_cases',case=0,count=0,current=new_app),chat('q1'),'modified Service before the first saved native source is verified')
    assert state(verified=True,version='modified',phase='modified_cases',case=0,count=0,current=new_app).admit(chat('q1'))['kind']=='run'

def test_known_apps_includes_run_history():
    with tempfile.TemporaryDirectory() as tmp:
        from app.storage import Store
        run_app,result_app,top_app=str(uuid4()),str(uuid4()),str(uuid4())
        store=Store(Path(tmp))
        store.put('task','public-task',{'id':'public-task','runs':[{'app_id':run_app,'result':{'app_id':result_app}}]})
        store.put('environment',str(uuid4()),{'id':'public-env','app_id':top_app})
        found=tool.known_apps(Path(tmp))
        assert {run_app,result_app,top_app}<=found

def test_fixed_source_reuse():
    result=tool.verify_fixed_reuse(ROOT)
    assert result['matched'] is True and set(result)==set(tool.PINS)|{'matched','393-helper'}
    assert len(result['386-boundary']['394_suffix_sha256'])==64 and result['386-boundary']['394_suffix_sha256']!=result['386-boundary']['derived_sha256']
    boundary='tools/reviewed-remaining394/boundary.py';journey_path='tools/reviewed-remaining394/journey.py'
    bad={boundary:(ROOT/boundary).read_bytes()+b'\n# public hand edit\n'}
    rejected(lambda:tool.verify_fixed_reuse(ROOT,files=bad),'hand-edited boundary')
    bad={boundary:(ROOT/boundary).read_bytes().replace(b"self.source_verified is True",b"self.source_verified is False")}
    rejected(lambda:tool.verify_fixed_reuse(ROOT,files=bad),'hand-edited boundary gate')
    bad={boundary:(ROOT/boundary).read_bytes().replace(b"class ReviewedBoundary(Boundary):",b"class ReviewedBoundary(Boundary,object):")}
    rejected(lambda:tool.verify_fixed_reuse(ROOT,files=bad),'hand-edited boundary suffix')
    # The frozen 374 functions are the reuse contract here; the remaining reviewed
    # journey code is bound to Git by verify_source at prepare/validate, not by this
    # fragment check.  Edit a pinned function to exercise that refusal.
    bad={journey_path:(ROOT/journey_path).read_bytes().replace(b"'Failure report already attempted'",b"'Failure report already attempted again'")}
    rejected(lambda:tool.verify_fixed_reuse(ROOT,files=bad),'hand-edited journey')
    helper='tools/reviewed-remaining394/reviewed_diagnostic_redaction.py'
    bad={helper:(ROOT/helper).read_bytes().replace(b'MAX_READS_CEILING = 14',b'MAX_READS_CEILING = 15')}
    rejected(lambda:tool.verify_fixed_reuse(ROOT,files=bad),'hand-edited helper')

def _write(path,value):path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value,'utf-8')
def _package_gate(project):
    project=Path(project);batch=tool.BATCH;src=project/'tools'/batch
    for name in tool.SOURCE_FILES:_write(src/name,'public '+name+'\n')
    subprocess.run(['git','init'],cwd=project,capture_output=True,check=True)
    subprocess.run(['git','add','.'],cwd=project,capture_output=True,check=True)
    subprocess.run(['git','-c','user.email=public@example.invalid','-c','user.name=public','commit','-m','public'],cwd=project,capture_output=True,check=True)
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=project,capture_output=True,check=True).stdout.decode().strip()
    sources=tool.verify_source(project,commit);root=project/'work'/batch;root.mkdir(parents=True)
    for name in tool.SOURCE_FILES:_write(root/name,(src/name).read_text('utf-8'))
    _write(project/tool.ROOT_PLAN,json.dumps({'isolated_paths':{label:rel for label,rel in tool.ROOT_PATHS.items() if label!='data'}}))
    from app.storage import Store
    for label,rel in tool.ROOT_PATHS.items():
        folder=project/rel;folder.mkdir(parents=True,exist_ok=True);store=Store(folder)
        store.put('task','task-'+label,{'id':'task-'+label,'label':label})
        store.put_with_secrets('environment','env-'+label,{'id':'env-'+label,'label':label},{'console_token':'TOKEN-'+label})
        _write(folder/'asset.txt','asset-'+label)
        _write(folder/'nested/server.pid','nested-'+label)
    roots=tool.capture_roots(project)
    old_files={}
    for i in range(tool.OLD_892_COUNT):
        rel=f'sealed892/{i:03d}.txt';_write(project/rel,str(i));old_files[rel]=tool.sha(project/rel)
    _write(project/tool.OLD_892_PATH,json.dumps(old_files,ensure_ascii=False))
    members={'protected-892.json':tool.sha(project/tool.OLD_892_PATH)}
    for i in range(tool.SEAL_MEMBER_COUNT-1):
        rel=f'member-{i}.txt';_write(project/'work/isolated-modification385'/rel,'seal-'+str(i));members[rel]=tool.sha(project/'work/isolated-modification385'/rel)
    _write(project/tool.SEAL_385_PATH,json.dumps(members,ensure_ascii=False));seal385_sha=tool.sha(project/tool.SEAL_385_PATH)
    seal391={}
    for i in range(tool.SEAL_391_MEMBER_COUNT):
        rel=f'work/reviewed-run391/member-{i}.txt';_write(project/rel,'seal391-'+str(i));seal391[rel]=tool.sha(project/rel)
    _write(project/tool.SEAL_391_PATH,json.dumps(seal391,ensure_ascii=False));seal391_sha=tool.sha(project/tool.SEAL_391_PATH)
    tool.SEAL_385_INDEX_SHA=seal385_sha;tool.SEAL_INDEX_SHA=seal391_sha
    protected=tool.verify_sealed(project)
    old,new=tool.NO_ANSWER_OLD,tool.NO_ANSWER_NEW
    original={'schema_version':1,'conversation_variables':[],'nodes':[
        {'id':'start','type':'start','config':{'variables':[]}},
        {'id':'retrieve','type':'knowledge-retrieval','config':{'query_variable_selector':['sys','query'],'dataset_source':'node','dataset_ids':['public-kb'],'top_k':3,'score_threshold':None,'reranking_enable':False}},
        {'id':'no_hit_text','type':'template-transform','config':{'template':old,'variables':[]}},
        {'id':'faq_llm','type':'llm','config':{'system_prompt':'前缀'+old+'后缀','user_prompt':'{{#sys.query#}}'}},
        {'id':'answer','type':'answer','config':{'answer':'{{#faq_llm.text#}}'}}],
        'edges':[{'source':'start','target':'retrieve'},{'source':'retrieve','target':'no_hit_text'},{'source':'no_hit_text','target':'faq_llm'},{'source':'faq_llm','target':'answer'}]}
    modified=copy.deepcopy(original);modified['nodes'][2]['config']['template']=new;modified['nodes'][3]['config']['system_prompt']='前缀'+new+'后缀'
    requirements={'goal':'公开双版平台核对','audience':'公开合成用户','input':'query文字','output':'无答案固定文案：'+old,
                  'rules':'只按本批已审图运行；不改期望','knowledge':'不适用','exceptions':'技术失败停止','tests':'六例七轮'}
    cases=[{'id':f'case{i}','name':f'样例{i}','input':{'query':f'公开问题{i}'},'expectation':{'mode':'equals','target':'answer','expected':(old if i==2 else '答案'+str(i))},'required':True} for i in range(1,7)]
    cases[5]['followups']=[{'input':{'query':'公开续问'},'expectation':{'mode':'equals','target':'answer','expected':'续答'}}]
    config={'dify_model_provider':'public/provider','dify_model':'public-model','temperature':tool.MODEL_TEMPERATURE,
            'max_tokens':tool.MODEL_MAX_TOKENS,'model_parameters':{'thinking':tool.MODEL_THINKING},'assistant_provider_id':str(uuid4())}
    first_run={'id':tool.EXISTING_FIRST_RUN,'kind':'run','revision':8,'environment_id':tool.ENVIRONMENT_ID,'status':'success','app_id':tool.EXISTING_APP_ID,
               'app_type':'advanced-chat','environment_binding':'a'*64,'result':{'message_id':tool.EXISTING_MESSAGE,'conversation_id':tool.EXISTING_SESSION},'evaluation':{'status':'passed'}}
    task={'id':tool.TASK_ID,'name':'公开剩余平台任务','app_type':'advanced-chat','environment_id':tool.ENVIRONMENT_ID,'revision':8,'plan_source':'manual','status':'run_completed',
          'requirements_confirmed':True,'configuration_confirmed':True,'dify_app_id':tool.EXISTING_APP_ID,
          'runs':[{'id':tool.EXISTING_IMPORT_RUN,'kind':'import','status':'success','result':{'app_id':tool.EXISTING_APP_ID}},
                  {'id':tool.EXISTING_PUBLISH_RUN,'kind':'publish','status':'success','result':{'app_id':tool.EXISTING_APP_ID}},
                  first_run],
          'requirements':requirements,'test_cases':cases,'configuration':config,'workflow_plan':original}
    env={'id':tool.ENVIRONMENT_ID,'base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':tool.WORKSPACE_ID,'service_app_id':tool.EXISTING_APP_ID}
    budget={'id':tool.TASK_ID,'policy_revision':1,'limit_usd':'0.600','entries':[
        {'id':str(uuid4()),'operation_id':str(uuid4()),'revision':8,'kind':'plan','provider_id':'synthetic-provider','model':'synthetic','pricing':{},'reserved_usd':'0.001','charged_usd':'0.001','status':'settled','call_status':'returned','cost_basis':'reported_usage','usage':{'completion_tokens':1},'policy_revision':1} for _ in range(5)],
        'policy_history':[],'excluded_history_present':False,'scope':'since_ledger_start','created_at':tool.now()}
    expectations={case['id']:{'1':{'must':['start'],'must_not':[]}} for case in cases}
    expectations[cases[5]['id']]['2']={'must':['start'],'must_not':[]}
    tool.ORIGINAL_GRAPH_SHA=tool.digest(original);tool.MODIFIED_GRAPH_SHA=tool.digest(modified)
    candidate_path=project/tool.FIXED_CANDIDATE_PATH;_write(candidate_path,json.dumps(modified,ensure_ascii=False))
    modified_requirements={**requirements,'output':requirements['output'].replace(old,new)}
    topic_answers={'original':_public_topic_answers(task,original,requirements),'modified':_public_topic_answers(task,modified,modified_requirements)}
    provider_id=config['assistant_provider_id']
    scope={'provider_id':provider_id,'purpose':tool.DIAGNOSTIC_PURPOSE,'memory_only':True,'model_calls':0,'max_reads':tool.DIAGNOSTIC_MAX_READS}
    review={'schema_version':1,'batch_id':batch,'task_id':tool.TASK_ID,'environment_id':tool.ENVIRONMENT_ID,
            'review_authority':'standing_delegated_content_review','actor':tool.REVIEW_ACTOR,'human_signoff':False,'decision':'proceed',
            'task_sha256':tool.digest(task),'budget_sha256':tool.digest(budget),'environment_sha256':tool.digest(env),'cases_sha256':tool.digest(cases),
            'existing_app_id':tool.EXISTING_APP_ID,'first_run_sha256':tool.run_source_hash(first_run),
            'original_plan_sha256':tool.ORIGINAL_GRAPH_SHA,'modified_plan_sha256':tool.MODIFIED_GRAPH_SHA,
            'diagnostic_scope':scope,'diagnostic_provider_sha256':'a'*64,'diagnostic_key_cipher_sha256':'b'*64,
            'topic_answers':topic_answers,'trace_expectations':expectations}
    fixture,contract,candidate=tool.reviewed_inputs(project,task,budget,env,review,backend=BACKEND)
    reviewed={'original_plan':original,'modified_plan':modified,'cases':cases,'trace_expectations':expectations,
              'fixture':fixture,'contract':contract,
              'original_native_sha256':tool.digest(contract['original']['native']),'original_core_sha256':tool.digest(contract['original']['core']),
              'modified_native_sha256':tool.digest(contract['modified']['native']),'modified_core_sha256':tool.digest(contract['modified']['core']),
              'source':'original=existing successful first-case r8 App reused without re-dispatch; modified=385 candidate + 388 manual save',
              'task_sha256':review['task_sha256'],'budget_sha256':review['budget_sha256']}
    _write(root/'reviewed.json',json.dumps(reviewed,ensure_ascii=False));_write(root/'protected.json',json.dumps(protected,ensure_ascii=False))
    existing={'app_id':tool.EXISTING_APP_ID,'import_run_id':tool.EXISTING_IMPORT_RUN,'publish_run_id':tool.EXISTING_PUBLISH_RUN,
              'first_run_id':tool.EXISTING_FIRST_RUN,'message_id':tool.EXISTING_MESSAGE,'conversation_id':tool.EXISTING_SESSION,
              'first_run_sha256':tool.run_source_hash(first_run),'provider_id':provider_id,'provider_sha256':'a'*64,'key_cipher_sha256':'b'*64,
              'execution_limits_sha256':'c'*64,'known_apps_contains':True}
    plan={'schema_version':1,'batch_id':batch,'source_commit':commit,'source_files':sources['files'],'pins':tool.PINS,
          'task_id':tool.TASK_ID,'task_revision':8,'environment_id':tool.ENVIRONMENT_ID,'workspace_id':tool.WORKSPACE_ID,
          'environment_sha256':review['environment_sha256'],'task_sha256':review['task_sha256'],'budget_sha256':review['budget_sha256'],
          'existing_source':existing,'diagnostic_scope':scope,'diagnostic_provider_sha256':'a'*64,'diagnostic_key_cipher_sha256':'b'*64,
          'original_plan_sha256':tool.ORIGINAL_GRAPH_SHA,'modified_plan_sha256':tool.MODIFIED_GRAPH_SHA,
          'original_graph_sha256':tool.ORIGINAL_GRAPH_SHA,'modified_graph_sha256':tool.MODIFIED_GRAPH_SHA,
          'original_native_sha256':tool.digest(contract['original']['native']),'original_core_sha256':tool.digest(contract['original']['core']),
          'modified_native_sha256':tool.digest(contract['modified']['native']),'modified_core_sha256':tool.digest(contract['modified']['core']),
          'fixture_sha256':tool.digest(fixture),'contract_sha256':tool.digest(contract),
          'topic_answers_sha256':tool.digest(contract['topic_answers']),
          'original_requirements_sha256':tool.digest(requirements),'original_cases_sha256':tool.digest(cases),
          'trace_expectations_sha256':tool.digest(expectations),
          'compile':{'task_id':tool.TASK_ID,'task_name':task['name'],'app_type':'advanced-chat','configuration':config,'messages':copy.deepcopy(task.get('messages',[]))},
          'limits':tool.LIMITS,'current_upper':tool.CURRENT_UPPER,'proposed_upper':tool.PROPOSED_UPPER,'model_estimate_book_upper_usd':tool.MODEL_BOOK,
          'estimated_new_dify_usd':tool.DIFY_ESTIMATE,'dify_is_billing_limit':False,'host_cost_known':False,'wall_seconds':tool.WALL_SECONDS,
          'old_reservations_preserved':True,'new_model_calls':0,'new_tasks':0,'new_libraries':0,
          'execution_policy':tool.EXECUTION_POLICY,'failure_policy':tool.FAILURE_POLICY,'failure_exception':tool.FAILURE_POLICY,
          'approval_phrase':tool.APPROVAL_PHRASE,'old_refs':list(tool.OLD_REFS),'protected':protected,'protected_sha256':tool.digest(protected),
          'root_paths':dict(tool.ROOT_PATHS),'roots':roots,'roots_sha256':tool.digest({'paths':tool.ROOT_PATHS,'roots':roots}),
          'runtime':{'build':tool.RUNTIME_BUILD,'version':tool.RUNTIME_VERSION,'file_count':tool.RUNTIME_FILE_COUNT,'backend_path':str(tool.RUNTIME_BACKEND),'manifest_sha256':'d'*64},
          'reviewed_files':{'reviewed.json':tool.sha(root/'reviewed.json'),'protected.json':tool.sha(root/'protected.json')},
          'fixture':fixture,'contract':contract}
    tool.atomic_json(root/'plan.json',plan)
    manifest={'schema_version':1,'batch_id':batch,'plan_sha256':tool.sha(root/'plan.json'),'files':{name:tool.sha(root/name) for name in tool.PACKAGE_FILES}}
    tool.atomic_json(root/'manifest.json',manifest)
    auth={'schema_version':1,'batch_id':batch,'authorization_source':'direct_user_reply','scope':batch,'question_ref':'call_'+'e'*32+'/q0',
          'literal':tool.APPROVAL_PHRASE,'plan_sha256':tool.sha(root/'plan.json'),'manifest_sha256':tool.sha(root/'manifest.json'),
          'limits':tool.LIMITS,'failure_policy':tool.FAILURE_POLICY,'execution_policy':tool.EXECUTION_POLICY,'wall_seconds':tool.WALL_SECONDS,
          'dify_estimate':tool.DIFY_ESTIMATE,'dify_is_billing_limit':False,'host_cost_known':False,'current_upper':tool.CURRENT_UPPER,
          'proposed_upper':tool.PROPOSED_UPPER,'old_reservations_preserved':True,'new_model_calls':0,'new_tasks':0,'new_libraries':0,
          'only_new_login':True,'failure_exception':tool.FAILURE_POLICY,'single_use':True,'retry':False,
          'diagnostic_scope':scope,'diagnostic_provider_sha256':'a'*64,'diagnostic_key_cipher_sha256':'b'*64,'created_at':tool.now()}
    tool.atomic_json(root/'approval.json',auth)
    return project,root,plan,manifest,auth,protected,reviewed,task,budget,review,env

def test_package_and_approval_gates():
    with tempfile.TemporaryDirectory() as tmp:
        anchors=(tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA);seal_anchors=(tool.SEAL_INDEX_SHA,tool.SEAL_385_INDEX_SHA)
        project,root,plan,manifest,auth,protected,reviewed,task,budget,review,env=_package_gate(tmp)
        try:
            tool.validate_package(project,root,backend=BACKEND)
            tool.validate_approval(root,auth,plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json'))
            tool.preflight_run(project,root,backend=BACKEND)
            bad={k:v for k,v in auth.items() if k not in {'diagnostic_scope','diagnostic_provider_sha256','diagnostic_key_cipher_sha256'}}
            tool.atomic_json(root/'approval.json',bad);rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'missing diagnostic approval');tool.atomic_json(root/'approval.json',auth)
            rejected(lambda:tool.validate_approval(root,{**auth,'limits':{**tool.LIMITS,'login':True}},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'bool limit')
            rejected(lambda:tool.validate_approval(root,{**auth,'question_ref':tool.OLD_REFS[0]},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'old ref')
            rejected(lambda:tool.validate_approval(root,{**auth,'diagnostic_scope':{**auth['diagnostic_scope'],'max_reads':13}},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'wrong diagnostic scope')
            rejected(lambda:tool.validate_approval(root,{**auth,'diagnostic_provider_sha256':'f'*64},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'wrong provider binding')
            bad_plan=copy.deepcopy(plan);bad_plan['diagnostic_scope']['max_reads']=15;tool.atomic_json(root/'plan.json',bad_plan);bad_manifest=copy.deepcopy(manifest);bad_manifest['plan_sha256']=tool.sha(root/'plan.json');bad_manifest['files']['plan.json']=bad_manifest['plan_sha256'];tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'plan wrong diagnostic scope');tool.atomic_json(root/'plan.json',plan);tool.atomic_json(root/'manifest.json',manifest)
            bad_plan=copy.deepcopy(plan);bad_plan['existing_source']['app_id']=str(uuid4());tool.atomic_json(root/'plan.json',bad_plan);bad_manifest=copy.deepcopy(manifest);bad_manifest['plan_sha256']=tool.sha(root/'plan.json');bad_manifest['files']['plan.json']=bad_manifest['plan_sha256'];tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'wrong existing app');tool.atomic_json(root/'plan.json',plan);tool.atomic_json(root/'manifest.json',manifest)
            bad_manifest=copy.deepcopy(manifest);bad_manifest['files']['extra.py']='f'*64;tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'extra member');tool.atomic_json(root/'manifest.json',manifest)
            _write(root/'extra.py','extra');rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'extra package file');(root/'extra.py').unlink()
            seal_bytes=(project/tool.SEAL_391_PATH).read_bytes();_write(project/tool.SEAL_391_PATH,'{}');rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'391 seal tamper');(project/tool.SEAL_391_PATH).write_bytes(seal_bytes)
            old_bytes=(project/tool.OLD_892_PATH).read_bytes();_write(project/tool.OLD_892_PATH,'{}');rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'old 892 tamper');(project/tool.OLD_892_PATH).write_bytes(old_bytes)
            tool.atomic_json(root/'attempt.json',{'state':'admitted'});rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'reused state');(root/'attempt.json').unlink()
            (root/'live-output').mkdir();rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'live output');(root/'live-output').rmdir()
            bad_plan=copy.deepcopy(plan);bad_plan['runtime']['build']='0.999.0';tool.atomic_json(root/'plan.json',bad_plan);bad_manifest=copy.deepcopy(manifest);bad_manifest['plan_sha256']=tool.sha(root/'plan.json');bad_manifest['files']['plan.json']=bad_manifest['plan_sha256'];tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'wrong runtime');tool.atomic_json(root/'plan.json',plan);tool.atomic_json(root/'manifest.json',manifest)
            bad_plan=copy.deepcopy(plan);bad_plan['root_paths']['391']=tool.ROOT_PATHS['394'];tool.atomic_json(root/'plan.json',bad_plan);bad_manifest=copy.deepcopy(manifest);bad_manifest['plan_sha256']=tool.sha(root/'plan.json');bad_manifest['files']['plan.json']=bad_manifest['plan_sha256'];tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'same-count root replacement');tool.atomic_json(root/'plan.json',plan);tool.atomic_json(root/'manifest.json',manifest)
            bad_roots=copy.deepcopy(plan);bad_roots['roots']['391']=copy.deepcopy(plan['roots']['394']);bad_roots['roots']['391']['path']=tool.ROOT_PATHS['391']
            rejected(lambda:tool.verify_roots_protected(project,bad_roots),'same-count root snapshot replacement')
            _write(project/tool.ROOT_PLAN,json.dumps({'isolated_paths':{'391':tool.ROOT_PATHS['394']}}));rejected(lambda:tool.verify_root_paths(project),'375 root plan replacement')
            def wrong_plan(mutate,label):
                value=copy.deepcopy(plan);mutate(value);tool.atomic_json(root/'plan.json',value)
                changed=copy.deepcopy(manifest);changed['plan_sha256']=tool.sha(root/'plan.json');changed['files']['plan.json']=changed['plan_sha256'];tool.atomic_json(root/'manifest.json',changed)
                rejected(lambda:tool.validate_package(project,root,backend=BACKEND),label)
                tool.atomic_json(root/'plan.json',plan);tool.atomic_json(root/'manifest.json',manifest)
            wrong_plan(lambda value:value['existing_source'].update(message_id=str(uuid4())),'wrong existing message')
            wrong_plan(lambda value:value['existing_source'].update(conversation_id=str(uuid4())),'wrong existing conversation')
            wrong_plan(lambda value:value['existing_source'].update(first_run_id=str(uuid4())),'wrong existing first run')
            wrong_plan(lambda value:value['existing_source'].update(import_run_id=str(uuid4())),'wrong existing import run')
            wrong_plan(lambda value:value['existing_source'].update(publish_run_id=str(uuid4())),'wrong existing publish run')
            wrong_plan(lambda value:value['existing_source'].update(first_run_sha256='f'*63),'invalid existing source hash')
            wrong_plan(lambda value:value['existing_source'].update(provider_id=str(uuid4())),'wrong existing provider')
            wrong_plan(lambda value:value.update(task_revision=7),'wrong task revision')
            wrong_plan(lambda value:value.update(workspace_id=str(uuid4())),'wrong workspace')
            wrong_plan(lambda value:value.update(original_graph_sha256='e'*64),'wrong original graph anchor')
            wrong_plan(lambda value:value.update(modified_plan_sha256='e'*64),'wrong modified graph anchor')
            wrong_plan(lambda value:value.update(diagnostic_scope=None),'missing diagnostic plan scope')
            wrong_plan(lambda value:value['source_files'].__setitem__(next(iter(value['source_files'])),'f'*64),'source file drift')
            assert 'call_90ac87674e9a4a4eb0fc35ea048b5314/q0' in tool.OLD_REFS,'old 391 ref missing'
            rejected(lambda:tool.validate_approval(root,{**auth,'question_ref':'call_90ac87674e9a4a4eb0fc35ea048b5314/q0'},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'old 391 approval ref')
            rejected(lambda:tool.validate_approval(root,{**auth,'scope':'reviewed-remaining391'},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'old 391 approval scope')
            rejected(lambda:tool.validate_approval(root,{**auth,'literal':'允许将391未派发资源复用','plan_sha256':tool.sha(root/'plan.json'),'manifest_sha256':tool.sha(root/'manifest.json')},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'old approval literal')
            rejected(lambda:tool.validate_approval(root,{**auth,'diagnostic_scope':None},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'missing approval diagnostic scope')
            rejected(lambda:tool.validate_approval(root,{**auth,'diagnostic_scope':{**auth['diagnostic_scope'],'provider_id':str(uuid4())}},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'wrong approval diagnostic provider')
            rejected(lambda:tool.safe_path(project,'../outside'),'path escape')
        finally:
            tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA=anchors;tool.SEAL_INDEX_SHA,tool.SEAL_385_INDEX_SHA=seal_anchors

def _guard_store(tmp):
    from app.storage import Store
    data=Path(tmp)/'guard-data';base=Store(data)
    owner,env_id,workspace=str(uuid4()),str(uuid4()),str(uuid4())
    old_text=tool.NO_ANSWER_OLD;new_text=tool.NO_ANSWER_NEW
    requirements={'goal':'公开守卫','audience':'公开用户','input':'query','output':old_text,'rules':'只按已审图','knowledge':'不适用','exceptions':'停止','tests':'一例'}
    modified_requirements={**requirements,'output':new_text}
    cases=[{'id':'case1','name':'公开样例','input':{'query':'q'},'expectation':{'mode':'equals','target':'answer','expected':old_text},'required':True}]
    modified_cases=copy.deepcopy(cases);modified_cases[0]['expectation']['expected']=new_text
    plan={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[]}},
          {'id':'no_hit_text','type':'template-transform','config':{'template':old_text,'variables':[]}},
          {'id':'answer','type':'answer','config':{'answer':'{{#no_hit_text.output#}}'}}],
          'edges':[{'source':'start','target':'no_hit_text'},{'source':'no_hit_text','target':'answer'}]}
    modified_plan=copy.deepcopy(plan);modified_plan['nodes'][1]['config']['template']=new_text
    timestamp='2026-11-28T00:00:00+00:00'
    env={'id':env_id,'base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':workspace,'service_app_id':None,'capabilities':{}}
    first={'id':tool.EXISTING_FIRST_RUN,'kind':'run','revision':8,'environment_id':env_id,'status':'success','app_id':str(uuid4()),'app_type':'advanced-chat',
           'environment_binding':'c'*64,'result':{'message_id':str(uuid4()),'conversation_id':str(uuid4())},'evaluation':{'status':'passed'}}
    task={'id':owner,'name':'公开守卫任务','app_type':'advanced-chat','environment_id':env_id,'revision':8,'status':'run_completed',
          'requirements':requirements,'requirements_confirmed':True,'configuration':{'dify_model_provider':'public/provider','dify_model':'public-model'},
          'configuration_confirmed':True,'materials':[],'test_cases':cases,'workflow_plan':plan,'plan_source':'manual','plan_stale':False,
          'artifact':{'revision':8,'sha256':'a'*64},'dify_app_id':first['app_id'],
          'messages':[{'role':'assistant','source':'system','content':'旧系统消息','created_at':timestamp}],
          'versions':[{'id':'v-old','revision':7,'label':'旧快照','created_at':timestamp}],
          'confirmations':[{'kind':'requirements','revision':7,'created_at':timestamp}],
          'intake_history':[],'intake_review':{'review':{'schema_version':1,'checks':[]},'source':'user_declared','created_at':timestamp},
          'runs':[first],'planning_runs':[],'created_at':timestamp,'updated_at':timestamp}
    budget={'id':owner,'policy_revision':1,'limit_usd':'0.600','created_at':timestamp,'excluded_history_present':False,
            'scope':'since_ledger_start','policy_history':[],'entries':[
        {'id':f'entry-{i}','operation_id':f'op-{i}','revision':8,'kind':'plan','provider_id':'public-provider','model':'public-model',
         'pricing':{},'reserved_usd':'0.001','charged_usd':'0.001','status':'settled','call_status':'returned','cost_basis':'reported_usage','usage':{'completion_tokens':1},'attempts':0,'policy_revision':1} for i in range(5)]}
    limits={'id':owner,'policy_revision':1,'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None,'updated_at':timestamp,
            'history':[{'before':{'max_started_runs':None,'max_total_minutes':None,'max_reported_cost_usd':None},'after':{'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None},'note':'公开已有策略','created_at':timestamp,'source':'user'}]}
    base.put('task',owner,task);base.put('task_budget',owner,budget);base.put('execution_limits',owner,limits)
    initial_task=base.get('task',owner);initial_budget=base.get('task_budget',owner);initial_limits=base.get('execution_limits',owner)
    contract={'original':{'plan':plan,'requirements':requirements,'cases':cases},
              'modified':{'plan':modified_plan,'requirements':modified_requirements,'cases':modified_cases}}
    class PublicBoundary:pass
    boundary=PublicBoundary();boundary.owner=owner;boundary.apps={first['app_id']};boundary.current=None
    old=tool.capture(data)
    Guarded=guarded(Store,env,contract,boundary,old,initial_task,initial_budget,initial_limits=initial_limits,first_run_id=tool.EXISTING_FIRST_RUN)
    return Guarded(data),initial_task,initial_budget,initial_limits,contract

def test_storage_guard_integrity():
    with tempfile.TemporaryDirectory() as tmp:
        g,initial_task,initial_budget,initial_limits,contract=_guard_store(tmp)
        owner=initial_task['id'];timestamp='2026-11-28T00:00:00+00:00'
        ok=copy.deepcopy(initial_task)
        ok['status']='ready';ok['messages'].append({'role':'assistant','source':'system','content':'正常新后缀','created_at':timestamp})
        ok['confirmations'].append({'kind':'configuration','revision':initial_task['revision'],'created_at':timestamp})
        ok['versions'].append({'id':'v-new','revision':initial_task['revision'],'label':'正常新快照','created_at':timestamp})
        g.put('task',owner,ok)
        allowed=copy.deepcopy(initial_task);allowed['requirements']=contract['modified']['requirements'];allowed['test_cases']=contract['modified']['cases'];allowed['workflow_plan']=contract['modified']['plan']
        g.put('task',owner,allowed)
        def bad_task(mutate,label):
            value=copy.deepcopy(initial_task);mutate(value);rejected(lambda:g.put('task',owner,value),label)
        def revision(value):value['confirmations'][0]['revision']=6
        bad_task(revision,'old confirmation revision')
        bad_task(lambda value:value['planning_runs'].append({'id':'new-model','status':'succeeded'}),'new planning run')
        bad_task(lambda value:value.update(workflow_plan=None),'erased workflow plan')
        bad_task(lambda value:value.update(id='other-task'),'task id')
        bad_task(lambda value:value.update(name='改名任务'),'task name')
        bad_task(lambda value:value.update(dify_app_id='not-an-app'),'wrong task app')
        bad_task(lambda value:value.update(configuration={'dify_model_provider':'other/provider','dify_model':'other-model'}),'configuration change')
        bad_task(lambda value:value.update(test_cases=[{'id':'case1','expected':'other'}]),'unreviewed cases')
        bad_task(lambda value:value['runs'][0].update(result={'tampered':True}),'existing run change')
        bad_task(lambda value:value['runs'][0].update(diagnostics=[{'run_id':tool.EXISTING_FIRST_RUN}]),'diagnostics without source binding')
        rejected(lambda:g.put('task','other-task',copy.deepcopy(initial_task)),'other task')
        rejected(lambda:g.delete('task',owner),'task delete')
        def bad_budget(mutate,label):
            value=copy.deepcopy(initial_budget);mutate(value);rejected(lambda:g.put('task_budget',owner,value),label)
        bad_budget(lambda value:value.update(limit_usd='0.700'),'budget metadata')
        bad_budget(lambda value:value.update(policy_revision=True),'budget bool revision')
        bad_budget(lambda value:value['entries'][0].update(charged_usd='0.002'),'budget entry value')
        bad_budget(lambda value:value['entries'].append(copy.deepcopy(value['entries'][0])),'new budget entry')
        rejected(lambda:g.put('task_budget','other-budget',copy.deepcopy(initial_budget)),'other budget')
        g.put('task_budget',owner,copy.deepcopy(initial_budget))
        changed=copy.deepcopy(initial_limits);changed['max_started_runs']=13;rejected(lambda:g.put('execution_limits',owner,changed),'existing policy changed')
        reset=copy.deepcopy(initial_limits);reset['max_started_runs']=None;rejected(lambda:g.put('execution_limits',owner,reset),'existing policy reset')
        g.put('execution_limits',owner,copy.deepcopy(initial_limits))
        # A real first-run diagnostics append with a matching source hash is allowed once and then stable.
        run_source=tool.run_source_hash(initial_task['runs'][0])
        report={'id':'d1','run_id':tool.EXISTING_FIRST_RUN,'source_hash':run_source,'app_id':initial_task['runs'][0]['app_id'],
                'source_revision':initial_task['runs'][0]['revision'],'environment_id':initial_task['runs'][0]['environment_id']}
        appended=copy.deepcopy(initial_task);appended['runs'][0]['diagnostics']=[copy.deepcopy(report)]
        g.put('task',owner,appended)
        g.put('task',owner,copy.deepcopy(appended))
        replaced=copy.deepcopy(appended);replaced['runs'][0]['diagnostics']=[{**report,'id':'d2'}];rejected(lambda:g.put('task',owner,replaced),'diagnostics replaced')
        second=copy.deepcopy(appended);second['runs'][0]['diagnostics'].append({**report,'id':'d3'});rejected(lambda:g.put('task',owner,second),'second diagnostics append')

def test_explicit_topic_answers():
    with tempfile.TemporaryDirectory() as tmp:
        anchors=(tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA);seal_anchors=(tool.SEAL_INDEX_SHA,tool.SEAL_385_INDEX_SHA)
        project,root,plan,manifest,auth,protected,reviewed,task,budget,review,env=_package_gate(tmp)
        try:
            def inputs(value=review):return tool.reviewed_inputs(project,task,budget,env,value,backend=BACKEND)
            def bad(mutate,label):
                value=copy.deepcopy(review);mutate(value);rejected(lambda:inputs(value),label)
            key=next(iter(review['topic_answers']['original']))
            bad(lambda value:value['topic_answers']['original'].pop(key),'missing topic answer')
            bad(lambda value:value['topic_answers']['original'].update(unknown_topic='公开未知主题说明'),'unknown topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:None}),'null topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:True}),'bool topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:'   '}),'blank topic answer')
            bad(lambda value:value.update(review_authority='human_signoff'),'human authority')
            bad(lambda value:value.update(actor='local_operator'),'human actor')
            bad(lambda value:value.update(human_signoff=True),'human signoff')
            bad(lambda value:value.update(diagnostic_scope={**value['diagnostic_scope'],'max_reads':15}),'wrong scope')
            bad(lambda value:value.update(diagnostic_scope={**value['diagnostic_scope'],'model_calls':1}),'model call scope')
            bad(lambda value:value.update(diagnostic_scope={**value['diagnostic_scope'],'provider_id':str(uuid4())}),'wrong provider scope')
        finally:
            tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA=anchors;tool.SEAL_INDEX_SHA,tool.SEAL_385_INDEX_SHA=seal_anchors

def test_strict_map_booleans():
    tool._strict_map(tool.FAILURE_POLICY,tool.FAILURE_POLICY,'failure policy');tool._strict_map(tool.EXECUTION_POLICY,tool.EXECUTION_POLICY,'execution policy')
    value={'truth':True,'falsehood':False,'count':1}
    tool._strict_map(value,value,'strict bool');assert value['truth'] is True and value['falsehood'] is False
    rejected(lambda:tool._strict_map({**tool.FAILURE_POLICY,'business_rule_failure_only':1},tool.FAILURE_POLICY,'failure policy'),'real int as bool')
    rejected(lambda:tool._strict_map({'truth':1,'falsehood':False,'count':1},value,'strict bool'),'int as true')
    rejected(lambda:tool._strict_map({'truth':True,'falsehood':False,'count':True},value,'strict bool'),'bool as int')

def test_runtime_process_identity():
    exe=str(tool.REAL_PROJECT/'.venv/Scripts/python.exe');backend=str(tool.RUNTIME_BACKEND)
    def q(value):return '"'+value+'"'
    command=q(exe)+' -m uvicorn app.main:app --app-dir '+q(backend)+' --host 127.0.0.1 --port 8765'
    tool._runtime_process_matches_command(exe,command,backend)
    rejected(lambda:tool._runtime_process_matches_command(exe,command.replace('127.0.0.1','0.0.0.0'),backend),'wrong runtime host')
    fake=q(exe)+' script.py uvicorn app.main:app --app-dir '+q(backend)+' --host 127.0.0.1 --port 8765'
    rejected(lambda:tool._runtime_process_matches_command(exe,fake,backend),'fake script signature')

def test_cli_refusal():
    with tempfile.TemporaryDirectory() as tmp:
        missing=Path(tmp)/'missing-project';r=subprocess.run([sys.executable,tool.__file__,'--project',str(missing),'run'],capture_output=True,text=True,timeout=30)
        out=r.stdout+r.stderr;assert r.returncode!=0 and 'stopped:' in out and 'Traceback' not in out and not missing.exists()

def main():
    test_full_synthetic_chain();print('ok full_synthetic_chain')
    test_unique_business_failure_bounded_capture();print('ok unique_business_failure_bounded_capture')
    test_second_turn_business_failure();print('ok second_turn_business_failure')
    test_service_technical_stops();print('ok service_technical_stops')
    test_service_technical_failure_after_first_case();print('ok service_technical_failure_after_first_case')
    test_diagnostic_identity_rejections();print('ok diagnostic_identity_rejections')
    test_existing_source_rejections();print('ok existing_source_rejections')
    test_existing_runs_prefix_binding();print('ok existing_runs_prefix_binding')
    test_inspect_existing_artifact_preconditions();print('ok inspect_existing_artifact_preconditions')
    test_diagnostic_scope_helper();print('ok diagnostic_scope_helper')
    test_failure_report_safety();print('ok failure_report_safety')
    test_trace_any_of();print('ok trace_any_of')
    test_boundary_rejections();print('ok boundary_rejections')
    test_boundary_source_and_resource_gates();print('ok boundary_source_and_resource_gates')
    test_known_apps_includes_run_history();print('ok known_apps_includes_run_history')
    test_fixed_source_reuse();print('ok fixed_source_reuse')
    test_package_and_approval_gates();print('ok package_and_approval_gates')
    test_storage_guard_integrity();print('ok storage_guard_integrity')
    test_explicit_topic_answers();print('ok explicit_topic_answers')
    test_strict_map_booleans();print('ok strict_map_booleans')
    test_runtime_process_identity();print('ok runtime_process_identity')
    test_cli_refusal();print('ok cli_refusal')
    print('reviewed-remaining394 public checks passed')
if __name__=='__main__':main()
