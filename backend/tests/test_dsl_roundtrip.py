import asyncio
import copy,json
import httpx
import pytest,yaml
from test_api import client,approved,create_env
from app import main
from app.dify import DifyClient,DifyError
from app.dsl_roundtrip import parse,merge,digest,validate_preserved
from app.storage import Store

APP='a161d921-8f76-4a42-ad1e-6150a54cf0d8'
CODE='def main(query: str) -> dict:\n    return {"result": query.strip()}\n'


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('AT-18 隔离检查不得访问真实 HTTP、Dify 请求或调用真实模型')
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)
    monkeypatch.setattr(DifyClient, 'request', forbidden)


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
    response=client.post(f"/api/tasks/{task['id']}/import",json={'revision':task['revision']});assert response.status_code==409 and len(main.get_task(task['id'])['runs'])==1


def confirm_and_build(client, task):
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision': task['revision'], 'kind': kind})
        assert response.status_code == 200, response.text
    response = client.post(f"/api/tasks/{task['id']}/build", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_changes_plus_new_requirement_survive_reopen_build_and_new_import(client, monkeypatch):
    task, root = prepared(client)
    original_task = copy.deepcopy(task)
    original_file = main.artifact_path(task)
    original_bytes = original_file.read_bytes()
    current = changed(root)
    seen = []

    async def exported(self, app_id):
        seen.append(('export', app_id))
        return yaml.safe_dump(current, allow_unicode=True)

    async def imported(self, content, name):
        seen.append(('import_new', parse(content, 'workflow')))
        return {'app_id': 'isolated-new-app', 'status': 'completed'}

    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    monkeypatch.setattr(DifyClient, 'import_new', imported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()['task']
    assert task['artifact'] is None and task['dify_app_id'] is None
    assert not task['requirements_confirmed'] and not task['configuration_confirmed']
    assert task['runs'] == original_task['runs']
    reference_id = task['dsl_reference']['id']
    response = client.patch(f"/api/tasks/{task['id']}", json={'requirements': {'rules': '新增要求：输出保留处理结果标题'}})
    assert response.status_code == 200, response.text
    task = response.json()
    plan = copy.deepcopy(task['workflow_plan'])
    plan['nodes'][2]['title'] = '新增要求的处理结果'
    response = client.post(f"/api/tasks/{task['id']}/plan", json={'revision': task['revision'], 'plan': plan})
    assert response.status_code == 200, response.text
    task = response.json()
    before_preview = copy.deepcopy(main.get_task(task['id']))
    preview = client.get(f"/api/tasks/{task['id']}/dsl-merge").json()
    assert preview['unresolved'] == 0 and preview['preserved'] and preview['generated_changes']
    assert main.get_task(task['id']) == before_preview
    result, _ = apply(client, task)
    assert result.status_code == 200, result.text
    task = result.json()
    assert not task['requirements_confirmed'] and not task['configuration_confirmed']
    monkeypatch.setattr(main, 'store', Store(main.store.root))
    assert main.get_task(task['id']) == task
    assert main.store.get('dsl_reference', reference_id)['current'] == current
    task = confirm_and_build(client, task)
    final_root = parse(main.artifact_path(task).read_text(encoding='utf-8'), 'workflow')
    assert digest(final_root) == digest(parse(preview['content'], 'workflow'))
    nodes = {node['id']: node for node in final_root['workflow']['graph']['nodes']}
    assert nodes['code'] == current['workflow']['graph']['nodes'][1]
    assert nodes['end']['data']['title'] == '新增要求的处理结果'
    assert task['artifact']['verification'] == 'static_only'
    response = client.post(f"/api/tasks/{task['id']}/import", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    assert seen == [('export', APP), ('export', APP), ('import_new', final_root)]
    assert response.json()['dify_app_id'] == 'isolated-new-app'
    assert response.json()['runs'][0] == original_task['runs'][0]
    assert original_file.read_bytes() == original_bytes
    assert main.store.get('dsl_reference', reference_id)['current'] == current


@pytest.mark.parametrize('change', ['revision', 'reference', 'generated'])
def test_preview_bound_to_revision_reference_and_generated_content(client, change):
    task, root = prepared(client)
    task = capture(client, task, changed(root))
    preview = client.get(f"/api/tasks/{task['id']}/dsl-merge").json()
    payload = {'revision': task['revision'], 'reference_id': preview['reference_id'], 'merge_token': preview['merge_token'], 'choices': {}}
    if change == 'reference':
        task = capture(client, task, root)
        payload['revision'] = task['revision']
    else:
        plan = copy.deepcopy(task['workflow_plan'])
        plan['nodes'][2]['title'] = '本次新增要求'
        response = client.post(f"/api/tasks/{task['id']}/plan", json={'revision': task['revision'], 'plan': plan})
        assert response.status_code == 200, response.text
        task = response.json()
        if change == 'generated':
            payload['revision'] = task['revision']
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.post(f"/api/tasks/{task['id']}/dsl-merge/apply", json=payload)
    assert response.status_code == 409, response.text
    assert main.get_task(task['id']) == before and not before.get('dsl_overlay')
    assert not list((main.DATA_ROOT / task['id']).glob('preserved-*.yaml'))


@pytest.mark.parametrize('mismatch', ['missing_baseline', 'wrong_app', 'wrong_environment'])
def test_missing_or_foreign_import_baseline_rejected_before_export(client, monkeypatch, mismatch):
    task, _ = prepared(client)
    if mismatch == 'missing_baseline':
        task['runs'] = []
    elif mismatch == 'wrong_app':
        task['runs'][0]['result']['app_id'] = 'other-app'
    else:
        task['runs'][0]['environment_id'] = 'other-environment'
    main.save_task(task)
    before = copy.deepcopy(main.get_task(task['id']))

    async def forbidden(*args):
        pytest.fail('缺少匹配基线时不能读取外部草稿')

    monkeypatch.setattr(DifyClient, 'export_dsl', forbidden)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 422 and '基线' in response.text
    assert main.get_task(task['id']) == before and not main.store.list('dsl_reference')


@pytest.mark.parametrize('failure', ['permission', 'timeout', 'invalid_yaml'])
def test_import_source_recheck_failure_keeps_reference_and_never_creates_app(client, monkeypatch, failure):
    task, root = prepared(client)
    current = changed(root)

    async def exported(*args):
        return yaml.safe_dump(current)

    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    task = response.json()['task']
    result, _ = apply(client, task)
    assert result.status_code == 200, result.text
    task = confirm_and_build(client, result.json())
    reference = main.store.get('dsl_reference', task['dsl_reference']['id'])
    artifact_bytes = main.artifact_path(task).read_bytes()

    async def failed_export(*args):
        if failure == 'invalid_yaml':
            return 'invalid: [yaml'
        raise DifyError('权限不足' if failure == 'permission' else '读取超时')

    async def forbidden(*args):
        pytest.fail('无法核对最新草稿时不得创建应用')

    monkeypatch.setattr(DifyClient, 'export_dsl', failed_export)
    monkeypatch.setattr(DifyClient, 'import_new', forbidden)
    response = client.post(f"/api/tasks/{task['id']}/import", json={'revision': task['revision']})
    assert response.status_code == 502 and '本次未创建应用' in response.text
    saved = main.get_task(task['id'])
    assert saved['dify_app_id'] is None and saved['runs'][:-1] == task['runs']
    assert saved['runs'][-1]['status'] == 'failed' and saved['runs'][-1]['revision'] == task['revision']
    assert main.artifact_path(saved).read_bytes() == artifact_bytes
    assert main.store.get('dsl_reference', reference['id']) == reference


@pytest.mark.parametrize('change', ['revision', 'environment_address'])
def test_changes_during_draft_read_never_persist_stale_reference(client, monkeypatch, change):
    task, root = prepared(client)
    concurrent = []

    async def exported(*args):
        if change == 'revision':
            response = await asyncio.to_thread(client.patch, f"/api/tasks/{task['id']}", json={'requirements': {'rules': '读取期间的新要求'}})
            assert response.status_code == 200, response.text
        else:
            env = main.store.get('environment', task['environment_id'])
            env['base_url'] = 'https://changed.invalid'
            main.store.put('environment', env['id'], env)
        concurrent.append(copy.deepcopy(main.get_task(task['id'])))
        return yaml.safe_dump(changed(root))

    monkeypatch.setattr(DifyClient, 'export_dsl', exported)
    response = client.post(f"/api/tasks/{task['id']}/dsl-reference", json={'revision': task['revision']})
    assert response.status_code == 409, response.text
    assert not main.store.list('dsl_reference')
    assert main.get_task(task['id']) == concurrent[0]
