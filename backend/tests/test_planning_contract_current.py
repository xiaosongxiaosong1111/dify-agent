"""Exercise the actual model input and its published examples without data egress."""
import json
import re
from pathlib import Path

import pytest

from test_api import client, approved, planning_provider
from test_iteration import batch_plan
from app import main
from app.workflow_plan import validate_plan, compile_workflow_plan
from app.loop import FIELDS


CONTRACT = Path(__file__).resolve().parents[2] / 'docs/workflow-plan-contract.md'


def examples():
    return [json.loads(value) for value in re.findall(r'```json\s*(.*?)```', CONTRACT.read_text(encoding='utf-8'), re.S)]


def loop_example(values):
    matches=[(plan,node) for plan in values for node in plan.get('nodes',[]) if node.get('type')=='loop']
    assert len(matches)==1, '当前循环示例须唯一，不能依赖无关JSON块的位置。'
    return matches[0]


@pytest.mark.parametrize('example', examples())
def test_actual_planning_contract_examples_compile_without_model_or_code_execution(example):
    if 'nodes' in example and 'schema_version' in example:
        plan = example
    else:
        plan = batch_plan()
        plan['nodes'][2] = example
    task = {'app_type': 'workflow', 'configuration': {'dify_model_provider': 'test/provider', 'dify_model': 'test-model'}, 'workflow_plan': plan}
    check = validate_plan(task, plan)
    assert check['valid'], check['errors']
    content, check = compile_workflow_plan(task)
    assert check['valid'] and content


def test_generation_receives_complete_current_loop_contract_and_retains_confirmation_gate(client, monkeypatch):
    planning_provider(client)
    task = approved(client)
    loop_plan, _ = loop_example(examples())
    calls = []

    async def controlled_call(provider, key, messages, **kwargs):
        calls.append(messages)
        prompt = messages[0]['content']
        # The exact sent message, not a separately loaded developer document.
        assert 'Loops are unsupported' not in prompt
        assert 'classifier inside containers are not adapted yet' not in prompt
        assert 'Iteration-containing DSL is **not yet supported**' not in prompt
        assert 'Nested/HTTP/retrieval/human/parallel-body remain unsupported' not in prompt
        sent = [json.loads(value) for value in re.findall(r'```json\s*(.*?)```', prompt, re.S)]
        _, node = loop_example(sent)
        cfg = node['config']
        assert set(cfg) == FIELDS
        assert cfg['progress_variables'] == ['count']
        assert cfg['no_progress_limit'] == 2
        assert 'repeated_read_policy={read_only:true' in prompt
        assert 'parameter-extractor' in prompt and 'explicit body DAG' in prompt
        return json.dumps(loop_plan), {'prompt_tokens': 80, 'completion_tokens': 30}

    monkeypatch.setattr(main, 'call_model', controlled_call)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={'revision': task['revision']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(calls) == 1
    assert result['workflow_plan'] == loop_plan
    assert result['plan_source'] == 'model' and not result['configuration_confirmed']
    assert not result['artifact'] and not result['runs'] and not result.get('dify_app_id')
