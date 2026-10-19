from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation import evaluate_output, validate_test_cases


def case(expectation: dict | None = None, **overrides: object) -> dict:
    value = {
        "id": "case-1",
        "name": "基础用例",
        "input": {"question": "你好"},
        "expectation": expectation or {"mode": "equals", "target": "result", "expected": "你好"},
    }
    value.update(overrides)
    return value


def test_valid_cases_accept_manual_without_target_or_expected() -> None:
    result = validate_test_cases([case({"mode": "manual", "description": "检查语气"}, required=False)])
    assert result == {"valid": True, "errors": []}


def test_validate_rejects_non_list_cases() -> None:
    assert validate_test_cases({})["valid"] is False


def test_validate_rejects_blank_name_and_non_object_input() -> None:
    result = validate_test_cases([case(name=" ", input=[])])
    assert not result["valid"]
    assert len(result["errors"]) == 2


def test_validate_rejects_unknown_mode_and_missing_target() -> None:
    result = validate_test_cases([case({"mode": "regex", "expected": "x"})])
    assert not result["valid"]
    assert any("mode" in error for error in result["errors"])


@pytest.mark.parametrize("expected", [1, None, {"needle": "x"}])
def test_validate_contains_requires_string_or_string_list(expected: object) -> None:
    result = validate_test_cases([case({"mode": "contains", "target": "answer", "expected": expected})])
    assert not result["valid"]


def test_validate_json_keys_requires_string_list() -> None:
    result = validate_test_cases([case({"mode": "json_keys", "target": "answer", "expected": ["ok", 2]})])
    assert not result["valid"]


def test_validate_rejects_non_json_values() -> None:
    result = validate_test_cases([case(input={"bad": float("nan")})])
    assert not result["valid"]
    assert any("有限值" in error for error in result["errors"])


def test_validate_rejects_duplicate_ids_and_non_boolean_required() -> None:
    result = validate_test_cases([case(required=1), case()])
    assert not result["valid"]
    assert any("required" in error for error in result["errors"])
    assert any("重复" in error for error in result["errors"])


def test_contains_matches_string_substring() -> None:
    result = evaluate_output({"answer": "订单将在明天送达"}, {"mode": "contains", "target": "answer", "expected": "明天"})
    assert result["status"] == "passed"


def test_contains_checks_each_requested_string_in_object_values() -> None:
    result = evaluate_output({"result": {"message": "已退款", "state": "完成"}}, {"mode": "contains", "target": "result", "expected": ["退款", "完成"]})
    assert result["status"] == "passed"


def test_contains_does_not_match_dictionary_keys_or_repr() -> None:
    result = evaluate_output({"result": {"secret-marker": 4}}, {"mode": "contains", "target": "result", "expected": "secret-marker"})
    assert result["status"] == "failed"


def test_equals_distinguishes_boolean_and_integer() -> None:
    result = evaluate_output({"result": True}, {"mode": "equals", "target": "result", "expected": 1})
    assert result["status"] == "failed"


def test_equals_compares_nested_json_values() -> None:
    expected = {"ok": True, "count": 2}
    result = evaluate_output({"result": expected.copy()}, {"mode": "equals", "target": "result", "expected": expected})
    assert result["status"] == "passed"


def test_missing_target_path_fails() -> None:
    result = evaluate_output({"result": {}}, {"mode": "equals", "target": "result.answer", "expected": "x"})
    assert result["status"] == "failed"
    assert "未找到" in result["details"]


def test_json_keys_checks_native_object() -> None:
    result = evaluate_output({"result": {"id": "7", "status": "ok"}}, {"mode": "json_keys", "target": "result", "expected": ["id", "status"]})
    assert result["status"] == "passed"


def test_json_keys_strictly_parses_json_text() -> None:
    result = evaluate_output({"result": '{"id":7,"ok":true}'}, {"mode": "json_keys", "target": "result", "expected": ["id"]})
    assert result["status"] == "passed"


@pytest.mark.parametrize("text", ['{"id":1,"id":2}', '{"id":NaN}', '["id"]', 'not json'])
def test_json_keys_rejects_invalid_json_text(text: str) -> None:
    result = evaluate_output({"result": text}, {"mode": "json_keys", "target": "result", "expected": ["id"]})
    assert result["status"] == "failed"


def test_manual_always_needs_review_even_when_description_exists() -> None:
    result = evaluate_output({"result": "done"}, {"mode": "manual", "description": "确认是否合规"})
    assert result["status"] == "needs_review"


def test_long_output_is_truncated_after_full_output_is_judged() -> None:
    answer = "x" * 5_000 + "终点"
    result = evaluate_output({"answer": answer}, {"mode": "contains", "target": "answer", "expected": "终点"})
    assert result["status"] == "passed"
    assert result["actual"]["truncated"] is True
    assert "判定基于完整输出" in result["details"]


def test_details_warn_rule_check_is_not_business_correctness_proof() -> None:
    # Passing a structural rule establishes only that the declared rule matched.
    result = evaluate_output({"result": "退款完成"}, {"mode": "contains", "target": "result", "expected": "退款"})
    assert result["status"] == "passed"
    assert "不代表完整业务正确性" in result["details"]
