"""Revision-bound declared requirement coverage; no claim of business correctness."""
from __future__ import annotations
from .contract_loading import load_contract

import copy
import hashlib
import json
import re
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

STATUS = {"planned", "unresolved", "excluded"}
SOURCE_FIELDS = {"goal", "audience", "input", "output", "rules", "knowledge", "exceptions", "tests"}


class CoverageRevision(BaseModel):
    revision: int


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def context(task):
    return {key: task.get(key) for key in ("app_type", "requirements", "configuration", "environment_id", "workflow_plan", "agent_plan", "plan_stale", "test_cases", "materials", "dsl_reference", "dsl_overlay")}


def evidence(task):
    result = {"scope:app_type": "所选应用类型"}
    if task.get("dsl_reference"):
        root, _ = final_root(task)
        if root:
            for node in root.get("workflow", {}).get("graph", {}).get("nodes", []):
                result["node:" + node["id"]] = "最终 DSL：" + (node["data"].get("title") or node["data"]["type"])
        return result
    for key in task.get("configuration", {}):
        if key != "assistant_provider_id":
            result["config:" + key] = "配置：" + key
    plan = task.get("workflow_plan")
    if plan:
        from .iteration import plan_nodes
        for node in plan_nodes(plan):
            result["node:" + node["id"]] = node.get("title") or node["type"]
    elif task.get("agent_plan"):
        result["agent:system_prompt"] = "原生 Agent 指令"
        if task["agent_plan"].get("scope") == "knowledge":
            result["agent:knowledge_sets"] = "原生 Agent 知识集"
    return result


def final_root(task):
    if not task.get("dsl_reference"):
        return None, None
    overlay = task.get("dsl_overlay")
    if not isinstance(overlay, dict) or not overlay or overlay.get("revision") != task["revision"]:
        return None, "有实际 DSL 引用时须先按当前修订确认保留文件，再检查覆盖；不能只核对生成建议。"
    try:
        from .main import preserved_file_text
        from .dsl_roundtrip import parse, digest as dsl_digest
        root = parse(preserved_file_text(task), task["app_type"])
        if dsl_digest(root) != overlay["digest"]:
            return None, "实际保留文件已变化，请重新分析保留与覆盖。"
        return root, None
    except (HTTPException, ValueError, OSError, KeyError):
        return None, "无法读取当前确认的最终 DSL，覆盖检查不能沿用生成建议。"


def validate_items(task, candidate, *, model=False):
    errors = []
    if not isinstance(candidate, dict) or set(candidate) != {"schema_version", "items"} or type(candidate.get("schema_version")) is not int or candidate["schema_version"] != 1:
        return {"valid": False, "errors": ["覆盖清单须为 schema_version=1 和 items 两个字段。"]}
    items = candidate["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 60:
        return {"valid": False, "errors": ["覆盖清单须有 1—60 项；不能清空后绕过确认。"]}
    refs, cases, seen = evidence(task), {c["id"] for c in task.get("test_cases", [])}, set()
    materials = {m["id"]: m for m in task.get("materials", [])}
    fields = {"id", "requirement", "source", "status", "evidence_ids", "case_ids", "explanation", "impact", "cost", "manual_work"}
    for i, item in enumerate(items, 1):
        prefix = f"覆盖项 {i}"
        if not isinstance(item, dict) or set(item) != fields:
            errors.append(prefix + " 字段不完整或包含未知字段。")
            continue
        nid = item["id"]
        if not isinstance(nid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", nid) or nid in seen:
            errors.append(prefix + " ID 须非空、唯一且仅含字母、数字、下划线或连字符。")
        else:
            seen.add(nid)
        for field in ("requirement", "explanation", "impact", "cost", "manual_work"):
            value = item[field]
            if not isinstance(value, str) or len(value) > 3000 or (field in {"requirement", "explanation"} and not value.strip()):
                errors.append(prefix + f" 的 {field} 须为最多 3000 字的文本，需求与说明不能空白。")
        state = item["status"]
        if not isinstance(state, str) or state not in STATUS:
            errors.append(prefix + " 状态只支持 planned／unresolved／excluded。")
        if state == "excluded":
            if model:
                errors.append(prefix + " 模型不能替用户排除需求；请改为 unresolved，由用户裁定。")
            for field in ("impact", "cost", "manual_work"):
                if not isinstance(item[field], str) or not item[field].strip():
                    errors.append(prefix + " 暂不纳入范围时，必须说明体验、费用和人工影响；无影响可明确填写无。")
        for field, known in (("evidence_ids", refs), ("case_ids", cases)):
            values = item[field]
            if not isinstance(values, list) or len(values) > 30 or any(not isinstance(v, str) or v not in known for v in values) or len(set(values)) != len(values):
                errors.append(prefix + f" 的 {field} 须为当前任务中存在且不重复的引用。")
        if state == "planned" and not item["evidence_ids"]:
            errors.append(prefix + " 标为已安排时须关联实际计划节点／配置；关联不是运行证明。")
        source = item["source"]
        if not isinstance(source, dict) or set(source) != {"kind", "id", "quote"}:
            errors.append(prefix + " 来源须包含 kind、id、quote。")
            continue
        kind, sid, quote = source["kind"], source["id"], source["quote"]
        original = None
        if kind == "requirement" and isinstance(sid, str) and sid in SOURCE_FIELDS:
            original = task.get("requirements", {}).get(sid)
        elif kind == "material" and isinstance(sid, str) and sid in materials and materials[sid].get("status") == "parsed":
            original = materials[sid].get("text")
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 3000 or not isinstance(original, str) or quote not in original:
            errors.append(prefix + " 来源引文必须是当前需求字段或已解析材料中的原文，不能编造来源。")
    prior = task.get("coverage_review") or {}
    old_ids = {item["id"] for item in prior.get("items", [])}
    if old_ids - seen:
        errors.append("已有覆盖项不能静默删除；保留该项并明确标为暂不纳入范围，说明影响后重新确认。")
    if model:
        referenced = {i["source"].get("id") for i in items if isinstance(i, dict) and isinstance(i.get("source"), dict) and i["source"].get("kind") == "requirement" and isinstance(i["source"].get("id"), str)}
        if SOURCE_FIELDS - referenced:
            errors.append("模型清单遗漏了需求类别：" + "、".join(sorted(SOURCE_FIELDS - referenced)) + "；不能按部分清单宣称完整检查。")
    return {"valid": not errors, "errors": list(dict.fromkeys(errors))}


def summary(task):
    review = task.get("coverage_review")
    enabled = bool(task.get("coverage_enabled") or review)
    token = digest({"revision": task["revision"], "context": context(task), "items": (review or {}).get("items")})
    stale = bool(review and (review.get("revision") != task["revision"] or review.get("context_digest") != digest(context(task))))
    errors = validate_items(task, {"schema_version": 1, "items": review["items"]})["errors"] if review else []
    blockers = []
    if enabled and not review:
        blockers.append("已启用覆盖检查，请重新建立并确认清单。")
    if stale:
        blockers.append("需求、材料、配置、环境、样例或最终 DSL 已变化，覆盖清单须重新复核并保存。")
    if task.get("plan_stale") and enabled:
        blockers.append("流程计划已过期，不能据此确认覆盖。")
    _, final_error = final_root(task)
    if enabled and final_error:
        blockers.append(final_error)
    unresolved = [i["requirement"] for i in (review or {}).get("items", []) if i["status"] == "unresolved"]
    if unresolved:
        blockers.append(f"仍有 {len(unresolved)} 项未解决，须补齐方案或明确协商本次范围。")
    blockers.extend(errors)
    referenced = {i["source"].get("id") for i in (review or {}).get("items", []) if i["source"].get("kind") == "requirement"}
    if enabled and SOURCE_FIELDS - referenced:
        blockers.append("清单尚未关联全部八类需求来源：" + "、".join(sorted(SOURCE_FIELDS - referenced)))
    confirmed = bool(enabled and review and not blockers and review.get("confirmation", {}).get("token") == token)
    if enabled and not confirmed and not blockers:
        blockers.append("覆盖清单尚未按当前修订明确确认。")
    return {"enabled": enabled, "review": review, "stale": stale, "confirmed": confirmed, "revision": task["revision"], "review_token": token, "blockers": blockers, "available_evidence": evidence(task), "case_ids": [c["id"] for c in task.get("test_cases", [])], "verification": "declared_plan_mapping_only", "warning": "关联与确认只证明用户已复核方案安排，不证明完整需求或实际运行正确。未建立清单的旧流程仍使用原准入规则。"}


def require_ready(task):
    state = summary(task)
    if state["enabled"] and not state["confirmed"]:
        raise HTTPException(422, "需求覆盖检查未通过：" + "；".join(state["blockers"]))


class CoverageManager:
    def __init__(self, host):
        self.h = host

    def save(self, task, items, source):
        h = self.h
        checked = validate_items(task, {"schema_version": 1, "items": items}, model=source == "model")
        if not checked["valid"]:
            raise HTTPException(422, "覆盖清单检查失败：" + "；".join(checked["errors"]))
        _, final_error = final_root(task)
        carry_overlay = bool(task.get("dsl_reference") and task.get("dsl_overlay") and not final_error)
        old_revision = task["revision"]
        h.invalidate(task, "需求覆盖清单更新前保存", preserve_requirements=True)
        if carry_overlay:
            task["dsl_overlay"] = {**task["dsl_overlay"], "revision": task["revision"], "carried_from_revision": old_revision}
        task["coverage_enabled"] = True
        task["coverage_review"] = {"items": copy.deepcopy(items), "source": source, "revision": task["revision"], "context_digest": digest(context(task)), "created_at": h.now(), "confirmation": {}}
        return h.save_task(task)

    def register(self):
        h = self.h

        @h.app.get("/api/tasks/{item_id}/coverage")
        def get_coverage(item_id: str):
            return summary(h.get_task(item_id))

        @h.app.post("/api/tasks/{item_id}/coverage")
        def save_coverage(item_id: str, payload: dict):
            if set(payload) != {"revision", "items"} or type(payload.get("revision")) is not int:
                raise HTTPException(422, "请提交 revision 与 items。")
            with h.store.lock:
                task = h.get_task(item_id); h.require_idle(task); h.require_revision(task, payload["revision"])
                return self.save(task, payload["items"], "manual")

        @h.app.post("/api/tasks/{item_id}/coverage/confirm")
        def confirm_coverage(item_id: str, payload: dict):
            if set(payload) != {"revision", "review_token", "acknowledge_review", "acknowledge_exclusions"} or type(payload.get("revision")) is not int or not isinstance(payload.get("review_token"), str) or payload.get("acknowledge_review") is not True or type(payload.get("acknowledge_exclusions")) is not bool:
                raise HTTPException(422, "请明确勾选已逐项复核，并提交当前清单凭据。")
            with h.store.lock:
                task = h.get_task(item_id); h.require_idle(task); h.require_revision(task, payload["revision"])
                state = summary(task)
                if not state["review"] or state["stale"] or task.get("plan_stale") or final_root(task)[1] or state["review_token"] != payload["review_token"]:
                    raise HTTPException(409, "清单或方案已变化，请重新复核并保存。")
                errors = validate_items(task, {"schema_version": 1, "items": state["review"]["items"]})["errors"]
                if errors or any(i["status"] == "unresolved" for i in state["review"]["items"]) or any("尚未关联全部" in b for b in state["blockers"]):
                    raise HTTPException(422, "清单仍有未解决项或无效引用，不能确认。")
                excluded = [i["id"] for i in state["review"]["items"] if i["status"] == "excluded"]
                if excluded and payload["acknowledge_exclusions"] is not True:
                    raise HTTPException(422, "存在暂不纳入范围的需求，须明确接受列出的影响与范围变化。")
                task["coverage_review"]["confirmation"] = {"token": state["review_token"], "revision": task["revision"], "created_at": h.now(), "excluded_ids": excluded}
                task.setdefault("confirmations", []).append({"kind": "coverage", **task["coverage_review"]["confirmation"]})
                return h.save_task(task)

        @h.app.post("/api/tasks/{item_id}/coverage/generate")
        async def generate_coverage(item_id: str, payload: CoverageRevision):
            from .planning import draft_plan, PlanningStopped
            with h.store.lock:
                task = h.get_task(item_id); h.require_idle(task); h.require_revision(task, payload.revision)
                if any(not text.strip() for text in task["requirements"].values()):
                    raise HTTPException(422, "请先填写八类需求，再请求模型拆分覆盖清单。")
                _, final_error = final_root(task)
                if final_error:
                    raise HTTPException(422, final_error)
                provider = h.main_provider(task); key = h.store.secret(provider["id"], "api_key")
                settings = copy.deepcopy(h.get_settings())
                operation = {"id": str(uuid.uuid4()), "kind": "coverage", "revision": task["revision"], "provider_id": provider["id"], "model": provider["model"], "status": "running", "previous_status": task["status"], "attempts": [], "created_at": h.now(), "settings": settings, "pricing": copy.deepcopy(provider.get("pricing")), "estimated_cost_usd": 0, "cost_is_estimate": True}
                task["planning_runs"].append(operation); task["status"] = "planning"; h.save_task(task)
            sources = [{"kind": "requirement", "id": k, "text": v} for k, v in task["requirements"].items()]
            remaining = 18000
            for material in task["materials"]:
                if material.get("status") != "parsed":
                    continue
                text = material.get("text", "")[:min(6000, remaining)]; remaining -= len(text)
                if text:
                    sources.append({"kind": "material", "id": material["id"], "text": text, "excerpt_only": len(text) < len(material.get("text", ""))})
            prompt = load_contract(h.PROJECT_ROOT,"coverage-contract.md")
            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps({"app_type": task["app_type"], "sources": sources, "configuration": task["configuration"], "workflow_plan": task.get("workflow_plan"), "agent_plan": task.get("agent_plan"), "final_dsl_note": "当前是生成建议；若有保留 DSL，须用户人工核对最终文件，模型不判定为已实现。" if task.get("dsl_reference") else None, "available_evidence": evidence(task), "test_cases": task["test_cases"], "previous_items": (task.get("coverage_review") or {}).get("items", [])}, ensure_ascii=False)}]

            def checkpoint():
                with h.store.lock:
                    current = h.get_task(item_id); current["planning_runs"] = [copy.deepcopy(operation) if r["id"] == operation["id"] else r for r in current["planning_runs"]]; h.save_task(current)

            def guard():
                current = h.get_task(item_id)
                if current["revision"] != payload.revision:
                    raise PlanningStopped("revision_changed", "需求已变化，停止旧清单检查。")
                if current["status"] == "paused":
                    raise PlanningStopped("user_pause", "覆盖检查已暂停，保留候选和可用用量。")
                h.budgets.ready(item_id)

            async def invoke(call_messages, timeout):
                return await h.budgets.call(item_id,payload.revision,'coverage',provider,key,call_messages,operation_id=operation['id'],max_tokens=6000,timeout=timeout,json_mode=provider.get('protocol')!='anthropic')

            try:
                candidate = await draft_plan(task, provider, messages, settings, operation, invoke, lambda p: validate_items(task, p, model=True), checkpoint, guard)
                with h.store.lock:
                    guard(); current = h.get_task(item_id)
                    if current["status"] != "planning":
                        raise PlanningStopped("state_changed", "执行状态变化，候选未应用。")
                    current["status"] = operation["previous_status"]
                    saved = self.save(current, candidate["items"], "model")
                    operation.update(status="succeeded", result_revision=saved["revision"], completed_at=h.now())
                    saved["planning_runs"] = [copy.deepcopy(operation) if r["id"] == operation["id"] else r for r in saved["planning_runs"]]
                    return h.save_task(saved)
            except BaseException as exc:
                operation.update(status="paused" if isinstance(exc, PlanningStopped) else "interrupted", stop_reason=exc.reason if isinstance(exc, PlanningStopped) else "operation_error", message=str(exc) if isinstance(exc, PlanningStopped) else "覆盖检查中断，已保存候选；派发用量可能未知，请核对后继续。", completed_at=h.now())
                for attempt in operation["attempts"]:
                    if attempt["status"] == "pending":
                        attempt.update(status="unknown_usage", estimated_cost_usd=attempt.get("reserved_cost_usd", 0), cost_basis="reserved_unknown_usage")
                operation["estimated_cost_usd"] = sum(a.get("estimated_cost_usd", 0) for a in operation["attempts"])
                with h.store.lock:
                    current = h.get_task(item_id)
                    if current["revision"] == payload.revision:
                        current["status"] = "paused"
                    current["planning_runs"] = [copy.deepcopy(operation) if r["id"] == operation["id"] else r for r in current["planning_runs"]]; h.save_task(current)
                if isinstance(exc, PlanningStopped):
                    raise HTTPException(422, str(exc)) from exc
                raise
