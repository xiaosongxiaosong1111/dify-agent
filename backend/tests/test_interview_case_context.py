import copy,json
import pytest
from test_api import client
from test_intake import new,review
from test_task_budget import provider,forbid_budget_external_calls
from app import main
from app.intake import validate_review,digest,ReviewContractError

def example():
    return {'id':'saved-public','name':'公开转换样例','input':{'query':'abc'},'expectation':{'mode':'equals','target':'result','expected':'ABC'},'required':True}

def seed(client,kind='workflow'):
    provider(client);t=new(client,kind)
    r=client.post(f"/api/tasks/{t['id']}/test-cases",json={'revision':t['revision'],'cases':[example()]})
    assert r.status_code==200,r.text
    return r.json()

@pytest.mark.parametrize('kind',['workflow','advanced-chat','agent'])
@pytest.mark.parametrize('stream',[False,True])
def test_review_receives_saved_examples_with_source_and_unverified_flags(client,monkeypatch,kind,stream):
    t=seed(client,kind);seen=[]
    async def fake(p,k,m,**kw):
        ctx=json.loads(m[1]['content'].split('当前任务资料：',1)[1]);seen.append(ctx)
        c=ctx['acceptance_cases'];assert c['items']==t['test_cases'] and c['revision']==t['revision']
        assert c['case_count']==c['turn_count']==1 and c['truncated'] is False
        assert c['execution_verified'] is False and c['resource_permission_granted'] is False
        assert '不是事实来源' in m[0]['content']
        checks=review(t);row=next(r for r in checks['checks'] if r['topic']=='tests')
        row['evidence']=[{'kind':'test_case','id':'saved-public','quote':'ABC'}]
        return json.dumps({'message':'逐项核对已保存案例，不声明已运行。','requirements_patch':{},'intake_review':checks},ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',fake)
    r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'请按我保存的样例检查需求。','mode':'review','stream_response':stream})
    assert r.status_code==200,r.text
    saved=r.json();assert len(seen)==1 and saved['intake_review']['source']=='model'
    assert next(r for r in saved['intake_review']['review']['checks'] if r['topic']=='tests')['evidence'][0]['kind']=='test_case'
    ops=client.get(f"/api/tasks/{t['id']}/interviews").json()['operations'];c=ops[-1]['acceptance_cases']
    assert c['content_sha256']==seen[0]['acceptance_cases']['content_sha256'] and 'items' not in c
    assert saved['test_cases']==t['test_cases'] and not saved['requirements_confirmed']

@pytest.mark.parametrize('change',['malformed','too_many','oversize','credential','surrogate'])
def test_bad_saved_cases_stop_before_key_message_checkpoint_or_budget(client,monkeypatch,change):
    t=seed(client);case=example()
    if change=='malformed':cases=[None]
    elif change=='too_many':cases=[{**case,'id':str(i)} for i in range(31)]
    elif change=='oversize':case['input']['query']='公开'*13000;cases=[case]
    elif change=='credential':case['input']['query']='api_key=sk-'+('a'*48);cases=[case]
    else:case['input']['query']='\ud800';cases=[case]
    t['test_cases']=cases
    with main.store.connect() as db:db.execute('UPDATE objects SET value=? WHERE kind=? AND id=?',(json.dumps(t,ensure_ascii=True),'task',t['id']))
    before=copy.deepcopy(main.get_task(t['id']));reads=[]
    def forbidden(*a,**kw):reads.append(True);raise AssertionError('No credential read or paid call')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
    r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'请核对保存样例。','mode':'review','stream_response':True})
    assert r.status_code==422,r.text
    assert '访谈' in r.text and 'sk-' not in r.text and not reads
    assert main.get_task(t['id'])==before and not main.store.list('interview_operation')
    assert not main.budgets.get(t['id'])['entries']

def test_case_quote_requires_current_saved_id_and_exact_text(client):
    t=seed(client);v=review(t);row=next(r for r in v['checks'] if r['topic']=='tests');row['evidence']=[{'kind':'test_case','id':example()['id'],'quote':'ABC'}]
    assert validate_review(t,v)==v
    for field,value in [('id','other'),('quote','invented')]:
        bad=copy.deepcopy(v);bad['checks'][-1]['evidence'][0][field]=value
        with pytest.raises(ReviewContractError):validate_review(t,bad)
    changed=copy.deepcopy(t);changed['test_cases'][0]['expectation']['expected']='CHANGED'
    with pytest.raises(ReviewContractError):validate_review(changed,v)

def test_case_source_changes_invalidate_case_based_review_not_legacy_unused_metadata(client):
    t=seed(client);v=review(t);v['checks'][-1]['evidence']=[{'kind':'test_case','id':example()['id'],'quote':'ABC'}]
    main.intake.save(t,v,'model');before=digest(t)
    changed=copy.deepcopy(t);changed['test_cases'][0]['expectation']['expected']='CHANGED';assert digest(changed)!=before
    metadata=copy.deepcopy(t);metadata['test_cases'][0]['last_run']='not a new requirement';assert digest(metadata)==before
    legacy=copy.deepcopy(t);legacy['intake_review']['review']=review(t);before=digest(legacy)
    legacy['test_cases'][0]['last_run']='not part of requirement source';assert digest(legacy)==before

def test_case_context_keeps_followups_and_excludes_runtime_metadata(client,monkeypatch):
    t=seed(client,'advanced-chat');c=t['test_cases'][0];c['followups']=[{'input':{'query':'def'},'expectation':{'mode':'equals','target':'result','expected':'DEF'}}];c['last_run']={'actual_answer':'OLD_FACT_DO_NOT_SEND'};main.store.put('task',t['id'],t);seen=[]
    async def fake(p,k,m,**kw):
        ctx=json.loads(m[1]['content'].split('当前任务资料：',1)[1]);value=ctx['acceptance_cases'];seen.append(value)
        assert value['turn_count']==2 and value['items'][0]['followups']==c['followups']
        assert 'OLD_FACT_DO_NOT_SEND' not in json.dumps(ctx) and 'last_run' not in value['items'][0]
        assert value['ignored_metadata_fields']==1
        return json.dumps({'message':'仅设计核对。','requirements_patch':{},'intake_review':review(t)},ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',fake)
    assert client.post(f"/api/tasks/{t['id']}/messages",json={'content':'核对当前接续。'}).status_code==200
    assert len(seen)==1

def test_empty_cases_do_not_create_or_confirm_cases(client,monkeypatch):
    provider(client);t=new(client);seen=[]
    async def fake(p,k,m,**kw):
        value=json.loads(m[1]['content'].split('当前任务资料：',1)[1])['acceptance_cases'];seen.append(value)
        assert value['items']==[] and value['case_count']==0
        return json.dumps({'message':'尚未保存逐例案例。','requirements_patch':{},'intake_review':review(t)},ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
    monkeypatch.setattr(main,'call_model',fake)
    r=client.post(f"/api/tasks/{t['id']}/messages",json={'content':'检查草案。'});assert r.status_code==200 and len(seen)==1
    assert not r.json().get('test_cases') and not r.json()['requirements_confirmed']

def test_case_evidence_keeps_multiline_original_field_text(client):
    t=seed(client);t['test_cases'][0]['input']['query']='first\nsecond';v=review(t)
    v['checks'][-1]['evidence']=[{'kind':'test_case','id':example()['id'],'quote':'first\nsecond'}]
    assert validate_review(t,v)==v
