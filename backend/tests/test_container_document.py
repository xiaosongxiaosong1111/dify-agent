import copy
import pytest,yaml
from test_api import client
from test_container_http_read import plan as http_body_plan,task
from test_preserved_loop import review
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest


def plan(owner='iteration',mode='workflow'):
    p,parent,request=http_body_plan(owner,mode);cfg=parent['config'];last=cfg['nodes'][-1]
    document={'id':'documents','type':'document-extractor','config':{'variable_selector':['fetch','files'],'input_type':'array[file]','empty_policy':'return_empty_array'}}
    cfg['nodes'].insert(1,document)
    last['config']['variables'].append({'variable':'texts','value_selector':['documents','text']})
    return p,parent,document


@pytest.mark.parametrize('owner,mode',[(o,m) for o in ('iteration','loop') for m in ('workflow','advanced-chat')])
def test_body_http_files_extracts_to_array_and_preserves_selector_layout_in_parent(owner,mode):
    p,parent,document=plan(owner,mode);before=copy.deepcopy(p)
    content,checked=compile_workflow_plan(task(p,mode));assert checked['valid'],checked
    root=yaml.safe_load(content);node=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='documents')
    assert node['parentId']==parent['id'] and node['data']['variable_selector']==['fetch','files'] and node['data']['is_array_file'] is True
    assert p==before and any('不提供OCR' in w for w in checked['warnings'])
    node['position']['x']+=17;node['data']['desc']='手工保留说明';stamp=digest(root)
    preserved=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None)
    assert preserved['valid'],preserved
    assert digest(root)==stamp and node['parentId']==parent['id'] and node['data']['variable_selector']==['fetch','files']


@pytest.mark.parametrize('owner',['iteration','loop'])
@pytest.mark.parametrize('fault',['body_text','url','code_object','outer_file','future','scalar_output','ocr','single_file','unknown_empty','extra_key'])
def test_document_body_never_guesses_source_shape_policy_or_parser_options(owner,fault):
    p,parent,doc=plan(owner);cfg=doc['config']
    if fault=='body_text':cfg['variable_selector']=['fetch','body']
    elif fault=='url':cfg['variable_selector']='https://files.example.test/a.pdf'
    elif fault=='code_object':cfg['variable_selector']=[parent['config']['nodes'][-1]['id'],'next_count' if owner=='loop' else 'result']
    elif fault=='outer_file':cfg['variable_selector']=['start','files']
    elif fault=='future':parent['config']['nodes'][0],parent['config']['nodes'][1]=parent['config']['nodes'][1],parent['config']['nodes'][0]
    elif fault=='scalar_output':
        last=parent['config']['nodes'][-1];last['type']='parameter-extractor';last['config']={'query':['documents','text'],'parameters':[{'name':'value','type':'string','description':'实际文字','required':True}],'instruction':'提取','reasoning_mode':'function_call','model':{'provider':'fixture','name':'fixture','mode':'chat','temperature':0.2,'max_tokens':100},'failure_policy':'guard'}
    elif fault=='ocr':cfg['ocr']=True
    elif fault=='single_file':cfg['input_type']='file'
    elif fault=='unknown_empty':cfg['empty_policy']='skip_bad'
    else:cfg['api_key']='not-a-real-key'
    before=copy.deepcopy(p);checked=validate_plan(task(p),p)
    assert not checked['valid'] and p==before


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_document_body_dag_selector_must_dominate_and_join_before_scalar_result(owner):
    p,parent,doc=plan(owner);cfg=parent['config'];final=cfg['nodes'][-1]['id']
    cfg.update(entry_node_id='fetch',edges=[{'source':'fetch','target':'documents'},{'source':'documents','target':final}])
    content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    root=yaml.safe_load(content);checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None);assert checked['valid'],checked



def test_parallel_iteration_keeps_document_node_and_declares_parser_cost_risks():
    p,parent,doc=plan();parent['config'].update(is_parallel=True,parallel_nums=3,parallel_safe=True,parallel_reason='独立文件查询与解析，索引汇总，实际读取及解析限流和费用需核对。')
    content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked
    root=yaml.safe_load(content);node=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='documents')
    assert node['parentId']==parent['id'] and node['data']['isInIteration'] is True and node['data']['variable_selector']==['fetch','files']
    assert any('额外费用' in w for w in checked['warnings'])


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_outer_http_file_binding_is_explicitly_rejected_without_synthetic_source_guess(owner):
    p,parent,doc=plan(owner);outer=copy.deepcopy(parent['config']['nodes'][0]);outer['id']='outer-http';outer['config']['url']='https://files.test/read';outer['config'].pop('sierra_read_policy',None)
    p['nodes'].insert(1,outer)
    for edge in p['edges']:
        if edge['target']==parent['id']:edge['target']='outer-http'
    p['edges'].append({'source':'outer-http','target':parent['id']})
    doc['config']['variable_selector']=['outer-http','files']
    checked=validate_plan(task(p),p)
    assert not checked['valid'] and any('HTTP.files' in e for e in checked['errors'])


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_dag_sibling_file_source_cannot_be_read_on_other_path(owner):
    p,parent,doc=plan(owner);cfg=parent['config'];fetch=cfg['nodes'][0];sibling=copy.deepcopy(fetch);sibling['id']='other-fetch';doc['config']['variable_selector']=['other-fetch','files']
    gate={'id':'gate','type':'if-else','config':{'cases':[{'case_id':'yes','logical_operator':'and','conditions':[{'variable_selector':['fetch','status_code'],'varType':'number','comparison_operator':'>=','value':'200'}]}]}}
    cfg['nodes']=[fetch,gate,doc,sibling,cfg['nodes'][-1]];terminal=cfg['nodes'][-1]['id']
    # Remove documents binding from shared terminal so the asserted failure is the file source itself.
    cfg['nodes'][-1]['config']['variables']=[r for r in cfg['nodes'][-1]['config']['variables'] if r['variable']!='texts']
    cfg.update(entry_node_id='fetch',edges=[{'source':'fetch','target':'gate'},{'source':'gate','target':'documents','source_handle':'yes'},{'source':'gate','target':'other-fetch','source_handle':'false'},{'source':'documents','target':terminal},{'source':'other-fetch','target':terminal}])
    checked=validate_plan(task(p),p);assert not checked['valid'] and any('documents' in e for e in checked['errors'])
