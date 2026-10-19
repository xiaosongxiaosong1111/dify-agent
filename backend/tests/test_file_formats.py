import base64,copy,json,uuid
import pytest,yaml
from test_api import client,create
from test_runtime_files import ready,prepare as upload_prepare,execute as upload_execute,receipt,OWNER,REMOTE
from test_file_run import plan,run,remote
from test_file_inputs import plan as extraction_plan
from test_file_model_run import model_document,MODEL
from test_file_join import POLICY,ACKS
from test_workflow_plan import plan_task
from app import main
from app.file_formats import FORMATS,descriptor,extensions,extraction
from app.file_join import template
from app.file_run import KIND,plan_token
from app.workflow_plan import compile_workflow_plan

CONTENT={'.txt':b'hello','.md':b'# Header\nhello','.csv':b'name,value\nx,01\n','.json':b'{"name":"x","value":1}', '.yaml':b'name: x\nvalue: 1\n','.yml':b'name: x\nvalue: 1\n'}

def setup(client,route):
 kind='file-list' if route in ('list','joined') else 'file';t,env=ready(client,kind)
 if route=='model':root=yaml.safe_load(model_document())
 else:
  p=template(POLICY,list(FORMATS)) if route=='joined' else extraction_plan(kind)
  if route=='joined':p['nodes'][3]['config']['model']=copy.deepcopy(MODEL)
  text,checked=compile_workflow_plan(plan_task(p));assert checked['valid'];root=yaml.safe_load(text)
 root['workflow']['graph']['nodes'][0]['data']['variables'][0]['allowed_file_extensions']=[*FORMATS,'.pdf','.docx']
 main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8');main.store.set_secret(env['id'],'console_token','fixture-console-token')
 return t,env

def upload(client,monkeypatch,t,ext,remote_id=REMOTE):
 content=CONTENT.get(ext,b'isolated unsupported format');name='sample'+ext
 async def request(*a):return {**receipt(name,len(content)),'id':remote_id}
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',request)
 p=upload_prepare(client,t,filename=name,content_base64=base64.b64encode(content).decode()).json();r=upload_execute(client,t,p);assert r.status_code==200,r.text
 return p

@pytest.mark.parametrize('ext',list(FORMATS))
@pytest.mark.parametrize('route',['pure','model','joined'])
def test_supported_formats_get_exact_frozen_parser_disclosure_and_single_mock_run(client,monkeypatch,ext,route):
 t,env=setup(client,route);p=upload(client,monkeypatch,t,ext);ref={'sierra_file_id':p['id']};values={'document':[ref] if route=='joined' else ref}
 if route!='pure':values['question']='隔离问题'
 before=copy.deepcopy(main.get_task(t['id']));q=plan(client,t,p,values);assert q.status_code==200,q.text;q=q.json();flow=q['data_flow'];info=flow['extraction']
 assert q['plan_schema_version']==4 and flow['schema_version']==3 and flow['scenario']==('document_extraction' if route=='pure' else 'document_list_model' if route=='joined' else 'document_model')
 assert info['files']==[{'position':1,'record_id':p['id'],**descriptor('sample'+ext)}] and info['verification']=='pinned_source_behavior_only'
 assert info['content_verified'] is info['live_parser_verified'] is False and main.get_task(t['id'])==before
 assert REMOTE not in json.dumps(q) and OWNER not in json.dumps(q) and CONTENT[ext].decode() not in json.dumps(q)
 calls,_=remote(monkeypatch,t,env);r=run(client,t,q,**(ACKS if route!='pure' else {}));assert r.status_code==200,r.text
 assert [c[0] for c in calls]==['keys','published','run'] and r.json()['task']['runs'][-1]['input']==values
 assert run(client,t,q,**(ACKS if route!='pure' else {})).status_code==409

def test_local_parser_preview_does_not_read_body_decrypt_or_call_services(client,monkeypatch):
 t,_=setup(client,'model');p=upload(client,monkeypatch,t,'.json');before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('解析计划不读正文、不解密、不联网或调用模型')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 r=plan(client,t,p,{'document':{'sierra_file_id':p['id']},'question':'fixture'});assert r.status_code==200,r.text
 info=r.json()['data_flow']['extraction'];assert '重复键' in info['files'][0]['behavior'] and '精度' in info['files'][0]['behavior'] and main.get_task(t['id'])==before

def test_mixed_format_list_keeps_order_repeated_records_and_empty_scope(client,monkeypatch):
 t,env=setup(client,'list');a=upload(client,monkeypatch,t,'.md');b=upload(client,monkeypatch,t,'.csv',str(uuid.uuid4()))
 refs=[{'sierra_file_id':r['id']} for r in (b,a,b)];q=plan(client,t,a,{'document':refs}).json();info=q['data_flow']['extraction']
 assert [r['record_id'] for r in info['files']]==[b['id'],a['id'],b['id']] and [r['extension'] for r in info['files']]==['.csv','.md','.csv']
 empty=plan(client,t,a,{'document':[]});assert empty.status_code==200 and empty.json()['data_flow']['extraction']['files']==[]

@pytest.mark.parametrize('ext',['.pdf','.docx'])
def test_upload_support_is_not_automatic_parser_authorization(client,monkeypatch,ext):
 t,env=setup(client,'pure');p=upload(client,monkeypatch,t,ext);calls,_=remote(monkeypatch,t,env);r=plan(client,t,p)
 assert r.status_code==422 and '不运行' in r.text and not calls and not main.store.list(KIND)

@pytest.mark.parametrize('mutation',['parser','behavior','position','extension','baseline'])
def test_modified_extraction_plan_cannot_reuse_original_or_recomputed_approval(client,monkeypatch,mutation):
 t,env=setup(client,'model');p=upload(client,monkeypatch,t,'.json');q=plan(client,t,p,{'document':{'sierra_file_id':p['id']},'question':'fixture'}).json();row=main.store.get(KIND,q['id']);info=row['data_flow']['extraction']
 if mutation=='baseline':info['graphon_version']='unknown'
 else:info['files'][0][mutation]={'parser':'plain_text','behavior':'完全保真','position':2,'extension':'.txt'}[mutation]
 row['resource_token']=plan_token(row);main.store.put(KIND,q['id'],row);q['resource_token']=row['resource_token'];calls,_=remote(monkeypatch,t,env)
 assert run(client,t,q,**ACKS).status_code==409 and not calls and not main.get_task(t['id'])['runs']

def test_schema_three_approval_stays_history_only_after_format_expansion(client,monkeypatch):
 t,env=setup(client,'pure');p=upload(client,monkeypatch,t,'.txt');q=plan(client,t,p).json();row=main.store.get(KIND,q['id']);row['plan_schema_version']=3;row['data_flow'].update(schema_version=2,scenario='txt_extraction');row['data_flow'].pop('extraction');row['resource_token']=plan_token(row);main.store.put(KIND,q['id'],row);q['resource_token']=row['resource_token'];calls,_=remote(monkeypatch,t,env)
 assert client.get(f"/api/tasks/{t['id']}/file-runs").status_code==200
 assert run(client,t,q).status_code==409 and not calls

@pytest.mark.parametrize('value',[[],None,['.PDF'],['.md','.md'],['.txt','.pdf'],['.json',False],['.csv',{}]],ids=['empty','null','unknown','duplicate','mixed-unsupported','bool','object'])
def test_format_scope_never_silently_defaults_or_filters(value):
 with pytest.raises(ValueError):extensions(value)

def test_template_api_explicit_extension_scope_and_invalid_policy_preserve_task(client):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));url=f"/api/tasks/{t['id']}/file-join-template"
 r=client.post(url,json={'revision':t['revision'],'policy':POLICY,'extensions':['.md','.json']});assert r.status_code==200,r.text
 assert r.json()['extensions']==['.md','.json'] and r.json()['plan']['nodes'][0]['config']['variables'][0]['allowed_file_extensions']==['.md','.json']
 for value in ([],['.txt','.pdf'],['.csv','.csv']):assert client.post(url,json={'revision':t['revision'],'policy':POLICY,'extensions':value}).status_code==422
 assert main.get_task(t['id'])==before
