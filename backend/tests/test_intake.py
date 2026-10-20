from test_api import restore_payload
import copy,json
import httpx
import pytest
from test_api import client
from test_task_budget import provider
from app import main
from app.intake import topics,summary,validate_review,sources

REQ={'goal':'将单条文本转成大写，范围仅文本转换。','audience':'内部同事使用。','input':'单条必填文本 query；空白时提示重新输入。','output':'返回 result 字符串，不保存到外部。','rules':'去除首尾空白再转大写，不改内部空白。','knowledge':'无额外资料或服务，纯文本处理。','exceptions':'输入空白返回明确提示；调用失败提示重试，不伪造成功。','tests':'输入 abc 输出 ABC；输入空白显示输入错误。'}

@pytest.fixture(autouse=True)
def forbid_at01_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('AT-01 隔离检查不得访问真实 HTTP 或调用真实模型')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(main, 'call_model', forbidden)

def new(client,app_type='workflow',filled=True):
 t=client.post('/api/tasks',json={'name':'新准入任务','app_type':app_type}).json();assert t['intake_required']
 if filled:t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':REQ}).json()
 return t

def state(client,t):return client.get(f"/api/tasks/{t['id']}/intake").json()

def manual(client,t,**patch):
 current=state(client,t);answers={row['id']:t['requirements'].get(row['id'],'本项明确不适用：本次只做文本转换，不包含相关流程。') for row in current['standard']}
 return client.post(f"/api/tasks/{t['id']}/intake/manual",json={'revision':t['revision'],'context_token':current['context_token'],'answers':answers,'acknowledge_review':True,**patch})

def review(t,gap=None):
 rows=[{'topic':row['id'],'status':'needs_input' if row['id']==gap else 'complete','detail':'需补充明确规则' if row['id']==gap else '技术检查样例，不是实际业务验收。','evidence':[] if row['id']==gap else [{'kind':'requirement','id':row['id'] if row['id'] in REQ else 'rules','quote':t['requirements'].get(row['id'],t['requirements']['rules'])}]} for row in topics(t)]
 q=[] if not gap else [{'topic':gap,'question':'失败时选择停止还是重试？','recommendation':'建议失败停止，请确认。','reason':'避免未经确认的重复处理。','experience':'用户需要重新发起。','cost':'不会自动追加调用。','manual_work':'需人工检查失败原因。'}]
 return {'schema_version':1,'checks':rows,'questions':q}

def test_new_task_nonempty_fields_do_not_equal_ready(client):
 t=new(client);value=state(client,t);assert value['state']=='unreviewed' and not value['can_confirm']
 r=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':'requirements'});assert r.status_code==422 and '准入' in r.text

def test_blank_task_questions_prioritized_without_model_charge(client):
 t=new(client,filled=False);value=state(client,t);assert len(value['gaps'])==8 and len(value['questions'])==3
 assert [q['topic'] for q in value['questions']]==['goal','audience','input']
 assert not main.budgets.get(t['id'])['entries']

@pytest.mark.parametrize('app_type', ['workflow', 'advanced-chat', 'agent'])
def test_at01_vague_goal_questions_persist_without_early_build(client, monkeypatch, app_type):
    t = new(client, app_type, filled=False)
    t = client.patch(f"/api/tasks/{t['id']}", json={
        'requirements': {'goal': '想做一个提高工作效率的助手。'},
    }).json()
    provider(client)
    calls = []
    rounds = [('goal', 'input', 'output'), ('rules',)]

    async def controlled(*args, **kwargs):
        context = json.loads(args[2][1]['content'].split('当前任务资料：', 1)[1])
        assert context['user_selected_type'] == app_type
        assert context['requirements'] == t['requirements']
        assert {row['id'] for row in context['intake_standard']} >= set(REQ)
        asked = rounds[len(calls)]
        calls.append(context)
        checks = [{'topic': row['id'], 'status': 'needs_input',
                   'detail': '目标仍模糊，需用户补充，不能默认补齐。', 'evidence': []}
                  for row in context['intake_standard']]
        questions = [{'topic': key, 'question': next(row['question'] for row in topics(t) if row['id'] == key),
                      'recommendation': '请先补充具体说明。', 'reason': '避免猜测业务。',
                      'experience': '补充后继续规划。', 'cost': '未发生真实模型费用。',
                      'manual_work': '需用户回答。'} for key in asked]
        return json.dumps({'message': '请先回答这些问题，尚未搭建。', 'requirements_patch': {},
                           'intake_review': {'schema_version': 1, 'checks': checks, 'questions': questions}},
                          ensure_ascii=False), {'prompt_tokens': 10, 'completion_tokens': 10}

    monkeypatch.setattr(main, 'call_model', controlled)
    for asked in rounds:
        response = client.post(f"/api/tasks/{t['id']}/messages", json={'content': '请检查还需要明确什么。'})
        assert response.status_code == 200, response.text
        saved = client.get(f"/api/tasks/{t['id']}").json()
        current = state(client, saved)
        assert current['reviewed'] and not current['can_confirm']
        assert [q['topic'] for q in current['questions']] == list(asked)
        assert {'goal', 'input', 'output', 'rules'} <= {gap['topic'] for gap in current['gaps']}
        assert current['record']['source'] == 'model'
        assert not saved.get('interview_attempts')
        before = copy.deepcopy(saved)
        ledger = copy.deepcopy(main.budgets.get(t['id']))
        for kind in ('requirements', 'configuration'):
            rejected = client.post(f"/api/tasks/{t['id']}/confirm", json={'revision': saved['revision'], 'kind': kind})
            assert rejected.status_code == 422, rejected.text
        rejected = client.post(f"/api/tasks/{t['id']}/plan/generate", json={'revision': saved['revision']})
        assert rejected.status_code == 422 and '八项需求' in rejected.text
        assert client.post(f"/api/tasks/{t['id']}/build", json={'revision': saved['revision']}).status_code == 422
        assert client.get(f"/api/tasks/{t['id']}/artifact").status_code == 404
        assert client.get(f"/api/tasks/{t['id']}").json() == before
        assert main.budgets.get(t['id']) == ledger
        assert saved['app_type'] == app_type and saved['revision'] == t['revision']
        assert saved['requirements'] == t['requirements']
        assert not saved['requirements_confirmed'] and not saved['configuration_confirmed']
        assert not saved.get('workflow_plan') and not saved.get('agent_plan')
        assert not saved['artifact'] and not saved['runs'] and not saved.get('dify_app_id')
        assert not saved['planning_runs']
    assert len(calls) == 2 and len(main.budgets.get(t['id'])['entries']) == 2
    assert calls[1]['previous_intake']['questions'][0]['topic'] == 'goal'


@pytest.mark.parametrize('gap', ['goal', 'input', 'output', 'rules'])
def test_at01_nonempty_but_unresolved_topic_blocks_confirmation(client, monkeypatch, gap):
    t = new(client)
    provider(client)

    async def controlled(*args, **kwargs):
        value = review(main.get_task(t['id']), gap)
        value['questions'][0]['question'] = next(row['question'] for row in topics(t) if row['id'] == gap)
        return json.dumps({'message': '仍需补充具体说明。', 'requirements_patch': {},
                           'intake_review': value}), {'prompt_tokens': 10, 'completion_tokens': 10}

    monkeypatch.setattr(main, 'call_model', controlled)
    response = client.post(f"/api/tasks/{t['id']}/messages", json={'content': '请检查说明是否具体。'})
    assert response.status_code == 200, response.text
    saved = response.json()
    current = state(client, saved)
    assert current['reviewed'] and not current['can_confirm']
    assert [row['topic'] for row in current['gaps']] == [gap]
    assert current['questions'][0]['topic'] == gap
    assert saved['requirements'] == REQ and saved['revision'] == t['revision']
    rejected = client.post(f"/api/tasks/{t['id']}/confirm", json={'revision': saved['revision'], 'kind': 'requirements'})
    assert rejected.status_code == 422 and '需求准入未通过' in rejected.text
    assert not client.get(f"/api/tasks/{t['id']}").json()['requirements_confirmed']

@pytest.mark.parametrize('app_type,expected',[('workflow',set()),('advanced-chat',{'memory','dialogue'}),('agent',{'memory','dialogue','agent_tools'})])
def test_type_specific_standard(client,app_type,expected):
 t=new(client,app_type);assert {r['id'] for r in topics(t) if r['special']}==expected

def test_many_scenarios_include_special_failure_questions(client):
 t=new(client);t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':{'goal':'批量处理数组，RAG 检索，HTTP 接口，定时触发并人工审批。'}}).json()
 assert {r['id'] for r in topics(t) if r['special']}=={'batch','retrieval','external','trigger','human','schedule_time','schedule_delivery','schedule_operations'}
 assert '失败' in next(r['question'] for r in topics(t) if r['id']=='batch')

def test_manual_review_has_separate_user_confirmation_and_build(client):
 t=new(client);r=manual(client,t);assert r.status_code==200,r.text;t=r.json()
 assert not t['requirements_confirmed'] and state(client,t)['record']['source']=='user_declared'
 assert state(client,t)['can_confirm'] and t['revision']==3
 t=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':'requirements'}).json()
 t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'dify_model_provider':'test/provider','dify_model':'test-model'}}).json()
 assert state(client,t)['can_confirm']  # Configuration alone does not re-ask business questions.
 # New tasks must save an explicit graph; this case promises deterministic text conversion.
 plan={'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'text-input','required':True}]}},{'id':'convert','type':'code','config':{'code_language':'python3','code':"def main(query):\n    return {'result': query.strip().upper() if query.strip() else '输入错误'}",'variables':[{'variable':'query','value_selector':['start','query']}],'outputs':{'result':{'type':'string'}}}},{'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['convert','result']}]}}],'edges':[{'source':'start','target':'convert'},{'source':'convert','target':'end'}]}
 response=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan':plan});assert response.status_code==200,response.text;t=response.json()
 assert client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':'configuration'}).status_code==200
 assert client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']}).status_code==200
 assert '需求准入检查' in client.get(f"/api/tasks/{t['id']}/report").text

def test_manual_special_answers_persist_and_enter_planning_context(client,monkeypatch):
 t=new(client,'advanced-chat');t=manual(client,t).json();value=state(client,t)
 assert 'memory' in value['record']['answers'] and value['can_confirm']
 p=provider(client);t=client.patch(f"/api/tasks/{t['id']}",json={'configuration':{'assistant_provider_id':p['id']}}).json();seen=[]
 async def model(*a,**kw):seen.append(json.loads(a[2][1]['content']));return json.dumps({'error':'技术测试，未生成方案'}),{'prompt_tokens':10,'completion_tokens':10}
 monkeypatch.setattr(main,'call_model',model)
 client.post(f"/api/tasks/{t['id']}/plan/generate",json={'revision':t['revision']})
 assert seen[0]['intake_assessment']['record']['answers']['memory']==value['record']['answers']['memory']

def test_manual_explicit_ack_and_same_context_required(client):
 t=new(client);assert manual(client,t,acknowledge_review=False).status_code==422
 assert manual(client,t,context_token='wrong').status_code==409
 answers={**REQ,'rules':'待确认规则'};assert manual(client,t,answers=answers).status_code==422
 answers={**REQ,'goal':'批量处理文本'};assert manual(client,t,answers=answers).status_code==422
 assert main.get_task(t['id'])['requirements']==REQ

def test_unparsed_material_not_bypassed_by_manual_review(client):
 t=new(client);t['materials']=[{'id':'m','name':'图片','status':'needs_input','reference_mode':None}];main.save_task(t)
 assert manual(client,t).status_code==422

def test_changed_sources_stale_review_but_config_does_not(client):
 t=new(client);t=manual(client,t).json();assert state(client,t)['can_confirm']
 t=client.patch(f"/api/tasks/{t['id']}",json={'requirements':{'exceptions':'失败转人工处理，不自动重试。'}}).json()
 assert state(client,t)['stale'] and not state(client,t)['can_confirm']
 assert client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':'requirements'}).status_code==422

@pytest.mark.parametrize('gap',[None,'exceptions'])
def test_interview_updates_checklist_and_does_not_approve(client,monkeypatch,gap):
 t=new(client);provider(client)
 async def model(*a,**kw):
  request=json.loads(a[2][1]['content'].split('当前任务资料：',1)[-1]);assert request['intake_standard'] and request['intake_sources']
  return json.dumps({'message':'先核对异常行为' if gap else '说明已明确，请复核确认。','requirements_patch':{},'intake_review':review(main.get_task(t['id']),gap)}),{'prompt_tokens':100,'completion_tokens':200}
 monkeypatch.setattr(main,'call_model',model);r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'检查当前说明'});assert r.status_code==200,r.text
 t=r.json();value=state(client,t);assert value['reviewed'] and value['can_confirm']==(gap is None) and not t['requirements_confirmed'],(value,t['messages'][-1],t.get('interview_attempts'))
 assert len(main.budgets.get(t['id'])['entries'])==1
 if gap:assert value['questions'][0]['topic']==gap and value['questions'][0]['cost']

def test_missing_model_check_cannot_be_counted_as_completed(client,monkeypatch):
 t=new(client);provider(client)
 async def model(*a,**kw):return json.dumps({'message':'都完成了','requirements_patch':{}}),{'prompt_tokens':1,'completion_tokens':1}
 monkeypatch.setattr(main,'call_model',model);t=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'检查'}).json()
 assert not state(client,t)['can_confirm'] and '没有返回标准检查' in t['messages'][-1]['content']

@pytest.mark.parametrize('bad',['fabricated_quote','missing_topic','extra_question','malformed_status','no_evidence','duplicate_topic'])
def test_invalid_model_review_rejected_before_apply(client,monkeypatch,bad):
 t=new(client);provider(client)
 async def model(*a,**kw):
  value=review(main.get_task(t['id']))
  if bad=='fabricated_quote':value['checks'][0]['evidence'][0]['quote']='根本不存在的内容'
  if bad=='missing_topic':value['checks'].pop()
  if bad=='extra_question':value['questions']=[{'topic':'unknown'}]*4
  if bad=='malformed_status':value['checks'][0]['status']=[]
  if bad=='no_evidence':value['checks'][0]['evidence']=[]
  if bad=='duplicate_topic':value['checks'][1]=copy.deepcopy(value['checks'][0])
  return json.dumps({'message':'不应写入','requirements_patch':{'goal':'错误结果'},'intake_review':value}),{'prompt_tokens':1,'completion_tokens':1}
 monkeypatch.setattr(main,'call_model',model);r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'检查'});assert r.status_code==200,r.text
 assert r.json()['requirements']==REQ and r.json()['interview_attempts'] and not state(client,t)['can_confirm']

@pytest.mark.parametrize('bad,reason', [
    ('extra_topic', '需求检查主题数量不匹配'),
    ('invalid_material_id', '需求来源引文不存在'),
    ('complete_with_question', '已齐全时不能仍有待答问题'),
])
def test_interview_contract_failures_are_isolated(client, monkeypatch, bad, reason):
    t = new(client)
    provider(client)
    material = {'id': 'material-1', 'name': '文本规则.txt', 'status': 'parsed',
                'reference_mode': 'reference', 'text': REQ['rules']}
    t['materials'] = [material]
    main.save_task(t)
    valid = review(t)
    rules = next(row for row in valid['checks'] if row['topic'] == 'rules')
    rules['evidence'] = [{'kind': 'material', 'id': material['id'], 'quote': material['text']}]
    # Start from an accepted review; each parameter introduces exactly one defect.
    assert validate_review(t, valid) == valid
    value = copy.deepcopy(valid)
    if bad == 'extra_topic':
        extra = copy.deepcopy(value['checks'][0])
        extra['topic'] = 'agent_tools'  # This workflow does not trigger Agent topics.
        value['checks'].append(extra)
    elif bad == 'invalid_material_id':
        next(row for row in value['checks'] if row['topic'] == 'rules')['evidence'][0]['id'] = material['name']
    else:
        # Full, otherwise valid question fields prevent a schema error masking the defect.
        value['questions'] = review(t, 'exceptions')['questions']
        assert all(row['status'] == 'complete' for row in value['checks'])

    calls = []
    async def model(*args, **kwargs):
        calls.append(True)
        return json.dumps({'message': '检查全部完成', 'requirements_patch': {'goal': '错误结果'},
                           'intake_review': value}), {'prompt_tokens': 1, 'completion_tokens': 1}

    monkeypatch.setattr(main, 'call_model', model)
    response = client.post(f"/api/tasks/{t['id']}/messages", json={'content': '检查当前说明'})
    assert response.status_code == 200, response.text
    saved = client.get(f"/api/tasks/{t['id']}").json()
    assert calls == [True]  # No automatic retry or external model call.
    assert saved['requirements'] == REQ
    assert saved['revision'] == t['revision']
    assert len(saved['interview_attempts']) == 1
    attempt = saved['interview_attempts'][0]
    assert attempt['applied'] is False and reason in attempt['reason']
    assert json.loads(attempt['response_excerpt'])['intake_review'] == value
    assert saved['messages'][-1]['source'] == 'system'
    assert reason in saved['messages'][-1]['content']
    current = state(client, saved)
    assert not current['reviewed'] and not current['can_confirm'] and not current['record']
    assert not saved['requirements_confirmed']
    assert client.post(f"/api/tasks/{t['id']}/confirm", json={
        'revision': saved['revision'], 'kind': 'requirements',
    }).status_code == 422


def test_restore_never_disables_new_task_gate(client):
 t=new(client);before=t['versions'][0];t=manual(client,t).json();t=client.post(f"/api/tasks/{t['id']}/restore",json=restore_payload(client, t['id'], before['id'])).json()
 assert t['intake_required'] and not state(client,t)['can_confirm']

def test_legacy_tasks_keep_original_manual_lane(client):
 t=new(client);t.pop('intake_required');main.save_task(t)
 assert state(client,t)['can_confirm'] and not state(client,t)['reviewed']
 assert client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':'requirements'}).status_code==200

def test_model_cannot_use_its_own_patch_as_user_evidence(client,monkeypatch):
 t=new(client);provider(client)
 async def model(*a,**kw):
  proposed=copy.deepcopy(main.get_task(t['id']));proposed['requirements']['goal']='模型自行发明的目标'
  return json.dumps({'message':'完成','requirements_patch':{'goal':proposed['requirements']['goal']},'intake_review':review(proposed)}),{'prompt_tokens':1,'completion_tokens':1}
 monkeypatch.setattr(main,'call_model',model);r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'只检查，不改变范围'});assert r.status_code==200
 assert r.json()['requirements']==REQ and r.json()['interview_attempts']

def test_manual_decisions_remain_available_after_model_review(client):
 t=new(client,'advanced-chat');t=manual(client,t).json();current=sources(t);key=next(key for key in current if key[0]=='decision' and key[1].endswith(':memory'));text=current[key]
 main.intake.save(t,review(t),'model');main.save_task(t)
 assert sources(t)[key]==text
