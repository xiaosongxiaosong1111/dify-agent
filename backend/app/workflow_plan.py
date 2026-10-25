"""Workflow-plan IR compiler for Dify 1.17.1.

Only the node subset in ``docs/workflow-plan-contract.md`` is emitted. Code
nodes are syntax checked, never executed by this process; Dify's sandbox owns
their runtime.
"""

from __future__ import annotations
from .model_parameters import completion_parameters, validate_node_model, resolve_node_model, needs_task_model
from .conversation import memory_configuration
from .conversation_state import native as native_conversation
from .schedule_trigger import ROOT_ENTRY_TYPES
from .iteration import plan_nodes, validate_container_ids, validate_iteration, native_iteration
from .retrieval_settings import dataset_ids as retrieval_ids, validate as validate_retrieval, native as native_retrieval
from .loop import validate_loop,variable_types as loop_types,native_loop
from .http_execution import validate as validate_http_execution, native as native_http_execution
from .http_auth_reference import settings as http_auth_settings, native as native_http_auth, declarations as http_secret_declarations

from .file_inputs import native as native_file_input
from .json_inputs import native as native_json_input

import ast
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import parse_qsl, urlparse

import yaml

from app.dsl import DSL_VERSION, TARGET_DIFY_VERSION, MOCK_DEPENDENCY_WARNING, mock_dependency_notice

SUPPORTED_PLAN_NODES = (
    "start",
    "trigger-schedule",
    "human-input",
    "llm",
    "question-classifier",
    "parameter-extractor",
    "list-operator",
    "document-extractor",
    "knowledge-retrieval",
    "if-else",
    "code",
    "template-transform",
    "http-request",
    "iteration",
    "loop",
    "variable-aggregator",
    "assigner",
    "end",
    "answer",
)

_REF = re.compile(r"\{\{#([\w-]+)\.([\w-]+)#\}\}")
from .condition_settings import OPERATORS as _CONDITION_OPERATORS
_SECRET_NAMES = {"authorization", "proxy-authorization", "cookie", "set-cookie", "api-key", "x-api-key", "token", "secret", "password"}
_URL_SECRET_NAMES = {"key", "api_key", "apikey", "token", "secret", "password", "authorization", "auth"}
_SYSTEM_VARIABLES = {"query"}


def _result(errors: list[str], warnings: list[str], nodes: int) -> dict:
    return {"valid": not errors, "errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings)), "nodes": nodes}


def _vars(config: dict) -> list:
    value = config.get("variables", [])
    return value if isinstance(value, list) else []


def _placeholder_refs(text: Any) -> list[tuple[str, str]]:
    return _REF.findall(text) if isinstance(text, str) else []


def _http_refs(config):
    """Inspect native request templates and file selectors without resolving them."""
    found=[];pending=[(key,config[key]) for key in ('url','headers','params','body') if key in config];seen=set();count=0
    while pending:
        field,value=pending.pop();count+=1
        if count>20000:
            found.append(('request_structure_limit',[]));break
        if isinstance(value,(dict,list)):
            if id(value) in seen:
                found.append(('request_shared_or_cyclic_structure',[]));continue
            seen.add(id(value))
        if isinstance(value,str):
            matches=list(re.finditer(r'\{\{#(.*?)#\}\}',value))
            found.extend((field+' reference',match.group(1).split('.')) for match in matches)
            if value.count('{{#')!=len(matches):found.append((field+' malformed reference',[]))
        elif isinstance(value,dict):
            for key,child in value.items():
                if key=='value_selector':found.append((field+'.value_selector',child))
                else:pending.append((field+'.'+str(key),child))
        elif isinstance(value,list):pending.extend((f'{field}[{i}]',child) for i,child in enumerate(value))
    return found


def _http_security_errors(config: dict, declared_secrets=None) -> list[str]:
    errors: list[str] = []
    from .body_http import validate as validate_read,KEY
    if KEY in config:errors.extend(validate_read(config))
    raw_url = config.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        errors.append("http-request 必须提供实际 url；不会生成 mock 或占位 URL")
    else:
        try:
            parsed = urlparse(raw_url.strip())
            hostname = parsed.hostname
        except ValueError:
            return ["http-request.url 不是有效 URL"]
        if parsed.scheme not in {"http", "https"} or not hostname:
            errors.append("http-request.url 必须是绝对 HTTP(S) URL")
        if parsed.username or parsed.password:
            errors.append("http-request.url 不得嵌入用户名或密码")
        if hostname and hostname.lower() in {"example.com", "example.org", "example.net"}:
            errors.append("http-request.url 不得使用 example.com 等文档占位域名")
        if hostname and hostname.lower().endswith(".invalid"):
            errors.append("http-request.url 不得使用 .invalid 占位域名")
        if any(key.lower() in _URL_SECRET_NAMES for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            errors.append("http-request.url 查询参数不得包含 API key、token 或其他凭据")
    headers = config.get("headers", "")
    if not isinstance(headers, str):
        errors.append("http-request.headers 必须是原生字符串")
    else:
        for line in headers.splitlines():
            name = line.split(":", 1)[0].strip().lower() if ":" in line else ""
            if name in _SECRET_NAMES or name.startswith("x-api-"):
                errors.append(f"http-request.headers 不得内嵌凭据字段：{name or 'unknown'}")
                break
        if re.search(r"(?i)\bbearer\s+\S+", headers):
            errors.append("http-request.headers 不得内嵌 Bearer 凭据")
    authorization = config.get("authorization")
    params = config.get('params','')
    if isinstance(params,str) and any(re.split(r'[:=]',line,maxsplit=1)[0].strip().lower() in _URL_SECRET_NAMES for line in params.splitlines()):
        errors.append('http-request.params 不得包含 API key、token 或其他凭据字段')
    if authorization is not None and authorization != {"type": "no-auth", "config": None}:
        if declared_secrets is None:
            errors.append('HTTP 计划不得填写原生认证凭据；请使用 authentication 的空秘密变量声明。')
        else:
            from .http_auth_reference import preserved as preserved_http_auth
            try:preserved_http_auth(config,declared_secrets)
            except ValueError as exc:errors.append(str(exc))
    try:http_auth_settings(config)
    except ValueError as exc:errors.append(str(exc))
    return errors


def _has_secret_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in {"apikey", "authorization", "token", "secret", "password", "credential", "credentials", "cookie"}:
                return True
            if _has_secret_field(child):
                return True
    elif isinstance(value, list):
        return any(_has_secret_field(item) for item in value)
    return False


def _syntax_check(code: str, language: str) -> str | None:
    """Parse code without evaluating it. JS uses Node's parser-only --check."""
    if language == "python3":
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return f"Python 代码语法错误：{exc.msg}（第 {exc.lineno} 行）"
        return None
    node = shutil.which("node")
    if not node:
        return "当前主机没有 Node.js parser，JavaScript 语法未验证；请在 Dify 沙箱验证。"
    try:
        checked = subprocess.run([node, "--check", "-"], input=code, capture_output=True, text=True, timeout=5, check=False)
        if checked.returncode:
            detail = (checked.stderr or checked.stdout).strip().splitlines()
            return "JavaScript 代码语法错误：" + (detail[-1] if detail else "parser check failed")
        return None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"JavaScript parser 检查失败：{exc}"


def _task_mode(task: dict) -> str | None:
    return task.get("app_type") if isinstance(task, dict) else None


def validate_plan(task: dict, plan: dict, *, _scope_types=None, _scope_file_items=None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(task, dict):
        return _result(["task 必须是对象"], warnings, 0)
    mode = _task_mode(task)
    if not isinstance(mode, str) or mode not in {"workflow", "advanced-chat"}:
        errors.append("计划编译只支持 workflow 和 advanced-chat；不会替换用户选择的应用类型")
    if not isinstance(plan, dict):
        return _result(errors + ["workflow_plan 必须是对象"], warnings, 0)
    if isinstance(plan.get("schema_version"), bool) or plan.get("schema_version") != 1:
        errors.append("workflow_plan.schema_version 必须为 1")
    nodes = plan.get("nodes")
    edges = plan.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return _result(errors + ["workflow_plan.nodes 必须是非空数组"], warnings, 0)
    if not isinstance(edges, list):
        errors.append("workflow_plan.edges 必须是数组")
        edges = []

    from .conversation_state import declarations as conversation_declarations
    conversation_errors,conversation_types=conversation_declarations(plan,mode)
    errors.extend(conversation_errors)
    if conversation_types:_scope_types={**(_scope_types or {}),**{('conversation',name):kind for name,kind in conversation_types.items()}}
    raw_task_config = task.get("configuration", {})
    if not isinstance(raw_task_config, dict):
        errors.append("task.configuration 必须是对象")
        raw_task_config = {}

    try:
        memory_configuration(mode,raw_task_config)
    except ValueError as exc:
        errors.append(str(exc))

    by_id: dict[str, dict] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{index}] 必须是对象")
            continue
        node_id, node_type, config = node.get("id"), node.get("type"), node.get("config", {})
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"nodes[{index}].id 必须是非空字符串")
            continue
        if node_id in by_id:
            errors.append(f"节点 id 重复：{node_id}")
            continue
        if not isinstance(node_type, str) or node_type not in SUPPORTED_PLAN_NODES:
            errors.append(f"节点 {node_id} 的类型 {node_type!r} 不在支持范围内")
            node_type = None
        if not isinstance(config, dict):
            errors.append(f"节点 {node_id}.config 必须是对象")
            config = {}
        by_id[node_id] = {**node, "id": node_id, "type": node_type, "config": config}

    starts = [node_id for node_id, node in by_id.items() if node["type"] in ROOT_ENTRY_TYPES]
    terminals = [node_id for node_id, node in by_id.items() if node["type"] in {"end", "answer"}]
    if len(starts) != 1:
        errors.append("计划必须包含且仅包含一个入口（start或Workflow trigger-schedule），不能共存或猜多入口")
    if not terminals:
        errors.append("计划必须包含至少一个 end 或 answer 终点")
    start_id = starts[0] if len(starts) == 1 else None
    if mode == "workflow" and any(by_id[t]["type"] != "end" for t in terminals):
        errors.append("workflow 计划终点只能使用 end")
    if mode == "advanced-chat" and any(by_id[t]["type"] != "answer" for t in terminals):
        errors.append("advanced-chat 计划终点只能使用 answer")

    if conversation_types and any(n.get('id')=='conversation' for n in plan_nodes(plan)):errors.append('conversation是持久状态命名空间，请明确改名同名节点，不能猜selector来源。')
    config_by_id = {node_id: node["config"] for node_id, node in by_id.items()}
    outputs: dict[str, set[str]] = {}
    branch_ids: dict[str, set[str]] = {}
    for node_id, node in by_id.items():
        kind, config = node["type"], node["config"]
        from .node_policy import validate_ir as validate_node_policy
        errors.extend(f'节点 {node_id}：{message}' for message in validate_node_policy(kind,config))
        if kind=='trigger-schedule':
            from .schedule_trigger import validate as validate_schedule,RUNTIME_LIMIT
            errors.extend(f'定时入口 {node_id}：{e}' for e in validate_schedule(config,mode))
            warnings.append(RUNTIME_LIMIT)
        if kind == "start":
            variables = config.get("variables", [])
            if not isinstance(variables, list):
                errors.append(f"start {node_id}.variables 必须是数组")
                variables = []
            names: set[str] = set()
            for i, variable in enumerate(variables):
                if not isinstance(variable, dict) or not isinstance(variable.get("variable"), str) or not variable["variable"]:
                    errors.append(f"start {node_id}.variables[{i}] 缺少 variable 名称")
                    continue
                if variable["variable"] in names:
                    errors.append(f"start {node_id} 变量名重复：{variable['variable']}")
                names.add(variable["variable"])
                from .start_inputs import validate_variable
                errors.extend(f"start {node_id} 变量 {variable['variable']}：{message}" for message in validate_variable(variable))
            from .file_inputs import has_files,RUNTIME_LIMIT
            if has_files(variables):
                warnings.append(RUNTIME_LIMIT)
                if mode!='workflow' or _scope_types is not None:errors.append('文件开始入口首批仅适配根Workflow，不改变用户应用类型或容器范围。')
            from .json_inputs import has_objects,NOTE as JSON_INPUT_NOTE
            if has_objects(variables):
                warnings.append(JSON_INPUT_NOTE)
                if mode!='workflow' or _scope_types is not None:errors.append('JSON对象入口首批仅根Workflow；不猜Chatflow字典初始参数／容器入口或自动换应用类型。')
            outputs[node_id] = names
            if mode == "advanced-chat" and names & {'query', 'conversation_id'}:
                errors.append("Chatflow 的 query／conversation_id 是试跑传输保留名，开始变量请使用其它名称；用户问题仍引用 sys.query。")
        elif kind=='trigger-schedule':outputs[node_id]=set()
        elif kind=='human-input':
            from .human_review import validate as validate_review,HANDLES,RUNTIME_LIMIT
            errors.extend(f'人工审核 {node_id}：{e}' for e in validate_review(config,mode));outputs[node_id]=set();branch_ids[node_id]=HANDLES
            warnings.append(RUNTIME_LIMIT)
            if _scope_types is not None or any(n.get('type')=='trigger-schedule' for n in nodes if isinstance(n,dict)):errors.append('首批人工审核不进入迭代／循环，也不与定时入口组合；不猜等待与送达行为。')
        elif kind=='assigner':
            from .conversation_state import validate_assignment
            errors.extend(f'持久状态赋值 {node_id}：{e}' for e in validate_assignment(config,conversation_types,mode))
            outputs[node_id]=set()
            warnings.append('持久状态赋值无节点输出，更新已声明conversation值；未执行时保留当前值，每个conversation独立。新会话初始值、同会话多轮、分支未更新与并发须实际验收；不是聊天历史或跨用户共享。')
        elif kind == "llm":
            from .structured_output import validate as validate_structured, output_type as structured_type, NOTE as STRUCTURED_NOTE
            errors.extend(f'LLM {node_id}：{message}' for message in validate_structured(config))
            outputs[node_id] = {"text", "usage", "finish_reason", "files"}
            if structured_type(config): outputs[node_id].add('structured_output')
            if config.get('structured_output_enabled') is True: warnings.append(STRUCTURED_NOTE)
            if 'model' in config:
                try:validate_node_model(config['model'])
                except ValueError as exc:errors.append(f'LLM {node_id}：{exc}')
                warnings.append(f'LLM {node_id} 使用独立模型和完整参数；实际供应商／型号、参数规则、插件、限流和费用尚需核对，不是已验证可用。')
            system_prompt, user_prompt = config.get("system_prompt", ""), config.get("user_prompt", "")
            if not isinstance(system_prompt, str) or not isinstance(user_prompt, str):
                errors.append(f"LLM {node_id} 的 system_prompt 和 user_prompt 必须是字符串")
            elif not (system_prompt.strip() or user_prompt.strip()):
                errors.append(f"LLM {node_id} 至少要有 system_prompt 或 user_prompt")
            selector = config.get("context_variable_selector")
            if selector is not None and (not isinstance(selector, list) or len(selector) != 2):
                errors.append(f"LLM {node_id}.context_variable_selector 必须是 [节点ID, 变量名]")
        elif kind=='document-extractor':
            from .document_extractor import validate as validate_document,NOTE as DOCUMENT_NOTE
            errors.extend(f'文档提取 {node_id}：{message}' for message in validate_document(config))
            outputs[node_id]={'text'}
            warnings.append(f'文档提取 {node_id}：{DOCUMENT_NOTE}')
        elif kind=='list-operator':
            from .list_operator import validate as validate_list,NOTE as LIST_NOTE
            errors.extend(f'数组处理 {node_id}：{message}' for message in validate_list(config))
            outputs[node_id]={'result'}
            warnings.append(f'数组处理 {node_id}：{LIST_NOTE} 静态检查不证明实际数组内容和序号有效。')
        elif kind=='parameter-extractor':
            from .parameter_extractor import validate as validate_extractor,output_types,NOTE
            errors.extend(f'提取 {node_id}：{message}' for message in validate_extractor(config))
            outputs[node_id]=set(output_types(config))
            warnings.append(f'提取 {node_id}：{NOTE} 该节点会调用模型，资源／抽取质量与业务值尚未实际验证。')
        elif kind=='question-classifier':
            from .question_classifier import validate as validate_classifier,branches as classifier_branches,FALLBACK_NOTE
            errors.extend(f'分类 {node_id}：{message}' for message in validate_classifier(config))
            outputs[node_id]={'class_id','class_name','class_label','usage'}
            branch_ids[node_id]=classifier_branches(config)
            warnings.append(f'分类 {node_id}：{FALLBACK_NOTE} 分类会调用模型、增加费用，准确性及各分支未实际验证。')
        elif kind=='loop':
            outputs[node_id]=set(loop_types(config))
        elif kind == "knowledge-retrieval":
            retrieval_errors,retrieval_warnings=validate_retrieval(config,raw_task_config)
            errors.extend(f'知识检索 {node_id}：{message}' for message in retrieval_errors)
            warnings.extend(f'知识检索 {node_id}：{message}' for message in retrieval_warnings)
            top_k = config.get("top_k", raw_task_config.get("retrieval_top_k", 3))
            if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
                errors.append(f"知识检索 {node_id}.top_k 必须是正整数")
            outputs[node_id] = {"result"}
        elif kind == "if-else":
            from .condition_settings import validate as validate_conditions
            errors.extend(f'条件 {node_id}：{error}' for error in validate_conditions(config))
            cases = config.get("cases")
            if not isinstance(cases, list) or not cases:
                errors.append(f"if-else {node_id} 必须包含至少一个 case")
                cases = []
            ids: list[str] = []
            for i, case in enumerate(cases):
                if not isinstance(case, dict):
                    errors.append(f"if-else {node_id}.cases[{i}] 必须是对象")
                    continue
                case_id = case.get("case_id")
                conditions = case.get("conditions")
                if not isinstance(case_id, str) or not case_id or case_id == "false":
                    errors.append(f"if-else {node_id}.cases[{i}].case_id 必须是非空且不等于 false")
                elif case_id in ids:
                    errors.append(f"if-else {node_id} case_id 重复：{case_id}")
                else:
                    ids.append(case_id)
                if not isinstance(case.get("logical_operator"), str) or case.get("logical_operator") not in {"and", "or"}:
                    errors.append(f"if-else {node_id} case {case_id!r} logical_operator 必须为 and 或 or")
                if not isinstance(conditions, list) or not conditions:
                    errors.append(f"if-else {node_id} case {case_id!r} 必须至少有一个 condition")
                else:
                    for j, condition in enumerate(conditions):
                        if not isinstance(condition, dict):
                            errors.append(f"if-else {node_id} case {case_id!r} condition[{j}] 必须是对象")
                            continue
                        if not isinstance(condition.get("comparison_operator"), str) or condition.get("comparison_operator") not in _CONDITION_OPERATORS:
                            errors.append(f"if-else {node_id} condition[{j}] comparison_operator 不受支持")
                        if not isinstance(condition.get("varType"), str) or not condition["varType"]:
                            errors.append(f"if-else {node_id} condition[{j}] 必须提供 varType")
                        if "value" not in condition:
                            errors.append(f"if-else {node_id} condition[{j}] 必须提供 value 字段")
            branch_ids[node_id] = set(ids) | {"false"}
            outputs[node_id] = set()
        elif kind == "code":
            from .structured_guard import validate_generated
            errors.extend(f'代码 {node_id}：{message}' for message in validate_generated(node, by_id, edges, mode=mode, nested=_scope_types is not None))
            from .file_join import validate_generated as validate_file_join
            errors.extend(f'代码 {node_id}：{message}' for message in validate_file_join(node, by_id, edges, mode=mode, nested=_scope_types is not None))
            outputs_schema = config.get("outputs")
            if not isinstance(outputs_schema, dict) or not outputs_schema:
                errors.append(f"code {node_id}.outputs 必须是非空对象")
                outputs_schema = {}
            for output_name, output_schema in outputs_schema.items():
                if not isinstance(output_name, str) or not isinstance(output_schema, dict) or not isinstance(output_schema.get("type"), str):
                    errors.append(f"code {node_id}.outputs 中每项必须定义名称和 type")
            outputs[node_id] = set(outputs_schema)
            language, code = config.get("code_language"), config.get("code")
            if not isinstance(language, str) or language not in {"python3", "javascript"}:
                errors.append(f"code {node_id}.code_language 只支持 python3 或 javascript")
            elif not isinstance(code, str) or not code.strip():
                errors.append(f"code {node_id}.code 必须是非空字符串")
            else:
                syntax_error = _syntax_check(code, language)
                if syntax_error:
                    if language == "javascript" and syntax_error.startswith("当前主机没有"):
                        warnings.append(f"节点 {node_id}：{syntax_error}")
                    else:
                        errors.append(f"节点 {node_id}：{syntax_error}")
            input_variables = config.get("variables", [])
            if not isinstance(input_variables, list):
                errors.append(f"code {node_id}.variables 必须是数组")
            else:
                for i, item in enumerate(input_variables):
                    if not isinstance(item, dict) or not isinstance(item.get("variable"), str) or not item.get("variable"):
                        errors.append(f"code {node_id}.variables[{i}] 必须包含 variable")
                    elif not isinstance(item.get("value_selector"), list) or len(item["value_selector"]) != 2:
                        errors.append(f"code {node_id}.variables[{i}].value_selector 必须引用一个变量")
                if language=='python3' and isinstance(code,str) and code.strip() and all(isinstance(v,dict) and isinstance(v.get('variable'),str) and v['variable'] for v in input_variables):
                    from .code_entry_contract import check as check_code_entry
                    entry_errors,entry_warnings=check_code_entry(code,[v['variable'] for v in input_variables])
                    errors.extend(f'节点 {node_id}：{message}' for message in entry_errors)
                    warnings.extend(f'节点 {node_id}：{message}' for message in entry_warnings)
        elif kind == "template-transform":
            if not isinstance(config.get("template"), str) or not config["template"].strip():
                errors.append(f"template-transform {node_id}.template 必须是非空字符串")
            outputs[node_id] = {"output"}
            input_variables = config.get("variables", [])
            if not isinstance(input_variables, list):
                errors.append(f"template-transform {node_id}.variables 必须是数组")
            else:
                for i, item in enumerate(input_variables):
                    if not isinstance(item, dict) or not isinstance(item.get("variable"), str) or not item.get("variable"):
                        errors.append(f"template-transform {node_id}.variables[{i}] 必须包含 variable")
                    elif not isinstance(item.get("value_selector"), list) or len(item["value_selector"]) != 2:
                        errors.append(f"template-transform {node_id}.variables[{i}].value_selector 必须引用一个变量")
        elif kind == "http-request":
            outputs[node_id] = {"status_code", "body", "headers", "files"}
            errors.extend(f"节点 {node_id}：{message}" for message in _http_security_errors(config))
            if config.get('authentication') is not None:
                warnings.append(f'HTTP 节点 {node_id}：DSL 仅声明空秘密环境变量；导入后须在 Dify 补齐凭据，未补齐不可运行。认证／权限／业务响应均未验证，Sierra 不接收该接口的密钥。')
            method = config.get("method", "get")
            if not isinstance(method, str) or method.lower() not in {"get", "post", "head", "patch", "put", "delete"}:
                errors.append(f"http-request {node_id}.method 不受支持")
            for field in ("params",):
                if field in config and not isinstance(config[field], str):
                    errors.append(f"http-request {node_id}.{field} 必须是字符串")
            body = config.get("body", {"type": "none", "data": []})
            if (
                not isinstance(body, dict)
                or not isinstance(body.get("type"), str)
                or body.get("type") not in {"none", "form-data", "x-www-form-urlencoded", "raw-text", "json", "binary"}
                or "data" not in body
            ):
                errors.append(f"http-request {node_id}.body 必须符合 Dify 1.17.1 的 type/data 结构")
            from .http_body import validate as validate_http_body
            body_errors,body_warnings=validate_http_body(body)
            errors.extend(f'HTTP 节点 {node_id}：{message}' for message in body_errors)
            warnings.extend(f'HTTP 节点 {node_id}：{message}' for message in body_warnings)
            policy_errors, policy_warnings = validate_http_execution(config)
            errors.extend(f'HTTP 节点 {node_id}：{message}' for message in policy_errors)
            warnings.extend(f'HTTP 节点 {node_id}：{message}' for message in policy_warnings)
            input_variables = config.get("variables", [])
            if not isinstance(input_variables, list):
                errors.append(f"http-request {node_id}.variables 必须是数组")
            else:
                for i, item in enumerate(input_variables):
                    if not isinstance(item, dict) or not isinstance(item.get("variable"), str) or not item.get("variable"):
                        errors.append(f"http-request {node_id}.variables[{i}] 必须包含 variable")
                    elif not isinstance(item.get("value_selector"), list) or len(item["value_selector"]) != 2:
                        errors.append(f"http-request {node_id}.variables[{i}].value_selector 必须引用一个变量")
        elif kind == "iteration":
            outputs[node_id] = {"output"}
        elif kind == 'variable-aggregator':
            outputs[node_id] = {'output'}
        elif kind == "end":
            from .terminal_settings import validate as validate_terminal
            terminal_errors,terminal_warnings=validate_terminal(kind,config)
            errors.extend(f'终点 {node_id}：{message}' for message in terminal_errors);warnings.extend(terminal_warnings)
            terminal_outputs = config.get("outputs")
            if not isinstance(terminal_outputs, list) or not terminal_outputs:
                errors.append(f"end {node_id}.outputs 必须是非空数组")
            elif any(
                not isinstance(output, dict)
                or not isinstance(output.get("variable"), str)
                or not output.get("variable")
                or not isinstance(output.get("value_selector"), list)
                or len(output["value_selector"]) != 2
                for output in terminal_outputs
            ):
                errors.append(f"end {node_id}.outputs 每项必须含 variable 与 [节点ID, 变量名] value_selector")
        elif kind == "answer":
            from .terminal_settings import validate as validate_terminal
            terminal_errors,terminal_warnings=validate_terminal(kind,config)
            errors.extend(f'回答 {node_id}：{message}' for message in terminal_errors);warnings.extend(terminal_warnings)
            if not isinstance(config.get("answer"), str) or not config["answer"].strip():
                errors.append(f"answer {node_id}.answer 必须是非空字符串")

        secret_scan = {key: value for key, value in config.items() if not (kind == "http-request" and key == "authorization")}
        if _has_secret_field(secret_scan):
            errors.append(f"节点 {node_id}.config 包含凭据字段；DSL 不得嵌入密钥或令牌")
        if kind == "code" and isinstance(config.get("code_language"), str) and config.get("code_language") in {"python3", "javascript"}:
            scope='语法及可判定的Python入口绑定检查' if config.get('code_language')=='python3' else '语法检查'
            warnings.append(f"节点 {node_id} 的代码只做{scope}，实际必须在 Dify 沙箱中运行；本机未执行代码")

    if needs_task_model(plan) and any(node['type'] in ('llm','question-classifier','parameter-extractor') for node in by_id.values()):
        provider, model = raw_task_config.get("dify_model_provider"), raw_task_config.get("dify_model")
        if not isinstance(provider, str) or not provider.strip() or not isinstance(model, str) or not model.strip():
            warnings.append("计划包含 LLM／问题分类模型调用，但尚未配置真实 dify_model_provider/dify_model；保存计划不受阻，构建 DSL 前必须提供")

    successors: dict[str, list[tuple[str, str]]] = {node_id: [] for node_id in by_id}
    predecessors: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] 必须是对象")
            continue
        source, target = edge.get("source"), edge.get("target")
        handle = edge.get("source_handle", edge.get("sourceHandle", "source"))
        if not isinstance(source, str) or not isinstance(target, str):
            errors.append(f"edges[{i}].source 和 target 必须是字符串")
            continue
        if source not in by_id or target not in by_id:
            errors.append(f"边引用不存在节点：{source!r} -> {target!r}")
            continue
        if not isinstance(handle, str):
            errors.append(f"edges[{i}].source_handle 必须是字符串")
            continue
        if by_id[source]["type"] == "if-else" and handle not in branch_ids.get(source, {"false"}):
            errors.append(f"if-else {source} 的边 handle {handle!r} 不是已声明 case 或 false")
        if by_id[source]['type']=='question-classifier' and (handle not in branch_ids.get(source,set()) or not {'source_handle','sourceHandle'}&set(edge)):
            errors.append(f'分类 {source} 的边须明确使用已声明类别 id，不能采用默认／未声明出口。')
        if by_id[source]['type']=='human-input' and (handle not in branch_ids.get(source,set()) or not {'source_handle','sourceHandle'}&set(edge)):errors.append('人工审核每条边须明确approve/reject/__timeout出口，不能采用默认或未声明分支。')
        if by_id[source]['type']=='loop' and handle!='source':errors.append('首批循环只能使用 source 出口；不能绕过停止复核或假装已支持失败分支。')
        successors[source].append((target, handle))
        predecessors[target].add(source)

    if conversation_types:
        for current_id,links in successors.items():
            if by_id[current_id]['type'] not in {'if-else','question-classifier'} and len(links)>1:errors.append('首批持久状态不与根隐式并行分叉共存，须明确串行或条件分支；不能猜读写先后。')
    for node_id, branches in branch_ids.items():
        outgoing = [handle for _, handle in successors.get(node_id, [])]
        for branch in branches:
            if outgoing.count(branch) != 1:
                errors.append(f"{by_id[node_id]['type']} {node_id} 分支 {branch!r} 必须且仅能有一条出口边")
        if by_id[node_id]['type']=='human-input' and len({target for target,_ in successors.get(node_id,[])})!=3:errors.append('首批审核三路须各有独立入口，分别明确批准／拒绝／超时行为，不猜统一处理。')
        if len(outgoing) != len(branches):
            errors.append(f"{by_id[node_id]['type']} {node_id} 存在重复或未声明的分支出口")

    for terminal in terminals:
        if successors.get(terminal):
            errors.append(f"终点 {terminal} 不能再有 outgoing edge")
    from .parameter_extractor import guards as extractor_guards
    guard_errors,extractor_success_targets=extractor_guards(by_id,successors)
    errors.extend(guard_errors)

    # Require a DAG and compute reachability on validated endpoints.
    indegree = {node_id: len(predecessors[node_id]) for node_id in by_id}
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    topo: list[str] = []
    while queue:
        current = queue.pop()
        topo.append(current)
        for target, _ in successors[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(topo) != len(by_id):
        errors.append("workflow_plan 不支持有向环或 loop")

    reachable: set[str] = set()
    if start_id:
        reachable.add(start_id)
        stack = [start_id]
        while stack:
            current = stack.pop()
            for target, _ in successors.get(current, []):
                if target not in reachable:
                    reachable.add(target)
                    stack.append(target)
        for node_id in by_id:
            if node_id not in reachable:
                errors.append(f"节点不可从 start 到达：{node_id}")

    can_reach_terminal: set[str] = set(terminals)
    stack = list(terminals)
    while stack:
        current = stack.pop()
        for source in predecessors.get(current, set()):
            if source not in can_reach_terminal:
                can_reach_terminal.add(source)
                stack.append(source)
    for node_id in by_id:
        if node_id not in can_reach_terminal:
            errors.append(f"节点存在无法到达终点的死路径：{node_id}")

    # Dominators enforce variables available on every path, preventing use of
    # values that exist only in a sibling branch.
    dominators: dict[str, set[str]] = {}
    if start_id:
        for node_id in by_id:
            dominators[node_id] = {node_id} if node_id == start_id else set(by_id)
        changed = True
        while changed:
            changed = False
            for node_id in topo:
                if node_id == start_id:
                    continue
                preds = [p for p in predecessors[node_id] if p in reachable]
                new = {node_id} | (set.intersection(*(dominators[p] for p in preds)) if preds else set())
                if new != dominators[node_id]:
                    dominators[node_id] = new
                    changed = True

    state_writers={}
    for current_id,current in by_id.items():
        if current['type']!='assigner':continue
        for row in current['config'].get('items',[]) if isinstance(current['config'].get('items'),list) else []:
            target=row.get('variable_selector') if isinstance(row,dict) else None
            if isinstance(target,list) and len(target)==2 and target[0]=='conversation' and isinstance(target[1],str):
                if target[1] in state_writers and state_writers[target[1]]!=current_id:errors.append('首批同一状态在一次图执行中只允许一个根赋值节点，不猜多个写入节点的顺序或分支合并。')
                state_writers[target[1]]=current_id
    from .extraction_safety import reachable as success_reachable
    failed_success_paths={}

    def check_ref(node_id: str, selector: Any, field: str) -> None:
        if not isinstance(selector, list) or len(selector) != 2 or not all(isinstance(part, str) for part in selector):
            errors.append(f"节点 {node_id} 的 {field} 必须是 [节点ID, 变量名]")
            return
        source, variable = selector
        if source=='conversation' and conversation_types:
            if mode!='advanced-chat' or variable not in conversation_types:errors.append(f'节点 {node_id} 的 {field} 只允许本Chatflow已声明的conversation状态；容器内读取尚未适配。')
            return
        if source == "sys":
            if mode != "advanced-chat" or variable not in _SYSTEM_VARIABLES:
                errors.append(f"节点 {node_id} 的 {field} 只能在 Chatflow 引用 sys.query")
            elif start_id is None or start_id not in dominators.get(node_id, set()):
                errors.append(f"节点 {node_id} 的 sys.query 不在所有执行路径上游")
            return
        if source not in by_id:
            errors.append(f"节点 {node_id} 的 {field} 引用了不存在节点：{source}")
            return
        if source == node_id:
            errors.append(f"节点 {node_id} 的 {field} 不能引用自身尚未生成的输出")
            return
        if by_id[source]['type']=='parameter-extractor' and variable not in {'__is_success','__reason','__usage'} and extractor_success_targets.get(source) not in dominators.get(node_id,set()):
            errors.append(f'节点 {node_id} 的 {field} 使用了未经成功分支保护的提取参数 {source}.{variable}，不能使用失败默认值。')
        if by_id[source]['type']=='parameter-extractor' and variable not in {'__is_success','__reason','__usage'} and source in extractor_success_targets:
            if source not in failed_success_paths:
                policy=by_id[source]['config']['failure_policy']
                failed_success_paths[source]=success_reachable(start_id,successors,(policy['guard_node_id'],extractor_success_targets[source],policy['success_case_id']))
            if node_id in failed_success_paths[source]:errors.append(f'节点 {node_id} 的 {field} 可能从提取失败路径到达，不能绕回成功节点后使用默认业务值。')
        if source not in dominators.get(node_id, set()):
            errors.append(f"节点 {node_id} 的 {field} 引用源 {source} 不保证在所有路径上游（可能来自兄弟分支）")
            return
        if variable not in outputs.get(source, set()):
            errors.append(f"节点 {node_id} 的 {field} 引用了不存在变量：{source}.{variable}")

    def selectors_for(node: dict) -> list[tuple[str, Any]]:
        kind, config, node_id = node["type"], node["config"], node["id"]
        found: list[tuple[str, Any]] = []
        if kind == "llm":
            if config.get("context_variable_selector") is not None:
                found.append(("context_variable_selector", config["context_variable_selector"]))
            for field in ("system_prompt", "user_prompt"):
                found.extend((f"{field} reference", [src, var]) for src, var in _placeholder_refs(config.get(field)))
        elif kind=='assigner':
            from .declared_types import resolve
            for i,row in enumerate(config.get('items',[]) if isinstance(config.get('items'),list) else []):
                if not isinstance(row,dict):continue
                if row.get('input_type')=='variable':
                    found.append((f'items[{i}].value',row.get('value')))
                    target=row.get('variable_selector');expected=conversation_types.get(target[1]) if isinstance(target,list) and len(target)==2 and isinstance(target[1],str) else None
                    if expected is None or resolve(by_id,row.get('value'),_scope_types,mode)!=expected:errors.append(f'赋值 {node_id} 的来源须有与目标一致的明确标量类型，不猜数组/对象或转换文字数字。')
        elif kind == "document-extractor":
            selector=config.get('variable_selector');found.append(('variable_selector',selector))
            from .declared_types import resolve
            actual=resolve(by_id,selector,_scope_types,mode)
            source=by_id.get(selector[0],{}) if isinstance(selector,list) and len(selector)==2 and isinstance(selector[0],str) else {}
            from .file_inputs import root_source
            if config.get('input_type')=='file':
                if root_source(source,selector,'file'):pass
                elif actual!='file' or not isinstance(selector,list) or len(selector)!=2 or any(not isinstance(v,str) for v in selector) or tuple(selector) not in (_scope_file_items or set()):errors.append(f'单文件文档提取 {node_id} 的is_array_file=false标记须接根Workflow已核对的必填或存在分支保护的可选单文件入口，或原生HTTP.files受保护迭代item；不接受代码伪造file、未知或跨容器来源。')
            elif root_source(source,selector,'file-list'):pass
            elif actual!='array[file]' or source.get('type')!='http-request' or selector[1]!='files':errors.append(f'文档提取 {node_id} 须接全路径上游HTTP.files或根Workflow明确文件列表；不猜URL、对象、未知文件或跨容器来源。')
        elif kind == "list-operator":
            found.append(('variable',config.get('variable')))
            from .declared_types import resolve
            actual=resolve(by_id,config.get('variable'),_scope_types,mode)
            if actual is None or actual!=config.get('input_type'):errors.append(f'数组处理 {node_id} 来源必须有与input_type一致的明确数组声明，不猜未知或转换对象／文字。')
        elif kind == "parameter-extractor":
            found.append(('query',config.get('query')))
            from .declared_types import resolve
            kind_value=resolve(by_id,config.get('query'),_scope_types,mode)
            if kind_value is not None and kind_value!='string':errors.append(f'提取 {node_id} 问题来源必须是文字，不自动转换其他类型。')
            elif kind_value is None:warnings.append(f'提取 {node_id} 来源类型未知，须核对实际文字输入。')
        elif kind == "question-classifier":
            found.append(('query_variable_selector',config.get('query_variable_selector')))
            from .declared_types import resolve
            query_type=resolve(by_id,config.get('query_variable_selector'),_scope_types,mode)
            if query_type is not None and query_type!='string':errors.append(f'分类 {node_id} 问题来源必须是文字，不能自动转换 {query_type}。')
            elif query_type is None:warnings.append(f'分类 {node_id} 问题来源类型未知，需核对实际文字输入。')
        elif kind == "knowledge-retrieval":
            selector = config.get("query_variable_selector")
            if selector is None:
                selector = ["sys", "query"] if mode == "advanced-chat" else [start_id, "query"]
            found.append(("query_variable_selector", selector))
        elif kind == "if-else":
            for ci, case in enumerate(config.get("cases", []) if isinstance(config.get("cases"), list) else []):
                if isinstance(case, dict):
                    for ji, condition in enumerate(case.get("conditions", []) if isinstance(case.get("conditions"), list) else []):
                        if isinstance(condition, dict):
                            found.append((f"cases[{ci}].conditions[{ji}].variable_selector", condition.get("variable_selector")))
                            from .iteration import output_type as condition_source_type
                            selector=condition.get('variable_selector')
                            if isinstance(selector,list) and len(selector)==2 and all(isinstance(v,str) for v in selector):
                                actual_type=(_scope_types[tuple(selector)] if _scope_types and tuple(selector) in _scope_types else 'string' if selector==['sys','query'] else condition_source_type(by_id,selector))
                                if actual_type and condition.get('varType')!=actual_type:
                                    errors.append(f'条件 {node["id"]} cases[{ci}].conditions[{ji}] varType 与已声明来源类型不一致，不自动更改类型或值。')
                            if condition.get('varType')=='file':
                                from .file_inputs import root_source
                                source=by_id.get(selector[0],{}) if isinstance(selector,list) and len(selector)==2 and isinstance(selector[0],str) else {}
                                if not root_source(source,selector,'file'):errors.append(f'条件 {node_id} 单文件存在判断只接已核对根Workflow文件入口，不接受代码对象或跨容器item。')
                            if condition.get('varType')=='array[file]':
                                from .file_inputs import root_source
                                source=by_id.get(selector[0],{}) if isinstance(selector,list) and len(selector)==2 and isinstance(selector[0],str) else {}
                                if not (root_source(source,selector,'file-list') or source.get('type')=='http-request' and selector[1]=='files'):
                                    errors.append(f'条件 {node_id} 文件列表须来自已核对根Workflow文件入口或本作用域HTTP.files，不接受伪造file数组、跨容器或未知来源。')
                            from .condition_settings import value_refs
                            found.extend((f"cases[{ci}].conditions[{ji}].value reference",selector) for selector in value_refs(condition.get('value')))

        elif kind=='human-input':
            from .human_review import references
            from .declared_types import resolve
            for selector in references(config):
                found.append(('form_content reference',selector))
                if resolve(by_id,selector,_scope_types,mode)!='string':errors.append('审核对象只接全路径上游明确文字；数组／对象／数值须先经明确模板，不猜转换。')
        elif kind in {"code", "template-transform", "http-request"}:
            for vi, variable in enumerate(_vars(config)):
                if isinstance(variable, dict):
                    found.append((f"variables[{vi}].value_selector", variable.get("value_selector")))
            if kind == "template-transform":
                for binding in _vars(config):
                    if not isinstance(binding,dict):continue
                    selector=binding.get('value_selector')
                    if isinstance(selector,list) and len(selector)==2 and selector[0]=='conversation' and isinstance(selector[1],str) and selector[1] in conversation_types:
                        if binding.get('value_type','string')!=conversation_types[selector[1]]:errors.append(f'模板 {node_id} 的 value_type 与声明会话状态类型不一致，不隐式转换。')
                for src, var in _placeholder_refs(config.get("template")):
                    found.append(("template reference", [src, var]))
            if kind == 'http-request':found.extend(_http_refs(config))
        elif kind == "end":
            for oi, output in enumerate(config.get("outputs", []) if isinstance(config.get("outputs"), list) else []):
                if isinstance(output, dict):
                    found.append((f"outputs[{oi}].value_selector", output.get("value_selector")))
        elif kind == "answer":
            for src, var in _placeholder_refs(config.get("answer")):
                found.append(("answer reference", [src, var]))
        return found

    for node_id, node in by_id.items():
        for field, selector in selectors_for(node):
            check_ref(node_id, selector, field)
            from .file_inputs import root_source
            if isinstance(selector,list) and len(selector)==2 and isinstance(selector[0],str) and node['type']!='document-extractor' and not (node['type']=='if-else' and field.endswith('.variable_selector') and any(root_source(by_id.get(selector[0],{}),selector,k) for k in ('file','file-list'))) and any(root_source(by_id.get(selector[0],{}),selector,k) for k in ('file','file-list')):
                errors.append(f'节点 {node_id} 的文件入口须先经根文档提取；原始文件到提示词、代码、输出或其它消费者尚未适配，不转成文字。')
            if isinstance(selector,list) and len(selector)==2 and all(isinstance(v,str) for v in selector) and tuple(selector) in (_scope_file_items or set()) and node['type']!='document-extractor':
                errors.append(f'节点 {node_id} 的文件迭代item须先文档提取，不直接传入提示词、模板或代码；文件元数据处理尚未适配。')
            if node['type']=='knowledge-retrieval' and field=='query_variable_selector':
                from .retrieval_settings import validate_query_source
                query_errors,query_warnings=validate_query_source(selector,by_id,mode,_scope_types)
                errors.extend(f'知识检索 {node_id}：{message}' for message in query_errors)
                warnings.extend(f'知识检索 {node_id}：{message}' for message in query_warnings)

    from .optional_file import graph_errors as optional_file_errors
    errors.extend(optional_file_errors(list(by_id.values()),edges))
    from .aggregation import validate_aggregation
    for node in by_id.values():
        if node['type']=='variable-aggregator':
            aggregation_errors,aggregation_warnings=validate_aggregation(node,by_id,outputs,predecessors,start_id,mode)
            # Aggregation intentionally permits partial branch outputs, but native
            # extraction defaults exist even on failure. They need the same gate.
            for index,selector in enumerate(node['config'].get('variables',[]) if isinstance(node['config'].get('variables'),list) else []):
                if isinstance(selector,list) and len(selector)==2 and all(isinstance(v,str) for v in selector) and by_id.get(selector[0],{}).get('type')=='parameter-extractor' and selector[1] not in {'__is_success','__reason','__usage'}:
                    check_ref(node['id'],selector,f'variables[{index}]')
            errors.extend(aggregation_errors);warnings.extend(aggregation_warnings)

    if any(node["type"] in {"iteration","loop"} for node in by_id.values()):
        errors.extend(validate_container_ids(plan))
        for node in by_id.values():
            if node["type"] == "iteration":
                inner_errors, inner_warnings = validate_iteration(task, node, by_id, outputs, dominators, check_ref,conversation_types=conversation_types)
                errors.extend(inner_errors)
                warnings.extend(inner_warnings)
            elif node['type']=='loop':
                inner_errors,inner_warnings=validate_loop(task,node,by_id,outputs,dominators,check_ref,conversation_types=conversation_types)
                errors.extend(f'循环 {node["id"]}：{message}' for message in inner_errors);warnings.extend(inner_warnings)

    if not any(node["type"] in {"llm","question-classifier","parameter-extractor"} for node in by_id.values()):
        pass
    else:
        warnings.append("模型依赖不会编造插件版本或安装凭据；目标 Dify 必须预装配置中指定的 provider/model。")
    if any(node["type"] == "http-request" for node in plan_nodes(plan)):
        try:http_secret_declarations(list(plan_nodes(plan)))
        except ValueError as exc:errors.append(str(exc))
        warnings.append("HTTP URL 与认证声明已静态检查；接口可达性、实际凭据及业务响应未验证。")
    warnings.append("计划编译与静态校验不等于 Dify 1.17.1 导入或运行验证。")
    return _result(errors, warnings, sum(1 for _ in plan_nodes(plan)))


def _native_node(node: dict, x: int) -> dict:
    node_id, kind, config = node["id"], node["type"], node["config"]
    title = node.get("title") or kind
    data: dict[str, Any] = {"desc": "", "selected": False, "title": title, "type": kind}
    if kind=='human-input':
        from .human_review import native as native_review
        data.update(native_review(config))
    elif kind=='trigger-schedule':
        from .schedule_trigger import native as native_schedule
        data.update(native_schedule(config))
    elif kind == "start":
        data["variables"] = [
            native_json_input(variable) if variable.get("type")=="json_object" else native_file_input(variable) if variable.get("type") in {"file","file-list"} else {
                "variable": variable["variable"],
                "label": variable.get("label", variable["variable"]),
                "type": variable.get("type", "text-input"),
                "required": variable.get("required", True),
                "max_length": variable.get("max_length", 50000),
                "options": variable.get("options", []),
                **({"default": variable["default"]} if "default" in variable else {}),
                **({key: variable[key] for key in ('description', 'hide') if key in variable}),
            }
            for variable in config.get("variables", []) if isinstance(variable, dict) and isinstance(variable.get("variable"), str)
        ]
    elif kind == "llm":
        task_config = node["_task_config"]
        model = resolve_node_model(config,task_config)
        memory = memory_configuration(node["_mode"],task_config)
        if memory is not None:data["memory"] = memory
        prompts = []
        if config.get("system_prompt", "").strip():
            prompts.append({"role": "system", "text": config["system_prompt"]})
        if config.get("user_prompt", "").strip():
            prompts.append({"role": "user", "text": config["user_prompt"]})
        selector = config.get("context_variable_selector")
        data.update({
            "model": model,
            "prompt_template": prompts,
            "context": {"enabled": selector is not None, "variable_selector": selector or []},
            "vision": {"enabled": False},
            "variables": [],
        })
        from .structured_output import native as native_structured
        data.update(native_structured(config))
    elif kind == "document-extractor":
        from .document_extractor import native as native_document,NOTE as DOCUMENT_NOTE
        data.update(native_document(config));data['desc']=(data.get('desc','')+' '+DOCUMENT_NOTE).strip()
    elif kind == "list-operator":
        from .list_operator import native as native_list,NOTE as LIST_NOTE
        data.update(native_list(config))
        data['desc']=(data.get('desc','')+' '+LIST_NOTE).strip()
    elif kind == "parameter-extractor":
        from .parameter_extractor import native as native_extractor,NOTE
        data.update(native_extractor(config,node['_task_config'],node['_mode']));data['desc']=(data.get('desc','')+' '+NOTE).strip()
    elif kind == "question-classifier":
        from .question_classifier import native as native_classifier,FALLBACK_NOTE
        data.update(native_classifier(config,node['_task_config'],node['_mode']))
        data['desc']=(data.get('desc','')+' '+FALLBACK_NOTE).strip()
    elif kind == "knowledge-retrieval":
        task_config = node["_task_config"]
        dataset_ids = retrieval_ids(config,task_config)
        selector = config.get("query_variable_selector") or (["sys", "query"] if node["_mode"] == "advanced-chat" else [node["_start_id"], "query"])
        top_k = config.get("top_k", task_config.get("retrieval_top_k", 3))
        data.update({
            "query_variable_selector": selector,
            "query_attachment_selector": [],
            "dataset_ids": dataset_ids,
            "retrieval_mode": "multiple",
            "multiple_retrieval_config": native_retrieval(config,task_config),
            "metadata_filtering_mode": "disabled",
            "vision": {"enabled": False},
        })
    elif kind == "if-else":
        cases = config.get("cases", [])
        native_cases = []
        branches = []
        for index, case in enumerate(cases):
            case_id = case["case_id"]
            branches.append({"id": case_id, "name": "IF" if index == 0 else f"ELIF {index}"})
            native_conditions = []
            for ci, condition in enumerate(case.get("conditions", [])):
                native_conditions.append({
                    "id": condition.get("id", f"condition_{index}_{ci}"),
                    "varType": condition["varType"],
                    "variable_selector": condition["variable_selector"],
                    "comparison_operator": condition["comparison_operator"],
                    "value": condition.get("value", ""),
                })
            native_cases.append({
                "case_id": case_id,
                "logical_operator": case["logical_operator"],
                "conditions": native_conditions,
            })
        branches.append({"id": "false", "name": "ELSE"})
        data.update({"_targetBranches": branches, "cases": native_cases})
    elif kind == "code":
        data.update({
            "code_language": config["code_language"],
            "code": config["code"],
            "variables": config.get("variables", []),
            "outputs": config["outputs"],
        })
    elif kind == "template-transform":
        data.update({"template": config["template"], "variables": config.get("variables", [])})
    elif kind == "http-request":
        from .body_http import KEY,description
        if KEY in config:data["desc"]=description(config)
        data.update({
            "variables": config.get("variables", []),
            "method": config.get("method", "get").lower(),
            "url": config["url"],
            "authorization": native_http_auth(config),
            "headers": config.get("headers", ""),
            "params": config.get("params", ""),
            "body": config.get("body", {"type": "none", "data": []}),
            **native_http_execution(config),
        })
    elif kind=='assigner':
        data.update(version='2',items=config.get('items',[]))
    elif kind == "end":
        data["outputs"] = config.get("outputs", [])
    elif kind == 'variable-aggregator':
        data.update(variables=config['variables'],output_type=config['output_type'],advanced_settings={'group_enabled':False,'groups':[]})
    elif kind == "answer":
        data.update({"answer": config.get("answer", ""), "variables": []})
    position = {"x": x, "y": 282}
    return {
        "data": data,
        "height": 100,
        "id": node_id,
        "position": position,
        "positionAbsolute": position.copy(),
        "selected": False,
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 244,
    }


def compile_workflow_plan(task: dict) -> tuple[str, dict]:
    plan = task.get("workflow_plan") if isinstance(task, dict) else None
    validation = validate_plan(task, plan)
    if not validation["valid"]:
        return "", validation
    mode = task["app_type"]
    task_config = task.get("configuration", {})
    if needs_task_model(plan):
        provider = task_config.get("dify_model_provider") if isinstance(task_config, dict) else None
        model = task_config.get("dify_model") if isinstance(task_config, dict) else None
        if not isinstance(provider, str) or not provider.strip() or not isinstance(model, str) or not model.strip():
            validation["errors"].append("继承任务模型的 LLM 节点必须有 configuration 中明确提供的 dify_model_provider 和 dify_model；独立节点须完整填写 model")
            validation["valid"] = False
            return "", validation
    start_id = next(node["id"] for node in plan["nodes"] if node["type"] in ROOT_ENTRY_TYPES)
    nodes = []
    iteration_edges = []
    loop_guards={}
    node_type_by_id = {node["id"]: node["type"] for node in plan["nodes"]}
    x = 80
    for node in plan["nodes"]:
        internal = {**node, "_task_config": task_config, "_mode": mode, "_start_id": start_id}
        if node["type"] == "iteration":
            emitted_nodes, emitted_edges, width = native_iteration(internal, x, _native_node)
            nodes.extend(emitted_nodes)
            iteration_edges.extend(emitted_edges)
            x += width + 80
        elif node['type']=='loop':
            emitted_nodes,emitted_edges,width,guard_id=native_loop(internal,x,_native_node)
            nodes.extend(emitted_nodes);iteration_edges.extend(emitted_edges);loop_guards[node['id']]=guard_id
            x+=width+380
        else:
            nodes.append(_native_node(internal, x))
            x += 300
    edges = []
    for edge in plan["edges"]:
        source, target = edge["source"], edge["target"]
        source_type, target_type = node_type_by_id[source], node_type_by_id[target]
        if source in loop_guards:source=loop_guards[source];source_type='code'
        handle = edge.get("source_handle", edge.get("sourceHandle", "source"))
        edges.append({
            "data": {"sourceType": source_type, "targetType": target_type},
            "id": f"{source}-{handle}-{target}",
            "source": source,
            "sourceHandle": handle,
            "target": target,
            "targetHandle": edge.get("target_handle", edge.get("targetHandle", "target")),
            "type": "custom",
            "zIndex": 0,
        })
    edges.extend(iteration_edges)
    for source,target in loop_guards.items():edges.append({'id':f'{source}-source-{target}','source':source,'sourceHandle':'source','target':target,'targetHandle':'target','type':'custom','zIndex':0,'data':{'sourceType':'loop','targetType':'code'}})
    dsl = {
        "app": {
            "description": f"由 Sierra 工作流计划生成，目标 Dify {TARGET_DIFY_VERSION}。静态验证通过前不会导入。",
            "icon": "🤖",
            "icon_background": "#FFEAD5",
            "mode": mode,
            "name": str(task.get("name") or "未命名应用"),
            "use_icon_as_answer_icon": False,
        },
        "dependencies": [],
        "kind": "app",
        "version": DSL_VERSION,
        "workflow": {
            "conversation_variables": native_conversation(plan,task),
            "environment_variables": http_secret_declarations(list(plan_nodes(plan))),
            "features": {
                "file_upload": {"enabled": False, "number_limits": 3},
                "opening_statement": task_config.get("opening_statement", ""),
                "retriever_resource": {"enabled": any(n["type"] == "knowledge-retrieval" for n in plan["nodes"])},
                "sensitive_word_avoidance": {"enabled": False},
                "suggested_questions": task_config.get("suggested_questions", []),
                "suggested_questions_after_answer": {"enabled": False},
                "speech_to_text": {"enabled": False},
                "text_to_speech": {"enabled": False, "language": "", "voice": ""},
            },
            "graph": {"edges": edges, "nodes": nodes, "viewport": {"x": 0, "y": 0, "zoom": 1}},
            "rag_pipeline_variables": [],
        },
    }
    if any(n['type']=='trigger-schedule' for n in plan['nodes']):
        from .schedule_trigger import RUNTIME_LIMIT
        dsl['app']['description']+=' '+RUNTIME_LIMIT
    if any(n['type']=='human-input' for n in plan['nodes']):
        from .human_review import RUNTIME_LIMIT
        dsl['app']['description']+=' '+RUNTIME_LIMIT
    mock_note = mock_dependency_notice(task_config)
    if mock_note:
        dsl['app']['description'] += '\n' + mock_note
        validation['warnings'].append(MOCK_DEPENDENCY_WARNING)
    from .mock_handoffs import apply_to_export
    apply_to_export(task, dsl, validation)
    if not validation['valid']:
        return '', validation
    content = yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False)
    return content, validation
