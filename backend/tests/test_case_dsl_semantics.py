import copy,json
import pytest
from fastapi import HTTPException
from test_api import client
from test_dsl_roundtrip import prepared,capture,apply,changed
from test_case_proposals import candidate
from test_task_budget import provider
from test_assistant_routing import setup,enable,state
from test_preserved_iteration_branches import native
from app import main
from app.case_dsl_semantics import summary,FIELDS,MAX_BYTES


def test_final_manual_code_and_real_edges_are_exposed_without_layout_or_source_mutation(client):
    t,root=prepared(client);root=changed(root);raw=copy.deepcopy(root)
    t=capture(client,t,root);response,_=apply(client,t);assert response.status_code==200
    source=main.case_proposals.contract(response.json())['source'];s=source['semantics']
    code=next(n for n in s['nodes'] if n['id']=='code')
    assert 'strip().upper()' in code['config']['code'] and code['parent_id'] is None
    assert all('position' not in n and 'width' not in n for n in s['nodes'])
    assert s['edges'][0]['source']=='start' and s['edges'][0]['target']=='code'
    assert root==raw and source['kind']=='preserved_dsl'


def test_branch_conditions_aggregator_priority_and_iteration_scope_are_actual():
    root=native();nodes={n['id']:n for n in root['workflow']['graph']['nodes']}
    nodes['route_item']['data']['cases'][0]['conditions'][0]['comparison_operator']='empty'
    nodes['merged_item']['data']['variables'].reverse();root['workflow']['graph']['nodes'].reverse()
    before=copy.deepcopy(root);s=summary(root);mapped={n['id']:n for n in s['nodes']}
    assert mapped['route_item']['config']['cases']==nodes['route_item']['data']['cases']
    assert mapped['merged_item']['config']['variables']==nodes['merged_item']['data']['variables']
    assert mapped['route_item']['parent_id']==nodes['route_item']['parentId']
    assert root==before
    # Returned values are copies; candidate code cannot mutate the source object.
    mapped['route_item']['config']['cases'].clear();assert root==before


@pytest.mark.parametrize('kind',list(FIELDS))
def test_declared_node_fields_preserve_false_zero_and_unknown_names_are_disclosed_without_values(kind):
    fields=FIELDS[kind];data={'type':kind,'title':'当前标题','private_unknown_field':'private-value-should-not-leave'}
    for i,key in enumerate(fields):data[key]=False if i%2 else 0
    root={'workflow':{'graph':{'nodes':[{'id':'current','parentId':'container','position':{'x':9},'data':data}],'edges':[]},'features':{'unknown_feature':'private-feature-value'}}}
    # This checks field projection, not an unacknowledged repeated-read contract.
    if kind=='http-request':
        root['workflow']['graph']['nodes'][0].pop('parentId')
        # Projection retains false/zero; execution metadata must itself be valid.
        data.update(timeout={'connect':0,'read':0,'write':0},retry_config={'retry_enabled':False,'max_retries':0,'retry_interval':0},ssl_verify=False)
    s=summary(root);cfg=s['nodes'][0]['config'];assert cfg=={key:data[key] for key in fields}
    assert s['omitted_node_fields']==[{'id':'current','fields':['private_unknown_field']}]
    assert s['omitted_feature_fields']==['unknown_feature']
    text=json.dumps(s);assert 'private-value-should-not-leave' not in text and 'private-feature-value' not in text


def test_unknown_node_is_not_silently_omitted():
    root={'workflow':{'graph':{'nodes':[{'id':'future','data':{'type':'unadapted-human-input'}}],'edges':[]}}}
    with pytest.raises(HTTPException,match='不会省略'):summary(root)


def test_large_summary_is_not_truncated_or_partly_accepted():
    root={'workflow':{'graph':{'nodes':[{'id':'code','data':{'type':'code','code':'中'*(MAX_BYTES//3+1)}}],'edges':[]}}}
    with pytest.raises(HTTPException,match='不会截断'):summary(root)


def test_generated_code_is_reference_text_and_never_executed():
    root={'workflow':{'graph':{'nodes':[{'id':'code','data':{'type':'code','code':'raise AssertionError("不得执行")'}}],'edges':[]}}}
    assert summary(root)['nodes'][0]['config']['code'].startswith('raise AssertionError')


def test_saved_final_code_reaches_only_mocked_generation_and_not_credentials(client,monkeypatch):
    t,root=prepared(client);root=changed(root);t=capture(client,t,root);response,_=apply(client,t);t=response.json();p=provider(client)
    t['configuration']['assistant_provider_id']=p['id'];t['requirements_confirmed']=True;main.save_task(t);seen=[]
    async def model(provider,key,messages,**kw):seen.append(json.loads(messages[1]['content']));return json.dumps(candidate()),{'prompt_tokens':20,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']});assert response.status_code==200,response.text
    semantic=seen[0]['contract']['source']['semantics'];assert 'strip().upper()' in next(n for n in semantic['nodes'] if n['id']=='code')['config']['code']
    assert 'not-a-real-key' not in json.dumps(seen) and not response.json()['test_cases']


def test_old_confirmed_light_route_blocks_new_scope_until_explicit_new_confirmation(client,monkeypatch):
    t,p,light=setup(client);assert enable(client,t,light).status_code==200
    old=main.routing.get(t['id']);old.pop('scope_version');main.store.put('assistant_routing',t['id'],old)
    seen=[]
    async def model(*a,**kw):seen.append(a);return json.dumps(candidate()),{'prompt_tokens':20,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',model)
    s=state(client,t);assert s['required_scope_version']==18 and '范围已升级' in s['blocker']
    response=client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']});assert response.status_code==422 and not seen
    assert enable(client,t,light,scope_version=1).status_code==409
    assert enable(client,t,light).status_code==200
    assert state(client,t)['scope_version']==18 and not state(client,t)['blocker']
    assert client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']}).status_code==200 and len(seen)==1
    assert old['history'][0]['after']['scope_version']==18


def test_missing_observed_scope_version_cannot_reuse_old_client_ack(client):
    t,p,light=setup(client);s=state(client,t)
    response=client.patch(f"/api/tasks/{t['id']}/assistant-routing",json={'revision':t['revision'],'policy_revision':0,'enabled':True,'light_provider_id':light['id'],'provider_token':s['eligible'][0]['provider_token'],'acknowledge_scope':True,'note':'旧页面未展示扩大范围。'})
    assert response.status_code==422 and not state(client,t)['enabled']


def test_current_loop_variables_guards_and_assigner_are_explicit_in_case_semantics(client):
    from test_preserved_loop import native,review
    t,_=prepared(client);root=native();t=capture(client,t,root);url=f"/api/tasks/{t['id']}/dsl-merge"
    first=client.get(url).json();reviews=review(root)
    p=client.post(url+'/preview',json={'revision':t['revision'],'loop_reviews':reviews}).json()
    response=client.post(url+'/apply',json={'revision':t['revision'],'reference_id':p['reference_id'],'merge_token':p['merge_token'],'loop_reviews':reviews});assert response.status_code==200,response.text
    s=main.case_proposals.contract(response.json())['source']['semantics'];nodes={n['id']:n for n in s['nodes']}
    assert nodes['repeat']['config']['loop_variables'][0]['value']==0
    assert nodes['repeat__loop_update']['config']['items'][-1]['value']==['repeat__loop_progress','stagnant_rounds']
    assert 'next_stagnant' in nodes['repeat__loop_progress']['config']['code']


def test_previous_scope_two_does_not_approve_loop_initial_state_scope_three(client,monkeypatch):
    t,p,light=setup(client);enable(client,t,light);old=main.routing.get(t['id']);old['scope_version']=2;main.store.put('assistant_routing',t['id'],old)
    async def forbidden(*a,**kw):pytest.fail('旧范围未允许循环初始状态，不应派发')
    monkeypatch.setattr(main,'call_model',forbidden)
    assert '初始值' in state(client,t)['scope_note'] and state(client,t)['blocker']
    assert enable(client,t,light,scope_version=2).status_code==409
    assert client.post(f"/api/tasks/{t['id']}/case-proposal/generate",json={'revision':t['revision']}).status_code==422
