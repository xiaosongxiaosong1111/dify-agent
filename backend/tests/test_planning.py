import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.planning import draft_plan, PlanningStopped, normalize_draft, preserves_scope, usage_cost, validate_pricing
from app.providers import ProviderError

RATES = {"input_per_million_usd": 1, "output_per_million_usd": 2, "cached_input_per_million_usd": .1}
USAGE = {"prompt_tokens": 100, "completion_tokens": 20}


def plan(code="def main(query):\n    return {'result': query.strip()}\n"):
    return {"schema_version": 1, "nodes": [
        {"id": "start", "type": "start", "config": {"variables": [{"variable": "query", "type": "text-input", "required": True}]}},
        {"id": "code", "type": "code", "config": {"code_language": "python3", "code": code, "variables": [{"variable":"query","value_selector":["start","query"]}], "outputs": {"result": {"type": "string"}}}},
        {"id": "end", "type": "end", "config": {"outputs": [{"variable": "result", "value_selector": ["code", "result"]}]}},
    ], "edges": [{"source": "start", "target": "code"}, {"source": "code", "target": "end"}]}


def run(responses, *, rates=RATES, settings=None, validate=None, guard=None, clock=None):
    operation = {"status": "running", "attempts": []}
    calls, checkpoints = [], []
    async def invoke(messages, timeout):
        calls.append({"messages": copy.deepcopy(messages), "timeout": timeout})
        result = responses[len(calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result
    async def execute():
        return await draft_plan({}, {"pricing": rates}, [{"role": "user", "content": "返回 JSON 计划"}],
            settings or {"max_retries": 3, "max_minutes": 1, "max_cost_usd": 1}, operation, invoke,
            validate or (lambda candidate: {"valid": True, "errors": []}),
            lambda: checkpoints.append(copy.deepcopy(operation)), guard or (lambda: None),
            **({"clock": clock} if clock else {}))
    try:
        result = asyncio.run(execute())
        return result, operation, calls, None
    except PlanningStopped as e:
        return None, operation, calls, e.reason


def test_valid_first_result_has_no_extra_call():
    result, op, calls, error = run([(json.dumps(plan()), USAGE)])
    assert result and not error and len(calls) == 1
    assert op["attempts"][0]["cost_basis"] == "reported_usage"


def test_invalid_json_repaired_once():
    result, op, calls, error = run([('{"nodes":', USAGE), (json.dumps(plan()), USAGE)])
    assert result and not error and len(calls) == 2
    assert "只修复" in calls[-1]["messages"][-1]["content"]
    assert op["attempts"][0]["status"] == "invalid"


def test_repeated_identical_problem_stops_before_third_call():
    result, op, calls, error = run([('bad-json', USAGE), ('also-bad-json', USAGE)])
    assert result is None and error == "no_progress" and len(calls) == 2
    assert op["last_response_excerpt"] == 'also-bad-json'


def test_zero_repair_limit_does_not_retry():
    result, op, calls, error = run([('bad-json', USAGE)], settings={"max_retries": 0, "max_minutes": 1, "max_cost_usd": 1})
    assert result is None and error == "retry_limit" and len(calls) == 1


def test_fee_precheck_prevents_first_call():
    result, op, calls, error = run([], settings={"max_retries": 3, "max_minutes": 1, "max_cost_usd": .001})
    assert error == "cost_limit" and not calls and not op["attempts"]


def test_unknown_price_prevents_paid_call():
    assert run([], rates=None)[-1] == "pricing_unknown"


def test_unknown_usage_does_not_trigger_blind_retry():
    result, op, calls, error = run([('bad-json', {})])
    assert error == "usage_unknown" and len(calls) == 1
    assert op["estimated_cost_usd"] > 0 and op["attempts"][0]["usage"] == {}


def test_provider_error_does_not_retry_and_keeps_reservation():
    result, op, calls, error = run([ProviderError("模型请求失败（HTTP 401）。")])
    assert error == "provider_error" and len(calls) == 1
    assert op["attempts"][0]["status"] == "unknown_usage"


def test_explicit_missing_resource_does_not_choose_alternative():
    assert run([(json.dumps({"error": "缺少知识库 ID"}), USAGE)])[-1] == "needs_decision"


def test_unsafe_graph_repair_is_not_automatic():
    result, op, calls, error = run([(json.dumps(plan()), USAGE)], validate=lambda _: {"valid": False, "errors": ["if-else 缺少 false 出口"]})
    assert error == "needs_decision" and len(calls) == 1
    assert op["last_candidate"]["nodes"]


def test_certain_metadata_corrections_are_visible():
    candidate = plan()
    del candidate["schema_version"]
    candidate["nodes"][0]["config"]["variables"][0]["required"] = "false"
    candidate["nodes"][1]["config"]["code_language"] = "python"
    fixed, changes = normalize_draft(candidate)
    assert len(changes) == 3 and fixed["schema_version"] == 1
    assert fixed["nodes"][0]["config"]["variables"][0]["required"] is False
    assert candidate["nodes"][1]["config"]["code_language"] == "python"


def test_code_repair_preserves_literals_bindings_and_topology():
    before = plan("def main(query)\n    return {'result': query.strip()}\n")
    after = plan()
    assert preserves_scope(before, after)
    changed = plan("def main(query):\n    return {'result': 'other'}\n")
    assert not preserves_scope(before, changed)
    after["edges"].reverse()
    assert not preserves_scope(before, after)


def test_python_syntax_repair_is_local_without_another_model_call():
    bad = plan("def main(query)\n    return {'result': query.strip()}\n")
    def validate(candidate):
        code = candidate["nodes"][1]["config"]["code"]
        try:
            compile(code, '<syntax only>', 'exec')
            return {"valid": True, "errors": []}
        except SyntaxError:
            return {"valid": False, "errors": ["Python 代码语法错误"]}
    result, op, calls, error = run([(json.dumps(bad), USAGE), (json.dumps(plan()), USAGE)], validate=validate)
    assert result and not error and len(calls) == 1
    assert result['nodes'][1]['config']['code']==plan()['nodes'][1]['config']['code']
    assert any('未追加模型调用' in fix for fix in op['attempts'][0]['deterministic_fixes'])


def test_pause_after_response_does_not_apply_candidate():
    checked = 0
    def guard():
        nonlocal checked
        checked += 1
        if checked > 1:
            raise PlanningStopped("user_pause", "已暂停")
    result, op, calls, error = run([(json.dumps(plan()), USAGE)], guard=guard)
    assert error == "user_pause" and result is None and op["attempts"][0]["usage"] == USAGE


def test_cache_and_reasoning_are_not_double_counted():
    cost = usage_cost({"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 40,
                       "completion_tokens_details": {"reasoning_tokens": 10}}, RATES)
    assert str(cost) == '0.000104'
    assert usage_cost({"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 25}, RATES) is None


@pytest.mark.parametrize("value", [{}, {"input_per_million_usd": True, "output_per_million_usd": 1},
    {"input_per_million_usd": float('nan'), "output_per_million_usd": 1}, {"input_per_million_usd": -1, "output_per_million_usd": 1}])
def test_invalid_pricing_rejected(value):
    with pytest.raises(ValueError):
        validate_pricing(value)


def test_time_spent_in_validation_prevents_commit():
    value = [0.0]
    def validate(candidate):
        value[0] = 70
        return {"valid": True, "errors": []}
    assert run([(json.dumps(plan()), USAGE)], validate=validate, clock=lambda: value[0])[-1] == "time_limit"
