"""Regression for the public C1 blank-task response shape; no supplier calls."""
import copy,json
import pytest
from test_api import client
from test_task_budget import provider
from app import main
from app.intake import BASE,PATTERNS,ReviewContractError,model_review_outline,topics,validate_review

VAGUE='我想从零做一个公开合成的售后知识问答Workflow，请先追问，不要提前搭建。'

def response():
    question=dict(topic='knowledge',question='资料范围是什么？',recommendation='先明确资料',reason='避免猜测',experience='先追问',cost='费用待核对',manual_work='需说明资料')
    return {'message':'先明确资料范围，不搭建。','requirements_patch':{'knowledge':'拟议（待确认）：只用公开合成知识库检索。'},'intake_review':{'schema_version':1,'checks':[{'topic':key,'status':'needs_input','detail':'尚待明确','evidence':[]} for key in BASE],'questions':[question]}}

@pytest.mark.parametrize('text,expected',[
    ('拟议知识库检索',{'retrieval'}),('拟议订单 API',{'external'}),
    ('拟议批量检索',{'batch','retrieval'}),('拟议扫描PDF解析',{'document_processing'}),
])
def test_catalog_covers_patch_triggered_ids_without_enabling_untriggered_topics(text,expected):
    task={'app_type':'workflow','requirements':{key:'' for key in BASE},'messages':[],'materials':[]}
    before=copy.deepcopy(task);outline=model_review_outline(task)
    assert outline['required_check_topics']==list(BASE)
    catalog={row['id']:row for row in outline['conditional_check_topics']}
    assert {key:row['text_pattern'] for key,row in catalog.items()}==PATTERNS
    task['requirements']['knowledge']=text
    assert {row['id'] for row in topics(task)}-set(BASE)==expected
    assert expected <= catalog.keys()
    assert before['requirements']=={key:'' for key in BASE}
    assert outline['question_fields'][-1]=='manual_work'

@pytest.mark.parametrize('failure',['missing_retrieval','camel_case_question','bad_evidence',None])
def test_blank_task_patch_uses_final_topics_and_keeps_strict_gate(client,monkeypatch,failure):
    t=client.post('/api/tasks',json={'name':'公开候选专项回归','app_type':'workflow'}).json();p=provider(client)
    t=client.patch('/api/tasks/'+t['id'],json={'configuration':{'assistant_provider_id':p['id']}}).json()
    value=response()
    if failure!='missing_retrieval':
        value['intake_review']['checks'].append({'topic':'retrieval','status':'needs_input','detail':'检索范围待确认','evidence':[]})
    if failure=='camel_case_question':
        q=value['intake_review']['questions'][0];q['manualWork']=q.pop('manual_work')
    if failure=='bad_evidence':
        value['intake_review']['checks'][0]['evidence']=[{'kind':'message','id':'missing','quote':'不存在'}]
    calls=[]
    async def model(*args,**kwargs):
        context=json.loads(args[2][1]['content'].split('当前任务资料：',1)[1]);outline=context['intake_response_outline']
        assert len(outline['required_check_topics'])==8
        assert 'retrieval' in {x['id'] for x in outline['conditional_check_topics']}
        assert 'manual_work' in outline['question_fields'] and 'manualWork' not in outline['question_fields']
        calls.append(1);return json.dumps(value,ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',model)
    r=client.post('/api/tasks/'+t['id']+'/messages',json={'content':VAGUE});assert r.status_code==200,r.text
    after=r.json();assert calls==[1] and not after['requirements_confirmed'] and not after['configuration_confirmed']
    assert not after.get('workflow_plan') and not after.get('artifact') and not after.get('runs')
    operation=client.get('/api/tasks/'+t['id']+'/interviews').json()['operations'][0]
    if failure:
        assert operation['status']=='failed' and operation['applied'] is False
        assert after['requirements']==t['requirements'] and not after.get('intake_review')
        assert len(after['interview_attempts'])==1 and not after['interview_attempts'][0]['applied']
        assert '未自动重试' in after['messages'][-1]['content']
        if failure=='missing_retrieval':assert '当前标准为 9 项' in after['messages'][-1]['content']
    else:
        assert operation['status']=='applied'
        assert len(after['intake_review']['review']['checks'])==9
        assert after['intake_review']['review']['questions'] and after['requirements']['knowledge']==value['requirements_patch']['knowledge']
    ledger=client.get('/api/tasks/'+t['id']+'/budget').json()
    assert len(ledger['entries'])==1 and ledger['entries'][0]['status']=='settled'
