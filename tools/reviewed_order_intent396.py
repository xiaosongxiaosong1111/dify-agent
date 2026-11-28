"""Reviewed, memory-only order-intent instruction amendment for saved plan copies.

Pure functions only.  Importing this module has no side effect: it never reads or
writes files, creates stores or configuration, contacts the network, calls a model,
runs Dify or authorizes anything.  ``amend_pair`` deep-copies two caller-supplied
JSON plan objects in memory and replaces exactly one field, the ``classify``
question-classifier ``instruction``, in both copies.

The caller (Root) is responsible for binding each input to the reviewed full-source
SHA256 (the original plan ``dd71f629c0d6a1e82d8e88aa424341fbe751369fbe0cedf19a9f1b5f44198c69``
and the modified plan ``3940d849...``) before calling.  This module deliberately has
no hidden binding, force switch, approval mechanism or external side-effect
permission of its own.

Static checks here only prove the reviewed wording and structure.  They do not prove
the real model's classification quality, a real Dify import, or that any remaining
two-version difference is acceptable in business terms.
"""
from __future__ import annotations

import copy
import json
import math

# Reviewed old value, byte-for-byte equal to the saved public snippet of run 395.
OLD_INSTRUCTION = "判断用户本轮诉求属于：1)售后资料／政策问答；2)查询模拟订单状态（用户本轮给出或明确要求查询订单号，或结合上文的订单查询话题）；3)其它范围外请求（例如预订、支付、真实订单、闲聊等）。没有订单上下文时，孤立的编号不要自动当作订单。"

# Root-reviewed replacement text.  Keep this literal verbatim; do not append notes.
NEW_INSTRUCTION = "按用户本轮的主要业务诉求分类：faq为售后资料、政策和规则问答，即使提到订单也不等于查询订单状态；order为查询某个订单的当前状态、物流或发货进度。普通订单查询无论是否提供订单号、是否说“模拟”，都进入order；缺号由后续流程追问，不得因缺号或未说“模拟”判为范围外。所有订单查询始终使用模拟接口，归入order不表示接入真实系统。out_of_scope为预订、支付、闲聊等不支持的诉求，以及明确要求连接、接入或操作真实订单系统或外部真实订单接口的请求；不要把普通订单查询等同于这种真实系统接入要求。没有订单上下文时，孤立编号不要自动当作订单查询。"

OLD_NO_HIT_TEXT = "知识库暂无相关信息，请联系人工客服。"
NEW_NO_HIT_TEXT = "知识库暂无相关信息，请联系人工客服并提供商品型号。"

QUERY_SELECTOR = ["sys", "query"]
UNMATCHED_POLICY = {"behavior": "first_class", "class_id": "faq"}
CLASSES = (
    {"id": "faq", "name": "售后资料问答", "label": "售后资料问答"},
    {"id": "order", "name": "模拟订单查询", "label": "模拟订单查询"},
    {"id": "out_of_scope", "name": "范围外", "label": "范围外"},
)

CLASSIFY_ID = "classify"
NO_HIT_ID = "no_hit_text"
FAQ_LLM_ID = "faq_llm"

_PAIR_MARK = "\u0001__reviewed_order_intent396_pair__\u0001"
_MAX_DEPTH = 500
_MAX_ITEMS = 2_000_000


def _check_json(value):
    """Reject anything that is not strict, acyclic JSON (no NaN, tuples, sets...)."""
    seen = set()
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > _MAX_ITEMS:
            raise ValueError("输入规模超出本机纯函数处理上限，拒绝。")
        if depth > _MAX_DEPTH:
            raise ValueError("输入嵌套过深，拒绝。")
        if isinstance(item, dict):
            if id(item) in seen:
                raise ValueError("输入不是可序列化 JSON：存在循环引用。")
            seen.add(id(item))
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("输入 JSON 对象的键必须全部是字符串。")
                stack.append((child, depth + 1))
        elif isinstance(item, list):
            if id(item) in seen:
                raise ValueError("输入不是可序列化 JSON：存在循环引用。")
            seen.add(id(item))
            for child in item:
                stack.append((child, depth + 1))
        elif isinstance(item, bool) or item is None or isinstance(item, str):
            continue
        elif isinstance(item, int):
            continue
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("输入包含 NaN／Infinity，不是严格 JSON。")
        else:
            raise ValueError(f"输入包含非 JSON 类型 {type(item).__name__}，拒绝。")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _same(left, right):
    return _canonical(left) == _canonical(right)


def _format_path(path):
    if not path:
        return "$"
    text = "$"
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else f".{part}"
    return text


def _first_diff(left, right, path=()):
    """Return the first path where two strict-JSON values differ, or None."""
    if type(left) is not type(right):
        return path
    if isinstance(left, dict):
        if set(left) != set(right):
            return path
        for key in sorted(left):
            found = _first_diff(left[key], right[key], path + (key,))
            if found is not None:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return path
        for index, (a, b) in enumerate(zip(left, right)):
            found = _first_diff(a, b, path + (index,))
            if found is not None:
                return found
        return None
    return None if left == right else path


def _collect_nodes(root, node_id):
    hits = []
    stack = [root]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if current.get("id") == node_id:
                hits.append(current)
            stack.extend(value for value in current.values() if isinstance(value, (dict, list)))
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return hits


def _unique_node(root, node_id):
    hits = _collect_nodes(root, node_id)
    if len(hits) != 1:
        raise ValueError(f"输入必须包含且仅包含一个 id={node_id!r} 的节点，实际 {len(hits)} 个。")
    node = hits[0]
    if not isinstance(node.get("type"), str) or not isinstance(node.get("config"), dict):
        raise ValueError(f"节点 {node_id!r} 必须声明文字 type 与对象 config。")
    return node


def _expected_classes():
    return [dict(row) for row in CLASSES]


def _check_classifier(root):
    node = _unique_node(root, CLASSIFY_ID)
    if node["type"] != "question-classifier":
        raise ValueError(f"节点 {CLASSIFY_ID!r} 的类型必须是 question-classifier。")
    cfg = node["config"]
    if not _same(cfg.get("classes"), _expected_classes()):
        raise ValueError("分类类别 id／name／label 或顺序与已审阅值不逐值相等，拒绝修改未知来源。")
    if not _same(cfg.get("query_variable_selector"), QUERY_SELECTOR):
        raise ValueError("分类 query_variable_selector 必须恰为 [\"sys\", \"query\"]。")
    if not _same(cfg.get("unmatched_policy"), UNMATCHED_POLICY):
        raise ValueError("分类 unmatched_policy 必须恰为 {behavior:first_class,class_id:faq}。")
    instruction = cfg.get("instruction")
    if not isinstance(instruction, str):
        raise ValueError("分类 instruction 必须是文字，缺失或类型不符时拒绝。")
    if instruction == NEW_INSTRUCTION:
        raise ValueError("输入已带本批新 instruction；本函数只接受公开片段保存的旧值。")
    if instruction != OLD_INSTRUCTION:
        raise ValueError("分类 instruction 与公开片段保存值不逐字相等，拒绝静默归一化或改写未知来源。")
    return node


def _check_pair_texts(original, modified):
    original_hit = _unique_node(original, NO_HIT_ID)["config"]
    modified_hit = _unique_node(modified, NO_HIT_ID)["config"]
    if not isinstance(original_hit.get("template"), str) or original_hit["template"] != OLD_NO_HIT_TEXT:
        raise ValueError("original 的 no_hit_text.config.template 必须恰为已保存旧文案。")
    if not isinstance(modified_hit.get("template"), str) or modified_hit["template"] != NEW_NO_HIT_TEXT:
        raise ValueError("modified 的 no_hit_text.config.template 必须恰为已审阅新文案。")
    original_prompt = _unique_node(original, FAQ_LLM_ID)["config"].get("system_prompt")
    modified_prompt = _unique_node(modified, FAQ_LLM_ID)["config"].get("system_prompt")
    if not isinstance(original_prompt, str) or original_prompt.count(OLD_NO_HIT_TEXT) != 1:
        raise ValueError("original 的 faq_llm.config.system_prompt 必须恰出现一次旧文案句子。")
    if not isinstance(modified_prompt, str) or modified_prompt.count(NEW_NO_HIT_TEXT) != 1:
        raise ValueError("modified 的 faq_llm.config.system_prompt 必须恰出现一次新文案句子。")
    if _PAIR_MARK in original_prompt or _PAIR_MARK in modified_prompt:
        raise ValueError("输入文案包含本函数的规范化标记，拒绝。")
    normalized_original = copy.deepcopy(original)
    normalized_modified = copy.deepcopy(modified)
    _unique_node(normalized_original, NO_HIT_ID)["config"]["template"] = None
    _unique_node(normalized_modified, NO_HIT_ID)["config"]["template"] = None
    _unique_node(normalized_original, FAQ_LLM_ID)["config"]["system_prompt"] = original_prompt.replace(
        OLD_NO_HIT_TEXT, _PAIR_MARK, 1
    )
    _unique_node(normalized_modified, FAQ_LLM_ID)["config"]["system_prompt"] = modified_prompt.replace(
        NEW_NO_HIT_TEXT, _PAIR_MARK, 1
    )
    diff = _first_diff(normalized_original, normalized_modified)
    if diff is not None:
        raise ValueError(f"输入 pair 除两处已审无答案文案外仍有差异：{_format_path(diff)}")


def _expected_after(before):
    expected = copy.deepcopy(before)
    _unique_node(expected, CLASSIFY_ID)["config"]["instruction"] = NEW_INSTRUCTION
    return expected


def amend_pair(original, modified):
    """Return amended deep copies; only classify.config.instruction changes.

    Both inputs must be strict JSON plan objects with exactly the reviewed old
    classifier field values and a pair that differs only in the two reviewed
    answer texts.  Inputs are never mutated.  Nothing is persisted or executed.
    """
    _check_json(original)
    _check_json(modified)
    if not isinstance(original, dict) or not isinstance(modified, dict):
        raise ValueError("两个输入都必须是 JSON 对象（已保存计划图）。")
    _check_classifier(original)
    _check_classifier(modified)
    _check_pair_texts(original, modified)

    original_copy = copy.deepcopy(original)
    modified_copy = copy.deepcopy(modified)
    _unique_node(original_copy, CLASSIFY_ID)["config"]["instruction"] = NEW_INSTRUCTION
    _unique_node(modified_copy, CLASSIFY_ID)["config"]["instruction"] = NEW_INSTRUCTION

    for before, after, label in (
        (original, original_copy, "original"),
        (modified, modified_copy, "modified"),
    ):
        diff = _first_diff(after, _expected_after(before))
        if diff is not None:
            raise RuntimeError(f"{label} 输出相对输入仍有多余差异：{_format_path(diff)}")
    try:
        _check_pair_texts(original_copy, modified_copy)
    except ValueError as exc:
        raise RuntimeError(f"输出 pair 未保持仅两处无答案文案差异：{exc}") from exc
    return original_copy, modified_copy
