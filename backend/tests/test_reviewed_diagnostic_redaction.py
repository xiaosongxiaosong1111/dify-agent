"""Public synthetic checks for the scoped memory-only diagnostic redaction helper.

Everything here is public and synthetic: a temporary Store, a fake assistant provider
with an encrypted fake key, a real POST diagnose call through the product API, and a
fake Dify transport.  No real data, key, model, network or Docker is touched.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
TOOLS = ROOT / "tools"
DUAL390 = TOOLS / "reviewed-dual390"
for _path in (str(BACKEND), str(DUAL390), str(TOOLS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_PREVIOUS_DATA_DIR = os.environ.get("FLOWCRAFT_DATA_DIR")
_BOOT = tempfile.mkdtemp(prefix="reviewed-diagnostic-redaction-boot-")
os.environ["FLOWCRAFT_DATA_DIR"] = _BOOT

import httpx
from fastapi.testclient import TestClient

from app import main as h
from app.storage import Store
from app.run_diagnostics import binding as product_binding

import tool as reviewed_tool
import storage_guard
import reviewed_diagnostic_redaction as redaction

_ORIGINAL_STORE = h.store
_ORIGINAL_DATA_ROOT = h.DATA_ROOT
_RAW = object()
TIMESTAMP = "2026-11-28T00:00:00+00:00"
APP = "a161d921-8f76-4a42-ad1e-6150a54cf0d8"
OTHER_APP = "895a778d-e2b2-4c41-9e26-5b08747dd59b"
REMOTE = "5b66dc55-cce6-4457-bd4b-8f48ecdfc1bd"
RUN_ID = "0d8b6f7a-6f0f-4a5e-9d6b-2a5a5f4c9e11"
MESSAGE_ID = "f0b0c3d4-6d2e-4f1a-9b8c-7a6e5d4c3b2a"
CONVERSATION_ID = "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f"
# Deliberately not matched by the generic token/key/JWT regexes, so a redaction
# proves the selected provider key itself was supplied to safe_text.
FAKE_KEY = "diagnostic-secret-7f3a9c1b"


def tearDownModule():
    if _PREVIOUS_DATA_DIR is None:
        os.environ.pop("FLOWCRAFT_DATA_DIR", None)
    else:
        os.environ["FLOWCRAFT_DATA_DIR"] = _PREVIOUS_DATA_DIR
    shutil.rmtree(_BOOT, ignore_errors=True)


class _AsyncBody(httpx.AsyncByteStream):
    def __init__(self, body):
        self._body = body

    async def __aiter__(self):
        yield self._body


def _json_response(value, status=200):
    return httpx.Response(status, headers=[("content-type", "application/json")],
                          stream=_AsyncBody(json.dumps(value, ensure_ascii=False).encode("utf-8")))


def _counting_store(provider_id):
    class CountingStore(Store):
        def __init__(self, root):
            super().__init__(root)
            self.api_key_reads = []

        def secret(self, item, key):
            value = super().secret(item, key)
            if item == provider_id and key == "api_key":
                self.api_key_reads.append(1)
            return value

    return CountingStore


class _FakeNative:
    """Fake Dify transport: message lookup plus two management reads, no network."""

    def __init__(self, nodes):
        self.nodes = nodes
        self.calls = []

    async def __call__(self, transport, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if path == f"/console/api/apps/{APP}/messages/{MESSAGE_ID}":
            return _json_response({"id": MESSAGE_ID, "conversation_id": CONVERSATION_ID,
                                   "workflow_run_id": REMOTE})
        if path == f"/console/api/apps/{APP}/workflow-runs/{REMOTE}":
            return _json_response({"id": REMOTE, "status": "succeeded"})
        if path == f"/console/api/apps/{APP}/workflow-runs/{REMOTE}/node-executions":
            return _json_response({"data": copy.deepcopy(self.nodes)})
        raise AssertionError("unexpected fake Dify path: " + path)


class _IsolatedTransport:
    def __init__(self, nodes):
        self.fake = _FakeNative(nodes)
        self.forbidden = []

    def __enter__(self):
        self._original_async = httpx.AsyncHTTPTransport.handle_async_request
        self._original_sync = httpx.HTTPTransport.handle_request
        self._original_model = h.call_model
        fake = self.fake

        async def intercepted(transport, request):
            return await fake(transport, request)

        def forbidden(*args, **kwargs):
            self.forbidden.append(1)
            raise AssertionError("real HTTP or model call is forbidden")

        httpx.AsyncHTTPTransport.handle_async_request = intercepted
        httpx.HTTPTransport.handle_request = forbidden
        h.call_model = forbidden
        return self.fake

    def __exit__(self, exc_type, exc, tb):
        httpx.AsyncHTTPTransport.handle_async_request = self._original_async
        httpx.HTTPTransport.handle_request = self._original_sync
        h.call_model = self._original_model
        return False


class _Fixture:
    def __init__(self, run_first=False, mutate=None, run_mutate=None):
        self.tmp = tempfile.mkdtemp(prefix="reviewed-redaction-")
        self.data = Path(self.tmp) / "data"
        self.provider_id = str(uuid.uuid4())
        self.owner = str(uuid.uuid4())
        self.run_first = run_first
        self.Base = _counting_store(self.provider_id)
        base = self.Base(self.data)

        env_id = str(uuid.uuid4())
        workspace = str(uuid.uuid4())
        env = {
            "id": env_id, "name": "公开脱敏合成环境", "base_url": "https://public-dify.invalid",
            "version": "1.17.1", "console_workspace_id": workspace,
            "console_login_binding": {"base_url": "https://public-dify.invalid", "version": "1.17.1", "workspace_id": workspace},
            "service_app_id": APP, "connection_revision": str(uuid.uuid4()),
            "capabilities": {"console": "verified", "datasets": "untested", "runtime": "verified"},
        }
        base.put_with_secrets("environment", env_id, env, {
            "console_token": "PUBLIC_CONSOLE_TOKEN_123456", "csrf_token": "PUBLIC_CSRF_TOKEN_123456",
            "service_api_key": "app-PUBLIC-SERVICE-390", "dataset_api_key": "dataset-PUBLIC-390",
            "console_login_email": "public@example.invalid", "console_login_password": "PUBLIC_ONLY",
        })
        base.put("provider", self.provider_id, {
            "id": self.provider_id, "name": "公开合成助手模型", "provider": "custom",
            "base_url": "https://public-model.invalid/v1", "model": "public-model", "role": "main",
            "protocol": "openai-compatible",
            "capabilities": {"text": "untested", "tools": "untested", "structured_output": "untested", "vision": "untested"},
        })
        base.set_secret(self.provider_id, "api_key", FAKE_KEY)

        requirements = {"goal": "公开脱敏诊断", "audience": "公开合成用户", "input": "query文字",
                        "output": "固定输出", "rules": "只读诊断", "knowledge": "不适用",
                        "exceptions": "停止", "tests": "一例"}
        cases = [{"id": "case1", "name": "公开样例", "input": {"query": "q"},
                  "expectation": {"mode": "equals", "target": "answer", "expected": "a"}, "required": True}]
        plan = {"schema_version": 1, "nodes": [
                    {"id": "start", "type": "start", "config": {"variables": []}},
                    {"id": "no_hit_text", "type": "template-transform", "config": {"template": "公开无答案", "variables": []}},
                    {"id": "answer", "type": "answer", "config": {"answer": "{{#no_hit_text.output#}}"}}],
                "edges": [{"source": "start", "target": "no_hit_text"}, {"source": "no_hit_text", "target": "answer"}]}
        modified = copy.deepcopy(plan)
        modified["nodes"][1]["config"]["template"] = "公开修改无答案"
        modified_requirements = {**requirements, "output": "修改输出"}
        modified_cases = copy.deepcopy(cases)
        modified_cases[0]["expectation"]["expected"] = "b"

        task = {
            "id": self.owner, "name": "公开脱敏诊断任务", "app_type": "advanced-chat",
            "environment_id": env_id, "revision": 8, "status": "draft_ready",
            "requirements": copy.deepcopy(requirements), "requirements_confirmed": True,
            "configuration": {"assistant_provider_id": self.provider_id,
                              "dify_model_provider": "public/provider", "dify_model": "public-model"},
            "configuration_confirmed": True, "materials": [], "test_cases": copy.deepcopy(cases),
            "workflow_plan": copy.deepcopy(plan), "agent_plan": None, "plan_source": "manual", "plan_stale": False,
            "artifact": {"revision": 8, "sha256": "a" * 64}, "dify_app_id": APP,
            "messages": [], "versions": [], "confirmations": [], "intake_history": [],
            "intake_review": {"review": {"schema_version": 1, "checks": []}, "source": "user_declared", "created_at": TIMESTAMP},
            "runs": [], "planning_runs": [], "created_at": TIMESTAMP, "updated_at": TIMESTAMP,
        }
        if mutate is not None:
            mutate(task, env)
            base.put("environment", env_id, env)
        self.env = base.get("environment", env_id)
        # Small synthetic graph, not the full business graph source check.  Task and
        # run are both advanced-chat; no native workflow_run_id is preset, so the
        # diagnostic must map the saved message to its native run.
        run = {"id": RUN_ID, "kind": "run", "revision": task["revision"], "environment_id": env_id,
               "environment_binding": product_binding(self.env), "app_type": "advanced-chat",
               "app_id": APP, "status": "success",
               "result": {"id": MESSAGE_ID, "message_id": MESSAGE_ID,
                          "conversation_id": CONVERSATION_ID, "mode": "advanced-chat",
                          "answer": "公开合成回答"}}
        if run_mutate is not None:
            run_mutate(run)
        self.run = run
        if run_first:
            task["runs"] = [copy.deepcopy(run)]
        base.put("task", self.owner, task)
        base.put("task_budget", self.owner, {
            "id": self.owner, "policy_revision": 1, "limit_usd": "0.600", "entries": [],
            "policy_history": [], "excluded_history_present": False, "scope": "since_ledger_start",
            "created_at": TIMESTAMP})
        self.initial_task = copy.deepcopy(base.get("task", self.owner))
        self.initial_budget = base.get("task_budget", self.owner)
        self.old = reviewed_tool.capture(self.data)
        self.contract = {
            "original": {"plan": copy.deepcopy(plan), "requirements": copy.deepcopy(requirements), "cases": copy.deepcopy(cases)},
            "modified": {"plan": modified, "requirements": modified_requirements, "cases": modified_cases},
        }
        self.boundary = SimpleNamespace(owner=self.owner, apps={APP: {"key": "app-PUBLIC-SERVICE-390"}},
                                        current=APP, halted=False, phase="original_cases",
                                        workspace_verified=False, login_tokens=None)
        self.store = None

    def build_guarded(self):
        self.guarded_cls = storage_guard.guarded(self.Base, self.env, self.contract, self.boundary,
                                                 self.old, self.initial_task, self.initial_budget)
        return self.guarded_cls

    def install(self, scope=_RAW):
        guarded = self.build_guarded()
        store_cls = guarded if scope is _RAW else redaction.extend_guard(
            guarded, self.Base, self.boundary, self.initial_task, scope)
        self.store = store_cls(self.data)
        h.store = self.store
        h.DATA_ROOT = self.data
        if not self.run_first:
            task = h.get_task(self.owner)
            task["runs"].append(copy.deepcopy(self.run))
            h.save_task(task)
        return self.store

    def scope(self, max_reads=2, **overrides):
        value = {"provider_id": self.provider_id, "purpose": "run_diagnostic_redaction",
                 "memory_only": True, "model_calls": 0, "max_reads": max_reads}
        value.update(overrides)
        return value

    def diagnose_path(self):
        return f"/api/tasks/{self.owner}/runs/{RUN_ID}/diagnose"

    def verify(self):
        return storage_guard.verify(self.store, self.env, self.boundary, self.old,
                                    self.initial_task, self.initial_budget)


def _nodes():
    return [
        {"id": "exec-1", "node_id": "start", "node_type": "start", "title": "开始",
         "status": "succeeded", "error": None},
        {"id": "exec-2", "node_id": "answer", "node_type": "answer", "title": "回答",
         "status": "failed", "error": "native failure: " + FAKE_KEY},
    ]


class RedactionScopeTests(unittest.TestCase):
    def setUp(self):
        self._tmpdirs = []
        h.store = _ORIGINAL_STORE
        h.DATA_ROOT = _ORIGINAL_DATA_ROOT

    def tearDown(self):
        h.store = _ORIGINAL_STORE
        h.DATA_ROOT = _ORIGINAL_DATA_ROOT
        for folder in self._tmpdirs:
            shutil.rmtree(folder, ignore_errors=True)

    def fixture(self, **kwargs):
        value = _Fixture(**kwargs)
        self._tmpdirs.append(value.tmp)
        return value

    def entries(self, api, fixture, client, **body):
        payload = {"revision": fixture.initial_task["revision"], "read_remote": True}
        payload.update(body)
        return client.request("POST", fixture.diagnose_path(), json=payload)

    def test_raw_guard_and_scope_none_keep_the_391_refusal(self):
        for mode in ("raw", "none"):
            with self.subTest(mode=mode):
                fixture = self.fixture()
                fixture.install(scope=_RAW if mode == "raw" else None)
                with _IsolatedTransport(_nodes()) as fake:
                    with TestClient(h.app) as api:
                        client = api if mode == "raw" else redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                        with self.assertRaises(RuntimeError) as caught:
                            self.entries(api, fixture, client)
                self.assertIn("Other credential read forbidden", str(caught.exception))
                self.assertEqual(fixture.store.api_key_reads, [])
                self.assertEqual(fake.calls, [])
                self.assertFalse(redaction.context_active())

    def test_scoped_helper_passes_real_diagnose_and_redacts(self):
        fixture = self.fixture()
        fixture.install(scope=fixture.scope(max_reads=2))
        with _IsolatedTransport(_nodes()) as fake:
            with TestClient(h.app) as api:
                client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                response = self.entries(api, fixture, client)
                self.assertEqual(response.status_code, 200, response.text)
                report = response.json()
                self.assertNotIn(FAKE_KEY, response.text)
                self.assertEqual(report["trace_state"], "read")
                self.assertEqual(report["node_count"], 2)
                self.assertIn("[已脱敏]", report["nodes"][1]["error"])
                self.assertNotIn(FAKE_KEY, json.dumps(report, ensure_ascii=False))
                self.assertEqual(len(fixture.store.api_key_reads), 1)
                resolution = report["remote_id_resolution"]
                self.assertEqual((resolution["message_id"], resolution["conversation_id"],
                                  resolution["workflow_run_id"]),
                                 (MESSAGE_ID, CONVERSATION_ID, REMOTE))
                self.assertEqual(resolution["kind"], "chat_message_record")
                self.assertFalse(resolution["message_body_saved"])
                self.assertEqual(fake.calls, [
                    ("GET", f"/console/api/apps/{APP}/messages/{MESSAGE_ID}"),
                    ("GET", f"/console/api/apps/{APP}/workflow-runs/{REMOTE}"),
                    ("GET", f"/console/api/apps/{APP}/workflow-runs/{REMOTE}/node-executions"),
                ])
                self.assertFalse(redaction.context_active())
                saved = h.get_task(fixture.owner)
                stored = json.dumps(saved["runs"][-1]["diagnostics"], ensure_ascii=False)
                self.assertTrue(saved["runs"][-1]["diagnostics"])
                self.assertNotIn(FAKE_KEY, stored)
                self.assertNotIn(FAKE_KEY, response.text)
        check = fixture.verify()
        self.assertTrue(check["original_objects_kept"])
        self.assertTrue(check["old_credentials_and_assets_kept"])
        self.assertTrue(check["budget_kept"])
        self.assertEqual(Store(fixture.data).secret(fixture.provider_id, "api_key"), FAKE_KEY)
        self.assertFalse(redaction.context_active())

    def test_max_reads_budget_is_cumulative_and_context_resets(self):
        fixture = self.fixture()
        fixture.install(scope=fixture.scope(max_reads=2))
        with _IsolatedTransport(_nodes()):
            with TestClient(h.app) as api:
                client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                self.assertEqual(self.entries(api, fixture, client).status_code, 200)
                self.assertFalse(redaction.context_active())
                self.assertEqual(self.entries(api, fixture, client).status_code, 200)
                self.assertFalse(redaction.context_active())
                with self.assertRaises(RuntimeError):
                    self.entries(api, fixture, client)
                self.assertFalse(redaction.context_active())
        self.assertEqual(len(fixture.store.api_key_reads), 2)
        self.assertTrue(fixture.verify()["budget_kept"])

    def test_wrong_provider_key_and_phase_are_refused(self):
        fixture = self.fixture(run_first=True)
        fixture.install(scope=fixture.scope())
        other = str(uuid.uuid4())
        with self.assertRaises(RuntimeError):
            fixture.store.secret(other, "api_key")
        with self.assertRaises(RuntimeError):
            fixture.store.secret(fixture.provider_id, "console_token")
        with self.assertRaises(RuntimeError):
            fixture.store.secret(fixture.env["id"], "api_key")
        with self.assertRaises(RuntimeError):
            fixture.store.set_secret(fixture.provider_id, "api_key", "replacement")
        with self.assertRaises(RuntimeError):
            fixture.store.put("provider", fixture.provider_id, {"id": fixture.provider_id})
        self.assertEqual(fixture.store.api_key_reads, [])

        fixture.boundary.phase = "original_import"
        with _IsolatedTransport(_nodes()) as fake:
            with TestClient(h.app) as api:
                client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                with self.assertRaises(RuntimeError):
                    self.entries(api, fixture, client)
        self.assertEqual(fixture.store.api_key_reads, [])
        self.assertEqual(fake.calls, [])
        self.assertFalse(redaction.context_active())

    def test_halted_batch_is_refused(self):
        fixture = self.fixture(run_first=True)
        fixture.install(scope=fixture.scope())
        fixture.boundary.halted = True
        with _IsolatedTransport(_nodes()) as fake:
            with TestClient(h.app) as api:
                client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                with self.assertRaises(RuntimeError):
                    self.entries(api, fixture, client)
        self.assertEqual(fixture.store.api_key_reads, [])
        self.assertEqual(fake.calls, [])
        self.assertFalse(redaction.context_active())

    def test_wrong_task_run_app_revision_and_environment_are_refused(self):
        cases = {
            "task": (lambda task, env: None, None, "boundary"),
            "run_revision": (None, lambda run: run.update(revision=7), "run"),
            "run_app": (None, lambda run: run.update(app_id=OTHER_APP), "run"),
            "run_environment": (None, lambda run: run.update(environment_id=str(uuid.uuid4())), "run"),
            "app": (lambda task, env: task.update(dify_app_id=OTHER_APP), None, "task"),
            "environment_binding": (None, lambda run: run.update(environment_binding="different"), "run"),
            "task_app_type_unsupported": (lambda task, env: task.update(app_type="agent"), None, "task"),
            "run_app_type_unsupported": (None, lambda run: run.update(app_type="agent"), "run"),
            "run_app_type_mismatch": (None, lambda run: run.update(app_type="workflow"), "run"),
        }
        for label, (mutate, run_mutate, kind) in cases.items():
            with self.subTest(label=label):
                fixture = self.fixture(run_first=True, mutate=mutate, run_mutate=run_mutate)
                fixture.install(scope=fixture.scope())
                if kind == "boundary":
                    fixture.boundary.owner = str(uuid.uuid4())
                with _IsolatedTransport(_nodes()) as fake:
                    with TestClient(h.app) as api:
                        client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                        with self.assertRaises(RuntimeError):
                            self.entries(api, fixture, client)
                self.assertEqual(fixture.store.api_key_reads, [])
                self.assertEqual(fake.calls, [])
                self.assertFalse(redaction.context_active())

    def test_environment_source_change_after_context_is_refused(self):
        fixture = self.fixture()
        fixture.install(scope=fixture.scope())
        original_secret = fixture.store.secret

        def changed_secret(item, key):
            if item == fixture.provider_id and key == "api_key":
                # The diagnostic context already holds the run's original binding.
                # Simulate an external source change before the guard re-checks it:
                # the environment and the stored run move together to a new binding,
                # so only the context snapshot can detect the change.  A plain base
                # Store is used deliberately to model the external mutation.
                raw = Store(fixture.data)
                env = raw.get("environment", fixture.env["id"])
                env["version"] = "1.17.2"
                raw.put("environment", env["id"], env)
                task = raw.get("task", fixture.owner)
                task["runs"][0]["environment_binding"] = product_binding(env)
                raw.put("task", fixture.owner, task)
            return original_secret(item, key)

        fixture.store.secret = changed_secret
        with _IsolatedTransport(_nodes()) as fake:
            with TestClient(h.app) as api:
                client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                with self.assertRaises(RuntimeError) as caught:
                    self.entries(api, fixture, client)
        self.assertIn("快照", str(caught.exception))
        self.assertEqual(fixture.store.api_key_reads, [])
        self.assertEqual(fake.calls, [])
        self.assertFalse(redaction.context_active())

    def test_wrong_revision_payload_is_rejected_before_the_provider_read(self):
        fixture = self.fixture(run_first=True)
        fixture.install(scope=fixture.scope())
        with _IsolatedTransport(_nodes()) as fake:
            with TestClient(h.app) as api:
                client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                response = self.entries(api, fixture, client, revision=fixture.initial_task["revision"] + 1)
                self.assertEqual(response.status_code, 409)
        self.assertEqual(fixture.store.api_key_reads, [])
        self.assertEqual(fake.calls, [])
        self.assertFalse(redaction.context_active())

    def test_ordinary_and_local_requests_keep_the_old_refusal(self):
        fixture = self.fixture()
        fixture.install(scope=fixture.scope())
        with _IsolatedTransport(_nodes()) as fake:
            with TestClient(h.app) as api:
                client = redaction.ScopedDiagnosticClient(api, h.store, fixture.boundary)
                self.assertEqual(client.request("GET", f"/api/tasks/{fixture.owner}").status_code, 200)
                self.assertFalse(redaction.context_active())
                with self.assertRaises(RuntimeError) as caught:
                    self.entries(api, fixture, client, read_remote=False)
                self.assertIn("Other credential read forbidden", str(caught.exception))
        self.assertEqual(fixture.store.api_key_reads, [])
        self.assertEqual(fake.calls, [])
        self.assertFalse(redaction.context_active())

    def test_invalid_scope_shapes_are_refused(self):
        fixture = self.fixture()
        guarded = fixture.build_guarded()
        good = fixture.scope()
        bad = [
            [], "scope", 7,
            {k: v for k, v in good.items() if k != "purpose"},
            {**good, "extra": 1},
            {**good, "provider_id": None},
            {**good, "provider_id": "not-a-uuid"},
            {**good, "provider_id": str(uuid.uuid4())},
            {**good, "purpose": "model_call"},
            {**good, "memory_only": False},
            {**good, "memory_only": 1},
            {**good, "model_calls": 1},
            {**good, "model_calls": True},
            {**good, "max_reads": 0},
            {**good, "max_reads": 15},
            {**good, "max_reads": True},
            {**good, "max_reads": "2"},
            {**good, "max_reads": 2.0},
        ]
        for value in bad:
            with self.subTest(scope=value):
                with self.assertRaises(RuntimeError):
                    redaction.extend_guard(guarded, fixture.Base, fixture.boundary, fixture.initial_task, value)

    def test_scope_none_returns_a_plain_subclass(self):
        fixture = self.fixture()
        guarded = fixture.build_guarded()
        scoped = redaction.extend_guard(guarded, fixture.Base, fixture.boundary, fixture.initial_task, None)
        self.assertTrue(issubclass(scoped, guarded))


if __name__ == "__main__":
    unittest.main()
