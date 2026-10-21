"""Explicit Dify 1.17.1 adapters. Console and service credentials are separate."""
from __future__ import annotations

import base64
import httpx
from .providers import checked_url


class DifyError(ValueError):
    def __init__(self, message, *, result=None, http_status=None, code=None):
        super().__init__(message)
        # A successful HTTP response can still describe a failed workflow.
        # Keep that known result separately; never append bodies to public errors.
        self.result = result
        self.http_status = http_status
        self.code = code


class DifyClient:
    def __init__(self, env, store):
        self.env = env
        self.store = store
        base = checked_url(env["base_url"])
        # Environment points to the instance root, not an arbitrary API endpoint.
        self.base = base.rstrip("/")

    async def request(self, method, path, *, credential, secret_owner=None, _console_refreshed=False, **kwargs):
        if secret_owner is not None and credential != "dataset_api_key":
            raise DifyError("独立资源凭据只允许用于该知识库服务 API。")
        key = self.store.secret(secret_owner or self.env["id"], credential)
        if credential == 'console_token':
            from .console_connection import expiry
            from .console_reauth import available,refresh
            import time
            expires = expiry(key)
            if not key or (expires is not None and expires <= time.time()):
                current = self.store.get('environment', self.env['id'])
                if not _console_refreshed and current and available(self.store,current):
                    await refresh(self,key)
                    _console_refreshed=True
                    key=self.store.secret(self.env['id'],credential)
                    expires=expiry(key)
                if not key or (expires is not None and expires <= time.time()):
                    if current and current.get('console_login_blocked'):
                        raise DifyError('此环境自动登录已暂停；请查看最近失败诊断，原操作不会重发。', code='automatic_login_paused')
                    raise DifyError('Sierra 保存的 Dify 管理令牌已过期或缺失，未发送本次请求。请在 Sierra 环境中连接并选择加密保存登录资料；在 Dify 页面登录不会更新此连接。', code='console_credentials_missing')
        if not key:
            raise DifyError(f'缺少 {credential} 凭据；管理、应用运行和知识库访问使用不同凭据。')
        headers = {"Authorization": "Bearer " + key}
        csrf = self.store.secret(self.env["id"], "csrf_token")
        if credential == "console_token" and csrf:
            headers["X-CSRF-Token"] = csrf
            # Dify verifies header AND cookie, including secure host-prefixed deployments.
            headers["Cookie"] = f"csrf_token={csrf}; __Host-csrf_token={csrf}"
        try:
            async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
                response = await client.request(method, self.base + path, headers=headers, **kwargs)
            if response.is_error:
                if credential == 'console_token' and response.status_code == 401:
                    from .console_reauth import available,refresh
                    current=self.store.get('environment',self.env['id'])
                    if not _console_refreshed and current and available(self.store,current):
                        await refresh(self,key)
                        if method.upper()=='GET':
                            return await self.request(method,path,credential=credential,_console_refreshed=True,**kwargs)
                        raise DifyError('Dify 管理请求返回 HTTP 401，已更新管理凭据；原写入未自动重发，请先核对操作状态。',http_status=401)
                    if _console_refreshed:
                        with self.store.lock:
                            current=self.store.get('environment',self.env['id'])
                            if (current and all(current.get(k)==self.env.get(k) for k in ('base_url','version','connection_revision'))
                                    and self.store.secret(self.env['id'],'console_token')==key and available(self.store,current)):
                                from .console_failures import record
                                record(self.store, current, DifyError('fresh token rejected', code='refreshed_token_rejected', http_status=401), automatic=True)
                        raise DifyError('自动登录后的管理令牌仍返回 HTTP 401，已暂停自动登录；未再次登录或重发。请核对原环境权限。',http_status=401,code='refreshed_token_rejected')
                    raise DifyError('Dify 管理连接返回 HTTP 401，当前管理凭据不可用。请在 Sierra 的 Dify 环境中重新使用邮箱密码连接；在 Dify 页面登录不会更新此连接。没有自动重新登录或重发本次操作。', http_status=401, code='console_http_error')
                raise DifyError(f"Dify 返回 HTTP {response.status_code}。请核对所选环境的接口权限、凭据类型及版本。", http_status=response.status_code, code="console_http_error")
            if response.status_code == 204:
                return {}
            return response.json()
        except httpx.TimeoutException as exc:
            raise DifyError("Dify 请求超时。外部写入结果可能未知，请先核对，不要直接重复创建。", code="console_timeout") from exc
        except httpx.RequestError as exc:
            raise DifyError("无法连接目标 Dify 环境。可以继续生成待验证 DSL。", code="console_unreachable") from exc
        except ValueError as exc:
            if isinstance(exc, DifyError):
                raise
            raise DifyError("Dify 返回的内容不是预期 JSON，可能是登录页面或接口不兼容。", code="console_response_invalid") from exc

    async def login(self, email: str, password: str):
        """Authenticate once and verify console access before returning transient tokens."""
        phase = 'login'
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.post(self.base + "/console/api/login", json={
                    "email": email, "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
                    "remember_me": False,
                })
                if response.status_code != 200:
                    raise DifyError(f"Dify 登录未成功（HTTP {response.status_code}）。不会自动注册或重试。", code='login_rejected', http_status=response.status_code)
                if response.json().get("result") != "success":
                    raise DifyError("Dify 登录未成功，请核对账号权限及登录方式。", code='login_rejected', http_status=response.status_code)
                cookies = {c.name: c.value for c in response.cookies.jar}
                prefix = "__Host-" if "__Host-access_token" in cookies else ""
                access = cookies.get(prefix + "access_token", "")
                csrf = cookies.get(prefix + "csrf_token", "")
                if not access or not csrf or any(len(t) > 16384 or any(c.isspace() or c in ';,\r\n' for c in t) for t in (access, csrf)):
                    raise DifyError("Dify 未返回完整、有效的登录 Cookie；当前仅适配 1.17.1 邮箱密码登录。", code='login_cookies_invalid')
                phase = 'probe'
                probe = await client.get(self.base + "/console/api/apps", params={"page": 1, "limit": 1},
                    headers={"Authorization": "Bearer " + access, "X-CSRF-Token": csrf,
                             "Cookie": f"{prefix}access_token={access}; {prefix}csrf_token={csrf}"})
                if probe.status_code != 200 or not isinstance(probe.json().get("data"), list):
                    raise DifyError("登录后的应用列表读取未通过；原有连接凭据保留，请检查工作空间权限。", code='login_probe_failed', http_status=probe.status_code)
                return {"console_token": access, "csrf_token": csrf}
        except httpx.TimeoutException as exc:
            raise DifyError("Dify 登录连接超时。不会自动重试。", code='login_timeout' if phase == 'login' else 'login_probe_timeout') from exc
        except httpx.RequestError as exc:
            raise DifyError("无法连接目标 Dify 登录接口或登录核对接口。", code='login_unreachable' if phase == 'login' else 'login_probe_unreachable') from exc
        except (ValueError, AttributeError) as exc:
            if isinstance(exc, DifyError): raise
            raise DifyError("Dify 登录接口返回不兼容的内容；原有凭据未替换。", code='login_response_invalid' if phase == 'login' else 'login_probe_response_invalid') from exc

    async def login_workspace(self, tokens):
        """Verify fresh login tokens before committing them to a pinned connection."""
        try:
            csrf = tokens['csrf_token']
            headers = {'Authorization': 'Bearer ' + tokens['console_token'], 'X-CSRF-Token': csrf,
                       'Cookie': f'csrf_token={csrf}; __Host-csrf_token={csrf}'}
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.get(self.base + '/console/api/workspaces/current/summary', headers=headers)
            if response.status_code != 200:
                raise DifyError('工作空间身份接口未成功返回，原凭据未替换。', code='workspace_probe_failed', http_status=response.status_code)
            value = response.json()
            ident = value.get('id') if isinstance(value, dict) else None
            if not isinstance(ident, str) or not 1 <= len(ident) <= 200 or any(c.isspace() for c in ident):
                raise DifyError('无法核对新登录令牌的工作空间，原凭据未替换。', code='workspace_response_invalid')
            return ident
        except httpx.TimeoutException:
            raise DifyError('工作空间核对超时，原凭据未替换。', code='workspace_timeout') from None
        except httpx.RequestError:
            raise DifyError('无法连接工作空间身份接口，原凭据未替换。', code='workspace_unreachable') from None
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, DifyError): raise
            raise DifyError('新登录的工作空间核对未通过，原凭据未替换；不会自动重试。', code='workspace_response_invalid') from None

    async def test(self):
        # Authenticated console query, not just public health.
        return await self.request("GET", "/console/api/apps", credential="console_token", params={"page": 1, "limit": 1})

    async def datasets(self, page=1, limit=100):
        return await self.request("GET", "/v1/datasets", credential="dataset_api_key", params={"page": page, "limit": limit})

    async def models(self, model_type="llm"):
        return await self.request("GET", "/console/api/workspaces/current/models/model-types/" + model_type, credential="console_token")

    async def model_parameters(self, provider_path, model):
        return await self.request("GET", "/console/api/workspaces/current/model-providers/" + provider_path + "/models/parameter-rules", credential="console_token", params={"model": model})

    async def console_datasets(self, page=1, limit=100):
        return await self.request("GET", "/console/api/datasets", credential="console_token", params={"page": page, "limit": limit})

    async def workspace(self):
        return await self.request("GET", "/console/api/workspaces/current/summary", credential="console_token")

    async def create_dataset(self, name, description, strategy, *, timeout=90):
        return await self.request("POST", "/console/api/datasets", credential="console_token", timeout=timeout,
                                  json={"name": name, "description": description, "indexing_technique": strategy, "permission": "only_me"})

    async def create_scoped_dataset_key(self, dataset_id, *, timeout=90):
        return await self.request("POST", "/console/api/datasets/api-keys", credential="console_token", timeout=timeout, json={"dataset_ids": [dataset_id]})

    async def create_text_document(self, dataset_id, document, strategy, owner, *, embedding_provider=None, embedding_model=None, timeout=90):
        payload = {"name": document["name"], "text": document["text"], "indexing_technique": strategy,
                   "doc_form": "text_model", "doc_language": "Chinese Simplified", "process_rule": {"mode": "automatic"}}
        if strategy == "high_quality":
            payload.update(embedding_model_provider=embedding_provider, embedding_model=embedding_model)
        return await self.request("POST", f"/v1/datasets/{dataset_id}/document/create-by-text", credential="dataset_api_key", secret_owner=owner, timeout=timeout, json=payload)

    async def document_status(self, dataset_id, document_id):
        return await self.request("GET", f"/console/api/datasets/{dataset_id}/documents/{document_id}/indexing-status", credential="console_token")

    async def import_new(self, content, name):
        # No app_id: never silently overwrite an existing app.
        return await self.request("POST", "/console/api/apps/imports", credential="console_token", json={"mode": "yaml-content", "yaml_content": content, "name": name})

    async def export_dsl(self, app_id):
        import uuid
        try:app_id=str(uuid.UUID(app_id))
        except (ValueError,TypeError,AttributeError) as exc:raise DifyError('源应用 ID 无效，不能请求 Dify 导出。') from exc
        result=await self.request('GET',f'/console/api/apps/{app_id}/export',credential='console_token',params={'include_secret':'false'})
        if not isinstance(result,dict) or not isinstance(result.get('data'),str):raise DifyError('Dify 未返回有效 DSL；不能用旧文件冒充当前编辑草稿。')
        return result['data']

    async def app_triggers(self,app_id):
        import uuid
        try:target=str(uuid.UUID(app_id))
        except (ValueError,TypeError,AttributeError):raise DifyError('目标App ID无效，未请求触发器。') from None
        return await self.request('GET',f'/console/api/apps/{target}/triggers',credential='console_token')

    async def workflow_app_logs(self,app_id):
        import uuid
        try:target=str(uuid.UUID(app_id))
        except (ValueError,TypeError,AttributeError):raise DifyError('App ID无效，未请求日志。') from None
        return await self.request('GET',f'/console/api/apps/{target}/workflow-app-logs',credential='console_token',params={'page':1,'limit':20,'detail':False})

    async def workflow_run_detail(self,app_id,run_id):
        import uuid
        try:app=str(uuid.UUID(app_id));run=str(uuid.UUID(run_id))
        except (ValueError,TypeError,AttributeError):raise DifyError('App／运行UUID无效，未请求详情。') from None
        return await self.request('GET',f'/console/api/apps/{app}/workflow-runs/{run}',credential='console_token')

    async def disable_app_trigger(self,app_id,trigger_id):
        import uuid
        try:app=str(uuid.UUID(app_id));trigger=str(uuid.UUID(trigger_id))
        except (ValueError,TypeError,AttributeError):raise DifyError('目标App或触发器ID无效，未发送停用。') from None
        return await self.request('POST',f'/console/api/apps/{app}/trigger-enable',credential='console_token',json={'trigger_id':trigger,'enable_trigger':False})

    async def enable_app_trigger(self,app_id,trigger_id):
        import uuid
        try:app=str(uuid.UUID(app_id));trigger=str(uuid.UUID(trigger_id))
        except (ValueError,TypeError,AttributeError):raise DifyError('目标App或触发器UUID无效，未发送启用。') from None
        return await self.request('POST',f'/console/api/apps/{app}/trigger-enable',credential='console_token',json={'trigger_id':trigger,'enable_trigger':True})

    async def published_workflow(self,app_id):
        import uuid
        try:target=str(uuid.UUID(app_id))
        except (ValueError,TypeError,AttributeError):raise DifyError('目标App ID无效，未请求发布图。') from None
        return await self.request('GET',f'/console/api/apps/{target}/workflows/publish',credential='console_token')

    async def upload_runtime_file(self, filename, content, mime_type):
        return await self.request("POST", "/v1/files/upload", credential="service_api_key", files={"file":(filename,content,mime_type)}, data={"user":"flowcraft-local"})

    async def run_workflow(self, inputs):
        return await self.request("POST", "/v1/workflows/run", credential="service_api_key", json={"inputs": inputs, "response_mode": "blocking", "user": "flowcraft-local"})

    async def run_chatflow(self, query, inputs=None, conversation_id=None):
        payload = {"query": query, "inputs": inputs or {}, "response_mode": "blocking", "user": "flowcraft-local"}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        return await self.request("POST", "/v1/chat-messages", credential="service_api_key", json=payload)

    async def run_agent(self, query, inputs=None, *, conversation_id=None, seconds=90, should_stop=None):
        from .agent_stream import collect_agent
        return await collect_agent(self, query, inputs or {}, conversation_id=conversation_id, seconds=seconds, should_stop=should_stop)
