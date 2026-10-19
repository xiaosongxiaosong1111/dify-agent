import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.acceptance import summarize_acceptance, same_json


def task():
    case = {"id": "case", "name": "标准场景", "input": {"query": "x"}, "required": True,
            "expectation": {"mode": "contains", "target": "result", "expected": "x"}}
    return {"revision": 4, "environment_id": "env", "test_cases": [case], "runs": [],
            "requirements_confirmed": True, "configuration_confirmed": True, "configuration": {}}


def record(t, **changes):
    case = copy.deepcopy(t["test_cases"][0])
    return {"id": "run", "kind": "run", "revision": t["revision"], "environment_id": t["environment_id"],
            "status": "success", "input": copy.deepcopy(case["input"]), "test_case": case,
            "evaluation": {"status": "passed", "mode": "contains", "details": "关键词满足"}, **changes}


def test_no_cases_does_not_vacuously_pass():
    t = task()
    t["test_cases"] = []
    result = summarize_acceptance(t)
    assert not result["all_required_passed"] and result["required"]["total"] == 0


def test_old_revision_or_other_environment_not_counted():
    t = task()
    t["runs"] = [record(t, revision=3), record(t, environment_id="elsewhere")]
    result = summarize_acceptance(t)
    assert result["cases"][0]["status"] == "not_run"
    assert not result["all_required_passed"]


@pytest.mark.parametrize("run_status,expected", [("pending", "running"), ("unknown", "unknown"), ("failed", "failed")])
def test_latest_run_replaces_previous_success(run_status, expected):
    t = task()
    t["runs"] = [record(t, id="old"), record(t, id="latest", status=run_status)]
    result = summarize_acceptance(t)
    assert result["cases"][0]["status"] == expected
    assert result["cases"][0]["run_id"] == "latest" and not result["all_required_passed"]


def test_different_input_or_expectation_needs_review():
    t = task()
    t["runs"] = [record(t, input={"query": "changed"})]
    assert summarize_acceptance(t)["cases"][0]["status"] == "needs_review"
    t["runs"] = [record(t)]
    t["runs"][0]["test_case"]["expectation"]["expected"] = "something else"
    assert summarize_acceptance(t)["cases"][0]["status"] == "needs_review"


def test_manual_verdict_keeps_original_evaluation():
    t = task()
    t["test_cases"][0]["expectation"] = {"mode": "manual", "description": "核对真实性"}
    r = record(t, evaluation={"status": "needs_review", "mode": "manual", "details": "人工判断"})
    t["runs"] = [r]
    assert summarize_acceptance(t)["required"]["needs_review"] == 1
    r["manual_review"] = {"source": "user", "decision": "passed", "reason": "已核对"}
    result = summarize_acceptance(t)
    assert result["all_required_passed"] and result["cases"][0]["method"] == "human"
    assert r["evaluation"]["status"] == "needs_review"


def test_human_verdict_cannot_override_automatic_failure():
    t = task()
    t["runs"] = [record(t, evaluation={"status": "failed", "mode": "contains"},
                       manual_review={"source": "user", "decision": "passed", "reason": "错误记录"})]
    assert summarize_acceptance(t)["cases"][0]["status"] == "failed"


def test_optional_failure_and_mock_are_not_full_verification():
    t = task()
    optional = copy.deepcopy(t["test_cases"][0])
    optional.update(id="optional", required=False)
    t["test_cases"].append(optional)
    t["runs"] = [record(t)]
    t["configuration"]["mock_dependencies"] = ["客户接口"]
    result = summarize_acceptance(t)
    assert result["all_required_passed"] and result["required"]["total"] == 1
    assert result["verification"] == "declared_checks_only"
    assert any("模拟" in x for x in result["blockers"])


def test_json_input_types_are_not_coerced():
    assert not same_json({"x": True}, {"x": 1})
    assert same_json({"a": 1, "b": 2}, {"b": 2, "a": 1})


def test_invalid_metadata_cannot_break_case_serialization():
    from app.evaluation import validate_test_cases
    case = task()["test_cases"][0]
    case["metadata"] = {"score": float("nan")}
    result = validate_test_cases([case])
    assert not result["valid"] and any("有限" in e for e in result["errors"])
