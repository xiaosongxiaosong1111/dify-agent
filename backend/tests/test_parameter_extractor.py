import copy
import pytest,yaml
from test_api import client,approved
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.declared_types import resolve
from app.model_parameters import needs_task_model

def plan(mode='workflow'):
 return {'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'text-input','required':True}] if mode=='workflow' else []}},{'id':'extract','type':'parameter-extractor','config':{'query':['start','query'] if mode=='workflow' else ['sys','query'],'parameters':[{'name':'order_no','type':'string','description':'提取明确给出的订单号，不编造。','required':True}],'reasoning_mode':'prompt','instruction':'信息不足不猜订单号。','failure_policy':{'behavior':'explicit_success_branch','guard_node_id':'check','success_case_id':'ok'}}},{'id':'check','type':'if-else','config':{'cases':[{'case_id':'ok','logical_operator':'and','conditions':[{'variable_selector':['extract','__is_success'],'varType':'number','comparison_operator':'=','value':'1'}]}]}},{'id':'success','type':'template-transform','config':{'template':'收到订单号 {{ order }}','variables':[{'variable':'order','value_selector':['extract','order_no']}]}},{'id':'failure','type':'template-transform','config':{'template':'请补充明确订单号。','variables':[]}},{'id':'merge','type':'variable-aggregator','config':{'variables':[['success','output'],['failure','output']],'output_type':'string','selection_mode':'first_available'}},{'id':'end','type':'end' if mode=='workflow' else 'answer','config':{'outputs':[{'variable':'result','value_selector':['merge','output']}]} if mode=='workflow' else {'answer':'{{#merge.output#}}'}}], 'edges':[{'source':'start','target':'extract'},{'source':'extract','target':'check'},{'source':'check','source_handle':'ok','target':'success'},{'source':'check','source_handle':'false','target':'failure'},{'source':'success','target':'merge'},{'source':'failure','target':'merge'},{'source':'merge','target':'end'}]}

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_text_extraction_compiles_with_explicit_failure_gate(client,mode):
 task=approved(client,app_type=mode);p=plan(mode);result=validate_plan(task,p);assert result['valid'],result
 task['workflow_plan']=p;content,_=compile_workflow_plan(task);doc=yaml.safe_load(content);node=next(n for n in doc['workflow']['graph']['nodes'] if n['id']=='extract')
 assert node['data']['query']==p['nodes'][1]['config']['query'] and node['data']['reasoning_mode']=='prompt'
 assert node['data']['parameters']==p['nodes'][1]['config']['parameters'] and 'failure_policy' not in node['data']
 assert needs_task_model(p) and resolve({'extract':p['nodes'][1]},['extract','__is_success'])=='number'
 assert any('__is_success=0' in warning for warning in result['warnings'])

@pytest.mark.parametrize('mutation',['missing_policy','bypass','wrong_guard','wrong_condition','extra_condition','failed_use','common_use','field_duplicate','field_reserved','legacy_bool','no_required','function_call','vision','dynamic','bad_query'])
def test_defaults_cannot_bypass_success_guard_or_unsupported_choices(client,mutation):
 task=approved(client);p=plan();cfg=p['nodes'][1]['config']
 if mutation=='missing_policy':cfg.pop('failure_policy')
 elif mutation=='bypass':p['edges'][1]['target']='success'
 elif mutation=='wrong_guard':cfg['failure_policy']['guard_node_id']='success'
 elif mutation=='wrong_condition':p['nodes'][2]['config']['cases'][0]['conditions'][0]['value']='0'
 elif mutation=='extra_condition':p['nodes'][2]['config']['cases'][0]['conditions'].append(copy.deepcopy(p['nodes'][2]['config']['cases'][0]['conditions'][0]))
 elif mutation=='failed_use':p['nodes'][4]['config']['variables']=[{'variable':'order','value_selector':['extract','order_no']}]
 elif mutation=='common_use':p['nodes'][-1]['config']['outputs'][0]['value_selector']=['extract','order_no']
 elif mutation=='field_duplicate':cfg['parameters'].append(copy.deepcopy(cfg['parameters'][0]))
 elif mutation=='field_reserved':cfg['parameters'][0]['name']='__is_success'
 elif mutation=='legacy_bool':cfg['parameters'][0]['type']='bool'
 elif mutation=='no_required':cfg['parameters'][0].pop('required')
 elif mutation=='function_call':cfg['reasoning_mode']='function_call'
 elif mutation=='vision':cfg['vision']={'enabled':True}
 elif mutation=='dynamic':cfg['parameters'][0]['description']='{{#sys.query#}}'
 else:cfg['query']=['extract','order_no']
 result=validate_plan(task,p);assert not result['valid'] and result['errors']

def test_reason_is_nullable_and_usage_is_object_not_a_business_parameter(client):
 task=approved(client);p=plan();node=p['nodes'][1]
 assert resolve({'extract':node},['extract','__reason']) is None and resolve({'extract':node},['extract','__usage'])=='object'
 assert validate_plan(task,p)['valid']
