import copy,json
from test_agent_environment_mapping import prepared,body,request,MODEL,A,B
from test_api import client
from app.agent_environment_mapping import source_summary
from app.agent_model_comparison import model


def test_valid_knowledge_source_contract_is_complete_and_no_state_change(client):
    from test_agent_environment_mapping import state
    task,root,p,target=prepared(client,knowledge=True,source_ids=[A,B])
    baseline=state();source=p['agent_mapping_source']
    assert source['available'] and source['dataset_ids']==[A,B]
    node=json.loads(source['model_template_json'])
    assert set(node)=={'provider','name','mode','completion_params'}
    assert node['completion_params']['temperature']==task['configuration']['temperature']
    assert node['completion_params']['max_tokens']==task['configuration']['max_tokens']
    assert 'credential_ref' not in source['model_template_json']
    # A template is only public input. A complete explicit target mapping is still required.
    bad=request(client,task,p,target,target_model_json=source['model_template_json'])
    assert bad.status_code==422 and state()==baseline


def test_valid_text_source_is_empty_library_list(client):
    _,_,p,_=prepared(client)
    assert p['agent_mapping_source']['available']
    assert p['agent_mapping_source']['dataset_ids']==[]


def test_unsupported_source_does_not_expose_mapping_entry(client):
    _,_,p,_=prepared(client,unsupported=True)
    assert not p['validation']['valid'] and 'agent_mapping_source' not in p


def test_source_model_template_does_not_default_missing_or_complex_settings(client):
    _,root,_,_=prepared(client)
    broken=copy.deepcopy(root);model(broken)['model_settings'].pop('temperature')
    assert source_summary(broken)['available'] is False
    model(broken)['model_settings']['temperature']=.2
    model(broken)['model_settings']['stop']=['not-representable']
    assert source_summary(broken)['available'] is False


def test_source_contract_retains_complete_safe_model_parameters(client):
    _,root,_,_=prepared(client)
    native=model(root);native['model_settings'].update(top_p=.75,response_format={'type':'json_object'})
    node=json.loads(source_summary(root)['model_template_json'])
    assert node['completion_params']['top_p']==.75
    assert node['completion_params']['response_format']=='json_object'
    assert native['model_settings']['response_format']=={'type':'json_object'}
