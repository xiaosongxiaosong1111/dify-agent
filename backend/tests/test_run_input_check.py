import copy
import pytest
from test_api import client,approved
from app import main

def setup(client):
 t=approved(client);response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200
 return response.json(),client.get(f"/api/tasks/{t['id']}/run-input-schema").json()
def check(client,t,s,values,**patch):return client.post(f"/api/tasks/{t['id']}/run-input-check",json={'revision':t['revision'],'source_sha256':s['source_sha256'],'input':values,**patch})

def test_explicit_local_check_no_calls_no_input_echo_or_task_change(client,monkeypatch):
 t,s=setup(client);before=copy.deepcopy(main.get_task(t['id']))
 async def forbidden(*a,**kw):pytest.fail('本机输入检查不能执行平台或模型')
 monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 name=s['fields'][0]['variable'];response=check(client,t,s,{name:'PRIVATE-INPUT'});assert response.status_code==200,response.text
 value=response.json();assert value['valid'] and not value['platform_checked'] and not value['business_verified'] and not value['defaults_copied']
 assert 'PRIVATE-INPUT' not in response.text and main.get_task(t['id'])==before

@pytest.mark.parametrize('mode',['missing','unknown','wrong_type'])
def test_text_only_form_required_extra_and_type_checks_not_skipped(client,mode):
 t,s=setup(client);name=s['fields'][0]['variable'];values={} if mode=='missing' else {name:'valid','extra':'PRIVATE-VALUE'} if mode=='unknown' else {name:123}
 response=check(client,t,s,values);assert response.status_code==422 and 'PRIVATE-VALUE' not in response.text

def test_revision_and_final_source_hash_bound_not_old_form(client):
 t,s=setup(client);values={s['fields'][0]['variable']:'valid'}
 assert check(client,t,s,values,revision=t['revision']+1).status_code==409
 assert check(client,t,s,values,source_sha256='f'*64).status_code==409
 main.artifact_path(t).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n',encoding='utf-8')
 assert check(client,t,s,values).status_code==409

def test_source_change_during_check_not_adopted(client,monkeypatch):
 t,s=setup(client);original=main.read_run_input_schema;count=0
 def read(item):
  nonlocal count;count+=1
  if count==2:main.artifact_path(t).write_text(main.artifact_path(t).read_text(encoding='utf-8')+'\n',encoding='utf-8')
  return original(item)
 monkeypatch.setattr(main,'read_run_input_schema',read)
 assert check(client,t,s,{s['fields'][0]['variable']:'valid'}).status_code==409
