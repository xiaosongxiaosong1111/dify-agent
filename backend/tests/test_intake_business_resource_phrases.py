import copy,json
import pytest
from test_api import client
from test_intake import new,REQ,review as review_for_task
from test_task_budget import provider,forbid_budget_external_calls
from app import main
from app.intake import topics,model_review_outline,validate_review,ReviewContractError,sources


@pytest.mark.parametrize('phrase,topic',[('根据资料回答售后问题','retrieval'),('资料问答','retrieval'),('查询订单','external'),('订单查询','external')])
@pytest.mark.parametrize('source',['requirement','message'])
def test_explicit_business_expression_requires_resource_condition_review(phrase,topic,source):
    t={'app_type':'workflow','requirements':{k:'' for k in REQ},'messages':[]}
    if source=='message':t['messages']=[{'role':'user','content':phrase}]
    else:t['requirements']['goal']=phrase
    assert topic in {x['id'] for x in topics(t)}
    assert topic in model_review_outline(t)['required_check_topics']

@pytest.mark.parametrize('goal',['把单条文本转成大写。','整理订单字段的显示名称。','统计订单数量，不连接其它资源。','阅读资料后整理本地文字，不做问答。'])
def test_general_text_or_order_noun_does_not_invent_retrieval_or_external_need(goal):
    t={'app_type':'workflow','requirements':{**{k:'' for k in REQ},'goal':goal},'messages':[]}
    assert not {'retrieval','external'} & {x['id'] for x in topics(t)}

def response(kind):
    names=list(REQ)+(['memory','dialogue'] if kind in {'advanced-chat','agent'} else [])+(['agent_tools'] if kind=='agent' else [])+['retrieval','external']
    quote='帮我做一个电商售后助手，能根据资料回答售后问题并查询订单。'
    rows=[{'topic':name,'status':'complete' if name=='goal' else 'needs_input','detail':'目标明确，其余资源与业务条件仍需补充。','evidence':[{'kind':'message','id':'1','quote':quote}] if name=='goal' else []} for name in names]
    questions=[{'topic':name,'question':'请明确本项。','recommendation':'先补说明，不猜资源。','reason':'避免未经核对的方案。','experience':'明确后再设计。','cost':'资源费用待核对。','manual_work':'提供条件。'} for name in ('audience','input','knowledge')]
    return {'message':'目标已记录；资料范围和订单接入或模拟均待确认。','requirements_patch':{'goal':'构建电商售后助手，根据资料回答售后问题，并能查询订单。'},'intake_review':{'schema_version':1,'checks':rows,'questions':questions}}

@pytest.mark.parametrize('kind',['workflow','advanced-chat','agent'])
def test_vague_interview_uses_consistent_resource_topics_without_assuming_availability(client,monkeypatch,kind):
    t=new(client,kind,filled=False);provider(client);seen=[];raw=response(kind)
    async def fake(p,k,m,**kw):
        seen.append(json.loads(m[1]['content'].split('当前任务资料：',1)[1]))
        return json.dumps(raw,ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',fake)
    r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'帮我做一个电商售后助手，能根据资料回答售后问题并查询订单。'})
    assert r.status_code==200,r.text
    saved=r.json();assert saved.get('intake_review') and saved['intake_review']['source']=='model'
    expected={x['topic'] for x in raw['intake_review']['checks']}
    assert {x['id'] for x in seen[0]['intake_standard']}==expected
    assert set(seen[0]['intake_response_outline']['required_check_topics'])==expected
    assert saved['requirements']['goal']==raw['requirements_patch']['goal']
    assert not saved['requirements_confirmed'] and not saved.get('artifact') and not saved.get('workflow_plan')
    assert saved['configuration']['dataset_ids']==[] and not saved.get('environment_id')
    state=client.get(f"/api/tasks/{t['id']}/intake").json();assert not state['can_confirm']
    assert {'retrieval','external'} <= {x['topic'] for x in state['gaps']}
    assert len(main.budgets.get(t['id'])['entries'])==1

@pytest.mark.parametrize('change',['extra','missing'])
def test_topic_contract_still_rejects_unknown_or_missing_topics(change):
    value=response('advanced-chat');t={'revision':1,'app_type':'advanced-chat','requirements':{**{k:'' for k in REQ},'goal':value['requirements_patch']['goal']},'messages':[{'role':'assistant','content':'开始'},{'role':'user','content':'帮我做一个电商售后助手，能根据资料回答售后问题并查询订单。'}],'materials':[]}
    v=value['intake_review'];assert validate_review(t,v)==v
    bad=copy.deepcopy(v)
    if change=='missing':bad['checks']=[x for x in bad['checks'] if x['topic']!='external']
    else:bad['checks'].append({**bad['checks'][-1],'topic':'invented_resource'})
    with pytest.raises(ReviewContractError):validate_review(t,bad)

def test_order_resource_topic_can_be_explicitly_inapplicable_for_declared_local_mock():
    t={'revision':1,'app_type':'workflow','requirements':{**REQ,'goal':'查询订单，仅演示。','knowledge':'明确只用无网络合成表，不连接真实订单系统。'},'messages':[],'materials':[]}
    value=review_for_task(t);row=next(x for x in value['checks'] if x['topic']=='external');row['status']='not_applicable';row['evidence']=[{'kind':'requirement','id':'knowledge','quote':t['requirements']['knowledge']}]
    assert validate_review(t,value)==value

def test_no_case_source_keeps_pure_requirement_validation_without_revision_metadata():
    t={'app_type':'workflow','requirements':copy.deepcopy(REQ),'messages':[],'materials':[]}
    assert sources(t)[('requirement','goal')]==REQ['goal']
    assert not any(kind=='test_case' for kind,_ in sources(t))
    assert validate_review(t,review_for_task(t))==review_for_task(t)
