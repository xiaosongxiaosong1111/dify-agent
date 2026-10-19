import copy
import pytest,yaml
from test_file_inputs import plan as file_plan
from test_workflow_plan import task,plan_task
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest
from app.condition_settings import validate

def plan(op='not empty'):
 p=file_plan('file-list');start,extract,end=p['nodes'];end['config']['outputs'][0]['value_selector']=['merged','output']
 condition={'variable_selector':['start','document'],'varType':'array[file]','comparison_operator':op,'value':''}
 route={'id':'has-files','type':'if-else','config':{'cases':[{'case_id':'selected','logical_operator':'and','conditions':[condition]}]}}
 join={'id':'join','type':'code','config':{'code_language':'python3','code':'def main(texts):\n    return {"result": "\\n".join(texts)}','variables':[{'variable':'texts','value_selector':['extract','text']}],'outputs':{'result':{'type':'string'}}}}
 empty={'id':'no-files','type':'template-transform','config':{'template':'未上传文件，请补齐后重新运行。','variables':[]}}
 merge={'id':'merged','type':'variable-aggregator','config':{'variables':[['join','result'],['no-files','output']],'output_type':'string','selection_mode':'first_available'}}
 p['nodes']=[start,route,extract,join,empty,merge,end]
 p['edges']=[{'source':'start','target':'has-files'},{'source':'has-files','target':'extract','source_handle':'selected'},{'source':'has-files','target':'no-files','source_handle':'false'},{'source':'extract','target':'join'},{'source':'join','target':'merged'},{'source':'no-files','target':'merged'},{'source':'merged','target':'end'}]
 if op=='empty':
  p['edges'][1]['target']='no-files';p['edges'][2]['target']='extract'
 return p

@pytest.mark.parametrize('op',['empty','not empty'])
def test_explicit_empty_file_list_branch_compiles_without_bypassing_extraction(op):
 p=plan(op);before=copy.deepcopy(p);content,checked=compile_workflow_plan(plan_task(p));assert checked['valid'],checked
 root=yaml.safe_load(content);nodes={n['id']:n for n in root['workflow']['graph']['nodes']};condition=nodes['has-files']['data']['cases'][0]['conditions'][0]
 assert condition['varType']=='array[file]' and condition['comparison_operator']==op and condition['value']==''
 assert nodes['extract']['data']['variable_selector']==['start','document'] and nodes['extract']['data']['is_array_file'] is True
 assert any(e['source']=='has-files' and e['sourceHandle']==('selected' if op=='empty' else 'false') and e['target']=='no-files' for e in root['workflow']['graph']['edges'])
 assert p==before and validate_preserved(root)['valid']

@pytest.mark.parametrize('op',['contains','exists','not exists','=','null','not null',[],None])
def test_file_array_only_supports_empty_or_nonempty_without_coercion(op):
 p=plan();p['nodes'][1]['config']['cases'][0]['conditions'][0]['comparison_operator']=op;old=copy.deepcopy(p)
 checked=validate_plan(task(),p);assert not checked['valid'] and p==old

@pytest.mark.parametrize('value',[True,0,['file'],{},'ignored','{{#start.document#}}'])
def test_ignored_file_comparison_values_are_not_silently_carried(value):
 p=plan();p['nodes'][1]['config']['cases'][0]['conditions'][0]['value']=value;checked=validate_plan(task(),p)
 assert not checked['valid']

@pytest.mark.parametrize('fault',['code_array','single_file','scalar_declaration','unknown_variable','fake_type'])
def test_file_array_condition_requires_native_provenance_and_exact_type(fault):
 p=plan();c=p['nodes'][1]['config']['cases'][0]['conditions'][0]
 if fault=='code_array':
  p['nodes'].insert(1,{'id':'fake','type':'code','config':{'code_language':'python3','code':'def main():\n    return {"files": []}','variables':[],'outputs':{'files':{'type':'array[file]'}}}})
  c['variable_selector']=['fake','files'];p['edges'][0]['target']='fake';p['edges'].insert(1,{'source':'fake','target':'has-files'})
 elif fault=='single_file':p['nodes'][0]['config']['variables'][0]['type']='file'
 elif fault=='scalar_declaration':c['varType']='string'
 elif fault=='unknown_variable':c['variable_selector']=['start','unknown']
 else:c['varType']='file'
 before=copy.deepcopy(p);checked=validate_plan(task(),p);assert not checked['valid'] and p==before


def test_manual_condition_fields_branch_edges_and_position_preserved():
 root=yaml.safe_load(compile_workflow_plan(plan_task(plan()))[0]);node=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='has-files')
 node['position']['x']+=29;node['data']['title']='人工文件检查';node['data']['cases'][0]['conditions'][0]['value']=None
 stamp=digest(root);checked=validate_preserved(root);assert checked['valid'],checked;assert digest(root)==stamp


@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_same_scope_native_http_files_can_be_checked_without_file_upload_entry(mode):
 from test_preservation_extensions import http_plan
 p=plan();p['nodes'][0]['config']['variables']=http_plan()['nodes'][0]['config']['variables'];http=copy.deepcopy(http_plan()['nodes'][1]);p['nodes'].insert(1,http)
 p['nodes'][2]['config']['cases'][0]['conditions'][0]['variable_selector']=[http['id'],'files'];p['nodes'][3]['config']['variable_selector']=[http['id'],'files']
 p['edges'][0]['target']=http['id'];p['edges'].insert(1,{'source':http['id'],'target':'has-files'})
 if mode=='advanced-chat':
  import json
  p['nodes'][0]['config']['variables']=[];http['config']=json.loads(json.dumps(http['config']).replace('{{#start.query#}}','{{#sys.query#}}'));p['nodes'][-1].update(type='answer',config={'answer':'{{#merged.output#}}'})
 content,checked=compile_workflow_plan(plan_task(p,mode));assert checked['valid'],checked;assert validate_preserved(yaml.safe_load(content))['valid']
