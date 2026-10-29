"""Independent failed-case evidence scope. Public data only, no production HTTP."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import httpx
import pytest

SOURCE=Path(__file__).resolve().parents[2]/'tools/first-case-trace376'
sys.path.insert(0,str(SOURCE))
sys.path.append(str(SOURCE.parents[1]/'backend'))
from probe import Boundary,metadata,protected
from support import LIMITS,PROJECT,sha,load
from execute import TARGET,UPPER,REGRANT,FROZEN,validated,approved,authorized,claim

BASE='https://public-dify.invalid'
DOC='11111111-2222-4222-8222-111111111111'
NATIVE='22222222-2222-4222-8222-111111111111'

@pytest.fixture
def gate():return Boundary(copy.deepcopy(TARGET),{'id':TARGET['environment_id'],'base_url':BASE},{})

def request(path,body=None,method=None,base=BASE):return httpx.Request(method or ('POST' if body is not None else 'GET'),base+path,json=body)

def ready(b,phase='diagnose'):
    b.phase=phase;b.workspace_verified=True;b.counts.update(reads=2,login=1);b.native=NATIVE
    if phase=='metadata':b.counts['reads']=6;b.trace_reads=4

@pytest.mark.parametrize('path,base,method,body',[
    ('/v1/chat-messages',BASE,'POST',{}),
    ('/v1/chat/completions','https://api.deepseek.com','POST',{}),
    ('/console/api/apps',BASE,'POST',{}),
    ('/console/api/apps/'+TARGET['app_id']+'/api-keys',BASE,'POST',{}),
    ('/console/api/datasets/'+TARGET['dataset_id'],BASE,'DELETE',None),
    ('/console/api/login?extra=1',BASE,'POST',{}),
    ('/console/api/apps?page=1&limit=1','https://elsewhere.invalid','GET',None),
])
def test_other_operations_never_dispatch(gate,path,base,method,body):
    with pytest.raises(RuntimeError):gate.admit(request(path,body,method,base))
    assert not any(gate.counts.values()) and not gate.record['dispatches']

def test_native_unread_cookies_and_no_second_login(gate):
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):yield b'{"result":"success"}'
    async def send(req):return httpx.Response(200,headers=[('set-cookie','access_token=PUBLIC_ACCESS; Path=/'),('set-cookie','csrf_token=PUBLIC_CSRF; Path=/')],stream=Stream())
    req=request('/console/api/login',{'email':'public@example.invalid','password':'PUBLIC_ONLY','remember_me':False})
    response=asyncio.run(gate.dispatch(send,req))
    assert response.is_stream_consumed and gate.tokens=={'console_token':'PUBLIC_ACCESS','csrf_token':'PUBLIC_CSRF'} and not gate.workspace_verified
    with pytest.raises(RuntimeError):asyncio.run(gate.dispatch(send,req))
    assert gate.halted and gate.counts['login']==1

def test_connection_failure_counts_once_and_cannot_retry(gate):
    ready(gate);calls=[]
    async def broken(req):calls.append(req);raise httpx.ReadError('PUBLIC interruption')
    req=request('/console/api/apps/'+TARGET['app_id']+'/messages/'+TARGET['message_id'])
    with pytest.raises(httpx.ReadError):asyncio.run(gate.dispatch(broken,req))
    with pytest.raises(RuntimeError):asyncio.run(gate.dispatch(broken,req))
    assert len(calls)==1 and gate.counts['reads']==3

@pytest.mark.parametrize('change',['origin','old_app','out_of_order','query','body','expired','cap','source_changed'])
def test_exact_source_and_deadline_before_dispatch(gate,change):
    ready(gate);path='/console/api/apps/'+TARGET['app_id']+'/messages/'+TARGET['message_id'];base=BASE;body=None
    if change=='origin':base='https://elsewhere.invalid'
    if change=='old_app':path=path.replace(TARGET['app_id'],DOC)
    if change=='out_of_order':path='/console/api/apps/'+TARGET['app_id']+'/workflow-runs/'+NATIVE
    if change=='query':path+='?page=2'
    if change=='body':body={}
    if change=='expired':gate.started-=601
    if change=='cap':gate.counts['reads']=10
    if change=='source_changed':gate.source_current=lambda:(_ for _ in ()).throw(RuntimeError('Changed'))
    before=copy.deepcopy(gate.counts)
    with pytest.raises(RuntimeError):gate.admit(request(path,body,'GET',base))
    assert gate.counts==before and not gate.record['dispatches']

@pytest.mark.parametrize('field,value',[('id',DOC),('conversation_id',DOC),('workflow_run_id','not-uuid')])
def test_message_identity_cannot_resolve_another_run(gate,field,value):
    data={'id':TARGET['message_id'],'conversation_id':TARGET['conversation_id'],'workflow_run_id':NATIVE};data[field]=value
    with pytest.raises(RuntimeError):gate.observed({'path':'/console/api/apps/'+TARGET['app_id']+'/messages/'+TARGET['message_id'],'kind':'reads'},httpx.Response(200,json=data))
    assert gate.native is None

@pytest.mark.parametrize('bad',['page','limit','duplicate','bad_id','too_many'])
def test_document_page_cannot_expand_or_change_identity(gate,bad):
    ready(gate,'metadata');data={'page':1,'limit':2,'data':[{'id':DOC}]}
    if bad=='page':data['page']=2
    if bad=='limit':data['limit']=20
    if bad=='duplicate':data['data']*=2
    if bad=='bad_id':data['data'][0]['id']='bad'
    if bad=='too_many':data['data']*=3
    with pytest.raises(RuntimeError):gate.observed({'path':'/console/api/datasets/'+TARGET['dataset_id']+'/documents','kind':'reads'},httpx.Response(200,json=data))

def test_document_status_requires_returned_ids_in_order_and_once(gate):
    ready(gate,'metadata');gate.metadata_reads=2;gate.documents=[DOC]
    prefix='/console/api/datasets/'+TARGET['dataset_id']+'/documents/'
    with pytest.raises(RuntimeError):gate.admit(request(prefix+NATIVE+'/indexing-status'))
    assert gate.admit(request(prefix+DOC+'/indexing-status'))['kind']=='reads'
    with pytest.raises(RuntimeError):gate.admit(request(prefix+DOC+'/indexing-status'))
    assert gate.read_documents==[DOC] and gate.counts['reads']==7

def test_metadata_does_not_store_names_content_errors_or_arbitrary_status():
    result=metadata({'indexing_status':'completed','error':'PRIVATE_KEY','word_count':-1,'name':'PRIVATE_NAME','text':'PRIVATE_CONTENT','enabled':True,'permission':'customer@example.invalid'},['indexing_status','word_count','enabled','permission'])
    assert result=={'indexing_status':'completed','word_count':None,'enabled':True,'permission':None,'error_present':True}

def frozen(root):
    plan={'batch_id':'first-case-trace376','limits':copy.deepcopy(LIMITS),'explicit_regrant':copy.deepcopy(REGRANT),'conservative_upper':copy.deepcopy(UPPER),'wall_seconds':600,'model_estimate_book_upper_usd':'0.755473652','old_reservations_preserved':True,'runtime_build':'0.356.0-5476d30269eac2811387','backend_path':str(PROJECT/'.runtime/snapshots/0.356.0-5476d30269eac2811387/backend')}
    for name in FROZEN:(root/name).write_text('{}' if name.endswith('.json') else 'PUBLIC ONLY','utf-8')
    (root/'target.json').write_text(json.dumps(TARGET),'utf-8')
    def save():
        (root/'plan.json').write_text(json.dumps(plan),'utf-8')
        (root/'manifest.json').write_text(json.dumps({'schema_version':1,'batch_id':plan['batch_id'],'files':{n:sha(root/n) for n in FROZEN}}),'utf-8')
    save();return plan,save

@pytest.mark.parametrize('change',['read_cap','service','login_bool','regrant_bool','regrant_count','runtime','wall','old_reservations','tamper'])
def test_frozen_scope_cannot_change(tmp_path,change):
    plan,save=frozen(tmp_path);assert validated(tmp_path)==plan
    if change=='read_cap':plan['limits']['reads']=11
    if change=='service':plan['limits']['run']=1
    if change=='login_bool':plan['limits']['login']=True
    if change=='regrant_bool':plan['explicit_regrant']['new_login']=True
    if change=='regrant_count':plan['explicit_regrant']['reads']=11
    if change=='runtime':plan['backend_path']='C:/other/backend'
    if change=='wall':plan['wall_seconds']=1200
    if change=='old_reservations':plan['old_reservations_preserved']=False
    save()
    if change=='tamper':(tmp_path/'probe.py').write_text('changed')
    with pytest.raises(RuntimeError):validated(tmp_path)

def test_no_approval_no_tools_live_no_second_claim(tmp_path):
    plan,_=frozen(tmp_path)
    with pytest.raises(FileNotFoundError):approved(tmp_path,plan)
    with pytest.raises(RuntimeError):authorized(SOURCE,plan)
    claim(tmp_path,{'state':'stopped'})
    with pytest.raises(FileExistsError):claim(tmp_path,{'state':'admitted'})

def test_protected_store_rejects_old_business_secret_and_delete():
    task={'id':TARGET['task_id'],'runs':[{'id':TARGET['run_id'],'result':{'answer':'ORIGINAL'},'evaluation':{'status':'failed'}}]};env={'id':TARGET['environment_id'],'service_app_id':TARGET['app_id']};b=Boundary(TARGET,env,{})
    class Base:
        def _put_object(self,*args):return 'written'
    G,_=protected(Base,task,env,b,{'objects':{}});store=G();changed=copy.deepcopy(task);changed['runs'][0]['result']['answer']='different'
    with pytest.raises(RuntimeError):store._put_object(None,None,'task',task['id'],changed)
    with pytest.raises(RuntimeError):store._put_object(None,None,'environment',env['id'],env|{'service_app_id':DOC})
    with pytest.raises(RuntimeError):store.check_secrets({env['id']:{'console_token':'PUBLIC'}})
    b.workspace_verified=True;b.tokens={'console_token':'PUBLIC','csrf_token':'PUBLIC_CSRF'}
    with pytest.raises(RuntimeError):store.check_secrets({env['id']:{'service_api_key':'PUBLIC'}})
    with pytest.raises(RuntimeError):store.delete('task',task['id'])

def test_strict_json_no_duplicate_or_nonfinite(tmp_path):
    path=tmp_path/'value.json'
    for value in ('{"reads":1,"reads":2}','{"reads":NaN}'):
        path.write_text(value)
        with pytest.raises(RuntimeError):load(path)
