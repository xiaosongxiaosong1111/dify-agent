import copy,json
import pytest
from test_api import client,approved,planning_provider
from test_workflow_plan import base_plan
from app import main
from app.storage import Store


def prepared(client):
    planning_provider(client);task=approved(client);plan=base_plan('workflow')
    task=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan}).json()
    task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'configuration'}).json()
    task=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']}).json()
    # Historical platform binding fixture only; the transport stays forbidden.
    task['dify_app_id']='prior-owned-app';main.store.put('task',task['id'],task)
    return task,plan


def respond(monkeypatch,plan):
    calls=[]
    async def controlled(provider,key,messages,**kwargs):
        calls.append(messages);return json.dumps(plan,ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':50}
    monkeypatch.setattr(main,'call_model',controlled);return calls


@pytest.mark.parametrize('change',['prompt','input','model','title','extra_node'])
def test_valid_changed_candidate_is_retained_not_automatically_adopted(client,monkeypatch,change):
    task,old=prepared(client);candidate=copy.deepcopy(old)
    if change=='prompt':candidate['nodes'][1]['config']['system_prompt']='PRIVATE-CONTENT-ONLY'
    elif change=='input':candidate['nodes'][0]['config']['variables'][0]['type']='paragraph'
    elif change=='model':candidate['nodes'][1]['config']['model']={'provider':'test/provider','name':'test-model','mode':'chat','completion_params':{'temperature':0.2,'max_tokens':512}}
    elif change=='title':candidate['nodes'][1]['title']='PRIVATE-CONTENT-ONLY'
    else:
        end=candidate['nodes'][-1];candidate['nodes'].insert(-1,{'id':'added','type':'template-transform','config':{'template':'PRIVATE-CONTENT-ONLY','variables':[]}})
        candidate['edges'][-1]['target']='added';candidate['edges'].append({'source':'added','target':end['id']});end['config']['outputs'][0]['value_selector']=['added','output']
    calls=respond(monkeypatch,candidate)
    r=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert r.status_code==422,r.text
    result=client.get(f"/api/tasks/{task['id']}").json();run=result['planning_runs'][-1]
    assert len(calls)==1 and run['status']=='paused' and run['stop_reason']=='replanning_review'
    assert result['revision']==task['revision'] and result['workflow_plan']==old
    assert result['artifact']==task['artifact'] and result['dify_app_id']=='prior-owned-app'
    assert result['requirements_confirmed'] and result['configuration_confirmed'] and not result['runs']
    assert run['last_candidate']==candidate and run['attempts'][0]['status']=='valid'
    summary=run['scope_change_summary'];assert summary['verification']=='replanning_review_summary'
    assert summary['areas'] or summary['nodes'];assert 'PRIVATE-CONTENT-ONLY' not in str(summary)
    assert main.budgets.get(task['id'])['entries'][0]['status']=='settled'
    restarted=Store(main.store.root).get('task',task['id']);assert restarted['planning_runs'][-1]['last_candidate']==candidate


def test_reading_retained_candidate_is_local_and_explicit_save_invalidates_prior_approvals(client,monkeypatch):
    task,old=prepared(client);candidate=copy.deepcopy(old);candidate['nodes'][1]['config']['system_prompt']='已明确的新提示'
    calls=respond(monkeypatch,candidate)
    client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    paused=client.get(f"/api/tasks/{task['id']}").json();run=paused['planning_runs'][-1]
    r=client.get(f"/api/tasks/{task['id']}/planning/{run['id']}/candidate");assert r.status_code==200,r.text
    retained=r.json();assert json.loads(retained['plan_text'])==candidate and not retained['formal_plan_changed'] and not retained['network_requested']
    assert client.get(f"/api/tasks/{task['id']}").json()==paused
    r=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan_text':retained['plan_text']});assert r.status_code==200,r.text
    adopted=r.json();assert adopted['workflow_plan']==candidate and adopted['revision']==task['revision']+1
    assert not adopted['artifact'] and not adopted['dify_app_id'] and not adopted['configuration_confirmed']
    assert adopted['requirements_confirmed'] and not adopted['runs'] and len(calls)==1
    assert adopted['planning_runs'][-1]['stop_reason']=='replanning_review'
    assert client.post(f"/api/tasks/{task['id']}/build",json={'revision':adopted['revision']}).status_code==422


def test_identical_regeneration_and_initial_generation_do_not_create_false_change_summary(client,monkeypatch):
    task,plan=prepared(client);calls=respond(monkeypatch,plan)
    r=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']});assert r.status_code==200,r.text
    assert r.json()['workflow_plan']==plan and 'scope_change_summary' not in r.json()['planning_runs'][-1]
    first=approved(client);calls=respond(monkeypatch,plan)
    r=client.post(f"/api/tasks/{first['id']}/plan/generate",json={'revision':first['revision']});assert r.status_code==200,r.text
    assert len(calls)==1 and r.json()['workflow_plan']==plan and 'scope_change_summary' not in r.json()['planning_runs'][-1]


@pytest.mark.parametrize('mode',['advanced-chat','agent'])
def test_other_app_types_keep_their_saved_plan_until_explicit_review(client,monkeypatch,mode):
    planning_provider(client)
    if mode=='agent':
        from test_agent_plan import prepare
        task=prepare(client);key='agent_plan'
    else:
        task=approved(client,app_type=mode);plan=base_plan(mode)
        result=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':plan})
        assert result.status_code==200,result.text
        task=result.json();key='workflow_plan'
    old=copy.deepcopy(task[key]);candidate=copy.deepcopy(old)
    if mode=='agent':candidate['system_prompt']='只改文字指令，保留原生Agent类型。'
    else:candidate['nodes'][1]['config']['system_prompt']='只改文字指令，保留Chatflow会话入口。'
    calls=respond(monkeypatch,candidate)
    result=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert result.status_code==422,result.text
    current=client.get(f"/api/tasks/{task['id']}").json()
    assert current['app_type']==mode and current['revision']==task['revision'] and current[key]==old
    assert current['planning_runs'][-1]['stop_reason']=='replanning_review' and len(calls)==1
    run=current['planning_runs'][-1]
    retained=client.get(f"/api/tasks/{task['id']}/planning/{run['id']}/candidate").json()
    assert retained['app_type']==mode and json.loads(retained['plan_text'])==candidate and not retained['formal_plan_changed']
