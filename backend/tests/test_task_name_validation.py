import copy,json
import pytest
from test_api import client,create,forbid_api_external_calls
from app import main

BAD=[('', 'empty'),('   ','blank'),('字'*101,'long'),('\ud800','high_surrogate'),('\udfff','low_surrogate'),(True,'bool'),(3,'number'),({},'object'),([],'array')]

@pytest.mark.parametrize('name',[v for v,_ in BAD],ids=[i for _,i in BAD])
def test_bad_create_name_is_safe_and_does_not_create_task_or_budget(client,name):
    before=(main.store.list('task'),main.store.list('task_budget'))
    r=client.post('/api/tasks',content=json.dumps({'name':name,'app_type':'workflow'}),headers={'Content-Type':'application/json'})
    assert r.status_code==422 and isinstance(r.json().get('detail'),str)
    assert (main.store.list('task'),main.store.list('task_budget'))==before


@pytest.mark.parametrize('name',[v for v,_ in BAD],ids=[i for _,i in BAD])
def test_bad_rename_never_truncates_or_applies_other_changes(client,name):
    t=create(client);before=copy.deepcopy(main.store.get('task',t['id']));ledger=main.store.get('task_budget',t['id'])
    r=client.patch(f"/api/tasks/{t['id']}",content=json.dumps({'name':name,'requirements':{'goal':'不能部分采用'},'expected_revision':t['revision']}),headers={'Content-Type':'application/json'})
    assert r.status_code==422 and isinstance(r.json().get('detail'),str)
    assert main.store.get('task',t['id'])==before and main.store.get('task_budget',t['id'])==ledger


@pytest.mark.parametrize('name',['字'*100,'😀'*100,'  '+'😀'*100+'  ','售后 [<Demo>]'],ids=['chinese_100','astral_100','trim_then_count','literal_name'])
def test_valid_name_is_preserved_in_create_and_rename(client,name):
    response=client.post('/api/tasks',json={'name':name,'app_type':'advanced-chat'});assert response.status_code==201,response.text
    t=response.json();assert t['name']==name.strip() and t['app_type']=='advanced-chat'
    other=create(client);r=client.patch(f"/api/tasks/{other['id']}",json={'name':name,'expected_revision':other['revision']});assert r.status_code==200,r.text
    assert r.json()['name']==name.strip() and r.json()['revision']==other['revision']+1 and len(r.json()['versions'])==len(other['versions'])+1


def test_same_trimmed_name_does_not_add_business_revision(client):
    t=create(client);r=client.patch(f"/api/tasks/{t['id']}",json={'name':'  '+t['name']+'  ','expected_revision':t['revision']})
    assert r.status_code==200 and r.json()['revision']==t['revision'] and r.json()['versions']==t['versions']
