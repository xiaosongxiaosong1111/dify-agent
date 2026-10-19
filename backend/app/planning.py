"""Bounded draft planning. No Dify writes and no generated code execution."""
from __future__ import annotations

import asyncio
import ast
import copy
import hashlib
import io
import json
import math
import time
import tokenize
from decimal import Decimal

from .providers import ProviderError, extract_json

RATE_KEYS = {"input_per_million_usd", "output_per_million_usd", "cached_input_per_million_usd"}
OUTPUT_LIMIT = 6000


def validate_pricing(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - RATE_KEYS:
        raise ValueError("单价需为指定的 USD／百万 tokens 字段。")
    if not {"input_per_million_usd", "output_per_million_usd"}.issubset(value):
        raise ValueError("请同时填写输入、输出单价。")
    for rate in value.values():
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate < 0:
            raise ValueError("模型单价须为有限的非负数。")
    return copy.deepcopy(value)


def _money(tokens, rate):
    return Decimal(tokens) * Decimal(str(rate)) / Decimal(1_000_000)


def reserve_cost(messages, rates, output_limit=OUTPUT_LIMIT):
    # Conservative text estimate; this is not a provider invoice guarantee.
    if any(not isinstance(m.get('content'),str) for m in messages):raise ValueError('非纯文字消息不能按普通文字长度估算费用；图像须有明确预留，不按base64长度猜计费。')
    tokens = sum(len(m["content"].encode("utf-8")) + 64 for m in messages) + 1024
    input_rate = max(rates["input_per_million_usd"], rates.get("cached_input_per_million_usd", 0))
    return _money(tokens, input_rate) + _money(output_limit, rates["output_per_million_usd"])


def usage_cost(usage, rates):
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    if any(type(v) is not int or v < 0 for v in (input_tokens, output_tokens)):
        return None
    if usage.get("cache_creation_input_tokens"):
        # The cache write premium is not described by these three rates.
        return None
    if "cache_read_input_tokens" in usage:
        read = usage["cache_read_input_tokens"]
        if type(read) is not int or read < 0:
            return None
        input_tokens += read
        usage = {**usage, "prompt_cache_hit_tokens": read}
    details=usage.get("prompt_tokens_details")
    cached = usage.get("prompt_cache_hit_tokens", details.get("cached_tokens", 0) if isinstance(details,dict) else 0)
    if type(cached) is not int or not 0 <= cached <= input_tokens:
        cached = 0
    cached_rate = rates.get("cached_input_per_million_usd", rates["input_per_million_usd"])
    return _money(input_tokens - cached, rates["input_per_million_usd"]) + _money(cached, cached_rate) + _money(output_tokens, rates["output_per_million_usd"])


def normalize_draft(plan, *, _body=False, _scope_types=None, _mode=None):
    """Only changes whose meaning is explicit; never invent resource values."""
    plan = copy.deepcopy(plan)
    fixes = []
    if not _body and _mode=='advanced-chat' and plan.get('conversation_variables') and isinstance(plan.get('nodes'),list):
        from .conversation_state import declarations
        from .iteration import plan_nodes
        state_errors,state_types=declarations(plan,_mode)
        if not state_errors and not any(n.get('id')=='conversation' for n in plan_nodes(plan)):
            _scope_types={**(_scope_types or {}),**{('conversation',name):kind for name,kind in state_types.items()}}
    if "schema_version" not in plan and isinstance(plan.get("nodes"), list) and isinstance(plan.get("edges"), list):
        plan["schema_version"] = 1
        fixes.append("补齐固定契约版本 schema_version=1")
    nodes = plan.get("nodes", [])
    if not isinstance(nodes, list):
        return plan, fixes
    identities=[n['id'] for n in nodes if isinstance(n,dict) and isinstance(n.get('id'),str)]
    by_id = {n.get("id"): n for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str) and identities.count(n['id'])==1}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("config"), dict):
            continue
        config = node["config"]
        if not _body and node.get("type") in ("iteration","loop") and isinstance(config.get("nodes"), list):
            from .declared_types import container_scope
            scope=container_scope(node,by_id,_scope_types,_mode)
            scope.update({key:kind for key,kind in (_scope_types or {}).items() if isinstance(key,tuple) and len(key)==2 and key[0]=='conversation'})
            nested, nested_fixes = normalize_draft({"nodes": config["nodes"]}, _body=True,_scope_types=scope,_mode=_mode)
            config["nodes"] = nested["nodes"]
            label='循环内部' if node.get('type')=='loop' else '迭代内部'
            fixes.extend(f"{label}：{fix}" for fix in nested_fixes)
        if node.get("type") == "start" and isinstance(config.get("variables"), list):
            for v in config["variables"]:
                if isinstance(v, dict) and isinstance(v.get("required"), str) and v["required"] in {"true", "false"}:
                    v["required"] = v["required"] == "true"
                    fixes.append("将明确的 required 文本转换为布尔值")
        if node.get("type") == "code" and config.get("code_language") == "python":
            config["code_language"] = "python3"
            fixes.append("将 Python 语言名称规范为 python3")
        if node.get('type')=='code' and config.get('code_language')=='python3' and isinstance(config.get('code'),str):
            fixed=_missing_header_colon(config['code'])
            if fixed is not None:
                config['code']=fixed
                fixes.append('本机补齐 Python 语句头单个冒号，AST 校验通过；代码其他内容保持，未执行代码、未追加模型调用')
        if node.get("type") == "if-else" and isinstance(config.get("cases"), list):
            for case in config["cases"]:
                if not isinstance(case, dict) or not isinstance(case.get("conditions"), list):
                    continue
                for condition in case["conditions"]:
                    if not isinstance(condition, dict) or "varType" in condition:
                        continue
                    selector = condition.get("variable_selector")
                    if not isinstance(selector, list) or len(selector) != 2 or not all(isinstance(s, str) for s in selector):
                        continue
                    source = by_id.get(selector[0], {})
                    source_config = source.get("config", {})
                    if not isinstance(source_config, dict):
                        continue
                    from .declared_types import resolve
                    known=resolve(by_id,selector,_scope_types,_mode)
                    if known:
                        condition['varType']=known
                        fixes.append('依据明确的上游／作用域类型声明补齐条件 varType='+known+'，不改比较值、业务条件或资源')
    return plan, list(dict.fromkeys(fixes))


def _code_tokens(code):
    preserved = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(code).readline):
            if t.type in {tokenize.NAME,tokenize.NUMBER,tokenize.STRING,tokenize.OP,tokenize.COMMENT,tokenize.INDENT,tokenize.DEDENT,tokenize.NEWLINE}:
                value='' if t.type in {tokenize.INDENT,tokenize.DEDENT} else '\n' if t.type==tokenize.NEWLINE else t.string
                preserved.append((t.type,value,t.start[0]))
    except (tokenize.TokenError, IndentationError):
        return None
    return preserved


def _syntax_only_code(before,after):
    """ASTs are parsed only. Invalid input permits one missing header colon."""
    if before==after:return True
    try:new_tree=ast.parse(after)
    except (SyntaxError,ValueError,UnicodeError,RecursionError):return False
    try:old_tree=ast.parse(before)
    except SyntaxError as exc:
        if exc.msg!="expected ':'":return False
        old,new=_code_tokens(before),_code_tokens(after)
        if old is None or new is None or len(new)!=len(old)+1:return False
        a=[row[:2] for row in old];b=[row[:2] for row in new]
        i=next((j for j in range(len(a)) if a[j]!=b[j]),len(a))
        return b[i]==(tokenize.OP,':') and new[i][2]==exc.lineno and a==b[:i]+b[i+1:]
    except (ValueError,UnicodeError,RecursionError):return False
    old,new=_code_tokens(before),_code_tokens(after)
    if old is None or new is None:return False
    comments=lambda rows:[row[1] for row in rows if row[0]==tokenize.COMMENT]
    return ast.dump(old_tree,include_attributes=False)==ast.dump(new_tree,include_attributes=False) and comments(old)==comments(new)


def _missing_header_colon(code):
    try:ast.parse(code)
    except SyntaxError as exc:
        if exc.msg!="expected ':'" or not exc.lineno:return None
        try:
            tokens=list(tokenize.generate_tokens(io.StringIO(code).readline))
            ends=[t.start[1] for t in tokens if t.start[0]==exc.lineno and t.type in {tokenize.COMMENT,tokenize.NEWLINE}]
            lines=code.splitlines(keepends=True)
            if not ends or exc.lineno>len(lines):return None
            col=min(ends);line=lines[exc.lineno-1]
            lines[exc.lineno-1]=line[:col]+':'+line[col:]
            candidate=''.join(lines)
            return candidate if _syntax_only_code(code,candidate) else None
        except (tokenize.TokenError,IndentationError,UnicodeError,ValueError,RecursionError):return None
    except (ValueError,UnicodeError,RecursionError):return None
    return None


def _repairable_python_headers(plan):
    from .iteration import plan_nodes
    found=False
    for node in plan_nodes(plan):
        if node.get('type')!='code':continue
        cfg=node.get('config',{})
        if not isinstance(cfg,dict) or cfg.get('code_language')!='python3':continue
        try:ast.parse(cfg.get('code',''))
        except SyntaxError as exc:
            if exc.msg!="expected ':'" or _missing_header_colon(cfg.get('code','')) is None:return False
            found=True
        except (TypeError,ValueError,UnicodeError,RecursionError):return False
    return found


def preserves_scope(original, repaired):
    """Code syntax retries cannot change topology, resources or data bindings."""
    if {k:v for k,v in original.items() if k!='nodes'} != {k:v for k,v in repaired.items() if k!='nodes'}:
        return False
    old = original.get("nodes")
    new = repaired.get("nodes")
    if not isinstance(old, list) or not isinstance(new, list) or len(old) != len(new):
        return False
    if any(not isinstance(n, dict) or not isinstance(n.get("id"), str) for n in old + new):
        return False
    if [n['id'] for n in old]!=[n['id'] for n in new]:return False
    old_map = {n["id"]: n for n in old}
    new_map = {n["id"]: n for n in new}
    if set(old_map) != set(new_map) or len(old_map) != len(old):
        return False
    for nid, node in old_map.items():
        other = new_map[nid]
        if {k:v for k,v in node.items() if k!='config'}!={k:v for k,v in other.items() if k!='config'}:
            return False
        cfg, nxt = node.get("config", {}), other.get("config", {})
        if not isinstance(cfg, dict) or not isinstance(nxt, dict):
            return False
        if node.get("type") in ("iteration","loop"):
            if {k: v for k, v in cfg.items() if k != "nodes"} != {k: v for k, v in nxt.items() if k != "nodes"}:
                return False
            if not preserves_scope({"nodes": cfg.get("nodes"), "edges": []}, {"nodes": nxt.get("nodes"), "edges": []}):
                return False
        elif node.get("type") != "code":
            if cfg != nxt:
                return False
        else:
            if {k: v for k, v in cfg.items() if k != "code"} != {k: v for k, v in nxt.items() if k != "code"}:
                return False
            if cfg.get('code')==nxt.get('code'):continue
            if cfg.get("code_language") != "python3" or not isinstance(cfg.get("code"), str) or not isinstance(nxt.get("code"), str):
                return False
            if not _syntax_only_code(cfg['code'],nxt['code']):
                return False
    return True


class PlanningStopped(Exception):
    def __init__(self, reason, message):
        self.reason, self.message = reason, message
        super().__init__(message)


async def draft_plan(task, provider, messages, settings, operation, invoke, validate, checkpoint, guard, *, clock=time.monotonic):
    started = clock()
    elapsed_limit = settings["max_minutes"] * 60
    budget = Decimal(str(settings["max_cost_usd"]))
    pricing = validate_pricing(provider.get("pricing"))
    spent = Decimal(0)
    previous_error = None
    original = None
    repair_rounds = 0

    def stop(reason, message):
        operation.update(status="paused", stop_reason=reason, message=message, estimated_cost_usd=float(spent), elapsed_seconds=round(clock() - started, 3))
        checkpoint()
        raise PlanningStopped(reason, message)

    if pricing is None:
        stop("pricing_unknown", "缺少模型输入／输出估算单价，无法做费用预检。请补齐单价，或手动编辑计划。")
    for index in range(settings["max_retries"] + 1):
        try:
            guard()
        except PlanningStopped as e:
            stop(e.reason, e.message)
        remaining = elapsed_limit - (clock() - started)
        if remaining <= 0:
            stop("time_limit", "本轮规划已达到时间上限，保留当前进度。")
        reservation = reserve_cost(messages, pricing)
        if spent + reservation > budget:
            stop("cost_limit", "下一次调用的费用预估会超过本轮上限，已暂停，未派发该调用。")
        attempt = {"number": index + 1, "status": "pending", "reserved_cost_usd": float(reservation), "usage": None}
        operation["attempts"].append(attempt)
        checkpoint()
        remaining = elapsed_limit - (clock() - started)
        if remaining <= 0:
            attempt["status"] = "not_dispatched"
            stop("time_limit", "调用准备期间达到时间上限，本次请求未派发。")
        text = None
        try:
            text, usage = await asyncio.wait_for(invoke(messages, min(remaining, 120)), timeout=remaining)
            attempt["usage"] = usage
            cost = usage_cost(usage, pricing)
            attempt.update(estimated_cost_usd=float(cost if cost is not None else reservation), cost_basis="reported_usage" if cost is not None else "reserved_unknown_usage")
            spent += cost if cost is not None else reservation
            attempt["status"] = "returned"
        except PlanningStopped as e:
            attempt.update(status="not_dispatched", usage=None, estimated_cost_usd=0, cost_basis="not_dispatched")
            stop(e.reason, str(e))
        except (ProviderError, asyncio.TimeoutError) as e:
            usage = e.usage if isinstance(e, ProviderError) else None
            cost = usage_cost(usage, pricing)
            spent += cost if cost is not None else reservation
            attempt.update(status="provider_failed" if cost is not None else "unknown_usage", usage=usage, estimated_cost_usd=float(cost if cost is not None else reservation), cost_basis="reported_usage" if cost is not None else "reserved_unknown_usage")
            if isinstance(e, ProviderError) and e.finish_reason:
                attempt['finish_reason'] = e.finish_reason
            stop("provider_error" if isinstance(e, ProviderError) else "time_limit", str(e) if isinstance(e, ProviderError) else "模型请求超过本轮时间上限，费用用量可能未知；请核对后再继续。")
        operation.update(estimated_cost_usd=float(spent), elapsed_seconds=round(clock() - started, 3))
        operation["last_response_excerpt"] = text[:16000]
        operation["response_truncated"] = len(text) > 16000
        checkpoint()
        try:
            guard()
        except PlanningStopped as e:
            stop(e.reason, e.message)
        if clock() - started >= elapsed_limit:
            stop("time_limit", "模型已返回，但本轮时间上限已达到；本次候选未应用。")
        if spent > budget:
            stop("cost_limit", "已返回用量对应的费用估算达到上限，本次候选未应用。单价与估算不是供应商账单保证。")
        try:
            candidate = extract_json(text)
        except (ValueError, TypeError):
            candidate = None
            errors = ["返回内容不是可解析的 JSON 计划"]
            repairable = True
        else:
            if "error" in candidate:
                from .planning_decisions import summarize
                attempt["status"] = "needs_decision"
                operation['decision_report'] = summarize(candidate)
                operation["diagnostics"] = [operation['decision_report']['message']]
                stop("needs_decision", "模型说明缺少条件或无法完成，需要确认资源或范围；没有自动删减功能。")
            if repair_rounds < settings["max_retries"]:
                candidate, changes = normalize_draft(candidate,_mode=task.get('app_type'))
                if changes:
                    repair_rounds += 1
                    attempt["deterministic_fixes"] = changes
            if original is not None and not preserves_scope(original, candidate):
                operation["last_candidate"] = candidate
                from .planning_scope_summary import summarize
                operation['scope_change_summary']=summarize(original,candidate)
                stop("scope_change", "修复候选改变了节点、资源、输入输出或代码关键内容，需要人工确认；原方案保留。")
            try:
                result = await asyncio.wait_for(asyncio.to_thread(validate, candidate), timeout=max(.001, elapsed_limit - (clock() - started)))
                guard()
            except asyncio.TimeoutError:
                stop("time_limit", "静态校验期间达到时间上限；本次候选未应用。")
            except (ValueError, TypeError, KeyError):
                stop("validation_error", "候选结构超出校验器可处理范围，需要人工检查；未应用本次候选。")
            if clock() - started >= elapsed_limit:
                stop("time_limit", "静态校验后达到时间上限；本次候选未应用。")
            errors = result["errors"]
            operation["last_candidate"] = candidate
            if result["valid"]:
                attempt["status"] = "valid"
                operation.update(status="ready_to_confirm", diagnostics=[], elapsed_seconds=round(clock() - started, 3))
                checkpoint()
                return candidate
            original = candidate
            repairable = bool(errors) and all("Python" in e and "语法" in e for e in errors) and _repairable_python_headers(candidate)
        attempt.update(status="invalid", diagnostics=errors)
        operation["diagnostics"] = errors
        signature = hashlib.sha256(json.dumps(sorted(errors), ensure_ascii=False).encode()).hexdigest()
        checkpoint()
        if previous_error == signature:
            stop("no_progress", "连续两次出现同一问题且未通过校验，停止继续修复并保留候选。")
        previous_error = signature
        if not repairable:
            stop("needs_decision", "此问题涉及图结构、资源、业务配置或不支持的语法修复，需要人工确认；明确的单个语句头冒号由本机修复，其余保留候选，不自动修改已确认方案或追加模型修复请求。")
        if attempt["cost_basis"] == "reserved_unknown_usage":
            stop("usage_unknown", "供应商没有返回可用的费用用量，本次按预留估算记录；请核对后再继续，不自动追加调用。")
        if repair_rounds >= settings["max_retries"] or index >= settings["max_retries"]:
            stop("retry_limit", "本轮自动修复次数已达到上限，保留当前候选与诊断。")
        repair_rounds += 1
        messages = messages + [{"role": "assistant", "content": text[:16000]},
            {"role": "user", "content": "只修复 JSON 格式，或给已指出缺少冒号的 Python 语句头补一个冒号，返回完整 JSON。保留节点顺序、属性、连接、资源、输入输出、代码注释、调用／索引及缩进语义；不得改变其他代码内容。不更换方案，不删除功能。诊断：" + json.dumps(errors, ensure_ascii=False)}]
    stop("retry_limit", "本轮自动修复次数已达到上限。")
