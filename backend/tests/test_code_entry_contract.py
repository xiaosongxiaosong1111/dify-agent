import copy
import pytest
from test_api import client,approved,forbid_api_external_calls
from test_planning import plan as base_plan
from app import main
from app.workflow_plan import validate_plan


def candidate(code,variables=('query',)):
    plan=base_plan();cfg=plan['nodes'][1]['config'];cfg['code']=code
    cfg['variables']=[{'variable':name,'value_selector':['start','query']} for name in variables]
    return plan


@pytest.mark.parametrize('code,variables',[
    ("def helper(query):\n return {'result':query}",('query',)),
    ("def main(other):\n return {'result':other}",('query',)),
    ("def main(query, required):\n return {'result':query}",('query',)),
    ("def main(query, /):\n return {'result':query}",('query',)),
    ("async def main(query):\n return {'result':query}",('query',)),
    ("def main(query):\n return {'result':query}",('query','query')),
    ("def main(*, query):\n return {'result':query}",()),
    ("def main(query='default', /):\n return {'result':query}",('query',)),
    ("def main(query, query):\n return {'result':query}",('query',)),
])
def test_definite_entry_binding_errors_are_rejected_before_execution(client,code,variables):
    task=approved(client);plan=candidate(code,variables);checked=validate_plan(task,plan)
    assert not checked['valid'] and any('入口' in error or '重复' in error for error in checked['errors'])


@pytest.mark.parametrize('code,variables',[
    ("def main(query):\n return {'result':query}",('query',)),
    ("def main(query='fallback'):\n return {'result':query}",()),
    ("def main(*, query):\n return {'result':query}",('query',)),
    ("def main(query, *, optional=None):\n return {'result':query}",('query',)),
    ("def main(**values):\n return {'result':values['query']}",('query',)),
    ("def main(*args, **values):\n return {'result':values['query']}",('query',)),
    ("def main(only_position='fallback', /, **values):\n return {'result':values['query']}",('query',)),
    ("def main(query: str = missing_default()) -> unknown_return:\n return {'result':query}",('query',)),
])
def test_supported_signature_binding_does_not_evaluate_annotations_defaults_or_body(client,code,variables):
    task=approved(client);result=validate_plan(task,candidate(code,variables))
    assert result['valid'],result['errors']
    assert any('本机未执行代码' in warning for warning in result['warnings'])


@pytest.mark.parametrize('code',[
    "@custom_wrapper\ndef main(query):\n return {'result':query}",
    "def main(query):\n return {'result':query}\nmain = custom_callable",
    "if condition:\n def main(query):\n  return {'result':query}",
    "from custom_module import main",
    "def main(query):\n return {'result':query}\nfrom custom_module import *",
])
def test_dynamic_entry_is_unverified_instead_of_guessed_or_executed(client,code):
    task=approved(client);result=validate_plan(task,candidate(code))
    assert result['valid'],result['errors']
    assert any('入口' in warning and '未核实' in warning for warning in result['warnings'])


def test_bad_entry_api_does_not_save_rewrite_or_execute_task(client):
    task=approved(client);before=copy.deepcopy(task)
    response=client.post(f"/api/tasks/{task['id']}/plan",json={'revision':task['revision'],'plan':candidate("def main(other):\n return {'result':other}")})
    assert response.status_code==422,response.text
    assert main.get_task(task['id'])==before and not main.store.list('planning_operation')


def test_nested_iteration_uses_the_same_entry_check(client):
    from test_iteration import batch_plan
    task=approved(client);plan=batch_plan();body=plan['nodes'][2]['config']['nodes'][0]
    body['config']['code']="def main(other):\n return {'result':other}"
    checked=validate_plan(task,plan)
    assert not checked['valid'] and any('入口' in error for error in checked['errors'])


def test_preserved_native_code_cannot_bypass_binding_check(client):
    import yaml
    from app.workflow_plan import compile_workflow_plan
    from app.dsl_roundtrip import validate_preserved
    task=approved(client);task['workflow_plan']=candidate("def main(query):\n return {'result':query}")
    original,_=compile_workflow_plan(task);root=yaml.safe_load(original)
    code=next(n for n in root['workflow']['graph']['nodes'] if n['data']['type']=='code')
    code['data']['code']="def main(other):\n return {'result':other}"
    checked=validate_preserved(root)
    assert not checked['valid'] and any('入口' in error for error in checked['errors'])
