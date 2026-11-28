"""Memory-only, precisely-scoped diagnostic redaction permission for reviewed batches.

This is a small helper for a later independent leftover executor, not an execution
entry point: there is no batch runner, approval system or CLI here.  Importing this
module has no side effect -- it never creates a Store, reads local configuration or
contacts any service.

A caller may pass an explicit scope only after a new frozen plan contains the
selected provider's memory-only diagnostic redaction scope and receives a direct
approval.  This batch does not use a real provider key; enabling it later is only
allowed after such a new frozen plan is explicitly and directly approved.  The
helper itself does not prove that a human approved anything and cannot authorize
batch 391 or automatically approve any new scope.

The scope only lets the existing diagnostic API decrypt the selected assistant
provider key inside the exact, already-authorized diagnostic context so the existing
``safe_text`` redaction can run.  Provider writes, model HTTP and every other secret
remain forbidden by the parent guard and the physical boundary.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import re
import uuid
from urllib.parse import urlsplit

PURPOSE = "run_diagnostic_redaction"
DIAGNOSTIC_PHASES = frozenset({"original_cases", "modified_cases"})
SUPPORTED_APP_TYPES = frozenset({"workflow", "advanced-chat"})
SCOPE_FIELDS = frozenset({"provider_id", "purpose", "memory_only", "model_calls", "max_reads"})
MAX_READS_FLOOR = 1
MAX_READS_CEILING = 14

_CONTEXT = contextvars.ContextVar("reviewed_diagnostic_redaction_context", default=None)
_DIAGNOSE_PATH = re.compile(r"^/api/tasks/([^/]+)/runs/([^/]+)/diagnose$")


class DiagnosticRedactionRefused(RuntimeError):
    """The scoped permission does not match the live diagnostic identity."""


def _require(condition, message):
    if not condition:
        raise DiagnosticRedactionRefused(message)


def _canonical_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _binding(env):
    # Deliberately the same source-binding formula as app.run_diagnostics.binding;
    # kept local so importing this helper pulls in no product module.
    return hashlib.sha256(json.dumps({k: env.get(k) for k in ("id", "base_url", "version")}, sort_keys=True).encode()).hexdigest()


def _validated_scope(scope, initial_task):
    _require(isinstance(scope, dict), "诊断脱敏范围必须是明确对象。")
    _require(set(scope) == SCOPE_FIELDS, "诊断脱敏范围字段必须固定且完整。")
    provider_id = scope.get("provider_id")
    _require(_canonical_uuid(provider_id), "诊断脱敏的模型服务ID必须是合法UUID。")
    configuration = initial_task.get("configuration") if isinstance(initial_task, dict) else None
    _require(isinstance(configuration, dict) and configuration.get("assistant_provider_id") == provider_id,
             "诊断脱敏的模型服务ID必须等于当前任务绑定的助手模型。")
    _require(scope.get("purpose") == PURPOSE, "诊断脱敏用途必须精确匹配。")
    _require(scope.get("memory_only") is True, "诊断脱敏必须声明仅内存。")
    _require(type(scope.get("model_calls")) is int and scope["model_calls"] == 0, "诊断脱敏不得调用模型。")
    max_reads = scope.get("max_reads")
    _require(type(max_reads) is int and MAX_READS_FLOOR <= max_reads <= MAX_READS_CEILING,
             "诊断脱敏读取预算必须是1到14的整数。")
    return {"provider_id": provider_id, "purpose": PURPOSE, "max_reads": max_reads}


class _DiagnosticContext:
    """Identity-only request context; it never holds a decrypted key or a copy."""

    __slots__ = ("store", "boundary", "owner", "run_id", "revision", "app_id", "environment_id", "environment_binding", "purpose")

    def __init__(self, store, boundary, owner, run_id, revision, app_id, environment_id, environment_binding):
        self.store = store
        self.boundary = boundary
        self.owner = owner
        self.run_id = run_id
        self.revision = revision
        self.app_id = app_id
        self.environment_id = environment_id
        self.environment_binding = environment_binding
        self.purpose = PURPOSE


def _check_context(store, ctx, boundary, owner, provider_id):
    _require(ctx.store is store, "诊断脱敏上下文不属于当前存储。")
    _require(ctx.boundary is boundary, "诊断脱敏上下文不属于当前边界。")
    _require(ctx.purpose == PURPOSE, "诊断脱敏上下文用途不匹配。")
    _require(_canonical_uuid(ctx.owner), "诊断脱敏任务ID必须是合法UUID。")
    _require(_canonical_uuid(ctx.run_id), "诊断脱敏运行ID必须是合法UUID。")
    _require(not getattr(boundary, "halted", True), "批次已停止，拒绝读取模型密钥。")
    _require(boundary.owner == owner == ctx.owner, "诊断脱敏任务身份不匹配。")
    _require(getattr(boundary, "phase", None) in DIAGNOSTIC_PHASES, "只允许在已批的诊断阶段读取模型密钥。")
    _require(getattr(boundary, "current", None) == ctx.app_id, "诊断脱敏应用身份不匹配。")
    _require(_canonical_uuid(ctx.app_id), "诊断脱敏应用ID必须是合法UUID。")
    task = store.get("task", ctx.owner)
    _require(isinstance(task, dict) and task.get("id") == ctx.owner, "诊断脱敏任务不存在。")
    _require(type(ctx.revision) is int and task.get("revision") == ctx.revision, "诊断脱敏任务修订不匹配。")
    _require(isinstance(ctx.app_id, str) and ctx.app_id and task.get("dify_app_id") == ctx.app_id, "诊断脱敏应用身份不匹配。")
    _require(task.get("environment_id") == ctx.environment_id, "诊断脱敏环境身份不匹配。")
    configuration = task.get("configuration")
    _require(isinstance(configuration, dict) and configuration.get("assistant_provider_id") == provider_id, "诊断脱敏模型服务已变化。")
    runs = [r for r in task.get("runs", []) if isinstance(r, dict) and r.get("id") == ctx.run_id]
    _require(len(runs) == 1 and runs[0].get("kind") == "run", "诊断脱敏运行记录不唯一。")
    run = runs[0]
    _require(run.get("revision") == ctx.revision and run.get("app_id") == ctx.app_id and run.get("environment_id") == ctx.environment_id,
             "诊断脱敏运行来源不匹配。")
    _require(task.get("app_type") in SUPPORTED_APP_TYPES and run.get("app_type") == task.get("app_type"),
             "诊断脱敏应用类型不受支持或与任务类型不一致。")
    _require(run.get("status") != "pending", "运行尚未结束，拒绝读取模型密钥。")
    _require(_canonical_uuid(ctx.environment_id), "诊断脱敏环境ID必须是合法UUID。")
    env = store.get("environment", ctx.environment_id)
    _require(isinstance(env, dict) and env.get("id") == ctx.environment_id, "诊断脱敏环境不存在。")
    _require(run.get("environment_binding") == _binding(env), "诊断脱敏环境绑定不匹配。")
    _require(ctx.environment_binding == run.get("environment_binding"), "诊断脱敏环境绑定快照已变化。")


def extend_guard(parent_guard, base_store, boundary, initial_task, scope):
    """Return a ``parent_guard`` subclass adding only the scoped key read.

    ``scope=None`` keeps the old behaviour exactly (a plain subclass with no extra
    permission).  With an enabled scope the subclass allows exactly one item/key
    pair -- the selected assistant provider's ``api_key`` -- and only while the
    matching :class:`ScopedDiagnosticClient` context is active.  Everything else is
    delegated to the parent guard, so provider writes, model HTTP and every other
    secret stay forbidden.
    """
    _require(isinstance(parent_guard, type), "父守卫必须是类。")
    _require(isinstance(base_store, type) and callable(getattr(base_store, "secret", None)), "基础存储必须提供secret。")
    _require(boundary is not None and isinstance(getattr(boundary, "owner", None), str) and boundary.owner,
             "诊断脱敏必须绑定明确任务所有者。")
    if scope is None:
        class Scoped(parent_guard):
            pass
        return Scoped
    fields = _validated_scope(scope, initial_task)
    provider_id = fields["provider_id"]
    max_reads = fields["max_reads"]
    owner = boundary.owner
    reads = [0]

    class Scoped(parent_guard):
        def secret(self, item, key):
            if item != provider_id or key != "api_key":
                return super().secret(item, key)
            ctx = _CONTEXT.get()
            if ctx is None:
                # No exact diagnostic context: preserve the old refusal.
                return super().secret(item, key)
            _check_context(self, ctx, boundary, owner, provider_id)
            _require(reads[0] < max_reads, "诊断脱敏密钥读取超出已批准预算。")
            reads[0] += 1
            # Read-only decryption through the unguarded base store; the value is
            # returned directly and never cached, logged or persisted here.
            return base_store.secret(self, provider_id, "api_key")

    return Scoped


class ScopedDiagnosticClient:
    """Wrap only the diagnostic call that may establish the redaction context.

    Ordinary requests are forwarded unchanged.  A context is established only for
    ``POST /api/tasks/{owner}/runs/{run}/diagnose`` with ``read_remote is True``,
    the current Task revision, and a stored run that belongs to the owner's current
    App/revision/environment and is not pending.  The context is a ContextVar; the
    ``finally`` restores it so it cannot leak across requests or instances.  The
    store lock is only held while reading identity, never across the API call, so a
    TestClient worker thread cannot deadlock.
    """

    def __init__(self, api, store, boundary):
        self.api = api
        self.store = store
        self.boundary = boundary

    def request(self, method, url, **kwargs):
        match = _DIAGNOSE_PATH.fullmatch(urlsplit(str(url)).path) if str(method).upper() == "POST" else None
        if match is None:
            return self.api.request(method, url, **kwargs)
        owner, run_id = match.group(1), match.group(2)
        body = kwargs.get("json")
        if owner != getattr(self.boundary, "owner", None) or not isinstance(body, dict) or body.get("read_remote") is not True:
            return self.api.request(method, url, **kwargs)
        ctx = self._identity(owner, run_id, body.get("revision"))
        if ctx is None:
            return self.api.request(method, url, **kwargs)
        token = _CONTEXT.set(ctx)
        try:
            return self.api.request(method, url, **kwargs)
        finally:
            _CONTEXT.reset(token)

    def _identity(self, owner, run_id, revision):
        if type(revision) is not int or not _canonical_uuid(owner) or not _canonical_uuid(run_id):
            return None
        with self.store.lock:
            task = self.store.get("task", owner)
            if not isinstance(task, dict) or task.get("id") != owner or task.get("revision") != revision:
                return None
            app_id = task.get("dify_app_id")
            environment_id = task.get("environment_id")
            if not _canonical_uuid(app_id) or not _canonical_uuid(environment_id):
                return None
            runs = [r for r in task.get("runs", []) if isinstance(r, dict) and r.get("id") == run_id and r.get("kind") == "run"]
            if len(runs) != 1:
                return None
            run = runs[0]
            if task.get("app_type") not in SUPPORTED_APP_TYPES or run.get("app_type") != task.get("app_type"):
                return None
            if run.get("app_id") != app_id or run.get("revision") != revision or run.get("environment_id") != environment_id:
                return None
            if run.get("status") == "pending":
                return None
            env = self.store.get("environment", environment_id)
            if not isinstance(env, dict) or env.get("id") != environment_id:
                return None
            if run.get("environment_binding") != _binding(env):
                return None
        return _DiagnosticContext(self.store, self.boundary, owner, run_id, revision, app_id, environment_id, run.get("environment_binding"))


def context_active():
    """Return whether an exact diagnostic context is active in this thread."""
    return _CONTEXT.get() is not None


def context_identity():
    """Return allowed identity metadata (never a secret) or ``None``."""
    ctx = _CONTEXT.get()
    if ctx is None:
        return None
    return {"owner": ctx.owner, "run_id": ctx.run_id, "revision": ctx.revision,
            "app_id": ctx.app_id, "environment_id": ctx.environment_id, "purpose": ctx.purpose}
