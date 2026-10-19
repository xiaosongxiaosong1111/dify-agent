import copy
import pytest,yaml
from test_api import client,approved
from app import main
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.model_parameters import needs_task_model
from app.declared_types import resolve

def plan(mode='workflow'):
 return {'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'text-input','required':True}] if mode=='workflow' else []}},{'id':'route','type':'question-classifier','title':'客户诉求分类','config':{'classes':[{'id':'other','name':'不明确或不属于购买咨询的问题','label':'其他／追问'},{'id':'sales','name':'明确咨询购买、产品或价格的问题','label':'售前'}],'query_variable_selector':['start','query'] if mode=='workflow' else ['sys','query'],'instruction':'先区分类别，不明确则选other。','unmatched_policy':{'behavior':'first_class','class_id':'other'}}},{'id':'other_reply','type':'template-transform','config':{'template':'请补充您的具体需求。','variables':[]}},{'id':'sales_reply','type':'template-transform','config':{'template':'购买咨询。','variables':[]}},{'id':'end','type':'end' if mode=='workflow' else 'answer','config':{'outputs':[{'variable':'route','value_selector':['route','class_id']}]} if mode=='workflow' else {'answer':'分类：{{#route.class_label#}}'}}], 'edges':[{'source':'start','target':'route'},{'source':'route','source_handle':'other','target':'other_reply'},{'source':'route','source_handle':'sales','target':'sales_reply'},{'source':'other_reply','target':'end'},{'source':'sales_reply','target':'end'}]}

@pytest.mark.parametrize('mode',['workflow','advanced-chat'])
def test_classifier_compiles_native_model_classes_handles_and_outputs(client,mode):
 task=approved(client,app_type=mode);graph=plan(mode);response=validate_plan(task,graph);assert response['valid'],response
 task['workflow_plan']=graph;content,_=compile_workflow_plan(task);doc=yaml.safe_load(content);node=next(n for n in doc['workflow']['graph']['nodes'] if n['id']=='route')
 assert node['data']['type']=='question-classifier' and node['data']['classes']==graph['nodes'][1]['config']['classes']
 assert node['data']['model']['provider']==task['configuration']['dify_model_provider'] and not node['data']['vision']['enabled']
 assert {e['sourceHandle'] for e in doc['workflow']['graph']['edges'] if e['source']=='route'}=={'other','sales'}
 assert 'unmatched_policy' not in node['data'] and any('classes 第一项' in w for w in response['warnings'])
 assert needs_task_model(graph) and resolve({'route':graph['nodes'][1]},['route','class_label'])=='string'

@pytest.mark.parametrize('mutation',['missing_policy','wrong_fallback','error_fallback','duplicate_id','duplicate_name','confidence','file','bad_query','unknown_branch','missing_branch','default_handle','dynamic_class'])
def test_unconfirmed_or_unsupported_routing_choices_are_refused(client,mutation):
 task=approved(client);graph=plan();cfg=graph['nodes'][1]['config']
 if mutation=='missing_policy':cfg.pop('unmatched_policy')
 elif mutation=='wrong_fallback':cfg['unmatched_policy']['class_id']='sales'
 elif mutation=='error_fallback':cfg['unmatched_policy']['behavior']='error'
 elif mutation=='duplicate_id':cfg['classes'][1]['id']='other'
 elif mutation=='duplicate_name':cfg['classes'][1]['name']=cfg['classes'][0]['name']
 elif mutation=='confidence':cfg['confidence_threshold']=.8
 elif mutation=='file':cfg['vision']={'enabled':True}
 elif mutation=='bad_query':cfg['query_variable_selector']=['route','class_name']
 elif mutation=='unknown_branch':graph['edges'][1]['source_handle']='false'
 elif mutation=='missing_branch':graph['edges'].pop(1)
 elif mutation=='default_handle':graph['edges'][1].pop('source_handle')
 else:cfg['classes'][0]['name']='{{#sys.query#}}'
 result=validate_plan(task,graph);assert not result['valid'] and result['errors']

def test_classifier_camelcase_explicit_handle_and_independent_model_are_preserved(client):
 task=approved(client);graph=plan();cfg=graph['nodes'][1]['config'];cfg['model']={'provider':'test/provider','name':'test-model','mode':'chat','completion_params':{'temperature':0,'max_tokens':512}}
 for edge in graph['edges']:
  if edge['source']=='route':edge['sourceHandle']=edge.pop('source_handle')
 result=validate_plan(task,graph);assert result['valid'],result
 assert not needs_task_model(graph);task['workflow_plan']=graph;content,_=compile_workflow_plan(task)
 native=next(n for n in yaml.safe_load(content)['workflow']['graph']['nodes'] if n['id']=='route');assert native['data']['model']==cfg['model']

def test_classifier_inherited_model_missing_is_explicit_pending_dependency(client):
 task=approved(client);graph=plan();task['configuration']['dify_model_provider']='';task['configuration']['dify_model']=''
 result=validate_plan(task,graph);assert result['valid'] and needs_task_model(graph)
 assert any('尚未配置真实' in warning for warning in result['warnings'])
