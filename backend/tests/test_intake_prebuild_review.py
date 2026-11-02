"""Public regression from 206: intake item review is not batch business processing."""
import copy,json
from pathlib import Path
import pytest
from test_api import client
from test_task_budget import provider
from app import main
from app.intake import topics,model_review_outline,validate_review,ReviewContractError,model_sources

FIXTURE=Path(__file__).resolve().parents[2]/'tools/c1-resume360/fixture.json'
PHRASE='先整理草案和逐项核对，待我确认再搭建。'
NO_JOINER='先整理草案逐项核对，待用户确认后再搭建。'
PRESERVE_NODES='其余节点、字段、顺序、边、模型参数、检索绑定、代码、状态和固定无答案文案须逐项保持。'

def task(phrase=PHRASE):
    req=json.loads(FIXTURE.read_text(encoding='utf-8'))['requirements']
    req['goal']+=' '+phrase
    return {'app_type':'workflow','requirements':req,'messages':[{'role':'user','content':'请按已声明资料回答，不扩充外部范围；'+phrase}],'materials':[],'workflow_plan':None}

def ids(t):return {row['id'] for row in topics(t)}

@pytest.mark.parametrize('phrase',[
    PHRASE,'先整理草案和逐项核对，待用户确认再搭建。',
    '先整理需求草案与逐项检查，待我确认后再构建。',
    '先草案并逐项复核，待用户确认后再生成流程。',
    NO_JOINER,'先整理需求草案逐项检查，待我确认后再构建。',
    PRESERVE_NODES,'现有节点ID与模型参数必须逐项保留不变。',
    '其他节点逐项保持。','其它节点和代码应逐项保留。',
])
def test_explicit_prebuild_intake_phrase_does_not_add_batch_or_modify_sources(phrase):
    t=task(phrase);before=copy.deepcopy(t);assert len(ids(t))==9 and 'batch' not in ids(t)
    assert t==before
    assert any(phrase in s['text'] for s in model_sources(t))
    outline=model_review_outline(t)
    assert 'batch' not in outline['required_check_topics'] and '同一topic最多一问' in outline['question_rule']
    assert '先整理草案逐项核对' in outline['prebuild_review_rule']

@pytest.mark.parametrize('business',[
    '逐项核对订单，待我确认再搭建。','逐项处理工单。','多条退货记录。',
    '输入为数组。','批量处理。','iteration 节点。','batch processing。',
    '先整理草案和逐项核对订单，待我确认再搭建。',
    '业务需要逐项核对，待我确认再搭建。',
    '先整理草案逐项核对订单，待用户确认后再搭建。',
    PRESERVE_NODES+'订单逐项处理，保留原顺序。',
    PRESERVE_NODES+'输入为数组。',PRESERVE_NODES+'多条工单。',
    PRESERVE_NODES+'批量处理业务数据。',
    '其他节点逐项保持订单处理结果。',
    '其他字段逐项保持。',
])
def test_real_itemwise_business_is_preserved_alongside_prebuild_phrase(business):
    t=task();t['requirements']['rules']+=' '+business;assert 'batch' in ids(t)

def test_existing_iteration_graph_still_requires_batch():
    t=task();t['workflow_plan']={'nodes':[{'id':'items','type':'iteration','config':{}}],'edges':[]}
    assert 'batch' in ids(t)

def review(t):
    return {'schema_version':1,'checks':[{'topic':row['id'],'status':'needs_input','detail':'待核对','evidence':[]} for row in topics(t)],'questions':[{'topic':'rules','question':'请核对问题文本与事实依据的边界。','recommendation':'问题只用于定位资料，请确认。','reason':'避免扩大事实依据。','experience':'明确再继续。','cost':'尚未调用运行模型。','manual_work':'需明确本项。'}]}

def test_duplicate_topic_still_rejected_instead_of_auto_merged():
    t=task();value=review(t);value['questions'].append(copy.deepcopy(value['questions'][0]));before=copy.deepcopy(value)
    with pytest.raises(ReviewContractError,match='追问主题重复'):validate_review(t,value)
    assert value==before

def test_missing_required_topic_and_bad_evidence_still_rejected():
    t=task();value=review(t);value['checks'].pop()
    with pytest.raises(ReviewContractError,match='主题数量'):validate_review(t,value)
    value=review(t);value['checks'][0]['evidence']=[{'kind':'message','id':'missing','quote':'不存在'}]
    with pytest.raises(ReviewContractError,match='引文不存在'):validate_review(t,value)

@pytest.mark.parametrize('duplicate',[False,True])
@pytest.mark.parametrize('phrase',[PHRASE,NO_JOINER,PRESERVE_NODES])
def test_normal_message_api_uses_nine_topics_and_keeps_review_gate(client,monkeypatch,duplicate,phrase):
    t=client.post('/api/tasks',json={'name':'公开搭建前核对回归','app_type':'workflow'}).json();p=provider(client)
    t=client.patch('/api/tasks/'+t['id'],json={'requirements':task()['requirements'],'configuration':{'assistant_provider_id':p['id']}}).json()
    calls=[]
    async def model(*args,**kw):
        context=json.loads(args[2][1]['content'].split('当前任务资料：',1)[1])
        assert len(context['intake_response_outline']['required_check_topics'])==9
        assert 'batch' not in context['intake_response_outline']['required_check_topics']
        current=main.get_task(t['id']);value=review(current)
        if duplicate:value['questions'].append(copy.deepcopy(value['questions'][0]))
        calls.append(1);return json.dumps({'message':'仍需核对规则，不搭建。','requirements_patch':{},'intake_review':value},ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',model)
    r=client.post('/api/tasks/'+t['id']+'/messages',json={'content':phrase});assert r.status_code==200,r.text
    after=r.json();assert calls==[1] and after['requirements']==t['requirements']
    assert not after['requirements_confirmed'] and not after['configuration_confirmed'] and not after.get('workflow_plan') and not after.get('artifact') and not after['runs']
    if duplicate:assert not after.get('intake_review') and '追问主题重复' in after['messages'][-1]['content'] and not after['interview_attempts'][-1]['applied']
    else:assert len(after['intake_review']['review']['checks'])==9 and after['intake_review']['review']['questions']
    ledger=client.get('/api/tasks/'+t['id']+'/budget').json();assert len(ledger['entries'])==1 and ledger['entries'][0]['status']=='settled'
