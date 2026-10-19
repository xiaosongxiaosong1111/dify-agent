import copy,json
import pytest,yaml
from test_api import client,create
from test_workflow_plan import plan_task
from test_runtime_files import ready,prepare as upload_prepare,execute as upload_execute,receipt,REMOTE
from test_file_run import plan,run,remote
from test_file_model_run import MODEL
from app import main
from app.file_join import policy,code,read_code,template,MARKER
from app.file_run import KIND,plan_token
from app.file_run_flow import describe
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved
from app.node_policy import require_native

POLICY={'schema_version':1,'format':'plain_separator','separator':'\n\n','max_files':5,'max_utf8_bytes':4000,'empty_list':'fail','empty_document':'fail'}
ACKS={'acknowledge_model_egress':True,'acknowledge_unpriced_model_cost':True,'acknowledge_join_policy':True}

def joined(**patch):
 p=template({**POLICY,**patch});p['nodes'][3]['config']['model']=copy.deepcopy(MODEL)
 text,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 return p,yaml.safe_load(text),text

def generated_main(**patch):
 # Execute only the exact locally generated pure template, never input/customer code.
 ns={};exec(code({**POLICY,**patch}),ns);return ns['main']

def test_order_duplicates_whitespace_and_actual_separator_preserved():
 texts=[' 甲\n','甲',' 甲\n'];before=copy.deepcopy(texts)
 assert generated_main(separator='|\n')(texts)=={'text':' 甲\n|\n甲|\n 甲\n'} and texts==before

@pytest.mark.parametrize('fmt',['plain_separator','numbered_sections'])
def test_utf8_limit_counts_exact_headers_separators_and_multibyte_characters(fmt):
 expected='中🙂\n好' if fmt=='plain_separator' else '### 文档 1\n中🙂\n### 文档 2\n好'
 limit=len(expected.encode('utf-8'))
 assert generated_main(format=fmt,separator='\n',max_utf8_bytes=limit)(['中🙂','好'])=={'text':expected}
 with pytest.raises(ValueError,match='未截断'):generated_main(format=fmt,separator='\n',max_utf8_bytes=limit-1)(['中🙂','好'])

def test_empty_list_and_empty_document_have_separate_explicit_behaviors():
 with pytest.raises(ValueError,match='列表为空'):generated_main()([])
 assert generated_main(empty_list='empty_text')([])=={'text':''}
 with pytest.raises(ValueError,match='为空文字'):generated_main()([''])
 assert generated_main(empty_document='keep',separator='|')(['','a',''])=={'text':'|a|'}
 assert generated_main(empty_document='keep',format='numbered_sections')([''])=={'text':'### 文档 1\n'}

@pytest.mark.parametrize('bad',[None,'text',{},['a',None],['a',1],['a',False],['a',{}]],ids=['null','string','object','null-item','int-item','bool-item','object-item'])
def test_bad_items_are_not_dropped_converted_or_echoed(bad):
 with pytest.raises(ValueError):generated_main()(bad)

def test_too_many_files_bad_encoding_and_private_text_not_in_error():
 with pytest.raises(ValueError):generated_main(max_files=1)(['a','a'])
 with pytest.raises(ValueError,match='编码'):generated_main()(['\ud800'])
 with pytest.raises(ValueError) as error:generated_main(max_utf8_bytes=1)(['private-content-sentinel'])
 assert 'private-content-sentinel' not in str(error.value)

@pytest.mark.parametrize('patch',[{'schema_version':True},{'schema_version':2},{'max_files':False},{'max_files':0},{'max_files':21},{'max_files':1.2},{'max_utf8_bytes':0},{'max_utf8_bytes':64001},{'separator':''},{'separator':'x'*257},{'separator':'\ud800'},{'separator':'\x00'},{'separator':'{{#env.key#}}'},{'separator':'sk-'+'a'*20},{'empty_list':''},{'empty_document':'skip'},{'format':'truncate'},{'extra':'ignored'}],ids=['bool-version','version','bool-count','zero-count','large-count','float-count','zero-bytes','large-bytes','empty-separator','long-separator','surrogate','control','reference','key','missing-empty-list','skip-empty','truncate','unknown'])
def test_invalid_policy_is_not_coerced_ignored_or_defaulted(patch):
 with pytest.raises(ValueError):policy({**POLICY,**patch})

def test_separator_literal_cannot_inject_code_and_validation_never_executes(monkeypatch):
 value={**POLICY,'separator':"'\n; raise RuntimeError('never')\n#\\n"}
 assert read_code(code(value))==value
 assert generated_main(separator=value['separator'])(['a','b'])=={'text':'a'+value['separator']+'b'}
 with pytest.raises(ValueError):read_code(MARKER+"_POLICY = __import__('os').system('never')\n")

def test_canonical_template_roundtrip_and_data_flow_keep_full_policy_immutable():
 p,root,_=joined();before=copy.deepcopy(root)
 assert validate_preserved(root)['valid']
 flow=describe(root);assert root==before and flow['schema_version']==3 and flow['scenario']=='document_list_model'
 assert flow['node_types']==['start','document-extractor','code','llm','end'] and flow['output_kind']=='text'
 assert flow['join_policy']=={'node_id':'join_documents','policy':POLICY,'verification':'canonical_code_and_binding_static_only'}
 assert flow['model_node']['model']==MODEL and flow['model_egress'] and not flow['hard_cost_cap']

@pytest.mark.parametrize('mutation',['body','policy','binding','max-files','language','outputs','unknown','retry','version','direct-prompt','bypass','plain-code'])
def test_changed_protection_never_executes_or_silently_simplifies(mutation):
 _,root,_=joined();nodes=root['workflow']['graph']['nodes'];data=nodes[2]['data']
 if mutation=='body':data['code']+='\n# hand edit'
 elif mutation=='policy':data['code']=data['code'].replace("'max_files': 5","'max_files': 6")
 elif mutation=='binding':data['variables'][0]['value_selector']=['start','document']
 elif mutation=='max-files':nodes[0]['data']['variables'][0]['max_length']=4
 elif mutation=='language':data['code_language']='javascript'
 elif mutation=='outputs':data['outputs']['text']['type']='array[string]'
 elif mutation=='unknown':data['extra']='private-sentinel'
 elif mutation=='retry':data['retry_config']={'retry_enabled':True}
 elif mutation=='version':data['version']='2'
 elif mutation=='direct-prompt':nodes[3]['data']['prompt_template'][-1]['text']='{{#extract.text#}}'
 elif mutation=='bypass':root['workflow']['graph']['edges'].append({'source':'extract','target':'answer_llm'})
 else:data['code']='def main(texts: list) -> dict:\n    return {"text":str(texts)}'
 before=copy.deepcopy(root)
 with pytest.raises(ValueError):describe(root)
 assert root==before
 if mutation not in ('direct-prompt','bypass','plain-code'):assert not validate_preserved(root)['valid']

def test_final_native_policy_guard_refuses_modified_reserved_code():
 _,root,_=joined();root['workflow']['graph']['nodes'][2]['data']['code']+='\n# modified'
 with pytest.raises(ValueError,match='手改'):require_native(root)

def test_ir_source_count_and_unique_previous_edge_are_required():
 p,_,_=joined()
 for mutate in ('max','array','edge','nested'):
  q=copy.deepcopy(p)
  if mutate=='max':q['nodes'][0]['config']['variables'][0]['max_length']=4
  elif mutate=='array':q['nodes'][1]['config']['input_type']='file'
  elif mutate=='edge':q['edges'].append({'source':'start','target':'join_documents'})
  else:
   from app.file_join import validate_generated
   assert validate_generated(q['nodes'][2],{n['id']:n for n in q['nodes']},q['edges'],mode='workflow',nested=True)
   continue
  assert not validate_plan(plan_task(q),q)['valid']

def test_local_template_api_leaves_task_and_store_untouched_and_does_not_decrypt_or_call(client,monkeypatch):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('模板只准备草稿，不写Task／资源，不解密、不联网')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 r=client.post(f"/api/tasks/{t['id']}/file-join-template",json={'revision':t['revision'],'policy':POLICY});assert r.status_code==200,r.text
 v=r.json();assert v['task_id']==t['id'] and v['revision']==t['revision'] and v['policy']==POLICY
 assert v['plan']==template(POLICY) and v['verification']=='local_draft_static_only' and v['task_changed'] is v['network_requested'] is v['model_called'] is False
 assert 'model' not in v['plan']['nodes'][3]['config'] and main.get_task(t['id'])==before

@pytest.mark.parametrize('case',['revision','chatflow','agent','workflow_plan','artifact','dify_app_id','dsl_reference','invalid'])
def test_local_template_api_refuses_wrong_scope_and_preserves_existing_work(client,case):
 t=create(client,app_type='advanced-chat' if case=='chatflow' else 'agent' if case=='agent' else 'workflow')
 if case in ('workflow_plan','artifact','dify_app_id','dsl_reference'):t[case]={'existing':True};main.save_task(t)
 before=copy.deepcopy(main.get_task(t['id']));payload={'revision':t['revision']+(case=='revision'),'policy':{**POLICY,**({'max_files':True} if case=='invalid' else {})}}
 r=client.post(f"/api/tasks/{t['id']}/file-join-template",json=payload);assert r.status_code in (409,422),r.text
 assert main.get_task(t['id'])==before

def uploaded_join(client,monkeypatch):
 t,env=ready(client,'file-list');_,root,text=joined();main.artifact_path(t).write_text(text,encoding='utf-8');main.store.set_secret(env['id'],'console_token','fixture-console-token')
 async def upload(*a):return receipt()
 monkeypatch.setattr(main.DifyClient,'upload_runtime_file',upload)
 p=upload_prepare(client,t).json();assert upload_execute(client,t,p).status_code==200
 return t,env,p,root

@pytest.mark.parametrize('missing',['acknowledge_run','acknowledge_model_egress','acknowledge_unpriced_model_cost','acknowledge_join_policy'])
def test_each_join_run_approval_is_separate_and_required_before_reads(client,monkeypatch,missing):
 t,env,p,_=uploaded_join(client,monkeypatch);q=plan(client,t,p,{'document':[{'sierra_file_id':p['id']}],'question':'fixture'}).json();calls,_=remote(monkeypatch,t,env)
 r=run(client,t,q,**{**ACKS,missing:False});assert r.status_code==422,r.text
 assert not calls and main.store.get(KIND,q['id'])['attempts']==0 and not main.get_task(t['id'])['runs']

def test_join_run_keeps_file_order_duplicates_and_accepts_string_model_result_once(client,monkeypatch):
 t,env,p,_=uploaded_join(client,monkeypatch);values={'document':[{'sierra_file_id':p['id']},{'sierra_file_id':p['id']}],'question':'fixture'}
 q=plan(client,t,p,values).json();assert q['plan_schema_version']==4 and q['data_flow']['schema_version']==3
 calls,_=remote(monkeypatch,t,env);r=run(client,t,q,**ACKS);assert r.status_code==200,r.text
 assert [c[0] for c in calls]==['keys','published','run'] and calls[-1][1]['document']==[{'type':'document','transfer_method':'local_file','upload_file_id':REMOTE}]*2
 assert r.json()['task']['runs'][-1]['input']==values and isinstance(r.json()['task']['runs'][-1]['result']['data']['outputs']['result'],str)
 assert main.store.get(KIND,q['id'])['join_policy_approved'] is True and run(client,t,q,**ACKS).status_code==409

def test_old_plan_two_remains_readable_but_cannot_be_upgraded_by_new_acks(client,monkeypatch):
 t,env,p,_=uploaded_join(client,monkeypatch);q=plan(client,t,p,{'document':[],'question':'fixture'}).json()
 row=main.store.get(KIND,q['id']);row['plan_schema_version']=2;row['resource_token']=plan_token(row);main.store.put(KIND,q['id'],row);q['resource_token']=row['resource_token'];calls,_=remote(monkeypatch,t,env)
 assert client.get(f"/api/tasks/{t['id']}/file-runs").json()['records'][0]['plan_schema_version']==2
 assert run(client,t,q,**ACKS).status_code==409 and not calls

def test_changed_join_separator_invalidates_entire_prepared_file_provenance(client,monkeypatch):
 t,env,p,root=uploaded_join(client,monkeypatch);q=plan(client,t,p,{'document':[{'sierra_file_id':p['id']}],'question':'fixture'}).json();calls,_=remote(monkeypatch,t,env)
 root['workflow']['graph']['nodes'][2]['data']['code']=code({**POLICY,'separator':'\n---\n'})
 main.artifact_path(t).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8')
 assert run(client,t,q,**ACKS).status_code==409 and not calls and not main.get_task(t['id'])['runs']
