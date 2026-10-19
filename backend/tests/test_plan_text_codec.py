import copy,json
import pytest
from test_api import client,create
from test_file_structured_run import shape
from test_file_model_run import MODEL
from app import main
from app.file_structured_template import template
from app.plan_text_codec import parse,render

def test_plan_text_save_read_and_legacy_interface_keep_integer_and_do_not_persist_derived_text(client):
 t=create(client);s=shape();n=900719925474099312345678901;s['properties']['amount']['maximum']=n;p=template(json.dumps(s),['.txt']);p['nodes'][2]['config']['model']=copy.deepcopy(MODEL);text=json.dumps(p,ensure_ascii=False)
 r=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan_text':text});assert r.status_code==200,r.text;saved=r.json()
 assert parse(saved['plan_text'])['nodes'][2]['config']['structured_output']['schema']['properties']['amount']['maximum']==n
 raw=main.store.get('task',t['id']);assert 'plan_text' not in raw and raw['workflow_plan']['nodes'][2]['config']['structured_output']['schema']['properties']['amount']['maximum']==n
 read=client.get(f"/api/tasks/{t['id']}/plan");assert read.status_code==200 and str(n) in read.json()['plan_text']
 legacy=client.post(f"/api/tasks/{t['id']}/plan",content=json.dumps({'revision':saved['revision'],'plan':p}),headers={'content-type':'application/json'});assert legacy.status_code==200 and str(n) in legacy.json()['plan_text']

@pytest.mark.parametrize('text',['{"a":1,"a":2}','[]','{"value":NaN}','{"value":1e999}','{"value":"\ud800"}','{broken'],ids=['duplicate','array','nonfinite','overflow','surrogate','broken'])
def test_invalid_raw_plan_does_not_change_task_or_echo_content(client,text):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));body=json.dumps({'revision':t['revision'],'plan_text':text},ensure_ascii=True)
 r=client.post(f"/api/tasks/{t['id']}/plan",content=body,headers={'content-type':'application/json'});assert r.status_code==422 and main.get_task(t['id'])==before

@pytest.mark.parametrize('patch',[{}, {'plan':{},'plan_text':'{}'},{'plan_text':{},'private_field':'private-raw'},{'revision':True,'plan_text':'{}'}])
def test_plan_interface_requires_one_explicit_strict_payload_and_hides_validation_input(client,patch):
 t=create(client);r=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],**patch});assert r.status_code==422 and 'private-raw' not in r.text

def test_outer_duplicate_and_null_are_not_silently_ignored(client):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']))
 for text in ['{"revision":1,"revision":1,"plan":{}}','{"revision":1,"plan_text":null}']:
  r=client.post(f"/api/tasks/{t['id']}/plan",content=text,headers={'content-type':'application/json'});assert r.status_code==422 and main.get_task(t['id'])==before

def test_canonical_plan_render_keeps_large_numbers_and_empty_is_explicit():
 value={'n':900719925474099312345678901};assert parse(render(value))==value and render(None) is None


def test_render_uses_complete_compact_text_when_indentation_exceeds_limit(monkeypatch):
 from app import plan_text_codec as codec
 value={'x':list(range(15))};monkeypatch.setattr(codec,'MAX_BYTES',100)
 assert len(json.dumps(value,indent=2).encode())>100
 assert len(codec.render(value).encode())<=100 and codec.parse(codec.render(value))==value

def test_plan_at_compact_limit_can_be_saved_read_and_saved_with_legacy_object(client,monkeypatch):
 from app import plan_text_codec as codec
 t=create(client);p=template(json.dumps(shape()),['.txt']);p['nodes'][2]['config']['model']=copy.deepcopy(MODEL)
 text=json.dumps(p,ensure_ascii=False,separators=(',',':'));monkeypatch.setattr(codec,'MAX_BYTES',len(text.encode('utf-8')))
 r=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan_text':text});assert r.status_code==200,r.text
 saved=r.json();assert codec.parse(saved['plan_text'])==p and len(saved['plan_text'].encode('utf-8'))<=codec.MAX_BYTES
 read=client.get(f"/api/tasks/{t['id']}/plan");assert read.status_code==200 and codec.parse(read.json()['plan_text'])==p
 r=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':saved['revision'],'plan':p});assert r.status_code==200 and codec.parse(r.json()['plan_text'])==p

def test_reply_encoding_failure_does_not_partially_save_plan_or_invalidate_confirmations(client,monkeypatch):
 from app import plan_text_codec as codec
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));p=template(json.dumps(shape()),['.txt'])
 def refuse(value):raise ValueError('private-encoding-content')
 monkeypatch.setattr(codec,'render',refuse)
 r=client.post(f"/api/tasks/{t['id']}/plan",json={'revision':t['revision'],'plan_text':json.dumps(p)})
 assert r.status_code==422 and 'private-encoding-content' not in r.text and main.get_task(t['id'])==before

@pytest.mark.parametrize('null_key',['plan','plan_text'])
def test_both_plan_keys_are_rejected_even_when_one_is_explicit_null(client,null_key):
 t=create(client);before=copy.deepcopy(main.get_task(t['id']));p=template(json.dumps(shape()),['.txt']);p['nodes'][2]['config']['model']=copy.deepcopy(MODEL)
 payload={'revision':t['revision'],'plan':p,'plan_text':json.dumps(p)};payload[null_key]=None
 r=client.post(f"/api/tasks/{t['id']}/plan",json=payload)
 assert r.status_code==422 and main.get_task(t['id'])==before
