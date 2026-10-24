"""Compare planning's entry contract with actual local dispatch, without external calls."""
import copy,json
import pytest
from test_api import client,approved,planning_provider,create_env,forbid_api_external_calls
from test_workflow_plan import base_plan
from test_agent_plan import prepare as agent_task
from app import main


@pytest.mark.parametrize('kind',['text-input','paragraph'])
def test_workflow_planner_gets_only_the_existing_local_required_text_guarantee(client,monkeypatch,kind):
    planning_provider(client);env=create_env(client);task=approved(client,env_id=env['id']);seen=[]
    plan=base_plan();plan['nodes'][0]['config']['variables'][0]['type']=kind
    plan['nodes'][0]['config']['variables'].append({'variable':'note','type':kind,'required':False})
    async def model(provider,key,messages,**kwargs):
        context=json.loads(messages[1]['content']);seen.append(context)
        assert '检索事实来源边界' in messages[0]['content']
        assert '即使它们在requirements.rules中' in messages[0]['content']
        assert '用户明确允许独立静态事实来源时按其范围处理' in messages[0]['content']
        gate=context['sierra_runtime_entry']
        assert gate['scope']=='sierra_manual_workflow_run' and gate['based_on']=='final_artifact_start_variables'
        assert gate['required_text_types']==['text-input','paragraph'] and gate['reject_blank_before_dispatch'] is True
        assert gate['normalizes_submitted_text'] is False and gate['direct_dify_entry_verified'] is False
        return json.dumps(plan),{'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',model)
    r=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']});assert r.status_code==200,r.text
    task=r.json();assert len(seen)==1
    task=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'configuration'}).json()
    r=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert r.status_code==200,r.text
    task=r.json();task['dify_app_id']='only-isolated-app';main.save_task(task)
    client.patch(f"/api/environments/{env['id']}",json={'service_app_id':'only-isolated-app','service_api_key':'isolated-runtime'})
    calls=[]
    async def remote(self,inputs):
        calls.append(copy.deepcopy(inputs));return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
    monkeypatch.setattr(main.DifyClient,'run_workflow',remote)
    before=copy.deepcopy(main.get_task(task['id']))
    # The contract must describe actual rejection before either dispatch or a run record.
    for value in ('','   ','\t\n','\u3000'):
        r=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':value}})
        assert r.status_code==422,r.text
        assert calls==[] and main.get_task(task['id'])==before
    # Nonblank input is not stripped or silently normalized.
    inputs={'query':'  ZXRET715  ','note':'   '}
    r=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':inputs})
    assert r.status_code==200,r.text
    assert calls==[inputs] and r.json()['runs'][-1]['input']==inputs
    gate=seen[0]['sierra_runtime_entry']
    for terminal,label in [('failed','known_platform_failed_terminal'),(None,'unknown_platform_terminal')]:
        async def failed_remote(self,values):
            calls.append(copy.deepcopy(values));return {'data':{'status':terminal,'error':'synthetic failure','outputs':{}}}
        monkeypatch.setattr(main.DifyClient,'run_workflow',failed_remote)
        response=client.post(f"/api/tasks/{task['id']}/run",json={'revision':task['revision'],'input':{'query':'failure-'+label}})
        assert response.status_code==gate[label]['http_status']
        assert set(response.json())=={'detail'} and gate[label]['http_success_result'] is False
        saved=main.get_task(task['id']);record=saved['runs'][-1]
        assert saved['status']==gate[label]['task_status'] and record['status']==gate[label]['run_status']
        assert record['result']['data']['status']==terminal and record.get('evaluation',{}).get('status')!='passed'


def test_new_entry_context_does_not_answer_or_remove_real_missing_business_decisions(client,monkeypatch):
    planning_provider(client);task=approved(client);before=copy.deepcopy(task);calls=[]
    async def model(provider,key,messages,**kwargs):
        calls.append(messages)
        assert '冲突则返回needs_decision' in messages[0]['content']
        return json.dumps({'error':'未指定哪套退款规则','needs_decision':['适用哪个退款政策版本？']}),{'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',model)
    r=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert r.status_code==422 and len(calls)==1
    saved=main.get_task(task['id']);op=saved['planning_runs'][-1]
    assert op['stop_reason']=='needs_decision' and op['decision_report']['questions'][0]['question']=='适用哪个退款政策版本？'
    for key in ('requirements','configuration','workflow_plan','artifact','runs','revision'):
        assert saved.get(key)==before.get(key)


def test_workflow_entry_guarantee_is_not_exported_as_agent_platform_capability(client,monkeypatch):
    planning_provider(client);task=agent_task(client);calls=[]
    async def model(provider,key,messages,**kwargs):
        context=json.loads(messages[1]['content']);calls.append(context)
        assert context['sierra_runtime_entry'] is None
        assert '检索事实来源边界' not in messages[0]['content']
        return json.dumps(task['agent_plan']),{'prompt_tokens':100,'completion_tokens':30}
    monkeypatch.setattr(main,'call_model',model)
    r=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert r.status_code==200,r.text
    assert len(calls)==1
