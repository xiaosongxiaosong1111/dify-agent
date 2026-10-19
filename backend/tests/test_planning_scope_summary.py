import copy
import pytest
from test_planning import plan
from test_iteration import batch_plan,iteration
from app.planning_scope_summary import summarize

def test_rejected_code_change_summary_has_no_raw_code_or_values():
 before=plan('def main(q):\n    return {"result": "opaque-private-value"}\n');after=copy.deepcopy(before);after['nodes'][1]['config']['code']='def main(q):\n    return q["secret"]\n'
 result=summarize(before,after);assert result['nodes'] and '代码内容变化' in result['nodes'][0]['areas'][0]
 assert 'opaque-private-value' not in str(result) and 'def main' not in str(result) and 'q[' not in str(result)

@pytest.mark.parametrize('change',['order','number','attrs','config','root'])
def test_summary_identifies_scope_areas_without_echoing_identifiers(change):
 before=plan();after=copy.deepcopy(before)
 if change=='order':after['nodes'].reverse()
 elif change=='number':after['nodes'].pop()
 elif change=='attrs':after['nodes'][1]['title']='private-name-not-for-summary'
 elif change=='config':after['nodes'][1]['config']['provider']='private-provider-value'
 else:after['customer_secret_choice']='private-customer-value'
 result=summarize(before,after);assert result['areas'] or result['nodes']
 assert 'private-name' not in str(result) and 'private-provider' not in str(result) and 'private-customer' not in str(result)

def test_nested_scope_summary_uses_position_only():
 before=batch_plan();after=copy.deepcopy(before);iteration(after)['nodes'][0]['config']['code']+='\n# changed scope\n'
 result=summarize(before,after);assert any('内部' in node['position'] for node in result['nodes'])
 assert 'changed scope' not in str(result)

def test_large_changed_graph_is_marked_incomplete_not_silent_empty():
 before={'nodes':[{'id':str(i),'type':'code','config':{'code':'first'}} for i in range(200)],'edges':[]};after=copy.deepcopy(before)
 for node in after['nodes']:node['config']['code']='second'
 result=summarize(before,after);assert result['truncated'] and len(result['nodes'])==100

@pytest.mark.parametrize('before,after',[(None,{}),({},None),({'nodes':None},{'nodes':[]})])
def test_untrusted_structure_returns_uncertain_summary(before,after):
 result=summarize(before,after);assert result['areas']

def test_overdeep_or_cyclic_candidate_is_not_recursed_or_dumped():
 value={'nodes':[]};value['recursive']=value
 result=summarize(value,{});assert result['truncated'] and result['areas'] and not result['nodes']

def test_summary_itself_does_not_change_candidates_or_imply_approval():
 before=plan();after=copy.deepcopy(before);after['nodes'][1]['title']='new';snapshot=copy.deepcopy(after)
 result=summarize(before,after);assert after==snapshot and result['verification']=='rejected_repair_summary' and '不替代' in result['note']

def test_nested_report_and_parent_share_one_cap():
 before={'nodes':[{'id':'container','type':'iteration','config':{'code':'old','nodes':[{'id':str(i),'config':{'code':'old'}} for i in range(100)]}}]}
 after=copy.deepcopy(before);after['nodes'][0]['config']['code']='new'
 for node in after['nodes'][0]['config']['nodes']:node['config']['code']='new'
 result=summarize(before,after)
 assert len(result['nodes'])==100 and result['truncated']

def test_rejected_candidate_summary_is_checkpointed_before_stop(monkeypatch):
 # Disable the local normalizer to exercise the defensive scope boundary:
 # a future repairer must not bypass it or hide its rejection explanation.
 import app.planning as planning
 from test_planning import run,USAGE
 import json,ast
 monkeypatch.setattr(planning,'normalize_draft',lambda candidate,**kwargs:(candidate,[]))
 before=plan('def main(query)\n    return {"result": query}\n')
 after=plan('def main(query):\n    return {"result": query["private-value"]}\n')
 checkpoints=[]
 original=planning.draft_plan
 async def capture(*args,**kwargs):
  arguments=list(args);checkpoint=arguments[7]
  def save():checkpoints.append(copy.deepcopy(arguments[4]));checkpoint()
  arguments[7]=save
  return await original(*arguments,**kwargs)
 monkeypatch.setattr(planning,'draft_plan',capture)
 # test_planning imports draft_plan directly, so bind its invocation as well.
 import test_planning
 monkeypatch.setattr(test_planning,'draft_plan',capture)
 def validate(candidate):
  try:ast.parse(candidate['nodes'][1]['config']['code'])
  except SyntaxError:return {'valid':False,'errors':['Python 代码语法错误']}
  return {'valid':True,'errors':[]}
 result,operation,calls,error=run([(json.dumps(before),USAGE),(json.dumps(after),USAGE)],validate=validate)
 assert result is None and error=='scope_change' and len(calls)==2
 assert checkpoints[-1]['status']=='paused' and checkpoints[-1]['scope_change_summary']==operation['scope_change_summary']
 assert operation['last_candidate']==after and 'private-value' not in str(operation['scope_change_summary'])
