import copy,json
import pytest
from test_api import client,approved
from test_task_budget import provider,policy,USAGE,forbid_budget_external_calls
from app import main
from app.providers import ProviderError

SYNTAX='{\n "message":"SYNTHETIC_PRIVATE",\n "requirements_patch":{}\n "intake_review":{}\n}'
CASES=[('syntax',SYNTAX,'第4行，第2列'),('wrapped','公开前置说明\n```json\n'+SYNTAX+'\n```\n公开后置说明','第4行，第2列'),('duplicate','{"message":"SYNTHETIC_PRIVATE","message":"other","requirements_patch":{}}','重复字段'),('depth','{"private_field":'+'['*70+'0'+']'*70+'}','60'),('shape','{}','模型返回了不符合约定的结构'),('contract',json.dumps({'message':'SYNTHETIC_PRIVATE','requirements_patch':{},'intake_review':{'schema_version':1,'checks':[],'questions':[]}}),'模型需求检查未通过')]

@pytest.mark.parametrize('stream',[False,True])
@pytest.mark.parametrize('kind,raw,hint',CASES)
def test_interview_failure_has_safe_consistent_diagnostic_and_preserves_state_and_fee(client,monkeypatch,stream,kind,raw,hint):
    t=approved(client);provider(client);before=copy.deepcopy(t);calls=[]
    async def fake(*a,**kw):
        calls.append(kw)
        if stream:await kw['on_delta'](raw)
        return raw,USAGE
    monkeypatch.setattr(main,'call_model',fake)
    r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'核对这个公开草案。','mode':'review','stream_response':stream});assert r.status_code==200,r.text
    saved=r.json();attempt=saved['interview_attempts'][-1];note=saved['messages'][-1]['content']
    op=client.get(f"/api/tasks/{t['id']}/interviews").json()['operations'][-1]
    assert hint in note and note==attempt['reason']==op['note']
    assert 'SYNTHETIC_PRIVATE' not in note and 'private_field' not in note and 'requirements_patch' not in note
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(op) and op['applied'] is False and op['status']=='failed'
    assert attempt['response_excerpt']==raw and attempt['response_truncated'] is False and attempt['applied'] is False
    assert attempt['usage']==USAGE and len(calls)==1
    for field in ('revision','requirements','configuration','workflow_plan','agent_plan','requirements_confirmed','configuration_confirmed','artifact','dify_app_id','runs'):
        assert saved.get(field)==before.get(field),field
    entries=main.budgets.get(t['id'])['entries'];assert len(entries)==1 and entries[0]['status']=='settled' and entries[0]['cost_basis']=='reported_usage'
    if kind in {'syntax','wrapped'}:
        assert '从0计字符偏移' in note and '抽取后的候选片段' in note and '公开前置说明' not in note
    elif kind in {'shape','contract'}:assert '字符偏移' not in note

@pytest.mark.parametrize('stream',[False,True])
def test_provider_failure_keeps_provider_reason_without_json_classification(client,monkeypatch,stream):
    t=approved(client);provider(client);calls=[]
    async def fake(*a,**kw):calls.append(True);raise ProviderError('公开固定供应商失败',usage=USAGE)
    monkeypatch.setattr(main,'call_model',fake)
    r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'核对草案。','stream_response':stream});assert r.status_code==200
    note=r.json()['messages'][-1]['content'];assert note=='公开固定供应商失败' and 'JSON' not in note and len(calls)==1
    assert r.json()['requirements']==t['requirements'] and r.json()['requirements_confirmed']==t['requirements_confirmed']
    assert main.budgets.get(t['id'])['entries'][0]['usage']==USAGE

@pytest.mark.parametrize('stream',[False,True])
def test_unknown_usage_keeps_budget_stop_ahead_of_json_location(client,monkeypatch,stream):
    t=approved(client);provider(client);policy(client,t);calls=[]
    async def fake(*a,**kw):calls.append(True);return SYNTAX,{}
    monkeypatch.setattr(main,'call_model',fake)
    r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'核对草案。','stream_response':stream});assert r.status_code==200
    saved=r.json();note=saved['messages'][-1]['content'];assert '费用不明' in note and '字符偏移' not in note and saved['status']=='paused' and len(calls)==1
    assert saved['requirements']==t['requirements'] and saved['requirements_confirmed']==t['requirements_confirmed']
    entries=main.budgets.get(t['id'])['entries'];assert len(entries)==1 and entries[0]['status']=='unknown' and entries[0]['reserved_usd'] is not None
