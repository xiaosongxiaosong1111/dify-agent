import copy
import hashlib
import json

import pytest
import yaml

from test_api import client, approved, planning_provider, forbid_api_external_calls
from test_workflow_plan import task as example_task, base_plan
from app import main


@pytest.mark.parametrize('mode', ['workflow', 'advanced-chat'])
def test_readonly_versioned_guidance_has_independent_static_examples(client, mode):
    response = client.get('/api/node-guidance', params={'app_type': mode, 'dify_version': '1.17.1'})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['app_type'] == mode and value['target_dify_version'] == '1.17.1'
    assert value['verification'] == 'static_guidance' and value['target_dsl_version'] == '0.7.0'
    assert value['complete_catalog'] is False and value['runtime_verified'] is False
    assert {row['node_type'] for row in value['items']} == {'code', 'if-else', 'knowledge-retrieval', 'llm'}
    from app.workflow_plan import compile_workflow_plan
    for row in value['items']:
        assert row['rules'] and row['sources'] and row['limitations']
        assert row['app_type'] == mode and row['example_kind'] == 'synthetic_plan'
        assert all(source['version'] == '1.17.1' for source in row['sources'])
        assert row['content_sha256'] == hashlib.sha256(json.dumps({k:v for k,v in row.items() if k!='content_sha256'}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        plan = row['example_plan']; before = copy.deepcopy(plan)
        content, checked = compile_workflow_plan({**example_task(mode), 'configuration':row['example_configuration'], 'workflow_plan': plan})
        assert checked['valid'], checked['errors']
        assert plan == before and yaml.safe_load(content)['app']['mode'] == mode
        if mode == 'advanced-chat':
            assert plan['nodes'][0]['config']['variables'] == []
            assert any(n['type']=='answer' for n in plan['nodes'])
            assert not any(n['type']=='end' for n in plan['nodes'])


@pytest.mark.parametrize('mode,version', [('bad','1.17.1'),('workflow','1.18.0'),('agent','main')])
def test_type_or_version_mismatch_is_explicit_rejection(client, mode, version):
    response = client.get('/api/node-guidance', params={'app_type':mode, 'dify_version':version})
    assert response.status_code == 422


def test_agent_does_not_receive_workflow_node_examples(client):
    response = client.get('/api/node-guidance', params={'app_type':'agent'})
    assert response.status_code == 200
    value = response.json()
    assert value['items'] == [] and value['app_type'] == 'agent'
    assert value['available_node_types'] == [] and value['notes']


def test_missing_rule_does_not_mean_unsupported_or_silently_substitute(client):
    value = client.get('/api/node-guidance', params={'app_type':'workflow','node_types':'http-request,code,http-request'}).json()
    assert [row['node_type'] for row in value['items']] == ['code']
    assert value['missing_node_types'] == ['http-request']
    assert value['complete_catalog'] is False


@pytest.mark.parametrize('filter_value', [',', 'code,,llm', 'x'*81, ','.join('type'+str(n) for n in range(17))])
def test_invalid_or_unbounded_query_rejected(client, filter_value):
    assert client.get('/api/node-guidance', params={'app_type':'workflow','node_types':filter_value}).status_code == 422


def test_lookup_is_readonly_and_does_not_share_mutable_examples(client):
    current = approved(client); before = copy.deepcopy(main.store.list('task'))
    first = client.get('/api/node-guidance', params={'app_type':'workflow','node_types':'code'}).json()
    first['items'][0]['rules'].clear()
    assert client.get('/api/node-guidance', params={'app_type':'workflow','node_types':'code'}).json()['items'][0]['rules']
    assert main.store.list('task') == before
    assert main.get_task(current['id']) == current


def test_planning_uses_only_current_task_rule_matches_and_records_provenance(client, monkeypatch):
    planning_provider(client); current = approved(client)
    current['requirements']['goal'] = '根据知识检索结果走条件分支，只用检索资料回答'
    main.save_task(current)
    other = approved(client); other['requirements']['goal'] = 'secret unrelated code task'
    main.save_task(other); other_before = copy.deepcopy(other); calls=[]
    async def model(provider, key, messages, **kwargs):
        context = json.loads(messages[1]['content']); calls.append(context)
        value = context['node_guidance']
        kinds = {row['node_type'] for row in value['items']}
        assert {'knowledge-retrieval','if-else'} <= kinds
        assert 'code' not in kinds and 'secret unrelated' not in json.dumps(value)
        assert '不是执行授权' in messages[0]['content']
        assert value['runtime_verified'] is False
        return json.dumps(base_plan()), {'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',model)
    response = client.post(f"/api/tasks/{current['id']}/plan/generate", json={'revision':current['revision']})
    assert response.status_code == 200, response.text
    assert len(calls) == 1 and main.get_task(other['id']) == other_before
    record = response.json()['planning_runs'][-1]['node_guidance']
    assert record['target_dify_version'] == '1.17.1' and record['app_type'] == 'workflow'
    assert record['items'] == [{'id':r['id'],'content_sha256':r['content_sha256']} for r in calls[0]['node_guidance']['items']]
    assert 'example_plan' not in json.dumps(record)


def test_rule_selection_uses_saved_plan_but_never_infers_resource_values():
    from app.node_guidance import for_task
    current = {'app_type':'workflow','requirements':{},'workflow_plan':{'nodes':[{'type':'code'},{'type':'http-request'}]}}
    before = copy.deepcopy(current)
    value = for_task(current)
    assert [r['node_type'] for r in value['items']] == ['code']
    assert value['missing_node_types'] == ['http-request']
    assert current == before and value['runtime_verified'] is False
    blank = for_task({'app_type':'workflow','requirements':{},'workflow_plan':None})
    assert blank['items'] == [] and blank['missing_node_types'] == []


def test_query_replaces_example_resource_with_no_task_data(client):
    current = approved(client)
    current['configuration']['dataset_ids'] = ['private-real-id']
    main.save_task(current)
    text = client.get('/api/node-guidance', params={'app_type':'workflow','node_types':'knowledge-retrieval'}).text
    assert 'private-real-id' not in text and 'EXAMPLE_DATASET_ID' in text


def test_guidance_context_preserves_agent_scope_and_does_not_leak_old_graph(client, monkeypatch):
    from test_agent_plan import prepare
    planning_provider(client); current=prepare(client); seen=[]
    async def model(provider,key,messages,**kwargs):
        value=json.loads(messages[1]['content'])['node_guidance'];seen.append(value)
        assert value['app_type']=='agent' and value['items']==[] and value['available_node_types']==[]
        return json.dumps(current['agent_plan']), {'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{current['id']}/plan/generate",json={'revision':current['revision']})
    assert response.status_code==200,response.text
    assert len(seen)==1 and response.json()['planning_runs'][-1]['node_guidance']['items']==[]


def test_guidance_retrieves_body_nodes_without_changing_scope():
    from app.node_guidance import for_task
    value=for_task({'app_type':'advanced-chat','requirements':{},'workflow_plan':{'nodes':[{'type':'iteration','config':{'nodes':[{'type':'code'}]}}]}})
    assert [r['node_type'] for r in value['items']]==['code']
    assert value['missing_node_types']==['iteration']
    # This is a root synthetic example, never a claim that it can be pasted into a container.
    assert value['items'][0]['example_plan']['nodes'][0]['type']=='start'


def test_example_selection_and_digest_are_stable_without_mutating_rules():
    from app.node_guidance import lookup
    first=lookup('workflow',['code','knowledge-retrieval'])
    original=copy.deepcopy(first)
    first['items'][0]['example_plan']['nodes'].clear()
    assert lookup('workflow',['code','knowledge-retrieval'])==original
    workflow=original['items'][0];chat=lookup('advanced-chat',['code'])['items'][0]
    assert workflow['id']!=chat['id'] and workflow['content_sha256']!=chat['content_sha256']
