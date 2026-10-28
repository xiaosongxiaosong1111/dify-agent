import copy,importlib.util,json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('literal_scope',ROOT/'tools/c1-model-free368/literal_scope.py');scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)


def pair():
    f=json.loads((ROOT/'tools/c1-planning365/fixture.json').read_text('utf-8'));a=copy.deepcopy(f['plan']);before,after=f['before_literal'],f['changed_fallback']
    llm=next(n for n in a['nodes'] if n['type']=='llm');llm['config']['system_prompt']+='\n资料不足时仅回答：'+before
    b=copy.deepcopy(a)
    for n in b['nodes']:
        if n['type']=='llm':n['config']['system_prompt']=n['config']['system_prompt'].replace(before,after)
        if n['type']=='template-transform':n['config']['template']=after
    return a,b,before,after


def test_two_locations_for_one_business_text_are_compared_without_edit_or_authorization():
    a,b,before,after=pair();old_a,old_b=copy.deepcopy(a),copy.deepcopy(b);r=scope.check(a,b,before,after)
    assert r['other_content_unchanged'] and len(r['changed_fields'])==2
    assert not any(r[k] for k in ('candidate_changed','network_requested','resource_authorized','platform_checked','business_verified'))
    assert a==old_a and b==old_b


@pytest.mark.parametrize('change',['template_only','prompt_only','input','output','edges','dataset','model','tokens','thinking','third_text','added_node','deleted_node','renamed_node','number_type'])
def test_incomplete_or_additional_changes_are_rejected(change):
    a,b,before,after=pair();by={n['type']:n for n in b['nodes']}
    if change=='template_only':by['llm']['config']=copy.deepcopy(next(n for n in a['nodes'] if n['type']=='llm')['config'])
    elif change=='prompt_only':by['template-transform']['config']['template']=before
    elif change=='input':by['start']['config']['variables'][0]['required']=False
    elif change=='output':by['end']['config']['outputs'][0]['variable']='another'
    elif change=='edges':b['edges'].pop()
    elif change=='dataset':by['knowledge-retrieval']['config']['dataset_ids']=['new-library']
    elif change in ('model','tokens','thinking'):
        model=by['llm']['config']['model']
        if change=='model':model['name']='another'
        else:model['completion_params']['max_tokens' if change=='tokens' else 'thinking']=True
    elif change=='third_text':by['llm']['config']['user_prompt']='new question'
    elif change=='added_node':b['nodes'].append({'id':'extra','type':'http-request','config':{}})
    elif change=='deleted_node':b['nodes'].pop()
    elif change=='renamed_node':b['nodes'][0]['id']='other'
    else:b['schema_version']=True
    with pytest.raises(scope.ScopeError):scope.check(a,b,before,after)


@pytest.mark.parametrize('change',['missing_literal','duplicate_literal','duplicate_target','duplicate_id','nonfinite','invalid_unicode','oversize','same_text'])
def test_ambiguous_source_does_not_infer_allowed_locations(change):
    a,b,before,after=pair();llm=next(n for n in a['nodes'] if n['type']=='llm')
    if change=='missing_literal':llm['config']['system_prompt']='no fixed fallback'
    elif change=='duplicate_literal':llm['config']['system_prompt']+=before
    elif change=='duplicate_target':a['nodes'].append(copy.deepcopy(llm)|{'id':'another-llm'})
    elif change=='duplicate_id':a['nodes'].append(copy.deepcopy(llm))
    elif change=='nonfinite':a['extra']=float('nan')
    elif change=='invalid_unicode':a['extra']='\ud800'
    elif change=='oversize':a['extra']='x'*2_000_001
    else:after=before
    with pytest.raises(scope.ScopeError):scope.check(a,b,before,after)
