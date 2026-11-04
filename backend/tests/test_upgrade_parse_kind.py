import copy,json
import pytest
from test_assistant_routing import client,setup,forbid_routing_external_calls
from test_lightweight_upgrade import upgrade,generate,USAGE
from test_case_proposals import candidate
from app import main,planning


@pytest.mark.parametrize('raw',['{"x":1 "y":2}','{"x" 1}','{x:1}','{"x":"unfinished}','NOT JSON'],ids=['comma','colon','quoted_key','unfinished','plain_text'])
def test_known_syntax_failure_with_location_enters_exactly_one_upgrade(client,monkeypatch,raw):
    t,p,light=setup(client);assert upgrade(client,t,light).status_code==200;before=copy.deepcopy(main.get_task(t['id']));calls=[]
    async def fake(provider,*a,**kw):
        calls.append(provider['id']);return (raw if len(calls)==1 else json.dumps(candidate())),USAGE
    monkeypatch.setattr(main,'call_model',fake)
    r=generate(client,t);assert r.status_code==200,r.text
    assert calls==[light['id'],p['id']]
    op=main.get_task(t['id'])['planning_runs'][-1];first=op['phases'][0]['attempts'][0]
    assert first['failure_kind']=='json_syntax' and len(first['diagnostics'])==2
    assert '候选片段' in first['diagnostics'][1] and first['response_excerpt']==raw and first['cost_basis']=='reported_usage'
    assert op['attempts'][0]['failure_kind']=='json_syntax' and op['routing']['upgrade']['triggered'] is True
    assert len(main.budgets.get(t['id'])['entries'])==2 and all(e['status']=='settled' for e in main.budgets.get(t['id'])['entries'])
    saved=main.get_task(t['id'])
    for key in ('revision','requirements','configuration','requirements_confirmed','configuration_confirmed','test_cases'):
        assert saved.get(key)==before.get(key)


def test_upgrade_classification_does_not_depend_on_display_diagnostic_text(client,monkeypatch):
    t,p,light=setup(client);upgrade(client,t,light);calls=[]
    monkeypatch.setattr(planning,'_json_syntax_diagnostic',lambda error:'公开新版显示说明，不作为机器分类')
    async def fake(provider,*a,**kw):calls.append(provider['id']);return ('{"x":1 "y":2}' if len(calls)==1 else json.dumps(candidate())),USAGE
    monkeypatch.setattr(main,'call_model',fake)
    assert generate(client,t).status_code==200 and calls==[light['id'],p['id']]
    assert main.get_task(t['id'])['planning_runs'][-1]['attempts'][0]['diagnostics'][-1]=='公开新版显示说明，不作为机器分类'


@pytest.mark.parametrize('raw',[
    '{"x":1,"x":2}',
    '{"x":'+ '['*61+'0'+']'*61+'}',
    '{"x":NaN}',
    '{"x":"\\ud800"}',
    '[]',
    '"public root text"',
    '{"schema_version":1,"items":[],"open_issues":[],"notes":"invalid","failure_kind":"json_syntax"}',
],ids=['duplicate','depth','nonfinite','unicode','array_root','text_root','business_with_fake_marker'])
def test_non_syntax_problem_cannot_be_reclassified_as_upgrade(client,monkeypatch,raw):
    t,p,light=setup(client);upgrade(client,t,light);calls=[]
    async def fake(provider,*a,**kw):calls.append(provider['id']);return raw,USAGE
    monkeypatch.setattr(main,'call_model',fake)
    assert generate(client,t).status_code==422
    op=main.get_task(t['id'])['planning_runs'][-1]
    assert calls==[light['id']] and not op['routing']['upgrade']['triggered'] and not main.store.list('case_proposal')
    assert op['attempts'][0].get('failure_kind')!='json_syntax'
    assert op['attempts'][0]['response_excerpt']==raw and op['attempts'][0]['usage']==USAGE
    assert len(main.budgets.get(t['id'])['entries'])==1
