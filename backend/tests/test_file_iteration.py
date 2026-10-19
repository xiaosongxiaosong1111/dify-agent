import copy,json
import pytest,yaml
from test_api import client
from test_preservation_extensions import http_plan
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest
from app.declared_types import resolve


def plan(mode='workflow',parallel=False):
    p=http_plan();p['nodes'][-1]['config']={'outputs':[{'variable':'texts','value_selector':['files-batch','output']}]}
    doc={'id':'single-doc','type':'document-extractor','config':{'variable_selector':['files-batch','item'],'input_type':'file','empty_policy':'fail_if_missing'}}
    parent={'id':'files-batch','type':'iteration','config':{'iterator_selector':['http','files'],'iterator_input_type':'array[file]','output_selector':['single-doc','text'],'output_type':'array[string]','nodes':[doc],'is_parallel':parallel,'error_handle_mode':'terminated','flatten_output':False}}
    if parallel:parent['config'].update(parallel_nums=3,parallel_safe=True,parallel_reason='逐文件独立读取解析，格式/Unstructured出站及费用待核对。')
    p['nodes'].insert(2,parent);p['edges']=[{'source':'start','target':'http'},{'source':'http','target':'files-batch'},{'source':'files-batch','target':p['nodes'][-1]['id']}]
    if mode=='advanced-chat':
        p['nodes'][0]['config']['variables']=[];p['nodes'][1]['config']=json.loads(json.dumps(p['nodes'][1]['config']).replace('{{#start.query#}}','{{#sys.query#}}'));p['nodes'][-1].update(type='answer',config={'answer':'{{#files-batch.output#}}'})
    return p


def task(p,mode='workflow'):return {'app_type':mode,'configuration':{},'workflow_plan':p}


@pytest.mark.parametrize('mode,parallel',[(m,b) for m in ('workflow','advanced-chat') for b in (False,True)])
def test_original_http_file_array_iterates_single_file_text_with_native_false_flag(mode,parallel):
    p=plan(mode,parallel);before=copy.deepcopy(p);content,checked=compile_workflow_plan(task(p,mode));assert checked['valid'],checked
    root=yaml.safe_load(content);nodes=root['workflow']['graph']['nodes'];parent=next(n for n in nodes if n['id']=='files-batch');doc=next(n for n in nodes if n['id']=='single-doc')
    assert parent['data']['iterator_input_type']=='array[file]' and parent['data']['iterator_selector']==['http','files']
    assert doc['data']['variable_selector']==['files-batch','item'] and doc['data']['is_array_file'] is False and doc['parentId']=='files-batch'
    assert parent['data']['output_type']=='array[string]' and p==before
    assert resolve({'single-doc':p['nodes'][2]['config']['nodes'][0]},['single-doc','text'])=='string'
    if not parallel:
        doc['position']['x']+=19;doc['data']['desc']='真实单文件手改说明';stamp=digest(root);preserved=validate_preserved(root);assert preserved['valid'],preserved;assert digest(root)==stamp


@pytest.mark.parametrize('fault',['code_array','wrong_http_field','unconfirmed_input','wrong_policy','file_array_marker','wrong_item','own_index','root_file','unsupported_type','unknown_fields','bad_file_type'])
def test_file_item_proof_cannot_be_replaced_by_user_declaration_or_marker(fault):
    p=plan();parent=p['nodes'][2];doc=parent['config']['nodes'][0];cfg=doc['config']
    if fault=='code_array':p['nodes'][1]={'id':'http','type':'code','config':{'code_language':'python3','code':'def main():\n    return {"files": []}','variables':[],'outputs':{'files':{'type':'array[file]'}}}}
    elif fault=='wrong_http_field':parent['config']['iterator_selector']=['http','body']
    elif fault=='unconfirmed_input':parent['config']['iterator_input_type']='array[object]'
    elif fault=='wrong_policy':cfg['empty_policy']='return_empty_array'
    elif fault=='file_array_marker':cfg['input_type']='array[file]';cfg['empty_policy']='return_empty_array'
    elif fault=='wrong_item':cfg['variable_selector']=['http','files']
    elif fault=='own_index':cfg['variable_selector']=['files-batch','index']
    elif fault=='root_file':p['nodes'].insert(2,{**copy.deepcopy(doc),'id':'root-doc'});p['edges'].insert(1,{'source':'http','target':'root-doc'})
    elif fault=='unsupported_type':cfg['input_type']=['file']
    elif fault=='unknown_fields':cfg['scope_file_verified']=True
    else:cfg['input_type']='object'
    before=copy.deepcopy(p);checked=validate_plan(task(p),p);assert not checked['valid'] and p==before


def test_single_document_string_is_valid_body_text_query_not_an_array_guess():
    p=plan();cfg=p['nodes'][2]['config'];cfg['nodes'].append({'id':'response','type':'llm','config':{'system_prompt':'根据单文件文字回答','user_prompt':'{{#single-doc.text#}}','model':{'provider':'fixture','name':'fixture','mode':'chat','completion_params':{'temperature':0.2,'max_tokens':100}}}});cfg['output_selector']=['response','text']
    content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    root=yaml.safe_load(content);response=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='response');assert response['parentId']=='files-batch' and response['data']['prompt_template'][1]['text']=='{{#single-doc.text#}}'
    cfg['nodes'][0]['config'].update(input_type='array[file]',empty_policy='return_empty_array');checked=validate_plan(task(p),p);assert not checked['valid']



def test_preserved_single_file_marker_must_match_runtime_selector_shape():
    p=plan();content,checked=compile_workflow_plan(task(p));assert checked['valid']
    root=yaml.safe_load(content);doc=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='single-doc')
    doc['data']['is_array_file']=True;before=copy.deepcopy(root);checked=validate_preserved(root)
    assert not checked['valid'] and root==before


def test_file_iterator_direct_text_output_never_accepts_fake_trusted_ir_field():
    p=plan();p['nodes'][2]['config']['iterator_input_type']='array[object]';p['trusted_file_items']=[['files-batch','item']]
    before=copy.deepcopy(p);checked=validate_plan(task(p),p);assert not checked['valid'] and p==before
