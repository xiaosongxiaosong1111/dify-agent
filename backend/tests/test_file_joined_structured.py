import copy,hashlib,json
import pytest,yaml
from test_api import client,create
from test_file_join import POLICY,ACKS
from test_file_model_run import MODEL
from test_file_structured_run import shape,result
from test_runtime_files import ready,prepare as upload_prepare,execute as upload_execute,receipt,REMOTE
from test_file_run import plan,run,remote
from test_workflow_plan import plan_task
from app import main
from app.file_run import KIND,plan_token
from app.file_structured_template import joined_template
from app.file_join import read_code
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved
from app.file_run_flow import describe

def post(client,t,text=None,**patch):
 return client.post(f"/api/tasks/{t['id']}/file-joined-structured-template",content=json.dumps({'revision':t['revision'],'schema_text':json.dumps(shape(),ensure_ascii=False) if text is None else text,'policy':POLICY,'extensions':['.txt'],**patch},ensure_ascii=True),headers={'content-type':'application/json'})

def uploaded(client,monkeypatch,**policy_patch):
 t,env=ready(client,'file-list');p=joined_template(json.dumps(shape()),{**POLICY,**policy_patch},['.txt']);p['nodes'][3]['config']['model']=copy.deepcopy(MODEL)
 text,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked;root=yaml.safe_load(text);main.artifact_path(t).write_text(text,encoding='utf-8');main.store.set_secret(env['id'],'console_token','fixture-console-token')
 async def upload(*args):return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload);u=upload_prepare(client,t).json();r=upload_execute(client,t,u);assert r.status_code==200,r.text
 return t,env,u,root

def values(p,empty=False):return {'document':[] if empty else [{'sierra_file_id':p['id']}]*2,'question':'按明确规则合并资料提取一个对象'}

def test_template_is_local_unsaved_full_schema_and_original_join_code_without_model_selection(client,monkeypatch):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));s=shape();s['properties']['amount']['maximum']=900719925474099312345678901;text=json.dumps(s,ensure_ascii=False)
 def forbidden(*args,**kwargs):pytest.fail('起步不能存任务、解密、联网或调用模型')
 monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 r=post(client,t,text,extensions=['.md','.csv']);assert r.status_code==200,r.text;v=r.json();p=json.loads(v['plan_text'])
 assert v['verification']=='local_joined_structured_file_draft_only' and all(v[k] is False for k in ('network_requested','model_called','task_changed','run_authorized'))
 assert v['policy']==POLICY and v['extensions']==['.md','.csv'] and v['source_schema_sha256']==hashlib.sha256(text.encode()).hexdigest() and v['plan_sha256']==hashlib.sha256(v['plan_text'].encode()).hexdigest()
 assert read_code(p['nodes'][2]['config']['code'])==POLICY and hashlib.sha256(p['nodes'][2]['config']['code'].encode()).hexdigest()==v['join_code_sha256']
 assert p['nodes'][3]['config']['structured_output']['schema']==s and '900719925474099312345678901' in v['plan_text'] and 'model' not in p['nodes'][3]['config'] and p['nodes'][-1]['config']['outputs'][0]['value_selector']==['answer_llm','structured_output']
 assert main.get_task(t['id'])==before

@pytest.mark.parametrize('ext',[['.txt'],['.json','.yaml','.yml','.csv','.md']])
def test_generated_plan_compiles_to_five_node_native_preserved_flow7(ext):
 p=joined_template(json.dumps(shape()),POLICY,ext);before=copy.deepcopy(p);text,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked;root=yaml.safe_load(text);assert validate_preserved(root)['valid'] and p==before
 f=describe(root);assert f['schema_version']==7 and f['scenario']=='document_list_model_object' and f['node_types']==['start','document-extractor','code','llm','end'] and f['output_kind']=='json-object' and f['planned_llm_node_executions']==1
 assert f['join_policy']['policy']==POLICY and f['structured_output']['schema']==shape() and f.get('strict_guard') is None

@pytest.mark.parametrize('patch',[{'policy':{}},{'policy':{**POLICY,'max_files':True}},{'policy':{**POLICY,'empty_list':'skip'}},{'extensions':[]},{'extensions':['.pdf']},{'schema_text':'{}'},{'schema_text':'{"type":"object","type":"array"}'},{'schema_text':'\ud800'}],ids=['missing-policy','bool-count','skip','empty-extensions','pdf','empty-schema','duplicate-schema','surrogate'])
def test_bad_inputs_do_not_fill_missing_policy_or_change_task(client,patch):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));assert post(client,t,**patch).status_code==422 and main.get_task(t['id'])==before

@pytest.mark.parametrize('key',['workflow_plan','artifact','dify_app_id','dsl_reference','revision','app_type'])
def test_existing_work_wrong_type_or_revision_is_not_replaced(client,key):
 t=create(client,app_type='advanced-chat' if key=='app_type' else 'workflow')
 if key not in ('revision','app_type'):t[key]={'existing':True};main.save_task(t)
 before=copy.deepcopy(main.get_task(t['id']));r=post(client,t,**({'revision':t['revision']+1} if key=='revision' else {}));assert r.status_code in {409,422} and main.get_task(t['id'])==before

@pytest.mark.parametrize('empty',[False,True])
def test_approved_list_object_runs_once_keeps_duplicate_positions_and_declared_empty_policy(client,monkeypatch,empty):
 t,env,u,root=uploaded(client,monkeypatch,empty_list='empty_text' if empty else 'fail');v=values(u,empty);r=plan(client,t,u,v);assert r.status_code==200,r.text;q=r.json();f=q['data_flow'];assert q['plan_schema_version']==8 and f['schema_version']==7 and f['join_policy']['policy']['empty_list']==('empty_text' if empty else 'fail')
 assert len(q['files'])==(0 if empty else 2) and len(f['extraction']['files'])==(0 if empty else 2)
 output={'customer':'甲','approved':False};calls,_=remote(monkeypatch,t,env,result=result(output));r=run(client,t,q,**ACKS);assert r.status_code==200,r.text
 assert r.json()['task']['runs'][-1]['input']==v and r.json()['task']['runs'][-1]['result']['data']['outputs']=={'result':output}
 assert calls[-1][1]['document']==([] if empty else [{'type':'document','transfer_method':'local_file','upload_file_id':REMOTE}]*2) and [c[0] for c in calls]==['keys','published','run'] and run(client,t,q,**ACKS).status_code==409

@pytest.mark.parametrize('missing',['acknowledge_model_egress','acknowledge_unpriced_model_cost','acknowledge_join_policy'])
def test_model_cost_and_join_approvals_are_not_inferred_from_new_object_scope(client,monkeypatch,missing):
 t,env,u,_=uploaded(client,monkeypatch);q=plan(client,t,u,values(u)).json();calls,_=remote(monkeypatch,t,env);assert run(client,t,q,**{**ACKS,missing:False}).status_code==422 and not calls

def test_old_scope_cannot_expand_to_list_objects_even_with_new_checks(client,monkeypatch):
 t,env,u,_=uploaded(client,monkeypatch);q=plan(client,t,u,values(u)).json();p=main.store.get(KIND,q['id']);p['plan_schema_version']=6;p['resource_token']=plan_token(p);main.store.put(KIND,p['id'],p);calls,_=remote(monkeypatch,t,env)
 assert run(client,t,p,**ACKS).status_code==409 and not calls

def test_invalid_list_object_is_not_repaired_or_retained_and_bad_join_code_is_never_run(client,monkeypatch):
 t,env,u,root=uploaded(client,monkeypatch);q=plan(client,t,u,values(u)).json();calls,_=remote(monkeypatch,t,env,result=result({'customer':'甲','approved':'private-value'}));r=run(client,t,q,**ACKS)
 assert r.status_code==502 and 'private-value' not in r.text and len(calls)==3 and main.store.get(KIND,q['id'])['state']=='unknown' and 'outputs' not in main.get_task(t['id'])['runs'][-1]['result']['data']
 root['workflow']['graph']['nodes'][2]['data']['code']+='\n# changed';before=copy.deepcopy(root)
 with pytest.raises(ValueError):describe(root)
 assert root==before

def test_fixed_list_object_evidence_requires_original_join_approval(client,monkeypatch):
 t,env,u,_=uploaded(client,monkeypatch);v=values(u);c=client.post(f"/api/tasks/{t['id']}/file-cases/capture",json={'revision':t['revision'],'catalog_revision':0,'input_text':json.dumps(v),'name':'多文档对象','expectation':{'mode':'json_schema','target':'result','expected':shape()}});assert c.status_code==200,c.text;case=c.json()
 q=client.post(f"/api/tasks/{t['id']}/file-runs/prepare",json={'revision':t['revision'],'input_text':json.dumps(v),'case_id':case['saved_case_id'],'case_catalog_revision':1}).json();remote(monkeypatch,t,env,result=result({'customer':'甲','approved':True}));r=run(client,t,q,**ACKS);assert r.status_code==200,r.text;record=r.json()['task']['runs'][-1]
 url=f"/api/tasks/{t['id']}/file-cases/runs/{record['id']}/evidence";assert client.get(url).status_code==200
 row=main.store.get(KIND,q['id']);row['join_policy_approved']=False;main.store.put(KIND,row['id'],row);assert client.get(url).status_code==422
