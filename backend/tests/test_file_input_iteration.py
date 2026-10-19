import copy
import pytest,yaml
from test_file_inputs import row
from test_file_iteration import plan as http_plan,task
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest

def plan(parallel=False):
 p=http_plan(parallel=parallel);p['nodes']=[n for n in p['nodes'] if n['id']!='http'];p['nodes'][0]['config']['variables']=[row('file-list')]
 p['nodes'][1]['config']['iterator_selector']=['start','document'];p['edges']=[{'source':'start','target':'files-batch'},{'source':'files-batch','target':p['nodes'][-1]['id']}]
 return p

@pytest.mark.parametrize('parallel',[False,True])
def test_root_file_list_native_item_extraction_and_explicit_execution_policy(parallel):
 p=plan(parallel);before=copy.deepcopy(p);content,result=compile_workflow_plan(task(p));assert result['valid'],result
 root=yaml.safe_load(content);parent=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='files-batch');child=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='single-doc')
 assert parent['data']['iterator_selector']==['start','document'] and parent['data']['iterator_input_type']=='array[file]'
 assert child['data']['variable_selector']==['files-batch','item'] and child['data']['is_array_file'] is False
 assert parent['data']['is_parallel'] is parallel and parent['data']['error_handle_mode']=='terminated' and parent['data']['flatten_output'] is False
 assert p==before and any('明确批准的单次上传' in w and '冻结运行绑定尚未接通' in w for w in result['warnings'])

def test_native_source_and_child_manual_changes_preserved_and_missing_type_inferred():
 root=yaml.safe_load(compile_workflow_plan(task(plan()))[0]);parent=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='files-batch');child=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='single-doc')
 parent['data'].pop('iterator_input_type');child['data']['desc']='人工说明';child['position']['x']+=23;stamp=digest(root)
 checked=validate_preserved(root);assert checked['valid'],checked;assert digest(root)==stamp

@pytest.mark.parametrize('fault',['single','optional','unknown_format','fake_code_array','wrong_field','body_root_array','wrong_item','wrong_marker','parallel_without_reason'])
def test_file_item_proof_requires_real_declared_source_and_original_item(fault):
 p=plan();batch=p['nodes'][1];cfg=batch['config'];doc=cfg['nodes'][0]['config']
 if fault=='single':p['nodes'][0]['config']['variables']=[row()]
 elif fault=='optional':p['nodes'][0]['config']['variables'][0]['required']=False
 elif fault=='unknown_format':p['nodes'][0]['config']['variables'][0]['allowed_file_extensions']=['.unknown']
 elif fault=='fake_code_array':
  p['nodes'].insert(1,{'id':'fake','type':'code','config':{'code_language':'python3','code':'def main():\n    return {"files": []}','variables':[],'outputs':{'files':{'type':'array[file]'}}}})
  cfg['iterator_selector']=['fake','files'];p['edges']=[{'source':'start','target':'fake'},{'source':'fake','target':'files-batch'},{'source':'files-batch','target':p['nodes'][-1]['id']}]
 elif fault=='wrong_field':cfg['iterator_selector']=['start','missing']
 elif fault=='body_root_array':doc.update(variable_selector=['start','document'],input_type='array[file]',empty_policy='return_empty_array')
 elif fault=='wrong_item':doc['variable_selector']=['files-batch','index']
 elif fault=='wrong_marker':doc.update(input_type='array[file]',empty_policy='return_empty_array')
 else:cfg.update(is_parallel=True,parallel_nums=2)
 before=copy.deepcopy(p);checked=validate_plan(task(p),p);assert not checked['valid'] and p==before


def test_each_file_text_can_branch_and_merge_with_native_body_edges_preserved():
 p=plan();cfg=p['nodes'][1]['config'];doc=cfg['nodes'][0]
 cfg.update(entry_node_id=doc['id'],output_selector=['merged','output'],nodes=[doc,
 {'id':'route','type':'if-else','config':{'cases':[{'case_id':'text','logical_operator':'and','conditions':[{'variable_selector':['single-doc','text'],'varType':'string','comparison_operator':'not empty','value':''}]}]}},
 {'id':'with-text','type':'template-transform','config':{'template':'{{ text }}','variables':[{'variable':'text','value_selector':['single-doc','text'],'value_type':'string'}]}},
 {'id':'empty-text','type':'template-transform','config':{'template':'已确认空文字文件，需人工处理','variables':[]}},
 {'id':'merged','type':'variable-aggregator','config':{'variables':[['with-text','output'],['empty-text','output']],'output_type':'string','selection_mode':'first_available'}}],
 edges=[{'source':'single-doc','target':'route'},{'source':'route','target':'with-text','source_handle':'text'},{'source':'route','target':'empty-text','source_handle':'false'},{'source':'with-text','target':'merged'},{'source':'empty-text','target':'merged'}])
 content,result=compile_workflow_plan(task(p));assert result['valid'],result
 root=yaml.safe_load(content);edges=root['workflow']['graph']['edges']
 assert any(e['source']=='route' and e['sourceHandle']=='false' and e['target']=='empty-text' for e in edges)
 assert validate_preserved(root)['valid']

@pytest.mark.parametrize('consumer',['llm','template-transform','code'])
def test_original_item_is_not_implicitly_serialized_for_other_consumers(consumer):
 p=plan();cfg=p['nodes'][1]['config'];cfg['nodes'].append({'id':'raw','type':consumer,'config':
 {'user_prompt':'{{#files-batch.item#}}'} if consumer=='llm' else {'template':'{{#files-batch.item#}}','variables':[]} if consumer=='template-transform' else {'code_language':'python3','code':'def main(file):\n    return {"result": "unsafe"}','variables':[{'variable':'file','value_selector':['files-batch','item']}],'outputs':{'result':{'type':'string'}}}})
 cfg['output_selector']=['raw','text' if consumer=='llm' else 'output' if consumer=='template-transform' else 'result']
 checked=validate_plan(task(p),p);assert not checked['valid'] and '文件迭代item须先文档提取' in str(checked['errors'])
