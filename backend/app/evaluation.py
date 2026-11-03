"""Deterministic checks for saved evaluation cases and workflow outputs.

These checks validate declared rules only. A passing result is not proof of
complete business correctness.
"""

from __future__ import annotations

import json
from .plan_text_codec import wire_float
import math
from typing import Any


_MODES = {"contains", "equals", "json_keys", "json_schema", "manual"}
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 20_000
_MAX_PREVIEW_CHARS = 4_000


def _json_value_error(value: Any, *, depth: int = 0, budget: list[int] | None = None) -> str | None:
    """Return a reason when value is outside the bounded JSON value model."""
    if budget is None:
        budget = [_MAX_JSON_NODES]
    budget[0] -= 1
    if budget[0] < 0:
        return "JSON值包含过多元素"
    if depth > _MAX_JSON_DEPTH:
        return "JSON值嵌套过深"
    if value is None or type(value) in (bool, int):
        return None
    if type(value) is str:
        try:value.encode('utf-8')
        except UnicodeError:return '文字编码无法完整核对，未替换字符'
        return None
    if type(value) is float:
        return None if math.isfinite(value) else "数字必须是有限值"
    if type(value) is list:
        for child in value:
            error = _json_value_error(child, depth=depth + 1, budget=budget)
            if error:
                return error
        return None
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                return "对象键必须是字符串"
            try:key.encode('utf-8')
            except UnicodeError:return '对象键编码无法完整核对，未替换字符'
            error = _json_value_error(child, depth=depth + 1, budget=budget)
            if error:
                return error
        return None
    return f"包含不支持的值类型：{type(value).__name__}"


def _expectation_error(expectation: Any, label: str) -> str | None:
    if type(expectation) is not dict:
        return f"{label}必须是对象"
    value_error = _json_value_error(expectation)
    if value_error:
        return f"{label}{value_error}"
    mode = expectation.get("mode")
    if not isinstance(mode, str) or mode not in _MODES:
        return f"{label}.mode必须是contains、equals、json_keys、json_schema或manual"
    if mode == "manual":
        description = expectation.get("description")
        if not isinstance(description, str) or not description.strip():
            return f"{label}.description在manual模式下不能为空"
        if "target" in expectation and expectation["target"] is not None and (
            not isinstance(expectation["target"], str) or not expectation["target"].strip()
        ):
            return f"{label}.target必须是非空字符串"
        if "expected" in expectation:
            return _json_value_error(expectation["expected"])
        return None

    target = expectation.get("target")
    if not isinstance(target, str) or not target.strip() or any(not part for part in target.split(".")):
        return f"{label}.target必须是非空点分路径"
    if "expected" not in expectation:
        return f"{label}.expected不能为空"
    expected = expectation["expected"]
    error = _json_value_error(expected)
    if error:
        return f"{label}.expected{error}"
    if mode == "json_schema":
        from .json_inputs import schema
        try: schema(expected)
        except ValueError as exc:return f"{label}.expected的输出Schema未适配：{exc}"
    if mode == "contains" and not (
        (isinstance(expected, str) and bool(expected))
        or (type(expected) is list and bool(expected) and all(isinstance(item, str) and item for item in expected))
    ):
        return f"{label}.expected在contains模式下必须是字符串或字符串列表"
    if mode == "json_keys" and not (
        type(expected) is list and bool(expected) and all(isinstance(item, str) and item for item in expected)
    ):
        return f"{label}.expected在json_keys模式下必须是非空字符串组成的列表"
    return None


def validate_test_cases(cases: list, app_type=None) -> dict:
    """Validate a list of named test cases without executing user code."""
    errors: list[str] = []
    if type(cases) is not list:
        return {"valid": False, "errors": ["cases必须是列表"]}

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        label = f"第{index + 1}个测试用例"
        if type(case) is not dict:
            errors.append(f"{label}必须是对象")
            continue
        value_error = _json_value_error(case)
        if value_error:
            errors.append(f"{label}{value_error}")
            continue
        if "id" in case:
            if not isinstance(case["id"], str) or not case["id"].strip():
                errors.append(f"{label}.id必须是非空字符串")
            elif case["id"] in seen_ids:
                errors.append(f"{label}.id重复：{case['id']}")
            else:
                seen_ids.add(case["id"])
        if not isinstance(case.get("name"), str) or not case["name"].strip():
            errors.append(f"{label}.name必须是非空字符串")
        if type(case.get("input")) is not dict:
            errors.append(f"{label}.input必须是对象")
        else:
            error = _json_value_error(case["input"])
            if error:
                errors.append(f"{label}.input{error}")
        if "required" in case and type(case["required"]) is not bool:
            errors.append(f"{label}.required必须是布尔值")
        error = _expectation_error(case.get("expectation"), f"{label}.expectation")
        if error:
            errors.append(error)
        if "followups" in case:
            if app_type not in {None, 'agent', 'advanced-chat'}:
                errors.append(f'{label}多轮验收仅适用于 Chatflow／原生 Agent。')
            followups = case['followups']
            if not isinstance(followups, list) or not 1 <= len(followups) <= 9:
                errors.append(f'{label}.followups须为 1—9 个后续轮次，总计最多 10 轮。')
                continue
            for turn_index, turn in enumerate([case, *followups]):
                turn_label = f'{label}第{turn_index + 1}轮'
                if not isinstance(turn, dict) or (turn_index and set(turn) != {'input', 'expectation'}):
                    errors.append(f'{turn_label}须为只含 input、expectation 的对象。')
                    continue
                value = turn.get('input')
                if not isinstance(value, dict) or not isinstance(value.get('query'), str) or not value['query'].strip() or 'conversation_id' in value:
                    errors.append(f'{turn_label}须有非空 query，不能手填 conversation_id。')
                elif app_type == 'agent' and set(value) != {'query'}:
                    errors.append(f'{turn_label}原生 Agent 仅支持 query，不支持变量或文件。')
                if turn_index:
                    error = _expectation_error(turn.get('expectation'), turn_label + '.expectation')
                    if error: errors.append(error)
    return {"valid": not errors, "errors": errors}


def _lookup_path(actual: Any, target: str) -> tuple[bool, Any]:
    value = actual
    for part in target.split("."):
        if type(value) is not dict or part not in value:
            return False, None
        value = value[part]
    return True, value


def _strict_json_object(value: str) -> dict[str, Any] | None:
    def reject_constant(constant: str) -> None:
        raise ValueError(f"非法JSON常量：{constant}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("JSON对象含重复键")
            result[key] = item
        return result

    try:
        parsed = json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique_object, parse_float=wire_float)
    except (ValueError, TypeError, RecursionError):
        return None
    if type(parsed) is not dict or _json_value_error(parsed):
        return None
    return parsed


def _contains_text_leaves(value: Any, needles: list[str]) -> bool:
    """Search string values only; never stringify objects for pseudo-matches."""
    if isinstance(value, str):
        return all(needle in value for needle in needles)
    if type(value) is list:
        return all(any(_contains_text_leaves(item, [needle]) for item in value) for needle in needles)
    if type(value) is dict:
        return all(any(_contains_text_leaves(item, [needle]) for item in value.values()) for needle in needles)
    return False


def _preview(value: Any) -> tuple[Any, bool]:
    """Bound returned output size after adjudication, preserving JSON shape."""
    try:
        serialized = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        serialized.encode('utf-8')
    except (TypeError, ValueError, RecursionError):
        return {"preview_unavailable": True}, True
    if len(serialized) <= _MAX_PREVIEW_CHARS:
        return value, False
    return {"truncated": True, "preview": serialized[:_MAX_PREVIEW_CHARS]}, True


EQUALITY_VERSION = 2


def strict_json_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):return False
    if type(left) is dict:return left.keys()==right.keys() and all(strict_json_equal(left[k],right[k]) for k in left)
    if type(left) is list:return len(left)==len(right) and all(strict_json_equal(a,b) for a,b in zip(left,right))
    return left==right


def evaluate_output(actual: dict, expectation: dict) -> dict:
    """Evaluate one declared expectation; never execute expressions or code."""
    shown_actual, truncated = _preview(actual)
    invalid = _expectation_error(expectation, "expectation")
    if invalid:
        return {"status": "failed", "details": invalid, "actual": shown_actual, "mode": str(expectation.get("mode", "invalid")) if type(expectation) is dict else "invalid"}

    mode = expectation["mode"]
    if mode == "manual":
        detail = "该用例需要人工审核：" + expectation["description"].strip()
        if truncated:
            detail += "；返回的actual预览已截断，判定基于完整输出"
        return {"status": "needs_review", "details": detail, "actual": shown_actual, "mode": mode}

    actual_error = _json_value_error(actual)
    if type(actual) is not dict or actual_error:
        return {
            "status": "failed",
            "details": "actual必须是有效的JSON对象" + (f"：{actual_error}" if actual_error else ""),
            "actual": shown_actual,
            "mode": mode,
        }

    found, value = _lookup_path(actual, expectation["target"])
    if not found:
        passed = False
        reason = f"未找到目标路径 {expectation['target']}"
    elif mode == "contains":
        expected = expectation["expected"]
        needles = [expected] if isinstance(expected, str) else expected
        passed = _contains_text_leaves(value, needles)
        reason = "目标包含所有指定文本" if passed else "目标未包含所有指定文本"
    elif mode == "equals":
        passed = strict_json_equal(value, expectation["expected"])
        reason = "目标与期望值相等" if passed else "目标与期望值不相等或类型不同"
    elif mode == "json_schema":
        from .json_inputs import validate_value, MAX_BYTES
        passed=False
        reason="目标未通过已声明的完整对象Schema；未修复JSON、补默认或丢弃字段"
        try:
            if isinstance(value,str):
                if len(value.encode('utf-8'))>MAX_BYTES:raise ValueError('JSON文字超过64000字节，不截断。')
                obj=_strict_json_object(value)
                if obj is None:raise ValueError('目标JSON文字无法核对完整唯一键、有限及无损数值；不去Markdown、舍入、截取或修复。')
            else:obj=value
            validate_value(expectation["expected"],obj)
            passed=True
            reason="目标通过已声明的完整对象Schema（仅本机结果核对，不是Dify入口强制规则）"
        except UnicodeError:reason='目标JSON文字编码无效，未使用原文错误回显。'
        except ValueError as exc:
            reason=str(exc).replace('JSON对象输入','输出对象').replace('JSON入口','输出Schema')
            reason+=' 仅本机结果检查，未自动修改或重跑。'
    else:  # json_keys
        obj = _strict_json_object(value) if isinstance(value, str) else value
        passed = type(obj) is dict and all(key in obj for key in expectation["expected"])
        reason = "对象含有所有指定键" if passed else "目标不是有效JSON对象或缺少指定键"

    details = reason
    if passed:
        details += "；该关键词或结构规则命中仅证明声明的规则成立，不代表完整业务正确性"
    if truncated:
        details += "；返回的actual预览已截断，判定基于完整输出"
    return {
        **({"comparison_version": EQUALITY_VERSION} if mode == "equals" else {}),
        "status": "passed" if passed else "failed",
        "details": details,
        "actual": shown_actual,
        "mode": mode,
    }
