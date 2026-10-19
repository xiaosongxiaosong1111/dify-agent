import copy
import pytest
import yaml
from test_retrieval_settings import plan,task
from test_api import client
from test_run_diagnostics import recorded,mock_reader,trace,diagnose
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.retrieval_settings import preserved
from app.run_diagnostics import classify

def upstream(p,kind):
 p['nodes'].insert(1,{'id':'source','type':'code','config':{'code_language':'python3','code':'def main() -> dict:\n    return {"value": "technical check only"}\n','variables':[],'outputs':{'value':{'type':kind}}}})
 p['edges']=[{'source':'start','target':'source'},{'source':'source','target':'retrieve'},{'source':'retrieve','target':'end'}]
 p['nodes'][2]['config']['query_variable_selector']=['source','value']
 return p

@pytest.mark.parametrize('kind',['number','boolean','object','array[string]','array[object]'])
def test_declared_non_text_query_is_refused_before_generating_dsl(kind):
 p=upstream(plan(),kind);text,result=compile_workflow_plan(task(p))
 assert not text and not result['valid'] and any('问题来源已声明为非文字类型' in e for e in result['errors'])

def test_explicit_text_query_keeps_native_selector_and_source_plan():
 p=upstream(plan(),'string');before=copy.deepcopy(p);text,result=compile_workflow_plan(task(p));assert result['valid'],result['errors']
 node=next(n for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='retrieve')
 assert node['data']['query_variable_selector']==['source','value'] and p==before

def test_custom_start_input_requires_explicit_selection_not_fabricated_query():
 p=plan();p['nodes'][0]['config']['variables'][0]['variable']='question';p['nodes'][1]['config'].pop('query_variable_selector')
 assert not validate_plan(task(p),p)['valid']
 p['nodes'][1]['config']['query_variable_selector']=['start','question']
 assert validate_plan(task(p),p)['valid']

def test_chatflow_default_question_is_sys_query():
 p=plan();p['nodes'][0]['config']['variables']=[];p['nodes'][1]['config'].pop('query_variable_selector');p['nodes'][-1]={'id':'answer','type':'answer','config':{'answer':'{{#retrieve.result#}}'}};p['edges'][-1]['target']='answer'
 text,result=compile_workflow_plan({**task(p),'app_type':'advanced-chat'});assert result['valid'],result['errors']
 node=next(n for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='retrieve')
 assert node['data']['query_variable_selector']==['sys','query']

def test_rag_results_cannot_be_another_nodes_query():
 p=plan();second=copy.deepcopy(p['nodes'][1]);second['id']='retrieve_again';second['config']['query_variable_selector']=['retrieve','result'];p['nodes'].insert(2,second);p['edges']=[{'source':'start','target':'retrieve'},{'source':'retrieve','target':'retrieve_again'},{'source':'retrieve_again','target':'end'}]
 result=validate_plan(task(p),p);assert not result['valid'] and any('非文字类型' in e for e in result['errors'])

@pytest.mark.parametrize('selector',[None,[],'',['start'],['start',''],['start',1]])
def test_native_no_query_or_unsupported_shape_is_not_ir_default_inheritance(selector):
 p=plan();text,result=compile_workflow_plan(task(p));assert result['valid']
 data=next(n for n in yaml.safe_load(text)['workflow']['graph']['nodes'] if n['id']=='retrieve')['data'];data['query_variable_selector']=selector
 with pytest.raises(ValueError,match='不能把它当作计划继承默认输入'):preserved(data)
 assert data['query_variable_selector']==selector

def test_native_query_type_diagnostic_is_scoped_to_retrieval():
 error='Query variable is not string type.'
 assert classify(error,'knowledge-retrieval')['category']=='retrieval_query_type'
 assert classify(error,'code')['category']=='unclassified' and classify(error)['category']=='unclassified'

def test_query_type_diagnostic_locates_node_without_modification_or_rerun(client,monkeypatch):
 t,r=recorded(client);before=copy.deepcopy(r);nodes=trace('Query variable is not string type.');nodes['data'][0].update(node_id='retrieve',node_type='knowledge-retrieval')
 calls=mock_reader(monkeypatch,nodes=nodes);report=diagnose(client,t,True).json()
 assert report['findings'][0]['category']=='retrieval_query_type' and report['findings'][0]['node_id']=='retrieve'
 assert '不会自动重跑' in report['findings'][0]['recommendation']
 from app import main
 saved=main.get_task(t['id']);assert {k:v for k,v in saved['runs'][-1].items() if k!='diagnostics'}==before
 assert len(calls)==2 and all(method=='GET' for method,_,_ in calls)
