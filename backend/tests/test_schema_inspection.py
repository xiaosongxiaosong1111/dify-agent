"""Pure schema diagnostics; no customer outputs, code execution or resources."""
import copy
import hashlib
import json
from uuid import uuid4
import pytest
from test_api import client,approved
from test_iteration_object_outcomes import SCHEMA
from app import main
from app.schema_inspection import inspect
from app.iteration_outcomes import digest


def test_valid_only_means_supported_rules_and_binds_exact_text():
    import hashlib
    raw=json.dumps(SCHEMA,indent=2);v=inspect(raw)
    assert v['valid'] is True and v['diagnostics']==[] and v['schema_sha256']==digest(SCHEMA)
    assert v['source_text_sha256']==hashlib.sha256(raw.encode()).hexdigest()
    for k in ('task_changed','network_requested','code_executed','platform_checked','business_verified'):assert v[k] is False
    assert v['verification']=='local_object_schema_rules_only'


@pytest.mark.parametrize('raw,code',[
    ('{\n "type": }','json'), ('{"type":"object","type":"string"}','duplicate'),
    ('{"x":NaN}','finite_json'), ('{"x":1e999}','finite_json'),
    ('[1]','root'), ('"private raw"','root'), ('{}','root'),
    (json.dumps({**SCHEMA,'additionalProperties':True}),'closed_object'),
    (json.dumps({**SCHEMA,'default':{}}),'keywords'),
    (json.dumps({**SCHEMA,'required':['missing private']}),'required'),
    (json.dumps({**SCHEMA,'properties':{'private':{'type':'unknown private'}}}),'type'),
    (json.dumps({**SCHEMA,'properties':{'v':{'type':'number','enum':[True]}}}),'enum'),
    (json.dumps({**SCHEMA,'properties':{'v':{'type':'number','minimum':2,'maximum':1}}}),'bounds'),
    (json.dumps({**SCHEMA,'description':3}),'text'),
    (json.dumps({**SCHEMA,'properties':{'v':{'type':'integer','maximum':9007199254740992}},'required':['v']}),'unsafe_integer'),
    ('{"type":"object","description":"sk-'+ 'x'*24+'"}','credentials'),
    (' '*64001,'size'), ('"\ud800"','encoding'),
],ids=lambda value:hashlib.sha256(repr(value).encode('utf-8','backslashreplace')).hexdigest()[:10])
def test_rejects_precisely_without_echoing_source(raw,code):
    v=inspect(raw);assert v['valid'] is False and v['schema_sha256'] is None
    assert code in [x['code'] for x in v['diagnostics']]
    assert 'private' not in json.dumps(v)


def test_json_positions_and_property_index_not_customer_field_name():
    v=inspect('{\n "type": }');d=v['diagnostics'][0]
    assert d=={'code':'json','path':None,'line':2,'column':10}
    schema={**SCHEMA,'properties':{'private_name':{'type':'string','minLength':-1}}}
    v=inspect(json.dumps(schema));assert {'code':'bounds','path':'schema.properties[1].minLength','line':None,'column':None} in v['diagnostics']
    assert 'private_name' not in json.dumps(v)


def test_many_errors_use_explicit_coarse_notice_not_partial_success():
    schema={'type':'object','properties':{str(i):{'type':'string','unknown':1} for i in range(30)},'additionalProperties':False}
    v=inspect(json.dumps(schema));assert v['valid'] is False
    assert v['diagnostics']==[{'code':'too_many','path':None,'line':None,'column':None}]


def test_preview_route_stateless_and_no_external_dispatch(client,monkeypatch):
    t=approved(client);url=f"/api/tasks/{t['id']}";before=copy.deepcopy(main.store.get('task',t['id']))
    def forbidden(*a,**kw):raise AssertionError('No models or Dify allowed')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
    p={'revision':t['revision'],'schema_text':json.dumps(SCHEMA),'request_nonce':str(uuid4())}
    r=client.post(url+'/object-schema-check',json=p);assert r.status_code==200,r.text
    v=r.json();assert v['valid'] and v['request_nonce']==p['request_nonce'] and v['task_id']==t['id']
    r=client.post(url+'/object-schema-check',json={**p,'schema_text':'{"x":}'});assert r.status_code==200 and not r.json()['valid']
    assert main.store.get('task',t['id'])==before


@pytest.mark.parametrize('field,value,status',[('revision',True,422),('revision',999,409),('request_nonce','private',422),('schema_text',{},422),('schema_text','private'*10000,422),('extra','private',422)],ids=lambda value:hashlib.sha256(repr(value).encode('utf-8','backslashreplace')).hexdigest()[:10])
def test_route_strict_no_echo(client,field,value,status):
    t=approved(client);p={'revision':t['revision'],'schema_text':json.dumps(SCHEMA),'request_nonce':str(uuid4())};p[field]=value
    r=client.post(f"/api/tasks/{t['id']}/object-schema-check",json=p)
    assert r.status_code==status and 'private' not in r.text
