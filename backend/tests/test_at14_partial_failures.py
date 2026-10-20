"""AT-14: execute only generated code from fixed developer fixtures, never Dify.

The small Python harness below is not a Dify iteration runner. Native stop
semantics are checked as serialized policy only, not claimed as platform runs.
"""
import copy
import json
from uuid import uuid4

import httpx
import pytest
import yaml

from test_api import approved, client
from test_iteration import batch_plan, iteration, task
from app import main
from app.dsl_roundtrip import validate_preserved
from app.iteration_outcomes import candidate
from app.iteration_summary import candidate as summarize
from app.workflow_plan import compile_workflow_plan


SCHEMA = {"type": "object", "properties": {"label": {"type": "string"}},
          "required": ["label"], "additionalProperties": False}
VALUES = {"string": "item.strip().upper()", "number": "len(item)",
          "object": '{"label": item.strip().upper()}'}


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("AT-14 隔离检查不得访问真实 HTTP 或调用模型")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(main, "call_model", forbidden)


def fixed_plan(kind="string"):
    plan = batch_plan()
    cfg = iteration(plan)
    cfg["output_type"] = f"array[{kind}]"
    cfg["nodes"][0]["config"].update(
        code=('def main(item: str) -> dict:\n'
              '    if item == "bad":\n'
              '        raise ValueError("固定样例私有异常正文")\n'
              f'    return {{"result": {VALUES[kind]}}}\n'),
        outputs={"result": {"type": kind, "children": None}},
    )
    return plan


def continued(plan, kind="string"):
    return candidate(task(plan), plan, "batch", True, SCHEMA if kind == "object" else None)


def native_nodes(plan):
    text, result = compile_workflow_plan(task(plan))
    assert result["valid"], result["errors"]
    document = yaml.safe_load(text)
    assert validate_preserved(document)["valid"]
    return {n["id"]: n["data"] for n in document["workflow"]["graph"]["nodes"]}


def fixed_function(node):
    # Call sites only pass freshly compiled fixed_plan fixtures and their
    # deterministic product-generated wrappers/summary. Never load saved code.
    scope = {}
    exec(node["code"], scope)
    return scope["main"]


@pytest.mark.parametrize("kind", ["string", "number", "object"])
@pytest.mark.parametrize("items", [
    ["bad", " a ", " a ", ""], [" a ", "bad", " a ", ""],
    [" a ", " a ", "", "bad"], ["bad", "bad"], [],
], ids=["first", "middle", "last", "all_failed", "empty"])
def test_generated_code_continues_and_end_outputs_exact_failure_items(kind, items):
    original = fixed_plan(kind)
    before = copy.deepcopy(original)
    preview = continued(original, kind)
    outcome_plan = json.loads(preview["plan_text"])
    outcome_before = copy.deepcopy(outcome_plan)
    summary_preview = summarize(task(outcome_plan), outcome_plan, "batch", True)
    final_plan = json.loads(summary_preview["plan_text"])
    assert original == before and outcome_plan == outcome_before
    assert iteration(final_plan) == iteration(outcome_plan)
    for value in (preview, summary_preview):
        assert all(value[key] is False for key in (
            "platform_checked", "business_verified", "task_changed", "network_requested"))

    nodes = native_nodes(final_plan)
    assert nodes["batch"]["error_handle_mode"] == "terminated"
    assert nodes["batch"]["is_parallel"] is False
    assert nodes["batch"]["flatten_output"] is False
    parse = fixed_function(nodes["parse"])
    calculate = fixed_function(nodes["clean"])
    summary_id = summary_preview["summary_node_id"]
    summary = fixed_function(nodes[summary_id])
    source = parse(json.dumps(items))["items"]
    rows = [calculate(item, index)["outcome"] for index, item in enumerate(source)]
    result = summary(rows, source)
    # Resolve the actual compiled End selectors, so a broken output binding fails.
    assert all(o["value_selector"][0] == summary_id for o in nodes["end"]["outputs"])
    outputs = {o["variable"]: result[o["value_selector"][1]] for o in nodes["end"]["outputs"]}
    expected = []
    for index, item in enumerate(items):
        success = item != "bad"
        value = {"string": item.strip().upper(), "number": len(item),
                 "object": {"label": item.strip().upper()}}[kind]
        expected.append({"index": index, "ok": success, "value": value if success else None,
                         "error_category": None if success else "ValueError"})
    successes = [row for row in expected if row["ok"]]
    failures = [row for row in expected if not row["ok"]]
    assert outputs == {"results": expected, "successes": successes, "failures": failures,
                       "total": len(items), "succeeded": len(successes), "failed": len(failures)}
    assert "固定样例私有异常正文" not in json.dumps(outputs, ensure_ascii=False)
    assert source == items


@pytest.mark.parametrize("kind", ["string", "number", "object"])
def test_stop_policy_keeps_original_code_and_does_not_turn_failure_into_success(kind):
    plan = fixed_plan(kind)
    before = copy.deepcopy(plan)
    nodes = native_nodes(plan)
    assert nodes["batch"]["error_handle_mode"] == "terminated"
    assert nodes["batch"]["is_parallel"] is False
    assert nodes["clean"]["code"] == iteration(plan)["nodes"][0]["config"]["code"]
    assert nodes["end"]["outputs"] == [{"variable": "results", "value_selector": ["batch", "output"]}]
    fn = fixed_function(nodes["clean"])
    assert "result" in fn(" a ")
    with pytest.raises(ValueError, match="固定样例私有异常正文"):
        fn("bad")
    assert plan == before
    # No stop-path failure-list output exists here; this remains an AT-14 gap.


@pytest.mark.parametrize("mode", ["continue-on-error", "remove-abnormal-output"])
def test_native_continue_or_drop_policy_is_rejected_without_rewriting(mode):
    plan = fixed_plan()
    iteration(plan)["error_handle_mode"] = mode
    before = copy.deepcopy(plan)
    text, checked = compile_workflow_plan(task(plan))
    assert not text and not checked["valid"]
    assert any("error_handle_mode=terminated" in error for error in checked["errors"])
    assert plan == before


def test_preview_acknowledgement_save_and_revision_gates_are_bound_to_new_contract(client):
    saved = approved(client)
    url = f"/api/tasks/{saved['id']}"
    before = client.get(url).json()
    draft = client.get(url + "/plan-draft").json()
    payload = {"revision": saved["revision"], "plan_text": json.dumps(fixed_plan()),
               "node_id": "batch", "acknowledge_result_contract": False,
               "request_nonce": str(uuid4())}
    refused = client.post(url + "/iteration-outcomes", json=payload)
    assert refused.status_code == 422 and "须明确同意" in refused.json()["detail"]
    payload["acknowledge_result_contract"] = True
    response = client.post(url + "/iteration-outcomes", json=payload)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["revision"] == saved["revision"]
    assert preview["task_id"] == saved["id"] and preview["request_nonce"] == payload["request_nonce"]
    summary_payload = {"revision": saved["revision"], "plan_text": preview["plan_text"],
                       "node_id": "batch", "acknowledge_summary_outputs": False,
                       "request_nonce": str(uuid4())}
    refused = client.post(url + "/iteration-summary", json=summary_payload)
    assert refused.status_code == 422 and "须明确接受" in refused.json()["detail"]
    summary_payload["acknowledge_summary_outputs"] = True
    response = client.post(url + "/iteration-summary", json=summary_payload)
    assert response.status_code == 200, response.text
    final = response.json()
    assert final["revision"] == saved["revision"] and final["task_id"] == saved["id"]
    assert final["request_nonce"] == summary_payload["request_nonce"]
    for value in (preview, final):
        assert all(value[key] is False for key in (
            "task_changed", "network_requested", "platform_checked", "business_verified"))
    assert client.get(url).json() == before
    assert client.get(url + "/plan-draft").json() == draft

    response = client.post(url + "/plan", json={"revision": saved["revision"], "plan_text": final["plan_text"]})
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["revision"] == saved["revision"] + 1
    assert changed["workflow_plan"] == json.loads(final["plan_text"])
    assert changed["requirements_confirmed"] is changed["configuration_confirmed"] is False
    assert changed["intake_required"] is True
    assert changed["requirements"] == before["requirements"]
    assert changed["confirmations"][:len(before["confirmations"])] == before["confirmations"]
    assert not changed["dify_app_id"] and not changed["runs"]
    # Save returns an extra plan_text projection; compare the same GET shape.
    persisted = client.get(url).json()
    assert persisted["workflow_plan"] == changed["workflow_plan"]
    assert persisted["revision"] == changed["revision"]
    for endpoint, request in (("iteration-outcomes", payload), ("iteration-summary", summary_payload)):
        assert client.post(url + "/" + endpoint, json=request).status_code == 409
    assert client.post(url + "/build", json={"revision": changed["revision"]}).status_code == 422
    assert client.get(url).json() == persisted
