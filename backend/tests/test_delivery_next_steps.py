import copy
from test_api import client, create_env, approved, forbid_api_external_calls
from app import main


def test_completed_current_app_report_does_not_request_duplicate_steps(client):
    env = create_env(client)
    response = client.patch(f"/api/environments/{env['id']}", json={"service_app_id":"report-current", "service_api_key":"not-real-delivery-key"})
    assert response.status_code == 200
    task = approved(client, env_id=env["id"])
    task["dify_app_id"] = "report-current"
    case = {"id":"declared-case", "name":"公开固定样例", "required":True, "input":{"query":"x"}, "expectation":{"mode":"contains", "target":"result", "expected":["x"]}}
    task["test_cases"] = [case]
    base = {"revision":task["revision"], "environment_id":env["id"], "status":"success"}
    task["runs"] = [
        {**base, "id":"import", "kind":"import", "result":{"app_id":"report-current"}},
        {**base, "id":"publish", "kind":"publish", "app_id":"report-current", "result":{"app_id":"report-current", "state":"succeeded", "workflow_id":"published-test-graph"}},
        {**base, "id":"run", "kind":"run", "app_id":"report-current", "input":case["input"], "test_case":case, "result":{"data":{"outputs":{"result":"x"}}}, "evaluation":{"status":"passed", "mode":"contains", "details":"固定关键词通过"}}]
    main.save_task(task)
    before = copy.deepcopy(task)
    response = client.get(f"/api/tasks/{task['id']}/report")
    assert response.status_code == 200
    todos = response.text.split("## 待办", 1)[1]
    assert "无需重复发布" in todos
    assert "无需再次创建或复制登记" in todos
    assert "已声明必选样例 1 / 1 通过" in todos
    assert "外部编辑" in todos and "完整业务" in todos
    assert "配置该应用专属的运行 API Key" not in todos
    assert "not-real-delivery-key" not in response.text
    assert main.get_task(task["id"]) == before


import pytest
from app.delivery_next_steps import describe


def saved_task():
    return {"revision":3, "environment_id":"env", "dify_app_id":"app", "app_type":"workflow",
            "requirements_confirmed":True, "configuration_confirmed":True, "configuration":{},
            "runs":[{"kind":"import", "revision":3, "environment_id":"env", "status":"success", "result":{"app_id":"app"}},
                    {"kind":"publish", "revision":3, "environment_id":"env", "app_id":"app", "status":"success", "result":{"app_id":"app", "state":"succeeded", "workflow_id":"graph"}}]}


PASSED = {"required":{"total":1,"passed":1}, "all_required_passed":True}


@pytest.mark.parametrize("field,value", [("revision",2),("environment_id","old-env"),("app_id","old-app"),("app_id",None)])
def test_publication_from_other_scope_never_clears_todo(field, value):
    task = saved_task()
    task["runs"][-1][field] = value
    text = "\n".join(describe(task, PASSED))
    assert "无需重复发布" not in text
    assert "尚无当前App的发布成功回执" in text


@pytest.mark.parametrize("status", ["pending","unknown"])
def test_unknown_publication_requires_original_record_without_retry(status):
    task = saved_task()
    task["runs"].append({**task["runs"][-1], "status":status})
    before = copy.deepcopy(task)
    text = "\n".join(describe(task, PASSED, runtime_key_paired=True))
    assert "禁止直接重发" in text and "无需重复发布" not in text
    assert task == before


@pytest.mark.parametrize("app_type", ["advanced-chat","agent"])
def test_other_app_types_keep_their_own_publication_path(app_type):
    task = saved_task()
    task["app_type"] = app_type
    text = "\n".join(describe(task, PASSED))
    assert "不套用Workflow发布回执" in text and "无需重复发布" not in text
    assert task["app_type"] == app_type


def test_missing_app_does_not_claim_paired_key_or_pass_from_summary():
    task = saved_task()
    task["dify_app_id"] = None
    text = "\n".join(describe(task, PASSED, runtime_key_paired=True))
    assert "无需再次创建或复制登记" not in text
    assert "已声明必选样例 1 / 1 通过" not in text


@pytest.mark.parametrize("status", ["running","unknown"])
def test_unfinished_case_requires_review_before_any_new_run(status):
    summary = {"required":{"total":1,"passed":0,status:1}, "all_required_passed":False}
    text = "\n".join(describe(saved_task(), summary))
    assert "不能直接当失败重新运行" in text


def test_unconfirmed_mock_keeps_scope_and_dependency_work():
    task = saved_task()
    task["configuration_confirmed"] = False
    task["configuration"]["mock_dependencies"] = "已声明模拟接口"
    text = "\n".join(describe(task, PASSED, runtime_key_paired=False))
    assert "不能作为当前执行许可" in text and "声明模拟依赖" in text
    assert "尚无当前App配对的本机运行Key" in text
