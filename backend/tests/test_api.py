import json
import sys
from pathlib import Path

import pytest
import httpx
import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.storage import Store
from app.dify import DifyError


@pytest.fixture(autouse=True)
def forbid_api_external_calls(monkeypatch):
    original_request = main.DifyClient.request
    def forbidden(*args, **kwargs):
        pytest.fail("API 隔离检查不得访问真实 HTTP 或调用真实模型")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(main.DifyClient, "request", forbidden)
    monkeypatch.setattr(main, "call_model", forbidden)
    return original_request


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


def at22_static_task(client, app_type="workflow", env_id=None):
    # Legacy intake bypass isolates offline delivery, not a complete new-task intake.
    task = approved(client, app_type=app_type, env_id=env_id)
    tid = task["id"]
    case = example_case()
    if app_type == "advanced-chat":
        case["expectation"]["target"] = "answer"
    response = client.post(f"/api/tasks/{tid}/test-cases", json={
        "revision": task["revision"], "cases": [case]})
    assert response.status_code == 200, response.text
    task = response.json()
    if app_type == "workflow":
        response = client.post(f"/api/tasks/{tid}/plan", json={
            "revision": task["revision"], "plan": code_only_plan()})
        assert response.status_code == 200, response.text
        task = response.json()
    for kind in ("requirements", "configuration"):
        response = client.post(f"/api/tasks/{tid}/confirm", json={
            "revision": task["revision"], "kind": kind})
        assert response.status_code == 200, response.text
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def at22_assert_delivery(client, task, original_bytes):
    tid = task["id"]
    assert task["artifact"]["revision"] == task["revision"]
    assert task["artifact"]["verification"] == "static_only"
    assert task["artifact"]["validation"]["valid"]
    download = client.get(f"/api/tasks/{tid}/artifact")
    assert download.status_code == 200
    assert download.content == original_bytes
    assert f"r{task['revision']}.yaml" in download.headers["content-disposition"]
    dsl = client.get(f"/api/tasks/{tid}/dsl")
    assert dsl.status_code == 200 and dsl.json()["revision"] == task["revision"]
    # The text endpoint uses universal newlines; the file download preserves bytes.
    assert dsl.json()["content"] == original_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    summary = client.get(f"/api/tasks/{tid}/acceptance").json()
    assert summary["verification"] == "declared_checks_only"
    assert not summary["all_required_passed"] and summary["required"]["passed"] == 0
    report = client.get(f"/api/tasks/{tid}/report")
    assert report.status_code == 200
    assert "静态" in report.text and "规则通过不代表完整业务验收" in report.text
    assert Store(main.store.root).get("task", tid) == task
    return report.text, summary


@pytest.mark.parametrize("app_type", ["workflow", "advanced-chat"])
@pytest.mark.parametrize("configured", [False, True])
def test_at22_offline_build_and_download_do_not_invent_import_or_run(client, app_type, configured):
    env_id = None
    if configured:
        response = client.post("/api/environments", json={
            "name": "未连接隔离环境", "base_url": "https://dify.example", "version": "1.17.1"})
        assert response.status_code == 201, response.text
        env_id = response.json()["id"]
        assert not main.store.has_secret(env_id, "console_token")
    task = at22_static_task(client, app_type, env_id)
    tid = task["id"]
    content = main.artifact_path(task).read_bytes()
    assert yaml.safe_load(content)["app"]["mode"] == app_type
    assert task["app_type"] == app_type and task["status"] == "draft_ready"
    assert not task["dify_app_id"] and not task["runs"]
    report, summary = at22_assert_delivery(client, task, content)
    assert "当前修订尚无匹配的真实导入记录" in report
    assert "当前应用标识：未导入" in report
    assert "成功运行返回" not in report
    assert summary["required"]["not_run"] == 1
    assert "当前App匹配" in summary["cases"][0]["details"] and "缺少App归属" in summary["cases"][0]["details"]
    # Missing environment and missing import binding are local gates, not failed runs.
    response = client.post(f"/api/tasks/{tid}/run", json={"revision": task["revision"], "case_id": "warranty"})
    assert response.status_code == 422
    assert ("尚未真实导入" if configured else "仍可生成待验证文件") in response.text
    assert client.get(f"/api/tasks/{tid}").json() == task


@pytest.mark.parametrize("kind", ["import", "run"])
@pytest.mark.parametrize("failure", ["connection", "timeout"])
def test_at22_disconnected_adapter_preserves_delivery_and_truthful_evidence(
        client, monkeypatch, forbid_api_external_calls, kind, failure):
    env = create_env(client)
    task = at22_static_task(client, env_id=env["id"])
    tid = task["id"]
    content = main.artifact_path(task).read_bytes()
    dispatched = []
    if kind == "run":
        # Synthetic import receipt establishes only the local run preconditions.
        async def controlled_import(self, content, name):
            return {"status": "completed", "app_id": "at22-synthetic-app"}
        monkeypatch.setattr(main.DifyClient, "import_new", controlled_import)
        response = client.post(f"/api/tasks/{tid}/import", json={"revision": task["revision"]})
        assert response.status_code == 200, response.text
        task = response.json()
        response = client.patch(f"/api/environments/{env['id']}", json={
            "service_app_id": "at22-synthetic-app", "service_api_key": "at22-not-a-real-key"})
        assert response.status_code == 200, response.text

    async def disconnected_transport(self, request):
        dispatched.append((request.method, request.url.path))
        assert request.url.host == "dify.example"
        error = httpx.ConnectError if failure == "connection" else httpx.ReadTimeout
        raise error("仅隔离测试的传输故障", request=request)

    # Restore the actual request/error adapter only behind a transport that always raises.
    monkeypatch.setattr(main.DifyClient, "request", forbid_api_external_calls)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", disconnected_transport)
    payload = {"revision": task["revision"], **({"case_id": "warranty"} if kind == "run" else {})}
    response = client.post(f"/api/tasks/{tid}/{kind}", json=payload)
    assert response.status_code == 502, response.text
    message = "可以继续生成待验证 DSL" if failure == "connection" else "结果可能未知"
    assert message in response.json()["detail"]
    expected_path = "/console/api/apps/imports" if kind == "import" else "/v1/workflows/run"
    assert dispatched == [("POST", expected_path)]  # No automatic retry.
    current = client.get(f"/api/tasks/{tid}").json()
    assert current["revision"] == task["revision"] and current["app_type"] == "workflow"
    assert current["status"] == "error" and current["artifact"] == task["artifact"]
    assert current["dify_app_id"] == ("at22-synthetic-app" if kind == "run" else None)
    record = current["runs"][-1]
    expected_status = "failed" if failure == "connection" else "unknown"
    assert record["kind"] == kind and record["status"] == expected_status
    assert record["revision"] == current["revision"] and record["environment_id"] == env["id"]
    assert record["error"] == response.json()["detail"] and record["completed_at"]
    assert "result" not in record and "evaluation" not in record
    report, summary = at22_assert_delivery(client, current, content)
    assert f"{kind} / r{current['revision']} / {expected_status}" in report
    assert "成功运行返回 1 次" not in report
    if kind == "import":
        assert len(current["runs"]) == 1
        assert "当前修订尚无匹配的真实导入记录" in report
        assert summary["required"]["not_run"] == 1
    else:
        assert len(current["runs"]) == 2 and current["runs"][0] == task["runs"][0]
        assert "成功运行返回 0 次" in report
        assert summary["cases"][0]["status"] == expected_status

    # Reopen the isolated database and run normal startup recovery; no redispatch.
    monkeypatch.setattr(main, "store", Store(main.store.root))
    main.recover_external_actions()
    assert client.get(f"/api/tasks/{tid}").json() == current
    assert dispatched == [("POST", expected_path)]
    rebuilt = client.post(f"/api/tasks/{tid}/build", json={"revision": current["revision"]})
    assert rebuilt.status_code == 200, rebuilt.text
    rebuilt_task = rebuilt.json()
    assert rebuilt_task["status"] == "draft_ready"
    assert rebuilt_task["runs"] == current["runs"]
    assert rebuilt_task["dify_app_id"] == current["dify_app_id"]
    at22_assert_delivery(client, rebuilt_task, content)
    assert dispatched == [("POST", expected_path)]
    if failure == "timeout":
        repeated = client.post(f"/api/tasks/{tid}/{kind}", json=payload)
        assert repeated.status_code == 409 and "禁止盲目重复执行" in repeated.text
        assert client.get(f"/api/tasks/{tid}").json() == rebuilt_task
        assert dispatched == [("POST", expected_path)]


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
    task["runs"] = [{"id": "i", "kind": "import", "revision": task["revision"], "environment_id": env['id'], "status": "success", "result": {"app_id": "report-app"}}, {"id": "r", "kind": "run", "app_id": "report-app", "revision": task["revision"], "environment_id": env['id'], "status": "success", "result": {"data": {"status": "succeeded"}}}]
    main.save_task(task)
    report = client.get(f"/api/tasks/{tid}/report").text
    assert "当前修订有匹配的真实导入记录" in report and "成功运行返回 1 次" in report
    assert "只完成静态检查" not in report
    task['runs'][0]['revision'] -= 1
    main.save_task(task)
    report = client.get(f"/api/tasks/{tid}/report").text
    assert "当前修订尚无匹配的真实导入记录" in report
    assert "成功运行返回 1 次" not in report


MOCK_ORDER = "订单查询接口：用户接受固定样例；模拟位置 code 节点；真实接入待办：补接口地址和鉴权、替换样例并重验"


@pytest.mark.parametrize("app_type", ["workflow", "advanced-chat", "agent"])
def test_at10_new_task_does_not_invent_mock_consent(client, app_type):
    response = client.post("/api/tasks", json={"name": "Sierra 模拟声明核对", "app_type": app_type})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["app_type"] == app_type
    assert task["configuration"]["mock_dependencies"] == []
    assert not task["configuration_confirmed"] and not task["artifact"] and not task["runs"]
    assert Store(main.store.root).get("task", task["id"])["configuration"]["mock_dependencies"] == []


@pytest.mark.parametrize("app_type", ["workflow", "advanced-chat"])
def test_at10_legacy_template_carries_explicit_declaration_to_downloads(client, app_type):
    # This exercises the legacy template only, not new-task intake or an executable mock service.
    task = approved(client, app_type=app_type)
    tid = task["id"]
    response = client.patch(f"/api/tasks/{tid}", json={"configuration": {"mock_dependencies": [MOCK_ORDER]}})
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["requirements_confirmed"] and not task["configuration_confirmed"]
    assert client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]}).status_code == 422
    response = client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]})
    assert response.status_code == 200, response.text
    assert response.json()["confirmations"][-1]["revision"] == task["revision"]
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    built = response.json()
    assert built["artifact"]["verification"] == "static_only"
    assert any("包含模拟依赖" in warning for warning in built["artifact"]["validation"]["warnings"])
    download = client.get(f"/api/tasks/{tid}/artifact")
    assert download.status_code == 200, download.text
    dsl = yaml.safe_load(download.text)
    assert dsl["app"]["mode"] == app_type
    assert "模拟依赖（未接入真实服务）" in dsl["app"]["description"]
    assert MOCK_ORDER in dsl["app"]["description"]
    assert all(node["data"]["type"] != "http-request" for node in dsl["workflow"]["graph"]["nodes"])
    report = client.get(f"/api/tasks/{tid}/report")
    assert report.status_code == 200, report.text
    assert MOCK_ORDER in report.text
    assert "按原确认范围替换并重新验证" in report.text and "不能当真实依赖已经交付" in report.text
    assert "静态" in report.text and "规则通过不代表完整业务验收" in report.text
    saved = Store(main.store.root).get("task", tid)
    assert saved["configuration"]["mock_dependencies"] == [MOCK_ORDER]
    assert saved["versions"][-1]["configuration"]["mock_dependencies"] == [MOCK_ORDER]
    assert not saved["dify_app_id"] and not saved["runs"]


@pytest.mark.parametrize("invalid", ["自动模拟", [None], [{"name": "接口"}]])
def test_at10_bad_mock_declaration_does_not_mutate_task(client, invalid):
    task = approved(client)
    tid = task["id"]
    before = client.get(f"/api/tasks/{tid}").json()
    response = client.patch(f"/api/tasks/{tid}", json={"configuration": {"mock_dependencies": invalid}})
    assert response.status_code == 422 and "mock_dependencies 必须为字符串列表" in response.text
    assert client.get(f"/api/tasks/{tid}").json() == before
    assert Store(main.store.root).get("task", tid)["configuration"] == before["configuration"]


@pytest.mark.parametrize("replacement", [[], ["订单接口改用另一份样例，仍未真实接入"]])
def test_at10_mock_change_invalidates_approval_and_download(client, replacement):
    task = approved(client)
    tid = task["id"]
    task = client.patch(f"/api/tasks/{tid}", json={"configuration": {"mock_dependencies": [MOCK_ORDER]}}).json()
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]}).status_code == 200
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    old_version = response.json()["versions"][-1]
    changed = client.patch(f"/api/tasks/{tid}", json={"configuration": {"mock_dependencies": replacement}}).json()
    assert changed["revision"] == task["revision"] + 1
    assert changed["requirements_confirmed"] and not changed["configuration_confirmed"]
    assert not changed["artifact"] and not changed["dify_app_id"] and not changed["runs"]
    assert client.get(f"/api/tasks/{tid}/artifact").status_code == 404
    assert client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]}).status_code == 409
    assert client.post(f"/api/tasks/{tid}/build", json={"revision": changed["revision"]}).status_code == 422
    saved = Store(main.store.root).get("task", tid)
    assert saved["configuration"]["mock_dependencies"] == replacement
    assert next(v for v in saved["versions"] if v["id"] == old_version["id"]) == old_version


def test_at10_proposal_requires_separate_mock_consent_and_persists_it(client):
    task = approved(client)
    tid = task["id"]
    # No environment: the real local discovery path records resources as unverified without HTTP.
    response = client.post(f"/api/tasks/{tid}/configuration-proposal/resources", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    candidate = {"schema_version": 1, "configuration": {"mock_dependencies": [MOCK_ORDER]},
                 "reasons": [{"field": "mock_dependencies", "reason": "接口未提供，拟用固定样例",
                              "experience": "只能展示样例", "cost": "真实接口费用待核对", "manual_work": "补鉴权并替换重验"}],
                 "open_issues": [], "notes": "合成候选，仅检查明确采纳门禁"}
    assert main.configuration_proposals.validate(task, candidate)["valid"]
    main.configuration_proposals.save(task, candidate)
    state = client.get(f"/api/tasks/{tid}/configuration-proposal").json()
    record = state["record"]
    assert state["can_adopt"]
    before = client.get(f"/api/tasks/{tid}").json()
    assert before["configuration"]["mock_dependencies"] == []
    payload = {"revision": task["revision"], "proposal_id": record["id"], "proposal_token": record["proposal_token"],
               "acknowledge_changes": True, "acknowledge_unverified_resources": True}
    url = f"/api/tasks/{tid}/configuration-proposal/adopt"
    response = client.post(url, json=payload)
    assert response.status_code == 422 and "单独明确接受" in response.text
    assert client.get(f"/api/tasks/{tid}").json() == before
    assert Store(main.store.root).get("configuration_proposal", record["id"])["status"] == "proposed"
    response = client.post(url, json={**payload, "acknowledge_mock_changes": True})
    assert response.status_code == 200, response.text
    adopted = response.json()
    assert adopted["revision"] == task["revision"] + 1
    assert adopted["configuration"]["mock_dependencies"] == [MOCK_ORDER]
    assert not adopted["configuration_confirmed"] and not adopted["artifact"] and not adopted["runs"]
    saved = Store(main.store.root)
    receipt = saved.get("configuration_proposal", record["id"])
    assert receipt["status"] == "adopted" and receipt["applied_revision"] == adopted["revision"]
    assert receipt["acknowledgements"]["mock_changes"] is True
    assert saved.get("task", tid)["configuration"]["mock_dependencies"] == [MOCK_ORDER]
    assert client.post(url, json={**payload, "acknowledge_mock_changes": True}).status_code == 409


@pytest.mark.parametrize("app_type", ["workflow", "advanced-chat", "agent"])
@pytest.mark.parametrize("confirm_requirements", [False, True])
def test_at11_build_requires_current_confirmations(client, monkeypatch, app_type, confirm_requirements):
    # Legacy intake bypass isolates this gate; it does not prove new-task intake acceptance.
    task = create(client, app_type=app_type)
    tid = task["id"]
    task = client.patch(f"/api/tasks/{tid}", json={
        "requirements": {k: "明确的测试规则" for k in main.REQ_KEYS},
        "configuration": {"dify_model_provider": "test/provider", "dify_model": "test-model",
                          "resource_plan": "仅新建 Sierra 测试应用，不覆盖已有资源。"},
    }).json()
    if confirm_requirements:
        response = client.post(f"/api/tasks/{tid}/confirm", json={"kind": "requirements", "revision": task["revision"]})
        assert response.status_code == 200, response.text

    def forbidden_compile(*args, **kwargs):
        pytest.fail("未确认配置和资源操作时不得编译成果")
    monkeypatch.setattr(main, "compile_current", forbidden_compile)
    before = client.get(f"/api/tasks/{tid}").json()
    saved = Store(main.store.root).get("task", tid)
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert response.status_code == 422
    assert response.json()["detail"] == "需求、具体配置和资源操作尚未全部确认。"
    assert before["requirements_confirmed"] is confirm_requirements
    assert not before["configuration_confirmed"]
    assert before["configuration"]["resource_plan"] == "仅新建 Sierra 测试应用，不覆盖已有资源。"
    assert not before["artifact"] and not before["runs"] and not before["dify_app_id"]
    assert client.get(f"/api/tasks/{tid}").json() == before
    assert Store(main.store.root).get("task", tid) == saved
    assert not list((main.DATA_ROOT / tid).glob("artifact-*.yaml"))


@pytest.mark.parametrize("action", ["import", "run"])
@pytest.mark.parametrize("missing", ["requirements_confirmed", "configuration_confirmed"])
def test_at11_external_gate_precedes_adapter_and_operation_record(client, monkeypatch, action, missing):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    # A synthetic ready artifact/binding isolates each missing flag from earlier run prerequisites.
    # This is not an import receipt or a naturally reachable partially approved state.
    task = main.get_task(tid)
    task[missing] = False
    if action == "run":
        task["dify_app_id"] = "at11-synthetic-app"
        response = client.patch(f"/api/environments/{env['id']}", json={
            "service_app_id": task["dify_app_id"], "service_api_key": "at11-not-a-real-key"})
        assert response.status_code == 200, response.text
    main.save_task(task)

    async def forbidden_adapter(*args, **kwargs):
        pytest.fail("未确认时不得派发导入或试跑适配器")
    monkeypatch.setattr(main.DifyClient, "import_new", forbidden_adapter)
    monkeypatch.setattr(main.DifyClient, "run_workflow", forbidden_adapter)
    before = client.get(f"/api/tasks/{tid}").json()
    saved = Store(main.store.root).get("task", tid)
    artifact = main.artifact_path(task).read_bytes()
    response = client.post(f"/api/tasks/{tid}/{action}", json={"revision": task["revision"],
                           **({"input": {"query": "隔离测试"}} if action == "run" else {})})
    assert response.status_code == 422
    assert response.json()["detail"] == "当前版本尚未确认需求、配置和资源操作。"
    assert client.get(f"/api/tasks/{tid}").json() == before
    assert Store(main.store.root).get("task", tid) == saved
    assert main.artifact_path(task).read_bytes() == artifact
    assert not before["runs"]


def test_at11_blank_resource_plan_cannot_be_confirmed(client):
    task = approved(client)
    tid = task["id"]
    task = client.patch(f"/api/tasks/{tid}", json={"configuration": {"resource_plan": "   "}}).json()
    before = client.get(f"/api/tasks/{tid}").json()
    saved = Store(main.store.root).get("task", tid)
    assert before["requirements_confirmed"] and not before["configuration_confirmed"]
    response = client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]})
    assert response.status_code == 422
    assert "请填写具体资源操作方案" in response.json()["detail"]
    assert client.get(f"/api/tasks/{tid}").json() == before
    assert Store(main.store.root).get("task", tid) == saved


def test_at11_resource_plan_change_requires_reconfirmation(client):
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    tid, old_revision = task["id"], task["revision"]
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": old_revision})
    assert response.status_code == 200, response.text
    old_version = response.json()["versions"][-1]
    plan = "仅新建另一个 Sierra 应用；保留所有已有应用和知识库。"
    task = client.patch(f"/api/tasks/{tid}", json={"configuration": {"resource_plan": plan}}).json()
    assert task["revision"] == old_revision + 1
    assert task["requirements_confirmed"] and not task["configuration_confirmed"]
    assert not task["artifact"] and not task["dify_app_id"] and not task["runs"]
    before = client.get(f"/api/tasks/{tid}").json()
    saved = Store(main.store.root).get("task", tid)
    for action in ("confirm", "build", "import"):
        payload = {"revision": old_revision, **({"kind": "configuration"} if action == "confirm" else {})}
        response = client.post(f"/api/tasks/{tid}/{action}", json=payload)
        assert response.status_code == 409
        assert response.json()["detail"] == "方案已变化，请刷新并确认当前版本。"
    for action in ("build", "import"):
        response = client.post(f"/api/tasks/{tid}/{action}", json={"revision": task["revision"]})
        assert response.status_code == 422 and "尚未" in response.json()["detail"]
    assert client.get(f"/api/tasks/{tid}/artifact").status_code == 404
    assert client.get(f"/api/tasks/{tid}").json() == before
    assert Store(main.store.root).get("task", tid) == saved
    assert next(v for v in saved["versions"] if v["id"] == old_version["id"]) == old_version
    response = client.post(f"/api/tasks/{tid}/confirm", json={"kind": "configuration", "revision": task["revision"]})
    assert response.status_code == 200, response.text
    assert response.json()["confirmations"][-1]["revision"] == task["revision"]
    response = client.post(f"/api/tasks/{tid}/build", json={"revision": task["revision"]})
    assert response.status_code == 200, response.text
    assert response.json()["artifact"]["verification"] == "static_only"
    assert not response.json()["runs"] and not response.json()["dify_app_id"]


def at11_knowledge_draft(client, monkeypatch, *, strategy="economy"):
    env = create_env(client)
    task = approved(client, env_id=env["id"])

    async def workspace(*args, **kwargs):
        return {"id": "at11-synthetic-workspace", "name": "Sierra 隔离空间"}
    async def models(*args, **kwargs):
        return {"data": [{"provider": "test/embed", "models": [{"model": "test-embedding", "status": "active"}]}]}
    async def forbidden_write(*args, **kwargs):
        pytest.fail("本次 AT-11 核对不得创建知识库、Key 或文档")
    monkeypatch.setattr(main.DifyClient, "workspace", workspace)
    monkeypatch.setattr(main.DifyClient, "models", models)
    for name in ("create_dataset", "create_scoped_dataset_key", "create_text_document"):
        monkeypatch.setattr(main.DifyClient, name, forbidden_write)
    response = client.post(f"/api/tasks/{task['id']}/knowledge-jobs", json={
        "revision": task["revision"], "name": "Sierra 隔离资料库", "purpose": "只核对方案门禁",
        "text": "合成资料，不涉及客户数据。", "indexing_technique": strategy,
        **({"embedding_provider": "test/embed", "embedding_model": "test-embedding"} if strategy == "high_quality" else {})})
    assert response.status_code == 201, response.text
    return task, env, response.json()


@pytest.mark.parametrize("strategy", ["economy", "high_quality"])
def test_at11_configuration_confirmation_does_not_approve_knowledge_job(client, monkeypatch, strategy):
    task, env, job = at11_knowledge_draft(client, monkeypatch, strategy=strategy)
    assert task["configuration_confirmed"] and job["status"] == "draft"
    assert job["name"] == "Sierra 隔离资料库" and job["purpose"] == "只核对方案门禁"
    assert job["workspace"]["id"] == "at11-synthetic-workspace"
    assert job["indexing_technique"] == strategy and job["cost_note"]
    assert not job.get("confirmation") and not job["operations"] and not job["dataset_id"]
    before = client.get(f"/api/tasks/{task['id']}").json()
    saved = Store(main.store.root).get("knowledge_job", job["id"])
    response = client.post(f"/api/knowledge-jobs/{job['id']}/execute", json={})
    assert response.status_code == 409 and "须先确认未执行方案" in response.json()["detail"]
    if strategy == "high_quality":
        response = client.post(f"/api/knowledge-jobs/{job['id']}/confirm", json={"task_revision": task["revision"]})
        assert response.status_code == 422 and "费用未明确接受" in response.json()["detail"]
    assert Store(main.store.root).get("knowledge_job", job["id"]) == saved
    assert client.get(f"/api/tasks/{task['id']}").json() == before
    response = client.post(f"/api/knowledge-jobs/{job['id']}/confirm", json={
        "task_revision": task["revision"], "accept_unknown_embedding_cost": strategy == "high_quality"})
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["status"] == "approved" and not confirmed["operations"] and not confirmed["dataset_id"]
    assert confirmed["confirmation"]["task_revision"] == task["revision"]
    assert confirmed["confirmation"]["workspace_id"] == job["workspace"]["id"]
    assert confirmed["confirmation"]["accepted_unknown_embedding_cost"] is (strategy == "high_quality")
    assert Store(main.store.root).get("knowledge_job", job["id"])["confirmation"] == confirmed["confirmation"]
    assert client.get(f"/api/tasks/{task['id']}").json() == before
    assert not main.store.has_secret(job["id"], "dataset_api_key")


@pytest.mark.parametrize("approved_first,change", [(False, "revision"), (True, "revision"), (True, "connection")])
def test_at11_knowledge_confirmation_is_bound_to_task_and_connection(client, monkeypatch, approved_first, change):
    task, env, job = at11_knowledge_draft(client, monkeypatch)
    if approved_first:
        response = client.post(f"/api/knowledge-jobs/{job['id']}/confirm", json={"task_revision": task["revision"]})
        assert response.status_code == 200, response.text
    if change == "revision":
        response = client.patch(f"/api/tasks/{task['id']}", json={"configuration": {"resource_plan": "修改后的资源范围，须重新复核。"}})
    else:
        response = client.patch(f"/api/environments/{env['id']}", json={"base_url": "https://changed.example"})
    assert response.status_code == 200, response.text
    before = client.get(f"/api/tasks/{task['id']}").json()
    # The environment PATCH also invalidates bound tasks, so task revision is checked first.
    assert before["revision"] > task["revision"] and not before["configuration_confirmed"]
    saved = Store(main.store.root).get("knowledge_job", job["id"])
    action = "execute" if approved_first else "confirm"
    response = client.post(f"/api/knowledge-jobs/{job['id']}/{action}", json={} if approved_first else {"task_revision": task["revision"]})
    assert response.status_code == 409
    assert response.json()["detail"] == "任务修订或目标环境已变化；旧方案不继续派发或自动加入配置。"
    assert client.get(f"/api/tasks/{task['id']}").json() == before
    assert Store(main.store.root).get("knowledge_job", job["id"]) == saved
    assert not saved["operations"] and not saved["dataset_id"]


def at19_checked_task(client, monkeypatch, mode="contains"):
    # Fixed adapters and legacy intake bypass isolate revision gates, not platform acceptance.
    env = create_env(client)
    response = client.patch(f"/api/environments/{env['id']}", json={
        "service_app_id": "at19-synthetic-app", "service_api_key": "at19-not-a-real-key"})
    assert response.status_code == 200, response.text
    dispatched = []

    async def controlled_import(self, content, name):
        assert yaml.safe_load(content)["app"]["mode"] == "workflow"
        dispatched.append("import_new")
        return {"status": "completed", "app_id": "at19-synthetic-app"}

    async def controlled_run(self, inputs):
        assert inputs == example_case(mode)["input"]
        dispatched.append("run")
        return {"data": {"status": "succeeded", "outputs": {"result": "保修一年"}}}

    monkeypatch.setattr(main.DifyClient, "import_new", controlled_import)
    monkeypatch.setattr(main.DifyClient, "run_workflow", controlled_run)
    task = approved(client, env_id=env["id"])
    tid = task["id"]
    response = client.post(f"/api/tasks/{tid}/test-cases", json={
        "revision": task["revision"], "cases": [example_case(mode)]})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(f"/api/tasks/{tid}/plan", json={
        "revision": task["revision"], "plan": code_only_plan()})
    assert response.status_code == 200, response.text
    task = response.json()
    for kind in ("requirements", "configuration"):
        response = client.post(f"/api/tasks/{tid}/confirm", json={"revision": task["revision"], "kind": kind})
        assert response.status_code == 200, response.text
    for action in ("build", "import", "run"):
        response = client.post(f"/api/tasks/{tid}/{action}", json={
            "revision": task["revision"], **({"case_id": "warranty"} if action == "run" else {})})
        assert response.status_code == 200, response.text
    task = response.json()
    if mode == "manual":
        response = client.post(f"/api/tasks/{tid}/runs/{task['runs'][-1]['id']}/review", json={
            "revision": task["revision"], "decision": "passed", "reason": "仅人工核对固定隔离样例"})
        assert response.status_code == 200, response.text
        task = response.json()
    assert client.get(f"/api/tasks/{tid}/acceptance").json()["all_required_passed"]
    assert dispatched == ["import_new", "run"]
    return task, dispatched


@pytest.mark.parametrize("mode", ["contains", "manual"])
@pytest.mark.parametrize("change", ["configuration", "requirements", "both"])
def test_at19_change_excludes_old_pass_until_reconfirmed_and_rerun(client, monkeypatch, mode, change):
    old, dispatched = at19_checked_task(client, monkeypatch, mode)
    tid, old_revision = old["id"], old["revision"]
    old_artifact = main.artifact_path(old)
    old_bytes = old_artifact.read_bytes()
    patch = {}
    if change in {"requirements", "both"}:
        patch["requirements"] = {"rules": "修改保修例外规则，须重新核对"}
    if change in {"configuration", "both"}:
        patch["configuration"] = {"temperature": 0.5}
    response = client.patch(f"/api/tasks/{tid}", json=patch)
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["revision"] == old_revision + 1
    assert changed["app_type"] == old["app_type"]
    assert changed["requirements_confirmed"] is (change == "configuration")
    assert not changed["configuration_confirmed"] and not changed["artifact"] and not changed["dify_app_id"]
    assert changed["plan_stale"] is (change != "configuration")
    assert changed["workflow_plan"] == old["workflow_plan"]
    assert changed["test_cases"] == old["test_cases"] and changed["runs"] == old["runs"]
    assert changed["confirmations"][:len(old["confirmations"])] == old["confirmations"]
    assert changed["versions"][:len(old["versions"])] == old["versions"]
    assert changed["versions"][-1]["artifact"] == old["artifact"]
    if change == "configuration":
        assert changed["confirmations"][-1]["carried_from_revision"] == old_revision
        assert changed["confirmations"][-1]["revision"] == changed["revision"]
    else:
        assert changed["confirmations"] == old["confirmations"]
    assert old_artifact.read_bytes() == old_bytes
    assert Store(main.store.root).get("task", tid) == changed

    def assert_not_run():
        summary = client.get(f"/api/tasks/{tid}/acceptance").json()
        assert summary["required"]["not_run"] == 1 and summary["required"]["passed"] == 0
        assert not summary["all_required_passed"] and summary["cases"][0]["run_id"] is None

    assert_not_run()
    assert client.get(f"/api/tasks/{tid}/artifact").status_code == 404
    assert "当前修订尚无匹配的真实导入记录" in client.get(f"/api/tasks/{tid}/report").text
    for kind in ("requirements", "configuration"):
        response = client.post(f"/api/tasks/{tid}/confirm", json={"revision": old_revision, "kind": kind})
        assert response.status_code == 409
    for action in ("build", "import"):
        assert client.post(f"/api/tasks/{tid}/{action}", json={"revision": old_revision}).status_code == 409
        assert client.post(f"/api/tasks/{tid}/{action}", json={"revision": changed["revision"]}).status_code == 422
    # The run entry checks missing App binding before its revision gate.
    for revision in (old_revision, changed["revision"]):
        response = client.post(f"/api/tasks/{tid}/run", json={"revision": revision, "case_id": "warranty"})
        assert response.status_code == 422 and response.json()["detail"] == "当前版本尚未真实导入。"
    if mode == "manual":
        response = client.post(f"/api/tasks/{tid}/runs/{old['runs'][-1]['id']}/review", json={
            "revision": changed["revision"], "decision": "passed", "reason": "不能复用旧修订意见"})
        assert response.status_code == 409
    assert client.get(f"/api/tasks/{tid}").json() == changed
    assert Store(main.store.root).get("task", tid) == changed
    assert dispatched == ["import_new", "run"]

    if change != "configuration":
        response = client.post(f"/api/tasks/{tid}/confirm", json={"revision": changed["revision"], "kind": "configuration"})
        assert response.status_code == 422 and "请先确认" in response.json()["detail"]
        response = client.post(f"/api/tasks/{tid}/confirm", json={"revision": changed["revision"], "kind": "requirements"})
        assert response.status_code == 200, response.text
        response = client.post(f"/api/tasks/{tid}/confirm", json={"revision": changed["revision"], "kind": "configuration"})
        assert response.status_code == 422 and "流程计划已过期" in response.json()["detail"]
        response = client.post(f"/api/tasks/{tid}/plan", json={"revision": changed["revision"], "plan": old["workflow_plan"]})
        assert response.status_code == 200, response.text
        changed = response.json()
        assert changed["revision"] > old_revision and not changed["plan_stale"]
    revision = changed["revision"]
    response = client.post(f"/api/tasks/{tid}/confirm", json={"revision": revision, "kind": "configuration"})
    assert response.status_code == 200, response.text
    assert response.json()["confirmations"][-1]["revision"] == revision
    assert_not_run()
    for action in ("build", "import"):
        response = client.post(f"/api/tasks/{tid}/{action}", json={"revision": revision})
        assert response.status_code == 200, response.text
        assert_not_run()
    assert response.json()["artifact"]["verification"] == "static_only"
    assert dispatched == ["import_new", "run", "import_new"]
    # With the binding restored, old run requests must reach and fail the revision gate.
    response = client.post(f"/api/tasks/{tid}/run", json={"revision": old_revision, "case_id": "warranty"})
    assert response.status_code == 409
    assert dispatched == ["import_new", "run", "import_new"]
    response = client.post(f"/api/tasks/{tid}/run", json={"revision": revision, "case_id": "warranty"})
    assert response.status_code == 200, response.text
    rerun = response.json()
    assert rerun["runs"][:len(old["runs"])] == old["runs"]
    new_run = rerun["runs"][-1]
    assert new_run["revision"] == revision and new_run["id"] != old["runs"][-1]["id"]
    assert new_run["test_case"] == old["test_cases"][0]
    if mode == "manual":
        summary = client.get(f"/api/tasks/{tid}/acceptance").json()
        assert not summary["all_required_passed"] and summary["required"]["needs_review"] == 1
        assert not new_run.get("manual_review")
        response = client.post(f"/api/tasks/{tid}/runs/{new_run['id']}/review", json={
            "revision": revision, "decision": "passed", "reason": "重新核对本次固定响应"})
        assert response.status_code == 200, response.text
    summary = client.get(f"/api/tasks/{tid}/acceptance").json()
    assert summary["all_required_passed"] and summary["cases"][0]["run_id"] == new_run["id"]
    assert summary["verification"] == "declared_checks_only"
    assert Store(main.store.root).get("task", tid)["runs"] == client.get(f"/api/tasks/{tid}").json()["runs"]
    assert dispatched == ["import_new", "run", "import_new", "run"]


@pytest.mark.parametrize("kind", ["requirements", "configuration"])
def test_at19_unchanged_values_keep_confirmations_and_case_evidence(client, monkeypatch, kind):
    old, dispatched = at19_checked_task(client, monkeypatch)
    value = ({"rules": "  " + old["requirements"]["rules"] + "  "} if kind == "requirements"
             else {"temperature": old["configuration"]["temperature"]})
    response = client.patch(f"/api/tasks/{old['id']}", json={kind: value})
    assert response.status_code == 200, response.text
    current = response.json()
    assert {k: v for k, v in current.items() if k != "updated_at"} == {k: v for k, v in old.items() if k != "updated_at"}
    assert client.get(f"/api/tasks/{old['id']}/acceptance").json()["all_required_passed"]
    assert Store(main.store.root).get("task", old["id"])["revision"] == old["revision"]
    assert dispatched == ["import_new", "run"]


@pytest.mark.parametrize("invalid", [{"temperature": 3}, {"unknown_setting": "不能保存"}])
def test_at19_rejected_mixed_patch_preserves_confirmations_and_history(client, monkeypatch, invalid):
    old, dispatched = at19_checked_task(client, monkeypatch)
    artifact = main.artifact_path(old).read_bytes()
    response = client.patch(f"/api/tasks/{old['id']}", json={
        "requirements": {"rules": "不应部分保存的需求"}, "configuration": invalid})
    assert response.status_code == 422
    assert client.get(f"/api/tasks/{old['id']}").json() == old
    assert Store(main.store.root).get("task", old["id"]) == old
    assert main.artifact_path(old).read_bytes() == artifact
    assert client.get(f"/api/tasks/{old['id']}/acceptance").json()["all_required_passed"]
    assert dispatched == ["import_new", "run"]


@pytest.mark.parametrize("app_id", ["other-app", None, ""])
def test_report_does_not_count_success_from_another_or_unidentified_app(client, app_id):
    import copy
    env = create_env(client)
    task = approved(client, env_id=env["id"])
    task["dify_app_id"] = "report-app"
    task["runs"] = [
        {"id":"import", "kind":"import", "revision":task["revision"], "environment_id":env["id"],
         "status":"success", "result":{"app_id":"report-app"}},
        {"id":"current", "kind":"run", "revision":task["revision"], "environment_id":env["id"],
         "app_id":"report-app", "status":"success", "result":{"data":{"status":"succeeded"}}},
        {"id":"unrelated", "kind":"run", "revision":task["revision"], "environment_id":env["id"],
         "app_id":app_id, "status":"success", "result":{"data":{"status":"succeeded"}}}]
    main.save_task(task)
    before = copy.deepcopy(task)
    response = client.get(f"/api/tasks/{task['id']}/report")
    assert response.status_code == 200
    assert "成功运行返回 1 次" in response.text
    assert "成功运行返回 2 次" not in response.text
    assert main.get_task(task["id"]) == before
