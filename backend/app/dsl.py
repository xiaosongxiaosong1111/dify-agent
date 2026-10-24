"""Small, explicit Dify 1.17.1 workflow/chatflow DSL compiler.

This module intentionally emits only a linear start -> optional retrieval ->
LLM -> end/answer graph. It does not claim to compile arbitrary business logic.
"""

from __future__ import annotations
from .model_parameters import completion_parameters
from .conversation import memory_configuration

import re
from typing import Any

import yaml

TARGET_DIFY_VERSION = "1.17.1"
DSL_VERSION = "0.7.0"
MOCK_DEPENDENCY_WARNING = "包含模拟依赖，结果属于模拟配置，不能视为已连接或已验证。"

REQUIREMENT_KEYS = (
    "goal",
    "audience",
    "input",
    "output",
    "rules",
    "knowledge",
    "exceptions",
    "tests",
)
_SECRET_KEYS = {"api_key", "apikey", "access_token", "refresh_token", "token", "secret", "password", "credential", "credentials"}
_REF_PATTERN = re.compile(r"\{\{#([\w-]+)\.([\w-]+)#\}\}")


def _node(node_id: str, title: str, data: dict[str, Any], x: int, *, height: int = 88) -> dict[str, Any]:
    position = {"x": x, "y": 282}
    return {
        "data": {"desc": "", "selected": False, "title": title, **data},
        "height": height,
        "id": node_id,
        "position": position.copy(),
        "positionAbsolute": position.copy(),
        "selected": False,
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 244,
    }


def _edge(source: str, target: str, source_type: str, target_type: str) -> dict[str, Any]:
    return {
        "data": {"sourceType": source_type, "targetType": target_type},
        "id": f"{source}-{target}",
        "source": source,
        "sourceHandle": "source",
        "target": target,
        "targetHandle": "target",
        "type": "custom",
        "zIndex": 0,
    }


def _contains_secret_key(value: Any) -> bool:
    from .http_auth_reference import allowed_api_key_objects
    allowed = allowed_api_key_objects(value)
    pending = [value];seen = set();count = 0
    names = {re.sub(r'[^a-z]', '', item) for item in _SECRET_KEYS}
    while pending:
        item = pending.pop();count += 1
        if count > 40000:return True
        if isinstance(item, (dict, list)):
            if id(item) in seen:return True
            seen.add(id(item))
        if isinstance(item, dict):
            for key, child in item.items():
                if key == 'api_key' and id(item) in allowed:continue
                if re.sub(r'[^a-z]', '', str(key).lower()) in names:return True
                pending.append(child)
        elif isinstance(item, list):pending.extend(item)
    return False


def _task_parts(task: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(task, dict):
        raise ValueError("task 必须是对象")
    app_type = task.get("app_type")
    if app_type == "agent":
        raise ValueError("Dify Agent DSL 当前不受支持；请保留用户选择的 Agent 类型，不能自动改为 Workflow 或 Chatflow。")
    if app_type not in {"workflow", "advanced-chat"}:
        raise ValueError(f"不支持的 Dify 应用类型：{app_type!r}；当前仅支持 workflow 和 advanced-chat。")
    requirements = task.get("requirements", {})
    configuration = task.get("configuration", {})
    if not isinstance(requirements, dict) or not isinstance(configuration, dict):
        raise ValueError("requirements 和 configuration 必须是对象")
    for key in REQUIREMENT_KEYS:
        value = requirements.get(key, "")
        if not isinstance(value, str):
            raise ValueError(f"requirements.{key} 必须是字符串")
    provider = configuration.get("dify_model_provider")
    model = configuration.get("dify_model")
    if not isinstance(provider, str) or not provider.strip() or not isinstance(model, str) or not model.strip():
        raise ValueError("必须提供真实的 dify_model_provider 和 dify_model；编译器不会猜测或编造模型信息。")
    return app_type, requirements, configuration


def mock_dependency_notice(configuration: dict) -> str:
    dependencies = configuration.get("mock_dependencies", [])
    if not isinstance(dependencies, list):
        dependencies = [str(dependencies)]
    dependencies = [str(item) for item in dependencies if str(item).strip()]
    return f"模拟依赖（未接入真实服务）：{', '.join(dependencies)}。" if dependencies else ""


def compile_dsl(task: dict) -> tuple[str, dict]:
    """Compile a simple linear graph and return its YAML plus static validation."""
    app_type, requirements, configuration = _task_parts(task)
    memory_configuration(app_type,configuration)
    dataset_ids = configuration.get("dataset_ids", [])
    if not isinstance(dataset_ids, list) or any(not isinstance(item, str) or not item.strip() for item in dataset_ids):
        raise ValueError("configuration.dataset_ids 必须是非空字符串组成的数组")
    dataset_ids = list(dict.fromkeys(item.strip() for item in dataset_ids))
    top_k = configuration.get("retrieval_top_k", 3)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("configuration.retrieval_top_k 必须是正整数")
    temperature = configuration.get("temperature", 0.2)
    max_tokens = configuration.get("max_tokens", 2048)
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not 0 <= temperature <= 2:
        raise ValueError("configuration.temperature 必须在 0 到 2 之间")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
        raise ValueError("configuration.max_tokens 必须是正整数")

    chatflow = app_type == "advanced-chat"
    input_ref = "sys.query" if chatflow else "start.query"
    query_selector = ["sys", "query"] if chatflow else ["start", "query"]
    terminal_id, terminal_type = ("answer", "answer") if chatflow else ("end", "end")
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    start_variables = [] if chatflow else [{
            "label": "query", "max_length": 50000, "options": [], "required": True,
            "type": "text-input", "variable": "query",
        }]
    nodes.append(_node("start", "开始", {"type": "start", "variables": start_variables}, 80, height=89))

    retrieval_id = "knowledge_retrieval"
    if dataset_ids:
        retrieval = _node(retrieval_id, "知识检索", {
            "type": "knowledge-retrieval",
            "query_variable_selector": query_selector,
            "query_attachment_selector": [],
            "dataset_ids": dataset_ids,
            "retrieval_mode": "multiple",
            "multiple_retrieval_config": {
                "top_k": top_k,
                "score_threshold": None,
                "reranking_enable": False,
            },
            "metadata_filtering_mode": "disabled",
            "vision": {"enabled": False},
        }, 380, height=92)
        nodes.append(retrieval)

    system_parts = ["你是一个严谨的业务助手。只依据已提供的信息回答；无法确认时明确说明不确定。"]
    labels = {
        "goal": "目标", "audience": "服务对象", "input": "输入", "output": "输出",
        "rules": "规则", "knowledge": "知识范围", "exceptions": "异常处理", "tests": "验收样例",
    }
    for key in REQUIREMENT_KEYS:
        value = requirements.get(key, "").strip()
        if value:
            system_parts.append(f"{labels[key]}：{value}")
    if dataset_ids:
        system_parts.append("知识库检索内容：{{#context#}}\n请优先依据检索内容回答；没有依据时说明未在知识库中找到。")
    system_prompt = "\n\n".join(system_parts)
    model_config: dict[str, Any] = {
        "provider": configuration["dify_model_provider"].strip(),
        "name": configuration["dify_model"].strip(),
        "mode": "chat",
        "completion_params": completion_parameters({**configuration, "temperature": float(temperature), "max_tokens": max_tokens}),
    }
    context_selector = [retrieval_id, "result"] if dataset_ids else []
    llm_node = _node("llm", "LLM", {
        "type": "llm",
        "model": model_config,
        "prompt_template": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": f"用户问题：{{{{#{input_ref}#}}}}"},
        ],
        "context": {"enabled": bool(dataset_ids), "variable_selector": context_selector},
        **({"memory": memory_configuration(app_type,configuration)} if configuration.get("conversation_memory") else {}),
        "vision": {"enabled": False},
        "variables": [],
    }, 680 if dataset_ids else 380, height=103)
    nodes.append(llm_node)
    if chatflow:
        nodes.append(_node(terminal_id, "直接回复", {
            "type": terminal_type, "answer": "{{#llm.text#}}", "variables": [],
        }, 980 if dataset_ids else 680, height=103))
    else:
        nodes.append(_node(terminal_id, "结束", {
            "type": terminal_type, "outputs": [{"variable": "result", "value_selector": ["llm", "text"]}],
        }, 980 if dataset_ids else 680, height=53))

    if chatflow:
        if dataset_ids:
            edges.extend([
                _edge("start", retrieval_id, "start", "knowledge-retrieval"),
                _edge(retrieval_id, "llm", "knowledge-retrieval", "llm"),
                _edge("llm", terminal_id, "llm", terminal_type),
            ])
        else:
            edges.extend([_edge("start", "llm", "start", "llm"), _edge("llm", terminal_id, "llm", terminal_type)])
    elif dataset_ids:
        edges.extend([
            _edge("start", retrieval_id, "start", "knowledge-retrieval"),
            _edge(retrieval_id, "llm", "knowledge-retrieval", "llm"),
            _edge("llm", terminal_id, "llm", terminal_type),
        ])
    else:
        edges.extend([_edge("start", "llm", "start", "llm"), _edge("llm", terminal_id, "llm", terminal_type)])

    mock_note = mock_dependency_notice(configuration)
    app_name = str(task.get("name") or "未命名应用").strip()
    resource_plan = configuration.get("resource_plan")
    description_parts = [f"由 Sierra 生成，目标 Dify {TARGET_DIFY_VERSION}。"]
    if isinstance(resource_plan, str) and resource_plan.strip():
        description_parts.append(f"资源计划：{resource_plan.strip()}")
    if mock_note:
        description_parts.append(mock_note)
    dsl = {
        "app": {
            "description": "\n".join(description_parts),
            "icon": "🤖",
            "icon_background": "#FFEAD5",
            "mode": app_type,
            "name": app_name,
            "use_icon_as_answer_icon": False,
        },
        # Dependency pins require the actual installed plugin version/hash; this
        # offline compiler must not invent them. Dify accepts the empty list.
        "dependencies": [],
        "kind": "app",
        "version": DSL_VERSION,
        "workflow": {
            "conversation_variables": [],
            "environment_variables": [],
            "features": {
                "file_upload": {"enabled": False, "number_limits": 3},
                "opening_statement": configuration.get("opening_statement", ""),
                "retriever_resource": {"enabled": bool(dataset_ids)},
                "sensitive_word_avoidance": {"enabled": False},
                "suggested_questions": configuration.get("suggested_questions", []),
                "suggested_questions_after_answer": {"enabled": False},
                "speech_to_text": {"enabled": False},
                "text_to_speech": {"enabled": False, "language": "", "voice": ""},
            },
            "graph": {"edges": edges, "nodes": nodes, "viewport": {"x": 0, "y": 0, "zoom": 1}},
            "rag_pipeline_variables": [],
        },
    }
    content = yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False)
    validation = validate_dsl(content)
    if mock_note:
        validation["warnings"].append(MOCK_DEPENDENCY_WARNING)
    validation["warnings"].append("此结果仅将已收集需求写入线性提示词模板；分支、循环、审批、批量策略和外部接口等复杂业务语义未展开，仍需人工设计与 Dify 实测。")
    validation["warnings"].append("DSL 静态检查不等于目标 Dify 导入或运行验证。")
    return content, validation


def validate_dsl(content: str) -> dict:
    """Validate only the supported linear node subset, with safe shape checks."""
    errors: list[str] = []
    warnings: list[str] = []

    def fail(message: str) -> None:
        if message not in errors:
            errors.append(message)

    try:
        root = yaml.safe_load(content)
    except (yaml.YAMLError, TypeError) as exc:
        return {"valid": False, "errors": [f"YAML 解析失败：{exc}"], "warnings": [], "nodes": 0}
    if not isinstance(root, dict):
        return {"valid": False, "errors": ["DSL 顶层必须是映射对象"], "warnings": [], "nodes": 0}
    if root.get("kind") != "app":
        fail("kind 必须为 app")
    if root.get("version") != DSL_VERSION:
        fail(f"version 必须为 {DSL_VERSION}")
    app = root.get("app")
    if not isinstance(app, dict):
        fail("缺少 app 对象")
        app = {}
    mode = app.get("mode")
    if mode == "agent":
        fail("Agent DSL 不受支持，不能将其当作 Workflow 或 Chatflow 校验")
    elif not isinstance(mode, str) or mode not in {"workflow", "advanced-chat"}:
        fail("app.mode 必须为 workflow 或 advanced-chat")

    workflow = root.get("workflow")
    graph = workflow.get("graph") if isinstance(workflow, dict) else None
    if not isinstance(graph, dict):
        fail("缺少 workflow.graph 对象")
        graph = {}
    raw_nodes, raw_edges = graph.get("nodes", []), graph.get("edges", [])
    if not isinstance(raw_nodes, list):
        fail("workflow.graph.nodes 必须是数组")
        raw_nodes = []
    if not raw_nodes:
        fail("workflow.graph.nodes 不能为空")
    if not isinstance(raw_edges, list):
        fail("workflow.graph.edges 必须是数组")
        raw_edges = []

    by_id: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not isinstance(node.get("data"), dict):
            fail(f"nodes[{index}] 必须包含字符串 id 和 data 对象")
            continue
        node_id = node["id"]
        if node_id in by_id:
            fail(f"节点 id 重复：{node_id}")
        else:
            by_id[node_id] = node

    terminal_type = "answer" if mode == "advanced-chat" else "end"
    allowed_types = {"start", "knowledge-retrieval", "llm", terminal_type}
    node_types: dict[str, str] = {}
    for node_id, node in by_id.items():
        node_type = node["data"].get("type")
        if not isinstance(node_type, str):
            fail(f"节点 {node_id} 缺少字符串 type")
            continue
        node_types[node_id] = node_type
        if node_type not in allowed_types:
            fail(f"节点类型 {node_type!r} 不在当前适配器支持范围内")
        if mode == "workflow" and node_type == "answer":
            fail("Workflow 模式不支持 answer 节点，应使用 end")
        if mode == "advanced-chat" and node_type == "end":
            fail("Chatflow 模式不支持 end 节点，应使用 answer")

    starts = [node_id for node_id, kind in node_types.items() if kind == "start"]
    terminals = [node_id for node_id, kind in node_types.items() if kind == terminal_type]
    if len(starts) != 1:
        fail("workflow graph 必须包含且仅包含一个 start 节点")
    if len(terminals) != 1:
        fail(f"{mode} graph 必须包含且仅包含一个 {terminal_type} 终点节点")
    start_id = starts[0] if len(starts) == 1 else None
    terminal_id = terminals[0] if len(terminals) == 1 else None

    outputs: dict[str, set[str]] = {}
    for node_id, node in by_id.items():
        data, kind = node["data"], node_types.get(node_id)
        if kind == "start":
            variables = data.get("variables", [])
            if not isinstance(variables, list):
                fail(f"start 节点 {node_id} 的 variables 必须是数组")
                variables = []
            names: set[str] = set()
            for index, variable in enumerate(variables):
                if not isinstance(variable, dict) or not isinstance(variable.get("variable"), str) or not variable["variable"]:
                    fail(f"start 节点 {node_id} 的 variables[{index}] 缺少 variable 名称")
                    continue
                if variable["variable"] in names:
                    fail(f"start 节点 {node_id} 的变量重复：{variable['variable']}")
                names.add(variable["variable"])
            outputs[node_id] = names
            if mode == "workflow" and not any(
                isinstance(v, dict) and v.get("variable") == "query" and v.get("required") is True and v.get("type") == "text-input"
                for v in variables
            ):
                fail("workflow start 必须声明必填的 query 字符串输入")
            if mode == "advanced-chat":
                from .start_inputs import validate_variable
                if names & {'query', 'conversation_id'}:
                    fail("Chatflow 的 query／conversation_id 为试跑传输保留名，不能作为自定义开始变量")
                for variable in variables:
                    if isinstance(variable, dict):
                        for message in validate_variable(variable): fail('Chatflow 开始变量：' + message)
        elif kind == "llm":
            from .structured_output import validate as validate_structured, output_type as structured_type
            for message in validate_structured(data): fail(f'LLM 节点 {node_id}：{message}')
            model = data.get("model")
            if not isinstance(model, dict) or not all(isinstance(model.get(k), str) and model[k].strip() for k in ("provider", "name")):
                fail(f"LLM 节点 {node_id} 必须包含模型 provider 和 name")
            prompts = data.get("prompt_template")
            if not isinstance(prompts, list) or not prompts:
                fail(f"LLM 节点 {node_id} 的 prompt_template 必须是非空数组")
            elif any(not isinstance(p, dict) or not isinstance(p.get("text"), str) for p in prompts):
                fail(f"LLM 节点 {node_id} 的 prompt_template 项必须包含 text 字符串")
            # These are the documented outputs used by this compiler and the
            # common LLM result metadata exposed by Dify's workflow LLM node.
            outputs[node_id] = {"text", "usage", "finish_reason", "files"}
            if structured_type(data): outputs[node_id].add('structured_output')
        elif kind == "knowledge-retrieval":
            outputs[node_id] = {"result"}
            dataset_ids = data.get("dataset_ids")
            if not isinstance(dataset_ids, list) or not dataset_ids or any(not isinstance(item, str) or not item.strip() for item in dataset_ids):
                fail(f"知识检索节点 {node_id} 必须包含非空 dataset_ids")
            query_selector = data.get("query_variable_selector")
            if query_selector is None or query_selector == []:
                fail(f"知识检索节点 {node_id} 必须声明 query_variable_selector")
            retrieval_mode = data.get("retrieval_mode")
            if not isinstance(retrieval_mode, str) or retrieval_mode not in {"single", "multiple"}:
                fail(f"知识检索节点 {node_id} 的 retrieval_mode 必须为 single 或 multiple")
            if retrieval_mode == "multiple":
                multiple_config = data.get("multiple_retrieval_config")
                if not isinstance(multiple_config, dict):
                    fail(f"知识检索节点 {node_id} 必须包含 multiple_retrieval_config")
                elif not isinstance(multiple_config.get("top_k"), int) or isinstance(multiple_config.get("top_k"), bool) or multiple_config["top_k"] < 1:
                    fail(f"知识检索节点 {node_id} 的 top_k 必须是正整数")
            if retrieval_mode == "single" and not isinstance(data.get("single_retrieval_config"), dict):
                fail(f"知识检索节点 {node_id} 必须包含 single_retrieval_config")
        else:
            outputs[node_id] = set()

    if _contains_secret_key(root):
        fail("DSL 包含疑似凭据字段；导出物不得包含密钥、令牌或密码")

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    reverse: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    for index, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            fail(f"edges[{index}] 必须是对象")
            continue
        source, target = edge.get("source"), edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            fail(f"edges[{index}] 的 source 和 target 必须是字符串")
            continue
        if source not in by_id or target not in by_id:
            fail(f"边引用不存在的节点：{source!r} -> {target!r}")
            continue
        adjacency[source].add(target)
        reverse[target].add(source)

    def ancestors(node_id: str) -> set[str]:
        found: set[str] = set()
        pending = list(reverse.get(node_id, set()))
        while pending:
            current = pending.pop()
            if current not in found:
                found.add(current)
                pending.extend(reverse.get(current, set()))
        return found

    state: dict[str, int] = {}
    def visit(node_id: str) -> None:
        state[node_id] = 1
        for neighbor in adjacency.get(node_id, set()):
            if state.get(neighbor) == 1:
                fail("当前适配器不支持有向环或 loop")
            elif state.get(neighbor, 0) == 0:
                visit(neighbor)
        state[node_id] = 2
    for node_id in by_id:
        if state.get(node_id, 0) == 0:
            visit(node_id)

    reachable: set[str] = set()
    if start_id is not None:
        reachable.add(start_id)
        pending = [start_id]
        while pending:
            current = pending.pop()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    pending.append(neighbor)
        for node_id in by_id:
            if node_id not in reachable:
                fail(f"节点不可从 start 到达：{node_id}")

    if terminal_id is not None:
        can_reach_terminal = {terminal_id}
        pending = [terminal_id]
        while pending:
            current = pending.pop()
            for predecessor in reverse.get(current, set()):
                if predecessor not in can_reach_terminal:
                    can_reach_terminal.add(predecessor)
                    pending.append(predecessor)
        for node_id in by_id:
            if node_id not in can_reach_terminal:
                fail(f"节点存在无法到达终点的死路径：{node_id}")

    def check_selector(node_id: str, selector: Any, field: str) -> None:
        if selector is None or selector == []:
            return
        if not isinstance(selector, list) or len(selector) != 2 or not all(isinstance(part, str) for part in selector):
            fail(f"节点 {node_id} 的 {field} 必须为空或 [节点ID, 变量名]")
            return
        source, variable = selector
        if source == "sys":
            if mode != "advanced-chat" or variable != "query":
                fail(f"节点 {node_id} 的 {field} 引用了无效系统变量 sys.{variable}")
            elif start_id is None or node_id == start_id or start_id not in ancestors(node_id):
                fail(f"节点 {node_id} 的系统变量 sys.{variable} 不在 start 上游")
            return
        if source not in by_id:
            fail(f"节点 {node_id} 的 {field} 引用了不存在的节点：{source}")
        elif source == node_id or source not in ancestors(node_id):
            fail(f"节点 {node_id} 的 {field} 引用源 {source} 不在当前节点上游")
        elif variable not in outputs.get(source, set()):
            fail(f"节点 {node_id} 的 {field} 引用了不存在的变量：{source}.{variable}")

    selector_keys = {"value_selector", "variable_selector", "query_variable_selector", "query_attachment_selector"}
    for node_id, node in by_id.items():
        data, kind = node["data"], node_types.get(node_id)
        if kind == "answer":
            answer = data.get("answer")
            if not isinstance(answer, str):
                fail(f"answer 节点 {node_id} 必须包含 answer 字符串")
            else:
                for source, variable in _REF_PATTERN.findall(answer):
                    check_selector(node_id, [source, variable], "answer")
        if kind == "end":
            end_outputs = data.get("outputs", [])
            if not isinstance(end_outputs, list):
                fail(f"end 节点 {node_id} 的 outputs 必须是数组")
                end_outputs = []
            if not end_outputs:
                fail(f"end 节点 {node_id} 必须包含至少一个输出")
            for index, item in enumerate(end_outputs):
                if not isinstance(item, dict):
                    fail(f"end 节点 {node_id} 的 outputs[{index}] 必须是对象")
                else:
                    check_selector(node_id, item.get("value_selector"), "outputs.value_selector")
        if kind == "llm":
            context = data.get("context", {})
            if not isinstance(context, dict):
                fail(f"LLM 节点 {node_id} 的 context 必须是对象")
            elif context.get("enabled"):
                if context.get("variable_selector") in (None, []):
                    fail(f"启用 context 的 LLM 节点 {node_id} 必须配置 variable_selector")
                check_selector(node_id, context.get("variable_selector"), "context.variable_selector")
        prompts = data.get("prompt_template", [])
        if isinstance(prompts, list):
            for prompt in prompts:
                if isinstance(prompt, dict) and isinstance(prompt.get("text"), str):
                    for source, variable in _REF_PATTERN.findall(prompt["text"]):
                        check_selector(node_id, [source, variable], "prompt_template")
        def inspect_selectors(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in selector_keys:
                        check_selector(node_id, child, key)
                    else:
                        inspect_selectors(child)
            elif isinstance(value, list):
                for child in value:
                    inspect_selectors(child)
        inspect_selectors(data)

    if isinstance(root.get("dependencies"), list) and not root["dependencies"] and "llm" in node_types.values():
        warnings.append("dependencies 未锁定模型插件版本；离线编译不会猜测插件版本或唯一标识，目标环境需具备该 provider。")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "nodes": len(raw_nodes)}

