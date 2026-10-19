import copy,yaml
import pytest
from test_iteration_branches import branch_plan as iteration_plan
from test_loop_body_graph import branch_plan as loop_plan
from test_preserved_loop import review
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest
from app.conversation import memory_configuration

def plan(owner='iteration'):
 p=iteration_plan() if owner=='iteration' else loop_plan();container=next(n for n in p['nodes'] if n['type']==owner);cfg=container['config'];route=cfg['nodes'][0];qid=route['id']
 if owner=='loop':p['nodes'][0]['config']['variables']=[{'variable':'query','type':'text-input','required':True}]
 query=[container['id'],'item'] if owner=='iteration' else ['start','query']
 route.update(type='question-classifier',config={'classes':[{'id':'a','name':'主要路线'},{'id':'b','name':'其他路线'}],'query_variable_selector':query,'instruction':'按明确类别判断，不忽略分支。','unmatched_policy':{'behavior':'first_class','class_id':'a'}})
 for edge in cfg['edges']:
  if edge['source']==qid:edge['source_handle']='b' if edge['source_handle']=='false' else 'a'
 return p,container,route

def task(p,mode='workflow'):return {'app_type':mode,'workflow_plan':p,'configuration':{'dify_model_provider':'mock/provider','dify_model':'mock-model','conversation_memory':mode=='advanced-chat','memory_turns':3}}

@pytest.mark.parametrize('owner,mode',[('iteration','workflow'),('iteration','advanced-chat'),('loop','workflow'),('loop','advanced-chat')])
def test_container_classification_preserves_branches_scope_models_and_no_history(owner,mode):
 p,container,route=plan(owner)
 if mode=='advanced-chat':
  p['nodes'][-1].update(type='answer',config={'answer':'完成处理'});p['nodes'][0]['config']['variables']=[]
  if owner=='loop':route['config']['query_variable_selector']=['sys','query']
  else:p['nodes'][1]['config']['variables'][0]['value_selector']=['sys','query']
 before=copy.deepcopy(p);text,result=compile_workflow_plan(task(p,mode));assert result['valid'],result
 root=yaml.safe_load(text);raw=next(n for n in root['workflow']['graph']['nodes'] if n['id']==route['id']);data=raw['data']
 assert raw['parentId']==container['id'] and data['query_variable_selector']==route['config']['query_variable_selector'] and 'memory' not in data
 assert data['model']['name']=='mock-model' and data['classes']==route['config']['classes']
 assert len([e for e in root['workflow']['graph']['edges'] if e['source']==route['id'] and e['sourceHandle'] in {'a','b'}])==2 and p==before
 refs=review(root) if owner=='loop' else None;checked=validate_preserved(root,loop_reviews=refs);assert checked['valid'],checked
 data['classes'][0]['name']='手动修改主要类';data['instruction']='实际规则保留';raw['position']['x']+=13;original=digest(root)
 assert validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None)['valid'] and digest(root)==original
 data['memory']=memory_configuration('advanced-chat',{'conversation_memory':True,'memory_turns':3})
 assert not validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None)['valid']

@pytest.mark.parametrize('owner,mutation',[('iteration','missing_branch'),('loop','missing_branch'),('iteration','sibling_input'),('loop','number_input'),('iteration','leaked_item'),('loop','memory'),('iteration','sequential'),('loop','sequential')])
def test_container_classification_does_not_guess_missing_branches_or_cross_scope(owner,mutation):
 p,container,route=plan(owner);cfg=container['config']
 if mutation=='missing_branch':cfg['edges']=[e for e in cfg['edges'] if not (e['source']==route['id'] and e['source_handle']=='b')]
 elif mutation=='sibling_input':route['config']['query_variable_selector']=['empty_item','output']
 elif mutation=='number_input':route['config']['query_variable_selector']=[container['id'],'count']
 elif mutation=='leaked_item':p['nodes'][-1]['config']['outputs'][0]['value_selector']=[route['id'],'class_id']
 elif mutation=='memory':route['config']['memory']={'enabled':True}
 else:cfg.pop('edges');cfg.pop('entry_node_id')
 result=validate_plan(task(p),p);assert not result['valid'] and result['errors']

def test_parallel_container_classification_still_requires_independence_and_declared_count():
 p,container,_=plan();container['config'].update(is_parallel=True,parallel_nums=3,parallel_safe=True,parallel_reason='每项分类只读取本项输入，各分支不共享状态，费用按逐项调用估算。')
 assert validate_plan(task(p),p)['valid']
 container['config']['parallel_safe']=False;assert not validate_plan(task(p),p)['valid']
