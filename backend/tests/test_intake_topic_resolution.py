import copy,json
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_api import client,forbid_api_external_calls
from test_saved_intake import ready,preview as saved_preview,adopt
from app import main
from app.intake import digest,model_sources

def prepared(client):
    t=ready(client);t=adopt(client,t,saved_preview(client,t).json()).json()
    return main.get_task(t['id'])

def body(t,**extra):return {'revision':t['revision'],'topic':'retrieval','answer':'只要求政策编号，保持原已声明资料口径。','evidence':[{'message_id':str(len(t['messages'])-2),'quote':'引用政策编号'}],**extra}
def post(client,t,op,value):return client.post('/api/tasks/'+t['id']+'/intake/topic-resolution/'+op,json=value)
def read(client,t):return post(client,t,'options',{'revision':t['revision']})
def preview(client,t,**extra):return post(client,t,'preview',body(t,**extra))
def save(client,t,p,**extra):return post(client,t,'save',{**body(t),'review_token':p['review_token'],'acknowledge_source_review':True,**extra})

def test_options_and_preview_readonly_no_secret_and_no_model(client,monkeypatch):
    t=prepared(client);before=copy.deepcopy(t);budget=main.store.get('task_budget',t['id'])
    def forbid(*a,**kw):pytest.fail('Source-based preview must not write/decrypt')
    monkeypatch.setattr(main.store,'put',forbid);monkeypatch.setattr(main.store,'secret',forbid)
    options=read(client,t);assert options.status_code==200 and options.headers['Cache-Control']=='no-store'
    assert [r['id'] for r in options.json()['topics']]==['retrieval'] and options.json()['sources']
    r=preview(client,t);assert r.status_code==200,r.text
    p=r.json();assert p['remaining_topics']==[] and p['operation']['actor']=='local_operator'
    assert all(p[k] is False for k in ['requirements_changed','requirements_confirmed','configuration_confirmed','network_requested','model_called','task_changed','business_verified'])
    for old,new in zip(before['intake_review']['review']['checks'],p['review']['checks']):
        if old['topic']!='retrieval':assert old==new
    assert main.get_task(t['id'])==before and main.store.get('task_budget',t['id'])==budget

def test_single_topic_save_retains_base_other_checks_failure_budget_and_confirmation(client,monkeypatch):
    t=prepared(client);before=copy.deepcopy(t);budget=main.store.get('task_budget',t['id']);p=preview(client,t).json()
    def forbid(*a,**kw):pytest.fail('Topic answer must not decrypt')
    monkeypatch.setattr(main.store,'secret',forbid)
    r=save(client,t,p);assert r.status_code==200,r.text
    after=r.json();assert after['revision']==t['revision']+1 and after['requirements']==before['requirements'] and after['configuration']==before['configuration']
    assert after['interview_attempts']==before['interview_attempts'] and after['intake_history'][-1]==before['intake_review']
    assert not after['requirements_confirmed'] and not after['configuration_confirmed'] and not after['artifact'] and not after['dify_app_id'] and not after['runs']
    assert after['intake_review']['source']=='source_backed_resolution' and after['intake_review']['resolution_actor']=='local_operator'
    assert main.store.get('task_budget',t['id'])==budget
    state=client.get('/api/tasks/'+t['id']+'/intake').json();assert state['can_confirm'] and not state['stale'] and not state['questions']
    assert after['intake_review']['context_digest']==digest(after)
    assert any(x['kind']=='decision' and '非模型验证或人类签收' in x['text'] for x in model_sources(after))
    assert save(client,t,p).status_code==409

def test_agent_source_is_explicit_and_requires_note(client):
    t=prepared(client);assert preview(client,t,actor='agent_delegated').status_code==422
    fields={'actor':'agent_delegated','actor_note':'依常规委托，按已给原话复核；没有新的人类答复。'}
    p=preview(client,t,**fields).json();r=save(client,t,p,**fields);assert r.status_code==200,r.text
    record=r.json()['intake_review'];assert record['resolution_actor']=='agent_delegated' and record['topic_resolutions'][-1]['actor_note']==fields['actor_note']
    assert record['source']!='user_declared'

@pytest.mark.parametrize('change',['source','answer','actor','review'])
def test_changed_source_or_payload_rejects_old_preview(client,change):
    t=prepared(client);p=preview(client,t).json();extra={}
    if change=='source':t['messages'][-2]['content']+=' 另有约束。';main.save_task(t)
    elif change=='review':t['intake_review']['review']['checks'][0]['detail']='同修订检查更新。';main.save_task(t)
    elif change=='answer':extra['answer']='另一份待确认说明。'
    else:extra.update(actor='agent_delegated',actor_note='新的代理复核来源。')
    before=copy.deepcopy(main.get_task(t['id']));assert save(client,t,p,**extra).status_code==409
    assert main.get_task(t['id'])==before

@pytest.mark.parametrize('bad',[
    {'topic':'input'},{'topic':'external'},
    {'evidence':[{'message_id':'999','quote':'引用政策编号'}]},
    {'evidence':[{'message_id':'0','quote':'模型推测的不存在文字'}]},
    {'evidence':[{'message_id':'-1','quote':'引用政策编号'}]},
    {'answer':'Bearer '+'x'*30},{'actor':'human_signoff'},
    {'answer':'调用新的外部订单 API。'},
    {'evidence':[]},
])
def test_no_unknown_topic_forged_source_secret_or_human_signoff(client,bad):
    t=prepared(client);before=copy.deepcopy(t);r=preview(client,t,**bad);assert r.status_code in {409,422},r.text
    assert 'xxxxxxxx' not in r.text and main.get_task(t['id'])==before

def test_discussion_and_secret_sources_are_not_offered_or_usable(client):
    t=prepared(client);message=t['messages'][-2];message['purpose']='discussion';main.save_task(t)
    # Current review becomes stale when a formerly used user source is changed.
    assert read(client,t).status_code==409
    t['messages'][-2].pop('purpose');t['messages'].append({'role':'user','purpose':'discussion','content':'Bearer '+'x'*30,'created_at':main.now()});main.save_task(t)
    options=read(client,t).json();assert all('xxxxxxxx' not in r['text'] for r in options['sources'])
    assert preview(client,t,evidence=[{'message_id':str(len(t['messages'])-1),'quote':'Bearer '+'x'*30}]).status_code==422

def test_duplicate_references_and_missing_ack_refused(client):
    t=prepared(client);refs=body(t)['evidence'];assert preview(client,t,evidence=refs+refs).status_code==422
    p=preview(client,t).json();assert save(client,t,p,acknowledge_source_review=False).status_code==422
    raw=json.dumps(body(t))[:-1]+',"topic":"external"}'
    assert client.post('/api/tasks/'+t['id']+'/intake/topic-resolution/preview',content=raw).status_code==422

def test_other_pending_topic_is_preserved_with_a_question(client):
    t=prepared(client);t['requirements']['rules']+=' 需要批量处理。'
    from test_intake import review
    value=review(t,gap='retrieval');next(r for r in value['checks'] if r['topic']=='batch').update(status='needs_input',evidence=[])
    main.intake.save(t,value,'model');main.save_task(t)
    p=preview(client,t).json();assert p['remaining_topics']==['batch'] and p['review']['questions'][0]['topic']=='batch'
    after=save(client,t,p).json();state=client.get('/api/tasks/'+t['id']+'/intake').json();assert not state['can_confirm'] and state['questions'] and after['requirements']==t['requirements']

def test_concurrent_save_only_one_new_revision(client):
    t=prepared(client);p=preview(client,t).json();budget=main.store.get('task_budget',t['id'])
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda _:save(client,t,p).status_code,range(2)))
    assert sorted(codes)==[200,409] and main.get_task(t['id'])['revision']==t['revision']+1
    assert main.store.get('task_budget',t['id'])==budget

def test_followup_manual_review_after_source_answer_is_not_immediately_stale(client):
    t=prepared(client);after=save(client,t,preview(client,t).json()).json()
    state=client.get('/api/tasks/'+t['id']+'/intake').json()
    answers={r['id']:after['requirements'].get(r['id'],after['intake_review']['answers'].get(r['id'],'')) for r in state['standard']}
    response=client.post('/api/tasks/'+t['id']+'/intake/manual',json={'revision':after['revision'],'context_token':state['context_token'],'answers':answers,'acknowledge_review':True})
    assert response.status_code==200,response.text
    latest=client.get('/api/tasks/'+t['id']+'/intake').json();assert latest['reviewed'] and not latest['stale'] and latest['can_confirm']

def test_followup_model_review_keeps_archived_answer_context_without_duplicate_digest(client):
    t=prepared(client);after=save(client,t,preview(client,t).json()).json()
    from test_intake import review
    main.intake.save(after,review(after),'model');main.save_task(after)
    state=client.get('/api/tasks/'+t['id']+'/intake').json();assert state['reviewed'] and not state['stale'] and state['can_confirm']
