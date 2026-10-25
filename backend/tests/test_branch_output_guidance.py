"""Real request construction, complete example compilation, unchanged rejection."""
import copy,json,re
from pathlib import Path
import yaml
from test_intake import client,new,manual,forbid_intake_external_calls
from test_task_budget import provider
from app import main

def example():
    text=(Path(__file__).resolve().parents[2]/'docs/workflow-plan-contract.md').read_text('utf-8')
    section=text.split('## Required root branch-output rule\n',1)[1]
    return json.loads(re.search(r'```json\n(.*?)\n```',section,re.S)[1])

def ready(client):
    p=provider(client);task=new(client)
    task=client.patch(f"/api/tasks/{task['id']}",json={'requirements':{'goal':'单条文字分支演示，只处理yes判断。','output':'只返回result文字。','rules':'query等于yes时返回yes，否则返回no。','tests':'输入yes返回yes；输入other返回no。'},'configuration':{'assistant_provider_id':p['id'],'resource_plan':'仅本机静态构建和下载，不执行模型以外的平台操作。'}}).json()
    task=manual(client,task).json()
    response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':'requirements'})
    assert response.status_code==200,response.text
    return response.json()

def test_actual_planning_prompt_has_complete_branch_example_and_builds(client,monkeypatch):
    task=ready(client);candidate=example();calls=[]
    async def model(provider,key,messages,**kwargs):
        calls.append(copy.deepcopy(messages))
        prompt=messages[0]['content']
        assert '## Required root branch-output rule' in prompt
        assert 'output field names MUST be unique' in prompt
        assert 'Existing_plan_context remains the full preservation baseline' in prompt
        assert 'Chatflow retains its answer-node contract' in prompt
        shown=json.loads(re.search(r'Complete minimal Workflow example.*?```json\n(.*?)\n```',prompt,re.S)[1])
        assert shown==candidate
        return json.dumps(candidate),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert response.status_code==200,response.text
    saved=response.json();assert saved['workflow_plan']==candidate and len(calls)==1
    assert not saved['configuration_confirmed'] and not saved['artifact']
    response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':saved['revision'],'kind':'configuration'})
    assert response.status_code==200,response.text
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':saved['revision']})
    assert response.status_code==200,response.text
    native=yaml.safe_load(client.get(f"/api/tasks/{task['id']}/artifact").text)
    ends=[n for n in native['workflow']['graph']['nodes'] if n['data']['type']=='end']
    assert len(ends)==2 and {n['id'] for n in ends}=={'yes_end','no_end'}
    for node in ends:
        assert len(node['data']['outputs'])==1 and node['data']['outputs'][0]['variable']=='result'
        assert node['data']['outputs'][0]['value_selector']==[node['id'].replace('_end','_text'),'output']

def test_generated_duplicate_branch_outputs_still_stop_without_fix_or_retry(client,monkeypatch):
    task=ready(client);candidate=example()
    outputs=[node['config']['outputs'][0] for node in candidate['nodes'] if node['type']=='end']
    candidate['nodes']=[n for n in candidate['nodes'] if n['type']!='end']+[{'id':'end','type':'end','config':{'outputs':outputs}}]
    for edge in candidate['edges']:
        if edge['target'].endswith('_end'):edge['target']='end'
    original=copy.deepcopy(candidate);calls=[]
    async def model(*args,**kwargs):
        calls.append(1);return json.dumps(candidate),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',model)
    response=client.post(f"/api/tasks/{task['id']}/plan/generate",json={'revision':task['revision']})
    assert response.status_code==422,response.text
    saved=client.get(f"/api/tasks/{task['id']}").json();run=saved['planning_runs'][-1]
    assert len(calls)==1 and run['last_candidate']==original and json.loads(run['last_response_excerpt'])==original
    assert any('字段名称重复' in e for e in run['diagnostics'])
    assert sum('不保证在所有路径上游' in e for e in run['diagnostics'])==2
    assert not saved['workflow_plan'] and not saved['artifact'] and not saved['configuration_confirmed'] and not saved['runs']
    assert saved['requirements']==task['requirements'] and saved['configuration']==task['configuration']
