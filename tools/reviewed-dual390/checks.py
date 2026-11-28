"""Public isolated full-chain checks for reviewed-dual390; fake Dify only."""
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

class _Stream(httpx.AsyncByteStream):
    def __init__(self,body):self.body=body
    async def __aiter__(self):yield self.body
def _response(value,status=200,headers=()):
    return httpx.Response(status,headers=[('content-type','application/json'),*headers],stream=_Stream(json.dumps(value,ensure_ascii=False).encode()))

def _raw(body,status=200):
    return httpx.Response(status,headers=[('content-type','application/json')],content=body)
class FakeDify:
    def __init__(self,b,fail_case=None,fail_turn=None,fail_mode=None,mismatch=None,fail_nodes=(),omit_nodes=()):
        self.b=b;self.fail_case=fail_case;self.fail_turn=fail_turn;self.fail_mode=fail_mode;self.mismatch=mismatch
        self.fail_nodes=set(fail_nodes);self.omit_nodes=set(omit_nodes);self.apps={};self.messages={};self.runs={}
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
        if path=='/v1/chat-messages':
            if self.fail_mode=='invalid_json':return _raw(b'not-json')
            if self.fail_mode=='http_500':return _response({'error':'公开合成技术失败'},500)
            if self.fail_mode=='transport':raise httpx.ConnectError('公开合成传输失败',request=request)
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
PUBLIC_TOPIC_EXTRA=PUBLIC_TOPIC_ANSWERS
def _public_topic_answers(task,plan,requirements):
    from app.intake import BASE,topics
    answers={}
    for row in topics({**task,'workflow_plan':plan,'requirements':requirements}):
        key=row['id']
        answers[key]=requirements[key] if key in BASE else PUBLIC_TOPIC_ANSWERS[key]
    return answers

def _setup(tmp,fail_case=None,fail_turn=None,fail_mode=None,mismatch=None,fail_nodes=(),omit_nodes=(),expectations_override=None,expected_stop=False):
    os.environ['FLOWCRAFT_DATA_DIR']=str(Path(tmp)/'data')
    from app import main as h
    from app.storage import Store
    from app.dsl_roundtrip import parse
    from app.workflow_publication import core
    data=Path(tmp)/'data';source=Store(data)
    env_id=str(uuid4());workspace=str(uuid4());old_app=str(uuid4())
    env={'id':env_id,'name':'公开合成Dify','base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':workspace,
         'console_login_binding':{'base_url':'https://public-dify.invalid','version':'1.17.1','workspace_id':workspace},
         'service_app_id':old_app,'connection_revision':str(uuid4()),'capabilities':{'console':'verified','datasets':'untested','runtime':'verified'}}
    source.put_with_secrets('environment',env_id,env,{'console_token':'PUBLIC_CONSOLE','csrf_token':'PUBLIC_CSRF','service_api_key':'app-PUBLIC-OLD','console_login_email':'public@example.invalid','console_login_password':'PUBLIC_ONLY'})
    h.store=source;h.DATA_ROOT=data
    old='知识库暂无相关信息，请联系人工客服。';new='知识库暂无相关信息，请联系人工客服并提供商品型号。'
    requirements={'goal':'公开双版平台核对','audience':'公开合成用户','input':'query文字','output':'无答案固定文案：'+old,
                  'rules':'只按本批已审图运行；不改期望','knowledge':'不适用','exceptions':'技术失败停止','tests':'六例七轮'}
    cases=[{'id':f'case{i}','name':f'样例{i}','input':{'query':f'公开问题{i}'},'expectation':{'mode':'equals','target':'answer','expected':(old if i==2 else '答案'+str(i))},'required':True} for i in range(1,7)]
    cases[5]['followups']=[{'input':{'query':'公开续问'},'expectation':{'mode':'equals','target':'answer','expected':'续答'}}]
    config=copy.deepcopy(h.CONFIG_DEFAULT);config.update(dify_model_provider='deepseek',dify_model='deepseek-flash',resource_plan='仅公开本机合成平台核对，不新建Task/库/模型。')
    from fastapi.testclient import TestClient
    with TestClient(h.app) as api:
        task=_api_call(api,'POST','/api/tasks',{'name':'公开双版平台任务','app_type':'advanced-chat','environment_id':env_id})
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
        source.put('task_budget',tid,budget);source.put('task','other-public-task',{'id':'other-public-task','name':'其它公开任务','app_type':'workflow','revision':1,'status':'requirements','requirements':{},'configuration':{},'materials':[],'messages':[],'versions':[],'planning_runs':[],'runs':[],'test_cases':[]})
        def native_of(p):
            content,validation=h.compile_current({**task,'workflow_plan':p});assert validation['valid'],validation['errors'];root=parse(content,'advanced-chat');return root,core(root['workflow'])
        onative,ocore=native_of(plan);mnative,mcore=native_of(modified)
        expectations=expectations_override or {c['id']:{'1':{'must':['start','no_hit_text','faq_llm','answer'],'must_not':[],'any_of':[['no_hit_text'],['faq_llm']]},'2':{'must':['start','no_hit_text','faq_llm','answer'],'must_not':[],'any_of':[['no_hit_text'],['faq_llm']]}} for c in cases}
        modified_cases=copy.deepcopy(cases);modified_cases[1]['expectation']['expected']=new
        modified_requirements={**requirements,'output':requirements['output'].replace(old,new)}
        topic_answers={'original':_public_topic_answers(task,plan,requirements),'modified':_public_topic_answers(task,plan,modified_requirements)}
        contract={'owner_task_id':tid,'review_source':{'authority':'standing_delegated_content_review','actor':tool.REVIEW_ACTOR,'human_signoff':False,'decision':'proceed'},'topic_answers':topic_answers,
                  'original':{'plan':plan,'native':onative,'core':ocore,'trace_expectations':expectations,'requirements':requirements,'cases':cases},
                  'modified':{'plan':modified,'native':mnative,'core':mcore,'trace_expectations':expectations,'requirements':modified_requirements,'cases':modified_cases}}
        fixture={'task_name':'公开双版平台任务','cases':cases,'requirements':requirements,'changed_no_hit_reply':new,'inputs':{'no_hit_reply':old},'topic_answers':topic_answers}
        old_capture=tool.capture(data);h.store=source
        record={'state':'running','physical_http':0,'automatic_retry':False,'model_http_started':0}
        b=Boundary(env,fixture,contract,record,tool.known_apps(data));b.owner=tid;b.save=lambda:None
        Protected=guarded(Store,env,contract,b,old_capture,task,budget)
        h.store=Protected(data);h.DATA_ROOT=data
        def forbidden(*a,**kw):raise RuntimeError('Sierra model/synchronous HTTP forbidden')
        h.call_model=forbidden;h.budgets.call=forbidden;httpx.HTTPTransport.handle_request=forbidden
        original=httpx.AsyncHTTPTransport.handle_async_request;synthetic=FakeDify(b,fail_case,fail_turn,fail_mode,mismatch,fail_nodes,omit_nodes)
        async def intercepted(own,request):
            async def physical(req):
                record['physical_http']+=1;return await original(own,req)
            return await b.dispatch(synthetic,request)
        httpx.AsyncHTTPTransport.handle_async_request=intercepted
        error=None
        try:
            with TestClient(h.app) as api:
                result=journey(api,h,b,fixture,contract,Path(tmp))
        except RuntimeError as exc:
            if fail_case is None and fail_mode is None and mismatch is None and not expected_stop:raise
            error=str(exc);b.record.update(state='stopped',failure_type='business_rule_failure' if fail_case is not None else 'protocol_stop');result=None
        finally:
            httpx.AsyncHTTPTransport.handle_async_request=original
        check=verify(h.store,env,b,old_capture,task,budget)
        saved=h.get_task(tid);ledger=h.store.get('task_budget',tid)
        if fail_case is not None:
            assert b.halted and b.record.get('failure_capture',{}).get('management_reads',99)<=4
            if fail_turn==2:
                assert b.record['failure_capture'].get('turn')==2
                assert b.counts['run']==7 and b.counts['import']==1 and b.counts['publish']==1 and b.counts['key']==1
                assert len([r for r in saved['runs'] if r.get('kind')=='run'])==6
            else:assert b.counts['run']==1
            assert record['physical_http']==0
            assert saved['workflow_plan']==plan and ledger['entries']==budget['entries']
            assert check['original_objects_kept'] and check['budget_kept']
            return b.record
        if fail_mode is not None or mismatch is not None or expected_stop:
            assert error is not None
            if fail_mode is not None or mismatch is not None:assert b.halted
            assert 'failure_capture' not in b.record and b.failure is None and not b.record.get('traces')
            assert record['physical_http']==0
            assert saved['workflow_plan']==plan and ledger['entries']==budget['entries']
            assert check['original_objects_kept'] and check['budget_kept']
            return {'error':error,'boundary':b,'record':b.record,'saved':saved,'ledger':ledger,'check':check}
        assert result['state']=='passed' and result['counts']['model']==0 and record['physical_http']==0
        assert b.counts['run']==14 and b.counts['login']==1 and b.counts['import']==2 and b.counts['publish']==2 and b.counts['key']==2 and b.counts['reads']<=116
        assert len([r for r in saved['runs'] if r.get('kind')=='run'])==12 and ledger['entries']==budget['entries']
        assert check['original_objects_kept'] and check['budget_kept']
        assert (Path(tmp)/'original.zip').is_file() and (Path(tmp)/'modified.zip').is_file()
        return result

def test_full_synthetic_chain():
    with tempfile.TemporaryDirectory() as tmp:return _setup(tmp)

def test_unique_business_failure_bounded_capture():
    with tempfile.TemporaryDirectory() as tmp:
        result=_setup(tmp,fail_case=0)
        assert result['state']=='stopped' and result['failure_capture']['state'] in {'captured','unavailable'}
        assert result['failure_capture']['management_reads']<=4

def test_second_turn_business_failure():
    with tempfile.TemporaryDirectory() as tmp:
        result=_setup(tmp,fail_case=5,fail_turn=2)
        assert result['state']=='stopped' and result['failure_capture']['turn']==2
        assert result['failure_capture']['state'] in {'captured','unavailable'}
        assert result['failure_capture']['management_reads']<=4

def test_service_technical_stops():
    for mode in ('invalid_json','http_500','transport'):
        with tempfile.TemporaryDirectory() as tmp:
            out=_setup(tmp,fail_mode=mode)
            assert out['boundary'].counts['run']==1 and out['boundary'].counts['import']==1
            assert out['boundary'].counts['publish']==1 and out['boundary'].counts['key']==1
            assert 'failure_capture' not in out['record'] and not out['record'].get('traces')

def test_diagnostic_identity_rejections():
    for mismatch,needle in (('message','Message mapping mismatch'),('native','Native execution graph/identity mismatch'),('source','Native execution graph/identity mismatch')):
        with tempfile.TemporaryDirectory() as tmp:
            out=_setup(tmp,mismatch=mismatch)
            assert needle in out['error'],out['error']
            assert out['boundary'].counts['run']==1 and out['boundary'].counts['import']==1

def test_trace_any_of():
    missing={f'case{i}':{'1':{'must':['start','answer'],'must_not':[],'any_of':[['branch_a'],['branch_b']]}} for i in range(1,7)}
    with tempfile.TemporaryDirectory() as tmp:
        out=_setup(tmp,expectations_override=missing,expected_stop=True)
        assert 'No allowed alternative terminal group succeeded' in out['error'],out['error']
    failed={f'case{i}':{'1':{'must':['start','answer'],'must_not':[],'any_of':[['no_hit_text'],['faq_llm']]}} for i in range(1,7)}
    with tempfile.TemporaryDirectory() as tmp:
        out=_setup(tmp,expectations_override=failed,fail_nodes={'no_hit_text','faq_llm'},expected_stop=True)
        assert 'No allowed alternative terminal group succeeded' in out['error'],out['error']
    legal={f'case{i}':{str(turn):{'must':['start','faq_llm','answer'],'must_not':[],'any_of':[['no_hit_text'],['faq_llm']]} for turn in (1,2)} for i in range(1,7)}
    with tempfile.TemporaryDirectory() as tmp:
        result=_setup(tmp,expectations_override=legal,omit_nodes={'no_hit_text'})
        assert result['state']=='passed' and result['stats']['diagnostics']==14

def _gate_state():
    old_app,app,last=str(uuid4()),str(uuid4()),str(uuid4())
    env={'id':str(uuid4()),'base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':str(uuid4()),'service_app_id':old_app}
    cases=[{'id':f'case{i}','input':{'query':f'q{i}'},'expectation':{'mode':'equals','target':'answer','expected':'a'}} for i in range(1,7)]
    cases[5]['followups']=[{'input':{'query':'follow'},'expectation':{'mode':'equals','target':'answer','expected':'a'}}]
    fixture={'task_name':'公开合成','cases':cases}
    contract={'owner_task_id':'public-owner','original':{'core':{'public':'core'},'native':{'workflow':{'graph':{'nodes':[{'id':'n1','data':{'type':'start','title':'开始'}}],'edges':[]}}}},'modified':{}}
    return env,fixture,contract,old_app,app,last
def _gate(env,fixture,contract,old_app):
    b=Boundary(env,fixture,contract,{'dispatches':[]},[old_app]);b.owner='public-owner';b.save=lambda:None;return b
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
    _expect_no_send(b,httpx.Request('POST',env['base_url']+'/console/api/login',json={'email':'public@example.invalid','password':'cHVibGlj','remember_me':False}),'login outside reconnect')
    b=fresh()
    _expect_no_send(b,httpx.Request('POST','https://api.deepseek.com/v1/chat/completions',json={'model':'deepseek-flash'}),'model URL')
    b=fresh()
    _expect_no_send(b,httpx.Request('GET',env['base_url']+'/console/api/apps/'+old_app+'/messages/'+str(uuid4())),'old App read')
    b=fresh();b.version='original';b.phase='original_cases';b.case_index=5;b.current=app
    b.apps[app]={'version':'original','published':True,'unpublished':False,'publish_started':True,'key_started':True,'key':'app-PUBLIC-390','service_count':6,'last_cid':last}
    body={'inputs':{},'query':'follow','response_mode':'blocking','conversation_id':str(uuid4()),'user':'flowcraft-local'}
    _expect_no_send(b,httpx.Request('POST',env['base_url']+'/v1/chat-messages',json=body,headers={'authorization':'Bearer app-PUBLIC-390'}),'cross-session turn')
    b=fresh();b.version='original';b.phase='original_cases';b.case_index=0;b.current=app
    b.apps[app]={'version':'original','published':True,'unpublished':False,'publish_started':True,'key_started':True,'key':'app-PUBLIC-390','service_count':1,'last_cid':None}
    body={'inputs':{},'query':'q1','response_mode':'blocking','user':'flowcraft-local'}
    _expect_no_send(b,httpx.Request('POST',env['base_url']+'/v1/chat-messages',json=body,headers={'authorization':'Bearer app-PUBLIC-390'}),'duplicate Service')
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
    assert result['matched'] is True and set(result)==set(tool.PINS)|{'matched'}
    boundary='tools/reviewed-dual390/boundary.py';journey='tools/reviewed-dual390/journey.py'
    bad={boundary:(ROOT/boundary).read_bytes()+b'\n# public hand edit\n'}
    rejected(lambda:tool.verify_fixed_reuse(ROOT,files=bad),'hand-edited boundary')
    bad={journey:(ROOT/journey).read_bytes().replace(b'Version must start at 0/6',b'Version must start at 0/7')}
    rejected(lambda:tool.verify_fixed_reuse(ROOT,files=bad),'hand-edited journey')

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
    _write(project/tool.SEAL_385_PATH,json.dumps(members,ensure_ascii=False));seal_sha=tool.sha(project/tool.SEAL_385_PATH)
    protected=tool.verify_sealed(project,seal_sha)
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
            'max_tokens':tool.MODEL_MAX_TOKENS,'model_parameters':{'thinking':tool.MODEL_THINKING}}
    task={'id':tool.TASK_ID,'name':'公开双版平台任务','app_type':'advanced-chat','revision':8,'plan_source':'manual','status':'draft_ready',
          'requirements_confirmed':True,'configuration_confirmed':True,'dify_app_id':None,'runs':[],
          'requirements':requirements,'test_cases':cases,'configuration':config,'workflow_plan':original}
    budget={'id':tool.TASK_ID,'policy_revision':1,'limit_usd':'0.600','entries':[
        {'id':str(uuid4()),'operation_id':str(uuid4()),'revision':8,'kind':'plan','provider_id':'synthetic-provider','model':'synthetic','pricing':{},'reserved_usd':'0.001','charged_usd':'0.001','status':'settled','call_status':'returned','cost_basis':'reported_usage','usage':{'completion_tokens':1},'policy_revision':1} for _ in range(5)],
        'policy_history':[],'excluded_history_present':False,'scope':'since_ledger_start','created_at':tool.now()}
    expectations={case['id']:{'1':{'must':['start'],'must_not':[]}} for case in cases}
    expectations[cases[5]['id']]['2']={'must':['start'],'must_not':[]}
    tool.ORIGINAL_GRAPH_SHA=tool.digest(original);tool.MODIFIED_GRAPH_SHA=tool.digest(modified)
    candidate_path=project/tool.FIXED_CANDIDATE_PATH;_write(candidate_path,json.dumps(modified,ensure_ascii=False))
    modified_requirements={**requirements,'output':requirements['output'].replace(old,new)}
    topic_answers={'original':_public_topic_answers(task,original,requirements),'modified':_public_topic_answers(task,modified,modified_requirements)}
    review={'schema_version':1,'batch_id':batch,'task_id':tool.TASK_ID,'environment_id':tool.ENVIRONMENT_ID,
            'review_authority':'standing_delegated_content_review','actor':tool.REVIEW_ACTOR,'human_signoff':False,'decision':'proceed',
            'task_sha256':tool.digest(task),'budget_sha256':tool.digest(budget),'cases_sha256':tool.digest(cases),
            'original_plan_sha256':tool.ORIGINAL_GRAPH_SHA,'modified_plan_sha256':tool.MODIFIED_GRAPH_SHA,
            'topic_answers':topic_answers,'trace_expectations':expectations}
    fixture,contract,candidate=tool.reviewed_inputs(project,task,budget,review,backend=BACKEND)
    reviewed={'original_plan':original,'modified_plan':modified,'cases':cases,'trace_expectations':expectations,
              'fixture':fixture,'contract':contract,
              'original_native_sha256':tool.digest(contract['original']['native']),'original_core_sha256':tool.digest(contract['original']['core']),
              'modified_native_sha256':tool.digest(contract['modified']['native']),'modified_core_sha256':tool.digest(contract['modified']['core']),
              'source':'original=380 model + 383 DeepSeek code correction + root agent explicit manual save; modified=385 model + 388 manual save',
              'task_sha256':review['task_sha256'],'budget_sha256':review['budget_sha256']}
    _write(root/'reviewed.json',json.dumps(reviewed,ensure_ascii=False));_write(root/'protected.json',json.dumps(protected,ensure_ascii=False))
    plan={'schema_version':1,'batch_id':batch,'source_commit':commit,'source_files':sources['files'],'pins':tool.PINS,
          'task_id':tool.TASK_ID,'task_revision':8,'environment_id':tool.ENVIRONMENT_ID,'workspace_id':tool.WORKSPACE_ID,
          'environment_sha256':'a'*64,'task_sha256':review['task_sha256'],'budget_sha256':review['budget_sha256'],
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
          'only_new_login':True,'failure_exception':tool.FAILURE_POLICY,'single_use':True,'retry':False,'created_at':tool.now()}
    tool.atomic_json(root/'approval.json',auth)
    return project,root,plan,manifest,auth,seal_sha,reviewed,task,budget,review

def test_package_and_approval_gates():
    with tempfile.TemporaryDirectory() as tmp:
        anchor=tool.SEAL_INDEX_SHA;graph_anchors=(tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA)
        project,root,plan,manifest,auth,seal_sha,reviewed,task,budget,review=_package_gate(tmp)
        tool.SEAL_INDEX_SHA=seal_sha
        root_plan_bytes=(project/tool.ROOT_PLAN).read_bytes()
        try:
            tool.validate_package(project,root,backend=BACKEND)
            native_nodes=plan['contract']['original']['native']['workflow']['graph']['nodes']
            assert next(node for node in native_nodes if node['id']=='faq_llm')['data']['model']=={'provider':'public/provider','name':'public-model','mode':'chat','completion_params':{'temperature':0.2,'max_tokens':512,'thinking':False}}
            retrieve=next(node for node in native_nodes if node['id']=='retrieve')['data']
            assert retrieve['dataset_ids']==['public-kb'] and retrieve['multiple_retrieval_config']['top_k']==3
            assert retrieve['multiple_retrieval_config']['score_threshold'] is None and retrieve['multiple_retrieval_config']['reranking_enable'] is False
            assert plan['contract']['original']['native']['workflow']['conversation_variables']==plan['contract']['modified']['native']['workflow']['conversation_variables']==[]
            tool.validate_approval(root,auth,plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json'))
            tool.preflight_run(project,root,backend=BACKEND)
            candidate_path=project/tool.FIXED_CANDIDATE_PATH;candidate_bytes=candidate_path.read_bytes()
            def inputs(value=review):return tool.reviewed_inputs(project,task,budget,value,backend=BACKEND)
            candidate_path.unlink();rejected(inputs,'missing fixed candidate');candidate_path.write_bytes(candidate_bytes)
            _write(candidate_path,'{}');rejected(inputs,'wrong fixed candidate');candidate_path.write_bytes(candidate_bytes)
            override={**review,'modified_candidate_path':str(Path(tmp)/'other.json')};rejected(lambda:inputs(override),'candidate path override')
            fake={**review,'actor':'direct_user_reply'};rejected(lambda:inputs(fake),'fake review actor')
            signoff={**review,'human_signoff':True};rejected(lambda:inputs(signoff),'fake human signoff')
            forged_fixture=copy.deepcopy(review);forged_fixture['fixture']={'task_name':'外部伪造'};rejected(lambda:inputs(forged_fixture),'external fixture injection')
            forged_contract=copy.deepcopy(review);forged_contract['contract']={'owner_task_id':'fake'};rejected(lambda:inputs(forged_contract),'external contract injection')
            missing_turn=copy.deepcopy(review);missing_turn['trace_expectations']['case6'].pop('2');rejected(lambda:inputs(missing_turn),'missing trace turn')
            missing_case=copy.deepcopy(review);missing_case['trace_expectations'].pop('case5');rejected(lambda:inputs(missing_case),'missing trace case')
            unknown_node=copy.deepcopy(review);unknown_node['trace_expectations']['case1']['1']['must']=['start','not_a_native_node'];rejected(lambda:inputs(unknown_node),'unknown trace node')
            arbitrary=copy.deepcopy(plan['contract']['original']['plan']);arbitrary['nodes'][0]['config']['variables']=[{'variable':'public_extra','type':'text-input','required':False}];arbitrary['nodes'][4]['config']['answer']='changed'
            _write(candidate_path,json.dumps(arbitrary,ensure_ascii=False));anchor_mod=tool.MODIFIED_GRAPH_SHA;tool.MODIFIED_GRAPH_SHA=tool.digest(arbitrary)
            arbitrary_review={**review,'modified_plan_sha256':tool.MODIFIED_GRAPH_SHA}
            try:rejected(lambda:inputs(arbitrary_review),'arbitrary two fields')
            finally:tool.MODIFIED_GRAPH_SHA=anchor_mod;candidate_path.write_bytes(candidate_bytes)
            def rebind(bad_plan,bad_reviewed):
                contract=bad_plan['contract']
                bad_plan['original_native_sha256']=tool.digest(contract['original']['native'])
                bad_plan['original_core_sha256']=tool.digest(contract['original']['core'])
                bad_plan['modified_native_sha256']=tool.digest(contract['modified']['native'])
                bad_plan['modified_core_sha256']=tool.digest(contract['modified']['core'])
                bad_plan['fixture_sha256']=tool.digest(bad_plan['fixture']);bad_plan['contract_sha256']=tool.digest(contract)
                bad_plan['trace_expectations_sha256']=tool.digest(contract['original']['trace_expectations'])
                bad_plan['original_requirements_sha256']=tool.digest(contract['original']['requirements'])
                bad_plan['original_cases_sha256']=tool.digest(contract['original']['cases'])
                bad_reviewed['contract']=contract;bad_reviewed['fixture']=bad_plan['fixture']
                bad_reviewed['original_plan']=contract['original']['plan'];bad_reviewed['modified_plan']=contract['modified']['plan']
                bad_reviewed['cases']=contract['original']['cases'];bad_reviewed['trace_expectations']=contract['original']['trace_expectations']
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            fake_native={'workflow':{'graph':{'nodes':[],'edges':[]},'conversation_variables':[],'environment_variables':[]}}
            bad_plan['contract']['original']['native']=fake_native;rebind(bad_plan,bad_reviewed)
            rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'native injection')
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            bad_plan['contract']['original']['core']['features']={'public':'tampered'}
            rebind(bad_plan,bad_reviewed);rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'core injection')
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            model_node=next(node for node in bad_plan['contract']['original']['native']['workflow']['graph']['nodes'] if node['id']=='faq_llm')
            model_node['data']['model']['completion_params']['temperature']=0.3
            rebind(bad_plan,bad_reviewed);rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'native model parameter injection')
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            bad_plan['contract']['original']['native']['workflow']['conversation_variables']=[{'name':'extra','value':1}]
            rebind(bad_plan,bad_reviewed);rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'native state injection')
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            retrieve=next(node for node in bad_plan['contract']['original']['native']['workflow']['graph']['nodes'] if node['id']=='retrieve')
            retrieve['data']['multiple_retrieval_config']['top_k']=5
            rebind(bad_plan,bad_reviewed);rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'native KB injection')
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            bad_plan['contract']['original']['trace_expectations']['case6'].pop('2')
            bad_plan['contract']['modified']['trace_expectations']=bad_plan['contract']['original']['trace_expectations']
            rebind(bad_plan,bad_reviewed);rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'missing trace turn')
            tool.validate_contract(plan,reviewed,backend=BACKEND)
            approved={**auth}
            bad={k:v for k,v in auth.items() if k not in {'authorization_source','scope','literal','question_ref','retry'}}
            tool.atomic_json(root/'approval.json',bad);rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'missing direct metadata')
            tool.atomic_json(root/'approval.json',approved)
            rejected(lambda:tool.validate_approval(root,{**auth,'limits':{**tool.LIMITS,'login':True}},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'bool limit')
            rejected(lambda:tool.validate_approval(root,{**auth,'question_ref':tool.OLD_REFS[0]},plan,tool.sha(root/'plan.json'),tool.sha(root/'manifest.json')),'old ref')
            bad_manifest=copy.deepcopy(manifest);bad_manifest['files']['extra.py']='f'*64;tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'extra member');tool.atomic_json(root/'manifest.json',manifest)
            _write(root/'extra.py','extra');rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'extra package file');(root/'extra.py').unlink()
            bad_plan=copy.deepcopy(plan);bad_plan['root_paths']['391']=tool.ROOT_PATHS['394'];tool.atomic_json(root/'plan.json',bad_plan);bad_manifest=copy.deepcopy(manifest);bad_manifest['plan_sha256']=tool.sha(root/'plan.json');bad_manifest['files']['plan.json']=bad_manifest['plan_sha256'];tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'same-count root replacement');tool.atomic_json(root/'plan.json',plan);tool.atomic_json(root/'manifest.json',manifest)
            bad_roots=copy.deepcopy(plan);bad_roots['roots']['391']=copy.deepcopy(plan['roots']['394']);bad_roots['roots']['391']['path']=tool.ROOT_PATHS['391']
            rejected(lambda:tool.verify_roots_protected(project,bad_roots),'same-count root snapshot replacement')
            _write(project/tool.ROOT_PLAN,json.dumps({'isolated_paths':{'391':tool.ROOT_PATHS['394']}}));rejected(lambda:tool.verify_root_paths(project),'375 root plan replacement');(project/tool.ROOT_PLAN).write_bytes(root_plan_bytes)
            old_bytes=(project/tool.OLD_892_PATH).read_bytes();_write(project/tool.OLD_892_PATH,'{}');rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'old 892 tamper');(project/tool.OLD_892_PATH).write_bytes(old_bytes)
            seal_bytes=(project/tool.SEAL_385_PATH).read_bytes();_write(project/tool.SEAL_385_PATH,'{}');rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'seal tamper');(project/tool.SEAL_385_PATH).write_bytes(seal_bytes)
            root_rel=project/tool.ROOT_PATHS['391'];root_backup=Path(tmp)/'root391-backup';shutil.copytree(root_rel,root_backup)
            def restore_root():shutil.rmtree(root_rel);shutil.copytree(root_backup,root_rel)
            from app.storage import Store
            Store(root_rel).put('task','task-extra',{'id':'task-extra'});rejected(lambda:tool.verify_roots_protected(project,plan),'old root object changed');restore_root()
            Store(root_rel).put_with_secrets('environment','env-extra',{'id':'env-extra'},{'console_token':'new'});rejected(lambda:tool.verify_roots_protected(project,plan),'old root secret changed');restore_root()
            _write(root_rel/'asset.txt','changed');rejected(lambda:tool.verify_roots_protected(project,plan),'old root asset changed');restore_root()
            _write(root_rel/'nested/server.pid','changed');rejected(lambda:tool.verify_roots_protected(project,plan),'nested same-name asset changed');restore_root()
            _write(root_rel/'server.pid','ignored-root-asset');tool.verify_roots_protected(project,plan);(root_rel/'server.pid').unlink()
            _write(root/'tool.py','drift');bad_manifest=copy.deepcopy(manifest);bad_manifest['files']['tool.py']=tool.sha(root/'tool.py');tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'source drift');_write(root/'tool.py',(project/'tools'/tool.BATCH/'tool.py').read_text('utf-8'));tool.atomic_json(root/'manifest.json',manifest)
            bad_plan=copy.deepcopy(plan);bad_plan['runtime']['build']='0.999.0';tool.atomic_json(root/'plan.json',bad_plan);bad_manifest=copy.deepcopy(manifest);bad_manifest['plan_sha256']=tool.sha(root/'plan.json');bad_manifest['files']['plan.json']=bad_manifest['plan_sha256'];tool.atomic_json(root/'manifest.json',bad_manifest)
            rejected(lambda:tool.validate_package(project,root,backend=BACKEND),'wrong runtime');tool.atomic_json(root/'plan.json',plan);tool.atomic_json(root/'manifest.json',manifest)
            tool.atomic_json(root/'attempt.json',{'state':'admitted'});rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'reused state');(root/'attempt.json').unlink()
            (root/'live-output').mkdir();rejected(lambda:tool.preflight_run(project,root,backend=BACKEND),'live output');(root/'live-output').rmdir()
            data=project/'data';data_backup=Path(tmp)/'data-backup';shutil.copytree(data,data_backup)
            Store(data).put('task','task-allowed',{'id':'task-allowed'});tool.verify_roots_protected(project,plan,production=False)
            rejected(lambda:tool.verify_roots_protected(project,plan,production=True),'production changed')
            shutil.rmtree(data);shutil.copytree(data_backup,data)
        finally:tool.SEAL_INDEX_SHA=anchor;tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA=graph_anchors

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
    task={'id':owner,'name':'公开守卫任务','app_type':'advanced-chat','environment_id':env_id,'revision':8,'status':'draft_ready',
          'requirements':requirements,'requirements_confirmed':True,'configuration':{'dify_model_provider':'public/provider','dify_model':'public-model'},
          'configuration_confirmed':True,'materials':[],'test_cases':cases,'workflow_plan':plan,'plan_source':'manual','plan_stale':False,
          'artifact':{'revision':8,'sha256':'a'*64},'dify_app_id':None,
          'messages':[{'role':'assistant','source':'system','content':'旧系统消息','created_at':timestamp}],
          'versions':[{'id':'v-old','revision':7,'label':'旧快照','created_at':timestamp}],
          'confirmations':[{'kind':'requirements','revision':7,'created_at':timestamp}],
          'intake_history':[],'intake_review':{'review':{'schema_version':1,'checks':[]},'source':'user_declared','created_at':timestamp},
          'runs':[],'planning_runs':[],'created_at':timestamp,'updated_at':timestamp}
    budget={'id':owner,'policy_revision':1,'limit_usd':'0.600','created_at':timestamp,'excluded_history_present':False,
            'scope':'since_ledger_start','policy_history':[],'entries':[
        {'id':f'entry-{i}','operation_id':f'op-{i}','revision':8,'kind':'plan','provider_id':'public-provider','model':'public-model',
         'pricing':{},'reserved_usd':'0.001','charged_usd':'0.001','status':'settled','call_status':'returned','cost_basis':'reported_usage','usage':{'completion_tokens':1},'attempts':0,'policy_revision':1} for i in range(5)]}
    base.put('task',owner,task);base.put('task_budget',owner,budget)
    initial_task=base.get('task',owner);initial_budget=base.get('task_budget',owner)
    contract={'original':{'plan':plan,'requirements':requirements,'cases':cases},
              'modified':{'plan':modified_plan,'requirements':modified_requirements,'cases':modified_cases}}
    class PublicBoundary:pass
    boundary=PublicBoundary();boundary.owner=owner;boundary.apps=set();boundary.current=None
    old=tool.capture(data)
    Guarded=guarded(Store,env,contract,boundary,old,initial_task,initial_budget)
    return Guarded(data),initial_task,initial_budget,contract

def test_storage_guard_integrity():
    with tempfile.TemporaryDirectory() as tmp:
        g,initial_task,initial_budget,contract=_guard_store(tmp)
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
        bad_task(lambda value:value.update(interview_attempts=[]),'default interview attempts')
        bad_task(lambda value:value.update(active_interview_id=None),'default active interview')
        bad_task(lambda value:value.update(workflow_plan=None),'erased workflow plan')
        bad_task(lambda value:value.update(id='other-task'),'task id')
        bad_task(lambda value:value.update(name='改名任务'),'task name')
        bad_task(lambda value:value.update(unlisted_user_field='new'),'unlisted user field')
        bad_task(lambda value:value.pop('materials'),'deleted material field')
        bad_task(lambda value:value.pop('intake_review'),'deleted intake review')
        bad_task(lambda value:value.update(environment_id='other-environment'),'environment id')
        bad_task(lambda value:value.update(dify_app_id='not-an-app'),'wrong task app')
        bad_task(lambda value:value.update(configuration={'dify_model_provider':'other/provider','dify_model':'other-model'}),'configuration change')
        bad_task(lambda value:value.update(requirements={**contract['original']['requirements'],'goal':'未审改变'}),'unreviewed requirements')
        bad_task(lambda value:value.update(test_cases=[{'id':'case1','expected':'other'}]),'unreviewed cases')
        rejected(lambda:g.put('task','other-task',copy.deepcopy(initial_task)),'other task')
        rejected(lambda:g.delete('task',owner),'task delete')
        def bad_budget(mutate,label):
            value=copy.deepcopy(initial_budget);mutate(value);rejected(lambda:g.put('task_budget',owner,value),label)
        bad_budget(lambda value:value.update(limit_usd='0.700'),'budget metadata')
        bad_budget(lambda value:value.update(policy_revision=True),'budget bool revision')
        bad_budget(lambda value:value['entries'][0].update(charged_usd='0.002'),'budget entry value')
        def bad_entry(mutate,label):
            value=copy.deepcopy(initial_budget);mutate(value['entries'][0]);rejected(lambda:g.put('task_budget',owner,value),label)
        bad_entry(lambda row:row.update(attempts=False),'budget entry zero vs false')
        bad_entry(lambda row:row.update(policy_revision=True),'budget entry one vs true')
        bad_budget(lambda value:value['entries'].append(copy.deepcopy(value['entries'][0])),'new budget entry')
        rejected(lambda:g.put('task_budget','other-budget',copy.deepcopy(initial_budget)),'other budget')
        g.put('task_budget',owner,copy.deepcopy(initial_budget))
        before={k:None for k in ('max_started_runs','max_total_minutes','max_reported_cost_usd')}
        after={'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None}
        def policy(**over):
            value={'id':owner,'policy_revision':1,**after,'updated_at':timestamp,
                   'history':[{'before':copy.deepcopy(before),'after':copy.deepcopy(after),'note':'公开首次上限','created_at':timestamp,'source':'user'}]}
            value.update(over);return value
        bad_policy=policy();bad_policy['max_total_minutes']=46;rejected(lambda:g.put('execution_limits',owner,bad_policy),'invalid first policy limits')
        bad_policy=policy();bad_policy['policy_revision']=2;rejected(lambda:g.put('execution_limits',owner,bad_policy),'invalid first policy revision')
        bad_policy=policy();bad_policy['history'][0]['source']='agent';rejected(lambda:g.put('execution_limits',owner,bad_policy),'invalid policy source')
        bad_policy=policy();bad_policy['history'][0]['before']['max_started_runs']=1;rejected(lambda:g.put('execution_limits',owner,bad_policy),'invalid policy before')
        bad_policy=policy();bad_policy['history'][0]['created_at']='bad-time';rejected(lambda:g.put('execution_limits',owner,bad_policy),'invalid policy time')
        record=policy();g.put('execution_limits',owner,record);g.put('execution_limits',owner,copy.deepcopy(record))
        changed=policy();changed['max_started_runs']=13;rejected(lambda:g.put('execution_limits',owner,changed),'existing policy changed')
        with tempfile.TemporaryDirectory() as order_tmp:
            g2,task2,budget2,contract2=_guard_store(order_tmp)
            early='2026-11-28T00:00:00.000000+00:00';late='2026-11-28T00:00:00.000500+00:00'
            order_record={'id':task2['id'],'policy_revision':1,**after,'updated_at':early,
                          'history':[{'before':copy.deepcopy(before),'after':copy.deepcopy(after),'note':'公开产品时间顺序','created_at':late,'source':'user'}]}
            g2.put('execution_limits',task2['id'],order_record)


def test_explicit_topic_answers():
    with tempfile.TemporaryDirectory() as tmp:
        anchors=(tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA)
        try:
            project,root,plan,manifest,auth,seal_sha,reviewed,task,budget,review=_package_gate(tmp)
            def inputs(value=review):return tool.reviewed_inputs(project,task,budget,value,backend=BACKEND)
            def bad(mutate,label):
                value=copy.deepcopy(review);mutate(value);rejected(lambda:inputs(value),label)
            key=next(iter(review['topic_answers']['original']))
            bad(lambda value:value['topic_answers']['original'].pop(key),'missing topic answer')
            bad(lambda value:value['topic_answers']['original'].update(unknown_topic='公开未知主题说明'),'unknown topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:None}),'null topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:True}),'bool topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:['公开文字']}),'list topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:'   '}),'blank topic answer')
            bad(lambda value:value['topic_answers']['original'].update({key:'待补充'}),'unknown placeholder topic answer')
            bad(lambda value:value['topic_answers']['modified'].update(output='错版输出说明'),'wrong output topic answer')
            bad(lambda value:value.update(review_authority='human_signoff'),'human authority')
            bad(lambda value:value.update(actor='local_operator'),'human actor')
            bad(lambda value:value.update(human_signoff=True),'human signoff')
            bad(lambda value:value.pop('review_authority'),'missing authority')
            def rebind(bad_plan,bad_reviewed):
                contract=bad_plan['contract'];bad_plan['contract_sha256']=tool.digest(contract)
                bad_plan['topic_answers_sha256']=tool.digest(contract['topic_answers'])
                bad_reviewed['contract']=contract
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            bad_plan['contract']['modified']['requirements']=copy.deepcopy(bad_plan['contract']['original']['requirements'])
            rebind(bad_plan,bad_reviewed);rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'contract wrong output')
            bad_plan=copy.deepcopy(plan);bad_reviewed=copy.deepcopy(reviewed)
            bad_plan['contract']['topic_answers']['original']['injected_topic']='公开注入说明'
            rebind(bad_plan,bad_reviewed);rejected(lambda:tool.validate_contract(bad_plan,bad_reviewed,backend=BACKEND),'contract injected topic')
        finally:tool.ORIGINAL_GRAPH_SHA,tool.MODIFIED_GRAPH_SHA=anchors
    with tempfile.TemporaryDirectory() as tmp:
        from app import main as h
        from app.storage import Store
        from types import SimpleNamespace
        from fastapi.testclient import TestClient
        data=Path(tmp)/'data';source=Store(data);h.store=source;h.DATA_ROOT=data
        requirements={'goal':'公开守卫','audience':'公开用户','input':'query','output':'知识库暂无相关信息，请联系人工客服。','rules':'只按已审图','knowledge':'不适用','exceptions':'停止','tests':'一例'}
        with TestClient(h.app) as api:
            task=_api_call(api,'POST','/api/tasks',{'name':'公开主题任务','app_type':'advanced-chat','environment_id':None})
            tid=task['id']
            _api_call(api,'PATCH',f'/api/tasks/{tid}',{'expected_revision':task['revision'],'requirements':requirements,'configuration':copy.deepcopy(h.CONFIG_DEFAULT)})
            fresh=_api_call(api,'GET',f'/api/tasks/{tid}')
            from app.intake import BASE,topics
            standard=[row['id'] for row in topics(fresh)]
            answers={item:(fresh['requirements'][item] if item in BASE else PUBLIC_TOPIC_ANSWERS[item]) for item in standard}
            fixture={'topic_answers':{'original':answers,'modified':answers}}
            boundary=SimpleNamespace(owner=tid,halted=False)
            import journey as journey_module
            journey_module.submit_intake(api,h,boundary,fixture,'original')
            drift=copy.deepcopy(answers);drift.pop(next(iter(drift)))
            rejected(lambda:journey_module.submit_intake(api,h,boundary,{'topic_answers':{'original':drift,'modified':drift}},'original'),'standard drift')
            class WrongToken:
                def __init__(self,inner):self.inner=inner
                def request(self,method,path,**kw):
                    response=self.inner.request(method,path,**kw)
                    if method=='GET' and path.endswith('/intake'):
                        value=response.json();value['context_token']='wrong-public-token'
                        return SimpleNamespace(status_code=response.status_code,json=lambda:value,text='')
                    return response
            rejected(lambda:journey_module.submit_intake(WrongToken(api),h,boundary,fixture,'original'),'wrong context token')

def test_strict_map_booleans():
    tool._strict_map(tool.FAILURE_POLICY,tool.FAILURE_POLICY,'failure policy');tool._strict_map(tool.EXECUTION_POLICY,tool.EXECUTION_POLICY,'execution policy')
    value={'truth':True,'falsehood':False,'count':1}
    tool._strict_map(value,value,'strict bool');assert value['truth'] is True and value['falsehood'] is False
    nested={'outer':{'truth':True,'falsehood':False,'count':1}}
    tool._strict_map(nested,nested,'nested strict bool')
    rejected(lambda:tool._strict_map({**tool.FAILURE_POLICY,'business_rule_failure_only':1},tool.FAILURE_POLICY,'failure policy'),'real int as bool')
    rejected(lambda:tool._strict_map({'truth':1,'falsehood':False,'count':1},value,'strict bool'),'int as true')
    rejected(lambda:tool._strict_map({'truth':True,'falsehood':0,'count':1},value,'strict bool'),'int as false')
    rejected(lambda:tool._strict_map({'truth':True,'falsehood':False,'count':True},value,'strict bool'),'bool as int')
    rejected(lambda:tool._strict_map({'outer':{'truth':1,'falsehood':False,'count':1}},nested,'nested strict bool'),'nested int as bool')

def test_runtime_process_identity():
    exe=str(tool.REAL_PROJECT/'.venv/Scripts/python.exe');backend=str(tool.RUNTIME_BACKEND)
    def q(value):return '"'+value+'"'
    command=q(exe)+' -m uvicorn app.main:app --app-dir '+q(backend)+' --host 127.0.0.1 --port 8765'
    tool._runtime_process_matches_command(exe,command,backend)
    spaced=str(tool.REAL_PROJECT/'snapshot with spaces'/'backend')
    spaced_command=q(exe)+' -m uvicorn app.main:app --app-dir '+q(spaced)+' --host 127.0.0.1 --port 8765'
    tool._runtime_process_matches_command(exe,spaced_command,spaced)
    eq_command=q(exe)+' -m uvicorn app.main:app --app-dir='+q(backend)+' --host 127.0.0.1 --port 8765'
    tool._runtime_process_matches_command(exe,eq_command,backend)
    rejected(lambda:tool._runtime_process_matches_command(exe,spaced_command,backend),'wrong runtime app-dir')
    rejected(lambda:tool._runtime_process_matches_command(str(tool.REAL_PROJECT/'other/python.exe'),command,backend),'wrong runtime exe')
    rejected(lambda:tool._runtime_process_matches_command(exe,command.replace('127.0.0.1','0.0.0.0'),backend),'wrong runtime host')
    rejected(lambda:tool._runtime_process_matches_command(exe,command.replace('8765','8766'),backend),'wrong runtime port')
    fake=q(exe)+' script.py uvicorn app.main:app --app-dir '+q(backend)+' --host 127.0.0.1 --port 8765'
    rejected(lambda:tool._runtime_process_matches_command(exe,fake,backend),'fake script signature')
    rejected(lambda:tool._runtime_process_matches_command(exe,command+' --reload',backend),'unexpected runtime flag')

def test_cli_refusal():
    with tempfile.TemporaryDirectory() as tmp:
        missing=Path(tmp)/'missing-project';r=subprocess.run([sys.executable,tool.__file__,'--project',str(missing),'run'],capture_output=True,text=True,timeout=30)
        out=r.stdout+r.stderr;assert r.returncode!=0 and 'stopped:' in out and 'Traceback' not in out and not missing.exists()

def main():
    test_full_synthetic_chain();print('ok full_synthetic_chain')
    test_unique_business_failure_bounded_capture();print('ok unique_business_failure_bounded_capture')
    test_second_turn_business_failure();print('ok second_turn_business_failure')
    test_service_technical_stops();print('ok service_technical_stops')
    test_diagnostic_identity_rejections();print('ok diagnostic_identity_rejections')
    test_trace_any_of();print('ok trace_any_of')
    test_boundary_rejections();print('ok boundary_rejections')
    test_known_apps_includes_run_history();print('ok known_apps_includes_run_history')
    test_fixed_source_reuse();print('ok fixed_source_reuse')
    test_package_and_approval_gates();print('ok package_and_approval_gates')
    test_storage_guard_integrity();print('ok storage_guard_integrity')
    test_explicit_topic_answers();print('ok explicit_topic_answers')
    test_strict_map_booleans();print('ok strict_map_booleans')
    test_runtime_process_identity();print('ok runtime_process_identity')
    test_cli_refusal();print('ok cli_refusal')
    print('reviewed-dual390 public checks passed')
if __name__=='__main__':main()
