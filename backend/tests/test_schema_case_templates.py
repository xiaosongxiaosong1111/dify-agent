import copy,hashlib,json
import pytest,yaml
from test_api import client,approved,create
from test_node_policy_audit import built
from test_structured_output import root as llm_root,schema as output_schema
from test_json_inputs import native as input_root,shape
from app import main
from app.schema_case_templates import templates


def get(client,t):return client.get(f"/api/tasks/{t['id']}/schema-case-templates",params={'revision':t['revision']})


def test_final_llm_schema_without_provider_prompt_runtime_data_or_mutation(client,monkeypatch):
 root=llm_root();root['workflow']['graph']['nodes'][1]['data']['prompt_template']=[{'role':'user','text':'private-prompt-sentinel'}];t=built(client,root);before=copy.deepcopy(main.get_task(t['id']));raw=main.artifact_path(t).read_text(encoding='utf-8')
 def forbidden(*a,**kw):pytest.fail('Schema模板仅读，不得解密／写Task／联网')
 monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden)
 r=get(client,t);assert r.status_code==200,r.text;value=r.json();assert value['total_outputs']==value['candidate_count']==1
 assert value['rows'][0]['schema']==output_schema() and value['rows'][0]['source_selector']==['llm','structured_output']
 assert value['source_sha256']==hashlib.sha256(raw.encode('utf-8')).hexdigest() and r.headers['cache-control']=='no-store'
 assert all(value[k] is False for k in ('credentials_decrypted','network_requested','platform_checked','business_verified','run_authorized'))
 assert value['verification']=='declared_schema_draft_only' and 'private-prompt-sentinel' not in r.text and 'api_key' not in r.text
 assert main.get_task(t['id'])==before


def test_root_object_input_direct_end_preserves_raw_schema():
 root=input_root();nodes=root['workflow']['graph']['nodes'];nodes[-1]['data']['outputs'][0]['value_selector']=['start','payload'];raw=json.dumps(shape(),ensure_ascii=False,indent=3);nodes[0]['data']['variables'][0]['json_schema']=raw;before=copy.deepcopy(root)
 r=templates(root);assert r['rows'][0]['origin']=='json_object_input' and r['rows'][0]['schema']==raw and root==before

@pytest.mark.parametrize('kind',['code','variable-aggregator','template-transform'])
def test_unknown_object_producer_not_inferred_as_schema(kind):
 root=llm_root();root['workflow']['graph']['nodes'][1]['data']['type']=kind;r=templates(root);assert r['candidate_count']==0 and r['total_outputs']==1 and r['rows'][0]['schema'] is None

@pytest.mark.parametrize('patch',[{'structured_output_enabled':False},{'structured_output_enabled':'true'},{'structured_output':{'schema':{'type':'array','items':{'type':'string'}}}},{'isInIteration':True},{'isInLoop':True}])
def test_disabled_malformed_or_container_llm_not_used(patch):
 root=llm_root();root['workflow']['graph']['nodes'][1]['data'].update(patch);assert templates(root)['candidate_count']==0


def test_duplicate_end_target_not_pick_one_branch_or_silently_omit():
 root=llm_root();nodes=root['workflow']['graph']['nodes'];other=copy.deepcopy(nodes[-1]);other['id']='another-end';nodes.append(other);r=templates(root)
 assert r['total_outputs']==2 and r['candidate_count']==0 and all(not row['supported'] and row['schema'] is None and '相同目标名' in row['reason'] for row in r['rows'])

@pytest.mark.parametrize('selector',[['llm','structured_output','child'],['missing','structured_output'],['llm','text'],[],None])
def test_exact_final_source_only_not_guessed(selector):
 root=llm_root();root['workflow']['graph']['nodes'][-1]['data']['outputs'][0]['value_selector']=selector
 assert templates(root)['candidate_count']==0

@pytest.mark.parametrize('mode',['advanced-chat','agent'])
def test_unsupported_app_type_does_not_change_type(client,mode):
 t=create(client,mode);before=copy.deepcopy(main.get_task(t['id']));r=get(client,t);assert r.status_code==422 and main.get_task(t['id'])==before


def test_missing_artifact_and_stale_revision_cannot_use_old_plan(client):
 t=approved(client);assert get(client,t).status_code==404
 assert client.get(f"/api/tasks/{t['id']}/schema-case-templates",params={'revision':t['revision']-1}).status_code==409


def test_source_change_during_read_refuses_old_candidate(client,monkeypatch):
 import app.schema_case_templates as module
 t=built(client,llm_root());original=module.read_bytes;calls=[]
 def change(path):
  raw=original(path);calls.append(True)
  return raw if len(calls)==1 else raw+b'\n'
 monkeypatch.setattr(module,'read_bytes',change);assert get(client,t).status_code==409


def test_invalid_file_private_raw_is_not_returned(client):
 t=built(client);main.artifact_path(t).write_text('private-document-sentinel: [not-finished',encoding='utf-8');r=get(client,t);assert r.status_code==422 and 'private-document-sentinel' not in r.text

@pytest.mark.parametrize('kind',['nodes','outputs','duplicate-id','schedule'])
def test_complete_limits_no_partial_candidate(kind):
 root=llm_root();nodes=root['workflow']['graph']['nodes']
 if kind=='nodes':nodes.extend({'id':f'n{i}','data':{'type':'code'}} for i in range(1000))
 elif kind=='outputs':nodes[-1]['data']['outputs']*=1001
 elif kind=='duplicate-id':nodes[1]['id']=nodes[0]['id']
 else:nodes[0]['data']['type']='trigger-schedule'
 with pytest.raises(ValueError):templates(root)


def test_final_artifact_used_instead_of_stale_ir(client):
 root=llm_root();root['workflow']['graph']['nodes'][1]['data']['structured_output']['schema']['properties']['label']['enum']=['最终枚举'];t=built(client,root)
 r=get(client,t);assert r.status_code==200,r.text;assert r.json()['rows'][0]['schema']['properties']['label']['enum']==['最终枚举']
