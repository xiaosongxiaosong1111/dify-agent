import copy,json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import pytest
from test_api import client,forbid_api_external_calls
from test_intake import new,review
from test_intake_runtime_scope import annotated
from app import main


def ready(client,app_type='workflow'):
    t=new(client,app_type);t['requirements']['knowledge']='只使用既有知识库检索公开资料。'
    t['messages'].append({'role':'user','content':'只处理当前已保存需求；引用政策编号，待补充的资料口径需继续明确。','created_at':main.now()})
    proposed=annotated(t);value=review(proposed,gap='retrieval')
    for row in value['checks']:
        for evidence in row['evidence']:
            evidence['quote']=t['requirements'][evidence['id']]
    payload={'message':'这是待复核需求草案，不是业务验收通过。','requirements_patch':proposed['requirements'],'intake_review':value}
    attempt={'revision':t['revision'],'applied':False,'response_excerpt':json.dumps(payload,ensure_ascii=False),'response_truncated':False,'reason':'模型需求检查未通过：旧规则误判；候选未应用。','created_at':main.now(),'usage':{'prompt_tokens':1,'completion_tokens':1}}
    t['interview_attempts']=[attempt];main.save_task(t);return main.get_task(t['id'])

def url(t,index=0):return '/api/tasks/'+t['id']+'/saved-intake-candidates/'+str(index)
def preview(client,t,index=0,**extra):return client.post(url(t,index)+'/preview',json={'revision':t['revision'],**extra})
def adopt(client,t,p,**extra):return client.post(url(t)+'/adopt',json={'revision':t['revision'],'review_token':p['review_token'],'acknowledge_unconfirmed':True,**extra})

def test_listing_preview_are_readonly_no_decryption_or_network(client,monkeypatch):
    t=ready(client);before=copy.deepcopy(t);budget=main.store.get('task_budget',t['id'])
    def forbid(*a,**kw):pytest.fail('Preview must not write or decrypt')
    monkeypatch.setattr(main.store,'put',forbid);monkeypatch.setattr(main.store,'secret',forbid)
    listing=client.post('/api/tasks/'+t['id']+'/saved-intake-candidates/list',json={'revision':t['revision']});assert listing.status_code==200
    assert listing.json()['candidates']==[{'index':0,'complete':True,'same_revision':True}]
    r=preview(client,t);assert r.status_code==200,r.text
    value=r.json();assert value['needs_input_topics']==['retrieval'] and len(value['review']['checks'])==9
    assert all(value[k] is False for k in ['network_requested','model_called','task_changed','requirements_confirmed','business_verified'])
    assert 'response_excerpt' not in value and r.headers['Cache-Control']=='no-store'
    assert main.get_task(t['id'])==before and main.store.get('task_budget',t['id'])==budget


@pytest.mark.parametrize('app_type',['workflow','advanced-chat','agent'])
def test_explicit_adoption_new_unconfirmed_revision_keeps_failure_and_budget(client,monkeypatch,app_type):
    t=ready(client,app_type);p=preview(client,t).json();budget=copy.deepcopy(main.store.get('task_budget',t['id']));versions=len(t['versions'])
    def forbid(*a,**kw):pytest.fail('Recovery must not decrypt')
    monkeypatch.setattr(main.store,'secret',forbid)
    r=adopt(client,t,p);assert r.status_code==200,r.text
    after=r.json();assert after['revision']==t['revision']+1 and len(after['versions'])==versions+1 and after['app_type']==app_type
    assert not after['requirements_confirmed'] and not after['configuration_confirmed'] and not after['artifact'] and not after['dify_app_id'] and not after['runs']
    assert after['interview_attempts']==t['interview_attempts'] and after['messages'][:len(t['messages'])]==t['messages']
    assert after['requirements']==p['requirements'] and after['intake_review']['source']=='saved_model_candidate'
    state=client.get('/api/tasks/'+t['id']+'/intake').json();assert state['can_confirm'] is False and state['questions'] and state['reviewed']
    assert main.store.get('task_budget',t['id'])==budget
    assert adopt(client,t,p).status_code==409 and main.get_task(t['id'])['revision']==after['revision']


@pytest.mark.parametrize('change',['candidate','user','configuration'])
def test_same_revision_source_change_rejects_stale_preview_before_write(client,change):
    t=ready(client);p=preview(client,t).json()
    if change=='candidate':
        value=json.loads(t['interview_attempts'][0]['response_excerpt']);value['message']='同一候选改了说明。';t['interview_attempts'][0]['response_excerpt']=json.dumps(value,ensure_ascii=False)
    elif change=='user':t['messages'][0]['content']='来源内容变更。'
    else:t['configuration']['max_tokens']=1024
    main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));assert adopt(client,t,p).status_code==409
    assert main.get_task(t['id'])==before


@pytest.mark.parametrize('change',['truncated','already_applied','old_revision','discussion','new_user','missing_time','paused','material','formal_plan','artifact','app','runs','interrupted'])
def test_ambiguous_or_incompatible_source_refused_without_mutation(client,change):
    t=ready(client);a=t['interview_attempts'][0]
    if change=='truncated':a['response_truncated']=True
    elif change=='already_applied':a['applied']=True
    elif change=='old_revision':a['revision']-=1
    elif change=='discussion':t['messages'][-1]['purpose']='discussion'
    elif change=='new_user':t['messages'].append({'role':'user','content':'还有新的业务要求。','created_at':(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()})
    elif change=='missing_time':t['messages'][-1].pop('created_at')
    elif change=='paused':t['status']='paused'
    elif change=='material':t['materials']=[{'id':'document'}]
    elif change=='formal_plan':t['workflow_plan']={'nodes':[{'id':'start'}]}
    elif change=='artifact':t['artifact']={'revision':t['revision']}
    elif change=='app':t['dify_app_id']='existing-app'
    elif change=='runs':t['runs']=[{'id':'existing','kind':'run','status':'success'}]
    else:a['reason']='访谈暂停，迟到回复未应用。'
    main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));assert preview(client,t).status_code in {404,409,422}
    assert main.get_task(t['id'])==before


@pytest.mark.parametrize('change',['bad_quote','still_missing_topic','bad_json','duplicate','secret','extra_field'])
def test_current_contract_and_secret_checks_are_not_relaxed(client,change):
    t=ready(client);a=t['interview_attempts'][0];v=json.loads(a['response_excerpt'])
    if change=='bad_quote':v['intake_review']['checks'][0]['evidence'][0]['quote']='不存在的引文'
    elif change=='still_missing_topic':v['intake_review']['checks'].pop()
    elif change=='bad_json':a['response_excerpt']='{unfinished'
    elif change=='duplicate':a['response_excerpt']=a['response_excerpt'][:-1]+',"message":"ambiguous"}'
    elif change=='secret':v['message']='Bearer '+'x'*28
    else:v['execute_now']=True
    if change not in {'bad_json','duplicate'}:a['response_excerpt']=json.dumps(v,ensure_ascii=False)
    main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));r=preview(client,t);assert r.status_code==422 and 'xxxxxxxx' not in r.text
    assert main.get_task(t['id'])==before


def test_acknowledgement_and_strict_request_required(client):
    t=ready(client);p=preview(client,t).json();before=copy.deepcopy(main.get_task(t['id']))
    assert adopt(client,t,p,acknowledge_unconfirmed=False).status_code==422
    assert preview(client,t,revision=True).status_code==422
    raw=json.dumps({'revision':t['revision']})[:-1]+',"revision":1}'
    assert client.post(url(t)+'/preview',content=raw).status_code==422
    assert preview(client,t,extra='invalid').status_code==422 and preview(client,t,index=-1).status_code==404
    assert main.get_task(t['id'])==before

def test_concurrent_adoption_only_creates_one_new_revision(client):
    t=ready(client);p=preview(client,t).json();budget=copy.deepcopy(main.store.get('task_budget',t['id']))
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:adopt(client,t,p).status_code,range(2)))
    assert sorted(results)==[200,409] and main.get_task(t['id'])['revision']==t['revision']+1
    assert main.store.get('task_budget',t['id'])==budget

def test_old_confirmation_and_review_do_not_survive_as_confirmation(client):
    t=ready(client);main.intake.save(t,review(t),'user_declared');t['requirements_confirmed']=True;t['configuration_confirmed']=True;main.save_task(t)
    prior=copy.deepcopy(t['intake_review']);p=preview(client,t).json();after=adopt(client,t,p).json()
    assert not after['requirements_confirmed'] and not after['configuration_confirmed']
    assert after['intake_history'][-1]==prior and after['interview_attempts']==t['interview_attempts']
