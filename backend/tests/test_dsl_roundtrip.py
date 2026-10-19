import copy,json
import pytest,yaml
from test_api import client,approved,create_env
from app import main
from app.dify import DifyClient,DifyError
from app.dsl_roundtrip import parse,merge,digest,validate_preserved

APP='a161d921-8f76-4a42-ad1e-6150a54cf0d8'
CODE='def main(query: str) -> dict:\n    return {"result": query.strip()}\n'


def prepared(client):
    env=create_env(client);task=approved(client,env_id=env['id'])
    plan={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'text-input','required':True}]}},{'id':'code','type':'code','config':{'code_language':'python3','code':CODE,'variables':[{'variable':'query','value_selector':['start','query']}],'outputs':{'result':{'type':'string','children':None}}}},{'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['code','result']}]}}],'edges':[{'source':'start','target':'code'},{'source':'code','target':'end'}]}
    response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan});assert response.status_code==200,response.text
    task=response.json()
    for kind in ('requirements','configuration'):task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind}).json()
    built=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert built.status_code==200,built.text
    task=built.json();root=parse(main.artifact_path(task).read_text(encoding='utf-8'),'workflow')
    task.update(dify_app_id=APP,status='imported');task['runs'].append({'id':'original-import','kind':'import','status':'success','revision':task['revision'],'environment_id':env['id'],'result':{'app_id':APP},'dsl_baseline':copy.deepcopy(root)})
    main.save_task(task);return task,root


def changed(root):
    current=copy.deepcopy(root);node=next(n for n in current['workflow']['graph']['nodes'] if n['id']=='code');node['data']['code']=CODE.replace('strip()','strip().upper()');node['position']['x']+=17;return current


def capture(client,task,root):
    response=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision'],'content':yaml.safe_dump(root,allow_unicode=True)});assert response.status_code==200,response.text
    return response.json()['task']


def apply(client,task,choices=None):
    preview=client.get(f"/api/tasks/{task['id']}/dsl-merge");assert preview.status_code==200,preview.text
    p=preview.json()
    result=client.post(f"/api/tasks/{task['id']}/dsl-merge/apply",json={'revision':task['revision'],'reference_id':p['reference_id'],'merge_token':p['merge_token'],'choices':choices or {}})
    return result,p


def test_preserves_manual_code_layout_and_final_file_until_new_approval(client):
    task,root=prepared(client);current=changed(root);captured=capture(client,task,current)
    assert captured['revision']>task['revision'] and not captured['requirements_confirmed'] and not captured['configuration_confirmed'] and not captured['dify_app_id']
    assert captured['dsl_reference']['source']=='uploaded_file' and '未在线核对' in captured['dsl_reference']['baseline_note']
    assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':captured['revision']}).status_code==422
    result,p=apply(client,captured);assert result.status_code==200,(result.text,p['validation'])
    merged=result.json();assert not merged['requirements_confirmed'] and not merged['configuration_confirmed']
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':merged['revision'],'kind':kind});assert response.status_code==200,response.text
    result=client.post(f"/api/tasks/{task['id']}/build",json={'revision':merged['revision']});assert result.status_code==200,result.text
    built=parse(main.artifact_path(result.json()).read_text(encoding='utf-8'),'workflow')
    assert digest(built)==digest(current) and 'upper()' in json.dumps(built)
    assert main.store.get('dsl_reference',captured['dsl_reference']['id'])['current']==current


@pytest.mark.parametrize('pick',['current','generated'])
def test_same_code_conflict_requires_choice_and_preview_matches_final_file(client,pick):
    task,root=prepared(client);captured=capture(client,task,changed(root))
    plan=copy.deepcopy(captured['workflow_plan']);plan['nodes'][1]['config']['code']=CODE.replace('strip()','strip().lower()')
    captured=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':captured['revision'],'plan':plan}).json()
    result,p=apply(client,captured);assert result.status_code==422 and p['unresolved']==1
    path=p['conflicts'][0]['path'];assert path.endswith('/@code/data/code')
    preview=client.post(f"/api/tasks/{task['id']}/dsl-merge/preview",json={'revision':captured['revision'],'choices':{path:pick}}).json()
    assert preview['unresolved']==0 and ('upper()' if pick=='current' else 'lower()') in preview['content']
    result,p=apply(client,captured,{path:pick});assert result.status_code==200,result.text


def test_editing_after_approval_blocks_silent_drop_or_old_overlay(client):
    task,root=prepared(client);task=capture(client,task,changed(root));result,_=apply(client,task);task=result.json()
    changed_task=client.patch(f"/api/tasks/{task['id']}",json={'configuration':{'opening_statement':'新配置'}}).json()
    assert changed_task['dsl_reference'] and changed_task['dsl_overlay']['revision']!=changed_task['revision']
    client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':changed_task['revision'],'kind':'requirements'})
    response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':changed_task['revision'],'kind':'configuration'});assert response.status_code==422 and '保留' in response.text


def test_stale_preview_never_applied_and_unknown_choices_rejected(client):
    task,root=prepared(client);task=capture(client,task,changed(root));p=client.get(f"/api/tasks/{task['id']}/dsl-merge").json()
    payload={'revision':task['revision'],'reference_id':p['reference_id'],'merge_token':'stale','choices':{}}
    assert client.post(f"/api/tasks/{task['id']}/dsl-merge/apply",json=payload).status_code==409
    payload.update(merge_token=p['merge_token'],choices={'/made-up':'current'})
    assert client.post(f"/api/tasks/{task['id']}/dsl-merge/apply",json=payload).status_code==422


def test_unsupported_graph_changes_are_retained_but_not_claimed_completed(client):
    task,root=prepared(client);current=changed(root);current['workflow']['graph']['nodes'][1]['data']['type']='iteration';task=capture(client,task,current)
    result,p=apply(client,task);assert result.status_code==422 and not p['validation']['valid']
    assert 'iteration' in p['content'] and main.store.get('dsl_reference',task['dsl_reference']['id'])['current']==current


def test_discard_requires_explicit_acceptance_preserves_audit_and_invalidates_confirmations(client):
    task,root=prepared(client);task=capture(client,task,changed(root));ref=task['dsl_reference']['id']
    assert client.post(f"/api/tasks/{task['id']}/dsl-reference/discard",json={'revision':task['revision']}).status_code==422
    response=client.post(f"/api/tasks/{task['id']}/dsl-reference/discard",json={'revision':task['revision'],'acknowledge_loss':True});assert response.status_code==200
    t=response.json();assert not t['dsl_reference'] and not t['configuration_confirmed'] and main.store.get('dsl_reference',ref)


@pytest.mark.parametrize('mutation',['duplicate','wrong_mode','wrong_version','secret','token','anchor'])
def test_unsafe_or_mismatched_yaml_not_persisted(client,mutation):
    task,root=prepared(client);content=yaml.safe_dump(root)
    if mutation=='duplicate':content+='\nkind: app\n'
    if mutation=='wrong_mode':root['app']['mode']='advanced-chat';content=yaml.safe_dump(root)
    if mutation=='wrong_version':root['version']='0.6.0';content=yaml.safe_dump(root)
    if mutation=='secret':root['api_key']='secret';content=yaml.safe_dump(root)
    if mutation=='token':root['app']['description']='sk-never-store-this-secret-token';content=yaml.safe_dump(root)
    if mutation=='anchor':content='kind: app\nversion: 0.7.0\napp: &x {mode: workflow}\nagain: *x\n'
    response=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision'],'content':content});assert response.status_code==422
    assert not main.store.list('dsl_reference') and not main.get_task(task['id']).get('dsl_reference')


def test_live_read_uses_recorded_source_and_export_errors_never_fallback_to_old_file(client,monkeypatch):
    task,root=prepared(client);seen=[]
    async def export(self,appid):seen.append(appid);return yaml.safe_dump(changed(root))
    monkeypatch.setattr(DifyClient,'export_dsl',export)
    result=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision']});assert result.status_code==200 and seen==[APP]
    task=result.json()['task'];assert task['dsl_reference']['source']=='dify_draft'
    async def fail(*args):raise DifyError('权限失败')
    monkeypatch.setattr(DifyClient,'export_dsl',fail)
    ref=task['dsl_reference']['id'];response=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision']});assert response.status_code==502
    assert main.get_task(task['id'])['dsl_reference']['id']==ref


def test_source_changes_before_import_abort_before_any_write(client,monkeypatch):
    task,root=prepared(client);current=changed(root)
    async def export(self,appid):return yaml.safe_dump(current)
    monkeypatch.setattr(DifyClient,'export_dsl',export)
    task=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision']}).json()['task'];result,_=apply(client,task);task=result.json()
    for kind in ('requirements','configuration'):client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind})
    assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']}).status_code==200
    current['app']['description']='再次手动改动'
    async def forbidden(*args):pytest.fail('Source changed; import must not dispatch')
    monkeypatch.setattr(DifyClient,'import_new',forbidden)
    response=client.post(f"/api/tasks/{task['id']}/import",json={'revision':task['revision']});assert response.status_code==502
    run=main.get_task(task['id'])['runs'][-1];assert run['status']=='failed' and '本次未创建' in run['error']


def test_keyed_graph_merge_keeps_independent_nodes_and_deletion_conflict():
    base={'workflow':{'graph':{'nodes':[{'id':'a','v':1},{'id':'b','v':1}],'edges':[]}}}
    current=copy.deepcopy(base);generated=copy.deepcopy(base);current['workflow']['graph']['nodes'][0]['v']=2;generated['workflow']['graph']['nodes'][1]['v']=3
    r=merge(base,current,generated);assert not r['conflicts'] and r['root']['workflow']['graph']['nodes']==[{'id':'a','v':2},{'id':'b','v':3}]
    generated['workflow']['graph']['nodes']=generated['workflow']['graph']['nodes'][1:];r=merge(base,current,generated);assert len(r['conflicts'])==1 and r['conflicts'][0]['generated']['missing']


def test_chatflow_prompt_and_model_parameters_are_preserved_and_structurally_checked(client):
    task=approved(client,app_type='advanced-chat');root=parse(main.compile_current(task)[0],'advanced-chat')
    node=next(n for n in root['workflow']['graph']['nodes'] if n['data']['type']=='llm');node['data']['prompt_template'][0]['text']='保留用户明确的新提示词';node['data']['model']['completion_params']['temperature']=.4
    assert validate_preserved(root)['valid']
    node['data']['prompt_template'][1]['text']='{{#missing.answer#}}';assert not validate_preserved(root)['valid']


def test_native_agent_text_file_is_preserved_without_workflow_projection(client):
    from test_agent_plan import runtime_task
    task=runtime_task(client);task['dify_app_id']=None;main.save_task(task)
    content=main.compile_current(task)[0]
    task=capture(client,task,parse(content,'agent'))
    result=client.get(f"/api/tasks/{task['id']}/dsl-merge");assert result.status_code==200 and result.json()['validation']['valid']
    assert result.json()['parallel_candidates']==[] and result.json()['loop_candidates']==[]
    assert main.store.get('dsl_reference',task['dsl_reference']['id'])['current']['app']['mode']=='agent'


def test_reimport_uses_generation_baseline_so_previous_preserved_changes_survive_next_cycle(client,monkeypatch):
    task,root=prepared(client);current=changed(root);task=capture(client,task,current);result,_=apply(client,task);task=result.json()
    for kind in ('requirements','configuration'):client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind})
    assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']}).status_code==200
    new_id='db4cd0c5-358b-4514-8b86-11502487d603'
    async def imported(*args):return {'app_id':new_id,'status':'completed'}
    monkeypatch.setattr(DifyClient,'import_new',imported)
    result=client.post(f"/api/tasks/{task['id']}/import",json={'revision':task['revision']});assert result.status_code==200,result.text
    task=result.json();run=task['runs'][-1];assert run['baseline_kind']=='generation_proposal' and digest(run['dsl_baseline'])==digest(root)
    async def exported(self,appid):assert appid==new_id;return yaml.safe_dump(current)
    monkeypatch.setattr(DifyClient,'export_dsl',exported)
    task=client.post(f"/api/tasks/{task['id']}/dsl-reference",json={'revision':task['revision']}).json()['task']
    result=client.get(f"/api/tasks/{task['id']}/dsl-merge");assert result.status_code==200
    preview=result.json();assert 'upper()' in preview['content'] and not preview['generated_changes'] and preview['unresolved']==0


def test_confirmed_file_tampering_blocks_import_before_any_dispatch(client,monkeypatch):
    task,root=prepared(client);task=capture(client,task,changed(root));result,_=apply(client,task);task=result.json()
    for kind in ('requirements','configuration'):client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind})
    task=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']}).json()
    main.artifact_path(task).write_text(yaml.safe_dump(root),encoding='utf-8')
    async def forbidden(*args):pytest.fail('Unapproved artifact dispatched')
    monkeypatch.setattr(DifyClient,'import_new',forbidden)
    response=client.post(f"/api/tasks/{task['id']}/import",json={'revision':task['revision']});assert response.status_code==422 and len(main.get_task(task['id'])['runs'])==1
