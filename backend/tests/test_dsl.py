from __future__ import annotations

import sys
from pathlib import Path

import yaml
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dsl import DSL_VERSION, TARGET_DIFY_VERSION, compile_dsl, validate_dsl


def task(app_type: str = "workflow") -> dict:
    return {
        "name": "售后问答",
        "app_type": app_type,
        "requirements": {
            "goal": "回答售后问题",
            "audience": "客户",
            "input": "用户问题",
            "output": "准确答复",
            "rules": "不知道时说明不确定",
            "knowledge": "产品与售后政策",
            "exceptions": "无匹配内容时转人工",
            "tests": "已知问题应答",
        },
        "configuration": {
            "dify_model_provider": "langgenius/deepseek/deepseek",
            "dify_model": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 2048,
            "dataset_ids": [],
            "retrieval_top_k": 3,
            "mock_dependencies": [],
            "resource_plan": "只创建新应用",
        },
    }


def parse(content: str) -> dict:
    return yaml.safe_load(content)


def test_compile_workflow_has_required_query_and_linear_llm_end() -> None:
    content, validation = compile_dsl(task("workflow"))
    dsl = parse(content)
    graph = dsl["workflow"]["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert TARGET_DIFY_VERSION == "1.17.1"
    assert dsl["version"] == DSL_VERSION == "0.7.0"
    assert dsl["app"]["mode"] == "workflow"
    assert nodes["start"]["data"]["variables"] == [{
        "label": "query", "max_length": 50000, "options": [], "required": True,
        "type": "text-input", "variable": "query",
    }]
    assert nodes["llm"]["data"]["prompt_template"][1]["text"] == "用户问题：{{#start.query#}}"
    assert nodes["end"]["data"]["outputs"][0]["value_selector"] == ["llm", "text"]
    assert [(edge["source"], edge["target"]) for edge in graph["edges"]] == [("start", "llm"), ("llm", "end")]
    assert validation["valid"]


def test_compile_chatflow_keeps_selected_type_and_references_sys_query() -> None:
    content, validation = compile_dsl(task("advanced-chat"))
    dsl = parse(content)
    graph = dsl["workflow"]["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert dsl["app"]["mode"] == "advanced-chat"
    assert nodes["start"]["data"]["variables"] == []
    assert nodes["llm"]["data"]["prompt_template"][1]["text"] == "用户问题：{{#sys.query#}}"
    assert nodes["answer"]["data"]["answer"] == "{{#llm.text#}}"
    assert validation["valid"]


def test_knowledge_retrieval_uses_1171_schema_and_real_dataset_ids() -> None:
    value = task("advanced-chat")
    value["configuration"]["dataset_ids"] = ["existing-dataset-1"]
    value["configuration"]["retrieval_top_k"] = 5
    content, validation = compile_dsl(value)
    dsl = parse(content)
    graph = dsl["workflow"]["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    retrieval = nodes["knowledge_retrieval"]["data"]
    assert retrieval["type"] == "knowledge-retrieval"
    assert retrieval["dataset_ids"] == ["existing-dataset-1"]
    assert retrieval["query_variable_selector"] == ["sys", "query"]
    assert retrieval["retrieval_mode"] == "multiple"
    assert retrieval["multiple_retrieval_config"] == {
        "top_k": 5, "score_threshold": None, "reranking_enable": False,
    }
    assert nodes["llm"]["data"]["context"] == {
        "enabled": True, "variable_selector": ["knowledge_retrieval", "result"],
    }
    assert [(edge["source"], edge["target"]) for edge in graph["edges"]] == [
        ("start", "knowledge_retrieval"), ("knowledge_retrieval", "llm"), ("llm", "answer"),
    ]
    assert validation["valid"]


@pytest.mark.parametrize("app_type", ["agent", "chat", "completion", "other"])
def test_unsupported_types_are_not_silently_substituted(app_type: str) -> None:
    with pytest.raises(ValueError, match="Agent DSL|不支持的 Dify 应用类型"):
        compile_dsl(task(app_type))


@pytest.mark.parametrize("field", ["dify_model_provider", "dify_model"])
def test_missing_model_is_rejected_without_guessing(field: str) -> None:
    value = task()
    value["configuration"][field] = ""
    with pytest.raises(ValueError, match="必须提供真实的"):
        compile_dsl(value)


def test_requirements_are_strings_and_values_reach_prompt() -> None:
    value = task()
    value["requirements"]["rules"] = 123
    with pytest.raises(ValueError, match="requirements.rules 必须是字符串"):
        compile_dsl(value)
    value["requirements"]["rules"] = "订单号缺失时先追问"
    content, _ = compile_dsl(value)
    prompt = parse(content)["workflow"]["graph"]["nodes"][1]["data"]["prompt_template"][0]["text"]
    assert "订单号缺失时先追问" in prompt


def test_mock_dependency_is_marked_in_yaml_and_validation() -> None:
    value = task()
    value["configuration"]["mock_dependencies"] = ["订单查询接口"]
    content, validation = compile_dsl(value)
    assert "模拟依赖" in parse(content)["app"]["description"]
    assert any("模拟依赖" in warning for warning in validation["warnings"])


def test_compiler_never_exports_secret_configuration_fields() -> None:
    value = task()
    value["configuration"]["api_key"] = "do-not-export-this"
    value["configuration"]["provider_credentials"] = {"secret": "also-do-not-export"}
    content, validation = compile_dsl(value)
    assert "do-not-export-this" not in content
    assert "also-do-not-export" not in content
    assert validation["valid"]
    assert "api_key" not in content
    assert "provider_credentials" not in content


def test_validate_rejects_missing_node_reference_duplicate_ids_and_disconnected_nodes() -> None:
    value = task()
    content, _ = compile_dsl(value)
    dsl = parse(content)
    llm = next(node for node in dsl["workflow"]["graph"]["nodes"] if node["id"] == "llm")
    llm["data"]["prompt_template"][1]["text"] = "{{#missing.text#}}"
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert not validation["valid"]
    assert any("不存在的节点：missing" in error for error in validation["errors"])

    dsl = parse(content)
    dsl["workflow"]["graph"]["nodes"][1]["id"] = "start"
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("节点 id 重复" in error for error in validation["errors"])

    dsl = parse(content)
    dsl["workflow"]["graph"]["edges"] = []
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("不可从 start 到达" in error for error in validation["errors"])


def test_validate_rejects_empty_graph_and_chatflow_without_start() -> None:
    content, _ = compile_dsl(task())
    dsl = parse(content)
    dsl["workflow"]["graph"]["nodes"] = []
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert not validation["valid"]
    assert any("nodes 不能为空" in error for error in validation["errors"])
    assert any("仅包含一个 start" in error for error in validation["errors"])

    content, _ = compile_dsl(task("advanced-chat"))
    dsl = parse(content)
    dsl["workflow"]["graph"]["nodes"] = [
        node for node in dsl["workflow"]["graph"]["nodes"] if node["data"]["type"] != "start"
    ]
    dsl["workflow"]["graph"]["edges"] = [
        edge for edge in dsl["workflow"]["graph"]["edges"] if edge["source"] != "start"
    ]
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert not validation["valid"]
    assert any("仅包含一个 start" in error for error in validation["errors"])


def test_validate_checks_variable_names_and_terminal_selectors() -> None:
    content, _ = compile_dsl(task())
    dsl = parse(content)
    llm = next(node for node in dsl["workflow"]["graph"]["nodes"] if node["id"] == "llm")
    llm["data"]["prompt_template"][1]["text"] = "{{#start.unknown#}}"
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("不存在的变量：start.unknown" in error for error in validation["errors"])

    dsl = parse(content)
    end = next(node for node in dsl["workflow"]["graph"]["nodes"] if node["id"] == "end")
    end["data"]["outputs"][0]["value_selector"] = ["llm", "unknown"]
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("不存在的变量：llm.unknown" in error for error in validation["errors"])


def test_validate_checks_answer_context_and_retrieval_selectors() -> None:
    value = task("advanced-chat")
    value["configuration"]["dataset_ids"] = ["dataset-1"]
    content, _ = compile_dsl(value)
    dsl = parse(content)
    graph = dsl["workflow"]["graph"]
    llm = next(node for node in graph["nodes"] if node["id"] == "llm")
    llm["data"]["context"]["variable_selector"] = ["knowledge_retrieval", "missing"]
    answer = next(node for node in graph["nodes"] if node["id"] == "answer")
    answer["data"]["answer"] = "{{#llm.missing#}}"
    retrieval = next(node for node in graph["nodes"] if node["id"] == "knowledge_retrieval")
    retrieval["data"]["query_variable_selector"] = ["sys", "not_query"]
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("不存在的变量：knowledge_retrieval.missing" in error for error in validation["errors"])
    assert any("不存在的变量：llm.missing" in error for error in validation["errors"])
    assert any("无效系统变量 sys.not_query" in error for error in validation["errors"])


def test_validate_rejects_non_upstream_references_and_cycles() -> None:
    content, _ = compile_dsl(task())
    dsl = parse(content)
    graph = dsl["workflow"]["graph"]
    graph["edges"] = [
        {"source": "start", "target": "end"},
        {"source": "end", "target": "llm"},
    ]
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("不在当前节点上游" in error for error in validation["errors"])
    assert any("死路径" in error for error in validation["errors"])

    dsl = parse(content)
    dsl["workflow"]["graph"]["edges"] = [
        {"source": "start", "target": "llm"},
        {"source": "llm", "target": "end"},
        {"source": "end", "target": "llm"},
    ]
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("有向环或 loop" in error for error in validation["errors"])


def test_validate_rejects_unsupported_nodes_and_malformed_shapes_without_typeerror() -> None:
    content, _ = compile_dsl(task())
    dsl = parse(content)
    llm = next(node for node in dsl["workflow"]["graph"]["nodes"] if node["id"] == "llm")
    llm["data"]["type"] = "code"
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert any("不在当前适配器支持范围内" in error for error in validation["errors"])

    for malformed in (
        {"nodes": [None], "edges": [None]},
        {"nodes": [{"id": [], "data": []}], "edges": [{"source": [], "target": {}}]},
        {"nodes": [{"id": "start", "data": {"type": "start", "variables": {}}}], "edges": []},
    ):
        dsl = parse(content)
        dsl["workflow"]["graph"] = malformed
        validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
        assert not validation["valid"]
        assert validation["errors"]

    dsl = parse(content)
    dsl["app"]["mode"] = []
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert not validation["valid"]
    assert validation["errors"]

    value = task("advanced-chat")
    value["configuration"]["dataset_ids"] = ["dataset-1"]
    content, _ = compile_dsl(value)
    dsl = parse(content)
    retrieval = next(node for node in dsl["workflow"]["graph"]["nodes"] if node["id"] == "knowledge_retrieval")
    retrieval["data"]["retrieval_mode"] = []
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert not validation["valid"]
    assert validation["errors"]


def test_validate_rejects_secret_fields_in_existing_dsl() -> None:
    value = task()
    content, _ = compile_dsl(value)
    dsl = parse(content)
    llm = next(node for node in dsl["workflow"]["graph"]["nodes"] if node["id"] == "llm")
    llm["data"]["model"]["api_key"] = "abc"
    validation = validate_dsl(yaml.safe_dump(dsl, allow_unicode=True))
    assert not validation["valid"]
    assert any("疑似凭据字段" in error for error in validation["errors"])
