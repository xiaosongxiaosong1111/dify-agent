import sys,json,copy,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import main
from app.model_configuration_check import check_rules
from test_api import client,create_env
from test_resources import catalog
from test_agent_environment_mapping import state

MODEL={'provider':'langgenius/test/test','name':'exact-model','mode':'chat','completion_params':{'temperature':.4,'max_tokens':512}}
RULES=[{'name':'temperature','label':'温度','type':'float','required':True,'min':0,'max':1},{'name':'max_tokens','label':'输出上限','type':'int','required':True,'min':1,'max':1024}]


def test_known_rules_match_does_not_inherit_or_claim_calls():
    model=copy.deepcopy(MODEL);rules=copy.deepcopy(RULES);result=check_rules(model,rules)
    assert result['matches_known_rules'] and result['status']=='matches_known_rules'
    assert result['errors']==result['unresolved']==[] and model==MODEL and rules==RULES


@pytest.mark.parametrize('field,value',[('temperature',1.5),('temperature',True),('max_tokens',512.5),('max_tokens',False),('max_tokens',1025)])
def test_type_and_range_errors_are_not_accepted(field,value):
    model=copy.deepcopy(MODEL);model['completion_params'][field]=value
    result=check_rules(model,RULES);assert result['status']=='invalid' and not result['matches_known_rules'] and result['errors']


def test_unknown_missing_and_template_only_rules_never_guess_or_default():
    model=copy.deepcopy(MODEL);model['completion_params']['unknown_extra']=.2
    rules=copy.deepcopy(RULES);rules[0].pop('type');rules[0]['use_template']='temperature'
    rules.append({'name':'future_required','label':'未知必填政策','type':'string'})
    v=check_rules(model,rules);assert v['status']=='needs_review' and len(v['unresolved'])==3 and not v['errors']
    rules[-1]['required']=True
    v=check_rules(model,rules);assert v['status']=='invalid' and any('future_required' in e for e in v['errors'])


def test_options_type_identity_does_not_match_boolean_to_number():
    model=copy.deepcopy(MODEL);model['completion_params']['flag']=True
    rules=copy.deepcopy(RULES)+[{'name':'flag','type':'boolean','required':False,'options':[1]}]
    assert check_rules(model,rules)['status']=='invalid'
    rules[-1]['options']=[True];assert check_rules(model,rules)['matches_known_rules']


@pytest.mark.parametrize('patch',[{'min':2,'max':1},{'max':True},{'options':[{}]}])
def test_malformed_constraints_unresolved_instead_of_ignoring(patch):
    rules=copy.deepcopy(RULES);rules[0].update(patch)
    v=check_rules(MODEL,rules);assert not v['matches_known_rules'] and v['unresolved']


@pytest.mark.parametrize('rules',[None,[{'name':'temperature'},{'name':'temperature'}],[{'name':'bad/name'}],[{}],[{'name':'x'}]*129])
def test_unbounded_or_ambiguous_rule_sets_rejected_as_whole(rules):
    with pytest.raises(ValueError):check_rules(MODEL,rules)


def install(monkeypatch,*,rules=RULES,status='active',change=False):
    calls=[]
    async def models(self,kind):calls.append('models');return catalog(status)
    async def parameters(self,path,model):
        calls.append('rules');assert path==MODEL['provider'] and model==MODEL['name']
        if change:
            env=main.store.get('environment',self.env['id']);env['connection_revision']='changed';main.store.put('environment',env['id'],env)
        return {'data':copy.deepcopy(rules)}
    monkeypatch.setattr(main.DifyClient,'models',models);monkeypatch.setattr(main.DifyClient,'model_parameters',parameters)
    return calls


def check(client,env,**patch):
    return client.post(f"/api/environments/{env['id']}/model-configuration-check",json={'model_json':json.dumps(MODEL),'expected_connection_revision':env.get('connection_revision'),**patch})


def test_api_metadata_only_bound_exact_document_and_no_persistent_writes(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch);before=state();r=check(client,env);assert r.status_code==200,r.text
    v=r.json();assert v['matches_known_rules'] and v['verification']=='directory_model_rules_only'
    assert v['model_document_token']==hashlib.sha256(json.dumps(MODEL).encode()).hexdigest()
    assert not v['platform_verified'] and not v['business_verified'] and not v['target_resources_verified'] and not v['task_modified'] and v['model_calls']==0
    assert calls==['models','rules'] and state()==before and 'PRIVATE' not in r.text


def test_api_generic_schema_ok_but_target_range_invalid_is_explicit(client,monkeypatch):
    env=create_env(client);install(monkeypatch);model=copy.deepcopy(MODEL);model['completion_params']['max_tokens']=1025
    before=state();r=check(client,env,model_json=json.dumps(model));assert r.status_code==200
    assert r.json()['status']=='invalid' and state()==before


def test_invalid_or_imprecise_model_refused_before_network_and_no_echo(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch);before=state()
    raw=json.dumps(MODEL).replace('0.4','0.40000000000000001')
    r=check(client,env,model_json=raw);assert r.status_code==422 and calls==[] and state()==before
    r=check(client,env,model_json='{"private-model-input":');assert r.status_code==422 and 'private-model-input' not in r.text and calls==[]


def test_changed_connection_before_or_during_read_not_accepted(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,change=True)
    before=state();r=check(client,env,expected_connection_revision='stale');assert r.status_code==409 and calls==[] and state()==before
    r=check(client,env);assert r.status_code==409 and calls==['models','rules']


def test_unavailable_model_never_calls_parameter_endpoint_or_substitutes(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,status='disabled');before=state()
    r=check(client,env);assert r.status_code==422 and calls==['models'] and state()==before


def test_api_template_rule_stays_unresolved_not_zero_rules_success(client,monkeypatch):
    env=create_env(client);rules=copy.deepcopy(RULES);rules[0].pop('type');rules[0]['use_template']='temperature'
    install(monkeypatch,rules=rules);r=check(client,env);assert r.status_code==200 and r.json()['status']=='needs_review' and not r.json()['matches_known_rules']


def test_duplicate_transport_key_rejected_and_input_never_echoed(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch);before=state()
    raw='{"model_json":"private-input","model_json":"duplicate-private","expected_connection_revision":null}'
    r=client.post(f"/api/environments/{env['id']}/model-configuration-check",content=raw,headers={'Content-Type':'application/json'})
    assert r.status_code==422 and 'private-input' not in r.text and calls==[] and state()==before


def test_empty_options_and_numeric_range_on_text_not_silently_ignored():
    model=copy.deepcopy(MODEL);rules=copy.deepcopy(RULES);rules[0]['options']=[]
    assert check_rules(model,rules)['status']=='needs_review'
    model['completion_params']['text_param']='public'
    rules=copy.deepcopy(RULES)+[{'name':'text_param','type':'string','required':False,'min':1}]
    v=check_rules(model,rules);assert v['status']=='needs_review' and v['unresolved']


def test_schema_error_uses_model_context_and_no_raw_fields(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch);r=client.post(f"/api/environments/{env['id']}/model-configuration-check",json={'model_json':'PRIVATE-SCHEMA-INPUT','unknown':True})
    assert r.status_code==422 and '模型配置核对字段无效' in r.text and '来源摘要' not in r.text and 'PRIVATE-SCHEMA-INPUT' not in r.text and calls==[]


def test_read_timeout_does_not_claim_unknown_external_write(client,monkeypatch):
    env=create_env(client)
    async def timeout(*args):raise main.DifyError('Dify 请求超时。外部写入结果可能未知，请先核对，不要直接重复创建。')
    monkeypatch.setattr(main.DifyClient,'models',timeout);before=state();r=check(client,env)
    assert r.status_code==502 and '未运行模型或写资源' in r.text and '写入结果可能未知' not in r.text and state()==before


def test_ambiguous_catalog_does_not_pick_first_model(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch)
    async def duplicate(*args):
        value=catalog();value['data'][0]['models']*=2;return value
    monkeypatch.setattr(main.DifyClient,'models',duplicate);r=check(client,env);assert r.status_code==422 and calls==[]


def test_unrepresentable_metadata_numbers_do_not_reach_browser_as_rounded_rules(client,monkeypatch):
    env=create_env(client);rules=copy.deepcopy(RULES);rules[1]['max']=9007199254740993
    install(monkeypatch,rules=rules);before=state();r=check(client,env)
    assert r.status_code==422 and '9007199254740993' not in r.text and '精确范围' in r.text and state()==before
