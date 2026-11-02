"""Saved single-turn cases need full validation before any external run boundary."""
import copy
import pytest
from fastapi.testclient import TestClient
from test_api import client,forbid_api_external_calls
from test_case_sequence import ready
from app import main


def valid():return {'id':'chosen','name':'公开用例','input':{'query':'q'},'expectation':{'mode':'equals','target':'result','expected':'ok'},'required':True}

BAD=[{'id':'chosen','name':'旧最小用例'},valid()|{'input':None},valid()|{'input':[]},valid()|{'expectation':None},valid()|{'expectation':{'mode':'PRIVATE_INVALID','target':'result','expected':'PRIVATE_TEXT'}},valid()|{'required':1},valid()|{'followups':[]},valid()|{'name':' '}]

@pytest.mark.parametrize('case',BAD)
def test_invalid_selected_case_stops_before_external_boundary_without_mutation(client,monkeypatch,case):
 t=ready(client);t['test_cases']=[case];main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));ledger=copy.deepcopy(main.store.get('task_budget',t['id']));entered=[];reads=[]
 async def boundary(*a,**kw):entered.append(1);return {'entered':True}
 old_secret=main.store.secret
 def secret(*a,**kw):reads.append(1);return old_secret(*a,**kw)
 monkeypatch.setattr(main,'external_action',boundary);monkeypatch.setattr(main.store,'secret',secret)
 with TestClient(main.app,raise_server_exceptions=False) as safe:r=safe.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'case_id':'chosen'})
 assert r.status_code==422 and not entered and not reads and 'PRIVATE' not in r.text
 assert main.get_task(t['id'])==before and main.store.get('task_budget',t['id'])==ledger

@pytest.mark.parametrize('cases',[None,{},[valid(),valid()]])
def test_invalid_collection_or_ambiguous_identity_not_dispatched(client,monkeypatch,cases):
 t=ready(client);t['test_cases']=cases;main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));entered=[]
 async def boundary(*a,**kw):entered.append(1);return {'entered':True}
 monkeypatch.setattr(main,'external_action',boundary)
 with TestClient(main.app,raise_server_exceptions=False) as safe:r=safe.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'case_id':'chosen'})
 assert r.status_code==422 and not entered and main.get_task(t['id'])==before


def test_invalid_expectation_does_not_spend_even_one_service_request(client,monkeypatch):
 t=ready(client);t['test_cases']=[valid()|{'expectation':{'mode':'PRIVATE_INVALID'}}];main.save_task(t);before=copy.deepcopy(main.get_task(t['id']));calls=[]
 async def run(self,values):calls.append(1);return {'data':{'status':'succeeded','outputs':{'result':'ok'}}}
 monkeypatch.setattr(main.DifyClient,'run_workflow',run)
 r=client.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'case_id':'chosen'})
 print('RUN_STATUS',r.status_code,'SERVICE_CALLS',len(calls))
 assert r.status_code==422 and not calls and main.get_task(t['id'])==before


def test_valid_selected_case_keeps_original_values_and_ignores_unrelated_bad_rows(client,monkeypatch):
 t=ready(client);chosen=valid();t['test_cases']=[{'id':'other'},chosen];main.save_task(t);received=[]
 async def boundary(*a,**kw):received.append(copy.deepcopy(kw['test_case']));return {'admitted':True}
 monkeypatch.setattr(main,'external_action',boundary)
 with TestClient(main.app,raise_server_exceptions=False) as safe:r=safe.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'case_id':'chosen'})
 assert r.status_code==200 and received==[chosen]


def test_free_input_does_not_validate_unselected_old_cases(client,monkeypatch):
 t=ready(client);t['test_cases']=[{'id':'other'}];main.save_task(t);received=[]
 async def boundary(*a,**kw):received.append(kw.get('test_case'));return {'admitted':True}
 monkeypatch.setattr(main,'external_action',boundary)
 r=client.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'input':{'query':'q'}})
 assert r.status_code==200 and received==[None]


def test_unknown_identity_still_404(client,monkeypatch):
 t=ready(client)
 async def boundary(*a,**kw):pytest.fail('unknown case must not enter external boundary')
 monkeypatch.setattr(main,'external_action',boundary)
 r=client.post('/api/tasks/'+t['id']+'/run',json={'revision':t['revision'],'case_id':'unknown'})
 assert r.status_code==404