import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.storage import Store
from app.dify import DifyError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", Store(tmp_path))
    monkeypatch.setattr(main, "DATA_ROOT", tmp_path)
    with TestClient(main.app) as client:
        yield client


def restore_payload(client, tid, version_id):
    task = client.get(f"/api/tasks/{tid}").json()
    response = client.get(f"/api/tasks/{tid}/versions/{version_id}/restore-preview", params={'revision': task['revision']})
    assert response.status_code == 200, response.text
    return {'revision': task['revision'], 'version_id': version_id, 'review_token': response.json()['review_token'], 'acknowledge_restore': True}


def create(client, app_type="workflow", env_id=None):
    response = client.post("/api/tasks", json={"name": "测试任务", "app_type": app_type, "environment_id": env_id})
    assert response.status_code == 201
    task=response.json()
    # Preserve the pre-0.17 manual intake contract in legacy regression fixtures.
    # New task intake gates are exercised directly through the API in test_intake.py.
    task['intake_required']=False
    task.pop('plan_review_required',None)  # Legacy implicit-template fixtures; new task graph gate has dedicated API coverage.
    main.store.put('task',task['id'],task)
    return task


def approved(client, *, app_type="workflow", env_id=None):
    task = create(client, app_type, env_id)
    tid = task["id"]
    requirements = {k: "明确的测试规则" for k in main.REQ_KEYS}
    task = client.patch(f"/api/tasks/{tid}", json={"requirements": requirements}).json()
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "requirements", "revision": task["revision"]}).status_code == 200
    task = client.patch(f"/api/tasks/{tid}", json={"configuration": {"dify_model_provider": "test/provider", "dify_model": "test-model"}}).json()
    assert task["requirements_confirmed"]  # configuration edits carry approved unchanged business requirements
    response = client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_explicit_type_and_no_internal_patch(client):
    assert client.post("/api/tasks", json={"name": "x", "app_type": ""}).status_code == 422
    task = create(client)
    assert client.patch(f"/api/tasks/{task['id']}", json={"app_type": "advanced-chat"}).status_code == 422
    assert client.patch(f"/api/tasks/{task['id']}", json={"configuration_confirmed": True}).status_code == 422


def test_requirements_gate_and_stale_confirmation(client):
    task = create(client)
    assert client.post(f"/api/tasks/{task['id']}/confirm", json={"kind": "requirements", "revision": 1}).status_code == 422
    assert client.post(f"/api/tasks/{task['id']}/build", json={"revision": 1}).status_code == 422
    changed = client.patch(f"/api/tasks/{task['id']}", json={"requirements": {"goal": "变化"}}).json()
    assert changed["revision"] == 2
    assert client.post(f"/api/tasks/{task['id']}/confirm", json={"kind": "requirements", "revision": 1}).status_code == 409


def test_build_is_static_and_change_invalidates(client):
    task = approved(client)
    response = client.post(f"/api/tasks/{task['id']}/build", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    built = response.json()
    assert built["status"] == "draft_ready"
    assert built["artifact"]["verification"] == "static_only"
    assert not built["dify_app_id"] and not built["runs"]
    dsl = client.get(f"/api/tasks/{task['id']}/artifact")
    assert dsl.status_code == 200 and "0.7.0" in dsl.text
    changed = client.patch(f"/api/tasks/{task['id']}", json={"requirements": {"rules": "新的规则"}}).json()
    assert not changed["requirements_confirmed"] and not changed["configuration_confirmed"]
    assert not changed["artifact"]
    assert client.get(f"/api/tasks/{task['id']}/artifact").status_code == 404


def test_config_change_preserves_requirements_only(client):
    task = approved(client)
    changed = client.patch(f"/api/tasks/{task['id']}", json={"configuration": {"temperature": 0.5}}).json()
    assert changed["requirements_confirmed"] and not changed["configuration_confirmed"]
    assert changed["confirmations"][-1]["revision"] == changed["revision"]
    assert "carried_from_revision" in changed["confirmations"][-1]


def test_agent_is_not_substituted(client):
    task = create(client, app_type="agent")
    task = client.patch(f"/api/tasks/{task['id']}", json={"requirements": {k: "明确测试规则" for k in main.REQ_KEYS}, "configuration": {"resource_plan": "本机文本技术方案", "dify_model_provider": "langgenius/deepseek/deepseek", "dify_model": "deepseek-flash"}}).json()
    assert client.post(f"/api/tasks/{task['id']}/confirm", json={"revision": task['revision'], "kind": "requirements"}).status_code == 200
    response = client.post(f"/api/tasks/{task['id']}/confirm", json={"revision": task['revision'], "kind": "configuration"})
    assert response.status_code == 422 and "Agent" in response.text  # explicit Agent plan required
    assert client.get(f"/api/tasks/{task['id']}").json()["app_type"] == "agent"


def test_credentials_encrypted_not_returned(client):
    secret = "test-secret-that-is-not-a-real-key"
    response = client.post("/api/providers", json={"name": "测试模型", "provider": "custom", "base_url": "https://example.com/v1", "model": "test", "api_key": secret})
    assert response.status_code == 201 and secret not in response.text
    pid = response.json()["id"]
    assert main.store.secret(pid, "api_key") == secret
    assert secret not in client.get("/api/providers").text
    assert secret.encode() not in main.store.path.read_bytes()
    patched = client.patch(f"/api/providers/{pid}", json={"api_key": "", "name": "改名"})
    assert patched.status_code == 200
    assert main.store.secret(pid, "api_key") == secret


def test_no_model_reply_explicit_and_persistent(client):
    task = create(client)
    response = client.post(f"/api/tasks/{task['id']}/messages", json={"content": "请帮我设计"})
    assert response.status_code == 200
    assert response.json()["messages"][-1]["source"] == "system"
    assert "没有调用 AI" in response.json()["messages"][-1]["content"]
    fresh_store = Store(main.store.root)
    assert fresh_store.get("task", task["id"])["messages"][-2]["content"] == "请帮我设计"


def test_real_model_path_with_controlled_transport(client, monkeypatch):
    # Controlled substitute verifies integration; never counted as an external credential test.
    client.post("/api/providers", json={"name": "测试模型", "provider": "custom", "base_url": "https://example.com/v1", "model": "test", "api_key": "test-only", "role": "main", "pricing": {"input_per_million_usd": 1, "output_per_million_usd": 1}})
    async def controlled_call(*args, **kwargs):
        return json.dumps({"message": "请补充输入形式", "requirements_patch": {"goal": "合同整理"}}), {"prompt_tokens": 30, "completion_tokens": 10}
    monkeypatch.setattr(main, "call_model", controlled_call)
    task = create(client)
    result = client.post(f"/api/tasks/{task['id']}/messages", json={"content": "做合同整理"}).json()
    assert result["requirements"]["goal"] == "合同整理"
    assert result["messages"][-1]["source"] == "model"
    assert result["messages"][-1]["usage"]["prompt_tokens"] == 30
    assert not result["requirements_confirmed"]


def test_material_extraction_and_reference_gate(client):
    task = approved(client)
    tid = task["id"]
    result = client.post(f"/api/tasks/{tid}/materials", files={"file": ("rules.txt", "保修一年".encode(), "text/plain")}).json()
    material = result["materials"][0]
    assert material["text"] == "保修一年" and material["status"] == "parsed"
    assert not result["requirements_confirmed"]
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "requirements", "revision": result["revision"]}).status_code == 422
    assert client.patch(f"/api/tasks/{tid}/materials/{material['id']}", json={"reference_mode": "preserve"}).status_code == 422
    result = client.patch(f"/api/tasks/{tid}/materials/{material['id']}", json={"reference_mode": "preserve", "preserve_items": "保修期限"}).json()
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "requirements", "revision": result["revision"]}).status_code == 200


def test_unparsed_material_can_be_removed(client):
    task = approved(client)
    tid = task["id"]
    result = client.post(f"/api/tasks/{tid}/materials", files={"file": ("flow.png", b"not-an-image", "image/png")}).json()
    material = result["materials"][0]
    assert material["status"] == "needs_input" and material["error"]
    result = client.delete(f"/api/tasks/{tid}/materials/{material['id']}").json()
    assert not result["materials"]


def test_strict_reference_is_not_silently_ignored(client):
    task = approved(client)
    tid = task["id"]
    task = client.post(f"/api/tasks/{tid}/materials", files={"file": ("ref.txt", b"important reference", "text/plain")}).json()
    task = client.patch(f"/api/tasks/{tid}/materials/{task['materials'][0]['id']}", json={"reference_mode": "replicate"}).json()
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "requirements", "revision": task["revision"]}).status_code == 200
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]}).status_code == 200
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert response.status_code == 422 and "严格复现" in response.text


def test_restore_creates_unapproved_revision(client):
    task = approved(client)
    tid = task["id"]
    client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    built = client.get(f"/api/tasks/{tid}").json()
    version = built["versions"][-1]
    changed = client.patch(f"/api/tasks/{tid}", json={"requirements": {"goal": "另一个目标"}}).json()
    restored = client.post(f"/api/tasks/{tid}/restore", json=restore_payload(client, tid, version["id"])).json()
    assert restored["revision"] > changed["revision"]
    assert restored["requirements"]["goal"] == version["requirements"]["goal"]
    assert not restored["requirements_confirmed"] and not restored["artifact"]


def create_env(client):
    response = client.post("/api/environments", json={"name": "测试实例", "base_url": "https://dify.example", "version": "1.17.1", "console_token": "test-console"})
    assert response.status_code == 201
    return response.json()


def test_runtime_credentials_do_not_erase_import_binding(client):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    task = main.get_task(tid)
    task["dify_app_id"] = "imported-app"
    main.save_task(task)
    client.patch(f"/api/environments/{env['id']}", json={"service_app_id": "imported-app", "service_api_key": "test-run-key"})
    current = main.get_task(tid)
    assert current["dify_app_id"] == "imported-app" and current["configuration_confirmed"]
    client.patch(f"/api/environments/{env['id']}", json={"base_url": "https://another.example"})
    current = main.get_task(tid)
    assert not current["dify_app_id"] and not current["configuration_confirmed"]


def test_wrong_app_key_binding_blocks_run(client):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    task["dify_app_id"] = "correct-app"
    main.save_task(task)
    response = client.post(f"/api/tasks/{task['id']}/run", json={"revision": task["revision"], "input": {"query": "x"}})
    assert response.status_code == 422 and "应用 ID" in response.text


def test_unknown_import_is_not_retried_blindly(client, monkeypatch):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    assert client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]}).status_code == 200
    async def timed_out(self, content, name):
        raise DifyError("Dify 请求超时。外部写入结果可能未知，请先核对。")
    monkeypatch.setattr(main.DifyClient, "import_new", timed_out)
    payload = {"revision": task["revision"]}
    assert client.post(f"/api/tasks/{tid}/import", json=payload).status_code == 502
    assert main.get_task(tid)["runs"][-1]["status"] == "unknown"
    assert client.post(f"/api/tasks/{tid}/import", json=payload).status_code == 409


def test_import_adapter_success_is_not_full_business_verification(client, monkeypatch):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    async def controlled_import(self, content, name):
        return {"status": "completed", "app_id": "test-app"}
    monkeypatch.setattr(main.DifyClient, "import_new", controlled_import)
    result = client.post(f"/api/tasks/{tid}/import", json={"revision": task["revision"]}).json()
    assert result["dify_app_id"] == "test-app" and result["status"] == "imported"
    assert result["artifact"]["verification"] == "static_only"
    assert result["status"] != "verified"


def code_only_plan():
    return {"schema_version": 1, "nodes": [
        {"id": "start", "type": "start", "config": {"variables": [{"variable": "query", "label": "问题", "type": "text-input", "required": True}]}},
        {"id": "code", "type": "code", "config": {"code_language": "python3", "code": "def main(query: str) -> dict:\n    return {'result': query}\n", "variables": [{"variable": "query", "value_selector": ["start", "query"]}], "outputs": {"result": {"type": "string", "children": None}}}},
        {"id": "end", "type": "end", "config": {"outputs": [{"variable": "result", "value_selector": ["code", "result"]}]}},
    ], "edges": [{"source": "start", "target": "code"}, {"source": "code", "target": "end"}]}


def test_manual_plan_without_key_builds_code_only_dsl(client):
    task = create(client)
    tid = task["id"]
    task = client.patch(f"/api/tasks/{tid}", json={"requirements": {k: "明确的规则" for k in main.REQ_KEYS}}).json()
    client.post(f"/api/tasks/{tid}/confirm", json={"kind": "requirements", "revision": task["revision"]})
    response = client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"], "plan": code_only_plan()})
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["plan_source"] == "manual" and task["requirements_confirmed"]
    assert not task["configuration"]["dify_model"] and not main.store.list("provider")
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]}).status_code == 200
    built = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert built.status_code == 200, built.text
    assert built.json()["artifact"]["verification"] == "static_only"
    assert "code_language: python3" in client.get(f"/api/tasks/{tid}/artifact").text


def test_plan_stale_revision_and_explicit_recheck(client):
    task = approved(client)
    tid = task["id"]
    task = client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"], "plan": code_only_plan()}).json()
    assert client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"] - 1, "plan": code_only_plan()}).status_code == 409
    task = client.patch(f"/api/tasks/{tid}", json={"requirements": {"goal": "新的业务目标"}}).json()
    assert task["plan_stale"] and task["workflow_plan"]
    client.post(f"/api/tasks/{tid}/confirm", json={"kind": "requirements", "revision": task["revision"]})
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]}).status_code == 422
    task = client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"], "plan": code_only_plan()}).json()
    assert not task["plan_stale"] and task["requirements_confirmed"]
    client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]})
    task = client.patch(f"/api/tasks/{tid}", json={"workflow_plan": None}).json()
    assert task["workflow_plan"] is None and not task["configuration_confirmed"]


def test_no_key_planning_does_not_invent_model_result(client):
    task = approved(client)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={"revision": task["revision"]})
    assert response.status_code == 422 and "没有 Key 仍可" in response.text
    assert main.get_task(task["id"])["workflow_plan"] is None


def test_model_plan_saved_with_usage_but_unapproved(client, monkeypatch):
    client.post("/api/providers", json={"name": "受控测试", "provider": "custom", "base_url": "https://example.com/v1", "model": "test", "api_key": "test-only", "role": "main", "pricing": {"input_per_million_usd": 1, "output_per_million_usd": 1}})
    async def controlled_call(*args, **kwargs):
        return json.dumps(code_only_plan()), {"prompt_tokens": 80, "completion_tokens": 30}
    monkeypatch.setattr(main, "call_model", controlled_call)
    task = approved(client)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["plan_source"] == "model" and not result["configuration_confirmed"]
    assert result["messages"][-1]["usage"]["completion_tokens"] == 30
    assert not result["artifact"] and not result["runs"]


def example_case(mode="contains"):
    expectation = {"mode": mode, "target": "result", "expected": "一年"}
    if mode == "manual":
        expectation = {"mode": "manual", "description": "人工确认回答是否符合保修规则"}
    return {"id": "warranty", "name": "保修规则", "input": {"query": "保修多久"}, "expectation": expectation, "required": True}


def test_cases_change_invalidates_approvals_and_restores_snapshot(client):
    task = approved(client)
    tid = task["id"]
    assert client.post(f"/api/tasks/{tid}/test-cases", json={"revision": task["revision"], "cases": [{"name": "无预期"}]}).status_code == 422
    task = client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"], "plan": code_only_plan()}).json()
    task = client.post(f"/api/tasks/{tid}/test-cases", json={"revision": task["revision"], "cases": [example_case()]}).json()
    assert not task["requirements_confirmed"] and not task["configuration_confirmed"]
    assert task["plan_stale"]
    task = client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"], "plan": code_only_plan()}).json()
    for kind in ("requirements", "configuration"):
        assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": kind, "revision": task["revision"]}).status_code == 200
    built = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]}).json()
    version = built["versions"][-1]
    changed = client.post(f"/api/tasks/{tid}/test-cases", json={"revision": task["revision"], "cases": []}).json()
    restored = client.post(f"/api/tasks/{tid}/restore", json=restore_payload(client, tid, version["id"])).json()
    assert restored["revision"] > changed["revision"]
    assert restored["test_cases"] == [example_case()] and restored["workflow_plan"] == code_only_plan()
    assert not restored["artifact"] and not restored["requirements_confirmed"]


@pytest.mark.parametrize("mode,status", [("contains", "passed"), ("manual", "needs_review")])
def test_run_checks_exact_saved_case_without_claiming_full_acceptance(client, monkeypatch, mode, status):
    env = create_env(client)
    client.patch(f"/api/environments/{env['id']}", json={"service_app_id": "case-app", "service_api_key": "test-only"})
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    task = client.post(f"/api/tasks/{tid}/test-cases", json={"revision": task["revision"], "cases": [example_case(mode)]}).json()
    for kind in ("requirements", "configuration"):
        client.post(f"/api/tasks/{tid}/confirm", json={"kind": kind, "revision": task["revision"]})
    client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    task = main.get_task(tid)
    task["dify_app_id"] = "case-app"
    main.save_task(task)
    async def controlled_run(self, inputs):
        assert inputs == example_case(mode)["input"]
        return {"data": {"status": "succeeded", "outputs": {"result": "保修一年"}}}
    monkeypatch.setattr(main.DifyClient, "run_workflow", controlled_run)
    assert client.post(f"/api/tasks/{tid}/run", json={"revision": task["revision"], "case_id": "warranty", "input": {"query": "另一个问题"}}).status_code == 422
    response = client.post(f"/api/tasks/{tid}/run", json={"revision": task["revision"], "case_id": "warranty"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["runs"][-1]["evaluation"]["status"] == status
    assert result["runs"][-1]["test_case"] == example_case(mode)
    assert result["status"] == "run_completed" and result["artifact"]["verification"] == "static_only"


def test_paused_inflight_task_cannot_be_edited(client):
    task = approved(client)
    task["status"] = "paused"
    task["runs"].append({"id": "pending-test", "kind": "run", "revision": task["revision"], "status": "pending"})
    main.save_task(task)
    tid = task["id"]
    assert client.patch(f"/api/tasks/{tid}", json={"requirements": {"goal": "并发修改"}}).status_code == 409
    assert client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"], "plan": code_only_plan()}).status_code == 409


def completed_case_run(client, monkeypatch, mode="manual"):
    env = create_env(client)
    client.patch(f"/api/environments/{env['id']}", json={"service_app_id": "review-app", "service_api_key": "test-only"})
    t = approved(client, env_id=env["id"])
    tid = t["id"]
    t = client.post(f"/api/tasks/{tid}/test-cases", json={"revision": t["revision"], "cases": [example_case(mode)]}).json()
    for kind in ("requirements", "configuration"):
        client.post(f"/api/tasks/{tid}/confirm", json={"kind": kind, "revision": t["revision"]})
    client.post(f"/api/tasks/{tid}/build", json={"revision": t["revision"]})
    t = main.get_task(tid)
    t["dify_app_id"] = "review-app"
    main.save_task(t)
    async def controlled_run(self, inputs):
        return {"data": {"status": "succeeded", "outputs": {"result": "保修一年"}}}
    monkeypatch.setattr(main.DifyClient, "run_workflow", controlled_run)
    response = client.post(f"/api/tasks/{tid}/run", json={"revision": t["revision"], "case_id": "warranty"})
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_review_history_and_summary_are_revision_bound(client, monkeypatch):
    t = completed_case_run(client, monkeypatch)
    tid, rid = t["id"], t["runs"][-1]["id"]
    url = f"/api/tasks/{tid}/runs/{rid}/review"
    assert client.get(f"/api/tasks/{tid}/acceptance").json()["required"]["needs_review"] == 1
    assert client.post(url, json={"revision": t["revision"], "decision": "passed", "reason": "  "}).status_code == 422
    response = client.post(url, json={"revision": t["revision"], "decision": "passed", "reason": "已逐项检查业务规则"})
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["runs"][-1]["evaluation"]["status"] == "needs_review"
    assert reviewed["status"] == "run_completed"
    assert client.get(f"/api/tasks/{tid}/acceptance").json()["all_required_passed"]
    reviewed = client.post(url, json={"revision": t["revision"], "decision": "failed", "reason": "复查发现缺少例外提示"}).json()
    assert len(reviewed["runs"][-1]["review_history"]) == 2
    assert client.get(f"/api/tasks/{tid}/acceptance").json()["required"]["failed"] == 1
    assert "复查发现缺少例外提示" in client.get(f"/api/tasks/{tid}/report").text
    changed = client.patch(f"/api/tasks/{tid}", json={"requirements": {"rules": "增加例外说明"}}).json()
    assert client.post(url, json={"revision": changed["revision"], "decision": "passed", "reason": "旧记录"}).status_code == 409
    assert client.get(f"/api/tasks/{tid}/acceptance").json()["required"]["not_run"] == 1


def test_automatic_checks_cannot_be_manually_overridden(client, monkeypatch):
    t = completed_case_run(client, monkeypatch, mode="contains")
    response = client.post(f"/api/tasks/{t['id']}/runs/{t['runs'][-1]['id']}/review", json={"revision": t["revision"], "decision": "passed", "reason": "想覆盖规则"})
    assert response.status_code == 422 and "自动检查规则" in response.text


def test_identical_cases_do_not_invalidate_confirmations(client):
    t = approved(client)
    response = client.post(f"/api/tasks/{t['id']}/test-cases", json={"revision": t["revision"], "cases": []})
    assert response.status_code == 200
    assert response.json()["revision"] == t["revision"] and response.json()["configuration_confirmed"]


def test_dataset_pages_validate_and_preserve_remote_result(client, monkeypatch):
    env = create_env(client)
    seen = []
    async def controlled_datasets(self, page=1, limit=100):
        seen.append((page, limit))
        return {"data": [{"id": "actual-id", "name": "资料库"}], "has_more": False, "page": page}
    monkeypatch.setattr(main.DifyClient, "datasets", controlled_datasets)
    url = f"/api/environments/{env['id']}/datasets"
    assert client.get(url + "?page=0").status_code == 422
    assert client.get(url + "?limit=101").status_code == 422
    result = client.get(url + "?page=2&limit=20")
    assert result.status_code == 200 and result.json()["data"][0]["id"] == "actual-id"
    assert seen == [(2, 20)]


@pytest.mark.parametrize("body,expected", [('{"ok":true}', 200), ('```json\n{"ok":true}\n```', 502), ('{"ok":1}', 502)])
def test_json_probe_checks_actual_schema_and_records_usage(client, monkeypatch, body, expected):
    p = client.post("/api/providers", json={"name": "受控 JSON 检查", "provider": "custom", "base_url": "https://example.test", "model": "test", "api_key": "test-only"}).json()
    async def controlled_call(*args, **kwargs):
        assert kwargs["json_mode"] and kwargs["max_tokens"] == 128
        return body, {"total_tokens": 9}
    monkeypatch.setattr(main, "call_model", controlled_call)
    response = client.post(f"/api/providers/{p['id']}/test-json")
    assert response.status_code == expected
    saved = main.store.get("provider", p["id"])
    assert saved["capabilities"]["structured_output"] == ("verified" if expected == 200 else "failed")
    if expected == 200:
        assert saved["checks"]["structured_output"]["usage"]["total_tokens"] == 9
    assert "test-only" not in response.text and body not in response.text


def test_invalid_model_plan_keeps_usage_without_overwriting_plan(client, monkeypatch):
    client.post("/api/providers", json={"name": "受控失败规划", "provider": "custom", "base_url": "https://example.test", "model": "test", "api_key": "test-only", "role": "main", "pricing": {"input_per_million_usd": 1, "output_per_million_usd": 1}})
    async def controlled_call(*args, **kwargs):
        return json.dumps({"schema_version": 1, "nodes": [], "edges": []}), {"total_tokens": 77}
    monkeypatch.setattr(main, "call_model", controlled_call)
    task = approved(client)
    tid = task["id"]
    response = client.post(f"/api/tasks/{tid}/plan/generate", json={"revision": task["revision"]})
    assert response.status_code == 422
    saved = main.get_task(tid)
    assert saved["workflow_plan"] is None and saved["revision"] == task["revision"]
    assert saved["messages"][-1]["outcome"] == "failed" and saved["messages"][-1]["usage"]["total_tokens"] == 77


def planning_provider(client, *, pricing=True):
    payload = {"name": "规划测试", "provider": "custom", "base_url": "https://example.test", "model": "test", "api_key": "test-only", "role": "main"}
    if pricing:
        payload["pricing"] = {"input_per_million_usd": 1, "output_per_million_usd": 1}
    return client.post("/api/providers", json=payload).json()


def test_planning_pause_blocks_mutation_and_does_not_apply_late_result(client, monkeypatch):
    from fastapi import HTTPException
    p = planning_provider(client)
    task = approved(client)
    tid = task["id"]
    async def controlled_call(*args, **kwargs):
        assert main.get_task(tid)["status"] == "planning"
        with pytest.raises(HTTPException) as e:
            main.patch_task(tid, {"name": "不能并发改需求"})
        assert e.value.status_code == 409
        with pytest.raises(HTTPException) as e:
            main.patch_provider(p["id"], {"model": "another"})
        assert e.value.status_code == 409
        main.pause(tid)
        return json.dumps(code_only_plan()), {"prompt_tokens": 80, "completion_tokens": 30}
    monkeypatch.setattr(main, "call_model", controlled_call)
    response = client.post(f"/api/tasks/{tid}/plan/generate", json={"revision": task["revision"]})
    assert response.status_code == 422
    saved = main.get_task(tid)
    assert saved["workflow_plan"] is None and saved["revision"] == task["revision"]
    assert saved["status"] == "paused" and saved["planning_runs"][-1]["stop_reason"] == "user_pause"
    assert saved["planning_runs"][-1]["attempts"][0]["usage"]["completion_tokens"] == 30


def test_unknown_price_preserves_confirmed_plan_and_never_calls_model(client, monkeypatch):
    planning_provider(client, pricing=False)
    task = approved(client)
    tid = task["id"]
    task = client.post(f"/api/tasks/{tid}/plan", json={"revision": task["revision"], "plan": code_only_plan()}).json()
    client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]})
    async def forbidden_call(*args, **kwargs):
        pytest.fail("Price check must happen before any model request")
    monkeypatch.setattr(main, "call_model", forbidden_call)
    response = client.post(f"/api/tasks/{tid}/plan/generate", json={"revision": task["revision"]})
    assert response.status_code == 422
    saved = main.get_task(tid)
    assert saved["workflow_plan"] == code_only_plan() and saved["configuration_confirmed"]
    assert not saved["planning_runs"][-1]["attempts"]


def test_failed_json_repair_history_persists_and_success_requires_confirmation(client, monkeypatch):
    planning_provider(client)
    task = approved(client)
    calls = []
    async def controlled_call(*args, **kwargs):
        calls.append(1)
        return ('bad-json' if len(calls) == 1 else json.dumps(code_only_plan())), {"prompt_tokens": 80, "completion_tokens": 30}
    monkeypatch.setattr(main, "call_model", controlled_call)
    response = client.post(f"/api/tasks/{task['id']}/plan/generate", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert len(calls) == 2 and len(saved["planning_runs"][-1]["attempts"]) == 2
    assert not saved["configuration_confirmed"] and not saved["artifact"]
    assert client.get(f"/api/tasks/{task['id']}/planning").json()["runs"][-1]["status"] == "succeeded"


def test_startup_recovers_model_request_without_marking_unknown_usage_zero(client):
    t = approved(client)
    t["status"] = "planning"
    t["planning_runs"] = [{"id": "interrupted", "status": "running", "attempts": [{"number": 1, "status": "pending", "reserved_cost_usd": .01}]}]
    main.save_task(t)
    main.recover_planning()
    saved = main.get_task(t["id"])
    assert saved["status"] == "paused"
    assert saved["planning_runs"][0]["status"] == "interrupted"
    assert saved["planning_runs"][0]["estimated_cost_usd"] == .01
    assert saved["planning_runs"][0]["attempts"][0]["status"] == "unknown_usage"


def test_price_change_keeps_capabilities_but_model_change_invalidates_price(client):
    p = planning_provider(client)
    current = main.store.get("provider", p["id"])
    current["capabilities"]["text"] = "verified"
    main.store.put("provider", p["id"], current)
    changed = client.patch(f"/api/providers/{p['id']}", json={"pricing": {"input_per_million_usd": 2, "output_per_million_usd": 3}}).json()
    assert changed["capabilities"]["text"] == "verified"
    changed = client.patch(f"/api/providers/{p['id']}", json={"model": "new-model"}).json()
    assert changed["pricing"] is None and changed["capabilities"]["text"] == "untested"


def test_settings_allow_no_repair_and_reject_infinite_budget(client):
    assert client.patch("/api/settings", json={"max_retries": 0}).status_code == 200
    response = client.patch("/api/settings", content='{"max_cost_usd": Infinity}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422


@pytest.mark.parametrize("remote_status", ["failed", "stopped", "partial-succeeded", "running", "paused", None])
def test_remote_unsuccessful_workflow_retains_result_without_passing(client, monkeypatch, remote_status):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    task["dify_app_id"] = "diagnostic-app"
    main.save_task(task)
    client.patch(f"/api/environments/{env['id']}", json={"service_app_id": "diagnostic-app", "service_api_key": "unit-key"})
    client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    result = {"workflow_run_id": "remote-run", "data": {"id": "remote-run", "status": remote_status, "error": "sandbox error", "outputs": {}}}
    async def controlled_run(self, inputs):
        return result
    monkeypatch.setattr(main.DifyClient, "run_workflow", controlled_run)
    response = client.post(f"/api/tasks/{tid}/run", json={"revision": task["revision"], "input": {"query": "x"}})
    assert response.status_code == 502 and "sandbox error" not in response.text
    current = main.get_task(tid)
    record = current["runs"][-1]
    assert current["status"] == "error"
    expected_status = "failed" if remote_status in {"failed", "stopped", "partial-succeeded"} else "unknown"
    assert record["status"] == expected_status
    if remote_status=='paused':
        assert record['result']['data']['status']=='paused' and not record['result']['waiting_state']['form_credentials_retained']
        assert 'sandbox error' not in json.dumps(record['result'])
    else:assert record["result"] == result
    assert "evaluation" not in record
    if expected_status == "unknown":
        repeated = client.post(f"/api/tasks/{tid}/run", json={"revision": task["revision"], "input": {"query": "x"}})
        assert repeated.status_code == 409
    assert client.get(f"/api/tasks/{tid}").json()["runs"][-1]["result"]["workflow_run_id"] == (None if remote_status=='paused' else "remote-run")


def test_report_distinguishes_current_real_import_from_stale_evidence(client):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    task["dify_app_id"] = "report-app"
    task["runs"] = [{"id": "i", "kind": "import", "revision": task["revision"], "environment_id": env['id'], "status": "success", "result": {"app_id": "report-app"}}, {"id": "r", "kind": "run", "revision": task["revision"], "environment_id": env['id'], "status": "success", "result": {"data": {"status": "succeeded"}}}]
    main.save_task(task)
    report = client.get(f"/api/tasks/{tid}/report").text
    assert "当前修订有匹配的真实导入记录" in report and "成功运行返回 1 次" in report
    assert "只完成静态检查" not in report
    task['runs'][0]['revision'] -= 1
    main.save_task(task)
    report = client.get(f"/api/tasks/{tid}/report").text
    assert "当前修订尚无匹配的真实导入记录" in report
    assert "成功运行返回 1 次" not in report
