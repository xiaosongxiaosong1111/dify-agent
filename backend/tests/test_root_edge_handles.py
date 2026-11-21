from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main
from app.workflow_plan import compile_workflow_plan, validate_plan
from test_api import approved, client, code_only_plan, forbid_api_external_calls
from test_workflow_plan import base_plan, end, llm, plan_task, start, task as workflow_task


def rejected(plan):
    result = validate_plan(workflow_task(), plan)
    content, checked = compile_workflow_plan(plan_task(plan))
    assert not result["valid"], result
    assert not checked["valid"] and content == ""
    return result


@pytest.mark.parametrize("field,value", [
    ("source_handle", None), ("source_handle", ""), ("source_handle", "case1"),
    ("source_handle", ["case1"]), ("source_handle", True), ("source_handle", 1),
    ("sourceHandle", None), ("sourceHandle", ""), ("sourceHandle", "case1"),
    ("sourceHandle", ["case1"]), ("sourceHandle", False), ("sourceHandle", 2),
])
def test_invalid_source_aliases_are_rejected_without_yaml(field, value):
    plan = base_plan()
    plan["edges"][0][field] = value
    result = rejected(plan)
    assert any("edges[0]" in error for error in result["errors"])


@pytest.mark.parametrize("field,value", [
    ("target_handle", None), ("target_handle", ""), ("target_handle", "not-a-handle"),
    ("target_handle", ["not-a-handle"]), ("target_handle", False), ("target_handle", 1),
    ("targetHandle", None), ("targetHandle", ""), ("targetHandle", "not-a-handle"),
    ("targetHandle", ["not-a-handle"]), ("targetHandle", True), ("targetHandle", 2),
])
def test_invalid_target_aliases_are_rejected_without_yaml(field, value):
    plan = base_plan()
    plan["edges"][1][field] = value
    result = rejected(plan)
    assert any("edges[1]" in error and "target" in error for error in result["errors"])


def test_conflicting_source_aliases_are_rejected():
    plan = base_plan()
    plan["edges"][0].update({"source_handle": "source", "sourceHandle": "case1"})
    result = rejected(plan)
    assert any("edges[0].source_handle 与 sourceHandle 不一致" in error for error in result["errors"])


def test_conflicting_target_aliases_are_rejected():
    plan = base_plan()
    plan["edges"][1].update({"target_handle": "target", "targetHandle": "other"})
    result = rejected(plan)
    assert any("edges[1].target_handle 与 targetHandle 不一致" in error for error in result["errors"])


def test_both_source_aliases_must_be_strings():
    plan = base_plan()
    plan["edges"][0].update({"source_handle": "source", "sourceHandle": None})
    result = rejected(plan)
    assert any("edges[0].sourceHandle 必须是字符串" in error for error in result["errors"])


@pytest.mark.parametrize("fields", [
    {},
    {"source_handle": "source", "target_handle": "target"},
    {"sourceHandle": "source", "targetHandle": "target"},
    {"source_handle": "source", "sourceHandle": "source", "target_handle": "target", "targetHandle": "target"},
])
def test_omitted_camel_snake_or_coherent_dual_handles_compile_unchanged(fields):
    plan = base_plan()
    plan["edges"] = [{"source": "start", "target": "llm", **fields}, {"source": "llm", "target": "end", **fields}]
    before = copy.deepcopy(plan)
    content, checked = compile_workflow_plan(plan_task(plan))
    assert checked["valid"], checked
    root = yaml.safe_load(content)
    assert [(edge["sourceHandle"], edge["targetHandle"]) for edge in root["workflow"]["graph"]["edges"]] == [
        ("source", "target"), ("source", "target"),
    ]
    assert plan == before


def test_chatflow_answer_terminal_and_source_query_still_compile():
    plan = base_plan("advanced-chat")
    content, checked = compile_workflow_plan(plan_task(plan, "advanced-chat"))
    assert checked["valid"], checked
    root = yaml.safe_load(content)
    assert root["app"]["mode"] == "advanced-chat"
    assert all(edge["sourceHandle"] == "source" and edge["targetHandle"] == "target" for edge in root["workflow"]["graph"]["edges"])


def test_ordinary_implicit_parallel_edges_remain_allowed():
    plan = base_plan()
    plan["nodes"] = [start(), llm("a"), llm("b"), end("end_a", ["a", "text"]), end("end_b", ["b", "text"])]
    plan["edges"] = [
        {"source": "start", "target": "a"}, {"source": "start", "target": "b"},
        {"source": "a", "target": "end_a"}, {"source": "b", "target": "end_b"},
    ]
    content, checked = compile_workflow_plan(plan_task(plan))
    assert checked["valid"], checked
    root = yaml.safe_load(content)
    assert len(root["workflow"]["graph"]["edges"]) == 4
    assert all(edge["sourceHandle"] == "source" and edge["targetHandle"] == "target" for edge in root["workflow"]["graph"]["edges"])


@pytest.mark.parametrize("edge_index,field,value", [
    (0, "source_handle", "case1"),
    (0, "sourceHandle", "case1"),
    (1, "target_handle", ["not-a-handle"]),
    (1, "targetHandle", False),
    (1, "target_handle", 1),
    (1, "targetHandle", None),
])
def test_normal_api_rejects_invalid_root_edge_handles_without_mutation(client, edge_index, field, value):
    current = approved(client)
    task_id = current["id"]
    before = copy.deepcopy(main.store.get("task", task_id))
    plan = copy.deepcopy(code_only_plan())
    plan["edges"][edge_index][field] = value
    response = client.post(f"/api/tasks/{task_id}/plan", json={"revision": current["revision"], "plan": plan})
    assert response.status_code == 422, response.text
    assert f"edges[{edge_index}]" in response.text
    assert main.store.get("task", task_id) == before
