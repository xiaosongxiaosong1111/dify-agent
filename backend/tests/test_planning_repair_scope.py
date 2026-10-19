import ast,copy,json
import pytest
from test_planning import plan,run,USAGE
from test_iteration import batch_plan,iteration
from app.planning import preserves_scope
from app.planning import normalize_draft,_missing_header_colon

@pytest.mark.parametrize('before,after',[
 ('def main(query):\n    return {"result": helper(query)}\n','def main(query):\n    return {"result": helper[query]}\n'),
 ('def main(query):\n    if query:\n        result = helper(query)\n    return {"result": result}\n','def main(query):\n    if query:\n        result = helper(query)\n        return {"result": result}\n'),
 ('def main(query):\n    return {"result": query}\n','def main(query):\n    return {"result": (query,)}\n'),
 ('def main(query):\n    return {"result": query[1:2]}\n','def main(query):\n    return {"result": query[1,2]}\n'),
])
def test_punctuation_and_indentation_cannot_change_code_semantics(before,after):
 assert not preserves_scope(plan(before),plan(after))

def test_missing_header_colon_does_not_allow_another_body_edit():
 before=plan('def main(query)\n    return {"result": helper(query)}\n')
 assert not preserves_scope(before,plan('def main(query):\n    return {"result": helper[query]}\n'))

def test_missing_header_colon_does_not_allow_indent_scope_movement():
 before=plan('def main(query)\n    if query:\n        result = helper(query)\n    return {"result": result}\n')
 after=plan('def main(query):\n    if query:\n        result = helper(query)\n        return {"result": result}\n')
 assert not preserves_scope(before,after)

@pytest.mark.parametrize('scope',['root','iteration','loop'])
def test_repair_cannot_reorder_nodes_even_when_ids_and_configs_are_same(scope):
 if scope=='root':before=plan();after=copy.deepcopy(before);after['nodes'].reverse()
 else:
  before=batch_plan();container=before['nodes'][2]
  if scope=='loop':container['type']='loop'
  child=copy.deepcopy(iteration(before)['nodes'][0]);child['id']='second';iteration(before)['nodes'].append(child)
  after=copy.deepcopy(before);iteration(after)['nodes'].reverse()
 assert not preserves_scope(before,after)

@pytest.mark.parametrize('change',['title','extra_node','extra_root','schema'])
def test_repair_preserves_node_annotations_and_top_level_choices(change):
 before=plan('def main(query)\n    return {"result": query}\n');after=plan('def main(query):\n    return {"result": query}\n')
 if change=='title':before['nodes'][1]['title']='客户确认名称';after['nodes'][1]['title']='其他名称'
 elif change=='extra_node':after['nodes'][1]['business_choice']='different'
 elif change=='extra_root':after['business_choice']='different'
 else:after['schema_version']=2
 assert not preserves_scope(before,after)

def test_unchanged_javascript_sibling_does_not_block_python_colon_repair():
 before=plan('def main(query)\n    return {"result": query}\n');after=plan('def main(query):\n    return {"result": query}\n')
 js={'id':'js','type':'code','config':{'code_language':'javascript','code':'function main(){ return {result:"kept"} }','outputs':{'result':{'type':'string'}}}}
 before['nodes'].append(copy.deepcopy(js));after['nodes'].append(copy.deepcopy(js))
 assert preserves_scope(before,after)
 after['nodes'][-1]['config']['code']='function main(){ return {result:"changed"} }'
 assert not preserves_scope(before,after)

def test_comments_remain_exact_during_automatic_repair():
 before=plan('def main(query)\n    # 已确认：先清理问题，不改资料范围\n    return {"result": query}\n')
 after=plan('def main(query):\n    # 已确认：先清理问题，不改资料范围\n    return {"result": query}\n')
 assert preserves_scope(before,after)
 after['nodes'][1]['config']['code']=after['nodes'][1]['config']['code'].replace('不改资料范围','改用其他资料')
 assert not preserves_scope(before,after)

def test_valid_ast_neutral_whitespace_is_preserved_without_execution():
 before=plan('def main(query):\n    return {"result": query}\n')
 after=plan('def main( query ):\n  return { "result" : query }\n\n')
 assert preserves_scope(before,after)

@pytest.mark.parametrize('code',[
 'def main(query):\n    return {"result": query "other": query}\n',
 'def main(query):\n    return helper(\n',
 'def main(query):\nreturn {"result": query}\n',
])
def test_ambiguous_syntax_errors_pause_before_paying_for_a_repair(code):
 def validate(candidate):
  try:ast.parse(candidate['nodes'][1]['config']['code'])
  except SyntaxError:return {'valid':False,'errors':['Python 代码语法错误']}
  return {'valid':True,'errors':[]}
 result,op,calls,error=run([(json.dumps(plan(code)),USAGE)],validate=validate)
 assert result is None and error=='needs_decision' and len(calls)==1
 assert op['last_candidate']['nodes'][1]['config']['code']==code

def test_local_colon_fix_does_not_request_or_adopt_another_model_body_change():
 before=plan('def main(query)\n    return {"result": helper(query)}\n');changed=plan('def main(query):\n    return {"result": helper[query]}\n')
 def validate(candidate):
  try:ast.parse(candidate['nodes'][1]['config']['code'])
  except SyntaxError:return {'valid':False,'errors':['Python 代码语法错误']}
  return {'valid':True,'errors':[]}
 result,op,calls,error=run([(json.dumps(before),USAGE),(json.dumps(changed),USAGE)],validate=validate)
 assert result is not None and error is None and len(calls)==1
 assert result['nodes'][1]['config']['code']=='def main(query):\n    return {"result": helper(query)}\n'

@pytest.mark.parametrize('code',[
 'def main(query)\n    return {"result": query}\n',
 'def main(query)  # 保留客户说明\n    return {"result": query}\n',
 'def main(query):\n    if query\n        return {"result": query}\n    return {"result": "empty"}\n',
 'def main(query):\n    for item in query\n        pass\n    return {"result": query}\n',
 'def main(\n    query\n)\n    return {"result": query}\n',
 'def main(query)\r\n    return {"result": query}\r\n',
])
def test_single_missing_header_colon_is_fixed_locally_with_exact_scope(code):
 fixed=_missing_header_colon(code);assert fixed is not None
 ast.parse(fixed);assert preserves_scope(plan(code),plan(fixed))
 assert len(fixed)==len(code)+1
 before=plan(code);original=copy.deepcopy(before);candidate,notes=normalize_draft(before)
 assert before==original and candidate['nodes'][1]['config']['code']==fixed and any('未追加模型调用' in note for note in notes)

def test_more_than_one_syntax_change_is_not_locally_fixed_or_retried():
 code='def main(query)\n    if query\n        return {"result": query}\n    return {"result": ""}\n'
 assert _missing_header_colon(code) is None
 def validate(candidate):return {'valid':False,'errors':['Python 代码语法错误']}
 result,op,calls,error=run([(json.dumps(plan(code)),USAGE)],validate=validate)
 assert result is None and error=='needs_decision' and len(calls)==1 and op['last_candidate']['nodes'][1]['config']['code']==code

def test_zero_automatic_fix_limit_keeps_candidate_without_local_change_or_extra_call():
 code='def main(query)\n    return {"result": query}\n'
 def validate(candidate):
  try:ast.parse(candidate['nodes'][1]['config']['code'])
  except SyntaxError:return {'valid':False,'errors':['Python 代码语法错误']}
  return {'valid':True,'errors':[]}
 result,op,calls,error=run([(json.dumps(plan(code)),USAGE)],settings={'max_retries':0,'max_minutes':1,'max_cost_usd':1},validate=validate)
 assert result is None and error=='retry_limit' and len(calls)==1 and op['last_candidate']['nodes'][1]['config']['code']==code

def test_container_local_fix_keeps_every_policy_and_output_binding():
 before=batch_plan();cfg=iteration(before);cfg['nodes'][0]['config']['code']=cfg['nodes'][0]['config']['code'].replace(') -> dict:',') -> dict',1)
 original=copy.deepcopy(before);candidate,notes=normalize_draft(before)
 assert preserves_scope(before,candidate) and before==original
 assert {k:v for k,v in iteration(candidate).items() if k!='nodes'}=={k:v for k,v in cfg.items() if k!='nodes'}
 assert any('未追加模型调用' in note for note in notes)
