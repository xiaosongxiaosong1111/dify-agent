"""AT-12: local diagnosis, explicit manual correction and branch preservation."""
import copy
import hashlib
import json
from uuid import uuid4

import pytest
import httpx
import yaml

from test_api import approved, client
from test_workflow_plan import end, llm, start, task
from app import main
from app.dsl_roundtrip import parse, validate_preserved
from app.workflow_plan import compile_workflow_plan


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("AT-12 隔离检查不得访问网络或调用模型")

    # TestClient uses an in-process transport; block actual HTTP transports.
    # Windows asyncio needs its own loopback socket pair to start TestClient.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(main, "call_model", forbidden)


def branch_plan(mode):
    selector = ["sys", "query"] if mode == "advanced-chat" else ["start", "query"]
    terminals = [
        {"id": f"{name}_end", "type": "answer", "config": {"answer": f"{{{{#{name}.text#}}}}"}}
        if mode == "advanced-chat" else end(f"{name}_end", [name, "text"])
        for name in ("order", "other")
    ]
    return {
        "schema_version": 1,
        "nodes": [
            start(mode),
            {"id": "route", "type": "if-else", "config": {"cases": [{
                "case_id": "orders", "logical_operator": "and", "conditions": [{
                    "variable_selector": selector, "comparison_operator": "contains",
                    "value": "订单", "varType": "string",
                }],
            }]}},
            llm("order", "处理订单"), llm("other", "保留转人工业务分支"), *terminals,
        ],
        "edges": [
            {"source": "start", "target": "route"},
            {"source": "route", "source_handle": "orders", "target": "order"},
            {"source": "route", "source_handle": "false", "target": "other"},
            {"source": "order", "target": "order_end"},
            {"source": "other", "target": "other_end"},
        ],
    }


CASES = ["missing_node", "missing_variable", "sibling", "condition", "terminal"]


def break_reference(nodes, mode, case, native=False):
    """Change one reference only; return its exact node/field diagnostic."""
    field = "data" if native else "config"
    if case == "condition":
        nodes["route"][field]["cases"][0]["conditions"][0]["variable_selector"] = ["order", "text"]
        return "节点 route 的 cases[0].conditions[0].variable_selector 引用源 order 不保证在所有路径上游（可能来自兄弟分支）"
    if case == "terminal":
        terminal = nodes["order_end"][field]
        if mode == "advanced-chat":
            terminal["answer"] = "{{#order.missing#}}"
            location = "answer reference"
        else:
            terminal["outputs"][0]["value_selector"] = ["order", "missing"]
            location = "outputs[0].value_selector"
        return f"节点 order_end 的 {location} 引用了不存在变量：order.missing"
    reference, reason = {
        "missing_node": ("absent.text", "引用了不存在节点：absent"),
        "missing_variable": ("order.missing", "引用了不存在变量：order.missing"),
        "sibling": ("other.text", "引用源 other 不保证在所有路径上游（可能来自兄弟分支）"),
    }[case]
    if case == "missing_variable":
        reference, reason = "start.missing", "引用了不存在变量：start.missing"
        if mode == "advanced-chat":
            reference, reason = "sys.missing", "只能在 Chatflow 引用 sys.query"
    prompt = "{{#" + reference + "#}}"
    if native:
        next(p for p in nodes["order"][field]["prompt_template"] if p["role"] == "user")["text"] = prompt
    else:
        nodes["order"][field]["user_prompt"] = prompt
    return f"节点 order 的 user_prompt reference {reason}"


@pytest.mark.parametrize("mode", ["workflow", "advanced-chat"])
@pytest.mark.parametrize("case", CASES)
def test_at12_plan_check_manual_correction_keeps_both_branches(client, monkeypatch, mode, case):
    saved = approved(client, app_type=mode)
    before = client.get(f"/api/tasks/{saved['id']}").json()
    original = branch_plan(mode)
    broken = copy.deepcopy(original)
    expected = break_reference({n["id"]: n for n in broken["nodes"]}, mode, case)

    def no_save(*args, **kwargs):
        pytest.fail("草稿检查不得保存任务或改变确认")

    monkeypatch.setattr(main.store, "put", no_save)

    def check(plan):
        text = json.dumps(plan, ensure_ascii=False)
        nonce = str(uuid4())
        response = client.post(f"/api/tasks/{saved['id']}/plan-check", json={
            "revision": saved["revision"], "plan_text": text, "request_nonce": nonce,
        })
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["source_text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
        assert value["revision"] == saved["revision"] and value["request_nonce"] == nonce
        assert value["verification"] == "local_plan_structure_only"
        assert value["nodes"] == 6
        assert not any(value[k] for k in (
            "task_changed", "network_requested", "code_executed", "platform_checked", "business_verified",
        ))
        assert client.get(f"/api/tasks/{saved['id']}").json() == before
        return value

    snapshot = copy.deepcopy(broken)
    failed = check(broken)
    assert not failed["valid"] and expected in failed["errors"]
    assert broken == snapshot
    # Explicit manual correction: restore only the node containing the bad ref.
    node_id = "route" if case == "condition" else "order_end" if case == "terminal" else "order"
    next(n for n in broken["nodes"] if n["id"] == node_id)["config"] = copy.deepcopy(
        next(n for n in original["nodes"] if n["id"] == node_id)["config"]
    )
    fixed = check(broken)
    assert fixed["valid"] and fixed["errors"] == []
    assert fixed["source_text_sha256"] != failed["source_text_sha256"]
    assert broken == original  # All nodes, branches, conditions and business text survive.


@pytest.mark.parametrize("mode", ["workflow", "advanced-chat"])
@pytest.mark.parametrize("case", CASES)
def test_at12_final_yaml_manual_correction_keeps_entire_document(mode, case):
    content, validation = compile_workflow_plan({**task(mode), "workflow_plan": branch_plan(mode)})
    assert validation["valid"], validation["errors"]
    original = parse(content, mode)
    assert validate_preserved(original)["valid"]
    broken = copy.deepcopy(original)
    nodes = {n["id"]: n for n in broken["workflow"]["graph"]["nodes"]}
    expected = break_reference(nodes, mode, case, native=True)
    # Exercise the actual YAML parser and preserved-DSL validator, not just a plan.
    text = yaml.safe_dump(broken, allow_unicode=True, sort_keys=False)
    document = parse(text, mode)
    snapshot = copy.deepcopy(document)
    failed = validate_preserved(document)
    assert not failed["valid"] and expected in failed["errors"]
    assert document == snapshot
    node_id = "route" if case == "condition" else "order_end" if case == "terminal" else "order"
    target = next(n for n in document["workflow"]["graph"]["nodes"] if n["id"] == node_id)
    target["data"] = copy.deepcopy(next(
        n["data"] for n in original["workflow"]["graph"]["nodes"] if n["id"] == node_id
    ))
    corrected = parse(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), mode)
    result = validate_preserved(corrected)
    assert result["valid"] and result["errors"] == [], result["errors"]
    assert corrected == original  # Includes edges/handles, models, prompts and layout.
