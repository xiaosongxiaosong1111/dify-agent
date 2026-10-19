import copy,json
import pytest
from test_api import client
from test_image_preview import setup,prepare
from app import main

RESULT={'transcription':'开发图中文字','diagram_description':'开始到结束，未证明实际Dify连接。','coverage_note':'仅本张图，细字需人工核对。','uncertainties':['右侧小字无法确定']}


def route(t,m,action):return f"/api/tasks/{t['id']}/materials/{m['id']}/image-interpretation/{action}"
def ack(t,r,**patch):return {'revision':t['revision'],'plan_id':r['id'],'preview_token':r['preview_token'],'acknowledge_outbound':True,'acknowledge_estimated_fee':True,'acknowledge_unverified_vision':True,'acknowledge_image_token_pricing':True,**patch}


@pytest.mark.parametrize('field',['acknowledge_outbound','acknowledge_estimated_fee','acknowledge_unverified_vision','acknowledge_image_token_pricing'])
def test_each_specific_ack_required_before_call_or_preview_consumption(client,monkeypatch,field):
    t,m,p=setup(client);r=prepare(client,t,m,p).json()['record'];before=main.get_task(t['id'])
    async def forbidden(*a,**kw):raise AssertionError('没有全部确认不能派发')
    monkeypatch.setattr(main,'call_model',forbidden)
    response=client.post(route(t,m,'execute'),json=ack(t,r,**{field:False}))
    assert response.status_code==422 and main.get_task(t['id'])==before
    assert main.store.get('image_preview',r['id'])['status']=='ready' and not main.budgets.get(t['id'])['entries']


def test_exactly_one_image_call_retains_candidate_until_explicit_reviewed_adoption(client,monkeypatch):
    t,m,p=setup(client);r=prepare(client,t,m,p).json()['record'];before=main.get_task(t['id']);calls=[]
    async def controlled(provider,key,messages,**kwargs):
        calls.append((messages,kwargs));assert key=='test-only-image-key'
        assert main.get_task(t['id'])['active_image_operation_id']==r['id']
        assert messages[1]['content'][0]['type']=='image_url'
        assert kwargs['allow_images'] is True and 'image_reserve_usd' not in kwargs
        assert '其他材料' not in json.dumps(messages)
        return json.dumps(RESULT),{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(route(t,m,'execute'),json=ack(t,r));assert response.status_code==200,response.text
    candidate=response.json()['record'];assert candidate['status']=='candidate_ready' and candidate['candidate']==RESULT
    current=main.get_task(t['id']);assert current['revision']==before['revision'] and current['materials']==before['materials']
    assert not current.get('active_image_operation_id') and current['status']==before['status']
    assert client.post(route(t,m,'execute'),json=ack(t,r)).status_code==409 and len(calls)==1
    adopted=client.post(route(t,m,'adopt'),json={'revision':t['revision'],'plan_id':r['id'],'candidate_token':candidate['candidate_token'],'text':'人工核对后的文字，关系仍需验证','coverage_note':'仅本图，保留右侧小字不确定项','acknowledge_review':True,'acknowledge_uncertainties':True})
    assert adopted.status_code==200,adopted.text
    saved=adopted.json();material=saved['materials'][0]
    assert saved['revision']==t['revision']+1 and not saved['requirements_confirmed'] and not saved['configuration_confirmed']
    assert material['source_kind']=='reviewed_model_image_text' and material['source_file_parsed'] is False
    assert material['image_uncertainties']==RESULT['uncertainties'] and material['reference_mode'] is None
    assert material['original_parse_error']==m['error'] and not saved['runs'] and not saved['artifact']


@pytest.mark.parametrize('mode',['bad_json','duplicate_key','secret','unknown_usage'])
def test_bad_or_unknown_result_pauses_without_model_retry_or_source_mutation(client,monkeypatch,mode):
    t,m,p=setup(client);r=prepare(client,t,m,p).json()['record'];before=main.get_task(t['id']);calls=[]
    async def controlled(*args,**kwargs):
        calls.append(1)
        if mode=='bad_json':return '{broken',{'prompt_tokens':100,'completion_tokens':20}
        if mode=='duplicate_key':return '{"transcription":"first","transcription":"last","diagram_description":"","coverage_note":"不确定","uncertainties":[]}',{'prompt_tokens':100,'completion_tokens':20}
        if mode=='secret':return json.dumps({**RESULT,'transcription':'test-only-image-key'}),{'prompt_tokens':100,'completion_tokens':20}
        return json.dumps(RESULT),{}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(route(t,m,'execute'),json=ack(t,r));assert response.status_code==(200 if mode=='unknown_usage' else 422),response.text
    current=main.get_task(t['id']);assert current['status']=='paused' and current['revision']==t['revision'] and current['materials']==before['materials']
    assert len(calls)==1 and not current.get('active_image_operation_id')
    record=main.store.get('image_preview',r['id']);assert 'test-only-image-key' not in str(record)
    assert record['status']==('paused_candidate' if mode=='unknown_usage' else 'failed')
    assert client.post(route(t,m,'execute'),json=ack(t,r)).status_code==409 and len(calls)==1


def test_user_pause_keeps_late_candidate_unapplied_and_recovery_does_not_replay(client,monkeypatch):
    t,m,p=setup(client);r=prepare(client,t,m,p).json()['record'];before=main.get_task(t['id'])
    async def controlled(*a,**kw):
        current=main.get_task(t['id']);current['status']='paused';main.save_task(current)
        return json.dumps(RESULT),{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    response=client.post(route(t,m,'execute'),json=ack(t,r));assert response.status_code==200
    assert response.json()['record']['status']=='paused_candidate' and main.get_task(t['id'])['materials']==before['materials']
    record=main.store.get('image_preview',r['id']);record.update(status='dispatched');main.store.put('image_preview',r['id'],record)
    current=main.get_task(t['id']);current['active_image_operation_id']=r['id'];current['status']='planning';main.save_task(current)
    main.image_executions.recover();assert main.store.get('image_preview',r['id'])['status']=='interrupted'
    assert main.get_task(t['id'])['status']=='paused' and not main.get_task(t['id']).get('active_image_operation_id')


@pytest.mark.parametrize('change',['revision','file','candidate_token','material_status','foreign_record'])
def test_reviewed_candidate_cannot_adopt_after_binding_changes(client,monkeypatch,change):
    t,m,p=setup(client);r=prepare(client,t,m,p).json()['record']
    async def controlled(*a,**kw):return json.dumps(RESULT),{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    result=client.post(route(t,m,'execute'),json=ack(t,r)).json()['record']
    payload={'revision':t['revision'],'plan_id':r['id'],'candidate_token':result['candidate_token'],'text':'人工核对','coverage_note':'仅本图','acknowledge_review':True,'acknowledge_uncertainties':True}
    if change=='revision':
        current=main.get_task(t['id']);main.invalidate(current,'受控修订变化');main.save_task(current)
    elif change=='file':
        from pathlib import Path
        (main.DATA_ROOT/t['id']/'materials'/(m['id']+'.png')).write_bytes(b'changed source')
    elif change=='candidate_token':payload['candidate_token']='wrong-token'
    elif change=='material_status':
        current=main.get_task(t['id']);current['materials'][0]['status']='parsed';main.save_task(current)
    else:
        record=main.store.get('image_preview',r['id']);record['task_id']='other-task';main.store.put('image_preview',r['id'],record)
    before=main.get_task(t['id']);record_before=main.store.get('image_preview',r['id'])
    response=client.post(route(t,m,'adopt'),json=payload)
    assert response.status_code in (404,409),response.text
    assert main.get_task(t['id'])==before and main.store.get('image_preview',r['id'])==record_before


@pytest.mark.parametrize('change',['expired','boolean_string','wrong_token'])
def test_image_dispatch_preflight_does_not_consume_preview_or_call(client,monkeypatch,change):
    t,m,p=setup(client);r=prepare(client,t,m,p).json()['record'];payload=ack(t,r)
    if change=='expired':
        record=main.store.get('image_preview',r['id']);record['expires_at_epoch']=0;main.store.put('image_preview',r['id'],record)
    elif change=='boolean_string':payload['acknowledge_outbound']='true'
    else:payload['preview_token']='wrong-token'
    async def forbidden(*a,**kw):raise AssertionError('前置核对失败不能调用模型')
    monkeypatch.setattr(main,'call_model',forbidden);before=main.get_task(t['id'])
    response=client.post(route(t,m,'execute'),json=payload)
    assert response.status_code in (409,422) and main.get_task(t['id'])==before
    assert main.store.get('image_preview',r['id'])['status']=='ready' and not main.budgets.get(t['id'])['entries']



def test_prior_candidate_remains_readable_after_new_preview_without_replay(client,monkeypatch):
    t,m,p=setup(client);first=prepare(client,t,m,p).json()['record'];calls=[]
    async def controlled(*a,**kw):calls.append(1);return json.dumps(RESULT),{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    candidate=client.post(route(t,m,'execute'),json=ack(t,first)).json()['record'];second=prepare(client,t,m,p).json()['record']
    url=route(t,m,'').rstrip('/')
    current=client.get(url).json();assert current['record']['id']==second['id'] and len(current['history'])==2
    previous=client.get(url,params={'plan_id':first['id']}).json();assert previous['record']['candidate']==RESULT and previous['record']['candidate_token']==candidate['candidate_token'] and not previous['can_execute'] and len(calls)==1
    record=main.store.get('image_preview',first['id']);record['material_id']='foreign';main.store.put('image_preview',first['id'],record)
    assert client.get(url,params={'plan_id':first['id']}).status_code==404
    assert len(client.get(url).json()['history'])==1 and len(calls)==1
