import copy,json,uuid
import pytest
from test_api import client,create
from test_file_join import joined,POLICY
from app import main
from app.file_join_policy import candidate
from app.file_join import read_code
from app.structured_guard import digest

def payload(t,p,**patch):return {'revision':t['revision'],'plan':p,'node_id':'join_documents','request_nonce':str(uuid.uuid4()),**patch}

def test_inspect_and_preview_only_read_local_draft_without_writes_secrets_or_execution(client,monkeypatch):
 t=create(client);p,_,_=joined();before=copy.deepcopy(main.get_task(t['id']))
 def forbidden(*a,**kw):pytest.fail('政策读写只准备本机草稿，不执行代码或修改Task／资源')
 monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 body=payload(t,p);r=client.post(f"/api/tasks/{t['id']}/file-join-policy/inspect",json=body);assert r.status_code==200,r.text
 v=r.json();assert v['policy']==POLICY and v['source_plan_sha256']==digest(p) and v['request_nonce']==body['request_nonce'] and 'plan' not in v
 body['policy']={**POLICY,'separator':'\n---\n'};r=client.post(f"/api/tasks/{t['id']}/file-join-policy/preview",json=body);assert r.status_code==200,r.text
 q=r.json();assert q['previous_policy']==POLICY and q['policy']==body['policy'] and q['updated_nodes']==1 and q['added_nodes']==q['changed_edges']==0
 assert q['source_plan_sha256']==digest(p) and q['candidate_plan_sha256']==digest(q['plan']) and q['verification']=='local_policy_static_only'
 assert q['network_requested'] is q['model_called'] is q['task_changed'] is False and main.get_task(t['id'])==before

@pytest.mark.parametrize('change',[{'separator':'|'}, {'format':'numbered_sections'},{'empty_list':'empty_text'},{'empty_document':'keep'},{'max_utf8_bytes':64000},{'max_files':7}])
def test_candidate_changes_only_code_and_explicit_count_field_preserving_every_other_field(change):
 p,_,_=joined();p['nodes'][2]['title']='我的拼接标题';p['nodes'][3]['config']['system_prompt']='人工提示词保留';before=copy.deepcopy(p)
 t={'app_type':'workflow','configuration':{}};q=candidate(t,p,'join_documents',{**POLICY,**change});expected=copy.deepcopy(p)
 expected['nodes'][2]['config']['code']=q['plan']['nodes'][2]['config']['code'];expected['nodes'][0]['config']['variables'][0]['max_length']=q['policy']['max_files']
 assert q['plan']==expected and p==before and read_code(q['plan']['nodes'][2]['config']['code'])==q['policy']
 assert q['updated_nodes']==(2 if 'max_files' in change else 1)

@pytest.mark.parametrize('mutation',['hand-code','binding','max','edge','node','unchanged','bad-policy'])
def test_policy_refresh_refuses_unsafe_or_ambiguous_originals_and_preserves_manual_changes(mutation):
 p,_,_=joined();new={**POLICY,'separator':'|'};chosen='join_documents'
 if mutation=='hand-code':p['nodes'][2]['config']['code']+='\n# manual'
 elif mutation=='binding':p['nodes'][2]['config']['variables'][0]['value_selector']=['start','question']
 elif mutation=='max':p['nodes'][0]['config']['variables'][0]['max_length']=4
 elif mutation=='edge':p['edges'].append({'source':'extract','target':'answer_llm'})
 elif mutation=='node':chosen='answer_llm'
 elif mutation=='unchanged':new=POLICY
 else:new['max_files']=False
 before=copy.deepcopy(p)
 with pytest.raises(ValueError):candidate({'app_type':'workflow','configuration':{}},p,chosen,new)
 assert p==before

@pytest.mark.parametrize('kind',['revision','chatflow','agent','unknown-field','nonce','strict-count','missing-policy'])
def test_api_scope_or_invalid_request_never_changes_task(client,kind):
 t=create(client,app_type='advanced-chat' if kind=='chatflow' else 'agent' if kind=='agent' else 'workflow');p,_,_=joined();body=payload(t,p,policy={**POLICY,'separator':'|'});before=copy.deepcopy(main.get_task(t['id']))
 if kind=='revision':body['revision']+=1
 elif kind=='unknown-field':body['private-sentinel']='private-sentinel'
 elif kind=='nonce':body['request_nonce']='private-sentinel'
 elif kind=='strict-count':body['policy']['max_files']=True
 elif kind=='missing-policy':body.pop('policy')
 r=client.post(f"/api/tasks/{t['id']}/file-join-policy/preview",json=body);assert r.status_code in (409,422),r.text
 assert 'private-sentinel' not in r.text and main.get_task(t['id'])==before


@pytest.mark.parametrize('kind',['duplicate-root','duplicate-policy','nan','infinite','surrogate','oversize'])
def test_policy_routes_reject_ambiguous_or_unbounded_raw_json_without_echo(client,kind):
 t=create(client);p,_,_=joined();body=payload(t,p,policy={**POLICY,'separator':'|'});raw=json.dumps(body)
 if kind=='duplicate-root':raw=raw[:-1]+',"node_id":"private-sentinel"}'
 elif kind=='duplicate-policy':raw=raw.replace('"max_files": 5','"max_files": 5,"max_files":6',1)
 elif kind=='nan':raw=raw.replace('"max_files": 5','"max_files": NaN',1)
 elif kind=='infinite':raw=raw.replace('"max_files": 5','"max_files": 1e999',1)
 elif kind=='surrogate':body['policy']['separator']='\ud800';raw=json.dumps(body)
 else:raw='{"private":"'+'x'*2_800_000+'"}'
 r=client.post(f"/api/tasks/{t['id']}/file-join-policy/preview",content=raw,headers={'content-type':'application/json'})
 assert r.status_code in (413,422),r.text
 assert 'private-sentinel' not in r.text


def test_initial_template_route_also_rejects_duplicate_policy_keys(client):
 t=create(client);raw=json.dumps({'revision':t['revision'],'policy':POLICY}).replace('"max_files": 5','"max_files":5,"max_files":6')
 r=client.post(f"/api/tasks/{t['id']}/file-join-template",content=raw,headers={'content-type':'application/json'})
 assert r.status_code==422 and main.get_task(t['id']).get('workflow_plan') is None
