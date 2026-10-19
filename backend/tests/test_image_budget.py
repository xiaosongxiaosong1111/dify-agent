import asyncio,copy
import pytest
from test_api import client,approved
from test_task_budget import provider,policy,ledger
from test_image_messages import messages
from app import main
from app.planning import reserve_cost,PlanningStopped
from app.providers import ProviderError


@pytest.mark.parametrize('reserve',[None,'0','-1','nan','0.00000000000001','0.00000001'])
def test_missing_invalid_or_underfunded_image_reserve_does_not_dispatch_or_create_ledger(client,monkeypatch,reserve):
    t=approved(client);p=provider(client);before=main.get_task(t['id'])
    async def forbidden(*a,**kw):raise AssertionError('不应派发')
    monkeypatch.setattr(main,'call_model',forbidden)
    with pytest.raises(ProviderError):asyncio.run(main.budgets.call(t['id'],t['revision'],'material-image',p,'test-only',messages(),allow_images=True,image_reserve_usd=reserve,max_tokens=100))
    assert not ledger(client,t)['entries'] and main.get_task(t['id'])==before


def test_explicit_image_hold_is_accounted_without_forwarding_budget_value_to_provider(client,monkeypatch):
    t=approved(client);p=provider(client);assert policy(client,t,limit='1').status_code==200
    calls=[]
    async def controlled(*args,**kwargs):
        calls.append(kwargs)
        held=ledger(client,t);assert held['held_estimated_usd']=='0.25' and held['pending_count']==1
        assert held['entries'][-1]['cost_basis']=='user_declared_image_reserve'
        return '隔离图像响应',{'prompt_tokens':100,'completion_tokens':20}
    monkeypatch.setattr(main,'call_model',controlled)
    result=asyncio.run(main.budgets.call(t['id'],t['revision'],'material-image',p,'test-only',messages(),allow_images=True,image_reserve_usd='0.25',max_tokens=100))
    saved=ledger(client,t);assert result[0]=='隔离图像响应' and len(calls)==1
    assert 'image_reserve_usd' not in calls[0] and calls[0]['allow_images'] is True
    assert saved['entries'][-1]['modality']=='image' and saved['entries'][-1]['image_reserve_is_estimate'] is True
    assert saved['known_estimated_usd']=='0.00014' and saved['pending_count']==0


def test_budget_limit_stops_image_before_dispatch_and_unknown_usage_holds_full_estimate(client,monkeypatch):
    t=approved(client);p=provider(client);assert policy(client,t,limit='.3').status_code==200
    calls=[]
    async def controlled(*args,**kwargs):calls.append(kwargs);return '隔离图像结果',{}
    monkeypatch.setattr(main,'call_model',controlled)
    with pytest.raises(PlanningStopped):asyncio.run(main.budgets.call(t['id'],t['revision'],'material-image',p,'test-only',messages(),allow_images=True,image_reserve_usd='.4',max_tokens=100))
    assert not calls
    asyncio.run(main.budgets.call(t['id'],t['revision'],'material-image',p,'test-only',messages(),allow_images=True,image_reserve_usd='.25',max_tokens=100))
    saved=ledger(client,t);assert saved['held_estimated_usd']=='0.25' and saved['unknown_count']==1 and saved['blocker']


def test_invalid_content_and_missing_pricing_fail_before_any_pending_hold(client,monkeypatch):
    t=approved(client);p=provider(client);bad=messages();bad[1]['content'][0]['image_url']['url']='https://private.example/image.png'
    for chosen in [bad,messages()]:
        current=p if chosen is bad else {k:v for k,v in p.items() if k!='pricing'}
        with pytest.raises(ProviderError):asyncio.run(main.budgets.call(t['id'],t['revision'],'material-image',current,'test-only',chosen,allow_images=True,image_reserve_usd='.25',max_tokens=100))
    assert not ledger(client,t)['entries']


def test_image_override_cannot_bypass_text_estimate_or_serve_as_truthy_string_consent(client):
    t=approved(client);p=provider(client)
    with pytest.raises(ProviderError):asyncio.run(main.budgets.call(t['id'],t['revision'],'interview',p,'test-only',[{'role':'user','content':'文字'}],image_reserve_usd='.25'))
    with pytest.raises(ProviderError):asyncio.run(main.budgets.call(t['id'],t['revision'],'material-image',p,'test-only',messages(),allow_images='true',image_reserve_usd='.25'))
    with pytest.raises(ValueError,match='base64'):reserve_cost(messages(),p['pricing'],100)
    assert not ledger(client,t)['entries']
