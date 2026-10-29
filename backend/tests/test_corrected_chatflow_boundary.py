"""Pure new-scope gate tests. No production Store, browser, model or Dify HTTP."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import httpx
import pytest

SOURCE=Path(__file__).resolve().parents[2]/'tools/corrected-chatflow378'
sys.path.insert(0,str(SOURCE))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import LIMITS,PROJECT,capture,sha,known_apps
from boundary import Boundary
from execute import approved,authorized,claim,load,validated,FROZEN
from storage_guard import guarded,verify
from synthetic import response

def test_corrected_contract_rejects_old_context_omission(monkeypatch):
    from app import main as h
    from app import after_sales_starter
    from contract import build
    fixture=json.loads((SOURCE/'fixture.json').read_text('utf-8'))
    prepare=after_sales_starter.prepare
    def old(*args):
        text,validation=prepare(*args);value=json.loads(text)
        next(n for n in value['nodes'] if n['id']=='grounded_answer')['config']['user_prompt']='{{#sys.query#}}'
        return json.dumps(value,ensure_ascii=False),validation
    monkeypatch.setattr(after_sales_starter,'prepare',old)
    with pytest.raises(RuntimeError,match='Corrected retrieval context'):build(h,fixture)

def test_both_new_versions_keep_context_and_only_two_reply_changes():
    from app import main as h
    from contract import build
    c=build(h,json.loads((SOURCE/'fixture.json').read_text('utf-8')))
    a=c['original']['plan'];b=c['modified']['plan'];diff=[]
    for before,after in zip(a['nodes'],b['nodes']):
        if before!=after:diff.append(before['id'])
        if before['id']=='grounded_answer':
            assert before['config']['user_prompt']==after['config']['user_prompt']
            assert '{{#context#}}' in before['config']['user_prompt']
    assert diff==['grounded_answer','no_hit'] and a['edges']==b['edges']

APP='11111111-2222-4222-8222-111111111111'
OLD='99999999-2222-4222-8222-111111111111'
CID='22222222-2222-4222-8222-111111111111'

@pytest.fixture
def gate():
    f=json.loads((SOURCE/'fixture.json').read_text('utf-8'))
    env={'id':f['environment_id'],'base_url':'https://public-dify.invalid','version':'1.17.1','console_workspace_id':f['workspace_id'],'service_app_id':OLD}
    return Boundary(env,f,{}, {},{OLD})

def req(path,body=None,method=None,base='https://public-dify.invalid',key=None):
    return httpx.Request(method or ('POST' if body is not None else 'GET'),base+path,json=body,headers={'authorization':'Bearer '+key} if key else {})

def service_ready(b,index=0,sequence=0):
    b.workspace_verified=True;b.phase='original_cases';b.case_index=index;b.current=APP
    b.apps[APP]={'version':'original','key':'app-PUBLIC_UNIT_KEY','service_count':sequence,'last_cid':CID,'published':APP,'unpublished':False,'publish_started':True,'key_started':True}
    turn=b.f['cases'][index];return {'inputs':{},'query':turn['input']['query'],'response_mode':'blocking','user':'flowcraft-local'}

@pytest.mark.parametrize('path,base,method,body',[
    ('/v1/chat/completions','https://api.deepseek.com','POST',{}),
    ('/console/api/datasets','https://public-dify.invalid','POST',{}),
    ('/console/api/apps/'+OLD,'https://public-dify.invalid','DELETE',None),
    ('/console/api/apps/'+OLD+'/api-keys','https://public-dify.invalid','POST',{}),
    ('/console/api/apps/'+OLD,'https://public-dify.invalid','GET',None),
    ('/console/api/apps/'+APP+'/messages/'+CID,'https://public-dify.invalid','GET',None),
    ('/console/api/apps?page=2&limit=1','https://public-dify.invalid','GET',None),
    ('/console/api/login?extra=1','https://public-dify.invalid','POST',{}),
])
def test_unapproved_origins_old_resources_and_operations_count_nothing(gate,path,base,method,body):
    with pytest.raises(RuntimeError):gate.admit(req(path,body,method,base))
    assert not any(gate.counts.values())

def test_unread_response_cookie_context_and_exact_one_login(gate):
    body={'email':'public@example.invalid','password':'PUBLIC_UNIT_ONLY','remember_me':False}
    async def send(request):return response({'result':'success'},headers=[('set-cookie','access_token=PUBLIC_ACCESS; Path=/'),('set-cookie','csrf_token=PUBLIC_CSRF; Path=/')])
    r=asyncio.run(gate.dispatch(send,req('/console/api/login',body)))
    assert r.is_stream_consumed and gate.record['dispatches'][0]['response_body_read']
    assert gate.login_tokens=={'console_token':'PUBLIC_ACCESS','csrf_token':'PUBLIC_CSRF'} and not gate.workspace_verified
    with pytest.raises(RuntimeError):asyncio.run(gate.dispatch(send,req('/console/api/login',body)))
    assert gate.halted and gate.counts['login']==1

@pytest.mark.parametrize('change',['wrong_user','extra_input','query','key','cid','response_mode','out_of_order'])
def test_service_exact_case_query_key_and_fresh_session(gate,change):
    body=service_ready(gate);key='app-PUBLIC_UNIT_KEY'
    if change=='wrong_user':body['user']='other'
    if change=='extra_input':body['inputs']={'password':'PUBLIC_UNIT_ONLY'}
    if change=='query':body['query']='unapproved'
    if change=='key':key='app-OTHER_KEY'
    if change=='cid':body['conversation_id']=CID
    if change=='response_mode':body['response_mode']='streaming'
    if change=='out_of_order':gate.apps[APP]['service_count']=3
    with pytest.raises(RuntimeError):gate.admit(req('/v1/chat-messages',body,key=key))
    assert gate.counts['run']==0

def test_second_turn_only_reuses_matching_first_conversation(gate):
    body=service_ready(gate,index=5,sequence=6);body.update(query='DEMO-001',conversation_id=CID)
    assert gate.admit(req('/v1/chat-messages',body,key='app-PUBLIC_UNIT_KEY'))['second_turn'] is True
    with pytest.raises(RuntimeError):gate.admit(req('/v1/chat-messages',body,key='app-PUBLIC_UNIT_KEY'))
    assert gate.counts['run']==1

def test_already_started_count_preserved_on_network_failure_and_no_retry(gate):
    body=service_ready(gate);seen=[]
    async def broken(request):seen.append(1);raise httpx.ReadError('PUBLIC transport interruption')
    with pytest.raises(httpx.ReadError):asyncio.run(gate.dispatch(broken,req('/v1/chat-messages',body,key='app-PUBLIC_UNIT_KEY')))
    with pytest.raises(RuntimeError):asyncio.run(gate.dispatch(broken,req('/v1/chat-messages',body,key='app-PUBLIC_UNIT_KEY')))
    assert seen==[1] and gate.counts['run']==1 and gate.record['dispatches'][0]['status'] is None

@pytest.mark.parametrize('kind,path',[('reads','/console/api/workspaces/current/summary'),('login','/console/api/login')])
def test_total_caps_and_expiry_block_before_dispatch(gate,kind,path):
    gate.counts[kind]=LIMITS[kind]
    with pytest.raises(RuntimeError):gate.admit(req(path,{'email':'public','password':'PUBLIC','remember_me':False} if kind=='login' else None))
    gate.counts[kind]=0;gate.started-=3601
    with pytest.raises(RuntimeError):gate.admit(req(path))
    assert not gate.record['dispatches']

@pytest.mark.parametrize('bad',['old','duplicate','not_uuid','partial'])
def test_import_must_return_unique_new_completed_app(gate,bad):
    value={'status':'completed','app_id':APP}
    if bad=='old':value['app_id']=OLD
    if bad=='duplicate':gate.apps[APP]={}
    if bad=='not_uuid':value['app_id']='not-an-app'
    if bad=='partial':value['status']='pending'
    with pytest.raises(RuntimeError):gate.observed({'path':'/console/api/apps/imports','kind':'import','method':'POST'},httpx.Response(200,json=value))

def test_wrong_workspace_never_proves_authentication(gate):
    with pytest.raises(RuntimeError):gate.observed({'path':'/console/api/workspaces/current/summary','kind':'reads','method':'GET'},httpx.Response(200,json={'id':APP}))
    assert not gate.workspace_verified

def frozen(tmp_path):
    plan={'batch_id':'corrected-chatflow378','limits':copy.deepcopy(LIMITS),'new_independent_scope':True,'old_reservations_preserved':True,'model_estimate_book_upper_usd':'0.755473652','estimated_new_dify_usd':'0.10','wall_seconds':3600,'execution_policy':{'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None},'new_conservative_upper':{'model':30,'reads':829,'login':40,'import':16,'publish':16,'key':16,'run':50},'environment_id':'202bfb35-2f92-47c1-bc1b-eac32082181d','workspace_id':'c3306c18-ceb2-4bee-b2d1-796ce2048f17','runtime_build':'0.357.0-c038db013b5e96bc4d3e','backend_path':str(PROJECT/'.runtime/snapshots/0.357.0-c038db013b5e96bc4d3e/backend')}
    for name in FROZEN:(tmp_path/name).write_text('{}' if name.endswith('.json') else 'PUBLIC UNIT FIXTURE','utf-8')
    def save():
        (tmp_path/'plan.json').write_text(json.dumps(plan),'utf-8')
        (tmp_path/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':'corrected-chatflow378','files':{name:sha(tmp_path/name) for name in FROZEN}}),'utf-8')
    save();return plan,save

@pytest.mark.parametrize('bad',['bool_limit','more_runs','wrong_workspace','wrong_backend','model_cost','longer_wall'])
def test_frozen_scope_cannot_be_silently_expanded(tmp_path,bad):
    plan,save=frozen(tmp_path);assert validated(tmp_path)==plan
    if bad=='bool_limit':plan['limits']['model']=False
    if bad=='more_runs':plan['limits']['run']=15
    if bad=='wrong_workspace':plan['workspace_id']=APP
    if bad=='wrong_backend':plan['backend_path']='C:\\some-other-backend'
    if bad=='model_cost':plan['model_estimate_book_upper_usd']='1.0'
    if bad=='longer_wall':plan['wall_seconds']=7200
    save()
    with pytest.raises(RuntimeError):validated(tmp_path)

def test_no_approval_no_source_live_and_no_second_claim(tmp_path):
    plan,_=frozen(tmp_path)
    with pytest.raises(FileNotFoundError):approved(tmp_path,plan)
    with pytest.raises(RuntimeError):authorized(SOURCE,plan)
    assert not (tmp_path/'attempt.json').exists() and not (tmp_path/'worker-started.json').exists()
    claim(tmp_path,{'state':'admitted'})
    with pytest.raises(FileExistsError):claim(tmp_path,{'state':'admitted'})

def test_source_and_duplicate_json_tampering_rejected(tmp_path):
    frozen(tmp_path);(tmp_path/'worker.py').write_text('CHANGED','utf-8')
    with pytest.raises(RuntimeError):validated(tmp_path)
    path=tmp_path/'duplicate.json';path.write_text('{"decision":"approve","decision":"reject"}','utf-8')
    with pytest.raises(RuntimeError):load(path)

def test_original_objects_credentials_and_assets_guarded(tmp_path,gate):
    from app.storage import Store
    base=Store(tmp_path);base.put('task',OLD,{'id':OLD,'status':'unknown'});base.set_secret(OLD,'api_key','PUBLIC_OLD_UNIT')
    base.put('environment',gate.env['id'],gate.env);(tmp_path/'old-asset.txt').write_text('PUBLIC OLD ASSET','utf-8');old=capture(base)
    contract={'configuration':{},'original':{'plan':{}},'modified':{'plan':{}}}
    G=guarded(Store,gate.env,gate.f,contract,gate,old);store=G(tmp_path)
    with pytest.raises(RuntimeError):store.put('task',OLD,{'id':OLD,'status':'success'})
    with pytest.raises(RuntimeError):store.set_secret(OLD,'api_key','CHANGED')
    with pytest.raises(RuntimeError):store.secret(OLD,'api_key')
    with pytest.raises(RuntimeError):store.set_secret(gate.env['id'],'console_token','UNVERIFIED')
    assert verify(store,gate.env,gate,old)['original_objects_kept']
    (tmp_path/'old-asset.txt').write_text('CHANGED','utf-8')
    with pytest.raises(RuntimeError):verify(store,gate.env,gate,old)

def test_legacy_import_app_only_in_result_is_still_an_old_resource(tmp_path):
    from app.storage import Store
    store=Store(tmp_path);store.put('task','public-old-task',{'id':'public-old-task','runs':[{'kind':'import','result':{'app_id':OLD}}]})
    assert OLD in known_apps(store)
