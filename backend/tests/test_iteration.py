import copy
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.workflow_plan import compile_workflow_plan, validate_plan
from app.planning import normalize_draft, preserves_scope
from app import main
from app.storage import Store


def batch_plan():
    return {"schema_version": 1, "nodes": [
        {"id": "start", "type": "start", "config": {"variables": [{"variable": "items_json", "type": "paragraph", "required": True}]}},
        {"id": "parse", "type": "code", "config": {"code_language": "python3", "code": 'import json\ndef main(items_json: str) -> dict:\n    items = json.loads(items_json)\n    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):\n        raise ValueError("输入须为 JSON 字符串数组")\n    return {"items": items}\n', "variables": [{"variable": "items_json", "value_selector": ["start", "items_json"]}], "outputs": {"items": {"type": "array[string]", "children": None}}}},
        {"id": "batch", "type": "iteration", "config": {"iterator_selector": ["parse", "items"], "iterator_input_type": "array[string]", "output_selector": ["clean", "result"], "output_type": "array[string]", "is_parallel": False, "error_handle_mode": "terminated", "flatten_output": False, "nodes": [
            {"id": "clean", "type": "code", "config": {"code_language": "python3", "code": 'def main(item: str) -> dict:\n    return {"result": item.strip().upper()}\n', "variables": [{"variable": "item", "value_selector": ["batch", "item"]}], "outputs": {"result": {"type": "string", "children": None}}}}
        ]}},
        {"id": "end", "type": "end", "config": {"outputs": [{"variable": "results", "value_selector": ["batch", "output"]}]}}
    ], "edges": [{"source": "start", "target": "parse"}, {"source": "parse", "target": "batch"}, {"source": "batch", "target": "end"}]}


def task(plan=None, **configuration):
    return {"app_type": "workflow", "configuration": configuration, "workflow_plan": plan or batch_plan()}


def iteration(plan):
    return plan["nodes"][2]["config"]


def test_native_container_preserves_scope_types_and_order():
    plan = batch_plan()
    original = copy.deepcopy(plan)
    content, checked = compile_workflow_plan(task(plan))
    assert checked["valid"], checked["errors"]
    assert checked["nodes"] == 5 and plan == original
    graph = yaml.safe_load(content)["workflow"]["graph"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["batch"]["data"]["error_handle_mode"] == "terminated"
    assert nodes["batch"]["data"]["flatten_output"] is False
    assert nodes["batch"]["data"]["start_node_id"] == "batch__iteration_start"
    assert nodes["clean"]["parentId"] == "batch"
    assert nodes["clean"]["data"]["variables"][0]["value_selector"] == ["batch", "item"]
    assert nodes["end"]["position"]["x"] > nodes["batch"]["position"]["x"] + nodes["batch"]["width"]
    inner_edges = [e for e in graph["edges"] if e["data"].get("isInIteration")]
    assert len(inner_edges) == 1 and inner_edges[0]["source"] == "batch__iteration_start"


@pytest.mark.parametrize("field,value", [("is_parallel", True), ("is_parallel", 0), ("error_handle_mode", "continue-on-error"), ("flatten_output", True), ("flatten_output", None), ("edges", []), ("nodes", []), ("nodes", [None]), ("nodes", "bad"), ("iterator_selector", ["start", "items_json"]), ("iterator_selector", ["clean", "result"]), ("iterator_input_type", "array[number]"), ("iterator_input_type", []), ("output_type", "array[number]"), ("output_selector", ["parse", "items"]), ("output_selector", ["clean", "missing"])])
def test_unsupported_or_inconsistent_config_is_rejected(field, value):
    plan = batch_plan()
    iteration(plan)[field] = value
    assert not validate_plan(task(plan), plan)["valid"]
    content, checked = compile_workflow_plan(task(plan))
    assert not content and not checked["valid"]


@pytest.mark.parametrize("selector", [["batch", "output"], ["clean", "result"], ["end", "results"], ["other", "text"], ["batch", "missing"]])
def test_body_cannot_read_future_or_unavailable_values(selector):
    plan = batch_plan()
    iteration(plan)["nodes"][0]["config"]["variables"][0]["value_selector"] = selector
    assert not validate_plan(task(plan), plan)["valid"]


@pytest.mark.parametrize("selector", [["clean", "result"], ["batch", "item"], ["batch", "index"]])
def test_body_values_do_not_leak_outside(selector):
    plan = batch_plan()
    plan["nodes"][-1]["config"]["outputs"][0]["value_selector"] = selector
    assert not validate_plan(task(plan), plan)["valid"]


@pytest.mark.parametrize("nid", ["parse", "start", "batch__iteration_start", "batch__scope_input", "batch__scope_end"])
def test_duplicate_and_reserved_ids_fail(nid):
    plan = batch_plan()
    iteration(plan)["nodes"][0]["id"] = nid
    assert not validate_plan(task(plan), plan)["valid"]


@pytest.mark.parametrize("kind", ["iteration", "if-else", "http-request", "knowledge-retrieval", "answer", "start", "end"])
def test_body_type_limits_are_explicit(kind):
    plan = batch_plan()
    iteration(plan)["nodes"][0]["type"] = kind
    assert not validate_plan(task(plan), plan)["valid"]


def test_ordered_body_and_index_with_real_upstream_binding():
    plan = batch_plan()
    cfg = iteration(plan)
    cfg["nodes"].append({"id": "format", "type": "template-transform", "config": {"template": "{{ index }}:{{ item }} / {{ source }}", "variables": [{"variable": "index", "value_selector": ["batch", "index"], "value_type": "number"}, {"variable": "item", "value_selector": ["clean", "result"], "value_type": "string"}, {"variable": "source", "value_selector": ["start", "items_json"], "value_type": "string"}]}})
    cfg["output_selector"] = ["format", "output"]
    assert validate_plan(task(plan), plan)["valid"]
    cfg["nodes"][-1]["config"]["variables"][0]["value_type"] = "string"
    assert not validate_plan(task(plan), plan)["valid"]


def test_sibling_branch_value_is_not_available_in_body():
    plan = batch_plan()
    plan["nodes"].extend([
        {"id": "route", "type": "if-else", "config": {"cases": [{"case_id": "yes", "logical_operator": "and", "conditions": [{"variable_selector": ["start", "items_json"], "varType": "string", "comparison_operator": "not empty", "value": ""}]}]}},
        {"id": "sibling", "type": "template-transform", "config": {"template": "sibling"}},
        {"id": "other_end", "type": "end", "config": {"outputs": [{"variable": "result", "value_selector": ["sibling", "output"]}]}}
    ])
    plan["edges"] = [{"source": "start", "target": "route"}, {"source": "route", "source_handle": "yes", "target": "parse"}, {"source": "parse", "target": "batch"}, {"source": "batch", "target": "end"}, {"source": "route", "source_handle": "false", "target": "sibling"}, {"source": "sibling", "target": "other_end"}]
    iteration(plan)["nodes"][0]["config"]["variables"][0]["value_selector"] = ["sibling", "output"]
    checked = validate_plan(task(plan), plan)
    assert not checked["valid"] and any("不存在节点" in e for e in checked["errors"])


def llm_body(plan):
    cfg = iteration(plan)
    cfg["nodes"] = [{"id": "item_llm", "type": "llm", "config": {"user_prompt": "{{#batch.index#}}:{{#batch.item#}}"}}]
    cfg["output_selector"] = ["item_llm", "text"]


def test_nested_llm_requires_model_and_chatflow_body_discloses_no_history():
    plan = batch_plan()
    llm_body(plan)
    assert not compile_workflow_plan(task(plan))[1]["valid"]
    cfg = {"dify_model_provider": "actual/provider", "dify_model": "actual-model", "temperature": .2, "max_tokens": 256}
    content, checked = compile_workflow_plan(task(plan, **cfg))
    assert checked["valid"]
    node = next(n for n in yaml.safe_load(content)["workflow"]["graph"]["nodes"] if n["id"] == "item_llm")
    assert node["data"]["model"]["name"] == "actual-model"
    plan["nodes"][0]["config"]["variables"] = []
    plan["nodes"][1]["config"]["variables"][0]["value_selector"] = ["sys", "query"]
    plan["nodes"][-1] = {"id": "end", "type": "answer", "config": {"answer": "{{#batch.output#}}"}}
    value = {**task(plan, **cfg), "app_type": "advanced-chat"}
    value["configuration"].update(conversation_memory=True, memory_turns=3)
    content, checked = compile_workflow_plan(value)
    assert checked["valid"], checked["errors"]
    inner = next(n for n in yaml.safe_load(content)["workflow"]["graph"]["nodes"] if n["id"] == "item_llm")
    assert "memory" not in inner["data"]


def test_body_syntax_only_repair_keeps_container_policy():
    original = batch_plan()
    original["nodes"][2]["config"]["nodes"][0]["config"]["code_language"] = "python"
    normalized, fixes = normalize_draft(original)
    assert fixes and iteration(normalized)["nodes"][0]["config"]["code_language"] == "python3"
    repaired = copy.deepcopy(normalized)
    iteration(repaired)["nodes"][0]["config"]["code"] += "\n"
    assert preserves_scope(normalized, repaired)
    iteration(repaired)["error_handle_mode"] = "continue-on-error"
    assert not preserves_scope(normalized, repaired)


def test_configuration_confirmation_gates_inner_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", Store(tmp_path))
    monkeypatch.setattr(main, "DATA_ROOT", tmp_path)
    with TestClient(main.app) as client:
        value = client.post("/api/tasks", json={"name": "迭代", "app_type": "workflow"}).json()
        tid = value["id"]
        value = client.patch(f"/api/tasks/{tid}", json={"requirements": {k: "明确的技术规则" for k in main.REQ_KEYS}, "configuration": {"resource_plan": "新建本机技术示例，逐项模型调用"}}).json()
        plan = batch_plan()
        llm_body(plan)
        response = client.post(f"/api/tasks/{tid}/plan", json={"revision": value["revision"], "plan": plan})
        assert response.status_code == 200, response.text
        value = response.json()
        intake_state=client.get(f"/api/tasks/{tid}/intake").json()
        answers={row['id']:value['requirements'].get(row['id'],'明确采用当前技术样例的顺序批量规则；任一项失败停止整批，保留顺序与重复项。') for row in intake_state['standard']}
        response=client.post(f"/api/tasks/{tid}/intake/manual",json={'revision':value['revision'],'context_token':intake_state['context_token'],'answers':answers,'acknowledge_review':True})
        assert response.status_code==200,response.text
        value=response.json()
        assert client.post(f"/api/tasks/{tid}/confirm", json={"revision": value["revision"], "kind": "requirements"}).status_code == 200
        response = client.post(f"/api/tasks/{tid}/confirm", json={"revision": value["revision"], "kind": "configuration"})
        assert response.status_code == 422 and "模型" in response.json()["detail"]
