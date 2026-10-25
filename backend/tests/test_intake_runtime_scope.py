import copy,json
import pytest
from test_api import client,forbid_api_external_calls
from test_intake import REQ,new,review
from test_task_budget import provider
from app import main
from app.intake import topics,validate_review,ReviewContractError,summary

LOCAL_INPUT='Sierra 本机普通试跑接口对必填文本以 strip 判空，派发前拒绝且不创建运行记录；不证明 Dify 直接入口行为。'
LOCAL_ERRORS='Sierra 本机接口对已知平台失败返回错误终态并保留诊断，未知终态不算成功，成功 result 与 HTTP 错误分开；不证明 Dify 直调或图节点实际错误传播。'

def task():
    req=copy.deepcopy(REQ);req['knowledge']='只使用已声明知识库检索资料。'
    return {'revision':1,'app_type':'workflow','requirements':req,'messages':[],'materials':[],'workflow_plan':None,'intake_required':True}
def ids(t):return {x['id'] for x in topics(t)}
def annotated(t):
    result=copy.deepcopy(t);result['requirements']['input']+='（'+LOCAL_INPUT+'）';result['requirements']['exceptions']+='（'+LOCAL_ERRORS+'）';return result

def test_known_local_runtime_explanations_do_not_add_business_external_topic():
    before=task();after=annotated(before)
    assert len(ids(before))==9 and ids(after)==ids(before)
    assert after['requirements']['input'].endswith('）')

@pytest.mark.parametrize('business',[
    '调用Sierra 本机接口对必填文本以 strip 判空。',
    '访问现有Sierra 本机接口对已知平台失败返回错误终态。',
    '通过Sierra 本机普通试跑接口对必填文本以 strip 判空。',
    '调用订单 API 获取订单。','向 https://orders.example.invalid/query 发请求。',
    '业务读取数据库。','对接外部系统。','收到 HTTP 错误应停止。',
    'Sierra 本机接口返回订单详情。',
])
def test_actual_integration_or_ambiguous_technical_scope_still_requires_external(business):
    t=annotated(task());t['requirements']['rules']+=' '+business;assert 'external' in ids(t)

def test_native_http_node_keeps_external_even_when_text_only_mentions_local_guarantees():
    t=annotated(task());t['workflow_plan']={'nodes':[{'id':'remote','type':'http-request','config':{}}],'edges':[]}
    assert 'external' in ids(t)

def test_strict_review_and_needs_input_remain_without_implicit_business_confirmation():
    t=annotated(task());value=review(t,gap='retrieval');result=validate_review(t,value)
    t['intake_review']={'source':'model','review':result,'revision':1,'context_digest':'old'}
    assert len(result['checks'])==9 and result['questions'] and not summary(t)['can_confirm']
    bad=copy.deepcopy(value);bad['checks'][0]['evidence'][0]['quote']='不存在的引文'
    with pytest.raises(ReviewContractError,match='引文'):validate_review(t,bad)
    t['requirements']['rules']+=' 调用订单 API。'
    with pytest.raises(ReviewContractError,match='主题数量'):validate_review(t,value)

def test_valid_annotated_candidate_can_be_saved_as_unconfirmed_question_without_external_calls(client,monkeypatch):
    t=new(client);t=client.patch('/api/tasks/'+t['id'],json={'requirements':task()['requirements']}).json();provider(client)
    proposal=annotated(t);value=review(proposal,gap='retrieval')
    for row in value['checks']:
        for evidence in row['evidence']:
            if evidence['kind']=='requirement':evidence['quote']=t['requirements'][evidence['id']]
    calls=[]
    async def fake(*a,**kw):calls.append(1);return json.dumps({'message':'需求草案待澄清资料引用。','requirements_patch':proposal['requirements'],'intake_review':value},ensure_ascii=False),{'prompt_tokens':1,'completion_tokens':1}
    monkeypatch.setattr(main,'call_model',fake)
    response=client.post('/api/tasks/'+t['id']+'/messages',json={'content':'继续核对已保存需求，不创建资源。'});assert response.status_code==200,response.text
    after=response.json();assert after.get('intake_review') and after['intake_review']['review']['questions'] and len(after['intake_review']['review']['checks'])==9
    assert after['requirements']==proposal['requirements'] and not after['requirements_confirmed'] and not after['configuration_confirmed']
    assert calls==[1] and after['runs']==[] and after['artifact'] is None and after['dify_app_id'] is None
