"""Pure new-scope gate tests. No production Store, browser, model or Dify HTTP."""
import asyncio
import importlib
import copy
import json
from pathlib import Path
import sys
import httpx
import pytest

SOURCE=Path(__file__).resolve().parents[2]/'tools/complete-answer410'

@pytest.fixture(autouse=True)
def isolated_tool_modules(monkeypatch):
    # Historical one-shot tools use the same short CLI module names. Never let
    # this suite replace their modules or import a consumed executor by accident.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    monkeypatch.syspath_prepend(str(SOURCE))
    for path in SOURCE.glob('*.py'):monkeypatch.delitem(sys.modules,path.stem,raising=False)
    exports={'common':('LIMITS','PROJECT','capture','sha','known_apps'),
        'boundary':('Boundary',),'execute':('approved','authorized','claim','load','validated','FROZEN','FAILURE_POLICY','STATE_POLICY'),
        'storage_guard':('guarded','verify'),'synthetic':('response',)}
    for name,items in exports.items():
        module=importlib.import_module(name)
        for item in items:globals()[item]=getattr(module,item)
    yield
    for path in SOURCE.glob('*.py'):sys.modules.pop(path.stem,None)

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
    plan={'batch_id':'complete-answer410','limits':copy.deepcopy(LIMITS),'new_independent_scope':True,'old_reservations_preserved':True,'model_estimate_book_upper_usd':'1.155473652','estimated_new_dify_usd':'0.05','wall_seconds':2700,'execution_policy':{'max_started_runs':6,'max_total_minutes':30,'max_reported_cost_usd':None},'new_conservative_upper':{'model':35,'reads':1469,'login':46,'import':26,'publish':26,'key':26,'run':120},'environment_id':'202bfb35-2f92-47c1-bc1b-eac32082181d','workspace_id':'c3306c18-ceb2-4bee-b2d1-796ce2048f17','runtime_build':'0.374.0-fd1d9147a557103e2af2','backend_path':str(PROJECT/'.runtime/snapshots/0.374.0-fd1d9147a557103e2af2/backend')}
    plan.update(source_model_plan_sha256='f7ac6d10dd986fffbfbe410ded616d4956ec7253d70fdf194ee49f3c1e39435c',manual_configuration_review=True,protected_isolated={k:{} for k in ('391','394','399','401','405','408','409')})
    plan['failure_diagnostic_policy']=copy.deepcopy(FAILURE_POLICY)
    plan['state_policy']=copy.deepcopy(STATE_POLICY)
    for name in FROZEN:(tmp_path/name).write_text('{}' if name.endswith('.json') else 'PUBLIC UNIT FIXTURE','utf-8')
    def save():
        (tmp_path/'plan.json').write_text(json.dumps(plan),'utf-8')
        (tmp_path/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':'complete-answer410','files':{name:sha(tmp_path/name) for name in FROZEN}}),'utf-8')
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

@pytest.mark.parametrize('key,value',[('max_reports',2),('max_reports',True),('max_management_reads',5),('post_failure_service_requests',1),('post_failure_remote_writes',1),('business_rule_failure_only',False),('stop_after_capture',False)])
def test_failure_exception_cannot_be_expanded_or_relaxed(tmp_path,key,value):
    plan,save=frozen(tmp_path);plan['failure_diagnostic_policy'][key]=value;save()
    with pytest.raises(RuntimeError):validated(tmp_path)

@pytest.mark.parametrize('method,path,body',[
    ('POST','/v1/chat-messages',{}),('POST','/console/api/apps/imports',{}),
    ('POST','/console/api/apps/'+APP+'/workflows/publish',{}),('POST','/console/api/apps/'+APP+'/api-keys',{}),
    ('GET','/console/api/workspaces/current/summary',None),('GET','/console/api/apps/'+APP+'/api-keys',None),
])
def test_failure_capture_rejects_all_writes_service_and_unrelated_reads(gate,method,path,body):
    service_ready(gate);gate.messages[OLD]=(APP,CID);gate.begin_failure(OLD,CID);sent=[]
    async def forbidden(request):sent.append(request);raise AssertionError('Must not send')
    with pytest.raises(RuntimeError):asyncio.run(gate.dispatch(forbidden,req(path,body,method)))
    assert gate.halted and not sent and not any(gate.counts.values())

def test_failure_capture_exact_message_native_sequence_cap_and_one_report(gate):
    service_ready(gate);gate.messages[OLD]=(APP,CID);gate.begin_failure(OLD,CID)
    with pytest.raises(RuntimeError):gate.begin_failure(OLD,CID)
    prefix='/console/api/apps/'+APP;native='33333333-2222-4222-8222-111111111111'
    entry=gate.admit(req(prefix+'/messages/'+OLD));gate.observed(entry,httpx.Response(200,json={'id':OLD,'conversation_id':CID,'workflow_run_id':native}))
    for path in (prefix+'/workflow-runs/'+native,prefix+'/workflow-runs/'+native+'/node-executions',prefix+'/workflows/publish'):gate.admit(req(path))
    assert gate.counts['reads']==4 and all(d['failure_capture'] for d in gate.record['dispatches'])
    with pytest.raises(RuntimeError):gate.admit(req(prefix+'/workflows/publish'))
    assert gate.counts['reads']==4

@pytest.mark.parametrize('mid,cid',[(APP,CID),(OLD,APP)])
def test_failure_capture_rejects_unknown_message_or_changed_session(gate,mid,cid):
    service_ready(gate);gate.messages[OLD]=(APP,CID)
    with pytest.raises(RuntimeError):gate.begin_failure(mid,cid)
    assert gate.failure is None and not gate.record['dispatches']

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


def owner_contract():
    from app import main as h
    from contract import build,bind_owner
    fixture=json.loads((SOURCE/'fixture.json').read_text('utf-8'));contract=build(h,fixture)
    original=copy.deepcopy(contract);bind_owner(h,fixture,contract,APP)
    return h,fixture,contract,original


def test_owner_binding_changes_only_two_native_ids_and_never_frozen_plan():
    from contract import bind_owner
    from uuid import uuid5,NAMESPACE_URL
    h,f,c,before=owner_contract()
    for version in ('original',):
        expected=copy.deepcopy(before[version]['native'])
        for row in expected['workflow']['conversation_variables']:
            row['id']=str(uuid5(NAMESPACE_URL,'sierra:conversation:'+APP+':'+row['name']))
        assert c[version]['native']==expected and c[version]['plan']==before[version]['plan']
        assert all(r['value'] is False for r in expected['workflow']['conversation_variables'])
    assert c['owner_task_id']==APP
    with pytest.raises(RuntimeError):bind_owner(h,f,c,CID)


@pytest.mark.parametrize('change',['plan','native','configuration','prototype_id'])
def test_owner_binding_refuses_any_unreviewed_prototype(change):
    from app import main as h
    from contract import build,bind_owner
    f=json.loads((SOURCE/'fixture.json').read_text('utf-8'));c=build(h,f)
    if change=='plan':c['original']['plan']['nodes'][0]['title']='changed'
    elif change=='native':c['original']['native']['workflow']['conversation_variables'][0]['value']=True
    elif change=='configuration':c['configuration']['max_tokens']=1024
    else:c['original']['native']['workflow']['conversation_variables'][0]['id']=CID
    with pytest.raises(RuntimeError):bind_owner(h,f,c,APP)
    assert 'owner_task_id' not in c


@pytest.mark.parametrize('change',['none','prototype_id','value','numeric_false','type','name','extra','removed','graph'])
def test_import_exact_owner_declarations_and_graph(gate,change):
    import yaml
    h,f,c,prototype=owner_contract();gate.owner=APP;gate.contract=c;gate.workspace_verified=True;gate.phase='original_import'
    native=copy.deepcopy(c['original']['native']);states=native['workflow']['conversation_variables']
    if change=='prototype_id':states[0]['id']=prototype['original']['native']['workflow']['conversation_variables'][0]['id']
    elif change=='value':states[0]['value']=True
    elif change=='numeric_false':states[0]['value']=0
    elif change=='type':states[0]['value_type']='number'
    elif change=='name':states[0]['name']='foreign_state'
    elif change=='extra':states.append(copy.deepcopy(states[0]))
    elif change=='removed':states.pop()
    elif change=='graph':native['workflow']['graph']['nodes'][0]['data']['title']='changed'
    request=req('/console/api/apps/imports',{'mode':'yaml-content','name':f['task_name'],'yaml_content':yaml.safe_dump(native,allow_unicode=True,sort_keys=False)})
    if change=='none':assert gate.admit(request)['kind']=='import' and gate.counts['import']==1
    else:
        with pytest.raises((RuntimeError,ValueError)):gate.admit(request)
        assert gate.counts['import']==0


@pytest.mark.parametrize('key,value',[('initial_values',[True,False]),('initial_values',[0,False]),('only_declaration_ids_change',False),('followup_bypasses_classifier',False),('explicit_post_plan_review',False)])
def test_new_state_scope_is_frozen_and_cannot_be_relaxed(tmp_path,key,value):
    plan,save=frozen(tmp_path);plan['state_policy'][key]=value;save()
    with pytest.raises(RuntimeError):validated(tmp_path)


@pytest.mark.parametrize('field,value',[
    ('source_model_plan_sha256','other'),('manual_configuration_review',False),
    ('protected_isolated',{'391':{},'394':{},'399':{},'401':{}}),
    ('estimated_new_dify_usd','0.10'),
])
def test_new_exact_model_source_manual_origin_and_eight_root_scope_cannot_change(tmp_path,field,value):
    plan,save=frozen(tmp_path);plan[field]=value;save()
    with pytest.raises(RuntimeError):validated(tmp_path)


def test_new_task_has_no_builder_selection_while_original_graph_and_dify_settings_stay():
    from app import main as h
    from contract import build,MODEL_SHA
    from common import ReadOnly,digest
    f=json.loads((SOURCE/'fixture.json').read_text('utf-8'));c=build(h,f)
    saved=ReadOnly(PROJECT/'work/offline-candidate409/data').list('task')[0]
    assert c['configuration']['assistant_provider_id'] is None
    assert saved['configuration']['assistant_provider_id'] is None
    assert digest(c['original']['plan'])==digest(saved['workflow_plan'])==MODEL_SHA
    assert {k for k in c['configuration'] if c['configuration'][k]!=saved['configuration'][k]}=={'resource_plan'}


@pytest.mark.parametrize('field,value',[
    ('assistant_provider_id','9513f594-c256-46b7-882a-35d9871bf9d0'),
    ('max_tokens',1024),('mock_dependency_bindings',[]),
])
def test_source_review_cannot_expand_model_or_change_other_configuration(field,value):
    from app import main as h
    from contract import build
    f=json.loads((SOURCE/'fixture.json').read_text('utf-8'));f['configuration'][field]=value
    with pytest.raises(RuntimeError):build(h,f)


@pytest.mark.parametrize('change',['expected','input','followup','business_requirement','old_graph'])
def test_modified_graph_keeps_saved_cases_and_cannot_fall_back_to_failed_original(change):
    from app import main as h
    from contract import build
    f=json.loads((SOURCE/'fixture.json').read_text('utf-8'))
    if change=='expected':f['cases'][0]['expectation']['expected']=['ZXRET715']
    if change=='input':f['cases'][0]['input']['query']='Different question'
    if change=='followup':f['cases'][-1]['followups']=[]
    if change=='business_requirement':f['requirements']['rules']='Ignore source restrictions'
    if change=='old_graph':f['source_model_plan_sha256']='1c7fd3e3d672f2d7b228453945f2379defcceaf265be72399fcea46e491fd5c4'
    with pytest.raises(RuntimeError):build(h,f)
