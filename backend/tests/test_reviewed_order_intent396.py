import ast
import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "reviewed_order_intent396.py"
_SPEC = importlib.util.spec_from_file_location("reviewed_order_intent396", MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
REVIEWED = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(REVIEWED)

OLD_INSTRUCTION = "判断用户本轮诉求属于：1)售后资料／政策问答；2)查询模拟订单状态（用户本轮给出或明确要求查询订单号，或结合上文的订单查询话题）；3)其它范围外请求（例如预订、支付、真实订单、闲聊等）。没有订单上下文时，孤立的编号不要自动当作订单。"
NEW_INSTRUCTION = "按用户本轮的主要业务诉求分类：faq为售后资料、政策和规则问答，即使提到订单也不等于查询订单状态；order为查询某个订单的当前状态、物流或发货进度。普通订单查询无论是否提供订单号、是否说“模拟”，都进入order；缺号由后续流程追问，不得因缺号或未说“模拟”判为范围外。所有订单查询始终使用模拟接口，归入order不表示接入真实系统。out_of_scope为预订、支付、闲聊等不支持的诉求，以及明确要求连接、接入或操作真实订单系统或外部真实订单接口的请求；不要把普通订单查询等同于这种真实系统接入要求。没有订单上下文时，孤立编号不要自动当作订单查询。"
OLD_NO_HIT = "知识库暂无相关信息，请联系人工客服。"
NEW_NO_HIT = "知识库暂无相关信息，请联系人工客服并提供商品型号。"
OLD_SYSTEM_PROMPT = "你是售后助手。知识库暂无相关信息，请联系人工客服。请勿编造订单信息。"
NEW_SYSTEM_PROMPT = OLD_SYSTEM_PROMPT.replace(OLD_NO_HIT, NEW_NO_HIT)


def _plan(instruction=None, no_hit=None, system_prompt=None, temperature=0.2, marker=1, ratio=1.0, flag=False):
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "config": {"variables": [{"variable": "query", "type": "text"}]}},
            {
                "id": "entry_probe",
                "type": "code",
                "config": {
                    "code_language": "python3",
                    "code": "def main(query):\n    return {'stripped_query': (query or '').strip()}\n",
                    "variables": [{"variable": "query", "value_selector": ["sys", "query"]}],
                    "outputs": {"stripped_query": {"type": "string", "children": None}},
                },
            },
            {
                "id": "classify",
                "type": "question-classifier",
                "config": {
                    "query_variable_selector": ["sys", "query"],
                    "classes": [
                        {"id": "faq", "name": "售后资料问答", "label": "售后资料问答"},
                        {"id": "order", "name": "模拟订单查询", "label": "模拟订单查询"},
                        {"id": "out_of_scope", "name": "范围外", "label": "范围外"},
                    ],
                    "unmatched_policy": {"behavior": "first_class", "class_id": "faq"},
                    "instruction": OLD_INSTRUCTION if instruction is None else instruction,
                    "model": {
                        "provider": "langgenius/deepseek/deepseek",
                        "name": "deepseek-flash",
                        "mode": "chat",
                        "completion_params": {"temperature": temperature, "max_tokens": 512, "thinking": False},
                    },
                    "memory": {"query_prompt_template": "{{#sys.query#}}", "window": {"enabled": True, "size": 6}},
                },
            },
            {
                "id": "no_hit_text",
                "type": "template-transform",
                "config": {"template": OLD_NO_HIT if no_hit is None else no_hit, "variables": []},
            },
            {
                "id": "faq_llm",
                "type": "llm",
                "config": {
                    "system_prompt": OLD_SYSTEM_PROMPT if system_prompt is None else system_prompt,
                    "user_prompt": "{{#sys.query#}}",
                    "count": marker,
                    "ratio": ratio,
                    "enabled": flag,
                    "note": "订单 DEMO-001，模拟入口",
                },
            },
            {"id": "out_of_scope_text", "type": "template-transform", "config": {"template": "暂不支持该请求。", "variables": []}},
            {"id": "answer_out_of_scope", "type": "answer", "config": {"answer": "{{#out_of_scope_text.output#}}"}},
            {"id": "end", "type": "end", "config": {"outputs": []}},
        ],
        "edges": [
            {"source": "start", "target": "classify", "source_handle": "source", "target_handle": "target"},
            {"source": "classify", "target": "faq_llm", "source_handle": "faq"},
            {"source": "classify", "target": "no_hit_text", "source_handle": "order"},
            {"source": "classify", "target": "out_of_scope_text", "source_handle": "out_of_scope"},
            {"source": "out_of_scope_text", "target": "answer_out_of_scope", "source_handle": "source"},
            {"source": "answer_out_of_scope", "target": "end", "source_handle": "source"},
        ],
        "conversation_variables": [
            {"id": "order_wait_requested", "name": "order_wait_requested", "value_type": "boolean", "value": False},
        ],
    }


def _pair():
    return _plan(), _plan(no_hit=NEW_NO_HIT, system_prompt=NEW_SYSTEM_PROMPT)


def _node(plan, node_id):
    matches = [node for node in plan["nodes"] if node["id"] == node_id]
    assert len(matches) == 1
    return matches[0]


def _mutate(plan, node_id, mutator):
    out = copy.deepcopy(plan)
    mutator(_node(out, node_id))
    return out


def _diff_paths(left, right, path=()):
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        if set(left) != set(right):
            return [path]
        found = []
        for key in sorted(left):
            found.extend(_diff_paths(left[key], right[key], path + (key,)))
        return found
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        found = []
        for index, (a, b) in enumerate(zip(left, right)):
            found.extend(_diff_paths(a, b, path + (index,)))
        return found
    return [] if left == right else [path]


class ReviewedOrderIntent396Tests(unittest.TestCase):
    def test_reviewed_constants_are_pinned_verbatim(self):
        self.assertEqual(REVIEWED.OLD_INSTRUCTION, OLD_INSTRUCTION)
        self.assertEqual(REVIEWED.NEW_INSTRUCTION, NEW_INSTRUCTION)
        self.assertEqual(REVIEWED.OLD_NO_HIT_TEXT, OLD_NO_HIT)
        self.assertEqual(REVIEWED.NEW_NO_HIT_TEXT, NEW_NO_HIT)

    def test_module_imports_only_stdlib_and_has_no_side_effect_dependencies(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        self.assertLessEqual(imported, {"__future__", "copy", "json", "math"})

    def test_only_classifier_instruction_changes_in_each_copy(self):
        original, modified = _pair()
        original_out, modified_out = REVIEWED.amend_pair(original, modified)
        expected = [("nodes", 2, "config", "instruction")]
        self.assertEqual(_diff_paths(original_out, original), expected)
        self.assertEqual(_diff_paths(modified_out, modified), expected)
        self.assertEqual(_node(original_out, "classify")["config"]["instruction"], NEW_INSTRUCTION)
        self.assertEqual(_node(modified_out, "classify")["config"]["instruction"], NEW_INSTRUCTION)

    def test_pair_still_differs_only_in_the_two_reviewed_answer_texts(self):
        original, modified = _pair()
        original_out, modified_out = REVIEWED.amend_pair(original, modified)
        self.assertEqual(
            _diff_paths(original_out, modified_out),
            [("nodes", 3, "config", "template"), ("nodes", 4, "config", "system_prompt")],
        )
        self.assertEqual(_node(original_out, "no_hit_text")["config"]["template"], OLD_NO_HIT)
        self.assertEqual(_node(modified_out, "no_hit_text")["config"]["template"], NEW_NO_HIT)
        self.assertEqual(_node(original_out, "faq_llm")["config"]["system_prompt"], OLD_SYSTEM_PROMPT)
        self.assertEqual(_node(modified_out, "faq_llm")["config"]["system_prompt"], NEW_SYSTEM_PROMPT)

    def test_inputs_are_not_mutated(self):
        original, modified = _pair()
        original_before, modified_before = copy.deepcopy(original), copy.deepcopy(modified)
        REVIEWED.amend_pair(original, modified)
        self.assertEqual(_diff_paths(original, original_before), [])
        self.assertEqual(_diff_paths(modified, modified_before), [])

    def test_returns_fresh_objects_and_preserves_value_types(self):
        original, modified = _pair()
        original_out, modified_out = REVIEWED.amend_pair(original, modified)
        self.assertIsNot(original_out, original)
        self.assertIsNot(modified_out, modified)
        for out in (original_out, modified_out):
            llm = _node(out, "faq_llm")["config"]
            self.assertIs(type(llm["count"]), int)
            self.assertIs(type(llm["ratio"]), float)
            self.assertIs(llm["enabled"], False)
            self.assertEqual(llm["note"], "订单 DEMO-001，模拟入口")
            classify = _node(out, "classify")["config"]
            self.assertEqual(classify["query_variable_selector"], ["sys", "query"])
            self.assertEqual(classify["unmatched_policy"], {"behavior": "first_class", "class_id": "faq"})
            self.assertIs(classify["model"]["completion_params"]["thinking"], False)
            self.assertEqual(_node(out, "entry_probe")["config"]["code"], "def main(query):\n    return {'stripped_query': (query or '').strip()}\n")

    def test_numeric_type_drift_between_pair_is_rejected(self):
        original, modified = _pair()
        modified = _mutate(modified, "faq_llm", lambda node: node["config"].__setitem__("ratio", 1))
        with self.assertRaises(ValueError):
            REVIEWED.amend_pair(original, modified)

    def test_bool_type_drift_between_pair_is_rejected(self):
        original, modified = _pair()
        modified = _mutate(modified, "faq_llm", lambda node: node["config"].__setitem__("enabled", 0))
        with self.assertRaises(ValueError):
            REVIEWED.amend_pair(original, modified)

    def test_extra_model_parameter_drift_between_pair_is_rejected(self):
        original, modified = _pair()
        modified = _mutate(modified, "classify", lambda node: node["config"]["model"]["completion_params"].__setitem__("temperature", 0.3))
        with self.assertRaises(ValueError):
            REVIEWED.amend_pair(original, modified)

    def test_extra_edge_between_pair_is_rejected(self):
        original, modified = _pair()
        modified["edges"].append({"source": "faq_llm", "target": "end", "source_handle": "source"})
        with self.assertRaises(ValueError):
            REVIEWED.amend_pair(original, modified)

    def test_already_amended_instruction_is_rejected(self):
        amended = _plan(instruction=NEW_INSTRUCTION)
        with self.assertRaises(ValueError):
            REVIEWED.amend_pair(amended, copy.deepcopy(amended))

    def test_unknown_instruction_is_rejected_not_normalized(self):
        other = _plan(instruction=OLD_INSTRUCTION + " ")
        with self.assertRaises(ValueError):
            REVIEWED.amend_pair(other, copy.deepcopy(other))

    def test_missing_or_duplicate_or_mistyped_classifier_is_rejected(self):
        original, modified = _pair()
        missing = copy.deepcopy(original)
        missing["nodes"] = [node for node in missing["nodes"] if node["id"] != "classify"]
        duplicate = copy.deepcopy(original)
        duplicate["nodes"].append(copy.deepcopy(_node(duplicate, "classify")))
        mistyped = _mutate(original, "classify", lambda node: node.__setitem__("type", "llm"))
        for label, bad in (("missing", missing), ("duplicate", duplicate), ("mistyped", mistyped)):
            with self.subTest(kind=label):
                with self.assertRaises(ValueError):
                    REVIEWED.amend_pair(bad, copy.deepcopy(modified))

    def test_class_id_order_or_labels_drift_is_rejected(self):
        original, modified = _pair()
        wrong_order = _mutate(original, "classify", lambda node: node["config"]["classes"].reverse())
        wrong_id = _mutate(original, "classify", lambda node: node["config"]["classes"][1].__setitem__("id", "real_order"))
        wrong_name = _mutate(original, "classify", lambda node: node["config"]["classes"][1].__setitem__("name", "订单查询"))
        wrong_label = _mutate(original, "classify", lambda node: node["config"]["classes"][2].__setitem__("label", "其它"))
        for bad in (wrong_order, wrong_id, wrong_name, wrong_label):
            with self.assertRaises(ValueError):
                REVIEWED.amend_pair(bad, copy.deepcopy(modified))

    def test_selector_and_unmatched_policy_drift_is_rejected(self):
        original, modified = _pair()
        wrong_selector = _mutate(original, "classify", lambda node: node["config"].__setitem__("query_variable_selector", ["sys", "query "]))
        wrong_policy = _mutate(original, "classify", lambda node: node["config"].__setitem__("unmatched_policy", {"behavior": "first_class", "class_id": "order"}))
        for bad in (wrong_selector, wrong_policy):
            with self.assertRaises(ValueError):
                REVIEWED.amend_pair(bad, copy.deepcopy(modified))

    def test_missing_or_wrong_no_hit_node_is_rejected(self):
        original, modified = _pair()
        missing = copy.deepcopy(original)
        missing["nodes"] = [node for node in missing["nodes"] if node["id"] != "no_hit_text"]
        duplicate = copy.deepcopy(original)
        duplicate["nodes"].append(copy.deepcopy(_node(duplicate, "no_hit_text")))
        wrong_old = _mutate(original, "no_hit_text", lambda node: node["config"].__setitem__("template", "别的文案。"))
        wrong_new = _mutate(modified, "no_hit_text", lambda node: node["config"].__setitem__("template", OLD_NO_HIT))
        for bad in (missing, duplicate, wrong_old):
            with self.assertRaises(ValueError):
                REVIEWED.amend_pair(bad, copy.deepcopy(modified))
        with self.assertRaises(ValueError):
            REVIEWED.amend_pair(copy.deepcopy(original), wrong_new)

    def test_faq_llm_sentence_count_must_be_exactly_one(self):
        original, modified = _pair()
        doubled = _mutate(original, "faq_llm", lambda node: node["config"].__setitem__("system_prompt", OLD_SYSTEM_PROMPT + OLD_NO_HIT))
        absent_old = _mutate(original, "faq_llm", lambda node: node["config"].__setitem__("system_prompt", "你是售后助手。请勿编造订单信息。"))
        missing_new = _mutate(modified, "faq_llm", lambda node: node["config"].__setitem__("system_prompt", OLD_SYSTEM_PROMPT))
        for bad_original, bad_modified in ((doubled, modified), (absent_old, modified), (original, missing_new)):
            with self.assertRaises(ValueError):
                REVIEWED.amend_pair(bad_original, bad_modified)

    def test_non_json_inputs_are_rejected(self):
        original, modified = _pair()
        nan_plan = copy.deepcopy(original)
        _node(nan_plan, "faq_llm")["config"]["ratio"] = float("nan")
        tuple_plan = copy.deepcopy(original)
        _node(tuple_plan, "faq_llm")["config"]["note"] = ("订单",)
        deep_key_plan = copy.deepcopy(original)
        deep_key_plan[1] = "not-a-key"
        for bad in (nan_plan, tuple_plan, deep_key_plan, [original]):
            with self.assertRaises(ValueError):
                REVIEWED.amend_pair(bad, copy.deepcopy(modified))

    def test_wrong_node_payload_shape_is_rejected(self):
        original, modified = _pair()
        no_config = copy.deepcopy(original)
        _node(no_config, "classify")["config"] = "not-an-object"
        no_type = copy.deepcopy(original)
        del _node(no_type, "classify")["type"]
        for bad in (no_config, no_type):
            with self.assertRaises(ValueError):
                REVIEWED.amend_pair(bad, copy.deepcopy(modified))


if __name__ == "__main__":
    unittest.main()
