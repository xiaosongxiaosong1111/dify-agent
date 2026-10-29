from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workflow_plan import SUPPORTED_PLAN_NODES, compile_workflow_plan, validate_plan


def task(app_type: str = "workflow") -> dict:
    return {
        "name": "售后流程",
        "app_type": app_type,
        "configuration": {
            "dify_model_provider": "langgenius/deepseek/deepseek",
            "dify_model": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 1024,
            "dataset_ids": ["dataset-existing"],
            "retrieval_top_k": 4,
        },
    }


def start(app_type: str = "workflow") -> dict:
    variables = [] if app_type == "advanced-chat" else [
        {"variable": "query", "label": "query", "type": "text-input", "required": True},
    ]
    return {"id": "start", "type": "start", "title": "开始", "config": {"variables": variables}}


def llm(node_id: str = "llm", user_prompt: str = "{{#start.query#}}", **config) -> dict:
    return {
        "id": node_id,
        "type": "llm",
        "title": "回答",
        "config": {"system_prompt": "按规则回答", "user_prompt": user_prompt, **config},
    }


def end(node_id: str = "end", selector=None) -> dict:
    return {
        "id": node_id,
        "type": "end",
        "title": "结束",
        "config": {"outputs": [{"variable": "result", "value_selector": selector or ["llm", "text"]}]},
    }


def base_plan(app_type: str = "workflow") -> dict:
    user_prompt = "{{#sys.query#}}" if app_type == "advanced-chat" else "{{#start.query#}}"
    terminal = (
        {"id": "answer", "type": "answer", "title": "回复", "config": {"answer": "{{#llm.text#}}"}}
        if app_type == "advanced-chat"
        else end()
    )
    return {
        "schema_version": 1,
        "nodes": [start(app_type), llm(user_prompt=user_prompt), terminal],
        "edges": [
            {"source": "start", "target": "llm"},
            {"source": "llm", "target": terminal["id"]},
        ],
    }


def plan_task(plan: dict, app_type: str = "workflow") -> dict:
    return {**task(app_type), "workflow_plan": plan}


def parse_yaml(text: str) -> dict:
    return yaml.safe_load(text)


def test_supported_node_types_are_explicit() -> None:
    assert SUPPORTED_PLAN_NODES == (
        "start", "trigger-schedule", "human-input", "llm", "question-classifier", "parameter-extractor", "list-operator", "document-extractor", "knowledge-retrieval", "if-else", "code",
        "template-transform", "http-request", "iteration", "loop", "variable-aggregator", "assigner", "end", "answer",
    )


def test_optional_custom_input_preserves_empty_default() -> None:
    plan = base_plan()
    plan["nodes"][0]["config"]["variables"] = [{"variable": "document", "type": "paragraph", "required": False, "default": ""}]
    plan["nodes"][1]["config"]["user_prompt"] = "{{#start.document#}}"
    text, result = compile_workflow_plan(plan_task(plan))
    assert result["valid"], result["errors"]
    variable = parse_yaml(text)["workflow"]["graph"]["nodes"][0]["data"]["variables"][0]
    assert variable["variable"] == "document" and variable["required"] is False and variable["default"] == ""


def test_input_free_constant_workflow_is_valid() -> None:
    plan = base_plan()
    plan["nodes"][0]["config"]["variables"] = []
    plan["nodes"][1]["config"]["user_prompt"] = "输出固定的欢迎文本"
    assert validate_plan(task(), plan)["valid"]


def test_invalid_input_metadata_is_not_silently_coerced() -> None:
    for patch in ({"required": "false"}, {"default": None}, {"type": "unsupported"}):
        plan = base_plan()
        plan["nodes"][0]["config"]["variables"][0].update(patch)
        assert not validate_plan(task(), plan)["valid"]


def test_compile_linear_workflow_with_real_task_model_config() -> None:
    content, validation = compile_workflow_plan(plan_task(base_plan()))
    dsl = parse_yaml(content)
    assert validation["valid"]
    assert dsl["version"] == "0.7.0"
    assert dsl["app"]["mode"] == "workflow"
    nodes = {node["id"]: node for node in dsl["workflow"]["graph"]["nodes"]}
    assert nodes["llm"]["data"]["model"]["provider"] == "langgenius/deepseek/deepseek"
    assert nodes["llm"]["data"]["model"]["name"] == "deepseek-chat"


def test_compile_chatflow_uses_system_query_and_answer() -> None:
    content, validation = compile_workflow_plan(plan_task(base_plan("advanced-chat"), "advanced-chat"))
    dsl = parse_yaml(content)
    nodes = {node["id"]: node for node in dsl["workflow"]["graph"]["nodes"]}
    assert validation["valid"]
    assert dsl["app"]["mode"] == "advanced-chat"
    assert nodes["llm"]["data"]["prompt_template"][-1]["text"] == "{{#sys.query#}}"
    assert nodes["answer"]["data"]["answer"] == "{{#llm.text#}}"


def test_retrieval_uses_explicit_ids_and_fallback_top_k() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "retrieve", "type": "knowledge-retrieval", "title": "检索", "config": {},
    })
    plan["nodes"][2]["config"]["context_variable_selector"] = ["retrieve", "result"]
    plan["nodes"][2]["config"]["user_prompt"] += " 资料：{{#context#}}"
    plan["edges"] = [
        {"source": "start", "target": "retrieve"},
        {"source": "retrieve", "target": "llm"},
        {"source": "llm", "target": "end"},
    ]
    content, validation = compile_workflow_plan(plan_task(plan))
    dsl = parse_yaml(content)
    retrieve = next(n for n in dsl["workflow"]["graph"]["nodes"] if n["id"] == "retrieve")["data"]
    assert validation["valid"]
    assert retrieve["dataset_ids"] == ["dataset-existing"]
    assert retrieve["multiple_retrieval_config"]["top_k"] == 4
    assert retrieve["query_variable_selector"] == ["start", "query"]


def test_if_else_native_branches_require_case_and_false_edges() -> None:
    plan = {
        "schema_version": 1,
        "nodes": [
            start(),
            {
                "id": "route", "type": "if-else", "title": "订单判断", "config": {"cases": [
                    {"case_id": "orders", "logical_operator": "and", "conditions": [
                        {"variable_selector": ["start", "query"], "comparison_operator": "contains", "value": "订单", "varType": "string"},
                    ]},
                ]},
            },
            llm("order", "订单处理"),
            llm("other", "一般处理"),
            end("order_end", ["order", "text"]),
            end("other_end", ["other", "text"]),
        ],
        "edges": [
            {"source": "start", "target": "route"},
            {"source": "route", "source_handle": "orders", "target": "order"},
            {"source": "route", "source_handle": "false", "target": "other"},
            {"source": "order", "target": "order_end"},
            {"source": "other", "target": "other_end"},
        ],
    }
    validation = validate_plan(task(), plan)
    assert validation["valid"], validation["errors"]
    content, _ = compile_workflow_plan(plan_task(plan))
    native = parse_yaml(content)["workflow"]["graph"]
    route = next(n for n in native["nodes"] if n["id"] == "route")["data"]
    assert [branch["id"] for branch in route["_targetBranches"]] == ["orders", "false"]
    assert {e["sourceHandle"] for e in native["edges"] if e["source"] == "route"} == {"orders", "false"}


def test_if_else_missing_case_or_false_exit_is_invalid() -> None:
    plan = {
        "schema_version": 1,
        "nodes": [start(), {
            "id": "route", "type": "if-else", "config": {"cases": [
                {"case_id": "yes", "logical_operator": "and", "conditions": [
                    {"variable_selector": ["start", "query"], "comparison_operator": "is", "value": "x", "varType": "string"},
                ]},
            ]},
        }, llm(), end()],
        "edges": [
            {"source": "start", "target": "route"},
            {"source": "route", "source_handle": "yes", "target": "llm"},
            {"source": "llm", "target": "end"},
        ],
    }
    result = validate_plan(task(), plan)
    assert not result["valid"]
    assert any("false" in error for error in result["errors"])


def test_if_else_unknown_branch_handle_is_rejected() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "route", "type": "if-else", "config": {"cases": [
            {"case_id": "yes", "logical_operator": "and", "conditions": [
                {"variable_selector": ["start", "query"], "comparison_operator": "contains", "value": "x", "varType": "string"},
            ]},
        ]},
    })
    plan["edges"] = [
        {"source": "start", "target": "route"},
        {"source": "route", "source_handle": "maybe", "target": "llm"},
        {"source": "route", "source_handle": "false", "target": "llm"},
        {"source": "llm", "target": "end"},
    ]
    result = validate_plan(task(), plan)
    assert not result["valid"]
    assert any("不是已声明 case 或 false" in error for error in result["errors"])


def test_if_else_case_condition_must_reference_existing_upstream_variable() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "route", "type": "if-else", "config": {"cases": [
            {"case_id": "yes", "logical_operator": "and", "conditions": [
                {"variable_selector": ["start", "missing"], "comparison_operator": "contains", "value": "x", "varType": "string"},
            ]},
        ]},
    })
    plan["edges"] = [
        {"source": "start", "target": "route"},
        {"source": "route", "source_handle": "yes", "target": "llm"},
        {"source": "route", "source_handle": "false", "target": "llm"},
        {"source": "llm", "target": "end"},
    ]
    result = validate_plan(task(), plan)
    assert any("不存在变量：start.missing" in error for error in result["errors"])


def test_code_python_ast_is_checked_without_execution() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "code", "type": "code", "title": "格式化", "config": {
            "code_language": "python3",
            "code": "def main(query: str) -> dict:\n    return {'result': query}\n",
            "variables": [{"variable": "query", "value_selector": ["start", "query"]}],
            "outputs": {"result": {"type": "string", "children": None}},
        },
    })
    plan["nodes"][2]["config"]["user_prompt"] = "{{#code.result#}}"
    plan["edges"] = [{"source": "start", "target": "code"}, {"source": "code", "target": "llm"}, {"source": "llm", "target": "end"}]
    result = validate_plan(task(), plan)
    assert result["valid"], result["errors"]
    assert any("本机未执行代码" in warning for warning in result["warnings"])


def test_python_syntax_error_is_reported() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "code", "type": "code", "config": {
            "code_language": "python3", "code": "def main(:\n  pass",
            "variables": [], "outputs": {"result": {"type": "string", "children": None}},
        },
    })
    plan["edges"] = [{"source": "start", "target": "code"}, {"source": "code", "target": "llm"}, {"source": "llm", "target": "end"}]
    result = validate_plan(task(), plan)
    assert not result["valid"]
    assert any("Python 代码语法错误" in error for error in result["errors"])


def test_javascript_parser_checks_syntax_but_does_not_run_body() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "code", "type": "code", "config": {
            "code_language": "javascript", "code": "function main(input) { return { result: input }; }",
            "variables": [], "outputs": {"result": {"type": "string", "children": None}},
        },
    })
    plan["edges"] = [{"source": "start", "target": "code"}, {"source": "code", "target": "llm"}, {"source": "llm", "target": "end"}]
    assert validate_plan(task(), plan)["valid"]


def test_template_transform_has_output_and_upstream_input() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "template", "type": "template-transform", "config": {
            "template": "Hello {{ name }}", "variables": [
                {"variable": "name", "value_selector": ["start", "query"]},
            ],
        },
    })
    plan["nodes"][2]["config"]["user_prompt"] = "{{#template.output#}}"
    plan["edges"] = [{"source": "start", "target": "template"}, {"source": "template", "target": "llm"}, {"source": "llm", "target": "end"}]
    content, result = compile_workflow_plan(plan_task(plan))
    native = parse_yaml(content)["workflow"]["graph"]["nodes"]
    template = next(node for node in native if node["id"] == "template")
    assert result["valid"]
    assert template["data"]["template"] == "Hello {{ name }}"


def test_http_request_emits_native_no_auth_schema() -> None:
    plan = base_plan()
    plan["nodes"].insert(1, {
        "id": "http", "type": "http-request", "title": "查询", "config": {
            "method": "post", "url": "https://api.acme.test/v1/query", "headers": "Content-Type: application/json",
            "params": "", "body": {"type": "json", "data": [{"type":"text","key":"","value":'{"query":"{{#start.query#}}"}'}]},
            "timeout": {"connect": 10, "read": 30, "write": 30},
            "variables": [],
        },
    })
    plan["edges"] = [{"source": "start", "target": "http"}, {"source": "http", "target": "llm"}, {"source": "llm", "target": "end"}]
    content, validation = compile_workflow_plan(plan_task(plan))
    native = parse_yaml(content)["workflow"]["graph"]["nodes"]
    http = next(node for node in native if node["id"] == "http")["data"]
    assert validation["valid"]
    assert http["authorization"] == {"type": "no-auth", "config": None}
    assert http["method"] == "post"
    assert http['timeout'] == {'connect': 10, 'read': 30, 'write': 30}
    assert http['retry_config']['retry_enabled'] is False


def test_http_missing_or_placeholder_url_is_rejected() -> None:
    for url in (None, "https://example.com/api", "https://mock.invalid/query"):
        plan = base_plan()
        plan["nodes"].insert(1, {"id": "http", "type": "http-request", "config": {"url": url}})
        plan["edges"] = [{"source": "start", "target": "http"}, {"source": "http", "target": "llm"}, {"source": "llm", "target": "end"}]
        result = validate_plan(task(), plan)
        assert not result["valid"]
        assert any("url" in error for error in result["errors"])


def test_http_credentials_in_url_and_headers_are_rejected() -> None:
    for url, headers in (("https://user:pass@api.acme.test", ""), ("https://api.acme.test", "Authorization: Bearer secret"), ("https://api.acme.test?api_key=secret", "")):
        plan = base_plan()
        plan["nodes"].insert(1, {"id": "http", "type": "http-request", "config": {"url": url, "headers": headers}})
        plan["edges"] = [{"source": "start", "target": "http"}, {"source": "http", "target": "llm"}, {"source": "llm", "target": "end"}]
        result = validate_plan(task(), plan)
        assert not result["valid"]
        assert any("http-request.url" in error or "http-request.headers" in error for error in result["errors"])


def test_sibling_branch_variable_is_not_available_after_merge() -> None:
    plan = {
        "schema_version": 1,
        "nodes": [
            start(),
            {"id": "route", "type": "if-else", "config": {"cases": [
                {"case_id": "yes", "logical_operator": "and", "conditions": [
                    {"variable_selector": ["start", "query"], "comparison_operator": "contains", "value": "x", "varType": "string"},
                ]},
            ]}},
            llm("yes_node", "answer yes"), llm("no_node", "answer no"),
            llm("merge", "{{#yes_node.text#}}"), end(),
        ],
        "edges": [
            {"source": "start", "target": "route"},
            {"source": "route", "source_handle": "yes", "target": "yes_node"},
            {"source": "route", "source_handle": "false", "target": "no_node"},
            {"source": "yes_node", "target": "merge"}, {"source": "no_node", "target": "merge"},
            {"source": "merge", "target": "end"},
        ],
    }
    result = validate_plan(task(), plan)
    assert any("兄弟分支" in error for error in result["errors"])


def test_cycles_and_dead_paths_are_rejected() -> None:
    plan = base_plan()
    plan["edges"] = [
        {"source": "start", "target": "llm"},
        {"source": "llm", "target": "end"},
        {"source": "end", "target": "llm"},
    ]
    result = validate_plan(task(), plan)
    assert not result["valid"]
    assert any("有向环" in error for error in result["errors"])
    assert any("终点" in error for error in result["errors"])


def test_invalid_variable_and_non_upstream_reference_are_rejected() -> None:
    plan = base_plan()
    plan["nodes"][1]["config"]["user_prompt"] = "{{#start.missing#}}"
    result = validate_plan(task(), plan)
    assert any("不存在变量：start.missing" in error for error in result["errors"])

    plan = base_plan()
    plan["nodes"].insert(1, llm("detached", "unused"))
    plan["nodes"][2]["config"]["user_prompt"] = "{{#detached.text#}}"
    result = validate_plan(task(), plan)
    assert any("不可从 start 到达" in error or "所有路径上游" in error for error in result["errors"])


def test_plan_rejects_unsupported_type_and_wrong_terminal_for_mode() -> None:
    plan = base_plan()
    plan["nodes"][1]["type"] = "agent"
    assert any("不在支持范围" in error for error in validate_plan(task(), plan)["errors"])

    chatflow_plan = base_plan("advanced-chat")
    chatflow_plan["nodes"][-1] = end()
    chatflow_plan["edges"][-1]["target"] = "end"
    assert any("终点只能使用 answer" in error for error in validate_plan(task("advanced-chat"), chatflow_plan)["errors"])


def test_model_is_required_only_when_plan_contains_llm() -> None:
    no_llm = {
        "schema_version": 1,
        "nodes": [start(), end(selector=["start", "query"])],
        "edges": [{"source": "start", "target": "end"}],
    }
    no_model_task = plan_task(no_llm)
    no_model_task["configuration"] = {}
    assert validate_plan(no_model_task, no_llm)["valid"]

    missing_model = plan_task(base_plan())
    missing_model["configuration"] = {}
    plan_validation = validate_plan(missing_model, missing_model["workflow_plan"])
    assert plan_validation["valid"]
    assert any("构建 DSL 前" in warning for warning in plan_validation["warnings"])
    content, compile_validation = compile_workflow_plan(missing_model)
    assert content == ""
    assert not compile_validation["valid"]
    assert any("明确提供" in error for error in compile_validation["errors"])


def test_http_schema_rejects_unknown_method_and_malformed_native_body() -> None:
    for method, body in (("options", {"type": "none", "data": []}), ("post", {"type": [], "data": []}),
                         ("post", {"type": "json"})):
        plan = base_plan()
        plan["nodes"].insert(1, {
            "id": "http", "type": "http-request", "config": {
                "method": method, "url": "https://api.acme.test/v1", "body": body,
            },
        })
        plan["edges"] = [
            {"source": "start", "target": "http"},
            {"source": "http", "target": "llm"},
            {"source": "llm", "target": "end"},
        ]
        result = validate_plan(task(), plan)
        assert not result["valid"]


def test_plan_and_structure_errors_return_validation_not_exceptions() -> None:
    for malformed in (None, [], {"schema_version": 1, "nodes": [None], "edges": [None]},
                      {"schema_version": 1, "nodes": [{"id": "x", "type": [], "config": []}], "edges": [{"source": [], "target": {}}]}):
        result = validate_plan(task(), malformed)
        assert not result["valid"]
        assert result["errors"]
    result = validate_plan({"app_type": []}, base_plan())
    assert not result["valid"]


def test_compile_invalid_plan_does_not_emit_yaml() -> None:
    plan = base_plan()
    plan["nodes"][1]["config"]["system_prompt"] = ""
    plan["nodes"][1]["config"]["user_prompt"] = ""
    content, validation = compile_workflow_plan(plan_task(plan))
    assert content == ""
    assert not validation["valid"]
