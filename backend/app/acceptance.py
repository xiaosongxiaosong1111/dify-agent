"""Summarize declared checks without claiming complete business verification."""

from __future__ import annotations

import json


def same_json(left, right) -> bool:
    """Compare JSON values without Python's True == 1 coercion."""
    return json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(right, sort_keys=True, ensure_ascii=False, allow_nan=False)


def matches_case(case: dict, run: dict) -> bool:
    saved = run.get("test_case") or {}
    return (
        saved.get("id") == case.get("id")
        and same_json(saved.get("input"), case.get("input"))
        and same_json(saved.get("expectation"), case.get("expectation"))
        and same_json(saved.get('followups'), case.get('followups'))
        and same_json(run.get("input"), case.get("input"))
    )


def summarize_acceptance(task: dict, file_rows=None) -> dict:
    rows = []
    for case in task.get("test_cases", []):
        run = next((r for r in reversed(task.get("runs", []))
                    if r.get("kind") == "run" and r.get("revision") == task["revision"]
                    and r.get("environment_id") == task.get("environment_id")
                    and (r.get("test_case") or {}).get("id") == case["id"]), None)
        status, method, detail = "not_run", "none", "当前修订尚未试跑此样例。"
        if run:
            if not matches_case(case, run):
                status, detail = "needs_review", "记录的输入或预期与当前样例不一致，不能计为通过。"
            elif run['status'] in {'waiting_platform','platform_finished'}:
                status,method,detail='needs_review','platform_state_only','平台运行暂停，需到Dify处理再主动只读核对；尚未评估业务结果。' if run['status']=='waiting_platform' else '平台已观察到终态，但未验证原方案及业务结果，不计通过。'
            elif run["status"] in {"pending", "unknown", "failed"}:
                status = {"pending": "running", "unknown": "unknown", "failed": "failed"}[run["status"]]
                detail = run.get("error") or "运行尚未确认完成。"
            elif run["status"] == "success":
                evaluation = run.get("evaluation") or {}
                if case.get('followups'):
                    from .conversation_cases import evaluate_conversation
                    evaluation = evaluate_conversation(case, run.get('result'))
                from .evaluation import EQUALITY_VERSION
                if not case.get('followups') and case['expectation']['mode']=='equals' and type(case['expectation'].get('expected')) in (dict,list) and (type(evaluation.get('comparison_version')) is not int or evaluation['comparison_version']!=EQUALITY_VERSION):
                    evaluation={'status':'needs_review','mode':'equals','details':'旧记录使用早期对象／数组等值规则，未完整核对嵌套类型；本次不沿用历史通过结论。请查看原输出并明确安排新核对；原记录保留，没有自动重跑或修改结果。'}
                status = evaluation.get("status", "needs_review")
                if status not in {"passed", "failed", "needs_review"}:
                    status = "needs_review"
                method = "rule"
                detail = evaluation.get("details") or "未记录输出规则检查。"
                review = run.get("manual_review") or {}
                if (case.get('followups') or case['expectation']['mode'] == 'manual') and evaluation.get('mode') == 'manual' and review.get("source") == "user" and review.get("decision") in {"passed", "failed"}:
                    status, method, detail = review["decision"], "human", review["reason"]
        rows.append({"id": case["id"], "name": case["name"], "required": case.get("required", True),
                     "status": status, "method": method, "details": detail, "run_id": run["id"] if run else None})
    used_ids={row['id'] for row in rows}
    for file_row in file_rows or []:
        row=dict(file_row)
        while row['id'] in used_ids:
            row['id']='file:'+row['id']
        used_ids.add(row['id']);rows.append(row)
    required = [row for row in rows if row["required"]]
    counts = {status: sum(row["status"] == status for row in required)
              for status in ("passed", "failed", "needs_review", "not_run", "unknown", "running")}
    blockers = []
    if not required:
        blockers.append("尚未定义必选验收样例。")
    if not task.get("requirements_confirmed") or not task.get("configuration_confirmed"):
        blockers.append("当前需求或配置尚未确认。")
    if task.get("configuration", {}).get("mock_dependencies"):
        blockers.append("包含模拟依赖，结果只能作为阶段性成果。")
    blockers.append("此汇总只检查已声明样例；完整业务覆盖仍需人工确认。")
    return {"revision": task["revision"], "cases": rows, "required": {"total": len(required), **counts},
            "all_required_passed": bool(required) and counts["passed"] == len(required),
            "verification": "declared_checks_only", "blockers": blockers}
